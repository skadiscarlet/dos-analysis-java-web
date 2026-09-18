from __future__ import annotations

import hashlib
import unittest

from dosweb.artifacts.schemas import validate_records
from dosweb.growth import (
    AttackerInfluence,
    BoundedSlice,
    CfgSummary,
    GrowthCandidate,
    GrowthContract,
    RegistrationFact,
    SourceExcerpt,
    StaticFact,
    build_bounded_slice,
    normalize_growth_rows,
    verify_growth_contract,
)


class GrowthVerificationTests(unittest.TestCase):
    def _raw(self, **changes: object) -> dict[str, object]:
        row: dict[str, object] = {
            "site_file": "fixture/spring/SpringFixture.java",
            "site_start_line": 40,
            "growth_kind": "container_growth",
            "operation": "java.util.Map.put",
            "resource_dimension": "entries",
            "receiver": "fixture.spring.SpringFixture.registry",
            "field_path": "this.registry",
            "demand_input_name": "key",
            "demand_input_role": "key",
            "escape_scope": "instance",
            "candidate_evidence": "map_put_receiver",
            "coverage_status": "complete",
            "coverage_note": "persistent_map_insertion",
            "query_name": "growth",
            "query_sha256": "a" * 64,
            "site_location": "fixture/spring/SpringFixture.java:40",
        }
        row.update(changes)
        return row

    def _candidate(self, **changes: object) -> GrowthCandidate:
        return GrowthCandidate.from_raw(self._raw(**changes))

    def _excerpt(self, excerpt_id: str = "excerpt:growth") -> SourceExcerpt:
        content = "registry.put(key, value);\n"
        return SourceExcerpt(
            excerpt_id,
            "fixture/spring/SpringFixture.java",
            35,
            45,
            content,
            "b" * 64,
            hashlib.sha256(content.encode()).hexdigest(),
        )

    def _slice(self, candidate: GrowthCandidate, *, facts: tuple[StaticFact, ...] | None = None) -> BoundedSlice:
        excerpt = self._excerpt()
        facts = facts or (
            StaticFact("fact:source", "flow", excerpt.excerpt_id, "source", None, "request_body"),
            StaticFact("fact:sink", "container_write", excerpt.excerpt_id, "sink", "fact:source"),
            StaticFact("fact:value-space", "value_space", excerpt.excerpt_id, "flows_to", "fact:source", "unlimited"),
            StaticFact("fact:retention", "retention", excerpt.excerpt_id, "sink", None, "process"),
            StaticFact("fact:amplification", "amplification", excerpt.excerpt_id, "sink", None, "high_cardinality_retention"),
            *(StaticFact(fact_id, "container_write", excerpt.excerpt_id, "sink") for fact_id in sorted(candidate.evidence_ids)),
        )
        return build_bounded_slice(
            entry_id="entry:fixture",
            candidate=candidate,
            source_excerpts=(excerpt,),
            static_facts=facts,
            cfg_summary=CfgSummary(("path:growth",), ("in_handler",), tuple(f.fact_id for f in facts)),
            registration_facts=(RegistrationFact("spring_mvc", excerpt.excerpt_id),),
            config_facts=(),
        )

    def _contract(self, **changes: object) -> GrowthContract:
        values: dict[str, object] = {
            "is_resource_growth": "yes",
            "growth_kind": "container_growth",
            "resource_dimension": "entries",
            "attacker_influence": (AttackerInfluence("key", "fact:source"),),
            "resource_effect": "adds_entries",
            "attacker_variable": "key",
            "attacker_value_space": "unlimited",
            "growth_unit": "one map entry",
            "growth_function": "distinct keys add retained entries",
            "amplification_class": "high_cardinality_retention",
            "requests_to_pressure": "many",
            "concurrency_model": "repeatable requests",
            "retention_window": "process",
            "failure_mechanism": "heap_exhaustion",
            "failure_signal": "retained entries exhaust heap",
            "required_static_evidence": ("fact:sink", "fact:value-space", "fact:retention", "fact:amplification"),
            "contract_status": "dos_relevant",
            "rejection_reason": "none",
            "confidence": "high",
        }
        values.update(changes)
        return GrowthContract(**values)

    def test_normalizes_g1_through_g4_and_matches_artifact_schema(self) -> None:
        cases = (
            ("input_materialization", "bytes", "value", "request"),
            ("direct_allocation", "bytes", "size", "request"),
            ("container_growth", "entries", "key", "instance"),
            ("async_work_growth", "tasks", "submission_count", "global"),
        )
        records = []
        for index, (kind, dimension, role, scope) in enumerate(cases, start=1):
            with self.subTest(kind=kind):
                candidate = self._candidate(
                    site_start_line=40 + index,
                    growth_kind=kind,
                    resource_dimension=dimension,
                    demand_input_role=role,
                    escape_scope=scope,
                    operation=f"fixture.{kind}",
                )
                self.assertEqual(candidate.kind, kind)
                self.assertEqual(candidate.resource_dimension, dimension)
                self.assertEqual(candidate.demand_inputs[0].role, role)
                records.append(candidate.to_dict())
        validate_records("growth_candidates", records)

    def test_normalization_merges_demand_inputs_and_is_row_order_independent(self) -> None:
        key = self._raw()
        value = self._raw(demand_input_name="value", demand_input_role="value", candidate_evidence="map_value")
        left = normalize_growth_rows((key, value, key))
        right = normalize_growth_rows((value, key))
        self.assertEqual(left, right)
        self.assertEqual([item["role"] for item in left[0]["demand_inputs"]], ["key", "value"])
        self.assertEqual(len(left[0]["candidate_evidence"]), 2)
        self.assertEqual(left[0]["coverage_status"], "complete")
        self.assertEqual(left[0]["coverage_notes"], ["persistent_map_insertion"])

    def test_partial_coverage_is_preserved_conservatively_and_cannot_verify(self) -> None:
        complete = self._raw()
        partial = self._raw(
            candidate_evidence="map_value",
            coverage_status="partial",
            coverage_note="receiver_capacity_requires_contract",
        )
        candidate = GrowthCandidate.from_raw(partial)
        self.assertEqual(candidate.coverage_status, "partial")
        self.assertEqual(candidate.coverage_notes, ("receiver_capacity_requires_contract",))

        merged = normalize_growth_rows((complete, partial))
        self.assertEqual(merged[0]["coverage_status"], "partial")
        self.assertEqual(
            merged[0]["coverage_notes"],
            ["persistent_map_insertion", "receiver_capacity_requires_contract"],
        )

        slice_ = self._slice(candidate)
        index = {fact.fact_id: fact for fact in slice_.payload.static_facts}
        result = verify_growth_contract(candidate, slice_, self._contract(), index)
        self.assertEqual(result.status, "unresolved")
        self.assertIn("GROWTH_COVERAGE_INCOMPLETE", result.reason_codes)

    def test_slice_id_is_stable_under_related_fact_ordering(self) -> None:
        candidate = self._candidate()
        excerpt = self._excerpt()
        source = StaticFact("fact:source", "flow", excerpt.excerpt_id, "source")
        sink = StaticFact("fact:sink", "container_write", excerpt.excerpt_id, "sink", source.fact_id)
        evidence = tuple(
            StaticFact(fact_id, "container_write", excerpt.excerpt_id, "sink")
            for fact_id in sorted(candidate.evidence_ids)
        )
        left = self._slice(candidate, facts=(source, sink, *evidence))
        right = self._slice(candidate, facts=(*reversed(evidence), sink, source))
        self.assertEqual(left.slice_id, right.slice_id)
        self.assertEqual(
            tuple(f.fact_id for f in left.payload.static_facts),
            tuple(sorted(f.fact_id for f in left.payload.static_facts)),
        )
        self.assertIn("fact:sink", {f.fact_id for f in left.payload.static_facts})
        self.assertIn("fact:source", {f.fact_id for f in left.payload.static_facts})

    def test_negative_and_unknown_status_short_circuit_before_mismatch_checks(self) -> None:
        candidate = self._candidate()
        slice_ = self._slice(candidate)
        index = {fact.fact_id: fact for fact in slice_.payload.static_facts}
        rejected = verify_growth_contract(
            candidate,
            slice_,
            self._contract(
                is_resource_growth="no",
                contract_status="growth_not_dos_relevant",
                rejection_reason="no_failure_mechanism",
                growth_kind="direct_allocation",
            ),
            index,
        )
        unresolved = verify_growth_contract(
            candidate,
            slice_,
            self._contract(
                is_resource_growth="unknown",
                contract_status="unknown",
                rejection_reason="unknown",
                resource_dimension="bytes",
            ),
            index,
        )
        self.assertEqual(
            (rejected.status, rejected.reason_codes),
            ("rejected", ("GROWTH_NOT_DOS_RELEVANT",)),
        )
        self.assertEqual(
            (unresolved.status, unresolved.reason_codes),
            ("unresolved", ("GROWTH_DOS_RELEVANCE_UNKNOWN",)),
        )

    def test_mismatches_and_unmapped_evidence_are_unresolved(self) -> None:
        candidate = self._candidate()
        slice_ = self._slice(candidate)
        index = {fact.fact_id: fact for fact in slice_.payload.static_facts}
        cases = (
            (self._contract(growth_kind="direct_allocation"), "GROWTH_KIND_MISMATCH"),
            (self._contract(resource_dimension="bytes"), "GROWTH_DIMENSION_MISMATCH"),
            (self._contract(required_static_evidence=("fact:missing",)), "GROWTH_UNMAPPED_REQUIRED_EVIDENCE"),
            (
                self._contract(attacker_influence=(AttackerInfluence("size", "fact:source"),)),
                "GROWTH_UNMAPPED_ATTACKER_INFLUENCE",
            ),
        )
        for contract, reason in cases:
            with self.subTest(reason=reason):
                result = verify_growth_contract(candidate, slice_, contract, index)
                self.assertEqual(result.status, "unresolved")
                self.assertIn(reason, result.reason_codes)

    def test_sink_only_candidate_evidence_cannot_prove_attacker_influence(self) -> None:
        candidate = self._candidate()
        slice_ = self._slice(candidate)
        index = {fact.fact_id: fact for fact in slice_.payload.static_facts}
        result = verify_growth_contract(
            candidate,
            slice_,
            self._contract(attacker_influence=(AttackerInfluence("key", "fact:sink"),)),
            index,
        )
        self.assertEqual(result.status, "unresolved")
        self.assertIn("GROWTH_UNMAPPED_ATTACKER_INFLUENCE", result.reason_codes)

    def test_evidence_location_outside_slice_is_unresolved(self) -> None:
        candidate = self._candidate()
        slice_ = self._slice(candidate)
        outside = StaticFact("fact:sink", "container_write", "excerpt:outside", "sink")
        index = {**{fact.fact_id: fact for fact in slice_.payload.static_facts}, outside.fact_id: outside}
        result = verify_growth_contract(candidate, slice_, self._contract(), index)
        self.assertEqual(result.status, "unresolved")
        self.assertIn("GROWTH_LOCATION_OUTSIDE_SLICE", result.reason_codes)

    def test_candidate_rejects_invalid_direct_scope_and_evidence(self) -> None:
        candidate = self._candidate()
        for changes in (
            {"escape_scope": "invalid"},
            {"evidence_ids": frozenset({"fact:bad space"})},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(Exception) as raised:
                    GrowthCandidate(**{**candidate.__dict__, **changes})
                self.assertEqual(getattr(raised.exception, "code", None), "ANALYSIS_GROWTH_INVALID")

    def test_slice_rejects_missing_candidate_evidence_instead_of_fabricating_it(self) -> None:
        candidate = self._candidate()
        excerpt = self._excerpt()
        source = StaticFact("fact:source", "flow", excerpt.excerpt_id, "source")
        with self.assertRaises(Exception) as raised:
            build_bounded_slice(
                entry_id="entry:fixture",
                candidate=candidate,
                source_excerpts=(excerpt,),
                static_facts=(source,),
                cfg_summary=CfgSummary(("path:growth",), ("in_handler",), (source.fact_id,)),
                registration_facts=(RegistrationFact("spring_mvc", excerpt.excerpt_id),),
                config_facts=(),
            )
        self.assertEqual(getattr(raised.exception, "code", None), "ANALYSIS_GROWTH_INVALID")

    def test_verifier_rejects_empty_evidence_and_same_id_semantic_mismatch(self) -> None:
        candidate = self._candidate()
        slice_ = self._slice(candidate)
        index = {fact.fact_id: fact for fact in slice_.payload.static_facts}
        empty = self._contract(attacker_influence=(), required_static_evidence=())
        result = verify_growth_contract(candidate, slice_, empty, index)
        self.assertEqual(result.status, "unresolved")
        self.assertIn("GROWTH_UNMAPPED_REQUIRED_EVIDENCE", result.reason_codes)

        mismatched = dict(index)
        mismatched["fact:source"] = StaticFact(
            "fact:source", "flow", "excerpt:growth", "source", "fact:sink"
        )
        result = verify_growth_contract(candidate, slice_, self._contract(), mismatched)
        self.assertEqual(result.status, "unresolved")
        self.assertIn("GROWTH_UNMAPPED_REQUIRED_EVIDENCE", result.reason_codes)

    def test_all_static_mappings_verify_with_confidence_independent_id(self) -> None:
        candidate = self._candidate()
        slice_ = self._slice(candidate)
        index = {fact.fact_id: fact for fact in slice_.payload.static_facts}
        results = [
            verify_growth_contract(candidate, slice_, self._contract(confidence=confidence), index)
            for confidence in ("high", "medium", "low")
        ]
        self.assertEqual({result.status for result in results}, {"verified"})
        self.assertEqual(len({result.verified_growth_id for result in results}), 1)
        self.assertTrue(results[0].verified_growth_id.startswith("verified_growth:"))
        self.assertTrue(all(result.checks for result in results))
        for result in results:
            validate_records("verified_growth", [result.to_dict()])

    def test_dos_contract_status_failure_pressure_and_semantic_citations_gate_verification(self) -> None:
        candidate = self._candidate()
        slice_ = self._slice(candidate)
        index = {fact.fact_id: fact for fact in slice_.payload.static_facts}
        cases = (
            (
                self._contract(
                    contract_status="growth_not_dos_relevant",
                    rejection_reason="low_amplification",
                    amplification_class="low_amplification",
                    failure_mechanism="none",
                ),
                "rejected",
                "GROWTH_NOT_DOS_RELEVANT",
            ),
            (
                self._contract(
                    is_resource_growth="unknown",
                    contract_status="unknown",
                    rejection_reason="unknown",
                ),
                "unresolved",
                "GROWTH_DOS_RELEVANCE_UNKNOWN",
            ),
            (
                self._contract(failure_mechanism="none"),
                "unresolved",
                "GROWTH_FAILURE_MECHANISM_UNPROVEN",
            ),
            (
                self._contract(requests_to_pressure="implausible"),
                "unresolved",
                "GROWTH_PRESSURE_IMPLAUSIBLE",
            ),
            (
                self._contract(required_static_evidence=("fact:sink", "fact:value-space", "fact:amplification")),
                "unresolved",
                "GROWTH_RETENTION_EVIDENCE_UNMAPPED",
            ),
            (
                self._contract(required_static_evidence=("fact:sink", "fact:value-space", "fact:retention")),
                "unresolved",
                "GROWTH_AMPLIFICATION_EVIDENCE_UNMAPPED",
            ),
            (
                self._contract(retention_window="session"),
                "unresolved",
                "GROWTH_RETENTION_EVIDENCE_UNMAPPED",
            ),
        )
        for contract, status, reason in cases:
            with self.subTest(reason=reason):
                result = verify_growth_contract(candidate, slice_, contract, index)
                self.assertEqual(result.status, status)
                self.assertIn(reason, result.reason_codes)


if __name__ == "__main__":
    unittest.main()
