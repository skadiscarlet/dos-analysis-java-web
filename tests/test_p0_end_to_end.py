from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dosweb.conclude import (
    CandidateCoverage,
    derive_verdict,
    evaluate_assertion_1,
    evaluate_assertion_2,
)
from dosweb.entries import AttackerInputFact, EntryFact, FrameworkCoverage, HandlerFact, RegistrationFact
from dosweb.flows import AttackerControl, FlowProof, verify_flow
from dosweb.growth import DemandInput, GrowthCandidate, SourceLocation, VerificationCheck, VerifiedGrowthResult
from dosweb.lifecycle import (
    BoundDecision,
    GuardCandidate,
    GuardDecision,
    ModeledConfiguration,
    ReleaseCandidate,
    ReleaseDecision,
    evaluate_guard,
    evaluate_synchronous_release,
)
from dosweb.lifecycle.certificates import StaticFinding, build_lifecycle_certificate
from dosweb.pipeline import Pipeline, STAGES, StageOutput
from dosweb.report import build_finding_families, build_summary, render_report


class P0EndToEndTests(unittest.TestCase):
    """Network-free E-to-G-to-lifecycle-to-report coverage for the ten P0 categories."""

    def _case(self, number: int, *, framework: str = "spring_mvc", kind: str,
              dimension: str, role: str, scope: str, registration: str | None = None,
              coverage_status: str = "complete") -> dict[str, object]:
        registration = registration or {
            "spring_mvc": "annotation_mapping",
            "netty": "pipeline_registration",
            "mqtt": "subscription_registration",
        }[framework]
        protocol = {"spring_mvc": "http", "netty": "tcp", "mqtt": "mqtt"}[framework]
        input_kind = {"spring_mvc": "request_parameter", "netty": "message_payload", "mqtt": "message_payload"}[framework]
        file_name = f"fixture/{framework}/P0Fixture{number}.java"
        handler = HandlerFact(f"fixture.{framework}.P0Fixture.handle{number}", file_name, 10)
        registration_fact = RegistrationFact(registration, f"fixture.{framework}.P0Fixture.register{number}", file_name, 8)
        input_name = {"size": "size", "key": "key", "value": "body", "submission_count": "count"}[role]
        input_type = "int" if role in {"size", "submission_count"} else "String"
        entry = EntryFact.create(
            framework=framework,
            protocol=protocol,
            handler=handler,
            registration=registration_fact,
            route_or_event="/p0" if framework == "spring_mvc" else "channelRead" if framework == "netty" else "messageArrived",
            auth_context="unauthenticated",
            attacker_inputs=(AttackerInputFact(input_name, input_type, input_kind),),
            materialization_phase="in_handler",
        )
        site = SourceLocation(file_name, 20)
        growth = GrowthCandidate.create(
            site=site,
            kind=kind,
            operation={
                "input_materialization": "request.getInputStream().readAllBytes",
                "direct_allocation": "ByteBuffer.allocate",
                "container_growth": "Map.put",
                "async_work_growth": "queue.submit",
            }[kind],
            resource_dimension=dimension,
            receiver="fixture.P0.resource",
            field_path="this.resource",
            demand_inputs=(DemandInput(input_name, role),),
            escape_scope=scope,
            evidence_ids=frozenset({f"fact:growth-{number}"}),
        )
        verified_growth = VerifiedGrowthResult.create(
            candidate=growth,
            slice_id=f"slice:p0-{number}",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )
        flow = verify_flow(
            FlowProof.create(
                entry_id=entry.entry_id,
                growth_id=growth.growth_id,
                attacker_control=AttackerControl(role, input_name, f"resource.{input_name}"),
                call_path=(
                    handler.callable,
                    f"{handler.callable}~resource.grow@{file_name}:19",
                ),
                phase_sequence=("in_handler", "growth"),
                confidence="proven",
            ),
            {entry.entry_id: entry},
            {growth.growth_id: verified_growth},
        )
        return {
            "entry": entry,
            "growth": verified_growth,
            "flow": flow,
            "registration": registration,
            "framework": framework,
            "coverage_status": coverage_status,
        }

    def _decisions(self, case: dict[str, object], *, guard_candidates=(), guard_config=(),
                   bound=BoundDecision("absent", ("BOUND_ABSENT",), (), (), (), ()),
                   release_candidates=()) -> tuple[GuardDecision, BoundDecision, ReleaseDecision]:
        entry, growth, flow = case["entry"], case["growth"], case["flow"]
        guard = evaluate_guard(entry, growth, flow, guard_candidates, ModeledConfiguration(guard_config))
        release = evaluate_synchronous_release(entry, growth, flow, release_candidates)
        return guard, bound, release

    def _coverage(self, case: dict[str, object]) -> CandidateCoverage:
        status = case["coverage_status"]
        if status == "partial":
            supported, unsupported, effect = ("static_subscription",), ("dynamic_subscription",), "forces_unknown"
        else:
            supported, unsupported, effect = (case["registration"],), (), "none"
        return CandidateCoverage(
            framework=case["framework"],
            status=status,
            supported_patterns=supported,
            unsupported_patterns=unsupported,
            effect_on_verdict=effect,
            registration_pattern=case["registration"],
            entry_id=case["entry"].entry_id,
            growth_id=case["growth"].growth_id,
            path_id=case["flow"].path_id,
        )

    def _certificate(self, case: dict[str, object], guard: GuardDecision,
                     bound: BoundDecision, release: ReleaseDecision):
        growth, flow = case["growth"], case["flow"]
        assertions = (
            evaluate_assertion_1(growth, flow, guard, bound),
            evaluate_assertion_2(growth, flow, bound, release),
        )
        coverage = self._coverage(case)
        verdict = derive_verdict(assertions, coverage)
        certificate = build_lifecycle_certificate(
            case["entry"], growth, (flow,), guard, bound, release,
            assertions, coverage, verdict,
        )
        return certificate, assertions, verdict

    def test_authoritative_ten_scenario_categories(self) -> None:
        finite_guard = GuardCandidate.create(
            site_file="fixture/spring/P0Fixture5.java", site_start_line=18,
            kind="input_validation", resource_dimension="bytes", scope="request",
            behavior="reject", dominates_growth=True, reject_path_reaches_growth=False,
            configuration_key="request.max-bytes", configuration_value="1024",
            representation="raw_body", phase="before_growth", covers_materialization=True,
            authorization_only=False, evidence=("fact:guard-5",), coverage_status="complete",
        )
        post_materialization_guard = GuardCandidate.create(
            site_file="fixture/spring/P0Fixture6.java", site_start_line=21,
            kind="input_validation", resource_dimension="bytes", scope="request",
            behavior="reject", dominates_growth=True, reject_path_reaches_growth=False,
            configuration_key="request.max-bytes", configuration_value="1024",
            representation="raw_body", phase="after_materialization", covers_materialization=True,
            authorization_only=False, evidence=("fact:guard-6",), coverage_status="complete",
        )
        success_only_release = ReleaseCandidate.create(
            site_file="fixture/spring/P0Fixture7.java", site_start_line=30,
            kind="remove", resource_dimension="entries", scope="global",
            receiver="fixture.P0.resource", key_identity="key", synchronous=True,
            normal_path=True, exceptional_path=False, actual_reduction=True, after_growth=True,
            transfer_only=False, async_kind="none", evidence=("fact:release-7",), coverage_status="complete",
        )
        async_release = ReleaseCandidate.create(
            site_file="fixture/spring/P0Fixture8.java", site_start_line=30,
            kind="remove", resource_dimension="tasks", scope="global",
            receiver="fixture.P0.resource", key_identity="count", synchronous=False,
            normal_path=True, exceptional_path=True, actual_reduction=True, after_growth=True,
            transfer_only=False, async_kind="consumer", evidence=("fact:release-8",), coverage_status="complete",
        )
        scenarios = (
            ("unbounded materialization", self._case(1, kind="input_materialization", dimension="bytes", role="size", scope="request"), {}, (), "static_vulnerable", ("matched", "not_applicable")),
            ("direct allocation", self._case(2, kind="direct_allocation", dimension="bytes", role="size", scope="request"), {}, (), "static_vulnerable", ("matched", "not_applicable")),
            ("distinct-key global map", self._case(3, kind="container_growth", dimension="entries", role="key", scope="global"), {}, (), "static_vulnerable", ("not_applicable", "matched")),
            ("unbounded queue", self._case(4, kind="async_work_growth", dimension="tasks", role="submission_count", scope="global"), {}, (), "static_vulnerable", ("not_applicable", "matched")),
            ("finite checked rejection", self._case(5, kind="direct_allocation", dimension="bytes", role="size", scope="request"), {"guard_candidates": (finite_guard,), "guard_config": (("request.max-bytes", 1024),)}, (), "bounded_under_modeled_assumptions", ("refuted", "not_applicable")),
            ("post-materialization Guard", self._case(6, kind="direct_allocation", dimension="bytes", role="size", scope="request"), {"guard_candidates": (post_materialization_guard,), "guard_config": (("request.max-bytes", 1024),)}, (), "static_vulnerable", ("matched", "not_applicable")),
            ("success-only Release", self._case(7, kind="container_growth", dimension="entries", role="key", scope="global"), {}, (success_only_release,), "static_vulnerable", ("not_applicable", "matched")),
            ("async consumer unknown", self._case(8, kind="async_work_growth", dimension="tasks", role="submission_count", scope="global"), {}, (async_release,), "static_unknown", ("not_applicable", "unknown")),
            ("Netty registration", self._case(9, framework="netty", kind="direct_allocation", dimension="bytes", role="size", scope="request"), {}, (), "static_vulnerable", ("matched", "not_applicable")),
            ("MQTT callback", self._case(10, framework="mqtt", kind="async_work_growth", dimension="tasks", role="submission_count", scope="global", coverage_status="partial"), {}, (), "static_unknown", ("not_applicable", "matched")),
        )
        certificates = []
        findings = []
        expected_verdicts = []
        for name, case, decision_kwargs, releases, expected_verdict, expected_assertions in scenarios:
            with self.subTest(scenario=name):
                guard, bound, release = self._decisions(case, release_candidates=releases, **decision_kwargs)
                certificate, assertions, verdict = self._certificate(case, guard, bound, release)
                self.assertEqual(tuple(item.status for item in assertions), expected_assertions)
                self.assertEqual(verdict.verdict, expected_verdict)
                self.assertEqual(certificate.verdict, expected_verdict)
                self.assertEqual(certificate.entry_id, case["entry"].entry_id)
                self.assertEqual(certificate.growth_id, case["growth"].growth_id)
                self.assertEqual(certificate.path_ids, (case["flow"].path_id,))
                finding = StaticFinding.from_certificate(certificate)
                self.assertEqual(finding.certificate_id, certificate.certificate_id)
                self.assertEqual(finding.entry_id, certificate.entry_id)
                self.assertEqual(finding.growth_id, certificate.growth_id)
                self.assertEqual(finding.verdict, certificate.verdict)
                self.assertEqual(finding.reason_codes, certificate.reason_codes)
                certificates.append(certificate)
                findings.append(finding)
                expected_verdicts.append(expected_verdict)

        self.assertEqual(len(certificates), 10)
        self.assertEqual(len({item.certificate_id for item in certificates}), 10)
        self.assertEqual([item.verdict for item in findings], expected_verdicts)
        mqtt_certificate = certificates[-1]
        self.assertEqual(mqtt_certificate.verdict, "static_unknown")
        self.assertIn("dynamic_subscription", mqtt_certificate.coverage_gaps)
        self.assertTrue(mqtt_certificate.coverage_gaps)

        entries = {
            case["entry"].entry_id: case["entry"]
            for _, case, _, _, _, _ in scenarios
        }
        amplification_classes = {
            (finding.entry_id, finding.growth_id): (
                "large_single_request"
                if case["growth"].candidate.kind
                in {"input_materialization", "direct_allocation"}
                else "high_cardinality_retention"
                if case["growth"].candidate.kind == "container_growth"
                else "queue_instability"
            )
            for finding, (_, case, _, _, _, _) in zip(findings, scenarios, strict=True)
        }
        families = build_finding_families(
            tuple(findings),
            tuple(certificates),
            entries,
            {},
            amplification_classes,
        )

        summary = build_summary(
            families,
            tuple(findings),
            (
                FrameworkCoverage("spring_mvc", "complete", ("annotation_mapping",), (), "none"),
                FrameworkCoverage("netty", "complete", ("pipeline_registration",), (), "none"),
                FrameworkCoverage("mqtt", "partial", ("static_subscription",), ("dynamic_subscription",), "forces_unknown"),
            ),
        )
        report = render_report(summary, families, tuple(findings), tuple(certificates))
        self.assertEqual(summary["finding_ids"], sorted(item.finding_id for item in findings))
        self.assertEqual(sum(summary["verdict_counts"].values()), 10)
        self.assertEqual(summary["verdict_counts"]["static_unknown"], 2)
        self.assertIn("mqtt:dynamic_subscription", summary["limitations"])
        self.assertIn("Coverage and limitations", report)
        self.assertNotIn("dynamically confirmed", report.lower())
        self.assertIn("does not provide dynamic confirmation", report)
        for finding in findings:
            self.assertIn(finding.finding_id, report)
            self.assertIn(finding.verdict, report)

    def test_local_pipeline_resume_does_not_duplicate_executor_calls(self) -> None:
        calls = {stage: 0 for stage in STAGES}

        def executor(context):
            calls[context.stage] += 1
            return StageOutput({f"{context.stage}.json": f"{context.stage}:{calls[context.stage]}\n"}, {"local_only": True})

        with tempfile.TemporaryDirectory() as temporary:
            executors = {stage: executor for stage in STAGES}
            Pipeline(
                Path(temporary), executors, database_fingerprint="fixture-db",
                model_fingerprint="fixture-model", report_fingerprint="fixture-report",
                config_fingerprint="fixture-config",
            ).run()
            Pipeline(
                Path(temporary), executors, database_fingerprint="fixture-db",
                model_fingerprint="fixture-model", report_fingerprint="fixture-report",
                config_fingerprint="fixture-config", resume=True,
            ).run()
        self.assertEqual(calls, {stage: 1 for stage in STAGES})


if __name__ == "__main__":
    unittest.main()
