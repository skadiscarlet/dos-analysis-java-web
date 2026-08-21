from __future__ import annotations

import unittest

from dosweb.growth.completeness import CandidateDisposition, CandidateEntryLink, RepeatabilityDecision, AmplificationDecision
from dosweb.growth import DemandInput, GrowthCandidate, SourceLocation
from dosweb.entries import EntryFact
from dosweb import production


class CandidateCompletenessTests(unittest.TestCase):
    def test_unmapped_complete_candidate_is_audited_not_silently_dropped(self) -> None:
        disposition = CandidateDisposition.create("growth:abc", "not_entry_reachable", (), ("ASSOCIATION_NO_ENTRY_COMPLETE",))
        self.assertEqual(disposition.status, "not_entry_reachable")
        self.assertEqual(disposition.link_ids, ())

    def test_partial_link_cannot_be_promoted_to_verified_relevant(self) -> None:
        link = CandidateEntryLink.create("growth:abc", "entry:abc", "partial", ("entry:abc", "growth:abc"), ("ASSOCIATION_CALL_GRAPH_UNAVAILABLE",))
        unresolved = CandidateDisposition.create("growth:abc", "unresolved", (link.link_id,), ("ASSOCIATION_CALL_GRAPH_UNAVAILABLE",))
        self.assertEqual(unresolved.status, "unresolved")
        self.assertEqual(link.status, "partial")

    def test_no_entry_association_is_unresolved_without_entry_coverage_proof(self) -> None:
        candidate = GrowthCandidate.create(site=SourceLocation("src/Detached.java", 9), kind="direct_allocation", operation="new byte[8]", resource_dimension="bytes", receiver="byte[]", field_path="allocation", demand_inputs=(DemandInput("size", "size"),), escape_scope="request", evidence_ids=frozenset({"fact:growth"}))
        links, disposition = production._candidate_association({}, candidate)  # noqa: SLF001
        self.assertEqual(links, ())
        self.assertEqual(disposition.status, "unresolved")
        self.assertIn("ASSOCIATION_ENTRY_COVERAGE_UNPROVEN", disposition.reason_codes)

    def test_duplicate_association_rows_publish_one_semantic_link(self) -> None:
        entry = EntryFact.from_raw({
            "framework": "servlet", "protocol": "http",
            "handler_fqn": "Filter.doFilter", "handler_file": "src/Filter.java", "handler_start_line": 10,
            "registration_kind": "static_registration", "registration_fqn": "Config.setFilter",
            "registration_file": "src/Config.java", "registration_start_line": 5,
            "route_or_event": "/api/*", "auth_context": "unknown",
            "attacker_input_name": "request", "attacker_input_type": "ServletRequest",
            "attacker_input_kind": "stream", "materialization_phase": "before_handler",
            "coverage_status": "complete", "coverage_note": "filter_registration_bean",
        })
        candidate = GrowthCandidate.create(
            site=SourceLocation("src/Service.java", 20),
            kind="container_growth",
            operation="computeIfAbsent",
            resource_dimension="entries",
            receiver="retained",
            field_path="retained",
            demand_inputs=(DemandInput("key", "key"),),
            escape_scope="instance",
            evidence_ids=frozenset({"fact:growth"}),
        )
        row = {
            "source_file": "src/Filter.java", "source_start_line": 10,
            "sink_file": "src/Service.java", "sink_start_line": 20,
            "coverage_status": "partial", "confidence": "partial",
            "coverage_note": "transitive_callgraph_association_requires_flow_witness",
        }
        links, disposition = production._candidate_association(
            {entry.entry_id: entry}, candidate, [row, dict(row)]
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].status, "partial")
        self.assertEqual(disposition.status, "unresolved")

    def test_repeatability_and_amplification_default_unknown(self) -> None:
        repeat = RepeatabilityDecision.create("repeatability", "entry:abc", "growth:abc", "unknown", ("entry:abc",), ("REPEATABILITY_TRIGGER_SEMANTICS_UNMODELED",))
        amplify = AmplificationDecision.create("amplification", "entry:abc", "growth:abc", "unknown", ("growth:abc",), ("AMPLIFICATION_LOOP_OR_BATCH_UNMODELED",))
        self.assertEqual(repeat.status, "unknown")
        self.assertEqual(amplify.status, "unknown")


if __name__ == "__main__":
    unittest.main()
