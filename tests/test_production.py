from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from dosweb.cli import main, parse_cli_values
from dosweb.codeql import DatabaseInfo, QueryResult
from dosweb.codeql.decoder import (
    BOUND_COLUMNS,
    ENTRY_COLUMNS,
    INTERPOSITION_COLUMNS,
    FLOW_COLUMNS,
    GROWTH_COLUMNS,
    GUARD_COLUMNS,
    LIFECYCLE_COVERAGE_COLUMNS,
    LIFECYCLE_SUMMARY_COLUMNS,
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
    VerificationCheck,
    VerifiedGrowthResult,
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
            "source_checkout": root,
            "analysis_source_root": root,
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

    def test_amplification_requires_exact_global_flow_loop_witness(self) -> None:
        positive = SimpleNamespace(
            kind="container_growth",
            coverage_notes=("persistent_field_container_write:attacker_controlled_loop_multiplicity_proven",),
        )
        self.assertEqual(
            ("proven", "AMPLIFICATION_CFG_DATAFLOW_LOOP_WITNESS"),
            production._amplification_decision_for_candidate(positive),  # noqa: SLF001
        )
        for notes in (
            ("persistent_field_container_write:loop_bound_not_attacker_proven",),
            ("finite_queue_submission_candidate:finite_capacity_prevents_amplification",),
            ("persistent_field_container_write:loop_multiplicity_unmodeled",),
        ):
            with self.subTest(notes=notes):
                self.assertEqual(
                    ("unknown", "AMPLIFICATION_LOOP_OR_BATCH_UNMODELED"),
                    production._amplification_decision_for_candidate(
                        SimpleNamespace(kind="container_growth", coverage_notes=notes)  # noqa: SLF001
                    ),
                )
        self.assertEqual(
            ("not_applicable", "AMPLIFICATION_DIRECT_DEMAND_ASSERTION"),
            production._amplification_decision_for_candidate(
                SimpleNamespace(kind="async_work_growth", coverage_notes=("queue:single_submission_no_enclosing_loop",))
            ),
        )

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
                decoded.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
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

    def _payload_for_query(self, query: Path) -> dict[str, object]:
        if query.name == "EntryInterpositions.ql":
            return {"#select": {"columns": list(INTERPOSITION_COLUMNS), "tuples": []}}
        return self._entry_payload()

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
            (source / "pom.xml").write_text("<project><dependencies><dependency>org.springframework</dependency></dependencies></project>", encoding="utf-8")
            info = DatabaseInfo(database, source, "d" * 64)
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
                generation.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
                return QueryResult(
                    query_name="entries",
                    query_path=query,
                    bqrs_path=query,
                    decoded_path=generation,
                    query_sha256="a" * 64,
                    bqrs_sha256="b" * 64,
                )

            values = self._values(root)
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=fake_validate,
                run_query_fn=fake_run,
            )
            result = pipeline.run("entries")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(queries, [*production._ENTRY_QUERIES, production._INTERPOSITION_QUERY])
            self.assertEqual(validations, [database])
            self.assertEqual(query_databases, [info] * (len(production._ENTRY_QUERIES) + 1))
            self.assertEqual(
                {path.name for path in (root / "output").iterdir()},
                {"entry_facts.jsonl", "entry_gap_facts.jsonl", "entry_interposition_facts.jsonl", "coverage.json", "configuration_coverage.json", "descriptor_coverage.json", "modeled_configuration.jsonl", "entry_security_facts.jsonl", "run.json", ".stage-manifests", ".pipeline.lock"},
            )
            self.assertEqual(
                {item["path"] for item in result["stages"]["entries"]["artifacts"]},
                {"entry_facts.jsonl", "entry_gap_facts.jsonl", "entry_interposition_facts.jsonl", "coverage.json", "configuration_coverage.json", "descriptor_coverage.json", "modeled_configuration.jsonl", "entry_security_facts.jsonl"},
            )
            run_metadata = (root / "output" / "run.json").read_text(encoding="utf-8")
            self.assertNotIn("DEEPSEEK_API_KEY", run_metadata)
            self.assertNotIn("Authorization", run_metadata)
            self.assertIn('"analysis_mode":"formal"', run_metadata)
            self.assertEqual(pipeline._fingerprint("entries", {}).database_fingerprint, "d" * 64)  # noqa: SLF001
            self.assertRegex(pipeline._fingerprint("entries", {}).query_pack_hash, r"^[0-9a-f]{64}$")  # noqa: SLF001

    def test_entries_recovers_dropwizard_guice_jaxrs_when_codeql_types_are_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            java = source / "service" / "src" / "main" / "java" / "example"
            database.mkdir()
            java.mkdir(parents=True)
            (java / "Paths.java").write_text(
                'package example; public interface Paths { String ROOT = "/"; String ASSET = "processAsset"; String ANNOTATE = "annotatePDF"; }',
                encoding="utf-8",
            )
            (java / "Resource.java").write_text(
                """package example;
import jakarta.ws.rs.*;
import org.glassfish.jersey.media.multipart.FormDataParam;
@Path(Paths.ROOT)
public class Resource implements Paths {
  @Path(ASSET) @POST
  public Object asset(@FormDataParam("input") java.io.InputStream input) { return null; }
  @POST @Path(ANNOTATE)
  public Object annotate(@FormDataParam("input") java.io.InputStream input) { return null; }
}
""",
                encoding="utf-8",
            )
            (java / "ServiceModule.java").write_text(
                """package example;
import ru.vyarus.dropwizard.guice.module.support.DropwizardAwareModule;
public class ServiceModule extends DropwizardAwareModule<Object> {
  protected void configure() { bind(Resource.class); }
}
""",
                encoding="utf-8",
            )
            (java / "ServiceApplication.java").write_text(
                """package example;
import io.dropwizard.core.Application;
import io.dropwizard.core.setup.Bootstrap;
import io.dropwizard.core.setup.Environment;
import ru.vyarus.dropwizard.guice.GuiceBundle;
public class ServiceApplication extends Application<Object> {
  private static final String RESOURCES = "/api";
  public void initialize(Bootstrap<Object> bootstrap) {
    GuiceBundle bundle = GuiceBundle.builder().modules(getModules()).build();
    bootstrap.addBundle(bundle);
  }
  private AbstractModule getModules() { return new ServiceModule(); }
  public void run(Object configuration, Environment environment) {
    environment.jersey().setUrlPattern(RESOURCES + "/*");
  }
}
""",
                encoding="utf-8",
            )
            info = DatabaseInfo(database, source, "d" * 64)

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                columns = INTERPOSITION_COLUMNS if query.name == "EntryInterpositions.ql" else ENTRY_COLUMNS
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(
                    json.dumps({"#select": {"columns": list(columns), "tuples": []}}),
                    encoding="utf-8",
                )
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            values = self._values(root)
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
            )

            self.assertEqual(pipeline.run("entries")["status"], "completed")
            entries = [
                json.loads(line)
                for line in (root / "output" / "entry_facts.jsonl").read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(
                {entry["route_or_event"] for entry in entries},
                {"POST /api/annotatePDF", "POST /api/processAsset"},
            )
            self.assertTrue(all(entry["framework"] == "jax_rs" for entry in entries))
            self.assertTrue(all(entry["registration"]["callable"] == "example.ServiceModule.bind" for entry in entries))
            self.assertTrue(all(entry["attacker_inputs"] == [{"kind": "stream", "name": "input", "type": "java.io.InputStream"}] for entry in entries))

    def test_formal_entries_query_failure_aborts_without_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"; source = root / "source"
            database.mkdir(); (source / "src/main/java/app").mkdir(parents=True)
            (source / "pom.xml").write_text("<project><dependencies><dependency>org.springframework</dependency></dependencies></project>", encoding="utf-8")
            info = DatabaseInfo(database, source, "d" * 64)
            def failing_run(*_args: object, **_kwargs: object) -> QueryResult:
                raise AnalyzerError("CODEQL_QUERY_FAILED", "CodeQL query execution failed.")
            values = self._values(root)
            values["source_checkout"] = source; values["analysis_source_root"] = source
            pipeline = build_production_pipeline(values, environ={}, validate_database_fn=lambda *_args, **_kwargs: info, run_query_fn=failing_run)
            with self.assertRaisesRegex(AnalyzerError, "CodeQL query execution failed") as raised:
                pipeline.run("entries")
            self.assertEqual(raised.exception.code, "CODEQL_QUERY_FAILED")
            self.assertFalse((root / "output" / ".stage-manifests" / "entries.json").exists())

    def test_default_entries_marks_failed_selected_queries_as_partial_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            (source / "src/main/java/app").mkdir(parents=True)
            (source / "pom.xml").write_text("<project><dependencies><dependency>org.springframework</dependency></dependencies></project>", encoding="utf-8")
            info = DatabaseInfo(database, source, "d" * 64)

            def failing_run(_query: Path, _database: DatabaseInfo, _output_dir: Path, **_kwargs: object) -> QueryResult:
                raise AnalyzerError("CODEQL_QUERY_FAILED", "CodeQL query execution failed.", {"stage": "query_run", "diagnostic": "timeout"})

            values = self._values(root)
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            values["allow_partial_codeql"] = True
            values["command"] = "entries"
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=failing_run,
            )
            result = pipeline.run("entries")
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["stages"]["entries"]["metadata"]["query_count"], 2)
            self.assertEqual(result["stages"]["entries"]["metadata"]["skipped_query_count"], 2)
            self.assertEqual(
                result["stages"]["entries"]["metadata"]["query_diagnostics"],
                [{
                    "code": "CODEQL_QUERY_FAILED",
                    "diagnostic": "timeout",
                    "query_name": "SpringMvcEntries.ql",
                    "stage": "query_run",
                }, {
                    "code": "CODEQL_QUERY_FAILED",
                    "query_name": "EntryInterpositions.ql",
                }],
            )
            coverage = json.loads((root / "output" / "coverage.json").read_text(encoding="utf-8"))
            spring = next(item for item in coverage if item["framework"] == "spring_mvc")
            self.assertEqual(spring["status"], "partial")
            self.assertIn("query_failed:SpringMvcEntries", spring["unsupported_patterns"])
            servlet = next(item for item in coverage if item["framework"] == "servlet")
            self.assertEqual(servlet["status"], "unsupported")
            self.assertIn("framework_evidence_absent:ServletEntries", servlet["unsupported_patterns"])
            self.assertEqual((root / "output" / "entry_facts.jsonl").read_text(encoding="utf-8"), "")

    def test_truncated_entry_hint_scan_marks_unselected_frameworks_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            java = source / "src/main/java/app"
            java.mkdir(parents=True)
            for index in range(513):
                (java / f"A{index:03d}.java").write_text(
                    "class A {}\n" if index else "@RestController class A {}\n",
                    encoding="utf-8",
                )
            info = DatabaseInfo(database, source, "d" * 64)

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                payload = self._payload_for_query(query)
                if query.name != "EntryInterpositions.ql":
                    payload["#select"]["tuples"][0][0] = "spring_mvc"  # type: ignore[index]
                    payload["#select"]["tuples"][0][16] = "spring_annotation_mapping"  # type: ignore[index]
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(payload), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            values = self._values(root)
            values["source_checkout"] = source
            values["analysis_source_root"] = source
            values["allow_partial_codeql"] = True
            values["command"] = "entries"
            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
            )
            self.assertEqual(pipeline.run("entries")["status"], "completed")
            coverage = json.loads((root / "output" / "coverage.json").read_text(encoding="utf-8"))
            servlet = next(item for item in coverage if item["framework"] == "servlet")
            self.assertEqual(servlet["status"], "partial")
            self.assertIn("framework_evidence_scan_truncated:ServletEntries", servlet["unsupported_patterns"])

    def test_default_entries_executes_the_preflight_query_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            source = root / "source"
            database.mkdir()
            source.mkdir()
            (source / "pom.xml").write_text("<project><dependencies><dependency>org.springframework</dependency></dependencies></project>", encoding="utf-8")
            info = DatabaseInfo(database, source, "d" * 64)
            observed: list[tuple[Path, bytes]] = []

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                observed.append((query, query.read_bytes()))
                decoded = output_dir / f"{query.stem}.json"
                decoded.parent.mkdir(parents=True, exist_ok=True)
                decoded.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            import dosweb.production as production

            pack_hash, snapshot = production._query_pack_snapshot()  # noqa: SLF001

            with mock.patch(
                "dosweb.production._query_pack_snapshot",
                return_value=(pack_hash, snapshot),
            ):
                values = self._values(root)
                values["source_checkout"] = source
                values["analysis_source_root"] = source
                pipeline = build_production_pipeline(
                    values,
                    environ={},
                    validate_database_fn=lambda *_args, **_kwargs: info,
                    run_query_fn=fake_run,
                )
                self.assertEqual(pipeline.run("entries")["status"], "completed")

            original = production._ENTRY_QUERY_DIR / "SpringMvcEntries.ql"  # noqa: SLF001
            self.assertEqual(len(observed), len(production._ENTRY_QUERIES) + 1)
            self.assertNotEqual(observed[0][0], original)
            self.assertEqual(
                observed[0][1],
                snapshot["dosweb/Entries/SpringMvcEntries.ql"],
            )
            self.assertEqual(
                {query.name for query, _ in observed},
                {*production._ENTRY_QUERIES, production._INTERPOSITION_QUERY},
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

    def test_default_preflight_accepts_separate_analysis_and_provider_checkouts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"
            analysis = root / "analysis"
            provider = root / "provider"
            database.mkdir()
            analysis.mkdir()
            provider.mkdir()
            values = self._values(root)
            values["analysis_source_root"] = analysis
            values["source_checkout"] = provider

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            pipeline = build_production_pipeline(
                values,
                environ={},
                validate_database_fn=lambda *_args, **_kwargs: DatabaseInfo(
                    database, analysis, "d" * 64
                ),
                run_query_fn=fake_run,
            )
            self.assertEqual(pipeline.run("entries")["status"], "completed")

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
                generation.write_text(json.dumps(self._payload_for_query(query)), encoding="utf-8")
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

        expected = {*production._ENTRY_QUERIES, production._INTERPOSITION_QUERY}  # noqa: SLF001 - packaging contract
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
                payload = self._payload_for_query(query)
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

    def test_candidate_entry_association_rejects_no_match_and_prefers_nearest_handler(self) -> None:
        entry, candidate = self._entry_and_candidate()
        with self.assertRaises(AnalyzerError) as no_match:
            production._entry_for_candidate({}, candidate)  # noqa: SLF001
        self.assertEqual(no_match.exception.code, "ANALYSIS_GROWTH_ENTRY_AMBIGUOUS")
        other = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact("fixture.Other.handle", "src/Handler.java", 12),
            registration=RegistrationFact("annotation_mapping", "fixture.Other", "src/Other.java", 8),
            route_or_event="/other",
            auth_context="unknown",
            attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
            materialization_phase="in_handler",
        )
        self.assertEqual(production._entry_for_candidate({entry.entry_id: entry, other.entry_id: other}, candidate), entry)  # noqa: SLF001
        self.assertEqual(production._entry_for_candidate({entry.entry_id: entry}, candidate), entry)  # noqa: SLF001

    def test_candidate_entry_association_collapses_semantic_duplicate_registrations(self) -> None:
        entry, candidate = self._entry_and_candidate()
        duplicate = EntryFact.create(
            framework=entry.framework,
            protocol=entry.protocol,
            handler=entry.handler,
            registration=RegistrationFact("static_registration", "fixture.Handler.register", "src/Config.java", 99),
            route_or_event=entry.route_or_event,
            auth_context=entry.auth_context,
            attacker_inputs=entry.attacker_inputs,
            materialization_phase=entry.materialization_phase,
        )
        chosen = production._entry_for_candidate({entry.entry_id: entry, duplicate.entry_id: duplicate}, candidate)  # noqa: SLF001
        self.assertEqual(chosen.entry_id, entry.entry_id)

    def test_flow_screening_reconciles_broad_source_fallback_to_extracted_entries(self) -> None:
        entry, candidate = self._entry_and_candidate()
        growth = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:fixture",
            status="unresolved",
            reason_codes=("GROWTH_ASSOCIATION_INCOMPLETE",),
            checks=(
                VerificationCheck(
                    "candidate_entry_association",
                    False,
                    "GROWTH_ASSOCIATION_INCOMPLETE",
                ),
            ),
        )
        valid = {
            "source_file": entry.handler.file,
            "source_start_line": entry.handler.start_line,
            "sink_file": candidate.site.file,
            "sink_start_line": candidate.site.start_line,
        }
        broad_non_entry = {
            **valid,
            "source_file": "src/UnregisteredService.java",
            "source_start_line": 61,
        }

        reconciled = production._reconcile_flow_rows(  # noqa: SLF001
            (valid, broad_non_entry),
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )

        self.assertEqual(reconciled, [valid])

    def test_flow_reconciliation_invalidates_pre_fix_resume_artifacts(self) -> None:
        self.assertEqual(set(production._IMPLEMENTATION_VERSIONS), set(STAGES))  # noqa: SLF001
        for stage, version in production._IMPLEMENTATION_VERSIONS.items():  # noqa: SLF001
            with self.subTest(stage=stage):
                self.assertTrue(
                    version.startswith(f"production-v2.6-poc33-demo-repair-{stage}-"),
                    version,
                )

    def test_candidate_entry_association_falls_back_to_single_semantic_target_entry(self) -> None:
        entry, _candidate = self._entry_and_candidate()
        duplicate = EntryFact.create(
            framework=entry.framework,
            protocol=entry.protocol,
            handler=entry.handler,
            registration=RegistrationFact("static_registration", "fixture.Handler.register", "src/Config.java", 99),
            route_or_event=entry.route_or_event,
            auth_context=entry.auth_context,
            attacker_inputs=entry.attacker_inputs,
            materialization_phase=entry.materialization_phase,
        )
        candidate = GrowthCandidate.create(
            site=SourceLocation("src/Helper.java", 50),
            kind="direct_allocation",
            operation="new byte[size]",
            resource_dimension="bytes",
            receiver="byte[]",
            field_path="allocation",
            demand_inputs=(DemandInput("body", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
        )
        chosen = production._entry_for_candidate({entry.entry_id: entry, duplicate.entry_id: duplicate}, candidate)  # noqa: SLF001
        self.assertEqual(chosen.entry_id, entry.entry_id)

    def _bqrs_payload(self, columns: tuple[str, ...], rows: list[list[object]]) -> dict[str, object]:
        return {"#select": {"columns": [{"name": name, "kind": "String"} for name in columns], "tuples": rows}}

    def test_duplicate_registrations_do_not_block_growth_or_flow_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "database"; database.mkdir()
            source = root / "source"; source.mkdir()
            info = DatabaseInfo(database, root, "d" * 64)

            rows_by_query: dict[str, tuple[tuple[str, ...], list[list[object]]]] = {
                "SpringMvcEntries": (ENTRY_COLUMNS, [[
                    "spring_mvc", "http", "fixture.Handler.handle", "src/Handler.java", 20,
                    "annotation_mapping", "fixture.Handler", "src/Handler.java", 8, "/items",
                    "unknown", "body", "byte[]", "request_body", "in_handler", "complete",
                    "spring_annotation_mapping",
                ]]),
                "ServletEntries": (ENTRY_COLUMNS, [[
                    "spring_mvc", "http", "fixture.Handler.handle", "src/Handler.java", 20,
                    "static_registration", "fixture.Router", "src/Router.java", 40, "/items",
                    "unknown", "body", "byte[]", "request_body", "in_handler", "complete",
                    "spring_annotation_mapping",
                ]]),
                "InputMaterialization": (GROWTH_COLUMNS, [[
                    "src/Handler.java", 24, "input_materialization", "request.readAllBytes",
                    "bytes", "fixture.Handler.body", "this.body", "body", "size", "request",
                    "fact:growth", "complete", "input_materialization",
                ]]),
                "EntryToGrowth": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle>request.readAllBytes", "in_handler", "data_flow", "proven",
                    "complete", "entry_to_growth",
                ]]),
                "EntryToGrowthAssociations": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle>request.readAllBytes", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ]]),
                "GuardCandidates": (GUARD_COLUMNS, []),
                "BoundCandidates": (BOUND_COLUMNS, []),
                "SynchronousReleaseCandidates": (RELEASE_COLUMNS, []),
                "LifecycleCoverage": (LIFECYCLE_COVERAGE_COLUMNS, []),
                "LifecycleSummary": (LIFECYCLE_SUMMARY_COLUMNS, []),
            }

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                columns, rows = rows_by_query.get(query.stem, (INTERPOSITION_COLUMNS if query.name == "EntryInterpositions.ql" else ENTRY_COLUMNS if query.parent.name == "Entries" else GROWTH_COLUMNS, []))
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._bqrs_payload(columns, rows)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            def fake_excerpt(checkout: Path, commit: str, path: str, line: int) -> SourceExcerpt:
                import hashlib
                content = f"attested line {line}\n"
                return SourceExcerpt(
                    f"excerpt:{line}", path, line, line, content, "c" * 64,
                    hashlib.sha256(content.encode()).hexdigest(),
                )

            class FakeLlm:
                def classify_growth(self, bounded: object) -> GrowthContract:
                    return GrowthContract("unknown", "input_materialization", "bytes", (), "unknown", (), "high")

            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": "fixture-secret"},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
                deepseek_client=FakeLlm(),
                source_excerpt_fn=fake_excerpt,
            )
            self.assertEqual(pipeline.run("analyze")["status"], "completed")
            verified = [
                json.loads(line)
                for line in (root / "output" / "verified_growth.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(verified), 1)
            self.assertEqual(verified[0]["status"], "unresolved")
            self.assertEqual(verified[0]["reason_codes"], ["GROWTH_ASSOCIATION_INCOMPLETE"])

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
                "SpringMvcEntries": (ENTRY_COLUMNS, [
                    [
                        "spring_mvc", "http", "fixture.Handler.handle", "src/Handler.java", 20,
                        "annotation_mapping", "fixture.Handler", "src/Handler.java", 8, "/items",
                        "unknown", "body", "byte[]", "request_body", "in_handler", "complete",
                        "spring_annotation_mapping",
                    ],
                    [
                        "spring_mvc", "http", "fixture.Other.handle", "src/OtherController.java", 40,
                        "annotation_mapping", "fixture.Other", "src/OtherController.java", 36, "/other",
                        "unknown", "body", "byte[]", "request_body", "in_handler", "complete",
                        "spring_annotation_mapping",
                    ],
                ]),
                "InputMaterialization": (GROWTH_COLUMNS, [
                    [
                        "src/Handler.java", 24, "input_materialization", "request.readAllBytes",
                        "bytes", "fixture.Handler.body", "this.body", "body", "size", "request",
                        "fact:growth", "complete", "input_materialization",
                    ],
                    [
                        "src/Detached.java", 9, "input_materialization", "request.readAllBytes",
                        "bytes", "fixture.Detached.body", "this.body", "body", "size", "request",
                        "fact:other-growth", "complete", "input_materialization",
                    ],
                ]),
                "EntryToGrowth": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle>request.readAllBytes", "in_handler", "data_flow", "proven",
                    "complete", "entry_to_growth",
                ]]),
                "EntryToGrowthAssociations": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle>request.readAllBytes", "entry>callgraph>growth", "data_flow", "proven",
                    "complete", "same_handler_call_graph_association",
                ]]),
                "GuardCandidates": (GUARD_COLUMNS, []),
                "BoundCandidates": (BOUND_COLUMNS, []),
                "SynchronousReleaseCandidates": (RELEASE_COLUMNS, []),
                "LifecycleCoverage": (LIFECYCLE_COVERAGE_COLUMNS, []),
                "LifecycleSummary": (LIFECYCLE_SUMMARY_COLUMNS, []),
            }

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                query_calls.append(query.stem)
                if query.stem in rows_by_query:
                    columns, rows = rows_by_query[query.stem]
                else:
                    columns = INTERPOSITION_COLUMNS if query.name == "EntryInterpositions.ql" else ENTRY_COLUMNS if query.parent.name == "Entries" else GROWTH_COLUMNS
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
            self.assertEqual(len(excerpt_calls), 3)
            self.assertEqual({call[1] for call in excerpt_calls}, {None})
            self.assertEqual(
                {call[2:] for call in excerpt_calls},
                {("src/Handler.java", 8), ("src/Handler.java", 20), ("src/Handler.java", 24)},
            )
            self.assertEqual(result["stages"]["growth"]["metadata"]["candidate_count"], 2)
            self.assertEqual(result["stages"]["growth"]["metadata"]["mapped_candidate_count"], 1)
            self.assertEqual(result["stages"]["growth"]["metadata"]["skipped_unmapped_candidate_count"], 0)
            self.assertEqual(len(query_calls), 19)
            self.assertEqual(
                {item["path"] for item in result["stages"]["conclude"]["artifacts"]},
                {"lifecycle_certificates.jsonl", "static_findings.jsonl"},
            )
            self.assertEqual(
                {item["path"] for item in result["stages"]["report"]["artifacts"]},
                {"summary.json", "report.md"},
            )

    def test_full_production_graph_publishes_certificate_backed_unknown_when_lifecycle_absence_is_unproven(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "database").mkdir()
            source_file = root / "src" / "Handler.java"
            source_file.parent.mkdir()
            lines = ["// fixture"] * 30
            lines[0] = "import org.springframework.web.bind.annotation.PostMapping;"
            lines[7] = "@PostMapping(\"/items\")"
            lines[19] = "public void handle(byte[] body) {"
            lines[23] = "  byte[] materialized = body;"
            lines[25] = "}"
            source_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            info = DatabaseInfo(root / "database", root, "d" * 64)
            rows_by_query: dict[str, tuple[tuple[str, ...], list[list[object]]]] = {
                "SpringMvcEntries": (ENTRY_COLUMNS, [[
                    "spring_mvc", "http", "fixture.Handler.handle", "src/Handler.java", 20,
                    "annotation_mapping", "fixture.Handler", "src/Handler.java", 8, "/items",
                    "unauthenticated", "body", "byte[]", "request_body", "in_handler", "complete",
                    "spring_annotation_mapping",
                ]]),
                "InputMaterialization": (GROWTH_COLUMNS, [[
                    "src/Handler.java", 24, "input_materialization", "spring_request_body_materialization",
                    "bytes", "fixture.Handler.handle", "body", "body", "size", "request",
                    "fact:growth", "complete", "recognized_spring_request_body_bytes",
                ]]),
                "EntryToGrowth": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "body", "body",
                    "fixture.Handler.handle", "entry>materialization", "data_flow", "proven",
                    "complete", "request_body_parameter_materialization",
                ]]),
                "EntryToGrowthAssociations": (FLOW_COLUMNS, [[
                    "src/Handler.java", 20, "src/Handler.java", 24, "size", "fixture.Handler.handle", "fixture.Handler.handle",
                    "fixture.Handler.handle", "entry>materialization", "data_flow", "proven",
                    "complete", "same_handler_request_body_materialization",
                ]]),
                "GuardCandidates": (GUARD_COLUMNS, []),
                "BoundCandidates": (BOUND_COLUMNS, []),
                "SynchronousReleaseCandidates": (RELEASE_COLUMNS, []),
                "LifecycleCoverage": (LIFECYCLE_COVERAGE_COLUMNS, []),
                "LifecycleSummary": (LIFECYCLE_SUMMARY_COLUMNS, []),
            }

            def fake_run(query: Path, _database: DatabaseInfo, output_dir: Path, **_kwargs: object) -> QueryResult:
                columns, rows = rows_by_query.get(
                    query.stem,
                    (INTERPOSITION_COLUMNS if query.name == "EntryInterpositions.ql" else ENTRY_COLUMNS if query.parent.name == "Entries" else GROWTH_COLUMNS, []),
                )
                decoded = output_dir / f"{query.stem}.json"
                decoded.write_text(json.dumps(self._bqrs_payload(columns, rows)), encoding="utf-8")
                return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

            def fake_excerpt(checkout: Path, commit: str, path: str, line: int) -> SourceExcerpt:
                import hashlib
                content = f"attested line {line}\n"
                return SourceExcerpt(
                    f"excerpt:{line}", path, line, line, content, "c" * 64,
                    hashlib.sha256(content.encode()).hexdigest(),
                )

            class FakeLlm:
                def classify_auth(self, entry_id: str, facts: object, configuration: object):
                    from dosweb.reachability import AuthContract
                    fact = tuple(facts)[0]
                    return AuthContract("unauthenticated", (fact.fact_id,), (), "high")

                def classify_growth(self, bounded: object) -> GrowthContract:
                    flow = next(fact for fact in bounded.payload.static_facts if fact.relation == "flows_to")
                    sink = next(fact for fact in bounded.payload.static_facts if fact.relation == "sink")
                    return GrowthContract(
                        "yes", "input_materialization", "bytes",
                        (AttackerInfluence("size", flow.fact_id),),
                        "materializes_bytes", (flow.fact_id, sink.fact_id), "high",
                    )

            pipeline = build_production_pipeline(
                self._values(root, allow_remote_llm=True),
                environ={"DEEPSEEK_API_KEY": "fixture-secret"},
                validate_database_fn=lambda *_args, **_kwargs: info,
                run_query_fn=fake_run,
                deepseek_client=FakeLlm(),
                source_excerpt_fn=fake_excerpt,
            )
            result = pipeline.run("analyze")
            self.assertEqual("completed", result["status"])
            findings = json.loads((root / "output" / "static_findings.jsonl").read_text().strip())
            self.assertEqual("static_unknown", findings["verdict"])
            certificate = json.loads((root / "output" / "lifecycle_certificates.jsonl").read_text().strip())
            self.assertEqual(findings["certificate_id"], certificate["certificate_id"])
            self.assertIn("VERDICT_UNRESOLVED_EVIDENCE", findings["reason_codes"])
            self.assertIn("static_unknown", (root / "output" / "report.md").read_text())

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
