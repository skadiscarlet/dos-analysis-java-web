from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from dosweb.cli import main
from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.codeql import DecodeSource, QUERY_SPECS, QueryResult, decode_bqrs_json, decode_rows, run_query
from dosweb.codeql import runner as codeql_runner
from dosweb.codeql.database import DatabaseInfo
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle.adapters import (
    ExtractedFacts,
    _executor_contract_from_dict,
    _unit_from_rows,
    adapt_codeql_rows,
    extracted_from_dict,
    extracted_to_dict,
    validate_extracted,
)
from dosweb.resource_lifecycle import commands as lifecycle_commands
from dosweb.resource_lifecycle.invariants import check_invariants
from dosweb.resource_lifecycle.models import AnalysisBudget
from dosweb.resource_lifecycle.solver import solve
from tests.support.fixture_database import fixture_database


ROOT = Path(__file__).resolve().parents[1]
DIRECT_QUERY = ROOT / "codeql/dosweb/ResourceLifecycle/ResourceLifecycleFacts.ql"
EMBEDDED_QUERY = ROOT / "dosweb/codeql/pack/dosweb/ResourceLifecycle/ResourceLifecycleFacts.ql"
DIRECT_TASK_QUERY = ROOT / "codeql/dosweb/ResourceLifecycle/ResourceLifecycleTaskRelations.ql"
EMBEDDED_TASK_QUERY = ROOT / "dosweb/codeql/pack/dosweb/ResourceLifecycle/ResourceLifecycleTaskRelations.ql"
RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
SYNTHETIC_HANDLE_ID = "java-callable-v1:Fixture.handle()V"
SYNTHETIC_SOURCE = "final class Fixture {\n\n\n}\n"


def fixture_callable(method: str, descriptor: str) -> str:
    return f"java-callable-v1:fixture.lifecycle.LifecycleFixture.{method}{descriptor}"


def fixture_v1_1_callable(method: str, descriptor: str) -> str:
    return f"java-callable-v1:fixture.lifecyclev11.SourcePairs.{method}{descriptor}"


def decoded_lifecycle_row(source_root: Path, query_sha256: str = "a" * 64) -> dict[str, object]:
    row = lifecycle_row()
    values = [row[column] for column in QUERY_SPECS["resource_lifecycle"].columns]
    return decode_rows(
        "resource_lifecycle",
        QUERY_SPECS["resource_lifecycle"].columns,
        [values],
        DecodeSource(source_root, query_sha256),
    )[0]


def decoded_query_row(
    source_root: Path,
    query_name: str,
    query_sha256: str,
    **overrides: object,
) -> dict[str, object]:
    row = lifecycle_row(**overrides)
    spec = QUERY_SPECS[query_name]
    values = [row[column] for column in spec.columns]
    return decode_rows(
        query_name,
        spec.columns,
        [values],
        DecodeSource(source_root, query_sha256),
    )[0]


def lifecycle_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "unit_id": SYNTHETIC_HANDLE_ID,
        "site_callable": SYNTHETIC_HANDLE_ID,
        "site_file": "Fixture.java",
        "site_start_line": 1,
        "site_start_column": 1,
        "program_point": "point:Fixture.java:1:1:create",
        "related_point": "none",
        "related_file": "Fixture.java",
        "related_start_line": 1,
        "related_start_column": 1,
        "relation_depth": 0,
        "binding_index": -1,
        "fact_kind": "create",
        "instance_key": "Fixture.java:1:1",
        "resource_type": "fixture.Resource",
        "requires_close": True,
        "holder_kind": "none",
        "holder_scope": "none",
        "holder_key": "none",
        "target_event": "none",
        "capacity": "unknown",
        "core_workers": "unknown",
        "max_workers": "unknown",
        "rejection_policy": "unknown",
        "normal_path": True,
        "exceptional_path": True,
        "source_evidence": "test",
        "coverage_status": "complete",
        "coverage_note": "test",
    }
    row.update(overrides)
    return row


_V1_1_FACT_FIELDS = {
    "query_name",
    "query_sha256",
    "site_callable",
    "program_point",
    "related_point",
    "related_location",
    "related_start_column",
    "relation_depth",
    "binding_index",
    "core_workers",
    "max_workers",
    "rejection_policy",
}


def _legacy_fact(current_fact):
    semantic = {
        "unit_id": current_fact.unit_id,
        "site_file": current_fact.location.path,
        "site_start_line": current_fact.location.start_line,
        "site_start_column": current_fact.site_start_column,
        "fact_kind": current_fact.fact_kind,
        "instance_key": current_fact.instance_key,
        "resource_type": current_fact.resource_type,
        "requires_close": current_fact.requires_close,
        "holder_kind": current_fact.holder_kind,
        "holder_scope": current_fact.holder_scope,
        "holder_key": current_fact.holder_key,
        "target_event": current_fact.target_event,
        "capacity": current_fact.capacity,
        "normal_path": current_fact.normal_path,
        "exceptional_path": current_fact.exceptional_path,
        "source_evidence": current_fact.source_evidence,
        "coverage_status": current_fact.coverage_status,
        "coverage_note": current_fact.coverage_note,
    }
    return replace(
        current_fact,
        fact_id=stable_identifier(
            "lifecycle-fact",
            {
                **semantic,
                "source_sha256": current_fact.location.source_sha256,
                "query_sha256": "a" * 64,
            },
        ),
    )


def _legacy_facts_payload(current, *, legacy_executor_identity: bool = False):
    facts = tuple(_legacy_fact(fact) for fact in current.facts)
    grouped = {
        unit_id: tuple(fact for fact in facts if fact.unit_id == unit_id)
        for unit_id in sorted({fact.unit_id for fact in facts})
    }
    selected = set(current.coverage["requested_entry_methods"])
    units = [
        _unit_from_rows(
            unit_id,
            grouped[unit_id],
            external_entry=unit_id in selected,
        )
        for unit_id in grouped
    ]
    if legacy_executor_identity:
        migrated_units = []
        for unit in units:
            contract_ids: dict[str, str] = {}
            for fact in grouped[unit.unit_id]:
                if fact.fact_kind != "dispatch":
                    continue
                holder_id = stable_identifier(
                    "holder",
                    {
                        "unit_id": unit.unit_id,
                        "holder_key": fact.holder_key,
                        "kind": "task",
                        "scope": fact.holder_scope,
                    },
                )
                target_event_id = stable_identifier(
                    "event",
                    {
                        "unit_id": unit.unit_id,
                        "phase": "task_queue",
                        "target_event": fact.target_event,
                    },
                )
                current_id = stable_identifier(
                    "executor-contract",
                    {
                        "unit_id": unit.unit_id,
                        "holder_id": holder_id,
                        "holder_key": fact.holder_key,
                        "target_event": fact.target_event,
                        "target_event_id": target_event_id,
                        "capacity": fact.capacity,
                        "core_workers": fact.core_workers,
                        "max_workers": fact.max_workers,
                        "rejection_policy": fact.rejection_policy,
                    },
                )
                contract_ids[current_id] = stable_identifier(
                    "executor-contract",
                    {
                        "unit_id": unit.unit_id,
                        "holder_id": holder_id,
                        "holder_key": fact.holder_key,
                        "target_event": fact.target_event,
                        "target_event_id": target_event_id,
                        "capacity": fact.capacity,
                    },
                )
            transitions = tuple(
                replace(
                    transition,
                    effects=tuple(
                        replace(
                            effect,
                            contract_id=contract_ids.get(
                                effect.contract_id, effect.contract_id
                            ),
                        )
                        for effect in transition.effects
                    ),
                )
                for transition in unit.program.transitions
            )
            coverage_gaps = tuple(
                (
                    dimension,
                    family_id,
                    next(
                        (
                            scope.replace(current_id, legacy_id)
                            for current_id, legacy_id in contract_ids.items()
                            if current_id in scope
                        ),
                        scope,
                    ),
                    reason,
                    evidence_id,
                )
                for dimension, family_id, scope, reason, evidence_id in unit.program.coverage_gaps
            )
            migrated_units.append(
                replace(
                    unit,
                    program=replace(
                        unit.program,
                        transitions=transitions,
                        coverage_gaps=coverage_gaps,
                    ),
                    invariants=tuple(
                        replace(
                            invariant,
                            executor_contract_id=contract_ids.get(
                                invariant.executor_contract_id,
                                invariant.executor_contract_id,
                            ),
                        )
                        for invariant in unit.invariants
                    ),
                    executor_contracts=tuple(
                        replace(
                            contract,
                            contract_id=contract_ids.get(
                                contract.contract_id, contract.contract_id
                            ),
                            rejection_drops_capture=True,
                        )
                        for contract in unit.executor_contracts
                    ),
                )
            )
        units = migrated_units
    legacy_fact_payloads = [
        {
            key: value
            for key, value in asdict(fact).items()
            if key not in _V1_1_FACT_FIELDS
        }
        for fact in facts
    ]
    legacy = ExtractedFacts(
        current.source_kind,
        hashlib.sha256(canonical_json(legacy_fact_payloads)).hexdigest(),
        current.extractor_version,
        current.budget,
        tuple(units),
        facts,
        {
            **current.coverage,
            "end_to_end_mode": "imported_static_facts",
            "source_snapshot_sha256": "b" * 64,
        },
    )
    payload = json.loads(json.dumps(extracted_to_dict(legacy)))
    payload["schema_version"] = "1.0"
    for unit in payload["units"]:
        unit["program"]["schema_version"] = "1.0"
        for field in (
            "program_points",
            "call_bindings",
            "task_bindings",
            "task_exits",
        ):
            unit["program"].pop(field)
        for transition in unit["program"]["transitions"]:
            transition.pop("population_effects")
        for contract in unit["executor_contracts"]:
            contract.pop("core_workers")
            contract.pop("max_workers")
            contract.pop("rejection_policy")
            contract.pop("termination")
    for fact in payload["facts"]:
        for field in _V1_1_FACT_FIELDS:
            fact.pop(field)
    return payload


