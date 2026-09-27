from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query, validate_database


RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
CODEQL = shutil.which("codeql")
JAVAC = shutil.which("javac")


def _selected_pack_search_path() -> str:
    packages = Path.home() / ".codeql" / "packages"
    java_versions = sorted((packages / "codeql" / "java-all").glob("*/qlpack.yml"))
    if not java_versions:
        raise unittest.SkipTest("A local codeql/java-all package is unavailable.")
    pending = [java_versions[-1].parent]
    selected: dict[str, Path] = {}
    while pending:
        pack = pending.pop()
        manifest = yaml.safe_load((pack / "qlpack.yml").read_text(encoding="utf-8"))
        name = manifest["name"]
        if name in selected:
            continue
        selected[name] = pack
        for dependency, version in (manifest.get("dependencies") or {}).items():
            candidate = packages / dependency / str(version)
            if not candidate.joinpath("qlpack.yml").is_file():
                raise unittest.SkipTest(
                    f"Local CodeQL dependency is unavailable: {dependency}@{version}"
                )
            pending.append(candidate)
    return os.pathsep.join(str(path) for path in selected.values())


def _codeql_wrapper(directory: Path) -> Path:
    wrapper = directory / "codeql-with-local-packs"
    wrapper.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = query ] && [ \"$2\" = run ]; then\n"
        f"  exec {CODEQL} \"$@\" --search-path={_selected_pack_search_path()}\n"
        "fi\n"
        f"exec {CODEQL} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    return wrapper


@unittest.skipUnless(
    RUN_FIXTURES and CODEQL and JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class HswebEntrySecurityCodeqlTests(unittest.TestCase):
    def _security_rows(
        self, fixture: str, temporary: Path, *overlays: str
    ) -> list[dict[str, object]]:
        root = Path(__file__).parents[1]
        assembled = temporary / "source"
        shutil.copytree(
            root / "tests" / "fixtures" / fixture / "src" / "main" / "java",
            assembled,
        )
        for overlay in overlays:
            shutil.copytree(
                root / "tests" / "fixtures" / overlay / "src" / "main" / "java",
                assembled,
                dirs_exist_ok=True,
            )
        classes = temporary / "classes"
        classes.mkdir()
        java_files = sorted(path.relative_to(assembled) for path in assembled.rglob("*.java"))
        database_path = temporary / "database"
        completed = subprocess.run(
            [
                CODEQL,
                "database",
                "create",
                str(database_path),
                "--language=java",
                f"--source-root={assembled}",
                f"--command={JAVAC} -d {classes} "
                + " ".join(str(path) for path in java_files),
                "--overwrite",
            ],
            cwd=assembled,
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
    def _method_rows(
        rows: list[dict[str, object]], method: str
    ) -> list[dict[str, object]]:
        return [row for row in rows if str(row["handler_fqn"]).endswith("." + method)]

    def test_match_if_missing_true_is_complete_default_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._security_rows("deployment_entry_security", Path(tmp))

        default_enabled = self._method_rows(rows, "defaultEnabled")
        self.assertTrue(
            any(
                row["kind"] == "deployment_gate"
                and row["value"] == "default_enabled"
                and row["coverage_status"] == "complete"
                and row["coverage_note"]
                == "conditional_property_match_if_missing_default_enabled"
                for row in default_enabled
            ),
            default_enabled,
        )
        gated = self._method_rows(rows, "explicitlyGated")
        self.assertTrue(
            any(
                row["value"] == "conditional_property:captcha.image.enabled=true"
                and row["coverage_status"] == "complete"
                for row in gated
            ),
            gated,
        )

    def test_no_hsweb_universe_does_not_invent_public_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._security_rows("deployment_entry_security", Path(tmp))

        self.assertEqual(self._method_rows(rows, "noHswebUniverse"), [], rows)

    def test_default_hsweb_parser_emits_public_only_for_proven_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._security_rows("hsweb_entry_security", Path(tmp))

        self.assertEqual(self._method_rows(rows, "internalHelper"), [], rows)

        for method in ("plain", "anonymous", "ignored", "methodIgnoreWins", "inheritedIgnore"):
            method_rows = self._method_rows(rows, method)
            self.assertTrue(
                any(
                    row["kind"] == "annotation"
                    and row["value"] == "unauthenticated_annotation"
                    and row["coverage_status"] == "complete"
                    for row in method_rows
                ),
                (method, method_rows),
            )

        for method in (
            "resourceProtected",
            "actionProtected",
            "inheritedResource",
            "methodAuthorizeOverridesClassIgnore",
        ):
            method_rows = self._method_rows(rows, method)
            self.assertFalse(
                any(row["value"] == "unauthenticated_annotation" for row in method_rows),
                (method, method_rows),
            )
            self.assertTrue(
                any(
                    row["kind"] == "dependency_coverage"
                    and row["coverage_status"] == "partial"
                    for row in method_rows
                ),
                (method, method_rows),
            )

    def test_composed_hsweb_annotations_stay_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._security_rows("hsweb_entry_security", Path(tmp))

        for method in ("composedAnnotation", "composedDimension"):
            method_rows = self._method_rows(rows, method)
            self.assertFalse(
                any(row["value"] == "unauthenticated_annotation" for row in method_rows),
                (method, method_rows),
            )
            self.assertTrue(
                any(
                    row["kind"] == "dependency_coverage"
                    and row["coverage_status"] == "partial"
                    and row["coverage_note"] == "hsweb_composed_annotation_unmodeled"
                    for row in method_rows
                ),
                (method, method_rows),
            )

    def test_non_hsweb_security_annotation_forces_partial_hsweb_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._security_rows("hsweb_entry_security", Path(tmp))

        method_rows = self._method_rows(rows, "springSecurityConflict")
        self.assertFalse(
            any(row["value"] == "unauthenticated_annotation" for row in method_rows),
            method_rows,
        )
        self.assertTrue(
            any(
                row["kind"] == "dependency_coverage"
                and row["coverage_status"] == "partial"
                and row["coverage_note"] == "hsweb_conflicting_security_model"
                for row in method_rows
            ),
            method_rows,
        )

    def test_customizer_prevents_ignore_or_empty_definition_from_being_public(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._security_rows(
                "hsweb_entry_security",
                Path(tmp),
                "hsweb_entry_security_customizer",
            )

        for method in ("plain", "ignored"):
            method_rows = self._method_rows(rows, method)
            self.assertFalse(
                any(row["value"] == "unauthenticated_annotation" for row in method_rows),
                (method, method_rows),
            )
            self.assertTrue(
                any(
                    row["kind"] == "dependency_coverage"
                    and row["coverage_status"] == "partial"
                    and row["coverage_note"] == "hsweb_customizer_precedes_default_parser"
                    for row in method_rows
                ),
                (method, method_rows),
            )

    def test_parser_override_keeps_hsweb_authorization_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = self._security_rows(
                "hsweb_entry_security",
                Path(tmp),
                "hsweb_entry_security_parser_override",
            )

        method_rows = self._method_rows(rows, "plain")
        self.assertFalse(
            any(row["value"] == "unauthenticated_annotation" for row in method_rows),
            method_rows,
        )
        self.assertTrue(
            any(
                row["kind"] == "dependency_coverage"
                and row["coverage_status"] == "partial"
                and row["coverage_note"] == "hsweb_default_parser_replaced"
                for row in method_rows
            ),
            method_rows,
        )
