from __future__ import annotations

import unittest

from dosweb.conclude import (
    AssertionEvaluation,
    CandidateCoverage,
    derive_verdict,
    evaluate_assertion_1,
    evaluate_assertion_2,
)
from dosweb.flows import AttackerControl, FlowProof, verify_flow
from dosweb.growth import DemandInput, GrowthCandidate, VerificationCheck, VerifiedGrowthResult
from dosweb.lifecycle import BoundDecision, DecisionCheck, GuardDecision, ReleaseDecision
from tests.test_flow_verification import FlowVerificationTests


class AssertionTests(unittest.TestCase):
    def setUp(self) -> None:
        helper = FlowVerificationTests()
        self.entry = helper._entry()
        self.growth = helper._growth()
        record = helper._raw()
        from dosweb.flows import FlowProof, normalize_flow_rows, verify_flow

        proof = FlowProof.from_dict(
            normalize_flow_rows(
                (record,),
                {self.entry.entry_id: self.entry},
                {self.growth.growth_id: self.growth},
            )[0]
        )
        self.flow = verify_flow(
            proof,
            {self.entry.entry_id: self.entry},
            {self.growth.growth_id: self.growth},
        )
        self.no_guard = GuardDecision("ineffective", ("GUARD_ABSENT",), (), (), (), ())
        self.no_bound = BoundDecision("absent", ("BOUND_ABSENT",), (), (), (), ())
        self.no_release = ReleaseDecision("absent", "absent", ("RELEASE_ABSENT",), (), (), (), ())
        self.coverage = CandidateCoverage(
            framework=self.entry.framework,
            status="complete",
            supported_patterns=(self.entry.registration.kind,),
            unsupported_patterns=(),
            effect_on_verdict="none",
            registration_pattern=self.entry.registration.kind,
            entry_id=self.entry.entry_id,
            growth_id=self.growth.growth_id,
            path_id=self.flow.path_id,
        )

    def test_assertion_1_matches_proven_unbounded_growth(self) -> None:
        result = evaluate_assertion_1(self.growth, self.flow, self.no_guard, self.no_bound)
        self.assertEqual(result, AssertionEvaluation(
            "assertion_1", "matched",
            ("A1_FLOW_PROVEN", "A1_GROWTH_VERIFIED", "A1_NO_EFFECTIVE_BOUND", "A1_NO_EFFECTIVE_GUARD"),
            result.evidence_ids,
            (),
        ))

    def test_assertion_1_is_refuted_by_effective_guard_or_bound(self) -> None:
        guard = GuardDecision("effective", (), (DecisionCheck("guard_effective", True),), ("fact:guard",), (), ("guard:one",))
        bound = BoundDecision("effective", (), (DecisionCheck("bound_effective", True),), ("fact:bound",), (), ("bound:one",))
        self.assertEqual(evaluate_assertion_1(self.growth, self.flow, guard, self.no_bound).status, "refuted")
        self.assertEqual(evaluate_assertion_1(self.growth, self.flow, self.no_guard, bound).status, "refuted")

    def test_assertion_1_unknown_growth_or_configuration_stays_unknown(self) -> None:
        unresolved_growth = FlowVerificationTests()._growth("unresolved")
        from dosweb.flows import FlowProof, normalize_flow_rows, verify_flow

        record = FlowVerificationTests()._raw()
        proof = FlowProof.from_dict(
            normalize_flow_rows(
                (record,),
                {self.entry.entry_id: self.entry},
                {unresolved_growth.growth_id: unresolved_growth},
            )[0]
        )
        unresolved_flow = verify_flow(
            proof,
            {self.entry.entry_id: self.entry},
            {unresolved_growth.growth_id: unresolved_growth},
        )
        self.assertEqual(
            evaluate_assertion_1(unresolved_growth, unresolved_flow, self.no_guard, self.no_bound).status,
            "unknown",
        )
        unknown_bound = BoundDecision("unknown", ("BOUND_CONFIGURATION_UNKNOWN",), (), (), ("queue.capacity",), ("bound:one",))
        self.assertEqual(evaluate_assertion_1(self.growth, self.flow, self.no_guard, unknown_bound).status, "unknown")

    def test_assertion_2_requires_persistent_attacker_demand_and_escaping_scope(self) -> None:
        result = evaluate_assertion_2(self.growth, self.flow, self.no_bound, self.no_release)
        self.assertEqual(result.status, "not_applicable")
        self.assertIn("A2_NONPERSISTENT_DEMAND", result.reason_codes)

    def _persistent_context(self, target: str = "key"):
        candidate = GrowthCandidate.create(
            site=self.growth.candidate.site,
            kind="container_growth",
            operation="Map.put",
            resource_dimension="entries",
            receiver="cache",
            field_path="entries",
            demand_inputs=(DemandInput("attackerKey", target),),
            escape_scope="global",
            evidence_ids=frozenset({"fact:persistent"}),
        )
        growth = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:persistent",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        proof = FlowProof.create(
            entry_id=self.entry.entry_id,
            growth_id=growth.growth_id,
            attacker_control=AttackerControl(target, "limit", "put(attackerKey)"),
            call_path=(self.entry.handler.callable,),
            phase_sequence=("in_handler", "growth"),
            confidence="proven",
        )
        flow = verify_flow(proof, {self.entry.entry_id: self.entry}, {growth.growth_id: growth})
        return growth, flow

    def test_assertion_2_does_not_treat_iteration_count_as_persistent_identity(self) -> None:
        growth, flow = self._persistent_context("iteration_count")
        result = evaluate_assertion_2(growth, flow, self.no_bound, self.no_release)
        self.assertEqual(result.status, "not_applicable")
        self.assertIn("A2_NONPERSISTENT_DEMAND", result.reason_codes)

    def test_effective_bound_refutes_a2_before_potential_async_release_unknown(self) -> None:
        growth, flow = self._persistent_context()
        bound = BoundDecision("effective", (), (), ("fact:bound",), (), ("bound:one",))
        release = ReleaseDecision(
            "unknown", "potential_async", ("RELEASE_POTENTIAL_ASYNC",), (),
            ("fact:release",), ("worker",), ("release:one",),
        )
        result = evaluate_assertion_2(growth, flow, bound, release)
        self.assertEqual(result.status, "refuted")
        self.assertEqual(result.reason_codes, ("A2_EFFECTIVE_BOUND",))

    def test_derive_verdict_uses_only_deterministic_assertion_status(self) -> None:
        matched = evaluate_assertion_1(self.growth, self.flow, self.no_guard, self.no_bound)
        not_applicable = evaluate_assertion_2(self.growth, self.flow, self.no_bound, self.no_release)
        verdict = derive_verdict((matched, not_applicable), self.coverage)
        self.assertEqual(verdict.verdict, "static_vulnerable")
        self.assertNotIn("safe", verdict.verdict)
        self.assertEqual(verdict.covered_entries, (self.entry.entry_id,))
        self.assertEqual(verdict.covered_paths, (self.flow.path_id,))

    def test_coverage_gap_or_unknown_evidence_forces_static_unknown(self) -> None:
        matched = evaluate_assertion_1(self.growth, self.flow, self.no_guard, self.no_bound)
        gap = CandidateCoverage(
            framework=self.entry.framework,
            status="partial",
            supported_patterns=(),
            unsupported_patterns=("dynamic_registration",),
            effect_on_verdict="forces_unknown",
            registration_pattern=self.entry.registration.kind,
            entry_id=self.entry.entry_id,
            growth_id=self.growth.growth_id,
            path_id=self.flow.path_id,
        )
        self.assertEqual(derive_verdict((matched,), gap).verdict, "static_unknown")
        unknown = AssertionEvaluation("assertion_2", "unknown", ("A2_RELEASE_UNKNOWN",), ("flow:" + self.flow.path_id.removeprefix("flow:"),), ("release",))
        self.assertEqual(derive_verdict((matched, unknown), self.coverage).verdict, "static_unknown")

    def test_candidate_coverage_rejects_overlapping_pattern_sets(self) -> None:
        with self.assertRaises(Exception):
            CandidateCoverage(
                framework=self.entry.framework,
                status="partial",
                supported_patterns=("overlap",),
                unsupported_patterns=("overlap",),
                effect_on_verdict="forces_unknown",
            )

    def test_scoped_coverage_rejects_omitted_candidate_scope(self) -> None:
        self.assertFalse(self.coverage.relevant_to(
            framework=self.entry.framework,
            registration_pattern=self.entry.registration.kind,
            entry_id=self.entry.entry_id,
            growth_id=self.growth.growth_id,
            path_id=None,
        ))

    def test_verdict_validates_assertions_before_access_and_each_coverage_scope(self) -> None:
        with self.assertRaises(Exception):
            derive_verdict((object(),), self.coverage)
        matched = evaluate_assertion_1(self.growth, self.flow, self.no_guard, self.no_bound)
        for field, value in (
            ("entry_id", "entry:other"),
            ("growth_id", "growth:other"),
            ("path_id", "flow:other"),
        ):
            scoped = CandidateCoverage(
                framework=self.entry.framework, status="complete",
                supported_patterns=(self.entry.registration.kind,), unsupported_patterns=(),
                effect_on_verdict="none", **{field: value},
            )
            with self.subTest(field=field), self.assertRaises(Exception):
                derive_verdict((matched,), scoped)

    def test_not_applicable_unresolved_facts_do_not_force_unknown(self) -> None:
        matched = evaluate_assertion_1(self.growth, self.flow, self.no_guard, self.no_bound)
        irrelevant = AssertionEvaluation(
            "assertion_2", "not_applicable", ("A2_NONPERSISTENT_DEMAND",),
            tuple(sorted((self.entry.entry_id, self.growth.growth_id, self.flow.path_id))),
            ("irrelevant_release_fact",),
        )
        self.assertEqual(derive_verdict((matched, irrelevant), self.coverage).verdict, "static_vulnerable")

    def test_all_applicable_assertions_refuted_are_bounded(self) -> None:
        guard = GuardDecision("effective", (), (), ("fact:guard",), (), ("guard:one",))
        refuted = evaluate_assertion_1(self.growth, self.flow, guard, self.no_bound)
        verdict = derive_verdict((refuted, self.no_release_assertion()), self.coverage)
        self.assertEqual(verdict.verdict, "bounded_under_modeled_assumptions")
        self.assertTrue(verdict.assumptions)
        self.assertTrue(verdict.reason_codes)

    def no_release_assertion(self) -> AssertionEvaluation:
        return AssertionEvaluation(
            "assertion_2", "not_applicable", ("A2_NONPERSISTENT_DEMAND",),
            tuple(sorted((self.growth.growth_id, self.flow.path_id))), (),
        )


if __name__ == "__main__":
    unittest.main()