class ResourceLifecycleCodeqlContractTests(unittest.TestCase):
    def test_schema_1_0_facts_loader_defaults_missing_relation_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "final class Fixture {}\n", encoding="utf-8"
            )
            current = adapt_codeql_rows(
                (lifecycle_row(),),
                source_root=source_root,
                query_sha256="a" * 64,
            )
        payload = _legacy_facts_payload(current)

        rebuilt = validate_extracted(extracted_from_dict(payload))

        self.assertEqual(SYNTHETIC_HANDLE_ID, rebuilt.facts[0].site_callable)
        self.assertEqual("none", rebuilt.facts[0].related_point)
        self.assertEqual(0, rebuilt.facts[0].relation_depth)
        self.assertEqual(-1, rebuilt.facts[0].binding_index)
        self.assertEqual("unknown", rebuilt.facts[0].max_workers)
        self.assertEqual("unknown", rebuilt.facts[0].rejection_policy)

    def test_schema_1_0_facts_migrates_legacy_executor_contract_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "final class Fixture {}\n", encoding="utf-8"
            )
            current = adapt_codeql_rows(
                (
                    lifecycle_row(),
                    lifecycle_row(
                        fact_kind="dispatch",
                        site_start_column=2,
                        program_point="point:Fixture.java:1:2:dispatch",
                        holder_kind="queue",
                        holder_scope="task",
                        holder_key="queue:jobs",
                        target_event="Fixture.task",
                        capacity="2",
                        source_evidence="dispatch",
                    ),
                ),
                source_root=source_root,
                query_sha256="a" * 64,
            )
        payload = _legacy_facts_payload(current, legacy_executor_identity=True)
        legacy_contract_id = payload["units"][0]["executor_contracts"][0][
            "contract_id"
        ]

        rebuilt = validate_extracted(extracted_from_dict(payload))

        self.assertEqual(1, len(rebuilt.units[0].executor_contracts))
        self.assertNotEqual(
            legacy_contract_id,
            rebuilt.units[0].executor_contracts[0].contract_id,
        )
        self.assertIsNone(rebuilt.units[0].executor_contracts[0].max_workers)
        self.assertEqual(
            "unknown", rebuilt.units[0].executor_contracts[0].rejection_policy
        )
        self.assertEqual("unknown", rebuilt.units[0].executor_contracts[0].termination)

    def test_schema_1_1_facts_requires_every_executor_semantic_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "final class Fixture {}\n", encoding="utf-8"
            )
            current = adapt_codeql_rows(
                (
                    lifecycle_row(),
                    lifecycle_row(
                        fact_kind="dispatch",
                        site_start_column=2,
                        program_point="point:Fixture.java:1:2:dispatch",
                        holder_kind="queue",
                        holder_scope="task",
                        holder_key="queue:jobs",
                        target_event="Fixture.task",
                        capacity="2",
                        source_evidence="dispatch",
                    ),
                ),
                source_root=source_root,
                query_sha256="a" * 64,
            )
            current = replace(
                current,
                coverage={
                    **current.coverage,
                    "source_snapshot_sha256": lifecycle_commands._java_source_snapshot(
                        source_root
                    )[1],
                },
            )
            payload = json.loads(json.dumps(extracted_to_dict(current)))

            for field in (
                "core_workers",
                "max_workers",
                "rejection_policy",
                "termination",
            ):
                invalid = json.loads(json.dumps(payload))
                invalid["units"][0]["executor_contracts"][0].pop(field)
                with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, "schema 1.1 executor contract"
                ):
                    validate_extracted(extracted_from_dict(invalid))

            invalid = json.loads(json.dumps(payload))
            invalid_contract = invalid["units"][0]["executor_contracts"][0]
            invalid_contract["rejection_policy"] = "unknown"
            invalid_contract["rejection_drops_capture"] = True
            with self.subTest(field="rejection_policy_consistency"), self.assertRaisesRegex(
                ValueError, "rejection policy"
            ):
                validate_extracted(extracted_from_dict(invalid))

    def test_schema_1_0_executor_booleans_migrate_without_inventing_policy(self) -> None:
        legacy = {
            "contract_id": "contract:legacy",
            "scheduling": "queued",
            "queue_capacity": 4,
            "capacity_atomic": True,
            "completion_drops_capture": True,
            "rejection_drops_capture": True,
            "cancellation": "unknown",
            "source_kind": "static_verified",
            "version": "executor-contract-v1",
        }

        migrated = _executor_contract_from_dict(legacy, schema_version="1.0")

        self.assertEqual("drops_capture", migrated.termination)
        self.assertEqual("unknown", migrated.rejection_policy)
        self.assertIsNone(migrated.core_workers)
        self.assertTrue(migrated.rejection_drops_capture)

    def test_schema_1_1_is_used_for_lifecycle_facts_and_program_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "final class Fixture {}\n", encoding="utf-8"
            )
            extracted = adapt_codeql_rows(
                (lifecycle_row(),),
                source_root=source_root,
                query_sha256="a" * 64,
            )

        serialized = extracted_to_dict(extracted)

        self.assertEqual("1.1", serialized["schema_version"])
        self.assertEqual("1.1", serialized["units"][0]["program"]["schema_version"])

    def test_schema_1_1_rejects_negative_raw_executor_limits(self) -> None:
        for field in ("capacity", "max_workers"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                source_root = Path(tmp)
                (source_root / "Fixture.java").write_text(
                    "final class Fixture {}\n", encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "positive"):
                    adapt_codeql_rows(
                        (lifecycle_row(**{field: "-1"}),),
                        source_root=source_root,
                        query_sha256="a" * 64,
                    )

    def test_v1_1_relation_columns_are_strict_decoder_inputs(self) -> None:
        required = {
            "site_callable",
            "program_point",
            "related_point",
            "relation_depth",
            "binding_index",
            "max_workers",
            "rejection_policy",
        }
        self.assertTrue(required <= set(QUERY_SPECS["resource_lifecycle"].columns))
        self.assertEqual(
            "integer",
            QUERY_SPECS["resource_lifecycle"].field_types["relation_depth"],
        )
        self.assertEqual(
            "integer",
            QUERY_SPECS["resource_lifecycle"].field_types["binding_index"],
        )
        self.assertEqual(
            frozenset(
                {"abort", "caller_runs", "discard", "discard_oldest", "unknown"}
            ),
            QUERY_SPECS["resource_lifecycle"].enum_fields["rejection_policy"],
        )

    def test_split_query_specs_reject_foreign_fact_kinds(self) -> None:
        self.assertIn("resource_lifecycle_task_relations", QUERY_SPECS)
        task_spec = QUERY_SPECS.get("resource_lifecycle_task_relations")
        if task_spec is None:
            return
        self.assertEqual(
            QUERY_SPECS["resource_lifecycle"].columns,
            task_spec.columns,
        )
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                SYNTHETIC_SOURCE, encoding="utf-8"
            )
            for query_name, fact_kind in (
                ("resource_lifecycle", "task_exit"),
                ("resource_lifecycle_task_relations", "create"),
                ("resource_lifecycle_task_relations", "retain"),
            ):
                spec = QUERY_SPECS[query_name]
                row = lifecycle_row(fact_kind=fact_kind)
                values = [row[column] for column in spec.columns]
                with self.subTest(query_name=query_name, fact_kind=fact_kind):
                    with self.assertRaises(AnalyzerError) as raised:
                        decode_rows(
                            query_name,
                            spec.columns,
                            [values],
                            DecodeSource(source_root, "a" * 64),
                        )
                    self.assertEqual("ENUM_INVALID", raised.exception.details["reason"])
            task_spec = QUERY_SPECS["resource_lifecycle_task_relations"]
            task_release = lifecycle_row(fact_kind="release")
            decoded = decode_rows(
                "resource_lifecycle_task_relations",
                task_spec.columns,
                [[task_release[column] for column in task_spec.columns]],
                DecodeSource(source_root, "a" * 64),
            )
            self.assertEqual("release", decoded[0]["fact_kind"])

    def _base_source_cfg_release_states(self, coverage, evidence, note, *, call_failed=False):
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("// synthetic raw CFG fixture\n" * 8)
            owner = SYNTHETIC_HANDLE_ID
            create_point, close_point, after_point = "point:create", "point:close", "point:after"

            def row(**fields):
                return decoded_query_row(source_root, "resource_lifecycle", "a" * 64, **fields)

            def cfg(source, target, line, related_line, source_evidence):
                return row(fact_kind="cfg_edge", program_point=source, related_point=target,
                           site_start_line=line, related_start_line=related_line,
                           target_event=owner, normal_path=True, exceptional_path=False,
                           source_evidence=source_evidence)

            rows = [
                row(program_point=create_point, site_start_line=2,
                    source_evidence="codeql_closeable_allocation"),
                row(fact_kind="retain", program_point=create_point, site_start_line=2,
                    holder_kind="field", holder_scope="global", holder_key="Fixture.shared#static"),
                cfg(owner + "#cfg_entry", create_point, 1, 2, "codeql_callable_cfg_entry"),
                cfg(create_point, close_point, 2, 3, "codeql_callable_cfg_edge"),
                row(fact_kind="release", program_point=close_point, site_start_line=3,
                    coverage_status=coverage, coverage_note=note, source_evidence=evidence,
                    normal_path=evidence != "ambiguous_alias", exceptional_path=coverage == "complete"),
            ]
            if call_failed:
                rows.append(cfg(close_point, owner + "#cfg_normal_exit", 3, 1,
                                "codeql_callable_cfg_exit_after_exception"))
            else:
                rows.extend((cfg(close_point, after_point, 3, 4, "codeql_callable_cfg_edge"),
                             cfg(after_point, owner + "#cfg_normal_exit", 4, 1,
                                 "codeql_callable_cfg_exit_after_success")))
            extracted = adapt_codeql_rows(rows, source_root=source_root, query_sha256="a" * 64)
        program = extracted.units[0].program
        result = solve(program, budget=AnalysisBudget())
        close_event = next(event.event_id for event in program.events if event.activation_condition == close_point)
        close_edge = next(edge for edge in program.transitions if edge.source_event_id == close_event)
        return extracted, result.event_states[close_event], result.event_states[close_edge.target_event_id], close_edge

    def test_base_source_cfg_partial_release_preserves_state(self) -> None:
        cases = (
            ("partial", "ambiguous_alias", "conditional_release_not_must", False),
            ("partial", "codeql_parameter_close_effect", "conditional_release_not_must", False),
            ("unsupported", "codeql_close_receiver_local_flow_candidate", "unsupported_receiver_identity", False),
            ("complete", "codeql_close_receiver_local_flow_candidate", "singleton_finally_exact_local_release", True),
        )
        for coverage, evidence, note, released in cases:
            with self.subTest(coverage=coverage, evidence=evidence):
                extracted, before, after, edge = self._base_source_cfg_release_states(coverage, evidence, note)
                self.assertTrue(before.open_obligations)
                self.assertEqual(before.held_edges, after.held_edges, "Close must not erase holder edges")
                self.assertEqual(before.held_counts, after.held_counts)
                if released:
                    self.assertFalse(after.open_obligations)
                    self.assertTrue(all(count.upper == 0 for _, count in after.obligation_counts))
                else:
                    self.assertEqual(before.open_obligations, after.open_obligations)
                    self.assertEqual(before.instance_obligation_counts, after.instance_obligation_counts)
                    self.assertEqual(before.obligation_counts, after.obligation_counts)
                    release_fact = next(fact for fact in extracted.facts if fact.fact_kind == "release")
                    self.assertTrue(any(point.point_id == release_fact.program_point
                                        for point in extracted.units[0].program.program_points))
                    self.assertTrue(any(gap[4] == release_fact.fact_id
                                        for gap in extracted.units[0].program.coverage_gaps))
                self.assertEqual(released, any(effect.kind == "release" for effect in edge.effects))

    def test_base_source_cfg_complete_release_requires_call_success(self) -> None:
        _, before, after, edge = self._base_source_cfg_release_states(
            "complete", "codeql_close_receiver_local_flow_candidate", "singleton_finally_exact_local_release",
            call_failed=True,
        )
        self.assertEqual(before.open_obligations, after.open_obligations)
        self.assertEqual(before.obligation_counts, after.obligation_counts)
        self.assertEqual(before.held_counts, after.held_counts)
        self.assertFalse(any(effect.kind == "release" for effect in edge.effects))

    def test_base_source_without_cfg_never_executes_fallback_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("// missing source CFG\n" * 8)
            wrapper = "java-callable-v1:Fixture.wrapper(Lfixture/Resource;)V"
            for coverage in ("complete", "partial", "unsupported"):
                with self.subTest(coverage=coverage):
                    def row(**fields):
                        return decoded_query_row(source_root, "resource_lifecycle", "a" * 64, **fields)
                    rows = [
                        row(source_evidence="codeql_closeable_allocation"),
                        row(fact_kind="release", program_point="point:root:close",
                            coverage_status=coverage, normal_path=True, exceptional_path=True,
                            source_evidence="codeql_close_receiver_local_flow_candidate",
                            coverage_note="singleton_finally_exact_local_release"),
                        row(fact_kind="call_binding", site_start_line=2, related_start_line=3,
                            program_point="point:call", related_point="point:parameter",
                            relation_depth=1, binding_index=0, target_event=wrapper),
                        row(fact_kind="cfg_edge", site_callable=wrapper,
                            site_start_line=3, related_start_line=4, relation_depth=1,
                            program_point="point:parameter", related_point="point:close",
                            target_event=wrapper, source_evidence="codeql_parameter_cfg_entry"),
                        row(fact_kind="release", site_callable=wrapper, site_start_line=4,
                            program_point="point:close", relation_depth=1,
                            coverage_status=coverage, normal_path=True, exceptional_path=True,
                            source_evidence="codeql_parameter_close_effect"),
                    ]
                    extracted = adapt_codeql_rows(rows, source_root=source_root, query_sha256="a" * 64)
                    unit = extracted.units[0]
                    self.assertFalse(any(effect.kind == "release"
                                         for edge in unit.program.transitions for effect in edge.effects))
                    releases = [fact for fact in extracted.facts if fact.fact_kind == "release"]
                    self.assertEqual(2, len(releases))
                    self.assertTrue({fact.program_point for fact in releases}
                                    <= {point.point_id for point in unit.program.program_points})
                    self.assertTrue(any(gap[3] == "callable_cfg_unavailable" for gap in unit.program.coverage_gaps))
                    self.assertTrue({fact.fact_id for fact in releases}
                                    <= {gap[4] for gap in unit.program.coverage_gaps})
                    result = solve(unit.program, budget=AnalysisBudget())
                    dimensions = check_invariants(unit.program, result, unit.invariants,
                                                  timeout_ms=100, executor_contracts=unit.executor_contracts)
                    self.assertTrue(all(value.lifecycle_status == "unknown" for value in dimensions
                                        if value.dimension == "close_obligation"))

    def test_synthetic_complete_wrapper_release_keeps_legacy_import_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "\n".join(f"// line {line}" for line in range(1, 9)) + "\n",
                encoding="utf-8",
            )
            wrapper = "java-callable-v1:Fixture.wrapper(Lfixture/Resource;)V"
            create = decoded_query_row(
                source_root,
                "resource_lifecycle",
                "a" * 64,
                program_point="point:1:create",
            )
            binding = decoded_query_row(
                source_root,
                "resource_lifecycle",
                "a" * 64,
                fact_kind="call_binding",
                site_start_line=2,
                related_start_line=3,
                program_point="point:2:call",
                related_point="point:3:parameter",
                relation_depth=1,
                binding_index=0,
                target_event=wrapper,
            )
            cfg_edge = decoded_query_row(
                source_root,
                "resource_lifecycle",
                "a" * 64,
                fact_kind="cfg_edge",
                site_callable=wrapper,
                site_start_line=3,
                related_start_line=4,
                program_point="point:3:parameter",
                related_point="point:4:close",
                relation_depth=1,
                target_event=wrapper,
            )
            release = decoded_query_row(
                source_root,
                "resource_lifecycle",
                "a" * 64,
                fact_kind="release",
                site_callable=wrapper,
                site_start_line=4,
                related_start_line=4,
                program_point="point:4:close",
                normal_path=True,
                exceptional_path=True,
                relation_depth=1,
                source_evidence="codeql_parameter_close_effect",
            )

            extracted = adapt_codeql_rows(
                (create, binding, cfg_edge, release),
                source_root=source_root,
                query_sha256="a" * 64,
            )

        unit = extracted.units[0]
        self.assertTrue(all(fact.source_evidence == "test" for fact in extracted.facts
                            if fact.fact_kind == "create"))
        release_fact = next(
            fact for fact in extracted.facts if fact.fact_kind == "release"
        )
        transition = next(
            transition
            for transition in unit.program.transitions
            if any(
                release_fact.fact_id in effect.evidence_ids
                for effect in transition.effects
            )
        )
        events = {event.event_id: event for event in unit.program.events}
        self.assertEqual(
            "point:3:parameter",
            events[transition.source_event_id].activation_condition,
        )
        self.assertEqual(
            "point:4:close",
            events[transition.target_event_id].activation_condition,
        )
        self.assertEqual(("release",), tuple(effect.kind for effect in transition.effects))
        self.assertTrue(
            any(
                events[edge.source_event_id].activation_condition
                == "point:2:call"
                and events[edge.target_event_id].activation_condition
                == "point:3:parameter"
                and not edge.effects
                for edge in unit.program.transitions
            )
        )
        self.assertEqual(
            1,
            sum(
                release_fact.fact_id in effect.evidence_ids
                for edge in unit.program.transitions
                for effect in edge.effects
            ),
        )

    def test_base_cfg_attaches_wrapper_summary_effect_kinds_and_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "\n".join(f"// line {line}" for line in range(1, 11)) + "\n",
                encoding="utf-8",
            )
            wrapper = "java-callable-v1:Fixture.wrapper(Lfixture/Resource;)V"
            rows = [
                decoded_query_row(
                    source_root,
                    "resource_lifecycle",
                    "a" * 64,
                    program_point="point:1:create",
                ),
                decoded_query_row(
                    source_root,
                    "resource_lifecycle",
                    "a" * 64,
                    fact_kind="call_binding",
                    site_start_line=2,
                    related_start_line=3,
                    program_point="point:2:call",
                    related_point="point:3:parameter",
                    relation_depth=1,
                    binding_index=0,
                    target_event=wrapper,
                ),
            ]
            for source_line, source_name, target_line, target_name in (
                (3, "parameter", 4, "retain"),
                (4, "retain", 5, "close"),
                (5, "close", 6, "return"),
            ):
                rows.append(
                    decoded_query_row(
                        source_root,
                        "resource_lifecycle",
                        "a" * 64,
                        fact_kind="cfg_edge",
                        site_callable=wrapper,
                        site_start_line=source_line,
                        related_start_line=target_line,
                        program_point=f"point:{source_line}:{source_name}",
                        related_point=f"point:{target_line}:{target_name}",
                        relation_depth=1,
                        target_event=wrapper,
                    )
                )
            rows.extend(
                (
                    decoded_query_row(
                        source_root,
                        "resource_lifecycle",
                        "a" * 64,
                        fact_kind="retain",
                        site_callable=wrapper,
                        site_start_line=4,
                        related_start_line=4,
                        program_point="point:4:retain",
                        relation_depth=1,
                        holder_kind="field",
                        holder_scope="global",
                        holder_key="Fixture.SHARED#static",
                        source_evidence="codeql_parameter_to_static_field_effect",
                    ),
                    decoded_query_row(
                        source_root,
                        "resource_lifecycle",
                        "a" * 64,
                        fact_kind="release",
                        site_callable=wrapper,
                        site_start_line=5,
                        related_start_line=5,
                        program_point="point:5:close",
                        relation_depth=1,
                        normal_path=True,
                        exceptional_path=False,
                        coverage_status="partial",
                        coverage_note="conditional_release_not_must",
                        source_evidence="codeql_parameter_close_effect",
                    ),
                    decoded_query_row(
                        source_root,
                        "resource_lifecycle",
                        "a" * 64,
                        fact_kind="unknown_call",
                        site_callable=wrapper,
                        site_start_line=6,
                        related_start_line=6,
                        program_point="point:6:return",
                        relation_depth=1,
                        normal_path=True,
                        exceptional_path=False,
                        coverage_status="partial",
                        coverage_note="returned_resource_ownership_unmodeled",
                        source_evidence="codeql_parameter_return_effect",
                    ),
                )
            )

            extracted = adapt_codeql_rows(
                rows, source_root=source_root, query_sha256="a" * 64
            )

        unit = extracted.units[0]
        event_by_id = {event.event_id: event for event in unit.program.events}
        attached = {
            event_by_id[transition.target_event_id].activation_condition: effect
            for transition in unit.program.transitions
            for effect in transition.effects
            if any(
                fact.site_callable == wrapper
                and fact.fact_id in effect.evidence_ids
                for fact in extracted.facts
            )
        }
        self.assertEqual(
            {"point:4:retain", "point:6:return"},
            set(attached),
        )
        self.assertEqual("retain", attached["point:4:retain"].kind)
        release_fact = next(fact for fact in extracted.facts if fact.fact_kind == "release")
        self.assertTrue(any(point.point_id == release_fact.program_point
                            for point in unit.program.program_points))
        self.assertTrue(any(gap[4] == release_fact.fact_id for gap in unit.program.coverage_gaps))
        self.assertEqual("unknown_call", attached["point:6:return"].kind)
        self.assertEqual("normal_path", attached["point:6:return"].condition)
        return_point = next(
            point
            for point in unit.program.program_points
            if point.point_id == "point:6:return"
        )
        self.assertEqual("return", return_point.kind)
        self.assertEqual(
            2,
            sum(
                fact.site_callable == wrapper
                and fact.fact_id in effect.evidence_ids
                for transition in unit.program.transitions
                for effect in transition.effects
                for fact in extracted.facts
            ),
        )

    def test_lifecycle_rows_bind_related_location(self) -> None:
        required = {
            "related_file",
            "related_start_line",
            "related_start_column",
        }

        self.assertTrue(
            required <= set(QUERY_SPECS["resource_lifecycle"].columns)
        )
        self.assertTrue(
            required
            <= set(QUERY_SPECS["resource_lifecycle_task_relations"].columns)
        )

    def test_base_query_projects_related_parameter_location_outside_recursive_relation(self) -> None:
        query = DIRECT_QUERY.read_text(encoding="utf-8")
        relation = query.split("predicate lifecycleRelationFact(", 1)[1].split(
            "predicate resourceLifecycleRow(", 1
        )[0]
        row_projection = query.split("predicate resourceLifecycleRow(", 1)[1]

        self.assertNotIn("parameter.getLocation()", relation)
        self.assertIn("relatedParameter.getLocation()", row_projection)

    def test_task_query_uses_immediate_cfg_edges_only(self) -> None:
        query = DIRECT_TASK_QUERY.read_text(encoding="utf-8")

        self.assertNotIn("getASuccessor+()", query)

    def test_lifecycle_rows_expose_thread_pool_core_workers(self) -> None:
        self.assertIn(
            "core_workers", QUERY_SPECS["resource_lifecycle"].columns
        )
        self.assertIn(
            "core_workers",
            QUERY_SPECS["resource_lifecycle_task_relations"].columns,
        )

    def test_related_program_point_uses_target_source_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                SYNTHETIC_SOURCE, encoding="utf-8"
            )
            create = decoded_query_row(
                source_root, "resource_lifecycle", "a" * 64
            )
            binding = decoded_query_row(
                source_root,
                "resource_lifecycle",
                "a" * 64,
                fact_kind="call_binding",
                program_point="point:Fixture.java:1:1:call",
                related_point="point:Fixture.java:4:1:parameter",
                related_file="Fixture.java",
                related_start_line=4,
                related_start_column=1,
                relation_depth=1,
                binding_index=0,
                target_event="java-callable-v1:Fixture.wrapper(Ljava/lang/Object;)V",
            )

            extracted = adapt_codeql_rows(
                (create, binding),
                source_root=source_root,
                query_sha256="a" * 64,
            )

        point = next(
            item
            for item in extracted.units[0].program.program_points
            if item.point_id == binding["related_point"]
        )
        self.assertEqual(4, point.location.start_line)

    def test_thread_pool_contract_binds_core_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                SYNTHETIC_SOURCE, encoding="utf-8"
            )
            create = decoded_query_row(
                source_root, "resource_lifecycle", "a" * 64
            )
            task_callable = "java-callable-v1:Fixture.lambda$task()V"
            dispatch = decoded_query_row(
                source_root,
                "resource_lifecycle_task_relations",
                "b" * 64,
                fact_kind="dispatch",
                program_point="point:Fixture.java:1:1:dispatch",
                related_point="point:Fixture.java:2:1:task-entry",
                related_start_line=2,
                holder_kind="queue",
                holder_scope="task",
                holder_key="Fixture.EXECUTOR#static",
                target_event=task_callable,
                capacity="3",
                core_workers="1",
                max_workers="2",
                rejection_policy="abort",
            )
            exits = tuple(
                decoded_query_row(
                    source_root,
                    "resource_lifecycle_task_relations",
                    "b" * 64,
                    fact_kind="task_exit",
                    site_callable=task_callable,
                    program_point=f"point:Fixture.java:{line}:1:{kind}",
                    site_start_line=line,
                    related_point="point:Fixture.java:2:1:task-entry",
                    related_start_line=2,
                    target_event=task_callable,
                    normal_path=kind == "normal",
                    exceptional_path=kind == "exceptional",
                )
                for line, kind in ((3, "normal"), (4, "exceptional"))
            )
            cfg_edges = tuple(
                decoded_query_row(
                    source_root,
                    "resource_lifecycle_task_relations",
                    "b" * 64,
                    fact_kind="cfg_edge",
                    site_callable=task_callable,
                    program_point="point:Fixture.java:2:1:task-entry",
                    site_start_line=2,
                    related_point=exit_row["program_point"],
                    related_start_line=exit_row["site_start_line"],
                    target_event=task_callable,
                )
                for exit_row in exits
            )
            extracted = adapt_codeql_rows(
                (create, dispatch, *cfg_edges, *exits),
                source_root=source_root,
                query_provenance=(
                    {
                        "query_name": "resource_lifecycle",
                        "query_sha256": "a" * 64,
                        "bqrs_sha256": "c" * 64,
                    },
                    {
                        "query_name": "resource_lifecycle_task_relations",
                        "query_sha256": "b" * 64,
                        "bqrs_sha256": "d" * 64,
                    },
                ),
                database_fingerprint="e" * 64,
                source_snapshot_sha256="f" * 64,
            )

        unit = extracted.units[0]
        self.assertEqual(1, unit.executor_contracts[0].core_workers)
        direct_accept = next(
            effect
            for transition in unit.program.transitions
            for effect in transition.population_effects
            if effect.kind == "direct_accept"
        )
        self.assertEqual("a<C or (q>=K and a<W)", direct_accept.guard)

    def test_executor_population_transitions_require_supported_contract_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "\n".join(f"// line {line}" for line in range(1, 12)) + "\n",
                encoding="utf-8",
            )
            task_callable = "java-callable-v1:Fixture.lambda$task()V"

            def extracted_for(
                rejection_policy: str,
                exit_specs=((4, "normal"), (5, "exceptional")),
                core_workers="1",
                release_evidence=None,
                release_at_exit=False,
                release_coverage="complete",
                cfg_evidence="codeql_task_cfg_successor",
                synthetic_suffix=None,
                terminal_evidence="codeql_task_annotated_cfg_exit",
                parallel_cfg=False,
                dispatch_owner=SYNTHETIC_HANDLE_ID,
                dispatch_depth=0,
                dispatch_binding=-1,
                base_bindings=(),
                callback_gap=False,
                callback_gap_owner=None,
            ):
                create = decoded_query_row(
                    source_root, "resource_lifecycle", "a" * 64
                )
                common = {
                    "site_callable": dispatch_owner,
                    "relation_depth": dispatch_depth,
                    "binding_index": dispatch_binding,
                    "program_point": "point:Fixture.java:2:1:dispatch",
                    "related_point": "point:Fixture.java:3:1:task-entry",
                    "related_start_line": 3,
                    "holder_kind": "queue",
                    "holder_scope": "task",
                    "holder_key": "Fixture.EXECUTOR#static",
                    "target_event": task_callable,
                    "capacity": "3",
                    "core_workers": core_workers,
                    "max_workers": "2",
                    "rejection_policy": rejection_policy,
                }
                dispatch = decoded_query_row(
                    source_root,
                    "resource_lifecycle_task_relations",
                    "b" * 64,
                    fact_kind="dispatch",
                    **common,
                )
                invariant = decoded_query_row(
                    source_root,
                    "resource_lifecycle_task_relations",
                    "b" * 64,
                    fact_kind="invariant",
                    **common,
                )
                exits = tuple(
                    decoded_query_row(
                        source_root,
                        "resource_lifecycle_task_relations",
                        "b" * 64,
                        fact_kind="task_exit",
                        site_callable=task_callable,
                        program_point=f"point:Fixture.java:{line}:1:{kind}",
                        site_start_line=line,
                        related_point="point:Fixture.java:3:1:task-entry",
                        related_start_line=3,
                        target_event=task_callable,
                        normal_path=kind == "normal",
                        exceptional_path=kind == "exceptional",
                    )
                    for line, kind in exit_specs
                )
                cfg_edges = tuple(
                    decoded_query_row(
                        source_root,
                        "resource_lifecycle_task_relations",
                        "b" * 64,
                        fact_kind="cfg_edge",
                        site_callable=task_callable,
                        program_point="point:Fixture.java:3:1:task-entry",
                        site_start_line=3,
                        related_point=exit["program_point"],
                        related_start_line=exit["site_start_line"],
                        target_event=task_callable,
                        normal_path=True,
                        exceptional_path=False,
                        source_evidence=cfg_evidence,
                        coverage_note="reachable_task_cfg_edge",
                    )
                    for exit in exits
                )
                releases = () if release_evidence is None else (
                    decoded_query_row(
                        source_root, "resource_lifecycle_task_relations", "b" * 64,
                        fact_kind="release", site_callable=task_callable,
                        program_point=exits[0]["program_point"] if release_at_exit else "point:Fixture.java:3:1:task-entry",
                        related_point=exits[0]["program_point"],
                        site_start_line=exits[0]["site_start_line"] if release_at_exit else 3,
                        related_start_line=exits[0]["site_start_line"],
                        target_event=task_callable,
                        source_evidence=release_evidence,
                        coverage_note="exact_captured_task_finally_close",
                        coverage_status=release_coverage,
                        normal_path=True, exceptional_path=False,
                    ),
                )
                if parallel_cfg:
                    cfg_edges += ({**cfg_edges[0], "normal_path": False, "exceptional_path": True},)
                if synthetic_suffix is not None:
                    close_point = "point:Fixture.java:3:1:task-entry"
                    success_point = close_point + synthetic_suffix
                    cfg_edges = (decoded_query_row(
                        source_root, "resource_lifecycle_task_relations", "b" * 64,
                        fact_kind="cfg_edge", site_callable=task_callable,
                        program_point=close_point, related_point=success_point,
                        site_start_line=3, related_start_line=3, target_event=task_callable,
                        normal_path=True, exceptional_path=False,
                        source_evidence=cfg_evidence,
                        coverage_note="exact_close_normal_success_continuation",
                    ),)
                    exits = tuple(decoded_query_row(
                        source_root, "resource_lifecycle_task_relations", "b" * 64,
                        fact_kind="task_exit", site_callable=task_callable,
                        program_point=point, related_point=close_point,
                        site_start_line=3, related_start_line=3, target_event=task_callable,
                        normal_path=kind == "normal", exceptional_path=kind == "exceptional",
                        source_evidence=terminal_evidence,
                        coverage_note=kind + "_task_annotated_cfg_exit",
                    ) for point, kind in ((success_point, "normal"), (success_point, "exceptional"),
                                           (close_point, "exceptional")))
                    releases = (decoded_query_row(
                        source_root, "resource_lifecycle_task_relations", "b" * 64,
                        fact_kind="release", site_callable=task_callable,
                        program_point=close_point, related_point=success_point,
                        site_start_line=3, related_start_line=3, target_event=task_callable,
                        source_evidence=release_evidence,
                        coverage_note="exact_captured_task_finally_close",
                        coverage_status=release_coverage, normal_path=True, exceptional_path=False,
                    ),)
                # Real task-query body rows carry the capture's declared depth;
                # a depth-two submit cannot borrow the old helper's depth-zero body.
                cfg_edges = tuple({**row, "relation_depth": dispatch_depth} for row in cfg_edges)
                exits = tuple({**row, "relation_depth": dispatch_depth} for row in exits)
                releases = tuple({**row, "relation_depth": dispatch_depth} for row in releases)
                additional_facts = tuple(decoded_query_row(
                    source_root, "resource_lifecycle", "a" * 64, **fields,
                ) for fields in base_bindings)
                if callback_gap:
                    additional_facts += (decoded_query_row(
                        source_root, "resource_lifecycle_task_relations", "b" * 64,
                        fact_kind="unknown_call", program_point=common["program_point"],
                        related_point=(callback_gap_owner or task_callable) + "#site:Fixture.java:7:1:7:1",
                        related_start_line=7, target_event=task_callable,
                        source_evidence="codeql_task_callback_effect_coverage_gap",
                        coverage_note="task_callback_effect_unmodeled", coverage_status="partial",
                    ),)
                return adapt_codeql_rows(
                    (create, dispatch, invariant, *cfg_edges, *exits, *releases, *additional_facts),
                    source_root=source_root,
                    query_provenance=(
                        {
                            "query_name": "resource_lifecycle",
                            "query_sha256": "a" * 64,
                            "bqrs_sha256": "c" * 64,
                        },
                        {
                            "query_name": "resource_lifecycle_task_relations",
                            "query_sha256": "b" * 64,
                            "bqrs_sha256": "d" * 64,
                        },
                    ),
                    database_fingerprint="e" * 64,
                    source_snapshot_sha256="f" * 64,
                )

            caller_runs = extracted_for("caller_runs")
            abort = extracted_for("abort")
            for specs in (((4, "normal"),), ((5, "exceptional"),),
                          ((4, "normal"), (5, "exceptional"), (6, "normal")), ()):
                with self.subTest(exits=specs):
                    program = extracted_for("abort", specs).units[0].program
                    self.assertEqual(1, len(program.task_bindings))
                    self.assertEqual(len(specs), len(program.task_exits))
            zero_core = extracted_for("abort", core_workers="0")
            self.assertEqual(0, zero_core.units[0].executor_contracts[0].core_workers)
            unknown_core = extracted_for("abort", core_workers="configuredCoreWorkers").units[0].program
            self.assertFalse(any(edge.population_effects for edge in unknown_core.transitions))
            self.assertIn("executor_worker_limits_unknown", {gap[3] for gap in unknown_core.coverage_gaps})
            forged = extracted_for("abort", release_evidence="invented_release")
            trusted = extracted_for("abort", release_evidence="codeql_task_callback_close_finally")
            self.assertFalse(any(effect.kind == "release"
                for edge in forged.units[0].program.transitions for effect in edge.effects))
            self.assertTrue(any(effect.kind == "release"
                for edge in trusted.units[0].program.transitions for effect in edge.effects))
            escaped = extracted_for("abort", release_evidence="codeql_task_callback_close_finally",
                                    callback_gap=True)
            escaped_program = escaped.units[0].program
            escape_fact = next(fact for fact in escaped.facts
                               if fact.source_evidence == "codeql_task_callback_effect_coverage_gap")
            self.assertTrue(any(effect.kind == "release" for edge in escaped_program.transitions
                                for effect in edge.effects))
            self.assertEqual({"held_instances", "item_size_bytes", "close_obligation"},
                             {gap[0] for gap in escaped_program.coverage_gaps if gap[4] == escape_fact.fact_id})
            self.assertEqual(task_callable, next(point.callable for point in escaped_program.program_points
                                                 if point.point_id == escape_fact.related_point))
            fallback = extracted_for("abort", callback_gap=True, callback_gap_owner=SYNTHETIC_HANDLE_ID)
            fallback_gap = next(fact for fact in fallback.facts
                                if fact.source_evidence == "codeql_task_callback_effect_coverage_gap")
            self.assertEqual(SYNTHETIC_HANDLE_ID, next(point.callable
                             for point in fallback.units[0].program.program_points
                             if point.point_id == fallback_gap.related_point))
            first = "java-callable-v1:Fixture.wrapper1(Lfixture/Resource;)V"
            second = "java-callable-v1:Fixture.wrapper2(Lfixture/Resource;)V"
            first_binding = dict(fact_kind="call_binding", program_point="point:call1",
                                 related_point="point:param1", target_event=first,
                                 relation_depth=1, binding_index=0)
            second_binding = dict(fact_kind="call_binding", site_callable=first,
                                  program_point="point:call2", related_point="point:param2",
                                  target_event=second, relation_depth=2, binding_index=0)
            for bindings, position, expected in (
                ((), 0, False),
                ((second_binding,), 0, False),
                ((first_binding, {**second_binding, "coverage_status": "partial"}), 0, False),
                ((first_binding, second_binding), 1, False),
                ((first_binding, second_binding), 0, True),
                ((first_binding, {**second_binding, "binding_index": 1}), 0, True),
            ):
                with self.subTest(base_binding_chain=len(bindings), parameter=position, expected=expected):
                    adapted = extracted_for(
                        "abort", release_evidence="codeql_task_callback_close_finally",
                        dispatch_owner=second, dispatch_depth=2, dispatch_binding=position,
                        base_bindings=bindings,
                    )
                    program = adapted.units[0].program
                    self.assertEqual(expected, bool(program.task_bindings))
                    self.assertEqual(expected, any(edge.population_effects for edge in program.transitions))
                    self.assertEqual(expected, any(effect.kind == "release" for edge in program.transitions
                                                   for effect in edge.effects))
                    if not expected:
                        dispatch_fact = next(fact for fact in adapted.facts if fact.fact_kind == "dispatch")
                        self.assertEqual({"held_instances", "item_size_bytes", "close_obligation"},
                                         {gap[0] for gap in program.coverage_gaps
                                          if gap[3] == "task_capture_call_binding_unverified"
                                          and gap[4] == dispatch_fact.fact_id})
            forged_cfg = extracted_for("abort", release_evidence="codeql_task_callback_close_finally",
                                       cfg_evidence="invented_cfg")
            self.assertFalse(any(effect.kind == "release"
                for edge in forged_cfg.units[0].program.transitions for effect in edge.effects))
            parallel = extracted_for("abort", release_evidence="codeql_task_callback_close_finally",
                                     parallel_cfg=True).units[0].program
            parallel_edges = [edge for edge in parallel.transitions if edge.guard == "task_cfg_edge"]
            self.assertEqual(3, len(parallel_edges))
            self.assertEqual(3, len({edge.transition_id for edge in parallel_edges}))
            self.assertEqual(1, sum(effect.kind == "release" for edge in parallel_edges for effect in edge.effects))
            for kind, evidence, coverage, expected in (
                ("normal", "codeql_task_callback_close_finally", "complete", 0),
                ("exceptional", "codeql_task_callback_close_finally", "complete", 0),
                ("normal", "invented_release", "complete", 0),
                ("normal", "codeql_task_callback_close_finally", "partial", 0),
            ):
                with self.subTest(terminal_kind=kind, release_evidence=evidence, coverage=coverage):
                    terminal_program = extracted_for(
                        "abort", ((4, kind),), release_evidence=evidence,
                        release_at_exit=True, release_coverage=coverage,
                    ).units[0].program
                    releases = [effect for edge in terminal_program.transitions
                                for effect in edge.effects if effect.kind == "release"]
                    self.assertEqual(expected, len(releases))
            for suffix, cfg_evidence, terminal_evidence, expected in (
                ("#normal-success:call-cfg-v1", "codeql_task_close_normal_successor", "codeql_task_annotated_cfg_exit", 1),
                ("#normal-success:invented", "codeql_task_close_normal_successor", "codeql_task_annotated_cfg_exit", 0),
                ("#normal-success:call-cfg-v1", "invented_cfg", "codeql_task_annotated_cfg_exit", 0),
                ("#normal-success:call-cfg-v1", "codeql_task_close_normal_successor", "invented_terminal", 0),
            ):
                with self.subTest(suffix=suffix, cfg_evidence=cfg_evidence, terminal_evidence=terminal_evidence):
                    program = extracted_for(
                        "abort", release_evidence="codeql_task_callback_close_finally",
                        cfg_evidence=cfg_evidence, synthetic_suffix=suffix,
                        terminal_evidence=terminal_evidence,
                    ).units[0].program
                    self.assertEqual(3, len(program.task_exits))
                    release_edges = [edge for edge in program.transitions
                                     if any(effect.kind == "release" for effect in edge.effects)]
                    self.assertEqual(expected, len(release_edges))
                    self.assertTrue(all(edge.guard == "task_cfg_edge" for edge in release_edges))
                    self.assertFalse(any(edge.effects for edge in program.transitions
                                         if edge.guard in {"normal_task_exit", "exceptional_task_exit"}))

        def population_kinds(extracted) -> set[str]:
            return {
                effect.kind
                for transition in extracted.units[0].program.transitions
                for effect in transition.population_effects
            }

        caller_runs_kinds = population_kinds(caller_runs)
        self.assertTrue(
            {"direct_accept", "enqueue", "assign_slot", "start"}
            <= caller_runs_kinds
        )
        self.assertFalse(
            {"reject", "cancel_queued", "cancel_active"}
            & caller_runs_kinds
        )
        self.assertIn("terminate", caller_runs_kinds)
        caller_runs_contract = caller_runs.units[0].executor_contracts[0]
        self.assertEqual((1, 2, 3), (
            caller_runs_contract.core_workers,
            caller_runs_contract.max_workers,
            caller_runs_contract.queue_capacity,
        ))
        guards = {
            effect.kind: effect.guard
            for transition in caller_runs.units[0].program.transitions
            for effect in transition.population_effects
        }
        self.assertEqual({
            "direct_accept": "a<C or (q>=K and a<W)",
            "enqueue": "q<K",
            "assign_slot": "q>0 and a<W",
        }, {key: guards[key] for key in ("direct_accept", "enqueue", "assign_slot")})

        abort_kinds = population_kinds(abort)
        self.assertTrue({"reject", "terminate"} <= abort_kinds)
        self.assertFalse(
            {"cancel_queued", "cancel_active"} & abort_kinds
        )

    def test_static_field_holder_identity_is_shared_across_callables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "\n".join(f"// line {line}" for line in range(1, 9)) + "\n",
                encoding="utf-8",
            )
            units = (
                ("java-callable-v1:Fixture.first()V", 1, 2),
                ("java-callable-v1:Fixture.second()V", 3, 4),
            )
            rows = []
            for unit_id, create_line, retain_line in units:
                instance_key = f"Fixture.java:{create_line}:1"
                rows.extend(
                    (
                        lifecycle_row(
                            unit_id=unit_id,
                            site_callable=unit_id,
                            site_start_line=create_line,
                            related_start_line=create_line,
                            program_point=f"point:{create_line}:create",
                            instance_key=instance_key,
                        ),
                        lifecycle_row(
                            unit_id=unit_id,
                            site_callable=unit_id,
                            site_start_line=retain_line,
                            related_start_line=retain_line,
                            program_point=f"point:{retain_line}:retain",
                            fact_kind="retain",
                            instance_key=instance_key,
                            holder_kind="field",
                            holder_scope="global",
                            holder_key="Fixture.SHARED#static",
                        ),
                    )
                )

            extracted = adapt_codeql_rows(
                rows, source_root=source_root, query_sha256="a" * 64
            )

        field_holders = [
            next(holder for holder in unit.program.holders if holder.kind == "field")
            for unit in extracted.units
        ]
        self.assertEqual(1, len({holder.holder_id for holder in field_holders}))
        self.assertTrue(
            all(holder.identity_precision == "exact" for holder in field_holders)
        )

    def test_unknown_instance_field_receivers_do_not_merge_and_emit_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                "\n".join(f"// line {line}" for line in range(1, 9)) + "\n",
                encoding="utf-8",
            )
            rows = (
                lifecycle_row(
                    site_start_line=1,
                    related_start_line=1,
                    program_point="point:1:create",
                    instance_key="Fixture.java:1:1",
                ),
                lifecycle_row(
                    site_start_line=2,
                    related_start_line=2,
                    program_point="point:2:create",
                    instance_key="Fixture.java:2:1",
                ),
                lifecycle_row(
                    site_start_line=3,
                    related_start_line=3,
                    program_point="point:3:retain",
                    fact_kind="retain",
                    instance_key="Fixture.java:1:1",
                    holder_kind="field",
                    holder_scope="instance",
                    holder_key="Fixture.resource",
                ),
                lifecycle_row(
                    site_start_line=4,
                    related_start_line=4,
                    program_point="point:4:retain",
                    fact_kind="retain",
                    instance_key="Fixture.java:2:1",
                    holder_kind="field",
                    holder_scope="instance",
                    holder_key="Fixture.resource",
                ),
            )

            extracted = adapt_codeql_rows(
                rows, source_root=source_root, query_sha256="a" * 64
            )

        unit = extracted.units[0]
        field_holders = [holder for holder in unit.program.holders if holder.kind == "field"]
        self.assertEqual(2, len(field_holders))
        self.assertEqual(
            {"unknown"}, {holder.identity_precision for holder in field_holders}
        )
        self.assertEqual(
            2,
            sum(
                dimension == "held_instances"
                and reason == "field_receiver_identity_unresolved"
                for dimension, _family, _scope, reason, _evidence
                in unit.program.coverage_gaps
            ),
        )

    def test_task_query_family_match_is_exact_and_precedes_base_match(self) -> None:
        self.assertEqual(
            "resource_lifecycle_task_relations",
            codeql_runner._query_family("ResourceLifecycleTaskRelations"),
        )
        self.assertEqual(
            "resource_lifecycle",
            codeql_runner._query_family("ResourceLifecycleFacts"),
        )
        with self.assertRaises(AnalyzerError):
            codeql_runner._query_family("ResourceLifecycleTaskRelationsBackup")

    def test_query_suite_sha_is_repeatable_and_order_sensitive(self) -> None:
        self.assertTrue(hasattr(lifecycle_commands, "_query_suite_sha256"))
        helper = getattr(lifecycle_commands, "_query_suite_sha256")
        ordered = (
            ("resource_lifecycle", "a" * 64),
            ("resource_lifecycle_task_relations", "b" * 64),
        )

        first = helper(ordered)
        second = helper(tuple(ordered))
        reversed_digest = helper(tuple(reversed(ordered)))

        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, second)
        self.assertNotEqual(first, reversed_digest)

    def test_implementation_digest_covers_both_packed_queries(self) -> None:
        self.assertIsInstance(lifecycle_commands._QUERY, tuple)
        self.assertEqual(
            (EMBEDDED_QUERY, EMBEDDED_TASK_QUERY),
            lifecycle_commands._QUERY,
        )
        seen: list[Path] = []
        original = lifecycle_commands.load_regular_bytes_with_sha256

        def tracking(path: Path):
            seen.append(path)
            return original(path)

        with patch.object(
            lifecycle_commands,
            "load_regular_bytes_with_sha256",
            side_effect=tracking,
        ):
            lifecycle_commands._implementation_sha256()

        self.assertIn(EMBEDDED_QUERY, seen)
        self.assertIn(EMBEDDED_TASK_QUERY, seen)

    def test_formal_query_suite_failure_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "source"
            source_root.mkdir()
            (source_root / "Fixture.java").write_text(
                SYNTHETIC_SOURCE, encoding="utf-8"
            )
            database_path = root / "database"
            database_path.mkdir()
            database = DatabaseInfo(database_path, source_root, "d" * 64)
            decoded = root / "base.json"
            decoded.write_text(
                json.dumps(
                    {
                        "#select": {
                            "columns": list(QUERY_SPECS["resource_lifecycle"].columns),
                            "tuples": [[
                                lifecycle_row()[column]
                                for column in QUERY_SPECS["resource_lifecycle"].columns
                            ]],
                        }
                    }
                ),
                encoding="utf-8",
            )
            bqrs = root / "base.bqrs"
            bqrs.write_bytes(b"base")
            first = QueryResult(
                "resource_lifecycle",
                DIRECT_QUERY,
                bqrs,
                decoded,
                "a" * 64,
                "c" * 64,
            )
            manifest = {
                "schema_version": "1.1",
                "mode": "codeql_database",
                "database": str(database_path),
                "entry_methods": [],
                "budget": {
                    "max_steps": 1024,
                    "max_updates_per_event": 32,
                    "timeout_ms": 5000,
                },
            }
            failure = AnalyzerError(
                "CODEQL_QUERY_FAILED",
                "second selected lifecycle query failed",
            )
            output = root / "output"

            with patch.object(
                lifecycle_commands, "validate_database", return_value=database
            ), patch.object(
                lifecycle_commands,
                "_verify_database_source_snapshot",
                return_value="e" * 64,
            ), patch.object(
                lifecycle_commands,
                "run_query",
                side_effect=(first, failure),
            ) as runner, patch.object(
                lifecycle_commands, "adapt_codeql_rows"
            ) as adapter:
                with self.assertRaises(AnalyzerError) as raised:
                    lifecycle_commands._codeql_facts(manifest, {}, output)

        self.assertEqual("CODEQL_QUERY_FAILED", raised.exception.code)
        self.assertEqual(2, runner.call_count)
        adapter.assert_not_called()
        self.assertFalse((output / "facts.json").exists())
        self.assertFalse((output / "coverage.json").exists())

    def test_adapter_checks_each_row_origin_against_ordered_suite(self) -> None:
        self.assertIn("resource_lifecycle_task_relations", QUERY_SPECS)
        if "resource_lifecycle_task_relations" not in QUERY_SPECS:
            return
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                SYNTHETIC_SOURCE, encoding="utf-8"
            )
            create = decoded_query_row(
                source_root, "resource_lifecycle", "a" * 64
            )
            task = decoded_query_row(
                source_root,
                "resource_lifecycle_task_relations",
                "b" * 64,
                fact_kind="dispatch",
                holder_kind="queue",
                holder_scope="task",
                holder_key="Fixture.EXECUTOR#static",
                target_event="java-callable-v1:Fixture.lambda$task()V",
                capacity="3",
                max_workers="2",
                rejection_policy="abort",
                exceptional_path=False,
            )
            provenance = (
                {
                    "query_name": "resource_lifecycle",
                    "query_sha256": "a" * 64,
                    "bqrs_sha256": "c" * 64,
                },
                {
                    "query_name": "resource_lifecycle_task_relations",
                    "query_sha256": "b" * 64,
                    "bqrs_sha256": "d" * 64,
                },
            )

            extracted = adapt_codeql_rows(
                (create, task),
                source_root=source_root,
                query_provenance=provenance,
                database_fingerprint="e" * 64,
                source_snapshot_sha256="f" * 64,
            )
            with self.assertRaisesRegex(ValueError, "row query digest"):
                adapt_codeql_rows(
                    (create, {**task, "query_sha256": "9" * 64}),
                    source_root=source_root,
                    query_provenance=provenance,
                    database_fingerprint="e" * 64,
                    source_snapshot_sha256="f" * 64,
                )

        self.assertEqual(
            {"resource_lifecycle", "resource_lifecycle_task_relations"},
            {fact.query_name for fact in extracted.facts},
        )
        self.assertEqual(
            {"a" * 64, "b" * 64},
            {fact.query_sha256 for fact in extracted.facts},
        )

    def test_split_query_merge_rejects_duplicate_or_orphan_rows(self) -> None:
        self.assertIn("resource_lifecycle_task_relations", QUERY_SPECS)
        if "resource_lifecycle_task_relations" not in QUERY_SPECS:
            return
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                SYNTHETIC_SOURCE, encoding="utf-8"
            )
            provenance = (
                {
                    "query_name": "resource_lifecycle",
                    "query_sha256": "a" * 64,
                    "bqrs_sha256": "c" * 64,
                },
                {
                    "query_name": "resource_lifecycle_task_relations",
                    "query_sha256": "b" * 64,
                    "bqrs_sha256": "d" * 64,
                },
            )
            create = decoded_query_row(
                source_root, "resource_lifecycle", "a" * 64
            )
            base_gap = decoded_query_row(
                source_root,
                "resource_lifecycle",
                "a" * 64,
                fact_kind="unknown_call",
                coverage_status="partial",
                coverage_note="dispatch_binding_unresolved",
            )
            duplicate_gap = {
                **base_gap,
                "query_name": "resource_lifecycle_task_relations",
                "query_sha256": "b" * 64,
            }
            orphan = decoded_query_row(
                source_root,
                "resource_lifecycle_task_relations",
                "b" * 64,
                fact_kind="dispatch",
                instance_key="Fixture.java:9:1",
                holder_kind="queue",
                holder_scope="task",
                holder_key="Fixture.EXECUTOR#static",
                target_event="java-callable-v1:Fixture.lambda$task()V",
                capacity="3",
                max_workers="2",
                rejection_policy="abort",
                exceptional_path=False,
            )
            unknown_unit = {
                **orphan,
                "unit_id": "java-callable-v1:Fixture.other()V",
                "site_callable": "java-callable-v1:Fixture.other()V",
            }
            base_only_dispatch = decoded_query_row(
                source_root,
                "resource_lifecycle",
                "a" * 64,
                fact_kind="dispatch",
                program_point="point:Fixture.java:2:1:base-dispatch",
                holder_kind="queue",
                holder_scope="task",
                holder_key="Fixture.QUEUE#static",
                target_event="java-callable-v1:Fixture.lambda$task()V",
                capacity="3",
                exceptional_path=False,
            )
            dangling_cfg = decoded_query_row(
                source_root,
                "resource_lifecycle_task_relations",
                "b" * 64,
                fact_kind="cfg_edge",
                program_point="point:Fixture.java:3:1:task-entry",
                related_point="point:Fixture.java:4:1:task-body",
                target_event="java-callable-v1:Fixture.lambda$task()V",
            )
            common = {
                "source_root": source_root,
                "query_provenance": provenance,
                "database_fingerprint": "e" * 64,
                "source_snapshot_sha256": "f" * 64,
            }

            with self.assertRaisesRegex(ValueError, "duplicate semantic row"):
                adapt_codeql_rows((create, base_gap, duplicate_gap), **common)
            with self.assertRaisesRegex(ValueError, "orphan instance_key"):
                adapt_codeql_rows((create, orphan), **common)
            with self.assertRaisesRegex(ValueError, "unknown base unit"):
                adapt_codeql_rows((create, unknown_unit), **common)
            with self.assertRaisesRegex(ValueError, "dangling task"):
                adapt_codeql_rows(
                    (create, base_only_dispatch, dangling_cfg), **common
                )

    def test_partial_task_relations_become_dimension_coverage_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                SYNTHETIC_SOURCE, encoding="utf-8"
            )
            provenance = (
                {
                    "query_name": "resource_lifecycle",
                    "query_sha256": "a" * 64,
                    "bqrs_sha256": "c" * 64,
                },
                {
                    "query_name": "resource_lifecycle_task_relations",
                    "query_sha256": "b" * 64,
                    "bqrs_sha256": "d" * 64,
                },
            )
            create = decoded_query_row(
                source_root, "resource_lifecycle", "a" * 64
            )
            task_callable = "java-callable-v1:Fixture.lambda$task()V"
            dispatch = decoded_query_row(
                source_root,
                "resource_lifecycle_task_relations",
                "b" * 64,
                fact_kind="dispatch",
                program_point="point:Fixture.java:2:1:dispatch",
                related_point="point:Fixture.java:3:1:task-entry",
                holder_kind="queue",
                holder_scope="task",
                holder_key="Fixture.EXECUTOR#static",
                target_event=task_callable,
                capacity="3",
                max_workers="2",
                rejection_policy="abort",
                exceptional_path=False,
            )
            common = {
                "source_root": source_root,
                "query_provenance": provenance,
                "database_fingerprint": "e" * 64,
                "source_snapshot_sha256": "f" * 64,
            }

            for fact_kind, overrides in (
                (
                    "cfg_edge",
                    {
                        "program_point": "point:Fixture.java:3:1:task-entry",
                        "related_point": "point:Fixture.java:4:1:task-body",
                    },
                ),
                (
                    "task_exit",
                    {
                        "program_point": "point:Fixture.java:5:1:task-exit",
                        "related_point": "none",
                        "exceptional_path": False,
                    },
                ),
            ):
                relation = decoded_query_row(
                    source_root,
                    "resource_lifecycle_task_relations",
                    "b" * 64,
                    fact_kind=fact_kind,
                    target_event=task_callable,
                    coverage_status="partial",
                    coverage_note=f"{fact_kind}_coverage_partial",
                    **overrides,
                )

                with self.subTest(fact_kind=fact_kind):
                    extracted = adapt_codeql_rows(
                        (create, dispatch, relation), **common
                    )
                    unit = extracted.units[0]
                    relation_fact = next(
                        fact
                        for fact in extracted.facts
                        if fact.fact_kind == fact_kind
                    )

                    self.assertFalse(unit.program.coverage_complete)
                    self.assertEqual(
                        {
                            "held_instances",
                            "item_size_bytes",
                            "close_obligation",
                        },
                        {
                            dimension
                            for dimension, _family, _scope, _reason, evidence_id
                            in unit.program.coverage_gaps
                            if evidence_id == relation_fact.fact_id
                        },
                    )

    def test_formal_provenance_detects_suite_and_artifact_tampering(self) -> None:
        self.assertIn("resource_lifecycle_task_relations", QUERY_SPECS)
        if "resource_lifecycle_task_relations" not in QUERY_SPECS:
            return
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(
                SYNTHETIC_SOURCE, encoding="utf-8"
            )
            create = decoded_query_row(
                source_root, "resource_lifecycle", "a" * 64
            )
            task_gap = decoded_query_row(
                source_root,
                "resource_lifecycle_task_relations",
                "b" * 64,
                fact_kind="unknown_call",
                coverage_status="partial",
                coverage_note="task_dispatch_unresolved",
            )
            provenance = (
                {
                    "query_name": "resource_lifecycle",
                    "query_sha256": "a" * 64,
                    "bqrs_sha256": "c" * 64,
                },
                {
                    "query_name": "resource_lifecycle_task_relations",
                    "query_sha256": "b" * 64,
                    "bqrs_sha256": "d" * 64,
                },
            )
            extracted = adapt_codeql_rows(
                (create, task_gap),
                source_root=source_root,
                query_provenance=provenance,
                database_fingerprint="e" * 64,
                source_snapshot_sha256="f" * 64,
            )

        validate_extracted(extracted)
        for label, mutate in (
            (
                "suite order",
                lambda coverage: coverage.update(
                    query_provenance=list(reversed(coverage["query_provenance"]))
                ),
            ),
            (
                "BQRS digest",
                lambda coverage: coverage["query_provenance"][0].update(
                    bqrs_sha256="0" * 64
                ),
            ),
            (
                "database fingerprint",
                lambda coverage: coverage.update(database_fingerprint="0" * 64),
            ),
            (
                "source snapshot",
                lambda coverage: coverage.update(source_snapshot_sha256="0" * 64),
            ),
        ):
            tampered = json.loads(json.dumps(extracted_to_dict(extracted)))
            mutate(tampered["coverage"])
            with self.subTest(label=label), self.assertRaisesRegex(
                ValueError, "provenance"
            ):
                validate_extracted(extracted_from_dict(tampered))

    def test_holder_scope_is_a_strict_decoder_column(self) -> None:
        self.assertIn("holder_scope", QUERY_SPECS["resource_lifecycle"].columns)
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            row = decoded_lifecycle_row(source_root)
            values = [row[column] for column in QUERY_SPECS["resource_lifecycle"].columns]
            values[QUERY_SPECS["resource_lifecycle"].columns.index("holder_scope")] = "unknown"

            self.assertEqual("none", row["holder_scope"])
            with self.assertRaises(AnalyzerError) as raised:
                decode_rows(
                    "resource_lifecycle",
                    QUERY_SPECS["resource_lifecycle"].columns,
                    [values],
                    DecodeSource(source_root, "a" * 64),
                )

        self.assertEqual("ENUM_INVALID", raised.exception.details["reason"])
        self.assertEqual("holder_scope", raised.exception.details["column"])

    def test_requires_close_is_a_strict_boolean_decoder_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            row = decoded_lifecycle_row(source_root)
            values = [row[column] for column in QUERY_SPECS["resource_lifecycle"].columns]
            values[QUERY_SPECS["resource_lifecycle"].columns.index("requires_close")] = "true"

            self.assertIs(row["requires_close"], True)
            with self.assertRaises(AnalyzerError) as raised:
                decode_rows(
                    "resource_lifecycle",
                    QUERY_SPECS["resource_lifecycle"].columns,
                    [values],
                    DecodeSource(source_root, "a" * 64),
                )

        self.assertEqual("FIELD_TYPE", raised.exception.details["reason"])
        self.assertEqual("requires_close", raised.exception.details["column"])

    def test_requires_close_participates_in_fact_identity_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            closeable = decoded_lifecycle_row(source_root)
            ordinary = {**closeable, "requires_close": False}
            closeable_facts = adapt_codeql_rows(
                (closeable,), source_root=source_root, query_sha256="a" * 64
            )
            ordinary_facts = adapt_codeql_rows(
                (ordinary,), source_root=source_root, query_sha256="a" * 64
            )
            tampered = replace(
                closeable_facts,
                facts=(replace(closeable_facts.facts[0], requires_close=False),),
            )

            self.assertNotEqual(closeable_facts.facts[0].fact_id, ordinary_facts.facts[0].fact_id)
            with self.assertRaisesRegex(ValueError, "identifier"):
                validate_extracted(tampered)

    def test_holder_scope_participates_in_fact_identity_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            created = decoded_lifecycle_row(source_root)
            retained = {
                **created,
                "fact_kind": "retain",
                "holder_kind": "field",
                "holder_scope": "instance",
                "holder_key": "Fixture.saved",
                "source_evidence": "test_field_assignment",
            }
            global_retained = {**retained, "holder_scope": "global"}
            instance_facts = adapt_codeql_rows(
                (created, retained), source_root=source_root, query_sha256="a" * 64
            )
            global_facts = adapt_codeql_rows(
                (created, global_retained), source_root=source_root, query_sha256="a" * 64
            )
            instance_retain = next(
                fact for fact in instance_facts.facts if fact.fact_kind == "retain"
            )
            global_retain = next(
                fact for fact in global_facts.facts if fact.fact_kind == "retain"
            )
            tampered = replace(
                instance_facts,
                facts=tuple(
                    replace(fact, holder_scope="global") if fact.fact_kind == "retain" else fact
                    for fact in instance_facts.facts
                ),
            )

        self.assertNotEqual(instance_retain.fact_id, global_retain.fact_id)
        with self.assertRaisesRegex(ValueError, "identifier"):
            validate_extracted(tampered)

    def test_adapter_uses_raw_requires_close_and_accepts_only_exact_provenance_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            decoded = {**decoded_lifecycle_row(source_root), "requires_close": False}
            bare = {
                key: value
                for key, value in decoded.items()
                if key
                not in {
                    "query_name",
                    "query_sha256",
                    "site_location",
                    "related_location",
                }
            }

            from_decoded = adapt_codeql_rows(
                (decoded,), source_root=source_root, query_sha256="a" * 64
            )
            from_bare = adapt_codeql_rows(
                (bare,), source_root=source_root, query_sha256="a" * 64
            )

        for extracted in (from_decoded, from_bare):
            family = extracted.units[0].program.families[0]
            dimensions = check_invariants(
                extracted.units[0].program,
                solve(extracted.units[0].program, budget=AnalysisBudget()),
                extracted.units[0].invariants,
                timeout_ms=100,
                executor_contracts=extracted.units[0].executor_contracts,
            )
            self.assertIs(family.requires_close, False)
            self.assertEqual(
                "not_applicable",
                next(
                    item
                    for item in dimensions
                    if item.dimension == "close_obligation"
                ).lifecycle_status,
            )

    def test_adapter_rejects_inconsistent_requires_close_for_one_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            created = decoded_lifecycle_row(source_root)
            retained = {
                **created,
                "site_start_line": 2,
                "fact_kind": "retain",
                "requires_close": False,
                "holder_kind": "field",
                "holder_scope": "instance",
                "holder_key": "Fixture.saved",
                "site_location": {"file": "Fixture.java", "start_line": 2, "start_column": 1},
            }

            with self.assertRaisesRegex(ValueError, "requires_close"):
                adapt_codeql_rows(
                    (created, retained),
                    source_root=source_root,
                    query_sha256="a" * 64,
                )

    def test_adapter_rejects_fact_without_matching_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            orphan = lifecycle_row(
                site_start_line=2,
                fact_kind="retain",
                instance_key="Fixture.java:2:1",
                holder_kind="field",
                holder_scope="instance",
                holder_key="Fixture.saved",
            )

            with self.assertRaisesRegex(ValueError, "exactly one create"):
                adapt_codeql_rows(
                    (lifecycle_row(), orphan),
                    source_root=source_root,
                    query_sha256="a" * 64,
                )

    def test_adapter_rejects_multiple_allocations_for_one_instance_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            duplicate = lifecycle_row(site_start_line=2)

            with self.assertRaisesRegex(ValueError, "exactly one create"):
                adapt_codeql_rows(
                    (lifecycle_row(), duplicate),
                    source_root=source_root,
                    query_sha256="a" * 64,
                )

    def test_adapter_rejects_inconsistent_resource_type_for_one_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            retained = lifecycle_row(
                site_start_line=2,
                fact_kind="retain",
                resource_type="fixture.OtherResource",
                holder_kind="field",
                holder_scope="instance",
                holder_key="Fixture.saved",
            )

            with self.assertRaisesRegex(ValueError, "resource_type"):
                adapt_codeql_rows(
                    (lifecycle_row(), retained),
                    source_root=source_root,
                    query_sha256="a" * 64,
                )

    def test_database_source_limit_is_enforced_during_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            first = source / "First.java"
            second = source / "Second.java"
            first.write_text("final class First {}\n", encoding="utf-8")
            second.write_text("final class Second {}\n", encoding="utf-8")
            database = root / "database"
            database.mkdir()
            info = DatabaseInfo(database, source, "f" * 64)

            def paths():
                yield first
                yield second
                raise AssertionError("source enumeration was consumed past the configured limit")

            with patch.object(Path, "rglob", return_value=paths()), patch.object(
                lifecycle_commands,
                "_MAX_SOURCE_FILES",
                1,
            ):
                with self.assertRaisesRegex(ValueError, "file limit"):
                    lifecycle_commands._verify_database_source_snapshot(info)

    def test_adapter_fact_snapshot_is_independent_of_bqrs_row_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            created = decoded_lifecycle_row(source_root)
            retained = {
                **created,
                "site_start_line": 2,
                "fact_kind": "retain",
                "holder_kind": "field",
                "holder_scope": "instance",
                "holder_key": "Fixture.saved",
                "source_evidence": "test_field_assignment",
                "site_location": {
                    "file": "Fixture.java",
                    "start_line": 2,
                    "start_column": 1,
                },
            }

            forward = adapt_codeql_rows((created, retained), source_root=source_root, query_sha256="a" * 64)
            reversed_rows = adapt_codeql_rows((retained, created), source_root=source_root, query_sha256="a" * 64)

        self.assertEqual(forward.snapshot_sha256, reversed_rows.snapshot_sha256)
        self.assertEqual(forward.facts, reversed_rows.facts)

    def test_adapter_marks_only_explicitly_selected_methods_as_external_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            row = decoded_lifecycle_row(source_root)

            selected = adapt_codeql_rows(
                (row,),
                source_root=source_root,
                query_sha256="a" * 64,
                entry_methods=(SYNTHETIC_HANDLE_ID,),
            )
            local = adapt_codeql_rows((row,), source_root=source_root, query_sha256="a" * 64)

        self.assertEqual("request", selected.units[0].program.events[0].kind)
        self.assertEqual("request_stack", selected.units[0].program.holders[0].kind)
        self.assertEqual("method", local.units[0].program.events[0].kind)
        self.assertEqual("local", local.units[0].program.holders[0].kind)

    def test_adapter_accepts_exact_decoder_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            row = decoded_lifecycle_row(source_root)

            extracted = adapt_codeql_rows((row,), source_root=source_root, query_sha256="a" * 64)

        self.assertEqual(1, len(extracted.facts))
        self.assertEqual(SYNTHETIC_HANDLE_ID, extracted.facts[0].unit_id)

    def test_adapter_rejects_mismatched_decoder_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            baseline = decoded_lifecycle_row(source_root)
            invalid_rows = (
                ({**baseline, "query_name": "entries"}, "query name"),
                ({**baseline, "query_sha256": "b" * 64}, "query SHA-256"),
                (
                    {
                        **baseline,
                        "site_location": {
                            "file": "Other.java",
                            "start_line": 1,
                            "start_column": 1,
                        },
                    },
                    "site location",
                ),
            )

            for row, expected_message in invalid_rows:
                with self.subTest(expected_message=expected_message):
                    with self.assertRaisesRegex(ValueError, expected_message):
                        adapt_codeql_rows((row,), source_root=source_root, query_sha256="a" * 64)

    def test_adapter_rejects_arbitrary_decoder_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            row = {**decoded_lifecycle_row(source_root), "unexpected": "value"}

            with self.assertRaisesRegex(ValueError, "fields"):
                adapt_codeql_rows((row,), source_root=source_root, query_sha256="a" * 64)

    def test_database_source_archive_must_match_live_source_tree(self) -> None:
        self.assertTrue(hasattr(lifecycle_commands, "_verify_database_source_snapshot"))
        verify_snapshot = getattr(lifecycle_commands, "_verify_database_source_snapshot")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            java = source / "Fixture.java"
            java.write_text("final class Fixture {}\n", encoding="utf-8")
            database = root / "database"
            database.mkdir()
            with zipfile.ZipFile(database / "src.zip", "w") as archive:
                archive.write(java, java.resolve().as_posix().lstrip("/"))
            info = DatabaseInfo(database, source, "f" * 64)

            snapshot = verify_snapshot(info)
            java.write_text("final class Fixture { int changed; }\n", encoding="utf-8")

            self.assertRegex(snapshot, r"^[0-9a-f]{64}$")
            with self.assertRaisesRegex(ValueError, "source snapshot"):
                verify_snapshot(info)

    def test_direct_and_embedded_queries_match_and_emit_only_raw_facts(self) -> None:
        self.assertEqual(DIRECT_QUERY.read_bytes(), EMBEDDED_QUERY.read_bytes())
        self.assertEqual(
            DIRECT_TASK_QUERY.read_bytes(), EMBEDDED_TASK_QUERY.read_bytes()
        )
        content = DIRECT_QUERY.read_text(encoding="utf-8")
        task_content = DIRECT_TASK_QUERY.read_text(encoding="utf-8")
        self.assertIn("@kind table", content)
        self.assertIn("import java", content)
        aliases = (
            "unit_id",
            "site_callable",
            "site_file",
            "site_start_line",
            "site_start_column",
            "program_point",
            "related_point",
            "relation_depth",
            "binding_index",
            "fact_kind",
            "instance_key",
            "resource_type",
            "requires_close",
            "holder_kind",
            "holder_scope",
            "holder_key",
            "target_event",
            "capacity",
            "max_workers",
            "rejection_policy",
            "normal_path",
            "exceptional_path",
            "source_evidence",
            "coverage_status",
            "coverage_note",
        )
        positions = [content.index(f"as {alias}") for alias in aliases]
        self.assertEqual(positions, sorted(positions))
        for forbidden in ("obligation_gap", "actual_reduction", "effective_bound", "static_vulnerable"):
            self.assertNotIn(forbidden, content.lower())
        self.assertIn("predicate exactLocalReleaseBinding", content)
        self.assertIn("predicate autoCloseableReleaseMethod", content)
        self.assertIn("predicate singleExecutionAllocationContext", content)
        self.assertIn("allocation.getParent*() = loop", content)
        self.assertIn("allocation_in_loop_release_not_must", content)
        self.assertIn("release.getNumArgument() = 0", content)
        self.assertIn("method.getAnOverride() = contract", content)
        self.assertIn('"java.lang", "AutoCloseable"', content)
        self.assertIn("cleanup.getNumStmt() = 1", content)
        self.assertIn("cleanup.getStmt(0) = release.getEnclosingStmt()", content)
        self.assertIn("string canonicalCallableIdentity", content)
        self.assertIn("callable.getMethodDescriptor()", content)
        self.assertIn("holderScope as holder_scope", content)
        self.assertNotIn("attempt.getFinally().getAChild*()", content)
        self.assertIn(
            "attempt.getBlock().(BlockStmt).getAStmt() = allocation.getEnclosingStmt()",
            content,
        )
        self.assertNotIn(
            "allocation.getLocation().getStartLine() < attempt.getLocation().getStartLine()",
            content,
        )
        self.assertIn("field.isFinal()", content)
        self.assertIn("predicate supportedQueueFieldType", content)
        self.assertIn("call.getNumArgument() = 1", content)
        self.assertIn("field.getType().getErasure().(RefType).hasQualifiedName", content)
        self.assertNotIn("call.getMethod().getDeclaringType().getErasure()", content)
        self.assertNotIn(
            "creation.getConstructedType().getErasure().(RefType).getASupertype*()",
            content,
        )
        self.assertIn("conditional_release_not_must", content)
        self.assertIn("allocationFlowsTo(allocation, unknown.getQualifier())", content)
        self.assertIn("unknown.getMethod().fromSource()", content)
        self.assertIn("external_callee_resource_effects_unmodeled", content)
        self.assertIn(
            'targetEvent = canonicalCallableIdentity(unknown.getMethod())',
            content,
        )
        self.assertNotIn(
            'factKind = "unknown_call" and holderKind = "none" and\n'
            '      holderScope = "none" and holderKey = "none" and targetEvent = "none" and capacityValue = "unknown" and\n'
            '      normalPath = true and exceptionalPath = true and evidence = "codeql_unmodeled_argument_escape"',
            content,
        )
        self.assertIn("exists(ReturnStmt returned", content)
        self.assertIn(
            'evidence = "codeql_resource_return_escape"',
            content,
        )
        self.assertIn("predicate lifecycleTaskRelationFact", task_content)
        self.assertNotIn("predicate lifecycleFact", task_content)
        self.assertNotIn('factKind = "create"', task_content)
        self.assertNotIn('factKind = "retain"', task_content)
        self.assertIn('factKind = "release"', task_content)
        self.assertIn("predicate exactCapturedFinallyClose", task_content)
        self.assertIn("codeql_task_callback_close_finally", task_content)

    def test_program_point_identity_is_site_based_and_uses_the_full_span(self) -> None:
        content = DIRECT_QUERY.read_text(encoding="utf-8")

        self.assertIn("bindingset[site]", content)
        self.assertIn("string programPointIdentity(ExprParent site)", content)
        self.assertNotIn(
            "string programPointIdentity(Expr site, string factKind)", content
        )
        self.assertNotIn(
            'canonicalCallableIdentity(callable) + "#" + factKind', content
        )
        self.assertIn("site.getLocation().getEndLine().toString()", content)
        self.assertIn("site.getLocation().getEndColumn().toString()", content)
        self.assertIn("programPoint as program_point", content)

    def test_bounded_queue_adapter_emits_task_dispatch_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text("final class Fixture {}\n", encoding="utf-8")
            common = {
                "unit_id": SYNTHETIC_HANDLE_ID,
                "site_file": "Fixture.java",
                "site_start_column": 1,
                "instance_key": "Fixture.java:1:1",
                "resource_type": "fixture.Resource",
                "requires_close": True,
                "holder_kind": "none",
                "holder_scope": "none",
                "holder_key": "none",
                "target_event": "none",
                "capacity": "unknown",
                "normal_path": True,
                "exceptional_path": True,
                "source_evidence": "test",
                "coverage_status": "complete",
                "coverage_note": "test",
            }
            rows = [
                {**common, "site_start_line": 1, "fact_kind": "create"},
                {
                    **common,
                    "site_start_line": 1,
                    "fact_kind": "dispatch",
                    "holder_kind": "queue",
                    "holder_scope": "task",
                    "holder_key": "Fixture.queue",
                    "target_event": f"{SYNTHETIC_HANDLE_ID}#queue",
                    "capacity": "2",
                    "exceptional_path": False,
                },
                {
                    **common,
                    "site_start_line": 1,
                    "fact_kind": "invariant",
                    "holder_kind": "queue",
                    "holder_scope": "task",
                    "holder_key": "Fixture.queue",
                    "target_event": f"{SYNTHETIC_HANDLE_ID}#queue",
                    "capacity": "2",
                    "exceptional_path": False,
                },
            ]

            extracted = adapt_codeql_rows(rows, source_root=source_root, query_sha256="a" * 64)
            source_snapshot_sha256 = lifecycle_commands._java_source_snapshot(source_root)[1]

        unit = extracted.units[0]
        dispatch = next(
            effect
            for transition in unit.program.transitions
            for effect in transition.effects
            if effect.kind == "dispatch"
        )
        holder = next(item for item in unit.program.holders if item.holder_id == dispatch.holder_id)
        dimensions = check_invariants(
            unit.program,
            solve(unit.program, budget=AnalysisBudget()),
            unit.invariants,
            timeout_ms=100,
            executor_contracts=unit.executor_contracts,
        )
        held = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("task", holder.kind)
        self.assertEqual("task", holder.scope)
        self.assertTrue(dispatch.contract_id.startswith("executor-contract:"))
        self.assertEqual(1, len(unit.executor_contracts))
        executor_contract = unit.executor_contracts[0]
        self.assertEqual(dispatch.contract_id, executor_contract.contract_id)
        invariant = unit.invariants[0]
        self.assertEqual(dispatch.contract_id, invariant.executor_contract_id)
        self.assertEqual(dispatch.holder_id, invariant.writer_holder_id)
        self.assertEqual(dispatch.target_event_id, invariant.writer_target_event_id)
        self.assertEqual("queued", executor_contract.scheduling)
        self.assertEqual(2, executor_contract.queue_capacity)
        self.assertTrue(executor_contract.capacity_atomic)
        self.assertFalse(executor_contract.completion_drops_capture)
        self.assertFalse(executor_contract.rejection_drops_capture)
        self.assertEqual("unknown", executor_contract.cancellation)
        self.assertEqual("static_verified", executor_contract.source_kind)
        self.assertEqual("executor-contract-v1", executor_contract.version)
        self.assertIsNone(executor_contract.max_workers)
        self.assertEqual("unknown", executor_contract.rejection_policy)
        validatable = replace(
            extracted,
            coverage={
                **extracted.coverage,
                "end_to_end_mode": "imported_static_facts",
                "source_snapshot_sha256": source_snapshot_sha256,
            },
        )
        serialized = extracted_to_dict(validatable)
        serialized_invariant = serialized["units"][0]["invariants"][0]
        self.assertEqual(dispatch.contract_id, serialized_invariant["executor_contract_id"])
        self.assertEqual(dispatch.holder_id, serialized_invariant["writer_holder_id"])
        self.assertEqual(
            dispatch.target_event_id,
            serialized_invariant["writer_target_event_id"],
        )
        self.assertEqual(
            [
                {
                    "contract_id": dispatch.contract_id,
                    "scheduling": "queued",
                    "queue_capacity": 2,
                    "capacity_atomic": True,
                    "completion_drops_capture": False,
                    "rejection_drops_capture": False,
                    "cancellation": "unknown",
                    "source_kind": "static_verified",
                    "version": "executor-contract-v1",
                    "core_workers": None,
                    "max_workers": None,
                    "rejection_policy": "unknown",
                    "termination": "unknown",
                }
            ],
            serialized["units"][0]["executor_contracts"],
        )
        json_round_trip = json.loads(json.dumps(serialized, sort_keys=True))
        self.assertEqual(validatable, validate_extracted(extracted_from_dict(json_round_trip)))
        missing_identity = json.loads(json.dumps(serialized, sort_keys=True))
        del missing_identity["units"][0]["invariants"][0]["writer_holder_id"]
        with self.assertRaisesRegex(ValueError, "invariant fields are invalid"):
            extracted_from_dict(missing_identity)
        with self.assertRaisesRegex(ValueError, "duplicate executor contract"):
            replace(
                unit,
                executor_contracts=(executor_contract, executor_contract),
            )
        with self.assertRaisesRegex(ValueError, "executor contract collection"):
            replace(unit, executor_contracts=[executor_contract])  # type: ignore[arg-type]
        stage = lifecycle_commands._analyze_payload(validatable)["units"][0]["async_stages"][0]
        task_edge = [dispatch.instance_id, dispatch.holder_id]
        self.assertIn(task_edge, stage["submitted"]["held_edges"])
        for phase in ("started", "completed", "rejected", "cancelled"):
            self.assertIsNone(stage[phase])
        self.assertIn(
            f"task_binding_unavailable:{dispatch.effect_id}",
            stage["submitted"]["unknown_reasons"],
        )
        self.assertIn(dispatch.instance_id, stage["submitted"]["open_obligations"])
        self.assertEqual(("unknown", None), (held.lifecycle_status, held.upper_bound))
        self.assertIn(
            "executor_population_binding_unavailable",
            held.reason_codes,
        )

        with tempfile.TemporaryDirectory() as tmp:
            secondary_source_root = Path(tmp)
            (secondary_source_root / "Fixture.java").write_text(
                "final class Fixture {}\n", encoding="utf-8"
            )
            without_invariant = adapt_codeql_rows(
                rows[:2], source_root=secondary_source_root, query_sha256="a" * 64
            )
            unknown_rows = [rows[0], {**rows[1], "capacity": "unknown"}]
            unknown_capacity = adapt_codeql_rows(
                unknown_rows, source_root=secondary_source_root, query_sha256="a" * 64
            )
            partial_invariant = adapt_codeql_rows(
                [
                    rows[0],
                    rows[1],
                    {
                        **rows[2],
                        "coverage_status": "partial",
                        "coverage_note": "capacity_atomicity_unresolved",
                    },
                ],
                source_root=secondary_source_root,
                query_sha256="a" * 64,
            )

        self.assertEqual(2, without_invariant.units[0].executor_contracts[0].queue_capacity)
        self.assertFalse(without_invariant.units[0].executor_contracts[0].capacity_atomic)
        self.assertIsNone(unknown_capacity.units[0].executor_contracts[0].queue_capacity)
        self.assertFalse(unknown_capacity.units[0].executor_contracts[0].capacity_atomic)
        self.assertFalse(partial_invariant.units[0].executor_contracts[0].capacity_atomic)
        self.assertEqual((), partial_invariant.units[0].invariants)

    def test_mismatched_queue_identity_cannot_publish_a_capacity_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            rows = [
                lifecycle_row(),
                lifecycle_row(
                    site_start_line=2,
                    fact_kind="dispatch",
                    holder_kind="queue",
                    holder_scope="task",
                    holder_key="Fixture.queueA",
                    target_event=f"{SYNTHETIC_HANDLE_ID}#queueA",
                    capacity="2",
                    exceptional_path=False,
                ),
                lifecycle_row(
                    site_start_line=3,
                    fact_kind="invariant",
                    holder_kind="queue",
                    holder_scope="task",
                    holder_key="Fixture.queueB",
                    target_event=f"{SYNTHETIC_HANDLE_ID}#queueB",
                    capacity="2",
                    exceptional_path=False,
                ),
            ]
            extracted = adapt_codeql_rows(
                rows, source_root=source_root, query_sha256="a" * 64
            )

        unit = extracted.units[0]
        self.assertFalse(unit.executor_contracts[0].capacity_atomic)
        self.assertNotEqual(
            unit.invariants[0].executor_contract_id,
            unit.executor_contracts[0].contract_id,
        )
        payload = lifecycle_commands._analyze_payload(extracted)
        held = next(
            item
            for item in payload["units"][0]["dimensions"]
            if item["dimension"] == "held_instances"
        )

        self.assertEqual("unknown", held["lifecycle_status"])

    def test_static_dispatch_requires_queue_holder_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            rows = [
                lifecycle_row(),
                lifecycle_row(
                    site_start_line=2,
                    fact_kind="dispatch",
                    holder_kind="none",
                    holder_scope="none",
                    holder_key="none",
                    target_event=f"{SYNTHETIC_HANDLE_ID}#queue",
                    capacity="2",
                    exceptional_path=False,
                ),
            ]

            with self.assertRaisesRegex(
                ValueError, "static dispatch queue identity is invalid"
            ):
                adapt_codeql_rows(
                    rows, source_root=source_root, query_sha256="a" * 64
                )

    def test_static_dispatch_rejects_unresolved_holder_or_target_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            for unresolved in ("holder_key", "target_event"):
                dispatch = {
                    "site_start_line": 2,
                    "fact_kind": "dispatch",
                    "holder_kind": "queue",
                    "holder_scope": "task",
                    "holder_key": "Fixture.queue",
                    "target_event": f"{SYNTHETIC_HANDLE_ID}#queue",
                    "capacity": "2",
                    "exceptional_path": False,
                }
                dispatch[unresolved] = "none"

                with self.subTest(unresolved=unresolved), self.assertRaisesRegex(
                    ValueError, "static dispatch queue identity is invalid"
                ):
                    adapt_codeql_rows(
                        [lifecycle_row(), lifecycle_row(**dispatch)],
                        source_root=source_root,
                        query_sha256="a" * 64,
                    )

    def test_same_family_queues_publish_only_distinct_per_queue_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            rows = [lifecycle_row()]
            for index, queue_name in enumerate(("queueA", "queueB"), start=2):
                identity = {
                    "site_start_line": index,
                    "holder_kind": "queue",
                    "holder_scope": "task",
                    "holder_key": f"Fixture.{queue_name}",
                    "target_event": f"{SYNTHETIC_HANDLE_ID}#{queue_name}",
                    "capacity": "2",
                    "exceptional_path": False,
                }
                rows.extend(
                    (
                        lifecycle_row(fact_kind="dispatch", **identity),
                        lifecycle_row(fact_kind="invariant", **identity),
                    )
                )
            extracted = adapt_codeql_rows(
                rows, source_root=source_root, query_sha256="a" * 64
            )

        unit = extracted.units[0]
        self.assertEqual(2, len(unit.executor_contracts))
        self.assertEqual(2, len({item.contract_id for item in unit.executor_contracts}))
        self.assertEqual(
            {item.executor_contract_id for item in unit.invariants},
            {item.contract_id for item in unit.executor_contracts},
        )
        payload = lifecycle_commands._analyze_payload(extracted)
        held = [
            item
            for item in payload["units"][0]["dimensions"]
            if item["dimension"] == "held_instances"
        ]

        self.assertEqual(2, len(held))
        self.assertEqual({("unknown", None)}, {
            (item["lifecycle_status"], item["upper_bound"]) for item in held
        })
        self.assertTrue(
            all(
                "executor_population_binding_unavailable" in item["reason_codes"]
                for item in held
            )
        )
        self.assertEqual(2, len({item["scope"] for item in held}))
        self.assertTrue(all(item["scope"].startswith("task_queue:") for item in held))
        evidence = lifecycle_commands._evidence_payload(extracted, payload)
        proofs = [
            item
            for item in evidence["dimension_derivations"]
            if item["dimension"] == "held_instances"
        ]
        all_candidate_evidence = {
            evidence_id
            for candidate in unit.invariants
            for evidence_id in candidate.evidence_ids
        }
        self.assertEqual(2, len(proofs))
        for proof in proofs:
            matching = [
                candidate
                for candidate in unit.invariants
                if candidate.executor_contract_id in proof["scope"]
            ]
            self.assertEqual(1, len(matching))
            expected = matching[0]
            self.assertEqual([expected.candidate_id], proof["candidate_ids"])
            self.assertEqual(
                set(expected.evidence_ids),
                set(proof["evidence_ids"]).intersection(all_candidate_evidence),
            )
            proof_dependencies = {
                item["evidence_id"]
                for item in evidence["proof_dependencies"]
                if item["proof_id"] == proof["proof_id"]
            }
            self.assertEqual(
                set(expected.evidence_ids),
                proof_dependencies.intersection(all_candidate_evidence),
            )

    def test_same_family_queue_coverage_and_proof_locations_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp)
            (source_root / "Fixture.java").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
            queue_a = {
                "holder_kind": "queue",
                "holder_scope": "task",
                "holder_key": "Fixture.queueA",
                "target_event": f"{SYNTHETIC_HANDLE_ID}#queueA",
                "capacity": "2",
                "exceptional_path": False,
            }
            queue_b = {
                "holder_kind": "queue",
                "holder_scope": "task",
                "holder_key": "Fixture.queueB",
                "target_event": f"{SYNTHETIC_HANDLE_ID}#queueB",
                "capacity": "unknown",
                "exceptional_path": False,
            }
            rows = [
                lifecycle_row(),
                lifecycle_row(site_start_line=2, fact_kind="dispatch", **queue_a),
                lifecycle_row(site_start_line=3, fact_kind="invariant", **queue_a),
                lifecycle_row(site_start_line=4, fact_kind="dispatch", **queue_b),
            ]
            extracted = adapt_codeql_rows(
                rows, source_root=source_root, query_sha256="a" * 64
            )

        unit = extracted.units[0]
        self.assertEqual(1, len(unit.invariants))
        candidate_a = unit.invariants[0]
        dispatch_a = next(
            fact
            for fact in extracted.facts
            if fact.fact_kind == "dispatch" and fact.holder_key == "Fixture.queueA"
        )
        dispatch_b = next(
            fact
            for fact in extracted.facts
            if fact.fact_kind == "dispatch" and fact.holder_key == "Fixture.queueB"
        )
        invariant_a = next(
            fact for fact in extracted.facts if fact.fact_kind == "invariant"
        )
        payload = lifecycle_commands._analyze_payload(extracted)
        held = [
            item
            for item in payload["units"][0]["dimensions"]
            if item["dimension"] == "held_instances"
        ]
        proof_by_scope = {
            item["scope"]: item
            for item in lifecycle_commands._evidence_payload(extracted, payload)[
                "dimension_derivations"
            ]
            if item["dimension"] == "held_instances"
        }

        self.assertEqual(2, len(held))
        modeled_a = next(item for item in held if candidate_a.executor_contract_id in item["scope"])
        unknown_b = next(item for item in held if item is not modeled_a)
        self.assertEqual(("unknown", None), (modeled_a["lifecycle_status"], modeled_a["upper_bound"]))
        self.assertIn(
            "executor_population_binding_unavailable",
            modeled_a["reason_codes"],
        )
        self.assertEqual("unknown", unknown_b["lifecycle_status"])
        self.assertIn("queue_capacity_unknown", unknown_b["reason_codes"])
        self.assertNotIn(dispatch_b.fact_id, modeled_a["evidence_ids"])
        self.assertNotIn(dispatch_a.fact_id, unknown_b["evidence_ids"])
        self.assertNotIn(invariant_a.fact_id, unknown_b["evidence_ids"])

        proof_a = proof_by_scope[modeled_a["scope"]]
        proof_b = proof_by_scope[unknown_b["scope"]]
        self.assertNotIn(dispatch_b.fact_id, proof_a["evidence_ids"])
        self.assertNotIn(dispatch_a.fact_id, proof_b["evidence_ids"])
        self.assertNotIn(invariant_a.fact_id, proof_b["evidence_ids"])
        self.assertNotIn(4, {item["start_line"] for item in proof_a["code_locations"]})
        self.assertNotIn(2, {item["start_line"] for item in proof_b["code_locations"]})


