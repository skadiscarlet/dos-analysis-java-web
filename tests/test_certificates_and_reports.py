from __future__ import annotations

import unittest
from dataclasses import replace

from dosweb.errors import AnalyzerError

from dosweb.conclude import (
    AssertionEvaluation,
    CandidateCoverage,
    derive_verdict,
    evaluate_assertion_1,
    evaluate_assertion_2,
)
from dosweb.flows import FlowProof, normalize_flow_rows, verify_flow
from dosweb.lifecycle import BoundDecision, GuardDecision, ReleaseDecision
from dosweb.lifecycle.certificates import StaticFinding, build_lifecycle_certificate
from dosweb.report import build_summary, render_report
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
            supported_patterns=(self.entry.registration.kind,),
            unsupported_patterns=(),
            effect_on_verdict="none",
            registration_pattern=self.entry.registration.kind,
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
        summary = build_summary((finding,), (self._framework_coverage(),))
        report = render_report(summary, (finding,), (certificate,))
        self.assertEqual(summary["finding_ids"], [finding.finding_id])
        self.assertEqual(summary["verdict_counts"][finding.verdict], 1)
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

    def test_report_rejects_orphan_certificate(self) -> None:
        certificate = self._certificate()
        summary = build_summary((), (self._framework_coverage(),))
        with self.assertRaises(AnalyzerError) as raised:
            render_report(summary, (), (certificate,))
        self.assertEqual(raised.exception.code, "ANALYSIS_REPORT_INVALID")

    def test_report_rejects_finding_certificate_disagreement(self) -> None:
        certificate = self._certificate()
        finding = StaticFinding.from_certificate(certificate)
        summary = build_summary((finding,), (self._framework_coverage(),))
        forged = replace(finding, reason_codes=("FORGED",))
        with self.assertRaises(AnalyzerError):
            render_report(summary, (forged,), (certificate,))

    def _framework_coverage(self):
        from dosweb.entries import FrameworkCoverage
        return FrameworkCoverage(
            self.entry.framework, "complete", (self.entry.registration.kind,), (), "none"
        )


if __name__ == "__main__":
    unittest.main()
