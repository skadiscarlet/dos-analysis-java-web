"""Offline regressions for the Task 3 artifact and relation review boundaries."""
from dataclasses import asdict, replace
import hashlib
import json
import os
from unittest.mock import patch

import pytest

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.codeql import DecodeSource, QUERY_SPECS, QueryResult, decode_bqrs_json, run_query
from dosweb.codeql.database import DatabaseInfo
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle import commands
from dosweb.resource_lifecycle import adapters
from dosweb.resource_lifecycle.adapters import (
    _unit_from_rows, adapt_codeql_rows, extracted_from_dict,
    extracted_to_dict, validate_extracted,
)
from tests.test_resource_lifecycle_codeql import (
    SYNTHETIC_HANDLE_ID, SYNTHETIC_SOURCE, decoded_query_row, lifecycle_row,
    ROOT, DIRECT_QUERY, DIRECT_TASK_QUERY,
)
from tests.support.fixture_database import fixture_database


def formal_extract(source_root, base_rows, task_rows=()):
    names = ("resource_lifecycle", "resource_lifecycle_task_relations")
    digests = ("a" * 64, "b" * 64)
    rows = [decoded_query_row(source_root, name, digest, **row)
        for name, digest, raw in zip(names, digests, (base_rows, task_rows))
        for row in raw]
    return adapt_codeql_rows(rows, source_root=source_root,
        query_provenance=tuple({"query_name": name, "query_sha256": digest,
            "bqrs_sha256": "c" * 64} for name, digest in zip(names, digests)),
        database_fingerprint="d" * 64, source_snapshot_sha256="e" * 64)


def test_source_mutation_during_adapter_never_publishes_artifacts(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    java = source / "Fixture.java"
    java.write_text(SYNTHETIC_SOURCE, encoding="utf-8")
    database = DatabaseInfo(tmp_path / "database", source, "d" * 64)
    initial_digest = hashlib.sha256(java.read_bytes()).hexdigest()
    results = []
    for name in ("resource_lifecycle", "resource_lifecycle_task_relations"):
        query = tmp_path / (name + ".ql")
        query.write_text("// offline query artifact\n", encoding="utf-8")
        bqrs = tmp_path / (name + ".bqrs")
        bqrs.write_bytes(name.encode())
        decoded = tmp_path / (name + ".json")
        columns = QUERY_SPECS[name].columns
        decoded.write_text(json.dumps({"#select": {
            "columns": list(columns),
            "tuples": [[lifecycle_row()[column] for column in columns]]
            if name == "resource_lifecycle" else [],
        }}), encoding="utf-8")
        results.append(QueryResult(name, query, bqrs, decoded,
            hashlib.sha256(query.read_bytes()).hexdigest(),
            hashlib.sha256(bqrs.read_bytes()).hexdigest()))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "1.1", "mode": "codeql_database",
        "database": str(database.path), "entry_methods": [],
        "budget": {"max_steps": 1024, "max_updates_per_event": 32, "timeout_ms": 5000},
    }), encoding="utf-8")
    observed = []

    def verify(_database):
        digest = hashlib.sha256(java.read_bytes()).hexdigest()
        observed.append(digest)
        return digest

    def mutate_then_adapt(*args, **kwargs):
        java.write_text(SYNTHETIC_SOURCE + "// changed during adaptation\n", encoding="utf-8")
        return adapt_codeql_rows(*args, **kwargs)

    output = tmp_path / "output"
    with patch.object(commands, "validate_database", return_value=database), \
         patch.object(commands, "run_query", side_effect=results), \
         patch.object(commands, "_verify_database_source_snapshot", side_effect=verify), \
         patch.object(commands, "adapt_codeql_rows", side_effect=mutate_then_adapt) as adapter, \
         patch.object(commands, "atomic_write_json", wraps=commands.atomic_write_json) as publish:
        with pytest.raises(AnalyzerError) as raised:
            commands.resource_extract({"manifest": manifest, "out": output})
    assert raised.value.code == "ARTIFACT_INPUT_INVALID"
    assert "snapshot changed" in str(raised.value.__cause__)
    assert adapter.call_count == 1
    assert observed[:2] == [initial_digest, initial_digest]
    assert observed[-1] != initial_digest
    publish.assert_not_called()
    assert not (output / "facts.json").exists()
    assert not (output / "coverage.json").exists()


