from __future__ import annotations

import unittest

from dosweb.growth.completeness import CandidateDisposition, CandidateEntryLink, RepeatabilityDecision, AmplificationDecision
from dosweb.growth import DemandInput, GrowthCandidate, SourceLocation
from dosweb.entries import EntryFact
from dosweb import production


class CandidateCompletenessTests(unittest.TestCase):
    def _netty_route_alias_entries(
        self,
        *,
        beat_changes: dict[str, object] | None = None,
    ) -> tuple[EntryFact, EntryFact, EntryFact]:
        common = {
            "framework": "netty",
            "protocol": "tcp",
            "handler_fqn": "fixture.netty.FullRequestHandler.channelRead0",
            "handler_file": "fixture/netty/NettyFixture.java",
            "handler_start_line": 74,
            "registration_kind": "pipeline_registration",
            "registration_fqn": "fixture.netty.NettyFixture.initChannel",
            "registration_file": "fixture/netty/NettyFixture.java",
            "registration_start_line": 24,
            "auth_context": "unknown",
            "attacker_input_name": "request",
            "attacker_input_type": "FullHttpRequest",
            "attacker_input_kind": "message_payload",
            "materialization_phase": "streaming",
            "coverage_status": "complete",
        }
        return (
            EntryFact.from_raw(
                {
                    **common,
                    "route_or_event": "channelRead",
                    "coverage_note": "netty_pipeline_registration",
                }
            ),
            EntryFact.from_raw(
                {
                    **common,
                    "route_or_event": "/beat",
                    "coverage_note": "netty_source_switch_route_alias",
                    **(beat_changes or {}),
                }
            ),
            EntryFact.from_raw(
                {
                    **common,
                    "route_or_event": "/trigger",
                    "coverage_note": "netty_source_switch_route_alias",
                }
            ),
        )

    def test_route_qualified_association_selects_only_the_matching_alias(self) -> None:
        base, beat, trigger = self._netty_route_alias_entries()
        candidate = GrowthCandidate.create(
            site=SourceLocation("fixture/netty/NettyFixture.java", 118),
            kind="container_growth",
            operation="java.util.List.add",
            resource_dimension="entries",
            receiver="fixture.netty.TriggerStore.requests",
            field_path="requests",
            demand_inputs=(DemandInput("request", "value"),),
            escape_scope="instance",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_status="partial",
            coverage_notes=("persistent_field_container_write:value_driver_unclassified",),
        )
        row = {
            "source_file": trigger.handler.file,
            "source_start_line": trigger.handler.start_line,
            "sink_file": candidate.site.file,
            "sink_start_line": candidate.site.start_line,
            "attacker_target": "value",
            "attacker_source": trigger.handler.callable,
            "attacker_sink": "request",
            "call_path": (
                "fixture.netty.FullRequestHandler.channelRead0[/trigger]>"
                "fixture.netty.TriggerServiceImpl.trigger>"
                "fixture.netty.TriggerStore.push"
            ),
            "phase_sequence": "entry>netty_json_switch>async>service>growth",
            "flow_kind": "data_flow",
            "confidence": "partial",
            "coverage_status": "partial",
            "coverage_note": "netty_json_switch_async_dispatch_requires_path_coverage",
        }

        links, disposition = production._candidate_association(  # noqa: SLF001
            {entry.entry_id: entry for entry in (base, beat, trigger)},
            candidate,
            (row,),
            (row,),
        )

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].entry_id, trigger.entry_id)
        self.assertEqual(links[0].status, "partial")
        self.assertEqual(disposition.status, "gap_eligible")
        self.assertEqual(disposition.canonical_entry_id, trigger.entry_id)

    def test_same_handler_association_uses_base_entry_not_route_alias_fanout(self) -> None:
        base, beat, trigger = self._netty_route_alias_entries()
        candidate = GrowthCandidate.create(
            site=SourceLocation("fixture/netty/NettyFixture.java", 76),
            kind="input_materialization",
            operation="netty_full_http_request_string_materialization",
            resource_dimension="bytes",
            receiver="content(...)",
            field_path="request",
            demand_inputs=(DemandInput("request", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_notes=("recognized_netty_full_http_request_string_materialization",),
        )
        association = {
            "source_file": base.handler.file,
            "source_start_line": base.handler.start_line,
            "sink_file": candidate.site.file,
            "sink_start_line": candidate.site.start_line,
            "attacker_target": "size",
            "attacker_source": base.handler.callable,
            "attacker_sink": "request",
            "call_path": base.handler.callable,
            "phase_sequence": "entry>global_dataflow>growth",
            "flow_kind": "data_flow",
            "confidence": "proven",
            "coverage_status": "complete",
            "coverage_note": "same_handler_global_dataflow",
        }
        flow = {**association, "attacker_source": "request"}

        links, disposition = production._candidate_association(  # noqa: SLF001
            {entry.entry_id: entry for entry in (base, beat, trigger)},
            candidate,
            (association,),
            (flow,),
        )

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].entry_id, base.entry_id)
        self.assertEqual(links[0].status, "complete")
        self.assertEqual(disposition.status, "formal_eligible")
        self.assertEqual(disposition.canonical_entry_id, base.entry_id)

    def test_same_handler_base_canonicalization_requires_every_entry_identity_dimension(self) -> None:
        cases = {
            "handler": {"handler_fqn": "fixture.netty.OtherHandler.channelRead0"},
            "registration_site": {"registration_start_line": 25},
            "auth": {"auth_context": "privileged"},
            "input": {"attacker_input_type": "ByteBuf"},
            "materialization": {"materialization_phase": "in_handler"},
        }
        for dimension, changes in cases.items():
            with self.subTest(dimension=dimension):
                base, beat, trigger = self._netty_route_alias_entries(
                    beat_changes=changes
                )
                candidate = GrowthCandidate.create(
                    site=SourceLocation("fixture/netty/NettyFixture.java", 76),
                    kind="input_materialization",
                    operation="netty_full_http_request_string_materialization",
                    resource_dimension="bytes",
                    receiver="content(...)",
                    field_path="request",
                    demand_inputs=(DemandInput("request", "size"),),
                    escape_scope="request",
                    evidence_ids=frozenset({"fact:growth"}),
                    coverage_notes=(
                        "recognized_netty_full_http_request_string_materialization",
                    ),
                )
                association = {
                    "source_file": base.handler.file,
                    "source_start_line": base.handler.start_line,
                    "sink_file": candidate.site.file,
                    "sink_start_line": candidate.site.start_line,
                    "attacker_target": "size",
                    "attacker_source": base.handler.callable,
                    "attacker_sink": "request",
                    "call_path": base.handler.callable,
                    "phase_sequence": "entry>global_dataflow>growth",
                    "flow_kind": "data_flow",
                    "confidence": "proven",
                    "coverage_status": "complete",
                    "coverage_note": "same_handler_global_dataflow",
                }
                flow = {**association, "attacker_source": "request"}

                links, disposition = production._candidate_association(  # noqa: SLF001
                    {entry.entry_id: entry for entry in (base, beat, trigger)},
                    candidate,
                    (association,),
                    (flow,),
                )

                self.assertGreater(len(links), 1)
                self.assertEqual(disposition.status, "inventory_unresolved")
                self.assertEqual(disposition.association_status, "ambiguous")
                self.assertEqual(disposition.canonical_entry_id, "")

    def test_same_handler_base_canonicalization_requires_uniform_link_status(self) -> None:
        base, beat, trigger = self._netty_route_alias_entries()
        candidate = GrowthCandidate.create(
            site=SourceLocation("fixture/netty/NettyFixture.java", 76),
            kind="input_materialization",
            operation="netty_full_http_request_string_materialization",
            resource_dimension="bytes",
            receiver="content(...)",
            field_path="request",
            demand_inputs=(DemandInput("request", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
            coverage_notes=(
                "recognized_netty_full_http_request_string_materialization",
            ),
        )
        complete = {
            "source_file": base.handler.file,
            "source_start_line": base.handler.start_line,
            "sink_file": candidate.site.file,
            "sink_start_line": candidate.site.start_line,
            "attacker_target": "size",
            "attacker_source": base.handler.callable,
            "attacker_sink": "request",
            "call_path": base.handler.callable,
            "phase_sequence": "entry>global_dataflow>growth",
            "flow_kind": "data_flow",
            "confidence": "proven",
            "coverage_status": "complete",
            "coverage_note": "same_handler_global_dataflow",
        }
        partial = {
            **complete,
            "confidence": "partial",
            "coverage_status": "partial",
            "coverage_note": "same_handler_path_partial",
        }
        flow = {**complete, "attacker_source": "request"}

        links, disposition = production._candidate_association(  # noqa: SLF001
            {entry.entry_id: entry for entry in (base, beat, trigger)},
            candidate,
            (complete, partial),
            (flow,),
        )

        self.assertEqual({link.status for link in links}, {"complete", "partial"})
        self.assertEqual(disposition.status, "inventory_unresolved")
        self.assertEqual(disposition.association_status, "ambiguous")
        self.assertEqual(disposition.canonical_entry_id, "")

    def test_unmapped_complete_candidate_is_audited_not_silently_dropped(self) -> None:
        disposition = CandidateDisposition.create(
            "growth:abc", "inventory_unresolved",
            canonical_entry_id="", local_growth_status="complete",
            association_status="missing", link_ids=(),
            evidence_ids=("fact:growth",), negative_proof_ids=(),
            reason_codes=("ASSOCIATION_NO_ENTRY_COMPLETE",),
        )
        self.assertEqual(disposition.status, "inventory_unresolved")
        self.assertEqual(disposition.link_ids, ())

    def test_partial_link_cannot_be_promoted_to_verified_relevant(self) -> None:
        link = CandidateEntryLink.create("growth:abc", "entry:abc", "partial", ("entry:abc", "growth:abc"), ("ASSOCIATION_CALL_GRAPH_UNAVAILABLE",))
        unresolved = CandidateDisposition.create(
            "growth:abc", "gap_eligible",
            canonical_entry_id="entry:abc", local_growth_status="complete",
            association_status="partial", link_ids=(link.link_id,),
            evidence_ids=("fact:growth", link.link_id), negative_proof_ids=(),
            reason_codes=("ASSOCIATION_CALL_GRAPH_UNAVAILABLE",),
        )
        self.assertEqual(unresolved.status, "gap_eligible")
        self.assertEqual(link.status, "partial")

        second = CandidateEntryLink.create(
            "growth:abc",
            "entry:def",
            "complete",
            ("entry:def", "growth:abc"),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        with self.assertRaises(Exception):
            CandidateDisposition.create(
                "growth:abc",
                "formal_eligible",
                canonical_entry_id="entry:abc", local_growth_status="complete",
                association_status="complete", link_ids=(link.link_id, second.link_id),
                evidence_ids=("fact:growth",), negative_proof_ids=(),
                reason_codes=("ASSOCIATION_QUERY_EVIDENCE",),
            )

    def test_gap_eligible_is_distinct_and_requires_one_canonical_link(self) -> None:
        link = CandidateEntryLink.create(
            "growth:abc",
            "entry:abc",
            "partial",
            ("entry:abc", "growth:abc"),
            ("ASSOCIATION_CALL_GRAPH_UNAVAILABLE",),
        )
        disposition = CandidateDisposition.create(
            "growth:abc",
            "gap_eligible",
            canonical_entry_id="entry:abc", local_growth_status="partial",
            association_status="partial", link_ids=(link.link_id,),
            evidence_ids=("fact:growth", link.link_id), negative_proof_ids=(),
            reason_codes=("MATURATION_GAP_ELIGIBLE",),
        )
        self.assertEqual(disposition.status, "gap_eligible")
        with self.assertRaises(Exception):
            CandidateDisposition.create(
                "growth:abc",
                "gap_eligible",
                canonical_entry_id="", local_growth_status="partial",
                association_status="partial", link_ids=(),
                evidence_ids=("fact:growth",), negative_proof_ids=(),
                reason_codes=("MATURATION_GAP_ELIGIBLE",),
            )

    def test_no_entry_association_is_unresolved_without_entry_coverage_proof(self) -> None:
        candidate = GrowthCandidate.create(site=SourceLocation("src/Detached.java", 9), kind="direct_allocation", operation="new byte[8]", resource_dimension="bytes", receiver="byte[]", field_path="allocation", demand_inputs=(DemandInput("size", "size"),), escape_scope="request", evidence_ids=frozenset({"fact:growth"}))
        links, disposition = production._candidate_association({}, candidate)  # noqa: SLF001
        self.assertEqual(links, ())
        self.assertEqual(disposition.status, "inventory_unresolved")
        self.assertIn("ASSOCIATION_ENTRY_COVERAGE_UNPROVEN", disposition.reason_codes)

    def test_source_order_fanout_is_partitioned_to_the_nearest_handler(self) -> None:
        entries = {}
        for index in range(65):
            entry = EntryFact.from_raw({
                "framework": "servlet", "protocol": "http",
                "handler_fqn": f"Handler{index}.service", "handler_file": "src/App.java",
                "handler_start_line": index + 1,
                "registration_kind": "static_registration",
                "registration_fqn": f"Config{index}.setServlet",
                "registration_file": f"src/Config{index}.java", "registration_start_line": 5,
                "route_or_event": f"/api/{index}", "auth_context": "unknown",
                "attacker_input_name": "request", "attacker_input_type": "ServletRequest",
                "attacker_input_kind": "stream", "materialization_phase": "before_handler",
                "coverage_status": "complete", "coverage_note": "web_xml_servlet_mapping",
            })
            entries[entry.entry_id] = entry
        candidate = GrowthCandidate.create(
            site=SourceLocation("src/App.java", 80),
            kind="direct_allocation",
            operation="new byte[size]",
            resource_dimension="bytes",
            receiver="byte[]",
            field_path="allocation",
            demand_inputs=(DemandInput("size", "size"),),
            escape_scope="request",
            evidence_ids=frozenset({"fact:growth"}),
        )
        links, disposition = production._candidate_association(entries, candidate)  # noqa: SLF001
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].entry_id, entries[next(
            key for key, value in entries.items() if value.handler.start_line == 65
        )].entry_id)
        self.assertEqual(disposition.status, "gap_eligible")
        self.assertEqual(disposition.canonical_entry_id, links[0].entry_id)

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
        self.assertEqual(disposition.status, "gap_eligible")

    def test_repeatability_and_amplification_default_unknown(self) -> None:
        repeat = RepeatabilityDecision.create("repeatability", "entry:abc", "growth:abc", "unknown", ("entry:abc",), ("REPEATABILITY_TRIGGER_SEMANTICS_UNMODELED",))
        amplify = AmplificationDecision.create("amplification", "entry:abc", "growth:abc", "unknown", ("growth:abc",), ("AMPLIFICATION_LOOP_OR_BATCH_UNMODELED",))
        self.assertEqual(repeat.status, "unknown")
        self.assertEqual(amplify.status, "unknown")

    def test_conclusion_pairs_include_only_formal_or_gap_eligible(self) -> None:
        verified_link = CandidateEntryLink.create(
            "growth:verified",
            "entry:verified",
            "complete",
            ("entry:verified", "growth:verified"),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        partial_link = CandidateEntryLink.create(
            "growth:partial",
            "entry:partial",
            "partial",
            ("entry:partial", "growth:partial"),
            ("ASSOCIATION_CALL_GRAPH_UNAVAILABLE",),
        )
        generic_link = CandidateEntryLink.create(
            "growth:generic",
            "entry:generic",
            "partial",
            ("entry:generic", "growth:generic"),
            ("ASSOCIATION_CALL_GRAPH_UNAVAILABLE",),
        )
        dispositions = (
            CandidateDisposition.create(
                "growth:verified",
                "formal_eligible",
                canonical_entry_id="entry:verified", local_growth_status="complete",
                association_status="complete", link_ids=(verified_link.link_id,),
                evidence_ids=("fact:verified", verified_link.link_id), negative_proof_ids=(),
                reason_codes=("MATURATION_FORMAL_ELIGIBLE",),
            ),
            CandidateDisposition.create(
                "growth:partial",
                "gap_eligible",
                canonical_entry_id="entry:partial", local_growth_status="partial",
                association_status="partial", link_ids=(partial_link.link_id,),
                evidence_ids=("fact:partial", partial_link.link_id), negative_proof_ids=(),
                reason_codes=("MATURATION_GAP_ELIGIBLE",),
            ),
            CandidateDisposition.create(
                "growth:generic",
                "inventory_unresolved",
                canonical_entry_id="", local_growth_status="unknown",
                association_status="ambiguous", link_ids=(generic_link.link_id,),
                evidence_ids=("fact:generic", generic_link.link_id), negative_proof_ids=(),
                reason_codes=("RELEVANCE_CANONICAL_ENTRY_UNPROVEN",),
            ),
            CandidateDisposition.create(
                "growth:rejected",
                "rejected",
                canonical_entry_id="", local_growth_status="rejected",
                association_status="missing", link_ids=(),
                evidence_ids=("fact:rejected", "negative_proof:rejected"),
                negative_proof_ids=("negative_proof:rejected",),
                reason_codes=("RELEVANCE_SERVER_SIZED_ALLOCATION",),
            ),
        )
        pairs, statuses = production._eligible_conclusion_pairs(  # noqa: SLF001
            tuple(item.to_dict() for item in dispositions),
            tuple(
                item.to_dict()
                for item in (verified_link, partial_link, generic_link)
            ),
            {
                ("entry:verified", "growth:verified"),
                ("entry:partial", "growth:partial"),
                ("entry:generic", "growth:generic"),
            },
        )
        self.assertEqual(
            pairs,
            {
                ("entry:verified", "growth:verified"),
                ("entry:partial", "growth:partial"),
            },
        )
        self.assertEqual(
            statuses,
            {
                ("entry:verified", "growth:verified"): "formal_eligible",
                ("entry:partial", "growth:partial"): "gap_eligible",
            },
        )


if __name__ == "__main__":
    unittest.main()
