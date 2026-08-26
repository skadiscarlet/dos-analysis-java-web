from __future__ import annotations

import hashlib
import unittest

from dosweb.configuration.models import ModeledConfigurationFact
from dosweb.entries import (
    AttackerInputFact,
    EntryFact,
    HandlerFact,
    RegistrationFact as EntryRegistrationFact,
)
from dosweb.errors import AnalyzerError
from dosweb.growth import (
    GrowthCandidate,
    SourceExcerpt,
    adapt_growth_static_evidence,
)


class GrowthStaticEvidenceAdapterTests(unittest.TestCase):
    def _entry(self, *, framework: str = "spring_mvc") -> EntryFact:
        return EntryFact.create(
            framework=framework,
            protocol="http" if framework in {"spring_mvc", "servlet"} else "tcp",
            handler=HandlerFact("fixture.Handler.handle", "src/Handler.java", 20),
            registration=EntryRegistrationFact(
                "annotation_mapping" if framework in {"spring_mvc", "servlet"} else "pipeline_registration",
                "fixture.Handler",
                "src/Handler.java",
                8,
            ),
            route_or_event="/items",
            auth_context="unknown",
            attacker_inputs=(AttackerInputFact("body", "byte[]", "request_body"),),
            materialization_phase="in_handler",
        )

    def _candidate(
        self,
        kind: str,
        *,
        evidence: str = "query_evidence",
        coverage_status: str = "complete",
        coverage_note: str = "fixture",
    ) -> GrowthCandidate:
        dimensions = {
            "input_materialization": ("bytes", "size", "request"),
            "direct_allocation": ("bytes", "size", "request"),
            "container_growth": ("entries", "key", "instance"),
            "async_work_growth": ("tasks", "value", "global"),
        }
        dimension, role, scope = dimensions[kind]
        return GrowthCandidate.from_raw(
            {
                "site_file": "src/Handler.java",
                "site_start_line": 24,
                "growth_kind": kind,
                "operation": f"fixture.{kind}",
                "resource_dimension": dimension,
                "receiver": "fixture.Handler.resource",
                "field_path": "this.resource",
                "demand_input_name": "body",
                "demand_input_role": role,
                "escape_scope": scope,
                "candidate_evidence": evidence,
                "coverage_status": coverage_status,
                "coverage_note": coverage_note,
                "query_name": "growth",
                "query_sha256": "a" * 64,
                "site_location": "src/Handler.java:24",
            }
        )

    def _excerpt(self, excerpt_id: str, start: int, end: int) -> SourceExcerpt:
        content = "class Handler { void handle() {} }\n"
        return SourceExcerpt(
            excerpt_id,
            "src/Handler.java",
            start,
            end,
            content,
            "b" * 64,
            hashlib.sha256(content.encode()).hexdigest(),
        )

    def _flow(self, candidate: GrowthCandidate) -> dict[str, object]:
        return {
            "source_file": "src/Handler.java",
            "source_start_line": 20,
            "sink_file": candidate.site.file,
            "sink_start_line": candidate.site.start_line,
            "attacker_target": candidate.demand_inputs[0].role,
            "attacker_source": "body",
            "attacker_sink": candidate.demand_inputs[0].name,
            "call_path": "fixture.Handler.handle>fixture.Handler.grow",
            "phase_sequence": "entry>dataflow>growth",
            "flow_kind": "data_flow",
            "confidence": "proven",
            "coverage_status": "complete",
            "coverage_note": "fixture_flow",
        }

    def test_maps_all_query_growth_kinds_only_with_extracted_flow_and_without_config(self) -> None:
        expected_kinds = {
            "input_materialization": "input_materialization",
            "direct_allocation": "allocation",
            "container_growth": "container_write",
            "async_work_growth": "async_submission",
        }
        excerpts = (
            self._excerpt("excerpt:registration", 1, 10),
            self._excerpt("excerpt:handler", 15, 22),
            self._excerpt("excerpt:growth", 23, 30),
        )
        for growth_kind, static_kind in expected_kinds.items():
            with self.subTest(growth_kind=growth_kind):
                candidate = self._candidate(growth_kind)
                evidence = adapt_growth_static_evidence(
                    self._entry(),
                    candidate,
                    excerpts,
                    (self._flow(candidate),),
                )
                sink_facts = tuple(fact for fact in evidence.static_facts if fact.relation == "sink")
                source_facts = tuple(fact for fact in evidence.static_facts if fact.relation == "flows_to")
                self.assertEqual(
                    tuple(fact.fact_id for fact in sink_facts),
                    tuple(sorted(candidate.evidence_ids)),
                )
                self.assertEqual(
                    {fact.kind for fact in sink_facts},
                    {static_kind},
                )
                self.assertEqual(
                    {fact.location_ref for fact in evidence.static_facts},
                    {"excerpt:handler", "excerpt:growth"},
                )
                self.assertTrue(source_facts)
                self.assertEqual({fact.kind for fact in source_facts}, {"flow"})
                self.assertEqual({fact.relation for fact in source_facts}, {"flows_to"})
                self.assertTrue(evidence.cfg_summary.path_ids)
                self.assertEqual(evidence.cfg_summary.phases, ("in_handler",))
                self.assertEqual(evidence.cfg_summary.branch_facts, ())
                self.assertEqual(evidence.config_facts, ())
                self.assertEqual(
                    [fact.to_dict() for fact in evidence.registration_facts],
                    [{"kind": "spring_mvc", "location_ref": "excerpt:registration"}],
                )

    def test_is_deterministic_under_excerpt_and_candidate_evidence_ordering(self) -> None:
        candidate = self._candidate("container_growth", evidence="fact:z")
        second = GrowthCandidate.create(
            site=candidate.site,
            kind=candidate.kind,
            operation=candidate.operation,
            resource_dimension=candidate.resource_dimension,
            receiver=candidate.receiver,
            field_path=candidate.field_path,
            demand_inputs=candidate.demand_inputs,
            escape_scope=candidate.escape_scope,
            evidence_ids=frozenset({"fact:z", "fact:a"}),
        )
        registration = self._excerpt("excerpt:registration", 1, 10)
        handler = self._excerpt("excerpt:handler", 15, 22)
        growth = self._excerpt("excerpt:growth", 23, 30)
        flow = self._flow(second)
        left = adapt_growth_static_evidence(self._entry(), second, (growth, registration, handler), (flow,))
        right = adapt_growth_static_evidence(self._entry(), second, (registration, handler, growth), (flow,))
        self.assertEqual(left, right)
        self.assertEqual(
            tuple(fact.fact_id for fact in left.static_facts if fact.relation == "sink"),
            ("fact:a", "fact:z"),
        )

    def test_multiple_attacker_inputs_on_one_cfg_path_share_one_path_identity(self) -> None:
        candidate = self._candidate("direct_allocation")
        first = self._flow(candidate)
        second = {**first, "attacker_source": "height", "attacker_sink": "height"}

        evidence = adapt_growth_static_evidence(
            self._entry(),
            candidate,
            (
                self._excerpt("excerpt:registration", 1, 10),
                self._excerpt("excerpt:handler", 15, 22),
                self._excerpt("excerpt:growth", 23, 30),
            ),
            (first, second),
        )

        self.assertEqual(
            len([fact for fact in evidence.static_facts if fact.relation == "flows_to"]),
            2,
        )
        self.assertEqual(len(evidence.cfg_summary.path_ids), 1)

    def test_preserves_partial_coverage_without_fabricating_cfg_or_config(self) -> None:
        candidate = self._candidate(
            "async_work_growth",
            coverage_status="partial",
            coverage_note="queue_or_executor_capacity_requires_contract",
        )
        evidence = adapt_growth_static_evidence(
            self._entry(),
            candidate,
            (
                self._excerpt("excerpt:registration", 1, 10),
                self._excerpt("excerpt:handler", 15, 22),
                self._excerpt("excerpt:growth", 23, 30),
            ),
            (self._flow(candidate),),
        )
        self.assertEqual(evidence.coverage_status, "partial")
        self.assertEqual(
            evidence.coverage_notes,
            ("queue_or_executor_capacity_requires_contract",),
        )
        self.assertTrue(evidence.cfg_summary.path_ids)
        self.assertEqual(evidence.config_facts, ())

    def test_cli_or_yaml_configuration_without_source_line_remains_auditable_by_config_id(self) -> None:
        candidate = self._candidate("direct_allocation")
        configured = ModeledConfigurationFact(
            "request.max-bytes", 1024, "", 0, "default", "cli_override", True, "known",
        )
        evidence = adapt_growth_static_evidence(
            self._entry(),
            candidate,
            (
                self._excerpt("excerpt:registration", 1, 10),
                self._excerpt("excerpt:handler", 15, 22),
                self._excerpt("excerpt:growth", 23, 30),
            ),
            (self._flow(candidate),),
            (configured,),
        )
        self.assertEqual(1, len(evidence.config_facts))
        self.assertEqual(configured.config_id, evidence.config_facts[0].source_location_ref)
        self.assertEqual(1024, evidence.config_facts[0].normalized_value)

    def test_does_not_fabricate_attacker_flow_when_codeql_has_no_matching_row(self) -> None:
        candidate = self._candidate("direct_allocation")
        evidence = adapt_growth_static_evidence(
            self._entry(),
            candidate,
            (
                self._excerpt("excerpt:registration", 1, 10),
                self._excerpt("excerpt:handler", 15, 22),
                self._excerpt("excerpt:growth", 23, 30),
            ),
            (),
        )
        self.assertFalse(any(fact.relation in {"source", "flows_to"} for fact in evidence.static_facts))
        self.assertEqual(evidence.cfg_summary.path_ids, ())
        self.assertTrue(all(fact.value_ref is None for fact in evidence.static_facts if fact.relation == "sink"))

    def test_requires_attested_candidate_and_registration_locations(self) -> None:
        candidate = self._candidate("container_growth")
        cases = (
            (self._excerpt("excerpt:registration", 1, 10), self._excerpt("excerpt:handler", 15, 22)),
            (self._excerpt("excerpt:handler", 15, 22), self._excerpt("excerpt:growth", 23, 30)),
        )
        for excerpts in cases:
            with self.subTest(excerpts=excerpts):
                with self.assertRaises(AnalyzerError) as raised:
                    adapt_growth_static_evidence(self._entry(), candidate, excerpts)
                self.assertEqual(raised.exception.code, "ANALYSIS_GROWTH_INVALID")


if __name__ == "__main__":
    unittest.main()
