from __future__ import annotations

from dataclasses import replace
import tempfile
from pathlib import Path
import unittest

from dosweb.resource_lifecycle.models import AnalysisBudget
from dosweb.resource_lifecycle.summaries import (
    FactIndex,
    RecordedUsage,
    SummaryBudget,
    SummaryCache,
    SummaryProposal,
    SummaryRequest,
    cache_key,
    validate_summary,
)
from tests.test_resource_lifecycle_solver import effect, location


def proposal(*, kind: str = "release", proposal_location=None) -> SummaryProposal:
    current = replace(
        effect(kind, holder_id="holder:field" if kind in {"retain", "drop"} else None),
        location=location("llm_proposed"),
    )
    return SummaryProposal(
        summary_id="summary:wrapper",
        method="Fixture.wrapper",
        preconditions=("argument 0 is instance:stream",),
        normal_effects=(current,),
        exceptional_effects=(current,),
        captures=(),
        field_saves=("holder:field",) if kind == "retain" else (),
        location=proposal_location or location("llm_proposed"),
        evidence_ids=(f"fact:{kind}",),
        source_kind="llm_proposed",
    )


def facts(*, kind: str = "release", identity_exact: bool = True, exceptional_exit: bool = True) -> FactIndex:
    return FactIndex(
        fact_ids=frozenset({f"fact:{kind}"}),
        locations=frozenset({("src/main/java/Fixture.java", 3)}),
        parameters=frozenset({"argument 0"}),
        supported_effects=frozenset({(kind, "instance:stream", "holder:field" if kind in {"retain", "drop"} else None)}),
        identity_exact=identity_exact,
        normal_exit_covered=True,
        exceptional_exit_covered=exceptional_exit,
    )


