from __future__ import annotations

import unittest

from dosweb import production
from dosweb.entries import AttackerInputFact, EntryFact, HandlerFact, RegistrationFact
from dosweb.growth.completeness import CandidateEntryLink
from dosweb.growth.relevance import evaluate_candidate_relevance
from dosweb.growth.slices import (
    DemandInput,
    GrowthCandidate,
    SourceLocation,
    normalize_growth_rows,
)


class GrowthRelevanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact("fixture.Controller.handle", "src/Controller.java", 20),
            registration=RegistrationFact(
                "annotation_mapping", "fixture.Controller", "src/Controller.java", 18
            ),
            registration_pattern_id=(
                "entry-registration-coverage:"
                "spring_mvc:annotation_mapping:spring_annotation_mapping"
            ),
            route_or_event="POST /items",
            auth_context="unknown",
            attacker_inputs=(
                AttackerInputFact("body", "byte[]", "request_body"),
                AttackerInputFact("count", "int", "request_parameter"),
                AttackerInputFact("key", "String", "request_parameter"),
                AttackerInputFact("size", "int", "request_parameter"),
                AttackerInputFact("width", "int", "request_parameter"),
            ),
            materialization_phase="in_handler",
        )

    def _candidate(
        self,
        *,
        kind: str,
        operation: str,
        demand_name: str,
        demand_role: str,
        escape_scope: str,
        coverage: str = "complete",
        notes: tuple[str, ...],
        file: str = "src/Controller.java",
        dimension: str = "bytes",
        receiver: str = "fixture.Controller.resource",
        field_path: str = "resource",
    ) -> GrowthCandidate:
        return GrowthCandidate.create(
            site=SourceLocation(file, 24),
            kind=kind,  # type: ignore[arg-type]
            operation=operation,
            resource_dimension=dimension,  # type: ignore[arg-type]
            receiver=receiver,
            field_path=field_path,
            demand_inputs=(DemandInput(demand_name, demand_role),),  # type: ignore[arg-type]
            escape_scope=escape_scope,  # type: ignore[arg-type]
            evidence_ids=frozenset({"fact:candidate"}),
            coverage_status=coverage,  # type: ignore[arg-type]
            coverage_notes=notes,
        )

    def _decision(self, candidate: GrowthCandidate):
        link = CandidateEntryLink.create(
            candidate.growth_id,
            self.entry.entry_id,
            "complete",
            (candidate.growth_id, self.entry.entry_id),
            ("ASSOCIATION_QUERY_EVIDENCE",),
        )
        return evaluate_candidate_relevance(self.entry, candidate, (link,))

    def test_attacker_sized_array_is_eligible_but_partial_witness_stays_partial(self) -> None:
        complete = self._candidate(
            kind="direct_allocation",
            operation="array_creation",
            demand_name="size",
            demand_role="size",
            escape_scope="request",
            notes=("direct_allocation:request_derived_size",),
        )
        partial = self._candidate(
            kind="direct_allocation",
            operation="array_creation",
            demand_name="size",
            demand_role="size",
            escape_scope="request",
            coverage="partial",
            notes=("direct_allocation:request_derived_size_partial",),
        )

        self.assertEqual("contract_eligible", self._decision(complete).status)
        self.assertEqual("large_single_request", self._decision(complete).amplification_class)
        self.assertEqual("dos_relevant_partial", self._decision(partial).status)

    def test_server_sized_array_is_rejected(self) -> None:
        candidate = self._candidate(
            kind="direct_allocation",
            operation="array_creation",
            demand_name="serverLimit",
            demand_role="size",
            escape_scope="request",
            notes=("direct_allocation:server_metadata_size",),
        )
        decision = self._decision(candidate)
        self.assertEqual("rejected", decision.status)
        self.assertIn("RELEVANCE_SERVER_SIZED_ALLOCATION", decision.reason_codes)

    def test_compile_time_fixed_allocation_is_rejected_as_server_controlled(self) -> None:
        candidate = self._candidate(
            kind="direct_allocation",
            operation="array_creation",
            demand_name="1",
            demand_role="size",
            escape_scope="request",
            notes=("direct_allocation:server_controlled_fixed_size",),
        )

        decision = self._decision(candidate)

        self.assertEqual("rejected", decision.status)
        self.assertIn("RELEVANCE_SERVER_SIZED_ALLOCATION", decision.reason_codes)

    def test_mixed_attacker_and_fixed_dimensions_survive_normalization_and_relevance(self) -> None:
        common: dict[str, object] = {
            "site_file": "src/Controller.java",
            "site_start_line": 24,
            "growth_kind": "direct_allocation",
            "operation": "java.awt.image.BufferedImage.<init>",
            "resource_dimension": "bytes",
            "receiver": "java.awt.image.BufferedImage",
            "field_path": "allocation",
            "demand_input_role": "size",
            "escape_scope": "request",
            "coverage_status": "complete",
            "query_name": "DirectAllocation.ql",
            "query_sha256": "a" * 64,
            "site_location": "src/Controller.java:24",
        }
        rows = (
            {
                **common,
                "demand_input_name": "width",
                "candidate_evidence": "image_dimension_size",
                "coverage_note": "direct_allocation:handler_parameter_size",
            },
            {
                **common,
                "demand_input_name": "1",
                "candidate_evidence": "image_dimension_fixed_height",
                "coverage_note": "direct_allocation:server_controlled_fixed_size",
            },
        )

        normalized = normalize_growth_rows(rows)

        self.assertEqual(len(normalized), 1)
        candidate = GrowthCandidate.from_dict(normalized[0])
        self.assertEqual(
            {(item.name, item.role) for item in candidate.demand_inputs},
            {("width", "size"), ("1", "size")},
        )
        self.assertEqual(
            set(candidate.coverage_notes),
            {
                "direct_allocation:handler_parameter_size",
                "direct_allocation:server_controlled_fixed_size",
            },
        )

        decision = self._decision(candidate)

        self.assertEqual("contract_eligible", decision.status)
        self.assertIn("RELEVANCE_ATTACKER_SIZED_ALLOCATION", decision.reason_codes)
        self.assertNotIn("RELEVANCE_SERVER_SIZED_ALLOCATION", decision.reason_codes)

    def test_fixed_size_marker_with_attacker_multiplicity_is_not_a_hard_negative(self) -> None:
        candidate = self._candidate(
            kind="direct_allocation",
            operation="array_creation",
            demand_name="1",
            demand_role="size",
            escape_scope="request",
            notes=(
                "direct_allocation:server_controlled_fixed_size",
                "direct_allocation:attacker_controlled_loop_multiplicity_proven",
            ),
        )

        decision = self._decision(candidate)

        self.assertNotEqual("rejected", decision.status)
        self.assertNotIn("RELEVANCE_SERVER_SIZED_ALLOCATION", decision.reason_codes)

    def test_fixed_size_marker_with_unmodeled_loop_is_not_a_hard_negative(self) -> None:
        candidate = self._candidate(
            kind="direct_allocation",
            operation="array_creation",
            demand_name="1",
            demand_role="size",
            escape_scope="request",
            coverage="partial",
            notes=(
                "direct_allocation:server_controlled_fixed_size",
                "direct_allocation:loop_multiplicity_unmodeled",
            ),
        )

        decision = self._decision(candidate)

        self.assertNotEqual("rejected", decision.status)
        self.assertNotIn("RELEVANCE_SERVER_SIZED_ALLOCATION", decision.reason_codes)

    def test_all_fixed_dimensions_own_the_exact_server_controlled_negative_proof(self) -> None:
        common: dict[str, object] = {
            "site_file": "src/Controller.java",
            "site_start_line": 24,
            "growth_kind": "direct_allocation",
            "operation": "array_creation",
            "resource_dimension": "bytes",
            "receiver": "byte[][]",
            "field_path": "allocation",
            "demand_input_role": "size",
            "escape_scope": "request",
            "coverage_status": "complete",
            "coverage_note": "direct_allocation:server_controlled_fixed_size",
            "query_name": "DirectAllocation.ql",
            "query_sha256": "a" * 64,
            "site_location": "src/Controller.java:24",
        }
        normalized = normalize_growth_rows(
            (
                {
                    **common,
                    "demand_input_name": "1",
                    "candidate_evidence": "array_first_dimension",
                },
                {
                    **common,
                    "demand_input_name": "2",
                    "candidate_evidence": "array_second_dimension",
                },
            )
        )
        self.assertEqual(len(normalized), 1)
        candidate = GrowthCandidate.from_dict(normalized[0])

        decision = self._decision(candidate)

        self.assertEqual(decision.status, "rejected")
        self.assertEqual(
            decision.reason_codes,
            ("RELEVANCE_SERVER_SIZED_ALLOCATION",),
        )
        proof = production._negative_proof_for_relevance(  # noqa: SLF001
            candidate,
            decision.reason_codes,
        )
        self.assertEqual(proof.kind, "server_controlled_source")
        self.assertEqual(proof.evidence_ids, tuple(sorted(candidate.evidence_ids)))
        self.assertEqual(proof.reason_codes, ("NEGATIVE_SERVER_CONTROLLED_SOURCE",))

    def test_request_string_and_bytes_materialization_are_eligible(self) -> None:
        for operation, note in (
            ("spring_request_body_materialization", "recognized_spring_request_body_bytes"),
            ("spring_request_body_string_materialization", "recognized_spring_request_body_string"),
        ):
            with self.subTest(operation=operation):
                candidate = self._candidate(
                    kind="input_materialization",
                    operation=operation,
                    demand_name="body",
                    demand_role="size",
                    escape_scope="request",
                    notes=(note,),
                )
                self.assertEqual("contract_eligible", self._decision(candidate).status)

    def test_server_file_read_is_rejected(self) -> None:
        candidate = self._candidate(
            kind="input_materialization",
            operation="java.nio.file.Files.readAllBytes",
            demand_name="path",
            demand_role="size",
            escape_scope="request",
            notes=("server_side_file_materialization",),
        )
        self.assertEqual("rejected", self._decision(candidate).status)

    def test_field_backed_high_cardinality_map_is_eligible(self) -> None:
        candidate = self._candidate(
            kind="container_growth",
            operation="java.util.Map.put",
            demand_name="key",
            demand_role="key",
            escape_scope="global",
            notes=("persistent_field_container_write:attacker_key_driver",),
            dimension="entries",
            field_path="items",
        )
        decision = self._decision(candidate)
        self.assertEqual("contract_eligible", decision.status)
        self.assertEqual("high_cardinality_retention", decision.amplification_class)

    def test_fixed_key_map_is_rejected(self) -> None:
        candidate = self._candidate(
            kind="container_growth",
            operation="java.util.Map.put",
            demand_name='"fixed"',
            demand_role="key",
            escape_scope="global",
            notes=("persistent_field_container_write:fixed_key",),
            dimension="entries",
        )
        self.assertEqual("rejected", self._decision(candidate).status)

    def test_request_local_container_without_cardinality_bound_is_unresolved(self) -> None:
        candidate = self._candidate(
            kind="container_growth",
            operation="java.util.Map.put",
            demand_name="key",
            demand_role="key",
            escape_scope="request",
            notes=("request_local_container_write:attacker_key_driver",),
            dimension="entries",
            receiver="local",
            field_path="local",
        )
        decision = self._decision(candidate)
        self.assertEqual("unresolved", decision.status)
        self.assertIn("RELEVANCE_REQUEST_LOCAL_CARDINALITY_UNPROVEN", decision.reason_codes)

    def test_request_local_container_with_attacker_loop_witness_is_eligible(self) -> None:
        candidate = self._candidate(
            kind="container_growth",
            operation="java.util.Map.put",
            demand_name="count",
            demand_role="iteration_count",
            escape_scope="request",
            notes=(
                "request_local_container_write:key_driver_unclassified:"
                "attacker_controlled_loop_cardinality_proven",
            ),
            dimension="entries",
            receiver="local",
            field_path="local",
        )

        decision = self._decision(candidate)

        self.assertEqual("contract_eligible", decision.status)
        self.assertEqual("superlinear", decision.amplification_class)
        self.assertIn(
            "RELEVANCE_ATTACKER_CARDINALITY_REQUEST_LOCAL",
            decision.reason_codes,
        )

    def test_request_local_loop_without_stable_new_entry_witness_is_unresolved(self) -> None:
        for reason in (
            "attacker_controlled_loop_new_entry_unproven",
            "attacker_controlled_loop_instance_stability_unproven",
            "attacker_controlled_loop_per_iteration_execution_unproven",
        ):
            with self.subTest(reason=reason):
                candidate = self._candidate(
                    kind="container_growth",
                    operation="java.util.Map.put",
                    demand_name="count",
                    demand_role="key",
                    escape_scope="request",
                    coverage="partial",
                    notes=(f"request_local_container_write:attacker_key_driver:{reason}",),
                    dimension="entries",
                    receiver="local",
                    field_path="local",
                )

                decision = self._decision(candidate)

                self.assertEqual("unresolved", decision.status)
                self.assertIn(
                    "RELEVANCE_REQUEST_LOCAL_CARDINALITY_UNPROVEN",
                    decision.reason_codes,
                )

    def test_request_local_old_multiplicity_marker_does_not_prove_cardinality(self) -> None:
        candidate = self._candidate(
            kind="container_growth",
            operation="java.util.Map.put",
            demand_name="count",
            demand_role="key",
            escape_scope="request",
            notes=(
                "request_local_container_write:attacker_key_driver:"
                "attacker_controlled_loop_multiplicity_proven",
            ),
            dimension="entries",
            receiver="local",
            field_path="local",
        )

        decision = self._decision(candidate)

        self.assertEqual("unresolved", decision.status)
        self.assertIn(
            "RELEVANCE_REQUEST_LOCAL_CARDINALITY_UNPROVEN",
            decision.reason_codes,
        )

    def test_request_local_cardinality_marker_requires_one_exact_structured_note(self) -> None:
        approximate_notes = (
            (
                "request_local_container_write:key_driver_unclassified:"
                "attacker_controlled_loop_cardinality_proven_but_unproven",
            ),
            (
                "prefix:request_local_container_write:key_driver_unclassified:"
                "attacker_controlled_loop_cardinality_proven",
            ),
            (
                "request_local_container_write:key_driver_unclassified:"
                "attacker_controlled_loop_cardinality_proven:suffix",
            ),
            (
                "request_local_container_write:key_driver_unclassified",
                "attacker_controlled_loop_cardinality_proven",
            ),
            (
                "request_local_container_write:attacker_key_driver:"
                "attacker_controlled_loop_cardinality_proven",
            ),
        )
        for notes in approximate_notes:
            with self.subTest(notes=notes):
                candidate = self._candidate(
                    kind="container_growth",
                    operation="java.util.Map.put",
                    demand_name="index",
                    demand_role="key",
                    escape_scope="request",
                    notes=notes,
                    dimension="entries",
                    receiver="local",
                    field_path="local",
                )

                decision = self._decision(candidate)

                self.assertEqual("unresolved", decision.status)
                self.assertIn(
                    "RELEVANCE_REQUEST_LOCAL_CARDINALITY_UNPROVEN",
                    decision.reason_codes,
                )

    def test_complete_finite_keyspace_is_rejected(self) -> None:
        candidate = self._candidate(
            kind="container_growth",
            operation="java.util.Map.put",
            demand_name="kind",
            demand_role="key",
            escape_scope="global",
            notes=("persistent_field_container_write:finite_enum_keyspace",),
            dimension="entries",
        )
        decision = self._decision(candidate)
        self.assertEqual("rejected", decision.status)
        self.assertIn("RELEVANCE_FINITE_KEYSPACE", decision.reason_codes)

    def test_single_session_fixed_attribute_stays_unresolved(self) -> None:
        candidate = self._candidate(
            kind="container_growth",
            operation="javax.servlet.http.HttpSession.setAttribute",
            demand_name="body",
            demand_role="value",
            escape_scope="session",
            coverage="partial",
            notes=("http_session_attribute_write:fixed_attribute_fresh_session_unproven",),
            dimension="objects",
            field_path='"captcha"',
        )
        decision = self._decision(candidate)
        self.assertEqual("unresolved", decision.status)
        self.assertEqual("low_amplification", decision.amplification_class)

    def test_looped_queue_submission_is_eligible(self) -> None:
        candidate = self._candidate(
            kind="async_work_growth",
            operation="java.util.concurrent.ExecutorService.submit",
            demand_name="count",
            demand_role="submission_count",
            escape_scope="instance",
            notes=("queue_capacity_unbounded:attacker_controlled_loop_multiplicity_proven",),
            dimension="tasks",
            field_path="executor",
        )
        decision = self._decision(candidate)
        self.assertEqual("contract_eligible", decision.status)
        self.assertEqual("queue_instability", decision.amplification_class)

    def test_one_shot_schedule_is_retained_for_repeatability_and_capacity_analysis(self) -> None:
        candidate = self._candidate(
            kind="async_work_growth",
            operation="java.util.concurrent.ScheduledExecutorService.schedule",
            demand_name="task",
            demand_role="value",
            escape_scope="instance",
            notes=("queue_capacity_complete:single_submission_no_enclosing_loop",),
            dimension="tasks",
            field_path="scheduler",
        )
        decision = self._decision(candidate)
        self.assertEqual("dos_relevant_partial", decision.status)
        self.assertEqual("queue_instability", decision.amplification_class)
        self.assertIn(
            "RELEVANCE_QUEUE_CAPACITY_OR_MULTIPLICITY_PARTIAL",
            decision.reason_codes,
        )

    def test_test_or_benchmark_only_sink_is_rejected(self) -> None:
        candidate = self._candidate(
            kind="direct_allocation",
            operation="array_creation",
            demand_name="size",
            demand_role="size",
            escape_scope="request",
            notes=("direct_allocation:request_derived_size",),
            file="src/test/java/fixture/AllocationBenchmark.java",
        )
        decision = self._decision(candidate)
        self.assertEqual("rejected", decision.status)
        self.assertIn("RELEVANCE_TEST_OR_BENCHMARK_ONLY", decision.reason_codes)

    def test_link_fanout_is_unresolved_instead_of_failing_the_target(self) -> None:
        candidate = self._candidate(
            kind="direct_allocation",
            operation="array_creation",
            demand_name="size",
            demand_role="size",
            escape_scope="request",
            notes=("direct_allocation:request_derived_size",),
        )
        links = tuple(
            CandidateEntryLink.create(
                candidate.growth_id,
                f"entry:{index}",
                "partial",
                (candidate.growth_id, f"entry:{index}"),
                ("ASSOCIATION_QUERY",),
            )
            for index in range(65)
        )
        decision = evaluate_candidate_relevance(self.entry, candidate, links)
        self.assertEqual("unresolved", decision.status)
        self.assertIn("RELEVANCE_LINK_FANOUT_EXCEEDED", decision.reason_codes)

    def test_production_package_named_test_is_not_mislabeled_test_only(self) -> None:
        candidate = self._candidate(
            kind="input_materialization",
            operation="spring_request_body_materialization",
            demand_name="body",
            demand_role="size",
            escape_scope="request",
            notes=("recognized_spring_request_body_bytes",),
            file="src/main/java/com/example/test/ProductionController.java",
        )
        self.assertEqual("contract_eligible", self._decision(candidate).status)


if __name__ == "__main__":
    unittest.main()
