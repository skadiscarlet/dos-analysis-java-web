from __future__ import annotations

import unittest

from dosweb.artifacts.schemas import validate_records
from dosweb.entries import EntryFact
from dosweb.flows import AttackerControl, FlowProof, normalize_flow_rows, verify_flow
from dosweb.growth import GrowthCandidate, VerificationCheck, VerifiedGrowthResult


class FlowVerificationTests(unittest.TestCase):
    def _entry(self) -> EntryFact:
        return EntryFact.from_raw({
            "framework": "spring_mvc", "protocol": "http",
            "handler_fqn": "fixture.spring.SpringFixture.create",
            "handler_file": "fixture/spring/SpringFixture.java", "handler_start_line": 15,
            "registration_kind": "annotation_mapping",
            "registration_fqn": "fixture.spring.SpringFixture.create",
            "registration_file": "fixture/spring/SpringFixture.java", "registration_start_line": 15,
            "route_or_event": "/items", "auth_context": "unauthenticated",
            "attacker_input_name": "limit", "attacker_input_type": "int",
            "attacker_input_kind": "request_parameter", "materialization_phase": "in_handler",
            "coverage_status": "complete", "coverage_note": "spring_annotation_mapping",
        })

    def _candidate(self) -> GrowthCandidate:
        return GrowthCandidate.from_raw({
            "site_file": "fixture/spring/SpringFixture.java", "site_start_line": 18,
            "growth_kind": "direct_allocation", "operation": "java.nio.ByteBuffer.allocate",
            "resource_dimension": "bytes", "receiver": "java.nio.ByteBuffer",
            "field_path": "allocation", "demand_input_name": "limit", "demand_input_role": "size",
            "escape_scope": "request", "candidate_evidence": "allocation",
            "coverage_status": "complete", "coverage_note": "direct allocation",
            "query_name": "growth", "query_sha256": "a" * 64,
            "site_location": "fixture/spring/SpringFixture.java:18",
        })

    def _growth(self, status: str = "verified") -> VerifiedGrowthResult:
        candidate = self._candidate()
        reasons = () if status == "verified" else ("GROWTH_CONTRACT_UNKNOWN",)
        checks = (VerificationCheck("resource_growth", status == "verified", None if status == "verified" else reasons[0]),)
        return VerifiedGrowthResult.create(candidate=candidate, slice_id="slice:fixture", status=status, reason_codes=reasons, checks=checks)

    def _raw(self, **changes: object) -> dict[str, object]:
        row: dict[str, object] = {
            "source_file": "fixture/spring/SpringFixture.java", "source_start_line": 15,
            "sink_file": "fixture/spring/SpringFixture.java", "sink_start_line": 18,
            "attacker_target": "size", "attacker_source": "limit", "attacker_sink": "allocate(limit)",
            "call_path": "fixture.spring.SpringFixture.create",
            "phase_sequence": "in_handler>growth", "flow_kind": "local_data_flow",
            "confidence": "proven", "coverage_status": "complete", "coverage_note": "direct",
        }
        row.update(changes)
        return row

    def test_normalizes_and_verifies_proven_flow(self) -> None:
        entry = self._entry()
        growth = self._growth()
        records = normalize_flow_rows((self._raw(),), {entry.entry_id: entry}, {growth.growth_id: growth})
        self.assertEqual(len(records), 1)
        validate_records("flow_proofs", records)
        proof = FlowProof.from_dict(records[0])
        verified = verify_flow(proof, {entry.entry_id: entry}, {growth.growth_id: growth})
        self.assertEqual(verified.status, "verified")
        self.assertTrue(verified.satisfies_premise)
        self.assertTrue(
            {proof.path_id, entry.entry_id, growth.growth_id}.issubset(
                set(verified.evidence_ids)
            )
        )
        self.assertTrue(
            {"entry_source_location", "growth_sink_location", "call_path_edges"}.issubset(
                {check.name for check in verified.checks if check.passed}
            )
        )

    def test_verifier_rejects_substring_sink_and_unbound_call_path(self) -> None:
        entry = self._entry()
        growth = self._growth()
        substring_sink = FlowProof.create(
            entry_id=entry.entry_id,
            growth_id=growth.growth_id,
            attacker_control=AttackerControl("size", "limit", "unlimited"),
            call_path=(entry.handler.callable,),
            phase_sequence=("in_handler", "growth"),
            confidence="proven",
        )
        invalid_sink = verify_flow(
            substring_sink,
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )
        self.assertEqual(invalid_sink.status, "unresolved")
        self.assertIn("FLOW_SEMANTIC_MAPPING_INVALID", invalid_sink.reason_codes)

        wrong_path = FlowProof.create(
            entry_id=entry.entry_id,
            growth_id=growth.growth_id,
            attacker_control=AttackerControl("size", "limit", "allocate(limit)"),
            call_path=("fixture.Other.handle",),
            phase_sequence=("in_handler", "growth"),
            confidence="proven",
        )
        invalid_path = verify_flow(
            wrong_path,
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )
        self.assertEqual(invalid_path.status, "partial")
        self.assertIn("FLOW_CALL_PATH_ENTRY_MISMATCH", invalid_path.reason_codes)

        unbound_edge = FlowProof.create(
            entry_id=entry.entry_id,
            growth_id=growth.growth_id,
            attacker_control=AttackerControl("size", "limit", "allocate(limit)"),
            call_path=(entry.handler.callable, "fixture.Helper.allocate"),
            phase_sequence=("in_handler", "growth"),
            confidence="proven",
        )
        invalid_edge = verify_flow(
            unbound_edge,
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )
        self.assertEqual(invalid_edge.status, "partial")
        self.assertIn("FLOW_CALL_PATH_EDGE_INVALID", invalid_edge.reason_codes)

        oversized_line = FlowProof.create(
            entry_id=entry.entry_id,
            growth_id=growth.growth_id,
            attacker_control=AttackerControl("size", "limit", "allocate(limit)"),
            call_path=(
                entry.handler.callable,
                f"{entry.handler.callable}~fixture.Helper.allocate@src/Helper.java:{'9' * 5000}",
            ),
            phase_sequence=("in_handler", "growth"),
            confidence="proven",
        )
        oversized_result = verify_flow(
            oversized_line,
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )
        self.assertEqual(oversized_result.status, "partial")
        self.assertIn("FLOW_CALL_PATH_EDGE_INVALID", oversized_result.reason_codes)

    def test_partial_remains_audit_evidence(self) -> None:
        entry = self._entry()
        growth = self._growth()
        record = normalize_flow_rows((self._raw(confidence="partial", coverage_status="partial"),), {entry.entry_id: entry}, {growth.growth_id: growth})[0]
        result = verify_flow(FlowProof.from_dict(record), {entry.entry_id: entry}, {growth.growth_id: growth})
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.satisfies_premise)
        self.assertIn("FLOW_CONFIDENCE_PARTIAL", result.reason_codes)

    def test_distinct_route_registrations_publish_partial_flow_for_each_entry(self) -> None:
        first = self._entry()
        second = EntryFact.from_raw({
            "framework": "spring_mvc", "protocol": "http",
            "handler_fqn": "fixture.spring.SpringFixture.create",
            "handler_file": "fixture/spring/SpringFixture.java", "handler_start_line": 15,
            "registration_kind": "annotation_mapping",
            "registration_fqn": "fixture.spring.SpringFixture.create",
            "registration_file": "fixture/spring/SpringFixture.java", "registration_start_line": 16,
            "route_or_event": "/aliases", "auth_context": "unauthenticated",
            "attacker_input_name": "limit", "attacker_input_type": "int",
            "attacker_input_kind": "request_parameter", "materialization_phase": "in_handler",
            "coverage_status": "complete", "coverage_note": "spring_annotation_mapping",
        })
        growth = self._growth()
        records = normalize_flow_rows(
            (self._raw(),),
            {first.entry_id: first, second.entry_id: second},
            {growth.growth_id: growth},
        )
        self.assertEqual({record["entry_id"] for record in records}, {first.entry_id, second.entry_id})
        self.assertTrue(all(record["confidence"] == "partial" for record in records))
        self.assertTrue(all(record["coverage_status"] == "partial" for record in records))
        self.assertTrue(
            all(
                record["coverage_note"] == "multiple_route_registrations_require_path_coverage"
                for record in records
            )
        )

    def test_dangling_references_raise_stable_error(self) -> None:
        entry = self._entry()
        growth = self._growth()
        proof = FlowProof.create(
            entry_id=entry.entry_id, growth_id=growth.growth_id,
            attacker_control=AttackerControl("size", "limit", "allocate(limit)"),
            call_path=(entry.handler.callable,), phase_sequence=("in_handler", "growth"), confidence="proven",
        )
        for entries, growth_index in (({}, {growth.growth_id: growth}), ({entry.entry_id: entry}, {})):
            with self.subTest(entries=bool(entries)):
                with self.assertRaises(Exception) as raised:
                    verify_flow(proof, entries, growth_index)
                self.assertEqual(getattr(raised.exception, "code", None), "ANALYSIS_DANGLING_FACT_REFERENCE")

    def test_invalid_attacker_target_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            AttackerControl("objects", "body", "sink")

    def test_proven_flow_rejects_unmapped_source_and_incomplete_coverage(self) -> None:
        entry = self._entry()
        growth = self._growth()
        with self.assertRaises(Exception):
            normalize_flow_rows(
                (self._raw(attacker_source="body"),),
                {entry.entry_id: entry},
                {growth.growth_id: growth},
            )
        partial = normalize_flow_rows(
            (self._raw(coverage_status="partial", coverage_note="wrapper"),),
            {entry.entry_id: entry},
            {growth.growth_id: growth},
        )[0]
        self.assertEqual(partial["confidence"], "partial")

    def test_verified_flow_direct_construction_rejects_forged_identity(self) -> None:
        from dosweb.flows import FlowCheck, VerifiedFlow

        with self.assertRaises(Exception):
            VerifiedFlow(
                "verified_flow:forged", "flow:forged", self._entry().entry_id,
                self._growth().growth_id, "verified", (),
                (FlowCheck("proven_confidence", True),), (), (), None,
            )

    def test_flow_artifact_recomputes_path_identity(self) -> None:
        entry = self._entry()
        growth = self._growth()
        record = normalize_flow_rows((self._raw(),), {entry.entry_id: entry}, {growth.growth_id: growth})[0]
        forged = {**record, "path_id": "flow:forged"}
        with self.assertRaises(Exception):
            validate_records("flow_proofs", (forged,))

    def test_duplicate_path_id_rows_fail_closed_in_every_codeql_order(self) -> None:
        entry = self._entry()
        growth = self._growth()
        first = self._raw(
            confidence="partial",
            coverage_status="complete",
            coverage_note="first_codeql_row",
        )
        second = self._raw(
            confidence="partial",
            flow_kind="unmodeled",
            coverage_status="partial",
            coverage_note="second_codeql_row",
        )
        sequences = {
            "forward": (first, second),
            "reverse": (second, first),
            "identical": (first, first),
        }
        observed: set[tuple[str, str | None]] = set()
        for label, rows in sequences.items():
            with self.subTest(order=label):
                with self.assertRaises(Exception) as raised:
                    normalize_flow_rows(
                        rows,
                        {entry.entry_id: entry},
                        {growth.growth_id: growth},
                    )
                observed.add(
                    (
                        getattr(raised.exception, "code", ""),
                        getattr(raised.exception, "details", {}).get("reason"),
                    )
                )
        self.assertEqual(
            observed,
            {("ANALYSIS_FLOW_INVALID", "DUPLICATE_PATH_ID")},
        )


if __name__ == "__main__":
    unittest.main()
