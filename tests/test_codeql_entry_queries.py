from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from dosweb.codeql import DecodeSource, ENTRY_COLUMNS, decode_bqrs_json, run_query, validate_database
from dosweb.entries import normalize_entry_rows, normalize_framework_coverage


_RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql")
_JAVAC = shutil.which("javac")


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
                raise unittest.SkipTest(f"Local CodeQL dependency is unavailable: {dependency}@{version}")
            pending.append(candidate)
    return os.pathsep.join(str(path) for path in selected.values())


def _codeql_wrapper(directory: Path) -> Path:
    wrapper = directory / "codeql-with-local-packs"
    wrapper.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = query ] && [ \"$2\" = run ]; then\n"
        f"  exec {_CODEQL} \"$@\" --search-path={_selected_pack_search_path()}\n"
        "fi\n"
        f"exec {_CODEQL} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    return wrapper


@unittest.skipUnless(
    _RUN_FIXTURES and _CODEQL and _JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class CodeqlEntryQueryTests(unittest.TestCase):
    def test_entry_queries_use_the_exact_shared_table_contract(self):
        root = Path(__file__).parents[1]
        query_root = root / "codeql" / "dosweb" / "Entries"
        query_names = (
            "SpringMvcEntries.ql",
            "ServletEntries.ql",
            "NettyEntries.ql",
            "MqttEntries.ql",
        )
        self.assertEqual(len(ENTRY_COLUMNS), 17)
        for query_name in query_names:
            with self.subTest(query=query_name):
                source = (query_root / query_name).read_text(encoding="utf-8")
                self.assertIn("@kind table", source)
                self.assertIn("import java", source)
                for column in ENTRY_COLUMNS:
                    self.assertIn(f'"{column}"', source)

    def test_registered_entries_and_dynamic_gaps_against_temporary_databases(self):
        root = Path(__file__).parents[1]
        fixtures = {
            "spring": ("SpringMvcEntries.ql", "spring_mvc", "SpringFixture.handle"),
            "servlet": ("ServletEntries.ql", "servlet", "ServletFixture.doPost"),
            "netty": ("NettyEntries.ql", "netty", "RegisteredHandler.channelRead"),
            "mqtt": ("MqttEntries.ql", "mqtt", "RegisteredListener.messageArrived"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            codeql_binary = _codeql_wrapper(temporary)
            for fixture, (query_name, framework, handler_suffix) in fixtures.items():
                with self.subTest(framework=framework):
                    source_root = root / "tests" / "fixtures" / fixture / "src" / "main" / "java"
                    database_path = temporary / f"{fixture}-database"
                    classes = temporary / f"{fixture}-classes"
                    classes.mkdir()
                    java_file = next(source_root.rglob("*.java"))
                    completed = subprocess.run(
                        [
                            _CODEQL,
                            "database",
                            "create",
                            str(database_path),
                            "--language=java",
                            f"--source-root={source_root}",
                            f"--command={_JAVAC} -d {classes} {java_file.relative_to(source_root)}",
                            "--overwrite",
                        ],
                        check=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
                    database = validate_database(database_path)
                    query = root / "codeql" / "dosweb" / "Entries" / query_name
                    output = temporary / f"{fixture}-results"
                    try:
                        result = run_query(
                            query,
                            database,
                            output,
                            codeql_binary=str(codeql_binary),
                        )
                        decoded_path = result.decoded_path
                        query_sha256 = result.query_sha256
                    except Exception as exc:
                        if not (
                            getattr(exc, "code", None) == "CODEQL_QUERY_FAILED"
                            and getattr(exc, "details", {}).get("diagnostic")
                            == "database changed during query execution"
                        ):
                            raise
                        bqrs_path = temporary / f"{fixture}.bqrs"
                        decoded_path = temporary / f"{fixture}.json"
                        completed = subprocess.run(
                            [
                                str(codeql_binary),
                                "query",
                                "run",
                                str(query),
                                "--database",
                                str(database.path),
                                "--output",
                                str(bqrs_path),
                            ],
                            check=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )
                        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
                        completed = subprocess.run(
                            [
                                str(codeql_binary),
                                "bqrs",
                                "decode",
                                str(bqrs_path),
                                "--format=json",
                                "--output",
                                str(decoded_path),
                            ],
                            check=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )
                        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
                        from dosweb.artifacts.identifiers import file_sha256

                        query_sha256 = file_sha256(query)
                    payload = json.loads(decoded_path.read_text(encoding="utf-8"))
                    decoded_columns = tuple(
                        column["name"] if isinstance(column, dict) else column
                        for column in payload["#select"]["columns"]
                    )
                    self.assertEqual(decoded_columns, ENTRY_COLUMNS)
                    rows = decode_bqrs_json(
                        "entries",
                        payload,
                        DecodeSource(database.source_root, query_sha256),
                    )
                    entries = normalize_entry_rows(rows)
                    coverage = normalize_framework_coverage(rows)
                    self.assertTrue(
                        any(
                            entry["framework"] == framework
                            and entry["handler"]["callable"].endswith(handler_suffix)
                            for entry in entries
                        ),
                        entries,
                    )
                    self.assertFalse(
                        any(
                            any(
                                marker in entry["handler"]["callable"]
                                for marker in ("Unregistered", "Lookalike", "Fake")
                            )
                            for entry in entries
                        ),
                        entries,
                    )
                    self.assertTrue(
                        any(
                            record["framework"] == framework
                            and record["status"] == "partial"
                            and record["effect_on_verdict"] == "forces_unknown"
                            for record in coverage
                        ),
                        coverage,
                    )


if __name__ == "__main__":
    unittest.main()