@unittest.skipUnless(
    RUN_FIXTURES and shutil.which("codeql") and shutil.which("javac"),
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class ResourceLifecycleCodeqlFixtureTests(unittest.TestCase):
    def test_v1_1_fresh_review_gaps_from_java(self) -> None:
        source_root = ROOT / "tests/fixtures/resource_lifecycle_v1_1_task_review/src/main/java"
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            base = run_query(DIRECT_QUERY, database, Path(tmp) / "base")
            task = run_query(DIRECT_TASK_QUERY, database, Path(tmp) / "task")
            rows = decode_bqrs_json(
                "resource_lifecycle", json.loads(base.decoded_path.read_text()),
                DecodeSource(database.source_root, base.query_sha256),
            ) + decode_bqrs_json(
                "resource_lifecycle_task_relations", json.loads(task.decoded_path.read_text()),
                DecodeSource(database.source_root, task.query_sha256),
            )
        extracted = adapt_codeql_rows(
            rows, source_root=database.source_root,
            query_provenance=tuple({"query_name": result.query_name,
                                    "query_sha256": result.query_sha256,
                                    "bqrs_sha256": result.bqrs_sha256} for result in (base, task)),
            database_fingerprint=database.fingerprint,
            source_snapshot_sha256=lifecycle_commands._verify_database_source_snapshot(database),
        )
        prefix = "java-callable-v1:fixture.lifecyclev11.taskreview.TaskReviewGaps."
        by_unit = {unit.unit_id: unit for unit in extracted.units}

        def source_facts(caller):
            return [fact for fact in extracted.facts if fact.unit_id == prefix + caller + "(I)V"]

        def task_facts(caller):
            return [fact for fact in source_facts(caller)
                    if fact.query_name == "resource_lifecycle_task_relations"]

        original = by_unit[prefix + "callerReassigned(I)V"]
        self.assertFalse(any(fact.fact_kind in {"dispatch", "release", "invariant", "cfg_edge", "task_exit"}
                             for fact in task_facts("callerReassigned")))
        self.assertFalse(original.program.task_bindings)
        self.assertFalse(any(edge.population_effects or any(effect.kind == "release" for effect in edge.effects)
                             for edge in original.program.transitions))
        original_result = solve(original.program, budget=AnalysisBudget())
        self.assertTrue(any(state.open_obligations for event_id, state in original_result.event_states.items()
                            if event_id in original.program.exit_event_ids),
                        "Rejecting a replacement capture must not close the original allocation")
        preserved = by_unit[prefix + "callerPreserved(I)V"]
        self.assertEqual({1, 2}, {binding.context_depth for binding in preserved.program.call_bindings})
        self.assertTrue(preserved.program.task_bindings)
        self.assertTrue(any(effect.kind == "release" for edge in preserved.program.transitions for effect in edge.effects))
        self.assertNotIn("task_capture_call_binding_unverified", {gap[3] for gap in preserved.program.coverage_gaps})

        for caller in ("callerCloseFieldEscape", "callerCloseContainerEscape", "callerCloseUnknownCall"):
            with self.subTest(caller=caller):
                unit = by_unit[prefix + caller + "(I)V"]
                gaps = [fact for fact in task_facts(caller)
                        if fact.source_evidence == "codeql_task_callback_effect_coverage_gap"
                        and fact.coverage_note == "task_callback_effect_unmodeled"
                        and fact.coverage_status == "partial"]
                self.assertTrue(gaps, "Exact close must not suppress independent callback effect coverage")
                self.assertTrue(any(fact.fact_kind == "release" and fact.coverage_status == "complete"
                                    for fact in task_facts(caller)))
                self.assertTrue(any(effect.kind == "release" for edge in unit.program.transitions for effect in edge.effects))
                for fact in gaps:
                    self.assertNotEqual("none", fact.related_point)
                    self.assertNotEqual(fact.program_point, fact.related_point)
                    point = next(point for point in unit.program.program_points if point.point_id == fact.related_point)
                    self.assertEqual(fact.target_event, point.callable)
                    self.assertEqual(fact.related_location, point.location)
                    self.assertEqual({"held_instances", "item_size_bytes", "close_obligation"},
                                     {gap[0] for gap in unit.program.coverage_gaps if gap[4] == fact.fact_id})
                dimensions = check_invariants(unit.program, solve(unit.program, budget=AnalysisBudget()),
                                              unit.invariants, timeout_ms=100, executor_contracts=unit.executor_contracts)
                self.assertTrue(all(value.lifecycle_status == "unknown" for value in dimensions
                                    if value.dimension == "held_instances"))

        for caller, reason, depth in (
            ("callerStoredMethodReference", "unsupported_method_reference", 1),
            ("callerStoredAnonymous", "unsupported_anonymous_runnable", 1),
            ("callerLocalLambda", "unsupported_local_capture", 0),
            ("callerLocalMethodReference", "unsupported_local_capture", 0),
            ("callerLocalAnonymous", "unsupported_local_capture", 0),
            ("callerFieldAliasExecutor", "executor_configuration_mutable_or_escaped", 1),
        ):
            with self.subTest(caller=caller):
                facts = task_facts(caller)
                gaps = [fact for fact in facts if fact.fact_kind == "unknown_call" and fact.coverage_note == reason]
                self.assertTrue(gaps)
                self.assertTrue(all(fact.relation_depth == depth and fact.binding_index == 0 for fact in gaps))
                self.assertFalse(any(fact.fact_kind in {"dispatch", "release", "invariant", "cfg_edge", "task_exit"}
                                     for fact in facts))
                unit = by_unit[prefix + caller + "(I)V"]
                self.assertFalse(unit.program.task_bindings)
                self.assertFalse(any(edge.population_effects or any(effect.kind == "release" for effect in edge.effects)
                                     for edge in unit.program.transitions))
                for fact in gaps:
                    self.assertNotEqual("none", fact.program_point)
                    self.assertNotEqual("none", fact.related_point)
                    self.assertEqual({"held_instances", "item_size_bytes", "close_obligation"},
                                     {gap[0] for gap in unit.program.coverage_gaps if gap[4] == fact.fact_id})

    def test_v1_1_unsupported_executor_policies_emit_bound_coverage_gaps_from_java(self) -> None:
        source_root = (
            ROOT
            / "tests/fixtures/resource_lifecycle_v1_1_task_policies/src/main/java"
        )
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_query(DIRECT_TASK_QUERY, database, Path(tmp) / "task-query")
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
        rows = decode_bqrs_json(
            "resource_lifecycle_task_relations",
            payload,
            DecodeSource(database.source_root, result.query_sha256),
        )
        prefix = "java-callable-v1:fixture.lifecyclev11.policies.TaskExecutorPolicies."
        cases = {
            "callerCallerRuns(I)V": (
                "dispatchCallerRuns(Lfixture/lifecyclev11/policies/TaskExecutorPolicies$TrackedResource;)V",
                "unsupported_rejection_policy_caller_runs",
            ),
            "callerDiscard(I)V": (
                "dispatchDiscard(Lfixture/lifecyclev11/policies/TaskExecutorPolicies$TrackedResource;)V",
                "unsupported_rejection_policy_discard",
            ),
            "callerDiscardOldest(I)V": (
                "dispatchDiscardOldest(Lfixture/lifecyclev11/policies/TaskExecutorPolicies$TrackedResource;)V",
                "unsupported_rejection_policy_discard_oldest",
            ),
        }

        for caller, (submitter, coverage_note) in cases.items():
            source_rows = [row for row in rows if row["unit_id"] == prefix + caller]
            gaps = [
                row
                for row in source_rows
                if row["fact_kind"] == "unknown_call"
                and row["coverage_status"] == "unsupported"
                and row["coverage_note"] == coverage_note
                and row["source_evidence"]
                == "codeql_unsupported_executor_rejection_policy"
            ]
            self.assertEqual(1, len(gaps), caller)
            gap = gaps[0]
            self.assertEqual(prefix + submitter, gap["site_callable"])
            self.assertEqual(1, gap["relation_depth"])
            self.assertEqual(0, gap["binding_index"])
            self.assertFalse(
                any(
                    row["fact_kind"]
                    in {"dispatch", "invariant", "cfg_edge", "task_exit", "release"}
                    for row in source_rows
                ),
                caller,
            )

        escaped = [row for row in rows if row["unit_id"] == prefix + "callerEscapedExecutor(I)V"]
        self.assertEqual(1, len(escaped))
        self.assertEqual(("unknown_call", "partial", "executor_configuration_mutable_or_escaped"),
                         tuple(escaped[0][key] for key in ("fact_kind", "coverage_status", "coverage_note")))
        self.assertEqual((1, 0), (escaped[0]["relation_depth"], escaped[0]["binding_index"]))

    def test_v1_1_unsupported_task_forms_emit_bound_coverage_gaps_from_java(self) -> None:
        source_root = (
            ROOT
            / "tests/fixtures/resource_lifecycle_v1_1_task_unsupported/src/main/java"
        )
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_query(DIRECT_TASK_QUERY, database, Path(tmp) / "task-query")
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
        rows = decode_bqrs_json(
            "resource_lifecycle_task_relations",
            payload,
            DecodeSource(database.source_root, result.query_sha256),
        )
        prefix = "java-callable-v1:fixture.lifecyclev11.unsupported.TaskUnsupportedForms."
        cases = {
            "callerSubmitCallable(I)V": (
                "submitCallable(Lfixture/lifecyclev11/unsupported/TaskUnsupportedForms$TrackedResource;)V",
                "unsupported_submit_callable",
            ),
            "callerAnonymousRunnable(I)V": (
                "submitAnonymousRunnable(Lfixture/lifecyclev11/unsupported/TaskUnsupportedForms$TrackedResource;)V",
                "unsupported_anonymous_runnable",
            ),
            "callerMethodReference(I)V": (
                "submitMethodReference(Lfixture/lifecyclev11/unsupported/TaskUnsupportedForms$TrackedResource;)V",
                "unsupported_method_reference",
            ),
            "callerLocalExecutor(I)V": (
                "submitLocalExecutor(Lfixture/lifecyclev11/unsupported/TaskUnsupportedForms$TrackedResource;)V",
                "executor_receiver_identity_unresolved",
            ),
            "callerLocalCapture(I)V": (
                "submitLocalCapture(Lfixture/lifecyclev11/unsupported/TaskUnsupportedForms$TrackedResource;)V",
                "unsupported_local_capture",
            ),
        }

        for caller, (submitter, coverage_note) in cases.items():
            source_rows = [row for row in rows if row["unit_id"] == prefix + caller]
            gaps = [
                row
                for row in source_rows
                if row["fact_kind"] == "unknown_call"
                and row["coverage_status"] == "unsupported"
                and row["coverage_note"] == coverage_note
            ]
            self.assertEqual(1, len(gaps), caller)
            gap = gaps[0]
            self.assertEqual(prefix + submitter, gap["site_callable"])
            self.assertEqual(1, gap["relation_depth"])
            self.assertEqual(0, gap["binding_index"])
            self.assertNotEqual("none", gap["program_point"])
            self.assertNotEqual("none", gap["related_point"])
            self.assertFalse(
                any(
                    row["fact_kind"]
                    in {"dispatch", "invariant", "cfg_edge", "task_exit", "release"}
                    for row in source_rows
                ),
                caller,
            )

    def test_v1_1_task_terminals_are_conservative_from_java(self) -> None:
        source_root = (
            ROOT
            / "tests/fixtures/resource_lifecycle_v1_1_task_terminals/src/main/java"
        )
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            base = run_query(DIRECT_QUERY, database, Path(tmp) / "base-query")
            base_payload = json.loads(base.decoded_path.read_text(encoding="utf-8"))
            result = run_query(DIRECT_TASK_QUERY, database, Path(tmp) / "task-query")
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
        rows = decode_bqrs_json(
            "resource_lifecycle_task_relations",
            payload,
            DecodeSource(database.source_root, result.query_sha256),
        )
        base_rows = decode_bqrs_json(
            "resource_lifecycle", base_payload,
            DecodeSource(database.source_root, base.query_sha256),
        )
        extracted = adapt_codeql_rows(
            base_rows + rows, source_root=database.source_root,
            query_provenance=tuple({"query_name": query.query_name,
                                    "query_sha256": query.query_sha256,
                                    "bqrs_sha256": query.bqrs_sha256} for query in (base, result)),
            database_fingerprint=database.fingerprint,
            source_snapshot_sha256=lifecycle_commands._verify_database_source_snapshot(database),
        )
        prefix = "java-callable-v1:fixture.lifecyclev11.terminals.TaskTerminals."

        def rows_for(caller: str) -> list[dict[str, object]]:
            return [row for row in rows if row["unit_id"] == prefix + caller]

        caught = rows_for("callerCaughtThrow(I)V")
        caught_exits = [row for row in caught if row["fact_kind"] == "task_exit"]
        self.assertEqual(
            {(True, False), (False, True)},
            {(row["normal_path"], row["exceptional_path"]) for row in caught_exits},
        )
        self.assertEqual({(31, True, False), (28, False, True)},
                         {(row["site_start_line"], row["normal_path"], row["exceptional_path"])
                          for row in caught_exits})
        self.assertFalse(any(row["site_start_line"] == 27 for row in caught_exits),
                         "The caught explicit throw cannot terminate the task before its catch")
        self.assertTrue(
            any(
                row["fact_kind"] == "unknown_call"
                and row["coverage_status"] == "partial"
                and row["coverage_note"] == "task_terminal_coverage_incomplete"
                for row in caught
            )
        )

        implicit = rows_for("callerImplicitNormal(I)V")
        implicit_exits = [row for row in implicit if row["fact_kind"] == "task_exit"]
        self.assertEqual({(True, False)},
                         {(row["normal_path"], row["exceptional_path"]) for row in implicit_exits})
        self.assertTrue(all(row["source_evidence"] == "codeql_task_annotated_cfg_exit"
                            for row in implicit_exits))
        self.assertTrue(
            any(
                row["fact_kind"] == "unknown_call"
                and row["coverage_note"] == "task_terminal_coverage_incomplete"
                for row in implicit
            )
        )

        call_exception = rows_for("callerCallException(I)V")
        call_exits = [
            row for row in call_exception if row["fact_kind"] == "task_exit"
        ]
        self.assertEqual(
            {(True, False)},
            {(row["normal_path"], row["exceptional_path"]) for row in call_exits},
        )
        self.assertTrue(
            any(
                row["fact_kind"] == "unknown_call"
                and row["coverage_note"] == "task_terminal_coverage_incomplete"
                for row in call_exception
            )
        )
        for caller, expected_kind in (("callerMultipleNormalExits(I)V", (True, False)),
                                      ("callerMultipleExceptionalExits(I)V", (False, True))):
            with self.subTest(caller=caller):
                exits = [row for row in rows_for(caller) if row["fact_kind"] == "task_exit"]
                self.assertEqual(2, len(exits))
                self.assertEqual(2, len({row["program_point"] for row in exits}))
                self.assertEqual({expected_kind}, {(row["normal_path"], row["exceptional_path"])
                                                   for row in exits})
                unit = next(unit for unit in extracted.units if unit.unit_id == prefix + caller)
                fallback_gaps = [fact for fact in extracted.facts if fact.unit_id == unit.unit_id
                                 and fact.source_evidence == "codeql_task_callback_effect_coverage_gap"]
                self.assertTrue(fallback_gaps)
                for fact in fallback_gaps:
                    self.assertTrue(fact.related_point.startswith(fact.site_callable + "#site:"))
                    self.assertFalse(fact.related_point.startswith(fact.target_event + "#site:"))
                    point = next(point for point in unit.program.program_points if point.point_id == fact.related_point)
                    self.assertEqual(fact.site_callable, point.callable,
                                     "The fallback LambdaExpr belongs to the wrapper, not its generated body")
                    self.assertEqual(fact.related_location, point.location)
                    self.assertEqual({"held_instances", "item_size_bytes", "close_obligation"},
                                     {gap[0] for gap in unit.program.coverage_gaps if gap[4] == fact.fact_id})

    def test_v1_1_task_cfg_success_exception_and_executor_gaps_from_java(self) -> None:
        source_root = ROOT / "tests/fixtures/resource_lifecycle_v1_1_task_cfg/src/main/java"
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            base = run_query(DIRECT_QUERY, database, Path(tmp) / "base")
            task = run_query(DIRECT_TASK_QUERY, database, Path(tmp) / "task")
            rows = decode_bqrs_json(
                "resource_lifecycle", json.loads(base.decoded_path.read_text()),
                DecodeSource(database.source_root, base.query_sha256),
            ) + decode_bqrs_json(
                "resource_lifecycle_task_relations", json.loads(task.decoded_path.read_text()),
                DecodeSource(database.source_root, task.query_sha256),
            )
        extracted = adapt_codeql_rows(
            rows, source_root=database.source_root,
            query_provenance=tuple({"query_name": result.query_name,
                                    "query_sha256": result.query_sha256,
                                    "bqrs_sha256": result.bqrs_sha256} for result in (base, task)),
            database_fingerprint=database.fingerprint,
            source_snapshot_sha256=lifecycle_commands._verify_database_source_snapshot(database),
        )
        prefix = "java-callable-v1:fixture.lifecyclev11.taskcfg.TaskCfgCoverage."

        def task_rows(caller):
            return [row for row in rows if row["unit_id"] == prefix + caller + "(I)V"
                    and row["query_name"] == "resource_lifecycle_task_relations"]

        for caller, reason in (
            ("callerExpressionBody", "unsupported_expression_body_lambda_caller_bound"),
            ("callerMutableExecutor", "executor_configuration_mutable_or_escaped"),
            ("callerUnresolvedExecutor", "executor_contract_unresolved"),
        ):
            with self.subTest(caller=caller):
                facts = task_rows(caller)
                self.assertTrue(any(row["coverage_note"] == reason for row in facts))
                self.assertFalse(any(row["fact_kind"] in {"dispatch", "invariant", "cfg_edge", "task_exit", "release"}
                                     for row in facts))
                unit = next(unit for unit in extracted.units if unit.unit_id == prefix + caller + "(I)V")
                self.assertFalse(unit.program.task_bindings)
                self.assertTrue(unit.program.coverage_gaps)
        constants = next(row for row in task_rows("callerConstants") if row["fact_kind"] == "dispatch")
        self.assertEqual(("2", "2", "2", "abort"),
                         tuple(constants[key] for key in ("core_workers", "max_workers", "capacity", "rejection_policy")))
        for caller in ("callerDirectClose", "callerComplexFinally"):
            with self.subTest(caller=caller):
                facts = task_rows(caller)
                self.assertTrue(any(row["fact_kind"] == "dispatch" for row in facts))
                self.assertFalse(any(row["fact_kind"] == "release" for row in facts))
                self.assertTrue(any(row["coverage_note"] == "task_callback_effect_unmodeled"
                                    and row["coverage_status"] == "partial" for row in facts))

        facts = task_rows("callerFinally")
        release = next(row for row in facts if row["fact_kind"] == "release")
        self.assertEqual(release["program_point"] + "#normal-success:call-cfg-v1", release["related_point"])
        self.assertEqual((True, False), (release["normal_path"], release["exceptional_path"]))
        terminals = [row for row in facts if row["fact_kind"] == "task_exit"]
        self.assertEqual({(release["related_point"], True, False),
                          (release["related_point"], False, True),
                          (release["program_point"], False, True)},
                         {(row["program_point"], row["normal_path"], row["exceptional_path"]) for row in terminals})
        unit = next(unit for unit in extracted.units if unit.unit_id == prefix + "callerFinally(I)V")
        program = unit.program
        self.assertEqual(3, len(program.task_exits))
        events = {event.event_id: event for event in program.events}
        releases = [edge for edge in program.transitions if any(effect.kind == "release" for effect in edge.effects)]
        self.assertEqual(1, len(releases))
        self.assertEqual(release["program_point"], events[releases[0].source_event_id].activation_condition)
        self.assertEqual(release["related_point"], events[releases[0].target_event_id].activation_condition)
        self.assertFalse(any(edge.effects for edge in program.transitions
                             if edge.guard in {"normal_task_exit", "exceptional_task_exit"}))
        failed_close_exit = next(exit for exit in program.task_exits if exit.point_id == release["program_point"])
        self.assertEqual("exceptional", failed_close_exit.kind)
        failed_edges = [edge for edge in program.transitions
                        if edge.target_event_id == failed_close_exit.event_id
                        and events[edge.source_event_id].activation_condition == release["program_point"]]
        self.assertEqual(1, len(failed_edges))
        self.assertFalse(failed_edges[0].effects)
        reachable = set(program.entry_event_ids)
        while True:
            expanded = reachable | {edge.target_event_id for edge in program.transitions
                                    if edge.source_event_id in reachable}
            if expanded == reachable:
                break
            reachable = expanded
        self.assertTrue(all(exit.event_id in reachable for exit in program.task_exits))

    def test_v1_1_source_relations_are_extracted_from_java(self) -> None:
        source_root = ROOT / "tests/fixtures/resource_lifecycle_v1_1/src/main/java"
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            base_result = run_query(
                DIRECT_QUERY, database, Path(tmp) / "base-query"
            )
            task_result = run_query(
                DIRECT_TASK_QUERY, database, Path(tmp) / "task-query"
            )
            base_payload = json.loads(
                base_result.decoded_path.read_text(encoding="utf-8")
            )
            task_payload = json.loads(
                task_result.decoded_path.read_text(encoding="utf-8")
            )
        rows = decode_bqrs_json(
            "resource_lifecycle",
            base_payload,
            DecodeSource(database.source_root, base_result.query_sha256),
        ) + decode_bqrs_json(
            "resource_lifecycle_task_relations",
            task_payload,
            DecodeSource(database.source_root, task_result.query_sha256),
        )

        caller = fixture_v1_1_callable("caller", "(I)V")
        wrapper1 = fixture_v1_1_callable(
            "wrapper1",
            "(Lfixture/lifecyclev11/SourcePairs$TrackedResource;)V",
        )
        wrapper2 = fixture_v1_1_callable(
            "wrapper2",
            "(Lfixture/lifecyclev11/SourcePairs$TrackedResource;)V",
        )
        source_rows = [row for row in rows if row["unit_id"] == caller]
        create = next(row for row in source_rows if row["fact_kind"] == "create")
        call_bindings = [
            row for row in source_rows if row["fact_kind"] == "call_binding"
        ]
        cfg_edges = [row for row in source_rows if row["fact_kind"] == "cfg_edge"]
        dispatch = next(row for row in source_rows if row["fact_kind"] == "dispatch")
        callback_release = next(
            row for row in source_rows if row["fact_kind"] == "release"
        )
        task_exits = [row for row in source_rows if row["fact_kind"] == "task_exit"]

        self.assertEqual(
            {(1, wrapper1, 0), (2, wrapper2, 0)},
            {
                (row["relation_depth"], row["target_event"], row["binding_index"])
                for row in call_bindings
            },
        )
        self.assertTrue(
            all(
                row["program_point"] != row["related_point"]
                and row["instance_key"] == create["instance_key"]
                and row["site_start_column"] > 1
                for row in call_bindings
            )
        )
        task_cfg_edges = [
            row for row in cfg_edges if row["target_event"] == dispatch["target_event"]
        ]
        self.assertTrue(
            {
                (31, 13, 31, 17),
                (31, 17, 32, 17),
                (36, 23, 37, 17),
            }
            <= {
                (
                    row["site_start_line"],
                    row["site_start_column"],
                    row["related_start_line"],
                    row["related_start_column"],
                )
                for row in task_cfg_edges
            }
        )
        self.assertTrue(
            all(
                row["query_name"] == "resource_lifecycle_task_relations"
                and row["site_callable"] == dispatch["target_event"]
                and row["program_point"] != row["related_point"]
                for row in task_cfg_edges
            )
        )
        self.assertEqual(dispatch["target_event"], callback_release["site_callable"])
        self.assertEqual(create["instance_key"], callback_release["instance_key"])
        self.assertEqual(37, callback_release["site_start_line"])
        self.assertEqual(17, callback_release["site_start_column"])
        self.assertTrue(callback_release["normal_path"])
        self.assertFalse(callback_release["exceptional_path"])
        self.assertEqual(
            "codeql_task_callback_close_finally",
            callback_release["source_evidence"],
        )
        self.assertTrue(any(
            row["program_point"] == callback_release["program_point"]
            and row["related_point"] == callback_release["related_point"]
            and row["normal_path"] and not row["exceptional_path"]
            for row in task_cfg_edges
        ), "Release must name an actual successful call continuation, never an incoming statement edge")

        self.assertEqual(wrapper2, dispatch["site_callable"])
        self.assertNotEqual("none", dispatch["related_point"])
        self.assertNotEqual(wrapper2, dispatch["target_event"])
        self.assertEqual(create["instance_key"], dispatch["instance_key"])
        self.assertEqual("fixture.lifecyclev11.SourcePairs.EXECUTOR#static", dispatch["holder_key"])
        self.assertEqual("3", dispatch["capacity"])
        self.assertEqual("2", dispatch["core_workers"])
        self.assertEqual("2", dispatch["max_workers"])
        self.assertEqual("abort", dispatch["rejection_policy"])
        self.assertEqual(0, dispatch["binding_index"])
        self.assertEqual("codeql_lambda_capture_to_executor", dispatch["source_evidence"])

        self.assertEqual({(True, False), (False, True)}, {
            (row["normal_path"], row["exceptional_path"])
            for row in task_exits
        })
        self.assertEqual({dispatch["target_event"]}, {
            row["target_event"] for row in task_exits
        })
        self.assertEqual(2, len({row["program_point"] for row in task_exits}))
        self.assertEqual(2, len({row["site_start_line"] for row in task_exits}))
        self.assertEqual({37, 39}, {row["site_start_line"] for row in task_exits})
        self.assertTrue(all(row["source_evidence"] == "codeql_task_annotated_cfg_exit"
                            for row in task_exits))
        self.assertTrue(
            all(
                row["related_point"] == dispatch["related_point"]
                and row["instance_key"] == create["instance_key"]
                for row in task_exits
            )
        )

        extracted = adapt_codeql_rows(
            rows,
            source_root=database.source_root,
            query_provenance=(
                {
                    "query_name": base_result.query_name,
                    "query_sha256": base_result.query_sha256,
                    "bqrs_sha256": base_result.bqrs_sha256,
                },
                {
                    "query_name": task_result.query_name,
                    "query_sha256": task_result.query_sha256,
                    "bqrs_sha256": task_result.bqrs_sha256,
                },
            ),
            database_fingerprint=database.fingerprint,
            source_snapshot_sha256=lifecycle_commands._verify_database_source_snapshot(
                database
            ),
        )
        unit = next(item for item in extracted.units if item.unit_id == caller)
        self.assertEqual(2, len(unit.program.call_bindings))
        self.assertEqual(1, len(unit.program.task_bindings))
        self.assertEqual({"normal", "exceptional"}, {
            item.kind for item in unit.program.task_exits
        })
        task_binding = unit.program.task_bindings[0]
        self.assertEqual(dispatch["target_event"], task_binding.task_callable)
        self.assertTrue(all(
            binding.instance_id == task_binding.instance_id
            for binding in unit.program.call_bindings
        ))
        contract = next(
            item
            for item in unit.executor_contracts
            if item.contract_id == task_binding.executor_contract_id
        )
        self.assertEqual((3, 2, 2, "abort"), (
            contract.queue_capacity,
            contract.core_workers,
            contract.max_workers,
            contract.rejection_policy,
        ))
        self.assertFalse(contract.completion_drops_capture)
        self.assertTrue(contract.rejection_drops_capture)
        self.assertEqual("unknown", contract.cancellation)
        self.assertEqual("unknown", contract.termination)
        release_fact = next(
            fact
            for fact in extracted.facts
            if fact.unit_id == caller and fact.fact_kind == "release"
        )
        self.assertEqual(callback_release["program_point"], release_fact.program_point)
        self.assertEqual(dispatch["target_event"], release_fact.site_callable)
        cfg_release_transitions = [
            transition
            for transition in unit.program.transitions
            if transition.guard == "task_cfg_edge"
            and any(
                effect.kind == "release"
                and effect.condition == "true"
                and effect.evidence_ids == (release_fact.fact_id,)
                for effect in transition.effects
            )
        ]
        self.assertEqual(1, len(cfg_release_transitions))
        events = {event.event_id: event for event in unit.program.events}
        self.assertEqual(release_fact.program_point,
                         events[cfg_release_transitions[0].source_event_id].activation_condition)
        self.assertEqual(release_fact.related_point,
                         events[cfg_release_transitions[0].target_event_id].activation_condition)
        reachable = set(unit.program.entry_event_ids)
        while True:
            expanded = reachable | {edge.target_event_id for edge in unit.program.transitions
                                    if edge.source_event_id in reachable}
            if expanded == reachable:
                break
            reachable = expanded
        self.assertIn(task_binding.submit_event_id, reachable)
        self.assertTrue(all(exit.event_id in reachable for exit in unit.program.task_exits))
        # In this exact-finally fixture every modeled terminal must pass close
        # success. The throw inside try must never bypass the finally block.
        unreleased = {task_binding.run_event_id}
        while True:
            expanded = unreleased | {edge.target_event_id for edge in unit.program.transitions
                                      if edge.source_event_id in unreleased
                                      and not any(effect.kind == "release" for effect in edge.effects)}
            if expanded == unreleased:
                break
            unreleased = expanded
        self.assertTrue(all(exit.event_id not in unreleased for exit in unit.program.task_exits))

        # Task 4: real CFG/capture relations must affect the main solver, using
        # the default budget. No callback edges or resource mappings are added.
        analyzed = solve(unit.program, budget=AnalysisBudget())
        self.assertTrue(analyzed.terminated, analyzed.unknown_reasons)
        terminated_states = analyzed.property_states["after_task_termination"]
        self.assertEqual({item.event_id for item in unit.program.task_exits}, set(terminated_states))
        for state in terminated_states.values():
            self.assertNotIn(task_binding.instance_id, state.open_obligations)
            self.assertNotIn((task_binding.instance_id, task_binding.holder_id), state.held_edges)
        without_release = replace(unit.program, transitions=tuple(
            replace(edge, effects=tuple(effect for effect in edge.effects if effect.kind != "release"))
            for edge in unit.program.transitions))
        missing = solve(without_release, budget=AnalysisBudget())
        self.assertTrue(missing.terminated, missing.unknown_reasons)
        for state in missing.property_states["after_task_termination"].values():
            self.assertIn(task_binding.instance_id, state.open_obligations)
        output = lifecycle_commands._analyze_payload(replace(extracted, units=(unit,)))
        self.assertEqual(1, len(output["units"][0]["async_stages"]))
        self.assertTrue(any(item["scope"].startswith("after_task_termination:")
                            for item in output["units"][0]["dimensions"]))
        if os.environ.get("DOSWEB_TASK4_FACTS_OUT"):
            lifecycle_commands.atomic_write_json(Path(os.environ["DOSWEB_TASK4_FACTS_OUT"]),
                extracted_to_dict(extracted))


    def test_v1_1_wrapper_summary_effects_are_extracted_from_java(self) -> None:
        source_root = (
            ROOT
            / "tests/fixtures/resource_lifecycle_v1_1_wrappers/src/main/java"
        )
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_query(DIRECT_QUERY, database, Path(tmp) / "base-query")
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
        rows = decode_bqrs_json(
            "resource_lifecycle",
            payload,
            DecodeSource(database.source_root, result.query_sha256),
        )
        prefix = "java-callable-v1:fixture.lifecyclev11.wrappers.WrapperEffects."
        resource = "Lfixture/lifecyclev11/wrappers/WrapperEffects$TrackedResource;"
        caller_effects = prefix + "callerEffects(IZ)V"
        wrapper_effect2 = prefix + f"wrapperEffect2({resource}Z)V"
        effect_rows = [
            row
            for row in rows
            if row["unit_id"] == caller_effects
            and row["site_callable"] == wrapper_effect2
        ]
        for row in effect_rows:
            if row["fact_kind"] == "cfg_edge" and "#site:" in row["related_point"]:
                span = row["related_point"].rsplit("#site:", 1)[1].rsplit(":", 4)
                self.assertEqual(
                    (span[0], int(span[1]), int(span[2])),
                    (row["related_file"], row["related_start_line"], row["related_start_column"]),
                    "CFG target evidence must locate the target AST, not its parameter",
                )
        retain = next(row for row in effect_rows if row["fact_kind"] == "retain")
        release = next(row for row in effect_rows if row["fact_kind"] == "release")
        normal_exit_edge = next(
            row
            for row in effect_rows
            if row["fact_kind"] == "cfg_edge"
            and row["normal_path"]
            and not row["exceptional_path"]
        )
        self.assertEqual(
            (
                "field",
                "global",
                "fixture.lifecyclev11.wrappers.WrapperEffects.SHARED#static",
            ),
            (retain["holder_kind"], retain["holder_scope"], retain["holder_key"]),
        )
        self.assertEqual(
            (True, False, "conditional_release_not_must"),
            (
                release["normal_path"],
                release["exceptional_path"],
                release["coverage_note"],
            ),
        )
        self.assertNotEqual(
            normal_exit_edge["program_point"], normal_exit_edge["related_point"]
        )

        caller_return = prefix + f"callerReturn(I){resource}"
        wrapper_return2 = prefix + f"wrapperReturn2({resource}){resource}"
        returned = next(
            row
            for row in rows
            if row["unit_id"] == caller_return
            and row["site_callable"] == wrapper_return2
            and row["coverage_note"] == "returned_resource_identity_bound"
        )
        self.assertEqual(
            ("retain", True, False),
            (
                returned["fact_kind"],
                returned["normal_path"],
                returned["exceptional_path"],
            ),
        )

        caller_instance = prefix + "callerInstanceField(I)V"
        instance_retain = next(
            row
            for row in rows
            if row["unit_id"] == caller_instance
            and row["fact_kind"] == "retain"
            and row["holder_kind"] == "field"
            and row["holder_scope"] == "instance"
        )
        self.assertEqual(
            ("partial", "field_receiver_identity_unresolved"),
            (instance_retain["coverage_status"], instance_retain["coverage_note"]),
        )
        reassigned_rows = [row for row in rows if row["unit_id"] == prefix + "callerReassigned(I)V"]
        self.assertFalse(any(row["fact_kind"] == "call_binding" and row["relation_depth"] == 2
                             for row in reassigned_rows))
        self.assertFalse(any(row["fact_kind"] == "release" for row in reassigned_rows))
        returned_closed = [row for row in rows if row["unit_id"] == prefix + "callerReturnClosed(I)V"]
        returned_create = next(row for row in returned_closed if row["fact_kind"] == "create")
        returned_release = next(row for row in returned_closed if row["fact_kind"] == "release")
        self.assertEqual(returned_create["instance_key"], returned_release["instance_key"])

        extracted = adapt_codeql_rows(
            rows,
            source_root=database.source_root,
            query_sha256=result.query_sha256,
        )
        effect_unit = next(
            item for item in extracted.units if item.unit_id == caller_effects
        )
        finally_unit = next(item for item in extracted.units
                            if item.unit_id == prefix + "callerFinallyWrapper(I)V")
        finally_events = {event.event_id: event for event in finally_unit.program.events}
        finally_binding = next(binding for binding in finally_unit.program.call_bindings
                               if binding.context_depth == 1)
        restored_exception_edges = [
            edge for edge in finally_unit.program.transitions
            if edge.exit_kind == "exceptional"
            and finally_events[edge.source_event_id].activation_condition
            == finally_binding.callee_callable + "#cfg_normal_exit"
        ]
        self.assertTrue(restored_exception_edges,
                        "A successful wrapper in finally must restore the caller's pending exception")
        repeated = next(item.program for item in extracted.units
                        if item.unit_id == prefix + "callerRepeated(I)V")
        first_bindings = [binding for binding in repeated.call_bindings if binding.context_depth == 1]
        self.assertEqual(2, len(first_bindings))
        self.assertNotEqual(first_bindings[0].source_point_id, first_bindings[1].source_point_id)
        adjacency = {}
        for edge in repeated.transitions:
            adjacency.setdefault(edge.source_event_id, set()).add(edge.target_event_id)
        active, done = set(), set()
        def visit(event):
            self.assertNotIn(event, active, "Call-return contexts must not create a cycle in acyclic Java")
            if event in done:
                return
            active.add(event)
            for target in adjacency.get(event, ()):
                visit(target)
            active.remove(event)
            done.add(event)
        for entry in repeated.entry_event_ids:
            visit(entry)
        reachable = set(effect_unit.program.entry_event_ids)
        while True:
            expanded = reachable | {
                edge.target_event_id for edge in effect_unit.program.transitions
                if edge.source_event_id in reachable
            }
            if expanded == reachable:
                break
            reachable = expanded
        self.assertTrue(all(
            any(event.activation_condition == binding.target_point_id
                and event.event_id in reachable for event in effect_unit.program.events)
            for binding in effect_unit.program.call_bindings
        ), "Every bound wrapper parameter must be reachable from the real caller entry")
        for point in effect_unit.program.program_points:
            if "#site:" in point.point_id:
                span = point.point_id.rsplit("#site:", 1)[1].rsplit(":", 4)
                self.assertEqual((span[0], int(span[1])),
                                 (point.location.path, point.location.start_line))
        effect_facts = {
            fact.fact_id: fact
            for fact in extracted.facts
            if fact.unit_id == caller_effects
            and fact.site_callable == wrapper_effect2
            and fact.fact_kind in {"retain", "release"}
        }
        attached_effects = [
            effect
            for transition in effect_unit.program.transitions
            for effect in transition.effects
            if any(evidence_id in effect_facts for evidence_id in effect.evidence_ids)
        ]
        self.assertEqual(
            {"retain"}, {effect.kind for effect in attached_effects}
        )
        partial_releases = [fact for fact in effect_facts.values() if fact.fact_kind == "release"]
        self.assertTrue(partial_releases)
        wrapper_result = solve(effect_unit.program, budget=AnalysisBudget())
        for fact in partial_releases:
            self.assertEqual("partial", fact.coverage_status)
            self.assertEqual("codeql_parameter_close_effect", fact.source_evidence)
            self.assertTrue(any(point.point_id == fact.program_point
                                for point in effect_unit.program.program_points))
            self.assertTrue(any(gap[4] == fact.fact_id for gap in effect_unit.program.coverage_gaps))
            close_events = {event.event_id for event in effect_unit.program.events
                            if event.activation_condition == fact.program_point}
            reached_edges = [edge for edge in effect_unit.program.transitions
                             if edge.source_event_id in close_events
                             and edge.source_event_id in wrapper_result.event_states
                             and edge.target_event_id in wrapper_result.event_states]
            self.assertTrue(reached_edges, "Partial wrapper release must remain on a reachable CFG site")
            for edge in reached_edges:
                before = wrapper_result.event_states[edge.source_event_id]
                after = wrapper_result.event_states[edge.target_event_id]
                self.assertTrue(before.open_obligations)
                self.assertEqual(before.open_obligations, after.open_obligations)
                self.assertEqual(before.obligation_counts, after.obligation_counts)
                self.assertEqual(before.instance_obligation_counts, after.instance_obligation_counts)
                self.assertEqual(before.held_edges, after.held_edges)
                self.assertEqual(before.held_counts, after.held_counts)

    def test_same_site_dispatch_and_invariant_share_program_point_identity(self) -> None:
        source_root = ROOT / "tests/fixtures/resource_lifecycle/src/main/java"
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_query(DIRECT_QUERY, database, Path(tmp) / "query")
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
        rows = decode_bqrs_json(
            "resource_lifecycle",
            payload,
            DecodeSource(database.source_root, result.query_sha256),
        )
        facts = [
            fact
            for fact in adapt_codeql_rows(
                rows,
                source_root=database.source_root,
                query_sha256=result.query_sha256,
            ).facts
            if fact.unit_id == fixture_callable("boundedQueued", "(I)Z")
            and fact.fact_kind in {"dispatch", "invariant"}
        ]
        by_kind = {fact.fact_kind: fact for fact in facts}

        self.assertEqual({"dispatch", "invariant"}, set(by_kind))
        self.assertEqual(
            by_kind["dispatch"].location,
            by_kind["invariant"].location,
        )
        self.assertEqual(
            by_kind["dispatch"].program_point,
            by_kind["invariant"].program_point,
        )

    def test_retained_values_and_holder_scopes_are_precise(self) -> None:
        source_root = ROOT / "tests/fixtures/resource_lifecycle/src/main/java"
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_query(DIRECT_QUERY, database, Path(tmp) / "query")
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
        rows = decode_bqrs_json(
            "resource_lifecycle",
            payload,
            DecodeSource(database.source_root, result.query_sha256),
        )
        extracted = adapt_codeql_rows(rows, source_root=database.source_root, query_sha256=result.query_sha256)

        retained_by_key = {
            fact.holder_key: fact
            for fact in extracted.facts
            if fact.fact_kind == "retain" and fact.holder_kind == "field"
        }
        instance_key = "fixture.lifecycle.LifecycleFixture.initializedPojo"
        global_key = "fixture.lifecycle.LifecycleFixture.globalInitializedPojo"
        self.assertIn(instance_key, retained_by_key)
        self.assertIn(global_key, retained_by_key)
        self.assertEqual("codeql_field_initializer_binding", retained_by_key[instance_key].source_evidence)
        self.assertEqual("codeql_field_initializer_binding", retained_by_key[global_key].source_evidence)
        self.assertEqual("instance", retained_by_key[instance_key].holder_scope)
        self.assertEqual("global", retained_by_key[global_key].holder_scope)

        units = {unit.unit_id: unit for unit in extracted.units}
        for holder_key, expected_scope in ((instance_key, "instance"), (global_key, "global")):
            fact = retained_by_key[holder_key]
            unit = units[fact.unit_id]
            self.assertTrue(unit.program.families)
            self.assertTrue(
                any(holder.kind == "field" and holder.scope == expected_scope for holder in unit.program.holders)
            )

        merge_value_id = "java-callable-v1:fixture.lifecycle.LifecycleFixture.mapMergeValueIsStored(I)V"
        merge_callback_id = (
            "java-callable-v1:fixture.lifecycle.LifecycleFixture.mapMergeCallbackIsNotStored()V"
        )
        self.assertIn(merge_value_id, units)
        self.assertNotIn(merge_callback_id, units)
        merge_create_facts = [
            fact
            for fact in extracted.facts
            if fact.unit_id == merge_value_id and fact.fact_kind == "create"
        ]
        self.assertEqual(1, len(merge_create_facts))
        self.assertEqual(1, len(units[merge_value_id].program.families))

    def test_callable_and_allocation_identities_are_precise(self) -> None:
        source_root = ROOT / "tests/fixtures/resource_lifecycle/src/main/java"
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_query(DIRECT_QUERY, database, Path(tmp) / "query")
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
        rows = decode_bqrs_json(
            "resource_lifecycle",
            payload,
            DecodeSource(database.source_root, result.query_sha256),
        )
        extracted = adapt_codeql_rows(rows, source_root=database.source_root, query_sha256=result.query_sha256)

        integer_id = "java-callable-v1:fixture.lifecycle.LifecycleFixture.overloadedResource(I)V"
        string_id = (
            "java-callable-v1:fixture.lifecycle.LifecycleFixture.overloadedResource"
            "(Ljava/lang/String;)V"
        )
        twin_id = "java-callable-v1:fixture.lifecycle.LifecycleFixture.twinEscapingAllocations(I)V"
        by_unit = {unit.unit_id: unit for unit in extracted.units}
        self.assertIn(integer_id, by_unit)
        self.assertIn(string_id, by_unit)
        self.assertIn(twin_id, by_unit)

        for overload_id in (integer_id, string_id):
            overload = by_unit[overload_id]
            self.assertEqual(1, len(overload.program.families))
            family_ids = {family.family_id for family in overload.program.families}
            self.assertEqual(1, len(family_ids))
            self.assertTrue(
                all(
                    effect.family_id in family_ids
                    for transition in overload.program.transitions
                    for effect in transition.effects
                    if effect.family_id is not None
                )
            )

        twin = by_unit[twin_id]
        self.assertEqual(2, len(twin.program.families))
        self.assertEqual(2, len({family.family_id for family in twin.program.families}))
        self.assertEqual(2, len({instance.instance_id for instance in twin.program.instances}))
        self.assertEqual(
            2,
            len(
                {
                    fact.instance_key
                    for fact in extracted.facts
                    if fact.unit_id == twin_id and fact.fact_kind == "create"
                }
            ),
        )
        self.assertTrue(
            check_invariants(
                twin.program,
                solve(twin.program, budget=AnalysisBudget()),
                twin.invariants,
                timeout_ms=100,
                executor_contracts=twin.executor_contracts,
            )
        )

        selected = adapt_codeql_rows(
            rows,
            source_root=database.source_root,
            query_sha256=result.query_sha256,
            entry_methods=(integer_id,),
        )
        selected_by_unit = {unit.unit_id: unit for unit in selected.units}
        self.assertEqual("request", selected_by_unit[integer_id].program.events[0].kind)
        self.assertEqual("method", selected_by_unit[string_id].program.events[0].kind)
        self.assertEqual([integer_id], selected.coverage["matched_entry_methods"])

    def test_java_source_to_resource_state_results(self) -> None:
        source_root = ROOT / "tests/fixtures/resource_lifecycle/src/main/java"
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            result = run_query(DIRECT_QUERY, database, Path(tmp) / "query")
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
        rows = decode_bqrs_json(
            "resource_lifecycle",
            payload,
            DecodeSource(database.source_root, result.query_sha256),
        )
        extracted = adapt_codeql_rows(rows, source_root=database.source_root, query_sha256=result.query_sha256)

        self.assertEqual("static_verified", extracted.source_kind)
        self.assertTrue(all(fact.location.source_sha256 for fact in extracted.facts))
        by_unit = {unit.unit_id: unit for unit in extracted.units}
        self.assertIn(fixture_callable("syncClosed", "(I)V"), by_unit)
        self.assertIn(fixture_callable("asyncQueued", "(I)V"), by_unit)
        self.assertIn(fixture_callable("boundedQueued", "(I)Z"), by_unit)
        self.assertIn(fixture_callable("concreteBoundedQueued", "(I)Z"), by_unit)
        self.assertIn(fixture_callable("customSubtypeQueued", "(I)Z"), by_unit)
        self.assertIn(fixture_callable("conditionalFinally", "(IZ)V"), by_unit)
        self.assertIn(fixture_callable("finallyPredecessorMayThrow", "(I)V"), by_unit)
        self.assertIn(fixture_callable("overloadedCloseDoesNotRelease", "(I)V"), by_unit)
        self.assertIn(fixture_callable("forUpdateRepeatedAllocation", "(I)V"), by_unit)
        self.assertIn(fixture_callable("whileConditionRepeatedAllocation", "(I)V"), by_unit)
        self.assertIn(fixture_callable("conditionalAlias", "(IZ)V"), by_unit)
        self.assertIn(fixture_callable("overwrittenAlias", "(I)V"), by_unit)
        self.assertIn(fixture_callable("selectedAlias", "(IZ)V"), by_unit)
        self.assertIn(fixture_callable("receiverEscape", "(I)V"), by_unit)
        self.assertIn(
            fixture_callable(
                "returnEscape",
                "(I)Lfixture/lifecycle/LifecycleFixture$TrackedResource;",
            ),
            by_unit,
        )
        self.assertIn(fixture_callable("preTryMayThrow", "(I)V"), by_unit)
        self.assertIn(fixture_callable("pojoFieldRetained", "(I)V"), by_unit)
        self.assertIn(fixture_callable("byteArrayFieldRetained", "(I)V"), by_unit)
        self.assertIn(fixture_callable("byteArrayContainerRetained", "(I)V"), by_unit)
        self.assertIn(fixture_callable("mutableReassignedQueued", "(I)Z"), by_unit)
        self.assertIn(fixture_callable("explicitTaskCapture", "(I)V"), by_unit)
        self.assertIn(fixture_callable("mapPutValueIsStored", "(I)V"), by_unit)
        self.assertIn(fixture_callable("mapReplaceValueIsStored", "(I)V"), by_unit)
        self.assertIn(fixture_callable("mapCompareReplaceNewValueIsStored", "(I)V"), by_unit)
        self.assertNotIn(fixture_callable("temporaryPojo", "(I)V"), by_unit)
        self.assertNotIn(fixture_callable("mapCallbackIsNotStored", "()V"), by_unit)
        self.assertNotIn(fixture_callable("mapCompareReplaceOldValueIsNotStored", "(I)V"), by_unit)

        for unit_name in (
            fixture_callable("pojoFieldRetained", "(I)V"),
            fixture_callable("byteArrayFieldRetained", "(I)V"),
            fixture_callable("byteArrayContainerRetained", "(I)V"),
            fixture_callable("explicitTaskCapture", "(I)V"),
            fixture_callable("mapPutValueIsStored", "(I)V"),
            fixture_callable("mapReplaceValueIsStored", "(I)V"),
            fixture_callable("mapCompareReplaceNewValueIsStored", "(I)V"),
        ):
            ordinary = by_unit[unit_name]
            ordinary_dimensions = check_invariants(
                ordinary.program,
                solve(ordinary.program, budget=AnalysisBudget()),
                ordinary.invariants,
                timeout_ms=100,
                executor_contracts=ordinary.executor_contracts,
            )
            self.assertTrue(ordinary.program.families)
            self.assertTrue(all(family.requires_close is False for family in ordinary.program.families))
            self.assertTrue(
                all(
                    item.lifecycle_status == "not_applicable"
                    for item in ordinary_dimensions
                    if item.dimension == "close_obligation"
                )
            )

        sync = by_unit[fixture_callable("syncClosed", "(I)V")]
        sync_release = next(
            fact for fact in extracted.facts
            if fact.unit_id == sync.unit_id and fact.fact_kind == "release"
        )
        close_exits = [
            fact for fact in extracted.facts
            if fact.unit_id == sync.unit_id and fact.fact_kind == "cfg_edge"
            and fact.program_point == sync_release.program_point
            and fact.related_point in {
                sync.unit_id + "#cfg_normal_exit", sync.unit_id + "#cfg_exceptional_exit"
            }
        ]
        self.assertEqual(
            {sync.unit_id + "#cfg_normal_exit", sync.unit_id + "#cfg_exceptional_exit"},
            {fact.related_point for fact in close_exits},
        )
        # Restoring a pending exception after a successful finally close is not
        # an exception thrown by close itself. Preserve its successful effect.
        self.assertTrue(all(
            fact.source_evidence == "codeql_callable_cfg_exit_after_success"
            for fact in close_exits
        ))
        sync_events = {event.event_id: event for event in sync.program.events}
        release_transitions = [
            edge for edge in sync.program.transitions
            if any(sync_release.fact_id in effect.evidence_ids and effect.kind == "release"
                   for effect in edge.effects)
        ]
        self.assertEqual({"normal", "exceptional"}, {edge.exit_kind for edge in release_transitions})
        self.assertTrue(all(
            sync_events[edge.source_event_id].activation_condition == sync_release.program_point
            for edge in release_transitions
        ))
        sync_result = solve(sync.program, budget=AnalysisBudget())
        sync_dimensions = check_invariants(
            sync.program,
            sync_result,
            sync.invariants,
            timeout_ms=100,
            executor_contracts=sync.executor_contracts,
        )
        self.assertEqual(
            "bounded",
            next(item for item in sync_dimensions if item.dimension == "close_obligation").lifecycle_status,
        )

        predecessor = by_unit[fixture_callable("finallyPredecessorMayThrow", "(I)V")]
        predecessor_releases = [
            fact
            for fact in extracted.facts
            if fact.unit_id == predecessor.unit_id and fact.fact_kind == "release"
        ]
        self.assertTrue(predecessor_releases)
        self.assertTrue(all(fact.coverage_status == "partial" for fact in predecessor_releases))
        self.assertTrue(all(fact.exceptional_path is False for fact in predecessor_releases))
        predecessor_dimensions = check_invariants(
            predecessor.program,
            solve(predecessor.program, budget=AnalysisBudget()),
            predecessor.invariants,
            timeout_ms=100,
            executor_contracts=predecessor.executor_contracts,
        )
        self.assertEqual(
            "unknown",
            next(
                item
                for item in predecessor_dimensions
                if item.dimension == "close_obligation"
            ).lifecycle_status,
        )

        overloaded_close = by_unit[fixture_callable("overloadedCloseDoesNotRelease", "(I)V")]
        overloaded_release_facts = [
            fact
            for fact in extracted.facts
            if fact.unit_id == overloaded_close.unit_id and fact.fact_kind == "release"
        ]
        self.assertFalse(overloaded_release_facts)
        self.assertTrue(
            any(
                fact.unit_id == overloaded_close.unit_id
                and fact.fact_kind == "unknown_call"
                and fact.coverage_status == "partial"
                and fact.coverage_note == "callee_resource_effects_unmodeled"
                for fact in extracted.facts
            )
        )
        method_unknowns = [
            fact
            for fact in extracted.facts
            if fact.fact_kind == "unknown_call"
            and fact.source_evidence == "codeql_unmodeled_argument_escape"
        ]
        self.assertTrue(method_unknowns)
        self.assertTrue(
            all(fact.target_event.startswith("java-callable-v1:") for fact in method_unknowns)
        )
        self.assertTrue(
            any(
                fact.unit_id == fixture_callable("receiverEscape", "(I)V")
                and fact.target_event.endswith(".touch()V")
                and fact.coverage_note == "callee_resource_effects_unmodeled"
                for fact in method_unknowns
            )
        )
        self.assertTrue(
            any(
                fact.unit_id
                == fixture_callable(
                    "polymorphicEscape",
                    "(ILfixture/lifecycle/LifecycleFixture$ResourceObserver;)V",
                )
                and fact.target_event.endswith(".inspect(Lfixture/lifecycle/LifecycleFixture$TrackedResource;)V")
                and fact.coverage_note == "source_callee_dispatch_target_unresolved"
                for fact in method_unknowns
            )
        )
        self.assertTrue(
            any(
                fact.unit_id == overloaded_close.unit_id
                and fact.target_event.endswith(".close(Z)V")
                for fact in method_unknowns
            )
        )
        return_unknowns = [
            fact
            for fact in extracted.facts
            if fact.unit_id
            == fixture_callable(
                "returnEscape",
                "(I)Lfixture/lifecycle/LifecycleFixture$TrackedResource;",
            )
            and fact.fact_kind == "unknown_call"
            and fact.source_evidence == "codeql_resource_return_escape"
        ]
        self.assertTrue(return_unknowns)
        self.assertTrue(all(fact.target_event == "none" for fact in return_unknowns))
        overloaded_close_dimensions = check_invariants(
            overloaded_close.program,
            solve(overloaded_close.program, budget=AnalysisBudget()),
            overloaded_close.invariants,
            timeout_ms=100,
            executor_contracts=overloaded_close.executor_contracts,
        )
        self.assertEqual(
            "unknown",
            next(
                item
                for item in overloaded_close_dimensions
                if item.dimension == "close_obligation"
            ).lifecycle_status,
        )

        for loop_unit_id in (
            fixture_callable("forUpdateRepeatedAllocation", "(I)V"),
            fixture_callable("whileConditionRepeatedAllocation", "(I)V"),
        ):
            with self.subTest(loop_unit_id=loop_unit_id):
                loop_unit = by_unit[loop_unit_id]
                loop_releases = [
                    fact
                    for fact in extracted.facts
                    if fact.unit_id == loop_unit_id and fact.fact_kind == "release"
                ]
                self.assertTrue(loop_releases)
                self.assertTrue(
                    all(
                        fact.coverage_status == "partial"
                        and fact.normal_path is False
                        and fact.exceptional_path is False
                        and fact.coverage_note == "allocation_in_loop_release_not_must"
                        for fact in loop_releases
                    )
                )
                loop_dimensions = check_invariants(
                    loop_unit.program,
                    solve(loop_unit.program, budget=AnalysisBudget()),
                    loop_unit.invariants,
                    timeout_ms=100,
                    executor_contracts=loop_unit.executor_contracts,
                )
                self.assertEqual(
                    "unknown",
                    next(
                        item
                        for item in loop_dimensions
                        if item.dimension == "close_obligation"
                    ).lifecycle_status,
                )

        for unit_name in (
            fixture_callable("conditionalAlias", "(IZ)V"),
            fixture_callable("overwrittenAlias", "(I)V"),
            fixture_callable("selectedAlias", "(IZ)V"),
        ):
            with self.subTest(unit_name=unit_name):
                ambiguous = by_unit[unit_name]
                ambiguous_releases = [
                    fact
                    for fact in extracted.facts
                    if fact.unit_id == ambiguous.unit_id and fact.fact_kind == "release"
                ]
                self.assertTrue(ambiguous_releases)
                self.assertTrue(
                    all(
                        fact.coverage_status == "partial"
                        and fact.normal_path is False
                        and fact.exceptional_path is False
                        for fact in ambiguous_releases
                    )
                )
                ambiguous_result = solve(ambiguous.program, budget=AnalysisBudget())
                release_ids = {fact.fact_id for fact in ambiguous_releases}
                self.assertFalse(any(
                    effect.kind == "release" and release_ids.intersection(effect.evidence_ids)
                    for edge in ambiguous.program.transitions for effect in edge.effects
                ))
                release_points = {fact.program_point for fact in ambiguous_releases}
                self.assertTrue(release_points <= {point.point_id for point in ambiguous.program.program_points})
                self.assertTrue(release_ids <= {gap[4] for gap in ambiguous.program.coverage_gaps})
                close_events = {event.event_id for event in ambiguous.program.events
                                if event.activation_condition in release_points}
                reached_edges = [edge for edge in ambiguous.program.transitions
                                 if edge.source_event_id in close_events
                                 and edge.source_event_id in ambiguous_result.event_states
                                 and edge.target_event_id in ambiguous_result.event_states]
                self.assertTrue(reached_edges)
                for edge in reached_edges:
                    before = ambiguous_result.event_states[edge.source_event_id]
                    after = ambiguous_result.event_states[edge.target_event_id]
                    self.assertTrue(before.open_obligations)
                    self.assertEqual(before.open_obligations, after.open_obligations)
                    self.assertEqual(before.obligation_counts, after.obligation_counts)
                    self.assertEqual(before.instance_obligation_counts, after.instance_obligation_counts)
                ambiguous_dimensions = check_invariants(
                    ambiguous.program,
                    ambiguous_result,
                    ambiguous.invariants,
                    timeout_ms=100,
                    executor_contracts=ambiguous.executor_contracts,
                )
                close_statuses = {
                    item.lifecycle_status
                    for item in ambiguous_dimensions
                    if item.dimension == "close_obligation"
                }
                self.assertIn("unknown", close_statuses)
                self.assertNotIn("bounded", close_statuses)

        pre_try = by_unit[fixture_callable("preTryMayThrow", "(I)V")]
        pre_try_dimensions = check_invariants(
            pre_try.program,
            solve(pre_try.program, budget=AnalysisBudget()),
            pre_try.invariants,
            timeout_ms=100,
            executor_contracts=pre_try.executor_contracts,
        )
        self.assertEqual(
            "unknown",
            next(
                item
                for item in pre_try_dimensions
                if item.dimension == "close_obligation"
            ).lifecycle_status,
        )

        asynchronous = by_unit[fixture_callable("asyncQueued", "(I)V")]
        async_result = solve(asynchronous.program, budget=AnalysisBudget())
        async_dimensions = check_invariants(
            asynchronous.program,
            async_result,
            asynchronous.invariants,
            timeout_ms=100,
            executor_contracts=asynchronous.executor_contracts,
        )
        self.assertEqual(
            "unknown",
            next(item for item in async_dimensions if item.dimension == "held_instances").lifecycle_status,
        )

        bounded = by_unit[fixture_callable("boundedQueued", "(I)Z")]
        bounded_returns = [
            fact for fact in extracted.facts
            if fact.unit_id == bounded.unit_id and fact.fact_kind == "cfg_edge"
            and fact.related_point == bounded.unit_id + "#cfg_normal_exit"
        ]
        self.assertEqual(2, len({fact.program_point for fact in bounded_returns}),
                         "Both boolean return statements must reach the actual normal exit")
        bounded_result = solve(bounded.program, budget=AnalysisBudget())
        self.assertEqual(set(bounded.program.exit_event_ids), set(bounded_result.exit_states))
        bounded_dimensions = check_invariants(
            bounded.program,
            bounded_result,
            bounded.invariants,
            timeout_ms=100,
            executor_contracts=bounded.executor_contracts,
        )
        held = next(item for item in bounded_dimensions if item.dimension == "held_instances")
        size = next(item for item in bounded_dimensions if item.dimension == "item_size_bytes")
        self.assertEqual(("bounded", 2), (held.lifecycle_status, held.upper_bound))
        self.assertEqual("unknown", size.lifecycle_status)
        bounded_close = next(item for item in bounded_dimensions if item.dimension == "close_obligation")
        self.assertEqual("unknown", bounded_close.lifecycle_status)
        self.assertIn("async_consumer_contract_unmodeled", bounded_close.reason_codes)
        self.assertTrue(any(event.kind == "task_queue" for event in bounded.program.events))
        self.assertTrue(any(effect.kind == "dispatch" for transition in bounded.program.transitions for effect in transition.effects))
        self.assertIn("dispatch_capture_on_contract", bounded_result.traces[next(iter(bounded_result.exit_states))].rule_ids)

        concrete_bounded = by_unit[fixture_callable("concreteBoundedQueued", "(I)Z")]
        concrete_facts = [
            fact for fact in extracted.facts if fact.unit_id == concrete_bounded.unit_id
        ]
        self.assertTrue(any(fact.fact_kind == "dispatch" for fact in concrete_facts))
        self.assertTrue(
            any(
                fact.fact_kind == "invariant" and fact.capacity == "3"
                for fact in concrete_facts
            )
        )
        concrete_dimensions = check_invariants(
            concrete_bounded.program,
            solve(concrete_bounded.program, budget=AnalysisBudget()),
            concrete_bounded.invariants,
            timeout_ms=100,
            executor_contracts=concrete_bounded.executor_contracts,
        )
        concrete_held = next(
            item for item in concrete_dimensions if item.dimension == "held_instances"
        )
        self.assertEqual(
            ("bounded", 3),
            (concrete_held.lifecycle_status, concrete_held.upper_bound),
        )

        custom_subtype = by_unit[fixture_callable("customSubtypeQueued", "(I)Z")]
        custom_facts = [
            fact for fact in extracted.facts if fact.unit_id == custom_subtype.unit_id
        ]
        self.assertFalse(
            any(fact.fact_kind in {"dispatch", "invariant"} for fact in custom_facts)
        )
        custom_dimensions = check_invariants(
            custom_subtype.program,
            solve(custom_subtype.program, budget=AnalysisBudget()),
            custom_subtype.invariants,
            timeout_ms=100,
            executor_contracts=custom_subtype.executor_contracts,
        )
        custom_held = next(
            item for item in custom_dimensions if item.dimension == "held_instances"
        )
        self.assertEqual("unknown", custom_held.lifecycle_status)

        mutable = by_unit[fixture_callable("mutableReassignedQueued", "(I)Z")]
        mutable_dimensions = check_invariants(
            mutable.program,
            solve(mutable.program, budget=AnalysisBudget()),
            mutable.invariants,
            timeout_ms=100,
            executor_contracts=mutable.executor_contracts,
        )
        self.assertFalse(mutable.invariants)
        self.assertEqual(
            "unknown",
            next(
                item
                for item in mutable_dimensions
                if item.dimension == "held_instances"
            ).lifecycle_status,
        )

        conditional = by_unit[fixture_callable("conditionalFinally", "(IZ)V")]
        conditional_dimensions = {
            item.dimension: item
            for item in check_invariants(
                conditional.program,
                solve(conditional.program, budget=AnalysisBudget()),
                conditional.invariants,
                timeout_ms=100,
                executor_contracts=conditional.executor_contracts,
            )
        }
        self.assertEqual("bounded", conditional_dimensions["held_instances"].lifecycle_status)
        self.assertEqual("unknown", conditional_dimensions["close_obligation"].lifecycle_status)
        self.assertIn(
            "conditional_release_not_must",
            conditional_dimensions["close_obligation"].reason_codes,
        )

        for unit_name in (
            fixture_callable("receiverEscape", "(I)V"),
            fixture_callable(
                "returnEscape",
                "(I)Lfixture/lifecycle/LifecycleFixture$TrackedResource;",
            ),
        ):
            unit = by_unit[unit_name]
            dimensions = check_invariants(
                unit.program,
                solve(unit.program, budget=AnalysisBudget()),
                unit.invariants,
                timeout_ms=100,
                executor_contracts=unit.executor_contracts,
            )
            self.assertTrue(all(item.lifecycle_status == "unknown" for item in dimensions))

    def test_real_codeql_database_runs_through_all_three_cli_commands(self) -> None:
        source_root = ROOT / "tests/fixtures/resource_lifecycle/src/main/java"
        database = fixture_database(str(source_root))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            facts = root / "facts"
            run = root / "run"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "mode": "codeql_database",
                        "database": str(database.path),
                        "entry_methods": [
                            fixture_callable("syncClosed", "(I)V"),
                            fixture_callable("asyncQueued", "(I)V"),
                            fixture_callable("boundedQueued", "(I)Z"),
                        ],
                        "budget": {"max_steps": 1024, "max_updates_per_event": 32, "timeout_ms": 5000},
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            self.assertEqual(0, main(["resource-extract", "--manifest", str(manifest), "--out", str(facts)]))
            self.assertEqual(0, main(["resource-analyze", "--facts", str(facts / "facts.json"), "--out", str(run), "--llm", "off"]))
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            coverage = json.loads((facts / "coverage.json").read_text(encoding="utf-8"))
            replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))

        self.assertEqual("real_source_codeql", coverage["end_to_end_mode"])
        self.assertGreaterEqual(coverage["units"], 3)
        self.assertTrue(replay["consistent"])
        self.assertEqual(results["result_sha256"], replay["recomputed_result_sha256"])


if __name__ == "__main__":
    unittest.main()
