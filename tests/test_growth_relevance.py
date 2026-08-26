from __future__ import annotations

import unittest

from dosweb.entries import AttackerInputFact, EntryFact, HandlerFact, RegistrationFact
from dosweb.growth.completeness import CandidateEntryLink
from dosweb.growth.relevance import evaluate_candidate_relevance
from dosweb.growth.slices import DemandInput, GrowthCandidate, SourceLocation


class GrowthRelevanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = EntryFact.create(
            framework="spring_mvc",
            protocol="http",
            handler=HandlerFact("fixture.Controller.handle", "src/Controller.java", 20),
            registration=RegistrationFact(
                "annotation_mapping", "fixture.Controller", "src/Controller.java", 18
            ),
            route_or_event="POST /items",
            auth_context="unknown",
            attacker_inputs=(
                AttackerInputFact("body", "byte[]", "request_body"),
                AttackerInputFact("count", "int", "request_parameter"),
                AttackerInputFact("key", "String", "request_parameter"),
                AttackerInputFact("size", "int", "request_parameter"),
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

    def test_one_shot_schedule_is_rejected(self) -> None:
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
        self.assertEqual("rejected", decision.status)
        self.assertEqual("low_amplification", decision.amplification_class)

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
