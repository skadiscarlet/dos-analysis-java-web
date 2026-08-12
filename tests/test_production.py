from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from dosweb.cli import main, parse_cli_values
from dosweb.codeql import DatabaseInfo, QueryResult
from dosweb.codeql.decoder import (
    BOUND_COLUMNS,
    ENTRY_COLUMNS,
    FLOW_COLUMNS,
    GROWTH_COLUMNS,
    GUARD_COLUMNS,
    RELEASE_COLUMNS,
)
from dosweb.entries import AttackerInputFact, EntryFact, HandlerFact, RegistrationFact
from dosweb.errors import AnalyzerError
from dosweb.growth import (
    AttackerInfluence,
    DemandInput,
    GrowthCandidate,
    GrowthContract,
    SourceExcerpt,
    SourceLocation,
)
from dosweb.lifecycle import BoundDecision, DecisionCheck, GuardDecision, ReleaseDecision
from dosweb.pipeline import STAGES, StageContext, StageFingerprint, StageOutput
from dosweb.production import build_production_pipeline
import dosweb.production as production


class ProductionFactoryTests(unittest.TestCase):
    """Network-free RED contract for the first production factory slice."""

    def _values(self, root: Path, *, allow_remote_llm: bool | None = None) -> dict[str, object]:
        values: dict[str, object] = {
            "command": "analyze",
            "database": root / "database",
            "output": root / "output",
            "config": None,
            "allow_remote_llm": allow_remote_llm,
            "public_source_url": "https://github.com/example/project",
            "source_commit_sha": "a" * 40,
            "source_checkout": root,
            "model": None,
            "base_url": None,
            "timeout_seconds": None,
            "max_retries": None,
            "temperature": None,
            "cache_dir": None,
            "codeql_binary": "codeql",
            "resume": False,
        }
        return values

    def _fake_executors(self, calls: list[str], secret: str = "", *, fail: bool = False):
        def execute(context: StageContext) -> StageOutput:
            calls.append(context.stage)
            if fail:
                raise RuntimeError(secret)
            # A production executor must not copy credentials into durable output.
            return StageOutput(
                {f"{context.stage}.jsonl": [{"stage": context.stage, "value": "ok"}]},
                {"executor": "fake"},
            )

        return {stage: execute for stage in STAGES}

    def test_factory_loads_config_and_injects_environment_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=False),
                environ={"DEEPSEEK_API_KEY": "unused-secret"},
                stage_executors=self._fake_executors(calls),
            )
            self.assertEqual(pipeline.output_root, root / "output")
            self.assertEqual(pipeline.run("entries")["status"], "completed")
            self.assertEqual(calls, ["entries"])

    def test_entries_does_not_require_an_unused_remote_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            values = self._values(root, allow_remote_llm=True)
            values["command"] = "entries"
            pipeline = build_production_pipeline(
                values,
                environ={},
                stage_executors=self._fake_executors(calls),
            )
            self.assertEqual(pipeline.run("entries")["status"], "completed")
            self.assertEqual(calls, ["entries"])

    def test_complete_production_stages_require_consent_before_provider_or_codeql_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            validations: list[Path] = []

            def fake_validate(path: Path, **_kwargs: object) -> DatabaseInfo:
                validations.append(path)
                raise AssertionError("database validation must follow consent")

            with mock.patch("dosweb.production._query_pack_hash") as query_hash:
                pipeline = build_production_pipeline(
                    self._values(root),
                    environ={"DEEPSEEK_API_KEY": "provider-secret"},
                    validate_database_fn=fake_validate,
                )
                with self.assertRaises(AnalyzerError) as raised:
                    pipeline.run("analyze")

            self.assertEqual(raised.exception.code, "CONFIG_REMOTE_LLM_NOT_AUTHORIZED")
            self.assertEqual(calls, [])
            self.assertEqual(validations, [])
            query_hash.assert_not_called()
            self.assertFalse((root / "output" / "run.json").exists())

    def test_default_authorized_production_exposes_all_stages_without_provider_at_build_or_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values = self._values(root, allow_remote_llm=True)
            values["command"] = "entries"
            database = root / "database"
            source = root / "source"
            database.mkdir()
            source.mkdir()
            info = DatabaseInfo(database, root, "d" * 64)

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._entry_payload()), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            with mock.patch("dosweb.production.DeepSeekClient") as provider:
                pipeline = build_production_pipeline(
                    values,
                    environ={"DEEPSEEK_API_KEY": "provider-secret"},
                    validate_database_fn=lambda *_args, **_kwargs: info,
                    run_query_fn=fake_run,
                )
                self.assertEqual(pipeline._available_stages, frozenset(STAGES))  # noqa: SLF001
                self.assertEqual(pipeline.run("entries")["status"], "completed")
                provider.assert_not_called()

    def test_default_authorized_graph_exposes_provider_stage_without_constructing_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": "provider-secret"},
            )
            self.assertEqual(pipeline._available_stages, frozenset(STAGES))  # noqa: SLF001

    def test_api_key_is_absent_from_fingerprints_errors_and_artifacts(self) -> None:
        secret = "provider-secret-do-not-persist"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": secret},
                stage_executors=self._fake_executors(calls, secret),
            )
            pipeline.run("analyze")
            self.assertEqual(calls, list(STAGES))
            for path in (root / "output").rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret.encode(), path.read_bytes(), str(path))

            fingerprint = pipeline._fingerprint("entries", {})  # noqa: SLF001 - contract boundary test
            self.assertNotIn(secret, json.dumps(fingerprint.to_dict(), sort_keys=True))

    def test_provider_error_is_redacted_before_it_reaches_pipeline_metadata(self) -> None:
        secret = "provider-secret-do-not-persist"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": secret},
                stage_executors=self._fake_executors(calls, secret, fail=True),
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertNotIn(secret, str(raised.exception))
            run_path = root / "output" / "run.json"
            if run_path.exists():
                self.assertNotIn(secret, run_path.read_text(encoding="utf-8"))

    def _entry_payload(self) -> dict[str, object]:
        columns = [
            {"name": name, "kind": "String"}
            for name in (
                "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
                "registration_kind", "registration_fqn", "registration_file",
                "registration_start_line", "route_or_event", "auth_context",
                "attacker_input_name", "attacker_input_type", "attacker_input_kind",
                "materialization_phase", "coverage_status", "coverage_note",
            )
        ]
        return {
            "#select": {
                "columns": columns,
                "tuples": [[
                    "servlet", "http", "fixture.Handler.handle", "src/Handler.java", 10,
                    "annotation_mapping", "fixture.Handler", "src/Handler.java", 8,
                    "/items", "unknown", "body", "byte[]", "request_body", "in_handler",
                    "complete", "servlet_annotation_mapping",
                ]],
            }
        }

    def test_default_entries_executor_validates_runs_four_queries_and_publishes_exact_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            source.mkdir()
            info = DatabaseInfo(database, root, "d" * 64)
            validations: list[Path] = []
            query_databases: list[DatabaseInfo] = []
            queries: list[str] = []

            def fake_validate(path: Path, **_kwargs: object) -> DatabaseInfo:
                validations.append(path)
                return info

            def fake_run(query: Path, database_info: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                queries.append(query.name)
                query_databases.append(database_info)
                generation = output_dir / f"{query.stem}.json"
                generation.write_text(json.dumps(self._entry_payload()), encoding="utf-8")
                return QueryResult(
                    query_name="entries",
                    query_path=query,
                    bqrs_path=query,
                    decoded_path=generation,
                    query_sha256="a" * 64,
                    bqrs_sha256="b" * 64,
                )

            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            result = pipeline.run("entries")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(queries, [
                "SpringMvcEntries.ql", "ServletEntries.ql", "NettyEntries.ql", "MqttEntries.ql",
                "JaxRsEntries.ql", "GrpcEntries.ql",
            ])
            self.assertEqual(validations, [database])
            self.assertEqual(query_databases, [info] * 6)
            self.assertEqual(
                {path.name for path in (root / "output").iterdir()},
                {"entry_facts.jsonl", "coverage.json", "run.json", ".stage-manifests", ".pipeline.lock"},
            )
            self.assertEqual(
                {item["path"] for item in result["stages"]["entries"]["artifacts"]},
                {"entry_facts.jsonl", "coverage.json"},
            )
            self.assertNotIn("DEEPSEEK_API_KEY", (root / "output" / "run.json").read_text())
            self.assertEqual(pipeline._fingerprint("entries", {}).database_fingerprint, "d" * 64)  # noqa: SLF001
            self.assertRegex(pipeline._fingerprint("entries", {}).query_pack_hash, r"^[0-9a-f]{64}$")  # noqa: SLF001

    def test_default_entries_executes_the_preflight_query_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            source.mkdir()
            info = DatabaseInfo(database, root, "d" * 64)
            observed: list[tuple[Path, bytes]] = []

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                observed.append((query, query.read_bytes()))
                decoded = output_dir / f"{query.stem}.json"
                decoded.parent.mkdir(parents=True, exist_ok=True)
                decoded.write_text(json.dumps(self._entry_payload()), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            import dosweb.production as production

            pack_hash, snapshot = production._query_pack_snapshot()  # noqa: SLF001

            with mock.patch(
                "dosweb.production._query_pack_snapshot",
                return_value=(pack_hash, snapshot),
            ):
                pipeline = build_production_pipeline(
                    self._values(root),
                    environ={},
                    validate_database_fn=lambda *_args, **_kwargs: info,
                    run_query_fn=fake_run,
                )
                self.assertEqual(pipeline.run("entries")["status"], "completed")

            original = production._ENTRY_QUERY_DIR / "SpringMvcEntries.ql"  # noqa: SLF001
            self.assertNotEqual(observed[0][0], original)
            self.assertEqual(
                observed[0][1],
                snapshot["dosweb/Entries/SpringMvcEntries.ql"],
            )

    def test_default_preflight_rejects_invalid_database_validator_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: None,  # type: ignore[arg-type]
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_DATABASE_INVALID")
            self.assertFalse((root / "output" / "run.json").exists())

    def test_default_preflight_rejects_database_from_different_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "other-source"
            database.mkdir()
            source.mkdir()
            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: DatabaseInfo(
                    database, source, "d" * 64
                ),
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_DATABASE_INVALID")
            self.assertFalse((root / "output" / "run.json").exists())

    def test_default_preflight_runs_under_the_pipeline_output_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            info = DatabaseInfo(root / "database", root, "d" * 64)
            (root / "database").mkdir()
            (root / "source").mkdir()

            def fake_validate(_path: Path, **_kwargs: object) -> DatabaseInfo:
                lock_path = root / "output" / ".pipeline.lock"
                self.assertTrue(lock_path.exists())
                return info

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                generation = output_dir / f"{query.stem}.json"
                generation.write_text(json.dumps(self._entry_payload()), encoding="utf-8")
                return QueryResult(query.name, query, query, generation, "a" * 64, "b" * 64)

            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            self.assertEqual(pipeline.run("entries")["status"], "completed")

    def test_packaged_query_assets_are_available_to_the_default_executor(self) -> None:
        import dosweb.production as production

        expected = set(production._ENTRY_QUERIES)  # noqa: SLF001 - packaging contract
        packaged = {path.name for path in production._ENTRY_QUERY_DIR.glob("*.ql")}  # noqa: SLF001
        self.assertEqual(packaged, expected)
        self.assertTrue((production._QUERY_PACK_DIR / "qlpack.yml").is_file())  # noqa: SLF001
        self.assertTrue((production._QUERY_PACK_DIR / "codeql-pack.lock.yml").is_file())  # noqa: SLF001
        self.assertRegex(production._query_pack_hash(), r"^[0-9a-f]{64}$")  # noqa: SLF001

    def test_default_entries_executor_rejects_aggregate_row_overflow_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            info = DatabaseInfo(root / "database", root, "d" * 64)
            (root / "database").mkdir()
            (root / "source").mkdir()

            def fake_validate(_path: Path, **_kwargs: object) -> DatabaseInfo:
                return info

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                payload = self._entry_payload()
                payload["#select"]["tuples"] *= 1025  # type: ignore[index,operator]
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(payload), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")
            self.assertFalse((root / "output" / "entry_facts.jsonl").exists())

    def test_default_entries_executor_rejects_malformed_decoded_result_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            info = DatabaseInfo(root / "database", root, "d" * 64)
            (root / "database").mkdir()
            (root / "source").mkdir()

            def fake_validate(_path: Path, **_kwargs: object) -> DatabaseInfo:
                return info

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                malformed = output_dir / f"{query.stem}.json"
                malformed.write_text('{"#select":{"columns":[],"tuples":[]}}', encoding="utf-8")
                return QueryResult(query.name, query, query, malformed, "a" * 64, "b" * 64)

            pipeline = build_production_pipeline(
                self._values(root),
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_RESULT_INVALID")
            self.assertFalse((root / "output" / "entry_facts.jsonl").exists())

    def _entry_and_candidate(self, *, handler_line: int = 20) -> tuple[EntryFact, GrowthCandidate]:
        entry = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact("fixture.Handler.handle", "src/Handler.java", handler_line),
            registration=RegistrationFact("annotation_mapping", "fixture.Handler", "src/Handler.java", 8),
            route_or_event="/items",
            auth_context="unknown",
            attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
            materialization_phase="in_handler",
        )
        candidate = GrowthCandidate.create(
            site=SourceLocation("src/Handler.java", handler_line + 4),
            kind="input_materialization",
            operation="request.getInputStream().readAllBytes",
            resource_dimension="bytes",
            receiver="fixture.Handler.body",
            field_path="this.body",
            demand_inputs=(DemandInput("body", "value"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
        )
        return entry, candidate

    def test_candidate_entry_association_rejects_no_match_and_ambiguity(self) -> None:
        entry, candidate = self._entry_and_candidate()
        with self.assertRaises(AnalyzerError) as no_match:
            production._entry_for_candidate({}, candidate)  # noqa: SLF001
        self.assertEqual(no_match.exception.code, "ANALYSIS_GROWTH_ENTRY_AMBIGUOUS")
        other = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact("fixture.Other.handle", "src/Handler.java", 12),
            registration=RegistrationFact("annotation_mapping", "fixture.Other", "src/Handler.java", 8),
            route_or_event="/other",
            auth_context="unknown",
            attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
            materialization_phase="in_handler",
        )
        with self.assertRaises(AnalyzerError) as ambiguous:
            production._entry_for_candidate({entry.entry_id: entry, other.entry_id: other}, candidate)  # noqa: SLF001
        self.assertEqual(ambiguous.exception.code, "ANALYSIS_GROWTH_ENTRY_AMBIGUOUS")
        self.assertEqual(production._entry_for_candidate({entry.entry_id: entry}, candidate), entry)  # noqa: SLF001

    def _bqrs_payload(self, columns: tuple[str, ...], rows: list[list[object]]) -> dict[str, object]:
        return {"#select": {"columns": [{"name": name, "kind": "String"} for name in columns], "tuples": rows}}

    def test_injected_query_llm_and_source_seams_exercise_the_full_default_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"; database.mkdir()
            source = root / "source"; source.mkdir()
            info = DatabaseInfo(database, root, "d" * 64)
            query_calls: list[str] = []
            excerpt_calls: list[tuple[Path, str, str, int]] = []
            llm_calls: list[object] = []

            rows_by_query: dict[str, tuple[tuple[str, ...], list[list[object]]]] = {
                "SpringMvcEntries": (ENTRY_COLUMNS, [[
                    "spring_mvc", "http", "fixture.Handler.handle", "src/Handler.java", 20,
                    "annotation_mapping", "fixture.Handler", "src/Handler.java", 8, "/items",
                    "unknown", "body", "byte[]", "request_body", "in_handler", "complete",
                    "spring_annotation_mapping",
                ]]),
                "InputMaterialization": (GROWTH_COLUMNS, [[
                    "src/Handler.java", 24, "input_materialization", "request.readAllBytes",
                    "bytes", "fixture.Handler.body", "this.body", "body", "value", "request",
                    "fact:growth", "complete", "input_materialization",
                ]]),
                "EntryToGrowth": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "value", "body", "body",
                    "fixture.Handler.handle>request.readAllBytes", "in_handler", "data_flow", "proven",
                    "complete", "entry_to_growth",
                ]]),
                "GuardCandidates": (GUARD_COLUMNS, []),
                "BoundCandidates": (BOUND_COLUMNS, []),
                "SynchronousReleaseCandidates": (RELEASE_COLUMNS, []),
            }

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                query_calls.append(query.stem)
                if query.stem in rows_by_query:
                    columns, rows = rows_by_query[query.stem]
                else:
                    columns = ENTRY_COLUMNS if query.parent.name == "Entries" else GROWTH_COLUMNS
                    rows = []
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._bqrs_payload(columns, rows)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            def fake_excerpt(checkout: Path, commit: str, path: str, line: int) -> SourceExcerpt:
                import hashlib
                excerpt_calls.append((checkout, commit, path, line))
                content = f"attested line {line}\n"
                return SourceExcerpt(
                    f"excerpt:{line}", path, line, line, content, "c" * 64,
                    hashlib.sha256(content.encode()).hexdigest(),
                )

            class FakeLlm:
                def classify_growth(self, bounded: object) -> GrowthContract:
                    llm_calls.append(bounded)
                    return GrowthContract("unknown", "input_materialization", "bytes", (), "unknown", (), "high")

            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": "fixture-secret"},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
                deepseek_client=FakeLlm(),
                source_excerpt_fn=fake_excerpt,
            )
            result = pipeline.run("analyze")

            self.assertEqual(result["status"], "completed")
            self.assertTrue(all(result["stages"][stage]["status"] == "completed" for stage in STAGES))
            self.assertEqual(len(llm_calls), 1)
            self.assertEqual(len(excerpt_calls), 2)
            self.assertEqual({call[1] for call in excerpt_calls}, {"a" * 40})
            self.assertEqual({call[2:] for call in excerpt_calls}, {("src/Handler.java", 8), ("src/Handler.java", 24)})
            self.assertEqual(len(query_calls), 14)
            self.assertEqual(
                {item["path"] for item in result["stages"]["conclude"]["artifacts"]},
                {"lifecycle_certificates.jsonl", "static_findings.jsonl"},
            )
            self.assertEqual(
                {item["path"] for item in result["stages"]["report"]["artifacts"]},
                {"summary.json", "report.md"},
            )

    def test_lifecycle_decision_records_preserve_exact_boolean_checks_and_coverage(self) -> None:
        for decision in (
            GuardDecision("unknown", ("GUARD_CONFIGURATION_UNKNOWN",), (DecisionCheck("guard", False, "GUARD_CONFIGURATION_UNKNOWN", ("fact:g",)),), ("fact:g",), ("request.max",), ("guard:1",)),
            BoundDecision("effective", (), (DecisionCheck("bound", True, None, ("fact:b",)),), ("fact:b",), (), ("bound:1",)),
            ReleaseDecision("unknown", "potential_async", ("RELEASE_POTENTIAL_ASYNC",), (DecisionCheck("release", False, "RELEASE_POTENTIAL_ASYNC", ("fact:r",)),), ("fact:r",), ("consumer",), ("release:1",)),
        ):
            record = production._decision_record(decision)  # noqa: SLF001
            self.assertEqual([check["passed"] for check in record["checks"]], [item.passed for item in decision.checks])
            self.assertEqual(record["status"], decision.status)
            self.assertEqual(record["reason_codes"], list(decision.reason_codes))
            self.assertEqual(record["unresolved_facts"], list(decision.unresolved_facts))
        self.assertFalse(production._decision_record(ReleaseDecision("unknown", "potential_async", ("RELEASE_POTENTIAL_ASYNC",), (), (), ("consumer",), ())) ["checks"])  # noqa: SLF001

    def test_provider_failure_publishes_no_growth_or_downstream_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []

            def fail_growth(context: StageContext) -> StageOutput:
                calls.append(context.stage)
                if context.stage == "growth":
                    raise RuntimeError("provider failed")
                return StageOutput({f"{context.stage}.jsonl": [{"stage": context.stage}]})

            executors = {stage: fail_growth for stage in STAGES}
            pipeline = build_production_pipeline(self._values(root, allow_remote_llm=True), environ={"DEEPSEEK_API_KEY": "fixture-secret"}, stage_executors=executors)
            with self.assertRaises(AnalyzerError) as raised:
                pipeline.run("analyze")
            self.assertEqual(raised.exception.code, "ANALYSIS_STAGE_FAILED")
            self.assertEqual(calls, ["entries", "growth"])
            output = root / "output"
            self.assertFalse((output / "growth.jsonl").exists())
            self.assertFalse((output / "flows.jsonl").exists())
            self.assertFalse((output / "lifecycle.jsonl").exists())
            self.assertFalse((output / "report.json").exists())
            run = json.loads((output / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["stages"]["growth"]["status"], "failed")
            self.assertEqual(run["stages"]["flows"]["status"], "pending")

    def test_production_resume_does_not_duplicate_injected_codeql_or_llm_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(self._values(root, allow_remote_llm=True), environ={"DEEPSEEK_API_KEY": "fixture-secret"}, stage_executors=self._fake_executors(calls))
            self.assertEqual(pipeline.run("analyze")["status"], "completed")
            resumed = build_production_pipeline({**self._values(root, allow_remote_llm=True), "resume": True}, environ={"DEEPSEEK_API_KEY": "fixture-secret"}, stage_executors=self._fake_executors(calls))
            self.assertEqual(resumed.run("analyze")["status"], "completed")
            self.assertEqual(calls, list(STAGES))

    def test_conclude_and_report_artifact_names_are_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[str] = []
            pipeline = build_production_pipeline(self._values(root, allow_remote_llm=True), environ={"DEEPSEEK_API_KEY": "fixture-secret"}, stage_executors=self._fake_executors(calls))
            result = pipeline.run("analyze")
            self.assertEqual(calls, list(STAGES))
            self.assertEqual({item["path"] for item in result["stages"]["conclude"]["artifacts"]}, {"conclude.jsonl"})
            self.assertEqual({item["path"] for item in result["stages"]["report"]["artifacts"]}, {"report.jsonl"})
            self.assertTrue((root / "output" / "run.json").is_file())
            self.assertEqual(result["stages"]["report"]["metadata"]["executor"], "fake")

    def test_cli_default_dispatch_uses_production_factory_and_preserves_stage_target(self) -> None:
        seen: list[tuple[dict[str, object], dict[str, str]]] = []

        class FakePipeline:
            def run(self, command: str) -> dict[str, str]:
                self.command = command
                return {"status": "completed"}

        def factory(values: dict[str, object], *, environ: dict[str, str] | None = None):
            seen.append((values, dict(environ or {})))
            return FakePipeline()

        with mock.patch("dosweb.production.build_production_pipeline", side_effect=factory):
            with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "cli-secret"}, clear=False):
                status = main(["report", "--database", "db", "--output", "out"])
        self.assertEqual(status, 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0]["command"], "report")
        self.assertEqual(seen[0][0]["database"], Path("db"))
        self.assertEqual(seen[0][1]["DEEPSEEK_API_KEY"], "cli-secret")

    def test_cli_parser_remains_parse_only_for_production_factory(self) -> None:
        values = parse_cli_values(["analyze", "--database", "db", "--output", "out"])
        self.assertEqual(values["command"], "analyze")
        self.assertIsNone(values["allow_remote_llm"])


if __name__ == "__main__":
    unittest.main()
