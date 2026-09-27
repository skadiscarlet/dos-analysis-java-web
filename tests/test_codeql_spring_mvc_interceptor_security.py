from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query, validate_database
from dosweb.reachability.extract import bind_entry_security_rows
from tests.test_codeql_hsweb_entry_security import _codeql_wrapper


RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
CODEQL = shutil.which("codeql")
JAVAC = shutil.which("javac")


@unittest.skipUnless(
    RUN_FIXTURES and CODEQL and JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class SpringMvcInterceptorEntrySecurityCodeqlTests(unittest.TestCase):
    def test_static_exclusions_and_helper_allowlists_bind_without_false_public_rows(self):
        root = Path(__file__).parents[1]
        source_root = (
            root
            / "tests"
            / "fixtures"
            / "spring_mvc_interceptor_security"
            / "src"
            / "main"
            / "java"
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            classes = temporary / "classes"
            classes.mkdir()
            java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
            database_path = temporary / "database"
            completed = subprocess.run(
                [
                    CODEQL,
                    "database",
                    "create",
                    str(database_path),
                    "--language=java",
                    f"--source-root={source_root}",
                    f"--command={JAVAC} -d {classes} "
                    + " ".join(str(path) for path in java_files),
                    "--overwrite",
                ],
                cwd=source_root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            database = validate_database(database_path)
            result = run_query(
                root / "codeql" / "dosweb" / "Entries" / "EntrySecurity.ql",
                database,
                temporary / "results",
                codeql_binary=str(_codeql_wrapper(temporary)),
            )
            rows = decode_bqrs_json(
                "entry_security",
                json.loads(result.decoded_path.read_text(encoding="utf-8")),
                DecodeSource(database.source_root, result.query_sha256),
            )

        public_rows = [
            row
            for row in rows
            if row["kind"] == "security_filter_chain"
            and row["value"] == "unauthenticated_filter"
            and row["coverage_status"] == "complete"
            and row["coverage_note"]
            in {
                "spring_mvc_security_interceptor_excluded_path",
                "spring_mvc_security_interceptor_helper_prefix_allowlist",
                "spring_mvc_security_interceptor_helper_exact_allowlist",
            }
        ]
        by_route = {str(row["route_or_event"]): row for row in public_rows}
        self.assertEqual(
            {
                "/gw/api/**",
                "/commons/barcode/render",
                "/commons/barcode/render-qr",
                "/commons/barcode/render-auto",
                "/exact-public",
            },
            set(by_route),
            public_rows,
        )
        self.assertEqual(
            by_route["/gw/api/**"]["coverage_note"],
            "spring_mvc_security_interceptor_excluded_path",
        )
        self.assertEqual(
            by_route["/commons/barcode/render-qr"]["coverage_note"],
            "spring_mvc_security_interceptor_helper_prefix_allowlist",
        )
        self.assertEqual(
            by_route["/exact-public"]["coverage_note"],
            "spring_mvc_security_interceptor_helper_exact_allowlist",
        )
        for negative in (
            "/commons/barcode/private",
            "/exact-public-child",
            "/gw/private",
            "/logging-only/open",
            "/forbidden-excluded/open",
            "/wrong-status/open",
            "/inverted/open",
        ):
            self.assertNotIn(negative, by_route, public_rows)

        annotation_rows = [
            row
            for row in rows
            if row["coverage_note"]
            == "spring_mvc_annotation_absent_interceptor_bypass"
        ]
        self.assertEqual(
            {"/ordered/open", "/unordered/open"},
            {row["route_or_event"] for row in annotation_rows},
            annotation_rows,
        )
        self.assertFalse(
            any(row["route_or_event"] == "/ordered/protected" for row in annotation_rows),
            annotation_rows,
        )

        ordered_filter_rows = [
            row
            for row in rows
            if row["handler_fqn"].endswith("OrderedBodyFilter.doFilter")
            and row["value"] == "unauthenticated_filter"
        ]
        self.assertEqual(len(ordered_filter_rows), 1, ordered_filter_rows)
        self.assertEqual(ordered_filter_rows[0]["route_or_event"], "")
        self.assertEqual(ordered_filter_rows[0]["coverage_status"], "complete")
        self.assertEqual(
            ordered_filter_rows[0]["coverage_note"],
            "ordered_servlet_filter_precedes_annotation_gated_mvc_interceptor",
        )
        self.assertFalse(
            any(
                row["handler_fqn"].endswith("UnorderedBodyFilter.doFilter")
                and row["value"] == "unauthenticated_filter"
                for row in rows
            ),
            rows,
        )

        entries: list[dict[str, object]] = []
        for index, route in enumerate(
            (
                "GET /gw/api/open",
                "GET /commons/barcode/render-qr",
                "GET /exact-public",
                "GET /gw/private",
            ),
            1,
        ):
            entries.append(
                {
                    "entry_id": f"entry:{index}",
                    "route_or_event": route,
                    "handler": {
                        "callable": f"fixture.Handler{index}.handle",
                        "file": "fixture/Handler.java",
                        "start_line": index,
                    },
                }
            )
        facts = bind_entry_security_rows(public_rows, entries)
        self.assertEqual(
            {"entry:1", "entry:2", "entry:3"},
            {fact.entry_id for fact in facts},
            facts,
        )
