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
class ShiroEntrySecurityCodeqlTests(unittest.TestCase):
    def _security_rows(self, temporary: Path, *, dynamic: bool = False) -> list[dict[str, object]]:
        root = Path(__file__).parents[1]
        base = root / "tests" / "fixtures" / "shiro_entry_security" / "src" / "main" / "java"
        source_root = temporary / "source"
        shutil.copytree(base, source_root)
        if dynamic:
            overlay = (
                root
                / "tests"
                / "fixtures"
                / "shiro_entry_security_dynamic"
                / "src"
                / "main"
                / "java"
            )
            shutil.copytree(overlay, source_root, dirs_exist_ok=True)
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
        return decode_bqrs_json(
            "entry_security",
            json.loads(result.decoded_path.read_text(encoding="utf-8")),
            DecodeSource(database.source_root, result.query_sha256),
        )

    @staticmethod
    def _shiro_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
        return [row for row in rows if str(row["coverage_note"]).startswith("shiro_")]

    def test_ordered_linked_hash_map_uses_first_matching_static_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._shiro_rows(self._security_rows(Path(tmp)))

        complete = {
            str(row["route_or_event"]): str(row["value"])
            for row in rows
            if row["coverage_status"] == "complete"
        }
        self.assertEqual("unauthenticated_filter", complete["/public/open"])
        for route in (
            "/session/open",
            "/fallback/open",
            "/late-public/open",
            "/hash-only/open",
            "/uncommitted/open",
            "/test/user/save",
        ):
            self.assertEqual("low_privilege_filter", complete[route], (route, rows))
        for route in ("/role/open", "/perm/open", "/admin/open"):
            self.assertEqual("privileged_filter", complete[route], (route, rows))
        self.assertNotIn("/conflict/open", complete, rows)
        self.assertTrue(
            any(
                row["route_or_event"] == "/conflict/open"
                and row["value"] == "security_matcher_unknown"
                and row["coverage_status"] == "partial"
                and row["coverage_note"] == "shiro_conflicting_filter_chain"
                for row in rows
            ),
            rows,
        )

        entries = [
            {
                "entry_id": "entry:target",
                "route_or_event": "POST /test/user/save",
                "handler": {
                    "callable": "fixture.shiro.PrefixedShiroController.save",
                    "file": "fixture/shiro/ShiroSecurityFixture.java",
                    "start_line": 1,
                },
            }
        ]
        facts = bind_entry_security_rows(rows, entries)
        self.assertEqual(len(facts), 1, facts)
        self.assertEqual(facts[0].value, "low_privilege_filter")

    def test_dynamic_ordered_rule_forces_partial_for_static_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._shiro_rows(self._security_rows(Path(tmp), dynamic=True))

        self.assertTrue(
            any(
                row["route_or_event"] == "/test/user/save"
                and row["value"] == "security_matcher_unknown"
                and row["coverage_status"] == "partial"
                and row["coverage_note"] == "shiro_dynamic_rule_precedence_unresolved"
                for row in rows
            ),
            rows,
        )