@pytest.mark.parametrize("change", [
    {"source_kind": "manual_fixture"},
    {"extractor_version": "other-extractor"},
    {"source_sha256": "b" * 64},
    {"end_line": 3},
])
def test_related_location_tamper_rejected_after_rebuilding_derived(change, tmp_path):
    (tmp_path / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
    extracted = formal_extract(tmp_path, (lifecycle_row(), lifecycle_row(
        fact_kind="call_binding", site_start_line=2, program_point="call:A",
        related_point="parameter:B", related_start_line=2,
        target_event="java-callable-v1:Fixture.wrapper(Lfixture/Resource;)V",
        relation_depth=1, binding_index=0,
    )))
    assert validate_extracted(extracted_from_dict(json.loads(json.dumps(extracted_to_dict(extracted))))) == extracted
    facts = tuple(replace(fact, related_location=replace(fact.related_location, **change))
        if fact.fact_kind == "call_binding" else fact for fact in extracted.facts)
    units = (_unit_from_rows(SYNTHETIC_HANDLE_ID, list(facts)),)
    altered = replace(extracted, facts=facts, units=units,
        snapshot_sha256=hashlib.sha256(canonical_json([asdict(fact) for fact in facts])).hexdigest())
    # No stale snapshot/derived-unit mismatch is allowed to hide the provenance defect.
    with pytest.raises(ValueError, match="source metadata|identifier"):
        validate_extracted(extracted_from_dict(json.loads(json.dumps(extracted_to_dict(altered)))))


def assert_distinct_submissions(extracted, expected=2):
    program = extracted.units[0].program
    tasks = program.task_bindings
    assert len(tasks) == expected
    assert len({task.task_id for task in tasks}) == expected
    assert len({task.holder_id for task in tasks}) == expected
    assert len({task.instance_id for task in tasks}) == 1
    assert len({task.executor_contract_id for task in tasks}) == 1
    stages = [getattr(task, field) for task in tasks for field in (
        "submit_event_id", "queued_event_id", "run_event_id", "normal_exit_event_id",
        "exceptional_exit_event_id", "rejected_event_id", "cancelled_event_id")]
    assert len(set(stages)) == 7 * expected
    assert len({exit.exit_id for exit in program.task_exits}) == len(program.task_exits)
    effects = [effect for edge in program.transitions for effect in edge.population_effects]
    assert {effect.task_id for effect in effects} == {task.task_id for task in tasks}
    assert {effect.executor_id for effect in effects} == {tasks[0].executor_contract_id}
    assert len({effect.effect_id for effect in effects}) == len(effects)
    return program


@pytest.mark.parametrize("with_exits", [False, True])
def test_repeated_lambda_submission_has_per_submit_identity(tmp_path, with_exits):
    (tmp_path / "Fixture.java").write_text("// synthetic identity fixture\n" * 10, encoding="utf-8")
    target = "java-callable-v1:Fixture.lambda$task()V"
    common = dict(related_point="task:entry", related_start_line=4,
        target_event=target, holder_kind="queue", holder_scope="task",
        holder_key="Fixture.EXECUTOR#static", capacity="3", core_workers="1",
        max_workers="2", rejection_policy="abort")
    dispatches = [lifecycle_row(fact_kind=kind, program_point=f"submit:{line}",
        site_start_line=line, **common) for line in (2, 3) for kind in ("dispatch", "invariant")]
    exits = [lifecycle_row(fact_kind="task_exit", site_callable=target,
        program_point=f"task:{kind}", site_start_line=line, related_point="task:entry",
        related_start_line=4, target_event=target, normal_path=kind == "normal",
        exceptional_path=kind == "exceptional")
        for line, kind in ((5, "normal"), (6, "exceptional"))] if with_exits else []
    cfg = [lifecycle_row(fact_kind="cfg_edge", site_callable=target,
        program_point="task:entry", site_start_line=4,
        related_point=exit["program_point"], related_start_line=exit["site_start_line"],
        target_event=target, normal_path=True, exceptional_path=False,
        source_evidence="codeql_task_cfg_successor", coverage_note="reachable_task_cfg_edge")
        for exit in exits]
    # Positive control: the very same body already composes for one submit.
    single = formal_extract(tmp_path, [lifecycle_row()], dispatches[:2] + exits + cfg)
    assert_distinct_submissions(single, expected=1)
    double = formal_extract(tmp_path, [lifecycle_row()], dispatches + exits + cfg)
    program = assert_distinct_submissions(double)
    assert len(program.task_exits) == (4 if with_exits else 0)
    validate_extracted(double)


@pytest.mark.skipif(os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") != "1", reason="opt-in CodeQL fixture")
def test_repeated_submission_from_java_through_both_queries(tmp_path):
    source = ROOT / "tests/fixtures/resource_lifecycle_v1_1_repeated_submit/src/main/java"
    database = fixture_database(str(source))
    results = [run_query(query, database, tmp_path / name) for query, name in (
        (DIRECT_QUERY, "base"), (DIRECT_TASK_QUERY, "task"))]
    rows = [row for result in results for row in decode_bqrs_json(
        result.query_name, json.loads(result.decoded_path.read_text()),
        DecodeSource(database.source_root, result.query_sha256))]
    for method, raw_submits, task_count, depths in (
        ("caller", 2, 2, {1}),
        ("callerDepthTwo", 2, 2, {2}),
        ("callerMixedDepth", 4, 4, {1, 2}),
        ("callerSameDepthPrefixes", 2, 4, {2}),
    ):
        caller = f"java-callable-v1:fixture.repeated.RepeatedSubmit.{method}(I)V"
        selected_rows = [row for row in rows if row["unit_id"] == caller]
        submits = [row for row in selected_rows if row["fact_kind"] == "dispatch"]
        assert len(submits) == raw_submits, method
        assert len({row["program_point"] for row in submits}) == 2, method
        assert len({row["target_event"] for row in submits}) == 1, method
        assert {row["relation_depth"] for row in submits} == depths, method
        assert all(row["coverage_status"] == "complete" for row in submits), method
        extracted = adapt_codeql_rows(selected_rows, source_root=database.source_root,
            query_provenance=tuple({"query_name": result.query_name,
                "query_sha256": result.query_sha256, "bqrs_sha256": result.bqrs_sha256}
                for result in results), database_fingerprint=database.fingerprint,
            source_snapshot_sha256=commands._verify_database_source_snapshot(database))
        facts = {fact.fact_id: fact for fact in extracted.facts}
        expected_exits = set()
        for binding in extracted.units[0].program.task_bindings:
            dispatch = facts[binding.evidence_ids[0]]
            expected_exits.update((binding.task_id, fact.fact_id) for fact in extracted.facts
                if fact.fact_kind == "task_exit" and fact.coverage_status == "complete"
                and fact.instance_key == dispatch.instance_key
                and fact.target_event == dispatch.target_event
                and fact.relation_depth == dispatch.relation_depth
                and fact.related_point == dispatch.related_point)
        program = assert_context_tasks(extracted, task_count, body_count=len(expected_exits))
        assert {(exit.task_id, evidence) for exit in program.task_exits
            for evidence in exit.evidence_ids} == expected_exits, method
        assert {exit.task_id for exit in program.task_exits} == {task.task_id for task in program.task_bindings}
        releases = [effect for edge in program.transitions for effect in edge.effects
            if effect.kind == "release"]
        assert len(releases) == task_count, method
        assert len({effect.effect_id for effect in releases}) == task_count, method
        (tmp_path / f"{method}-facts.json").write_text(json.dumps(extracted_to_dict(extracted)), encoding="utf-8")


def context_graph_rows(links, extra_points=None):
    root = SYNTHETIC_HANDLE_ID
    rows = [lifecycle_row(program_point="create", source_evidence="codeql_closeable_allocation")]
    owners = {root} | {owner for source, target, _ in links for owner in (source, target)}
    for owner in sorted(owners):
        depths = {0} if owner == root else {depth for _, target, depth in links if target == owner}
        for depth in depths:
            points = [owner + "#cfg_entry"]
            if owner == root:
                points.append("create")
            points += [source + "->" + target for source, target, _ in links if source == owner]
            points += (extra_points or {}).get(owner, [])
            points.append(owner + "#cfg_normal_exit")
            for source, target in zip(points, points[1:]):
                evidence = "codeql_callable_cfg_entry" if source.endswith("#cfg_entry") else (
                    "codeql_callable_cfg_exit_after_success" if target.endswith("#cfg_normal_exit")
                    else "codeql_callable_cfg_edge")
                rows.append(lifecycle_row(fact_kind="cfg_edge", site_callable=owner,
                    program_point=source, related_point=target, relation_depth=depth,
                    target_event=owner, normal_path=True, exceptional_path=False,
                    source_evidence=evidence))
    for source, target, depth in links:
        rows.append(lifecycle_row(fact_kind="call_binding", site_callable=source,
            target_event=target, program_point=source + "->" + target,
            related_point=target + "#cfg_entry", relation_depth=depth, binding_index=0))
    return rows


def test_declared_call_depth_never_borrows_another_prefix(tmp_path):
    (tmp_path / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
    root, a, b, c = SYNTHETIC_HANDLE_ID, "callable:A", "callable:B", "callable:C"
    links = ((root, a, 1), (root, b, 1), (a, b, 2), (b, c, 2))
    rows = context_graph_rows(links)
    extracted = formal_extract(tmp_path, rows)
    assert formal_extract(tmp_path, list(reversed(rows))) == extracted
    program = extracted.units[0].program
    c_entries = {edge.target_event_id for edge in program.transitions
        if edge.guard == "exact call binding" and any(event.event_id == edge.target_event_id
            and event.callable == c for event in program.events)}
    expected = stable_identifier("event", {"unit_id": root,
        "program_point": c + "#cfg_entry", "call_context": (root + "->" + b, b + "->" + c)})
    assert c_entries == {expected}
    assert any(gap[3] == "call_binding_context_depth_mismatch" for gap in program.coverage_gaps)


def test_missing_call_prefix_retains_scoped_gap_without_relation(tmp_path):
    (tmp_path / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
    rows = context_graph_rows((("callable:B", "callable:C", 2),))
    extracted = formal_extract(tmp_path, rows)
    program = extracted.units[0].program
    assert not program.call_bindings
    assert not any(edge.guard == "exact call binding" for edge in program.transitions)
    fact = next(fact for fact in extracted.facts if fact.fact_kind == "call_binding")
    assert {gap[0] for gap in program.coverage_gaps
        if gap[3] == "call_binding_context_missing" and gap[4] == fact.fact_id} == {
            "held_instances", "item_size_bytes", "close_obligation"}


def test_call_context_budget_fails_closed_without_hash_order_truncation(tmp_path):
    (tmp_path / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
    rows = context_graph_rows(((SYNTHETIC_HANDLE_ID, "callable:A", 1),
        (SYNTHETIC_HANDLE_ID, "callable:B", 1), ("callable:A", "callable:B", 2)))
    with patch.object(adapters, "_MAX_CALL_CONTEXTS", 3, create=True):
        for ordered in (rows, list(reversed(rows))):
            with pytest.raises(ValueError, match="call context budget"):
                formal_extract(tmp_path, ordered)


def test_valid_depth_two_chain_is_retained(tmp_path):
    (tmp_path / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
    rows = context_graph_rows(((SYNTHETIC_HANDLE_ID, "callable:A", 1),
        ("callable:A", "callable:B", 2)))
    program = formal_extract(tmp_path, rows).units[0].program
    assert len(program.call_bindings) == 2
    assert sum(edge.guard == "exact call binding" for edge in program.transitions) == 2
    assert not any(gap[3].startswith("call_binding_context_") for gap in program.coverage_gaps)


def test_source_cfg_does_not_construct_discarded_fallback_effects(tmp_path):
    (tmp_path / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
    with patch.object(adapters, "_effect", wraps=adapters._effect) as build:
        program = formal_extract(tmp_path, context_graph_rows(())).units[0].program
    assert sum(len(edge.effects) for edge in program.transitions) == 3
    assert build.call_count == 3


def task_context_rows(links, depths, *, submit_count=1, body_depths=None):
    owner, target = "callable:B", "java-callable-v1:Fixture.lambda$context()V"
    submits = [f"submit:B:{index}" for index in range(submit_count)]
    base = context_graph_rows(links, {owner: submits})
    task = [lifecycle_row(fact_kind=kind, site_callable=owner,
        program_point=submit, related_point="task:entry", related_start_line=4,
        relation_depth=depth, binding_index=0, target_event=target,
        holder_kind="queue", holder_scope="task", holder_key="Fixture.EXECUTOR#static",
        capacity="3", core_workers="1", max_workers="2", rejection_policy="abort")
        for depth in depths for submit in submits for kind in ("dispatch", "invariant")]
    for depth in depths if body_depths is None else body_depths:
        task += [lifecycle_row(fact_kind="task_exit", site_callable=target,
            program_point="task:normal", site_start_line=5, related_point="task:entry",
            related_start_line=4, relation_depth=depth, target_event=target,
            normal_path=True, exceptional_path=False),
            lifecycle_row(fact_kind="cfg_edge", site_callable=target,
                program_point="task:entry", site_start_line=4, related_point="task:normal",
                related_start_line=5, relation_depth=depth, target_event=target,
                normal_path=True, exceptional_path=False,
                source_evidence="codeql_task_cfg_successor", coverage_note="reachable_task_cfg_edge"),
            lifecycle_row(fact_kind="release", site_callable=target,
                program_point="task:entry", site_start_line=4, related_point="task:normal",
                related_start_line=5, relation_depth=depth, target_event=target,
                normal_path=True, exceptional_path=False,
                source_evidence="codeql_task_callback_close_finally",
                coverage_note="exact_captured_task_finally_close")]
    return base, task


def assert_context_tasks(extracted, count, *, body_count=None):
    program = assert_distinct_submissions(extracted, expected=count)
    assert len(program.task_exits) == (count if body_count is None else body_count)
    attachments = [edge for edge in program.transitions if edge.guard == "source_submit_binding"]
    assert len(attachments) == count
    assert len({edge.source_event_id for edge in attachments}) == count
    assert len({edge.target_event_id for edge in attachments}) == count
    assert len(extracted.units[0].invariants) == count
    assert {candidate.writer_holder_id for candidate in extracted.units[0].invariants} == {
        task.holder_id for task in program.task_bindings}
    assert {candidate.writer_target_event_id for candidate in extracted.units[0].invariants} == {
        task.queued_event_id for task in program.task_bindings}
    assert len({candidate.candidate_id for candidate in extracted.units[0].invariants}) == count
    facts = {fact.fact_id: fact for fact in extracted.facts}
    tasks = {task.task_id: task for task in program.task_bindings}
    for exit in program.task_exits:
        assert facts[exit.evidence_ids[0]].relation_depth == facts[tasks[exit.task_id].evidence_ids[0]].relation_depth
    validate_extracted(extracted)
    return program


@pytest.mark.parametrize("shape", ["depth1", "depth2", "mixed_depth", "same_depth_prefixes"])
def test_task_identity_owns_full_call_context(tmp_path, shape):
    (tmp_path / "Fixture.java").write_text("// context fixture\n" * 8, encoding="utf-8")
    root, a, b, c = SYNTHETIC_HANDLE_ID, "callable:A", "callable:B", "callable:C"
    links, depths, count = {
        "depth1": (((root, b, 1),), (1,), 1),
        "depth2": (((root, a, 1), (a, b, 2)), (2,), 1),
        "mixed_depth": (((root, b, 1), (root, a, 1), (a, b, 2)), (1, 2), 2),
        "same_depth_prefixes": (((root, a, 1), (root, c, 1), (a, b, 2), (c, b, 2)), (2,), 2),
    }[shape]
    base, task = task_context_rows(links, depths)
    extracted = formal_extract(tmp_path, base, task)
    program = assert_context_tasks(extracted, count)
    assert len([effect for edge in program.transitions for effect in edge.effects if effect.kind == "release"]) == count


def test_task_body_cannot_borrow_other_depth_evidence(tmp_path):
    (tmp_path / "Fixture.java").write_text("// context fixture\n" * 8, encoding="utf-8")
    root, a, b = SYNTHETIC_HANDLE_ID, "callable:A", "callable:B"
    base, task = task_context_rows(((root, b, 1), (root, a, 1), (a, b, 2)), (1, 2), body_depths=(1,))
    extracted = formal_extract(tmp_path, base, task)
    program = assert_context_tasks(extracted, 2, body_count=1)
    assert sum(edge.guard == "task_cfg_edge" for edge in program.transitions) == 1
    assert sum(effect.kind == "release" for edge in program.transitions for effect in edge.effects) == 1
    depth2 = next(fact for fact in extracted.facts if fact.fact_kind == "dispatch" and fact.relation_depth == 2)
    assert any(gap[3] == "task_exit_coverage_unavailable" and gap[4] == depth2.fact_id for gap in program.coverage_gaps)


def test_task_context_product_has_early_hard_budget(tmp_path):
    (tmp_path / "Fixture.java").write_text("// context fixture\n" * 8, encoding="utf-8")
    root, a, b, c = SYNTHETIC_HANDLE_ID, "callable:A", "callable:B", "callable:C"
    base, task = task_context_rows(((root, a, 1), (root, c, 1), (a, b, 2), (c, b, 2)),
        (2,), submit_count=4)
    with patch.object(adapters, "_MAX_CALL_CONTEXTS", 6):
        with pytest.raises(ValueError, match="task context budget"):
            formal_extract(tmp_path, base, task)
