"""Hermetic production-pipeline checks. All query/provider inputs are synthetic.

These tests verify tool plumbing, never target discovery or empirical recall.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dosweb.codeql import DatabaseInfo, QueryResult
from dosweb.codeql.decoder import (
    BOUND_COLUMNS, ENTRY_COLUMNS, FLOW_COLUMNS, GROWTH_COLUMNS, GUARD_COLUMNS,
    INTERPOSITION_COLUMNS, LIFECYCLE_COVERAGE_COLUMNS, LIFECYCLE_SUMMARY_COLUMNS,
    RELEASE_COLUMNS, SECURITY_COLUMNS,
)
from dosweb.growth import AttackerInfluence, GrowthContract, SourceExcerpt
from dosweb.pipeline import STAGES
from dosweb.production import build_production_pipeline
from tests.test_resource_lifecycle_production_bridge import _run

_FILE = "src/main/java/Fixture.java"


class SyntheticClassifier:
    def __init__(self):
        self.calls = 0

    def classify_growth(self, bounded):
        self.calls += 1
        facts = bounded.payload.static_facts
        flow = next(f for f in facts if f.kind == "flow" and f.relation == "flows_to")
        evidence = tuple(next(f for f in facts if f.kind == kind).fact_id for kind in (
            "async_submission", "value_space", "retention", "amplification",
        ))
        return GrowthContract(
            is_resource_growth="yes", growth_kind="async_work_growth",
            resource_dimension="tasks", attacker_influence=(AttackerInfluence("submission_count", flow.fact_id),),
            resource_effect="enqueues_tasks", attacker_variable="request count",
            attacker_value_space="unlimited", growth_unit="accepted tasks",
            growth_function="request count controls task submissions",
            amplification_class="queue_instability", requests_to_pressure="one",
            concurrency_model="bounded executor", retention_window="process",
            failure_mechanism="queue_latency_collapse", failure_signal="synthetic demand",
            required_static_evidence=evidence, contract_status="dos_relevant",
            rejection_reason="none", confidence="high",
        )


def run_synthetic_case(root: Path, variant: str, *, resume: bool = False):
    database = root / "database"
    database.mkdir(parents=True, exist_ok=True)
    source = root / _FILE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('@PostMapping("/submit")\nvoid handle(int count) {\n  this.executor.execute(task);\n}\n')
    flow = [_FILE, 2, _FILE, 3, "submission_count", "count", "count", "Fixture.handle",
            "in_handler", "data_flow", "proven", "complete", "same_handler_call_graph_association"]
    rows = {
        "SpringMvcEntries": (ENTRY_COLUMNS, [["spring_mvc", "http", "Fixture.handle", _FILE, 2,
            "annotation_mapping", "Fixture", _FILE, 1, "/submit", "unknown", "count", "int",
            "request_parameter", "in_handler", "complete", "spring_annotation_mapping"]]),
        "AsyncWorkGrowth": (GROWTH_COLUMNS, [[_FILE, 3, "async_work_growth", "java.util.concurrent.Executor.execute",
            "tasks", "this.executor", "this.executor", "count", "submission_count", "instance", "async_submission",
            "partial" if variant == "growth_gap" else "complete",
            "queue_or_executor_capacity_requires_contract:attacker_controlled_loop_multiplicity_proven"]]),
        "EntryToGrowth": (FLOW_COLUMNS, [flow]),
        "EntryToGrowthAssociations": (FLOW_COLUMNS, [flow]),
        "EntrySecurity": (SECURITY_COLUMNS, [["Fixture.handle", _FILE, 2, "", _FILE, 1,
            "annotation", "unauthenticated_annotation", "partial" if variant == "auth_gap" else "complete", "permit_all"]]),
        "GuardCandidates": (GUARD_COLUMNS, []),
        "BoundCandidates": (BOUND_COLUMNS, []),
        "SynchronousReleaseCandidates": (RELEASE_COLUMNS, []),
        "LifecycleCoverage": (LIFECYCLE_COVERAGE_COLUMNS, [[_FILE, 3, family,
            "partial" if variant == "lifecycle_gap" else "complete", "exact_anchor_no_candidate"]
            for family in ("guard", "bound", "release")]),
        "LifecycleSummary": (LIFECYCLE_SUMMARY_COLUMNS, []),
    }
    query_calls = []
    resource_calls = []
    classifier = SyntheticClassifier()

    def query_provider(query, _database, output_dir, **_kwargs):
        assert not resume, "resume unexpectedly re-executed a query"
        query_calls.append(query.name)
        columns, values = rows.get(query.stem, (
            INTERPOSITION_COLUMNS if query.name == "EntryInterpositions.ql" else
            ENTRY_COLUMNS if query.parent.name == "Entries" else GROWTH_COLUMNS, []))
        decoded = output_dir / f"{query.stem}.json"
        decoded.write_text(json.dumps({"#select": {"columns": list(columns), "tuples": values}}))
        return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

    def excerpt_provider(_checkout, _commit, path, line):
        text = f"synthetic attested line {line}\n"
        return SourceExcerpt(f"excerpt:{line}", path, line, line, text, "c" * 64,
                             hashlib.sha256(text.encode()).hexdigest())

    def resource_provider(_database, _output):
        assert not resume, "resume unexpectedly re-executed a resource provider"
        resource_calls.append(True)
        return _run(bounded=variant != "resource_unknown")

    pipeline = build_production_pipeline({
        "command": "analyze", "database": database, "output": root / "output",
        "source_checkout": root, "analysis_source_root": root, "allow_remote_llm": True,
        "resume": resume,
    }, environ={"DEEPSEEK_API_KEY": "synthetic-not-a-credential"},
        validate_database_fn=lambda *_a, **_kw: DatabaseInfo(database, root, "9" * 64),
        run_query_fn=query_provider, source_excerpt_fn=excerpt_provider,
        deepseek_client=classifier, resource_lifecycle_provider=resource_provider,
        resource_lifecycle_provider_identity="fse-offline-fixture-v1",
        resource_lifecycle_propagation_enabled=variant != "off")
    result = pipeline.run("analyze")
    return result, root / "output", query_calls, classifier.calls, resource_calls


@pytest.mark.parametrize("variant,expected", [
    ("full", "bounded_under_modeled_assumptions"),
    ("off", "static_vulnerable"),
    ("auth_gap", "static_unknown"),
    ("growth_gap", "static_unknown"),
    ("lifecycle_gap", "static_unknown"),
    ("resource_unknown", "static_unknown"),
])
def test_all_production_stages_preserve_proof_gates(tmp_path, monkeypatch, variant, expected):
    import socket

    def no_network(*_args, **_kwargs):
        raise AssertionError("Offline tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    result, output, queries, calls, _ = run_synthetic_case(tmp_path, variant)
    assert result["status"] == "completed"
    assert all(result["stages"][stage]["status"] == "completed" for stage in STAGES)
    assert queries and calls == 1
    finding = json.loads((output / "static_findings.jsonl").read_text())
    certificate = json.loads((output / "lifecycle_certificates.jsonl").read_text())
    family = json.loads((output / "finding_families.jsonl").read_text())
    assert finding["verdict"] == certificate["verdict"] == family["verdict"] == expected
    assert finding["certificate_id"] == certificate["certificate_id"]
    assert finding["finding_id"] in family["member_finding_ids"]
    assert expected in (output / "report.md").read_text()
    if variant == "full":
        assert certificate["resource_lifecycle_decisions"]
        assert certificate["assumptions"]


def test_complete_offline_run_resumes_without_reexecuting_test_providers(tmp_path):
    _, output, _, _, _ = run_synthetic_case(tmp_path, "full")
    before = (output / "static_findings.jsonl").read_bytes()
    result, _, queries, calls, resource_calls = run_synthetic_case(tmp_path, "full", resume=True)
    assert result["status"] == "completed"
    assert not queries and calls == 0 and not resource_calls
    assert (output / "static_findings.jsonl").read_bytes() == before


@pytest.mark.parametrize("stage,old_version,expected_calls", [
    ("entries", "production-v2.8-open-world-maturation-entries-v17", ["entries", "growth"]),
    ("growth", "production-v2.8-open-world-maturation-growth-v33", ["growth"]),
])
def test_pre_fix_stage_cache_is_not_silently_reused(tmp_path, monkeypatch, stage, old_version, expected_calls):
    import dosweb.production as production
    from tests.test_production import ProductionFactoryTests

    helper = ProductionFactoryTests()
    calls = []
    stale_versions = {**production._IMPLEMENTATION_VERSIONS, stage: old_version}
    with monkeypatch.context() as context:
        context.setattr(production, "_IMPLEMENTATION_VERSIONS", stale_versions)
        stale = build_production_pipeline(
            helper._values(tmp_path, allow_remote_llm=True),
            environ={"DEEPSEEK_API_KEY": "synthetic-not-a-credential"},
            stage_executors=helper._fake_executors(calls))
        assert stale.run("growth")["status"] == "completed"
    assert calls == ["entries", "growth"]
    calls.clear()
    resumed = build_production_pipeline(
        {**helper._values(tmp_path, allow_remote_llm=True), "resume": True},
        environ={"DEEPSEEK_API_KEY": "synthetic-not-a-credential"},
        stage_executors=helper._fake_executors(calls))
    assert resumed.run("growth")["status"] == "completed"
    assert calls == expected_calls