class ResourceLifecycleSummaryTests(unittest.TestCase):
    def test_verified_llm_release_remains_display_only(self) -> None:
        validation = validate_summary(proposal(kind="release"), facts(kind="release"))

        self.assertEqual("verified", validation.status)
        self.assertEqual((), validation.usable_effects)
        self.assertIn("llm_proposed_release_cannot_prove_must_release", validation.reason_codes)

    def test_llm_retain_can_be_used_only_after_all_semantic_layers_verify(self) -> None:
        current = proposal(kind="retain")
        validation = validate_summary(current, facts(kind="retain"))

        self.assertEqual("verified", validation.status)
        self.assertEqual(current.normal_effects, validation.usable_effects)
        self.assertTrue(all(layer.status == "verified" for layer in validation.layers))

    def test_fabricated_location_is_rejected(self) -> None:
        invalid_location = replace(location("llm_proposed"), start_line=99, end_line=99)
        validation = validate_summary(proposal(proposal_location=invalid_location), facts())

        self.assertEqual("rejected", validation.status)
        self.assertIn("location_not_in_static_slice", validation.reason_codes)

    def test_missing_exceptional_exit_is_unresolved_and_cannot_prove_release(self) -> None:
        validation = validate_summary(proposal(), facts(exceptional_exit=False))

        self.assertEqual("unresolved", validation.status)
        self.assertEqual((), validation.usable_effects)
        self.assertIn("exceptional_exit_uncovered", validation.reason_codes)

    def test_identity_uncertainty_is_distinct_from_location_failure(self) -> None:
        validation = validate_summary(proposal(kind="drop"), facts(kind="drop", identity_exact=False))

        self.assertEqual("unresolved", validation.status)
        self.assertIn("resource_identity_unresolved", validation.reason_codes)
        self.assertNotIn("location_not_in_static_slice", validation.reason_codes)

    def test_proposal_rejects_effect_that_is_not_marked_llm_proposed(self) -> None:
        current = effect("retain", holder_id="holder:field")
        with self.assertRaisesRegex(ValueError, "effect source"):
            replace(proposal(kind="retain"), normal_effects=(current,))

    def test_proposal_rejects_duplicate_effect_identity(self) -> None:
        current = proposal(kind="retain")
        duplicate = replace(current.normal_effects[0], condition="other_path")

        with self.assertRaisesRegex(ValueError, "effect identity"):
            replace(current, normal_effects=(current.normal_effects[0], duplicate))

    def test_effect_evidence_must_be_present_in_static_fact_index(self) -> None:
        current = replace(proposal(kind="retain").normal_effects[0], evidence_ids=("fact:fabricated",))
        validation = validate_summary(
            replace(proposal(kind="retain"), normal_effects=(current,), exceptional_effects=(current,)),
            facts(kind="retain"),
        )

        self.assertEqual("unresolved", validation.status)
        self.assertIn("operation_or_dataflow_unresolved", validation.reason_codes)

    def test_full_operation_support_binds_condition_size_and_evidence(self) -> None:
        current = proposal(kind="retain")
        supported = current.normal_effects[0]
        indexed = replace(
            facts(kind="retain"),
            supported_operations=frozenset(
                {
                    (
                        supported.kind,
                        supported.instance_id,
                        supported.family_id,
                        supported.holder_id,
                        supported.target_event_id,
                        supported.contract_id,
                        supported.condition,
                        supported.size_lower,
                        supported.size_upper,
                        supported.evidence_ids,
                    )
                }
            ),
        )
        tampered = replace(supported, condition="fabricated_condition")

        baseline = validate_summary(current, indexed)

        validation = validate_summary(
            replace(current, normal_effects=(tampered,), exceptional_effects=(tampered,)),
            indexed,
        )

        self.assertEqual("verified", baseline.status)
        self.assertEqual("unresolved", validation.status)
        self.assertIn("operation_or_dataflow_unresolved", validation.reason_codes)

    def test_operation_support_is_bound_to_normal_and_exceptional_exits(self) -> None:
        current = proposal(kind="retain")
        supported = current.normal_effects[0]
        operation = (
            supported.kind,
            supported.instance_id,
            supported.family_id,
            supported.holder_id,
            supported.target_event_id,
            supported.contract_id,
            supported.condition,
            supported.size_lower,
            supported.size_upper,
            supported.evidence_ids,
        )
        indexed = replace(
            facts(kind="retain"),
            supported_operations=frozenset({operation}),
            normal_supported_operations=frozenset({operation}),
            exceptional_supported_operations=frozenset(),
        )

        normal_only = validate_summary(replace(current, exceptional_effects=()), indexed)
        unsupported_exceptional = validate_summary(current, indexed)

        self.assertEqual("verified", normal_only.status)
        self.assertEqual("unresolved", unsupported_exceptional.status)
        self.assertIn("operation_or_dataflow_unresolved", unsupported_exceptional.reason_codes)

    def test_cache_key_covers_source_model_contract_and_budget(self) -> None:
        request = SummaryRequest(
            unknown_effect_id="effect:" + "1" * 24,
            method="Fixture.wrapper",
            source_path="src/main/java/Fixture.java",
            start_line=3,
            end_line=3,
            start_column=7,
            source_sha256="a" * 64,
            source_snapshot_sha256="c" * 64,
            snippet_sha256="b" * 64,
            signature="void wrapper(Resource value)",
            model="recorded-model",
            contract_version="summary-contract-v1",
        )
        manifest = {
            "tool_version": "resource-lifecycle-v1.0",
            "implementation_sha256": "d" * 64,
            "budget": {"calls": 2, "tokens": 1000, "timeout_ms": 100, "retries": 1},
        }
        baseline = cache_key(request, manifest)

        variants = (
            replace(request, source_sha256="c" * 64),
            replace(request, model="other-model"),
            replace(request, contract_version="summary-contract-v2"),
        )
        self.assertTrue(all(cache_key(item, manifest) != baseline for item in variants))
        self.assertNotEqual(
            baseline,
            cache_key(request, {**manifest, "budget": {"calls": 1, "tokens": 1000, "timeout_ms": 100, "retries": 1}}),
        )
        self.assertNotEqual(
            baseline,
            cache_key(request, {**manifest, "implementation_sha256": "e" * 64}),
        )

    def test_cache_version_change_is_a_miss(self) -> None:
        request = SummaryRequest(
            "effect:" + "1" * 24,
            "Fixture.wrapper",
            "src/main/java/Fixture.java",
            3,
            3,
            7,
            "a" * 64,
            "c" * 64,
            "b" * 64,
            "void wrapper(Resource value)",
            "recorded-model",
            "summary-contract-v1",
        )
        manifest = {"tool_version": "resource-lifecycle-v1.0", "budget": {"calls": 1, "tokens": 100, "timeout_ms": 100, "retries": 0}}
        key = cache_key(request, manifest)
        with tempfile.TemporaryDirectory() as tmp:
            first = SummaryCache(Path(tmp), version="summary-cache-v1")
            first.put(key, proposal(kind="retain"))
            self.assertIsNotNone(first.get(key))

            stale = SummaryCache(Path(tmp), version="summary-cache-v2")
            self.assertIsNone(stale.get(key))

    def test_summary_budget_is_explicitly_bounded(self) -> None:
        value = SummaryBudget(max_calls=2, max_tokens=1000, timeout_ms=500, max_retries=1)
        self.assertEqual((2, 1000, 500, 1), (value.max_calls, value.max_tokens, value.timeout_ms, value.max_retries))
        with self.assertRaisesRegex(ValueError, "budget"):
            SummaryBudget(max_calls=0, max_tokens=1000, timeout_ms=500, max_retries=1)
        with self.assertRaisesRegex(ValueError, "budget"):
            SummaryBudget(max_calls=float("inf"), max_tokens=1000, timeout_ms=500, max_retries=1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "budget"):
            SummaryBudget(max_calls=1.5, max_tokens=1000, timeout_ms=500, max_retries=1)  # type: ignore[arg-type]

    def test_recorded_usage_requires_non_negative_integers(self) -> None:
        self.assertEqual((1, 2), (RecordedUsage(1, 2).input_tokens, RecordedUsage(1, 2).output_tokens))
        for value in (0.5, float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "usage"):
                RecordedUsage(value, 1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
