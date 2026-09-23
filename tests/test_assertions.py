from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from dosweb.conclude import (
    AssertionEvaluation,
    CandidateCoverage,
    VerdictProofGate,
    apply_positive_proof_gate,
    derive_verdict,
    evaluate_assertion_1,
    evaluate_assertion_2,
)
from dosweb.flows import AttackerControl, FlowProof, verify_flow
from dosweb.growth import DemandInput, GrowthCandidate, VerificationCheck, VerifiedGrowthResult
from dosweb.lifecycle import BoundDecision, DecisionCheck, GuardDecision, ReleaseDecision
from dosweb.lifecycle.resource_properties import ResourceLifecycleDecision
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
            supported_patterns=(self.entry.registration_pattern_id,),
            unsupported_patterns=(),
            effect_on_verdict="none",
            registration_pattern_id=self.entry.registration_pattern_id,
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

    def test_resource_task_population_refutes_only_a2_and_preserves_property_scope(self) -> None:
        growth, flow = self._persistent_context("submission_count")
        candidate = GrowthCandidate.create(
            site=growth.candidate.site,
            kind="async_work_growth",
            operation="executor.execute(task)",
            resource_dimension="tasks",
            receiver="executor",
            field_path="executor",
            demand_inputs=(DemandInput("count", "submission_count"),),
            escape_scope="instance",
            evidence_ids=frozenset({"fact:async"}),
        )
        growth = VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id="slice:async",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        proof = FlowProof.create(
            entry_id=self.entry.entry_id,
            growth_id=growth.growth_id,
            attacker_control=AttackerControl(
                "submission_count", "limit", "count"
            ),
            call_path=(self.entry.handler.callable,),
            phase_sequence=("in_handler", "growth"),
            confidence="proven",
        )
        flow = verify_flow(
            proof,
            {self.entry.entry_id: self.entry},
            {growth.growth_id: growth},
        )
        bounded = ResourceLifecycleDecision.create(
            status="refutes_relevant_growth",
            reason_codes=(
                "RESOURCE_PROPERTY_ACCEPTED_TASK_POPULATION_BOUNDED",
            ),
            evidence_ids=("resource-binding:fixture", "property:fixture"),
            unresolved_facts=(),
            binding_id="resource-binding:fixture",
            property_id="property:fixture",
            result_sha256="a" * 64,
            dimension="accepted_task_population",
            scope="executor:executor",
            cut="arbitrary_finite_repetitions",
            upper_bound=5,
            assumptions=(
                "q counts accepted tasks in the modeled executor queue",
                "proof is inductive for arbitrary finite repetitions, not one unrolling",
            ),
            entry_id=self.entry.entry_id,
            growth_id=growth.growth_id,
            path_id=flow.path_id,
        )
        result = evaluate_assertion_2(
            growth,
            flow,
            self.no_bound,
            self.no_release,
            resource_lifecycle=bounded,
        )
        self.assertEqual("refuted", result.status)
        self.assertEqual(("A2_BOUNDED_ACCEPTED_TASK_POPULATION",), result.reason_codes)
        self.assertIn(bounded.decision_id, result.evidence_ids)
        assertion_1 = evaluate_assertion_1(
            growth,
            flow,
            self.no_guard,
            self.no_bound,
            amplification=SimpleNamespace(status="proven"),
            resource_lifecycle=bounded,
        )
        self.assertEqual("refuted", assertion_1.status)
        self.assertEqual(
            ("A1_BOUNDED_ACCEPTED_TASK_POPULATION",),
            assertion_1.reason_codes,
        )

        unresolved = ResourceLifecycleDecision.create(
            status="unresolved",
            reason_codes=("RESOURCE_PROPERTY_TASK_POPULATION_UNRESOLVED",),
            evidence_ids=("resource-binding:unknown",),
            unresolved_facts=("RESOURCE_PROPERTY_TASK_POPULATION_UNRESOLVED",),
            binding_id="resource-binding:unknown",
            property_id=None,
            result_sha256="b" * 64,
            dimension=None,
            scope=None,
            cut=None,
            upper_bound=None,
            assumptions=(),
            entry_id=self.entry.entry_id,
            growth_id=growth.growth_id,
            path_id=flow.path_id,
        )
        unknown = evaluate_assertion_2(
            growth,
            flow,
            self.no_bound,
            self.no_release,
            resource_lifecycle=unresolved,
        )
        self.assertEqual("unknown", unknown.status)
        self.assertEqual(("A2_RESOURCE_LIFECYCLE_UNKNOWN",), unknown.reason_codes)

    def test_derive_verdict_uses_only_deterministic_assertion_status(self) -> None:
        matched = evaluate_assertion_1(self.growth, self.flow, self.no_guard, self.no_bound)
        not_applicable = evaluate_assertion_2(self.growth, self.flow, self.no_bound, self.no_release)
        verdict = derive_verdict((matched, not_applicable), self.coverage)
        self.assertEqual(verdict.verdict, "static_vulnerable")
        self.assertNotIn("safe", verdict.verdict)
        self.assertEqual(verdict.covered_entries, (self.entry.entry_id,))
        self.assertEqual(verdict.covered_paths, (self.flow.path_id,))

    def test_positive_proof_gate_preserves_only_fully_proven_vulnerability(self) -> None:
        matched = evaluate_assertion_1(self.growth, self.flow, self.no_guard, self.no_bound)
        not_applicable = evaluate_assertion_2(
            self.growth, self.flow, self.no_bound, self.no_release
        )
        verdict = derive_verdict((matched, not_applicable), self.coverage)
        gate = VerdictProofGate(
            entry_complete=True,
            ordinary_reachability=True,
            growth_verified=True,
            flow_proven=True,
            assertion_1_lifecycle_complete=True,
            assertion_2_lifecycle_complete=True,
            candidate_relevant_gap_free=True,
        )

        self.assertEqual(apply_positive_proof_gate(verdict, gate), verdict)

    def test_positive_proof_gate_downgrades_each_missing_obligation_with_exact_reason(self) -> None:
        matched = evaluate_assertion_1(self.growth, self.flow, self.no_guard, self.no_bound)
        not_applicable = evaluate_assertion_2(
            self.growth, self.flow, self.no_bound, self.no_release
        )
        verdict = derive_verdict((matched, not_applicable), self.coverage)
        complete = VerdictProofGate(True, True, True, True, True, True, True)
        reasons = {
            "entry_complete": "VERDICT_ENTRY_COVERAGE_INCOMPLETE",
            "ordinary_reachability": "VERDICT_REACHABILITY_NOT_PROVEN",
            "growth_verified": "VERDICT_GROWTH_NOT_VERIFIED",
            "flow_proven": "VERDICT_FLOW_NOT_PROVEN",
            "assertion_1_lifecycle_complete": "VERDICT_ASSERTION_1_LIFECYCLE_COVERAGE_INCOMPLETE",
            "assertion_2_lifecycle_complete": "VERDICT_ASSERTION_2_LIFECYCLE_COVERAGE_INCOMPLETE",
            "candidate_relevant_gap_free": "VERDICT_CANDIDATE_RELEVANT_GAP",
        }

        for field, reason in reasons.items():
            with self.subTest(field=field):
                gated = apply_positive_proof_gate(
                    verdict,
                    replace(complete, **{field: False}),
                )
                self.assertEqual(gated.verdict, "static_unknown")
                self.assertIn(reason, gated.reason_codes)

    def test_positive_proof_gate_downgrades_bounded_candidate_gap(self) -> None:
        guard = GuardDecision(
            "effective", (), (), ("fact:guard",), (), ("guard:one",)
        )
        bounded = derive_verdict(
            (
                evaluate_assertion_1(self.growth, self.flow, guard, self.no_bound),
                self.no_release_assertion(),
            ),
            self.coverage,
        )
        gate = VerdictProofGate(True, True, True, True, True, True, False)

        gated = apply_positive_proof_gate(bounded, gate)

        self.assertEqual("static_unknown", gated.verdict)
        self.assertEqual(
            ("VERDICT_CANDIDATE_RELEVANT_GAP",),
            tuple(sorted(set(gated.reason_codes) - set(bounded.reason_codes))),
        )
        self.assertNotIn("STATIC_EVIDENCE_COVERAGE_COMPLETE", gated.assumptions)
        self.assertIn("MODELED_DEFAULT_CONFIGURATION", gated.assumptions)
        self.assertEqual(bounded.modeled_configuration_refs, gated.modeled_configuration_refs)

    def test_positive_proof_gate_downgrades_bounded_applicable_lifecycle_gap(self) -> None:
        guard = GuardDecision(
            "effective", (), (), ("fact:guard",), (), ("guard:one",)
        )
        bounded = derive_verdict(
            (
                evaluate_assertion_1(self.growth, self.flow, guard, self.no_bound),
                self.no_release_assertion(),
            ),
            self.coverage,
        )
        gate = VerdictProofGate(True, True, True, True, False, True, True)

        gated = apply_positive_proof_gate(bounded, gate)

        self.assertEqual("static_unknown", gated.verdict)
        self.assertEqual(
            ("VERDICT_ASSERTION_1_LIFECYCLE_COVERAGE_INCOMPLETE",),
            tuple(sorted(set(gated.reason_codes) - set(bounded.reason_codes))),
        )
        self.assertNotIn("STATIC_EVIDENCE_COVERAGE_COMPLETE", gated.assumptions)
        self.assertIn("MODELED_DEFAULT_CONFIGURATION", gated.assumptions)
        self.assertEqual(bounded.modeled_configuration_refs, gated.modeled_configuration_refs)

    def test_positive_proof_gate_downgrades_bounded_with_all_missing_reasons(self) -> None:
        guard = GuardDecision(
            "effective", (), (), ("fact:guard",), (), ("guard:one",)
        )
        bounded = derive_verdict(
            (
                evaluate_assertion_1(self.growth, self.flow, guard, self.no_bound),
                self.no_release_assertion(),
            ),
            self.coverage,
        )
        gate = VerdictProofGate(False, False, False, False, False, False, False)

        gated = apply_positive_proof_gate(bounded, gate)

        self.assertEqual("static_unknown", gated.verdict)
        self.assertEqual(
            gate.missing_reason_codes,
            tuple(sorted(set(gated.reason_codes) - set(bounded.reason_codes))),
        )

    def test_positive_proof_gate_keeps_unknown_and_records_missing_reasons(self) -> None:
        matched = evaluate_assertion_1(
            self.growth, self.flow, self.no_guard, self.no_bound
        )
        unknown = AssertionEvaluation(
            "assertion_2",
            "unknown",
            ("A2_RELEASE_UNKNOWN",),
            tuple(sorted((self.entry.entry_id, self.growth.growth_id, self.flow.path_id))),
            ("release",),
        )
        verdict = derive_verdict((matched, unknown), self.coverage)
        gate = VerdictProofGate(True, True, True, True, True, False, True)

        gated = apply_positive_proof_gate(verdict, gate)

        self.assertEqual("static_unknown", gated.verdict)
        self.assertIn(
            "VERDICT_ASSERTION_2_LIFECYCLE_COVERAGE_INCOMPLETE",
            gated.reason_codes,
        )
        self.assertNotIn("STATIC_EVIDENCE_COVERAGE_COMPLETE", gated.assumptions)

    def test_coverage_gap_or_unknown_evidence_forces_static_unknown(self) -> None:
        matched = evaluate_assertion_1(self.growth, self.flow, self.no_guard, self.no_bound)
        gap = CandidateCoverage(
            framework=self.entry.framework,
            status="partial",
            supported_patterns=(),
            unsupported_patterns=("dynamic_registration",),
            effect_on_verdict="forces_unknown",
            registration_pattern_id=self.entry.registration_pattern_id,
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
            registration_pattern_id=self.entry.registration_pattern_id,
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
                supported_patterns=(self.entry.registration_pattern_id,), unsupported_patterns=(),
                effect_on_verdict="none",
                registration_pattern_id=self.entry.registration_pattern_id,
                **{field: value},
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
