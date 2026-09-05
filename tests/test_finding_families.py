from __future__ import annotations

import unittest
from dataclasses import replace

from dosweb.conclude import CandidateCoverage, derive_verdict, evaluate_assertion_1, evaluate_assertion_2
from dosweb.entries import EntryFact
from dosweb.flows import AttackerControl, FlowProof, verify_flow
from dosweb.growth import DemandInput, GrowthCandidate, VerificationCheck, VerifiedGrowthResult
from dosweb.lifecycle import BoundDecision, GuardDecision, ReleaseDecision
from dosweb.lifecycle.certificates import StaticFinding, build_lifecycle_certificate
from dosweb.reachability import ReachabilityDecision
from dosweb.report.families import FindingFamily, build_finding_families


class FindingFamilyTests(unittest.TestCase):
    def _entry(
        self,
        route: str,
        *,
        auth_context: str = "unauthenticated",
    ) -> EntryFact:
        return EntryFact.from_raw(
            {
                "framework": "spring_mvc",
                "protocol": "http",
                "handler_fqn": "fixture.Handler.create",
                "handler_file": "fixture/Handler.java",
                "handler_start_line": 15,
                "registration_kind": "annotation_mapping",
                "registration_fqn": "fixture.Handler.create",
                "registration_file": "fixture/Handler.java",
                "registration_start_line": 14,
                "route_or_event": route,
                "auth_context": auth_context,
                "attacker_input_name": "limit",
                "attacker_input_type": "int",
                "attacker_input_kind": "request_parameter",
                "materialization_phase": "in_handler",
                "coverage_status": "complete",
                "coverage_note": "spring_annotation_mapping",
            }
        )

    def _growth(
        self,
        *,
        receiver: str = "fixture.Buffer",
        line: int = 18,
    ) -> VerifiedGrowthResult:
        candidate = GrowthCandidate.create(
            site=self._source_location(line),
            kind="direct_allocation",
            operation="java.nio.ByteBuffer.allocate",
            resource_dimension="bytes",
            receiver=receiver,
            field_path="allocation",
            demand_inputs=(DemandInput("limit", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({f"fact:allocation_{line}"}),
        )
        return VerifiedGrowthResult.create(
            candidate=candidate,
            slice_id=f"slice:fixture_{line}",
            status="verified",
            reason_codes=(),
            checks=(VerificationCheck("resource_growth", True),),
        )

    @staticmethod
    def _source_location(line: int):
        from dosweb.growth import SourceLocation

        return SourceLocation("fixture/Handler.java", line)

    def _reach(
        self,
        entry: EntryFact,
        *,
        auth_context: str | None = None,
        deployment_status: str = "default_enabled",
    ) -> ReachabilityDecision:
        auth = auth_context or entry.auth_context
        status = (
            "ordinary_attacker_reachable"
            if auth in {"unauthenticated", "low_privilege"}
            and deployment_status == "default_enabled"
            else "not_entry_reachable"
            if auth == "privileged"
            or deployment_status in {"default_disabled", "optional"}
            else "unknown"
        )
        return ReachabilityDecision(
            entry.entry_id,
            "auth_contract:fixture",
            auth,
            deployment_status,
            status,
            (),
            ("REACH_FIXTURE",),
        )

    def _member(
        self,
        entry: EntryFact,
        growth: VerifiedGrowthResult,
        reachability: ReachabilityDecision,
        *,
        bounded: bool = False,
    ):
        proof = FlowProof.create(
            entry_id=entry.entry_id,
            growth_id=growth.growth_id,
            attacker_control=AttackerControl("size", "limit", "allocate(limit)"),
            call_path=(entry.handler.callable,),
            phase_sequence=("in_handler", "growth"),
            confidence="proven",
        )
        flow = verify_flow(
            proof,
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )
        guard = GuardDecision("ineffective", ("GUARD_ABSENT",), (), (), (), ())
        bound = (
            BoundDecision(
                "effective",
                (),
                (),
                ("bound:fixture",),
                (),
                ("bound:fixture",),
            )
            if bounded
            else BoundDecision("absent", ("BOUND_ABSENT",), (), (), (), ())
        )
        release = ReleaseDecision(
            "absent", "absent", ("RELEASE_ABSENT",), (), (), (), ()
        )
        assertions = (
            evaluate_assertion_1(
                growth,
                flow,
                guard,
                bound,
                reachability=reachability,
            ),
            evaluate_assertion_2(
                growth,
                flow,
                bound,
                release,
                reachability=reachability,
            ),
        )
        coverage = CandidateCoverage(
            entry.framework,
            "complete",
            (entry.registration_pattern_id,),
            (),
            "none",
            registration_pattern_id=entry.registration_pattern_id,
            entry_id=entry.entry_id,
            growth_id=growth.growth_id,
            path_id=flow.path_id,
        )
        verdict = derive_verdict(assertions, coverage)
        certificate = build_lifecycle_certificate(
            entry,
            growth,
            (flow,),
            guard,
            bound,
            release,
            assertions,
            coverage,
            verdict,
            reachability=reachability,
        )
        return StaticFinding.from_certificate(certificate), certificate

    def _families(self, members, entries, reaches, amplifications):
        findings = tuple(member[0] for member in members)
        certificates = tuple(member[1] for member in members)
        return build_finding_families(
            findings,
            certificates,
            {entry.entry_id: entry for entry in entries},
            {reach.entry_id: reach for reach in reaches},
            amplifications,
        )

    def test_route_aliases_share_one_family_and_retain_all_exact_members(self) -> None:
        first = self._entry("/items")
        second = self._entry("POST /items")
        growth = self._growth()
        first_reach, second_reach = self._reach(first), self._reach(second)
        members = (
            self._member(first, growth, first_reach),
            self._member(second, growth, second_reach),
        )

        families = self._families(
            members,
            (first, second),
            (first_reach, second_reach),
            {
                (first.entry_id, growth.growth_id): "large_single_request",
                (second.entry_id, growth.growth_id): "large_single_request",
            },
        )

        self.assertEqual(len(families), 1)
        family = families[0]
        self.assertIsInstance(family, FindingFamily)
        self.assertEqual(
            family.member_finding_ids,
            tuple(sorted(member[0].finding_id for member in members)),
        )
        self.assertEqual(
            family.member_certificate_ids,
            tuple(sorted(member[1].certificate_id for member in members)),
        )
        self.assertEqual(family.entry_ids, tuple(sorted((first.entry_id, second.entry_id))))
        self.assertEqual(family.growth_ids, (growth.growth_id,))
        self.assertEqual(family.resource_id, growth.candidate.resource_id)
        with self.assertRaises(Exception):
            replace(family, family_id="family:forged")

    def test_auth_deployment_resource_and_verdict_are_strict_family_boundaries(self) -> None:
        cases = []

        unauth, low = self._entry("/unauth"), self._entry("/low", auth_context="low_privilege")
        growth = self._growth()
        unauth_reach, low_reach = self._reach(unauth), self._reach(low)
        cases.append(
            (
                (self._member(unauth, growth, unauth_reach), self._member(low, growth, low_reach)),
                (unauth, low),
                (unauth_reach, low_reach),
            )
        )

        disabled, optional = self._entry("/disabled", auth_context="privileged"), self._entry("/optional", auth_context="privileged")
        disabled_reach = self._reach(disabled, deployment_status="default_disabled")
        optional_reach = self._reach(optional, deployment_status="optional")
        cases.append(
            (
                (self._member(disabled, growth, disabled_reach), self._member(optional, growth, optional_reach)),
                (disabled, optional),
                (disabled_reach, optional_reach),
            )
        )

        first_resource, second_resource = self._entry("/resource-a"), self._entry("/resource-b")
        first_growth, second_growth = self._growth(receiver="fixture.BufferA"), self._growth(receiver="fixture.BufferB")
        first_reach, second_reach = self._reach(first_resource), self._reach(second_resource)
        cases.append(
            (
                (self._member(first_resource, first_growth, first_reach), self._member(second_resource, second_growth, second_reach)),
                (first_resource, second_resource),
                (first_reach, second_reach),
            )
        )

        vulnerable, bounded = self._entry("/vulnerable"), self._entry("/bounded")
        vulnerable_reach, bounded_reach = self._reach(vulnerable), self._reach(bounded)
        cases.append(
            (
                (self._member(vulnerable, growth, vulnerable_reach), self._member(bounded, growth, bounded_reach, bounded=True)),
                (vulnerable, bounded),
                (vulnerable_reach, bounded_reach),
            )
        )

        for members, entries, reaches in cases:
            with self.subTest(
                verdicts=tuple(member[0].verdict for member in members),
                deployments=tuple(reach.deployment_status for reach in reaches),
            ):
                amplifications = {
                    (member[0].entry_id, member[0].growth_id): "large_single_request"
                    for member in members
                }
                self.assertEqual(
                    len(self._families(members, entries, reaches, amplifications)),
                    2,
                )

    def test_primary_uses_amplification_then_stable_id_without_truth_input(self) -> None:
        first, second = self._entry("/first"), self._entry("/second")
        growth = self._growth()
        first_reach, second_reach = self._reach(first), self._reach(second)
        members = (
            self._member(first, growth, first_reach),
            self._member(second, growth, second_reach),
        )
        families = self._families(
            members,
            (first, second),
            (first_reach, second_reach),
            {
                (first.entry_id, growth.growth_id): "low_amplification",
                (second.entry_id, growth.growth_id): "superlinear",
            },
        )

        self.assertEqual(len(families), 1)
        self.assertEqual(families[0].primary_finding_id, members[1][0].finding_id)
        self.assertEqual(families[0].amplification_class, "superlinear")
        self.assertEqual(families[0].priority, "P0")


if __name__ == "__main__":
    unittest.main()
