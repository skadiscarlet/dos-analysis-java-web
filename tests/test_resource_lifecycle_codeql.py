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
from dosweb.codeql import DecodeSource, QUERY_SPECS, decode_bqrs_json, decode_rows, run_query
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
RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
SYNTHETIC_HANDLE_ID = "java-callable-v1:Fixture.handle()V"
SYNTHETIC_SOURCE = "final class Fixture {\n\n\n}\n"


def fixture_callable(method: str, descriptor: str) -> str:
    return f"java-callable-v1:fixture.lifecycle.LifecycleFixture.{method}{descriptor}"


def decoded_lifecycle_row(source_root: Path, query_sha256: str = "a" * 64) -> dict[str, object]:
    row = lifecycle_row()
    values = [row[column] for column in QUERY_SPECS["resource_lifecycle"].columns]
    return decode_rows(
        "resource_lifecycle",
        QUERY_SPECS["resource_lifecycle"].columns,
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
    "site_callable",
    "program_point",
    "related_point",
    "relation_depth",
    "binding_index",
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

            for field in ("max_workers", "rejection_policy", "termination"):
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
                if key not in {"query_name", "query_sha256", "site_location"}
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
        content = DIRECT_QUERY.read_text(encoding="utf-8")
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

    def test_program_point_identity_is_site_based_and_uses_the_full_span(self) -> None:
        content = DIRECT_QUERY.read_text(encoding="utf-8")

        self.assertIn("bindingset[site]", content)
        self.assertIn("string programPointIdentity(Expr site)", content)
        self.assertNotIn(
            "string programPointIdentity(Expr site, string factKind)", content
        )
        self.assertNotIn(
            'canonicalCallableIdentity(callable) + "#" + factKind', content
        )
        self.assertIn("site.getLocation().getEndLine().toString()", content)
        self.assertIn("site.getLocation().getEndColumn().toString()", content)
        self.assertIn("programPointIdentity(site) as program_point", content)

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
        self.assertIn(task_edge, stage["started"]["held_edges"])
        self.assertIn(task_edge, stage["rejected"]["held_edges"])
        self.assertIn(task_edge, stage["completed"]["held_edges"])
        self.assertIn(task_edge, stage["cancelled"]["held_edges"])
        self.assertIn(
            f"completion_contract_unknown:{dispatch.contract_id}",
            stage["completed"]["unknown_reasons"],
        )
        self.assertIn(
            f"cancel_contract_unknown:{dispatch.contract_id}",
            stage["cancelled"]["unknown_reasons"],
        )
        self.assertIn(
            f"rejection_policy_conservative:{dispatch.contract_id}:unknown",
            stage["rejected"]["unknown_reasons"],
        )
        for phase in ("submitted", "started", "completed", "rejected", "cancelled"):
            self.assertIn(dispatch.instance_id, stage[phase]["open_obligations"])
        self.assertEqual(("bounded", 2), (held.lifecycle_status, held.upper_bound))

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
        self.assertEqual({("bounded", 2)}, {
            (item["lifecycle_status"], item["upper_bound"]) for item in held
        })
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
        bounded_a = next(item for item in held if candidate_a.executor_contract_id in item["scope"])
        unknown_b = next(item for item in held if item is not bounded_a)
        self.assertEqual(("bounded", 2), (bounded_a["lifecycle_status"], bounded_a["upper_bound"]))
        self.assertEqual("unknown", unknown_b["lifecycle_status"])
        self.assertIn("queue_capacity_unknown", unknown_b["reason_codes"])
        self.assertNotIn(dispatch_b.fact_id, bounded_a["evidence_ids"])
        self.assertNotIn(dispatch_a.fact_id, unknown_b["evidence_ids"])
        self.assertNotIn(invariant_a.fact_id, unknown_b["evidence_ids"])

        proof_a = proof_by_scope[bounded_a["scope"]]
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
                ambiguous_dimensions = check_invariants(
                    ambiguous.program,
                    solve(ambiguous.program, budget=AnalysisBudget()),
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
        bounded_result = solve(bounded.program, budget=AnalysisBudget())
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
