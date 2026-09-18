from __future__ import annotations

import unittest
from dataclasses import replace

from dosweb.errors import AnalyzerError

from dosweb.conclude import (
    AssertionEvaluation,
    CandidateCoverage,
    VerdictProofGate,
    apply_positive_proof_gate,
    derive_verdict,
    evaluate_assertion_1,
    evaluate_assertion_2,
)
from dosweb.flows import FlowProof, normalize_flow_rows, verify_flow
from dosweb.lifecycle import BoundDecision, GuardDecision, ReleaseDecision
from dosweb.lifecycle.certificates import (
    LifecycleCertificate,
    StaticFinding,
    build_lifecycle_certificate,
)
from dosweb.report import build_finding_families, build_summary, render_report
from tests.test_flow_verification import FlowVerificationTests


class CertificateReportTests(unittest.TestCase):
    def setUp(self) -> None:
        helper = FlowVerificationTests()
        self.entry = helper._entry()
        self.growth = helper._growth()
        proof = FlowProof.from_dict(
            normalize_flow_rows(
                (helper._raw(),),
                {self.entry.entry_id: self.entry},
                {self.growth.growth_id: self.growth},
            )[0]
        )
        self.flow = verify_flow(
            proof,
            {self.entry.entry_id: self.entry},
            {self.growth.growth_id: self.growth},
        )
        self.guard = GuardDecision("ineffective", ("GUARD_ABSENT",), (), (), (), ())
        self.bound = BoundDecision("absent", ("BOUND_ABSENT",), (), (), (), ())
        self.release = ReleaseDecision("absent", "absent", ("RELEASE_ABSENT",), (), (), (), ())
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

    def _certificate(self):
        assertions = (
            evaluate_assertion_1(self.growth, self.flow, self.guard, self.bound),
            evaluate_assertion_2(self.growth, self.flow, self.bound, self.release),
        )
        verdict = derive_verdict(assertions, self.coverage)
        return build_lifecycle_certificate(
            self.entry, self.growth, (self.flow,), self.guard, self.bound,
            self.release, assertions, self.coverage, verdict,
        )

    def test_certificate_is_complete_and_finding_only_references_it(self) -> None:
        certificate = self._certificate()
        record = certificate.to_dict()
        for field in (
            "entry_id", "growth_id", "attacker_inputs", "resource_point", "path_ids",
            "guard_decision", "bound_decision", "release_decision", "assertions",
            "verdict", "reason_codes", "assumptions", "coverage_gaps", "unresolved_facts",
            "suggested_follow_up_measurements",
        ):
            self.assertIn(field, record)
        finding = StaticFinding.from_certificate(certificate)
        self.assertEqual(finding.certificate_id, certificate.certificate_id)
        self.assertEqual(finding.verdict, certificate.verdict)
        self.assertEqual(finding.to_dict()["reason_codes"], record["reason_codes"])

    def test_framework_coverage_rejects_overlapping_pattern_sets(self) -> None:
        from dosweb.entries import FrameworkCoverage

        with self.assertRaises(AnalyzerError):
            FrameworkCoverage(
                self.entry.framework,
                "partial",
                ("overlap",),
                ("overlap",),
                "forces_unknown",
            )

    def test_summary_and_markdown_agree_on_ids_and_verdicts(self) -> None:
        certificate = self._certificate()
        finding = StaticFinding.from_certificate(certificate)
        families = self._families(finding, certificate)
        summary = build_summary(families, (finding,), (self._framework_coverage(),))
        report = render_report(summary, families, (finding,), (certificate,))
        self.assertEqual(summary["family_ids"], [families[0].family_id])
        self.assertEqual(summary["finding_ids"], [finding.finding_id])
        self.assertEqual(summary["verdict_counts"][finding.verdict], 1)
        self.assertIn("## Finding families", report)
        self.assertIn("| Priority | Family ID | Verdict | Amplification | Reachability | Bound status | Missing evidence / reasons |", report)
        self.assertLess(report.index("## Finding families"), report.index("## Exact finding audit"))
        self.assertIn(finding.finding_id, report)
        self.assertIn(certificate.verdict, report)
        self.assertIn("Coverage and limitations", report)
        self.assertNotIn("dynamically confirmed", report.lower())
        self.assertNotIn("safe", report.lower())

    def test_builder_rejects_forged_verdict_and_uncovered_paths(self) -> None:
        assertions = (
            evaluate_assertion_1(self.growth, self.flow, self.guard, self.bound),
            evaluate_assertion_2(self.growth, self.flow, self.bound, self.release),
        )
        verdict = derive_verdict(assertions, self.coverage)
        with self.assertRaises(AnalyzerError):
            build_lifecycle_certificate(
                self.entry, self.growth, (self.flow,), self.guard, self.bound, self.release,
                assertions, self.coverage, replace(verdict, verdict="static_unknown"),
            )
        with self.assertRaises(AnalyzerError):
            build_lifecycle_certificate(
                self.entry, self.growth, (self.flow,), self.guard, self.bound, self.release,
                assertions, self.coverage, replace(verdict, covered_paths=()),
            )

    def test_certificate_rejects_sibling_registration_pattern_scope(self) -> None:
        sibling_pattern_id = (
            "entry-registration-coverage:"
            "spring_mvc:annotation_mapping:spring_spel_source_default_modeled_entry"
        )
        sibling_coverage = replace(
            self.coverage,
            supported_patterns=(sibling_pattern_id,),
            registration_pattern_id=sibling_pattern_id,
        )
        assertions = (
            evaluate_assertion_1(self.growth, self.flow, self.guard, self.bound),
            evaluate_assertion_2(self.growth, self.flow, self.bound, self.release),
        )
        verdict = derive_verdict(assertions, sibling_coverage)
        with self.assertRaises(AnalyzerError) as raised:
            build_lifecycle_certificate(
                self.entry,
                self.growth,
                (self.flow,),
                self.guard,
                self.bound,
                self.release,
                assertions,
                sibling_coverage,
                verdict,
            )
        self.assertEqual(raised.exception.code, "ANALYSIS_CERTIFICATE_INVALID")

    def test_certificate_rejects_generic_unscoped_current_or_sibling_coverage(self) -> None:
        assertions = (
            evaluate_assertion_1(self.growth, self.flow, self.guard, self.bound),
            evaluate_assertion_2(self.growth, self.flow, self.bound, self.release),
        )
        sibling_pattern_id = (
            "entry-registration-coverage:"
            "spring_mvc:annotation_mapping:spring_spel_source_default_modeled_entry"
        )
        for pattern_id in (self.entry.registration_pattern_id, sibling_pattern_id):
            with self.subTest(pattern_id=pattern_id):
                unscoped = CandidateCoverage(
                    framework=self.entry.framework,
                    status="complete",
                    supported_patterns=(pattern_id,),
                    unsupported_patterns=(),
                    effect_on_verdict="none",
                )
                verdict = derive_verdict(assertions, unscoped)
                with self.assertRaises(AnalyzerError) as raised:
                    build_lifecycle_certificate(
                        self.entry,
                        self.growth,
                        (self.flow,),
                        self.guard,
                        self.bound,
                        self.release,
                        assertions,
                        unscoped,
                        verdict,
                    )
                self.assertEqual(
                    raised.exception.code, "ANALYSIS_CERTIFICATE_INVALID"
                )

    def test_certificate_requires_exact_entry_and_growth_coverage_scope(self) -> None:
        assertions = (
            evaluate_assertion_1(self.growth, self.flow, self.guard, self.bound),
            evaluate_assertion_2(self.growth, self.flow, self.bound, self.release),
        )
        for missing_scope in ("entry_id", "growth_id"):
            with self.subTest(missing_scope=missing_scope):
                incomplete_scope = replace(self.coverage, **{missing_scope: None})
                verdict = derive_verdict(assertions, incomplete_scope)
                with self.assertRaises(AnalyzerError) as raised:
                    build_lifecycle_certificate(
                        self.entry,
                        self.growth,
                        (self.flow,),
                        self.guard,
                        self.bound,
                        self.release,
                        assertions,
                        incomplete_scope,
                        verdict,
                    )
                self.assertEqual(
                    raised.exception.code, "ANALYSIS_CERTIFICATE_INVALID"
                )

    def test_builder_recomputes_positive_proof_gate_before_signing_certificate(self) -> None:
        assertions = (
            evaluate_assertion_1(self.growth, self.flow, self.guard, self.bound),
            evaluate_assertion_2(self.growth, self.flow, self.bound, self.release),
        )
        derived = derive_verdict(assertions, self.coverage)
        gate = VerdictProofGate(True, False, True, True, True, True, True)
        gated = apply_positive_proof_gate(derived, gate)

        certificate = build_lifecycle_certificate(
            self.entry,
            self.growth,
            (self.flow,),
            self.guard,
            self.bound,
            self.release,
            assertions,
            self.coverage,
            gated,
            proof_gate=gate,
        )
        self.assertEqual(certificate.verdict, "static_unknown")
        self.assertIn("VERDICT_REACHABILITY_NOT_PROVEN", certificate.reason_codes)
        with self.assertRaises(AnalyzerError):
            build_lifecycle_certificate(
                self.entry,
                self.growth,
                (self.flow,),
                self.guard,
                self.bound,
                self.release,
                assertions,
                self.coverage,
                derived,
                proof_gate=gate,
            )

    def test_builder_downgrades_bounded_certificate_with_candidate_gap(self) -> None:
        guard = GuardDecision(
            "effective", (), (), ("fact:guard",), (), ("guard:one",)
        )
        assertions = (
            evaluate_assertion_1(self.growth, self.flow, guard, self.bound),
            evaluate_assertion_2(self.growth, self.flow, self.bound, self.release),
        )
        derived = derive_verdict(assertions, self.coverage)
        self.assertEqual("bounded_under_modeled_assumptions", derived.verdict)
        gate = VerdictProofGate(True, True, True, True, True, True, False)
        gated = apply_positive_proof_gate(derived, gate)

        certificate = build_lifecycle_certificate(
            self.entry,
            self.growth,
            (self.flow,),
            guard,
            self.bound,
            self.release,
            assertions,
            self.coverage,
            gated,
            proof_gate=gate,
        )

        self.assertEqual("static_unknown", certificate.verdict)
        self.assertIn("VERDICT_CANDIDATE_RELEVANT_GAP", certificate.reason_codes)
        self.assertNotIn(
            "STATIC_EVIDENCE_COVERAGE_COMPLETE", certificate.assumptions
        )
        self.assertIn("MODELED_DEFAULT_CONFIGURATION", certificate.assumptions)
        with self.assertRaises(AnalyzerError):
            build_lifecycle_certificate(
                self.entry,
                self.growth,
                (self.flow,),
                guard,
                self.bound,
                self.release,
                assertions,
                self.coverage,
                derived,
                proof_gate=gate,
            )

    def test_partial_sibling_path_forces_static_unknown(self) -> None:
        partial_proof = FlowProof.create(
            entry_id=self.entry.entry_id,
            growth_id=self.growth.growth_id,
            attacker_control=self.flow.proof.attacker_control,
            call_path=("fixture.Handler.partial",),
            phase_sequence=("in_handler", "growth"),
            confidence="partial",
            coverage_status="partial",
            coverage_note="fixture_partial",
        )
        partial = verify_flow(
            partial_proof,
            {self.entry.entry_id: self.entry},
            {self.growth.growth_id: self.growth},
        )
        assertions = tuple(
            evaluation
            for flow in (self.flow, partial)
            for evaluation in (
                evaluate_assertion_1(self.growth, flow, self.guard, self.bound),
                evaluate_assertion_2(self.growth, flow, self.bound, self.release),
            )
        )
        coverage = replace(self.coverage, path_id=None)
        verdict = derive_verdict(assertions, coverage)
        self.assertEqual(verdict.verdict, "static_unknown")
        certificate = build_lifecycle_certificate(
            self.entry,
            self.growth,
            (self.flow, partial),
            self.guard,
            self.bound,
            self.release,
            assertions,
            coverage,
            verdict,
        )
        self.assertEqual(certificate.verdict, "static_unknown")
        self.assertEqual(
            certificate.path_ids,
            tuple(sorted((self.flow.path_id, partial.path_id))),
        )

    def test_builder_rejects_forged_assertion_evaluation(self) -> None:
        assertions = (
            evaluate_assertion_1(self.growth, self.flow, self.guard, self.bound),
            evaluate_assertion_2(self.growth, self.flow, self.bound, self.release),
        )
        forged = AssertionEvaluation(
            "assertion_1",
            "refuted",
            ("FORGED",),
            assertions[0].evidence_ids,
            (),
        )
        forged_assertions = (forged, assertions[1])
        forged_verdict = derive_verdict(forged_assertions, self.coverage)
        with self.assertRaises(AnalyzerError):
            build_lifecycle_certificate(
                self.entry, self.growth, (self.flow,), self.guard, self.bound,
                self.release, forged_assertions, self.coverage, forged_verdict,
            )

    def test_direct_certificate_rejects_forged_id_and_snapshots_nested_values(self) -> None:
        certificate = self._certificate()
        with self.assertRaises(AnalyzerError):
            replace(certificate, certificate_id="certificate:forged")
        record = certificate.to_dict()
        record["resource_point"]["receiver"] = "mutated"
        self.assertNotEqual(record["resource_point"], certificate.to_dict()["resource_point"])

    def test_certificate_roundtrip_reconstruction_preserves_canonical_scope(self) -> None:
        certificate = self._certificate()
        record = certificate.to_dict()
        constructor_record = {
            **record,
            "attacker_inputs": tuple(record["attacker_inputs"]),
            "path_ids": tuple(record["path_ids"]),
            "assertions": tuple(record["assertions"]),
            "resource_lifecycle_decisions": tuple(
                record["resource_lifecycle_decisions"]
            ),
            "reason_codes": tuple(record["reason_codes"]),
            "assumptions": tuple(record["assumptions"]),
            "coverage_gaps": tuple(record["coverage_gaps"]),
            "unresolved_facts": tuple(record["unresolved_facts"]),
            "suggested_follow_up_measurements": tuple(
                record["suggested_follow_up_measurements"]
            ),
        }
        reconstructed = LifecycleCertificate(**constructor_record)
        self.assertEqual(reconstructed.to_dict(), record)
        with self.assertRaises(AnalyzerError) as raised:
            LifecycleCertificate(
                **{
                    **constructor_record,
                    "entry_id": "entry:sibling",
                }
            )
        self.assertEqual(raised.exception.code, "ANALYSIS_CERTIFICATE_INVALID")

    def test_report_rejects_orphan_certificate(self) -> None:
        certificate = self._certificate()
        summary = build_summary((), (), (self._framework_coverage(),))
        with self.assertRaises(AnalyzerError) as raised:
            render_report(summary, (), (), (certificate,))
        self.assertEqual(raised.exception.code, "ANALYSIS_REPORT_INVALID")

    def test_report_rejects_finding_certificate_disagreement(self) -> None:
        certificate = self._certificate()
        finding = StaticFinding.from_certificate(certificate)
        families = self._families(finding, certificate)
        summary = build_summary(families, (finding,), (self._framework_coverage(),))
        forged = replace(finding, reason_codes=("FORGED",))
        with self.assertRaises(AnalyzerError):
            render_report(summary, families, (forged,), (certificate,))

    def _families(self, finding, certificate):
        return build_finding_families(
            (finding,),
            (certificate,),
            {self.entry.entry_id: self.entry},
            {},
            {(self.entry.entry_id, self.growth.growth_id): "large_single_request"},
        )

    def _framework_coverage(self):
        from dosweb.entries import FrameworkCoverage
        return FrameworkCoverage(
            self.entry.framework,
            "complete",
            (self.entry.registration_pattern_id,),
            (),
            "none",
        )


if __name__ == "__main__":
    unittest.main()
