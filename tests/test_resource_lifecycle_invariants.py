from __future__ import annotations

from dataclasses import replace
import unittest

from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.invariants import InvariantCandidate, check_invariants
from dosweb.resource_lifecycle.models import (
    AbstractInstance,
    AnalysisBudget,
    Effect,
    Event,
    Holder,
    Program,
    ResourceFamily,
    Transition,
)
from dosweb.resource_lifecycle.solver import solve
from tests.test_resource_lifecycle_solver import effect, family, location, program_for


def candidate(**overrides) -> InvariantCandidate:
    values = {
        "candidate_id": "invariant:queue-capacity",
        "family_id": "family:stream",
        "dimension": "held_instances",
        "scope": "task_queue",
        "upper_bound": 4,
        "initial_holds": True,
        "transitions_preserve": True,
        "covers_writers": True,
        "atomic": True,
        "source_kind": "trusted_contract",
        "assumptions": ("executor implementation is BoundedAtomicExecutor",),
        "evidence_ids": ("contract:bounded-executor",),
        "executor_contract_id": "bounded-queue-capacity:4",
        "writer_holder_id": "holder:task",
        "writer_target_event_id": "event:queue",
    }
    values.update(overrides)
    if "upper_bound" in overrides and "executor_contract_id" not in overrides:
        values["executor_contract_id"] = f"bounded-queue-capacity:{values['upper_bound']}"
    return InvariantCandidate(**values)


def executor_contract(
    bound: int | str = 4,
    *,
    atomic: bool = True,
    source_kind: str = "trusted_contract",
) -> ExecutorContract:
    return ExecutorContract(
        contract_id=f"bounded-queue-capacity:{bound}",
        scheduling="queued",
        queue_capacity=bound,
        capacity_atomic=atomic,
        completion_drops_capture=False,
        rejection_drops_capture=True,
        cancellation="unknown",
        source_kind=source_kind,  # type: ignore[arg-type]
        version="executor-contract-v1",
        core_workers=1,
        max_workers=2,
        rejection_policy="abort",
        termination="unknown",
    )


def check_with_contract(
    program: Program,
    result: object,
    candidates: tuple[InvariantCandidate, ...],
    *,
    timeout_ms: int = 100,
    contract_bound: int | str = 4,
):
    return check_invariants(
        program,
        result,  # type: ignore[arg-type]
        candidates,
        timeout_ms=timeout_ms,
        executor_contracts=(executor_contract(contract_bound),),
    )


def _dispatch_effect(instance_id: str, *, bound: int | str = 4) -> Effect:
    return Effect(
        effect_id=f"effect:dispatch:{instance_id}",
        kind="dispatch",
        instance_id=instance_id,
        family_id="family:stream",
        holder_id="holder:task",
        target_event_id="event:queue",
        condition="accepted",
        location=location(),
        evidence_ids=(f"fact:dispatch:{instance_id}",),
        contract_id=f"bounded-queue-capacity:{bound}",
    )


def solved(*, known_size: bool = True, contract_bound: int | str = 4):
    effects = (effect("create"), _dispatch_effect("instance:stream", bound=contract_bound), effect("release"))
    transitions = (
        Transition(
            "transition:normal",
            "event:entry",
            "event:normal",
            "normal",
            effects,
            "normal",
            (),
        ),
        Transition(
            "transition:error",
            "event:entry",
            "event:error",
            "exceptional",
            effects,
            "exceptional",
            (),
        ),
    )
    base = program_for(())
    resource = family()
    resource = ResourceFamily(
        resource.family_id,
        resource.allocation,
        resource.context,
        resource.resource_type,
        resource.requires_close,
        1024 if known_size else None,
    )
    program = Program(
        base.schema_version,
        (resource,),
        base.instances,
        base.holders + (Holder("holder:task", "task", "task", "exact"),),
        base.events + (Event("event:queue", "task_queue", "Fixture.handle#queue", "accepted"),),
        transitions,
        base.entry_event_ids,
        base.exit_event_ids,
        base.coverage_complete,
        base.contracts_version,
    )
    return program, solve(program, budget=AnalysisBudget())


def two_instance_queue_program(*, bound: int | str) -> tuple[Program, object]:
    base, _ = solved(contract_bound=bound)
    second = AbstractInstance("instance:stream:second", "family:stream", "recent", "exact")
    first_create = effect("create")
    second_create = replace(
        first_create,
        effect_id="effect:create:second",
        instance_id=second.instance_id,
        evidence_ids=("fact:create:second",),
    )
    effects = (
        first_create,
        _dispatch_effect("instance:stream", bound=bound),
        second_create,
        _dispatch_effect(second.instance_id, bound=bound),
    )
    transition = Transition(
        "transition:two-instances",
        "event:entry",
        "event:normal",
        "normal",
        effects,
        "normal",
        (),
    )
    program = replace(
        base,
        instances=base.instances + (second,),
        transitions=(transition,),
        exit_event_ids=("event:normal",),
    )
    return program, solve(program, budget=AnalysisBudget())


class ResourceLifecycleInvariantTests(unittest.TestCase):
    def test_legacy_candidate_without_population_model_cannot_prove_scope(self) -> None:
        program, result = solved()

        dimensions = check_with_contract(program, result, (candidate(),))
        queue = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("unknown", queue.lifecycle_status)
        self.assertTrue(queue.scope.startswith("task_queue:"))
        self.assertIsNone(queue.upper_bound)
        self.assertIn("executor_population_binding_unavailable", queue.reason_codes)
        self.assertNotEqual("global", queue.scope)

    def test_non_atomic_check_then_add_cannot_prove_concurrent_bound(self) -> None:
        program, result = solved()

        dimensions = check_with_contract(program, result, (candidate(atomic=False),))
        held = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("unknown", held.lifecycle_status)
        self.assertIn("executor_population_binding_unavailable", held.reason_codes)

    def test_candidate_atomic_flag_cannot_override_non_atomic_executor_contract(self) -> None:
        program, result = solved()

        dimensions = check_invariants(
            program,
            result,
            (candidate(atomic=True),),
            timeout_ms=100,
            executor_contracts=(executor_contract(atomic=False),),
        )
        held = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("unknown", held.lifecycle_status)
        self.assertIn("capacity_not_atomic", held.reason_codes)

    def test_candidate_bound_must_equal_executor_contract_capacity(self) -> None:
        program, result = solved()
        mismatched_contract = replace(executor_contract(), queue_capacity=3)

        dimensions = check_invariants(
            program,
            result,
            (candidate(),),
            timeout_ms=100,
            executor_contracts=(mismatched_contract,),
        )
        held = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("unknown", held.lifecycle_status)
        self.assertIn("queue_capacity_contract_mismatch", held.reason_codes)

    def test_untrusted_executor_contract_cannot_publish_a_bound(self) -> None:
        program, result = solved()

        dimensions = check_invariants(
            program,
            result,
            (candidate(),),
            timeout_ms=100,
            executor_contracts=(executor_contract(source_kind="llm_proposed"),),
        )
        held = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("unknown", held.lifecycle_status)
        self.assertIn("untrusted_executor_contract_source", held.reason_codes)

    def test_uncovered_queue_writer_gets_its_own_unknown_result(self) -> None:
        base, _ = solved()
        second_holder = Holder("holder:task:second", "task", "task", "exact")
        second_event = Event(
            "event:queue:second",
            "task_queue",
            "Fixture.handle#queueSecond",
            "accepted",
        )
        second_dispatch = replace(
            _dispatch_effect("instance:stream"),
            effect_id="effect:dispatch:second",
            holder_id=second_holder.holder_id,
            target_event_id=second_event.event_id,
            contract_id="contract:queue:second",
            evidence_ids=("fact:dispatch:second",),
        )
        program = replace(
            base,
            holders=base.holders + (second_holder,),
            events=base.events + (second_event,),
            transitions=(
                Transition(
                    "transition:two-queues",
                    "event:entry",
                    "event:normal",
                    "normal",
                    (effect("create"), _dispatch_effect("instance:stream"), second_dispatch),
                    "normal",
                    (),
                ),
            ),
            exit_event_ids=("event:normal",),
        )

        dimensions = check_invariants(
            program,
            solve(program, budget=AnalysisBudget()),
            (candidate(),),
            timeout_ms=100,
            executor_contracts=(executor_contract(),),
        )
        held = [item for item in dimensions if item.dimension == "held_instances"]

        self.assertEqual(2, len(held))
        uncovered = next(item for item in held if "contract:queue:second" in item.scope)
        self.assertIn("queue_writer_not_covered", uncovered.reason_codes)
        self.assertIn("contract:queue:second", uncovered.scope)

    def test_candidate_writer_flag_does_not_replace_population_model(self) -> None:
        program, result = solved()
        dimensions = check_with_contract(program, result, (candidate(covers_writers=False),))

        self.assertEqual("unknown", dimensions[0].lifecycle_status)
        self.assertIn(
            "executor_population_binding_unavailable",
            dimensions[0].reason_codes,
        )
        self.assertNotIn("writer_coverage_incomplete", dimensions[0].reason_codes)

    def test_candidate_induction_flag_does_not_replace_population_model(self) -> None:
        program, result = solved()
        dimensions = check_with_contract(program, result, (candidate(transitions_preserve=False),))

        self.assertEqual("unknown", dimensions[0].lifecycle_status)
        self.assertIn(
            "executor_population_binding_unavailable",
            dimensions[0].reason_codes,
        )
        self.assertNotIn("candidate_not_inductive", dimensions[0].reason_codes)
        self.assertNotIn("unbounded", dimensions[0].lifecycle_status)

    def test_known_item_size_and_count_remain_separate_results(self) -> None:
        program, result = solved(known_size=True)
        dimensions = check_with_contract(program, result, (candidate(),))

        size = next(item for item in dimensions if item.dimension == "item_size_bytes")
        count = next(item for item in dimensions if item.dimension == "held_instances")
        self.assertEqual(("bounded", 1024), (size.lifecycle_status, size.upper_bound))
        self.assertEqual(("unknown", None), (count.lifecycle_status, count.upper_bound))
        self.assertIn("executor_population_binding_unavailable", count.reason_codes)

    def test_unknown_item_size_is_not_hidden_by_count_bound(self) -> None:
        program, result = solved(known_size=False)
        dimensions = check_with_contract(program, result, (candidate(),))

        size = next(item for item in dimensions if item.dimension == "item_size_bytes")
        self.assertEqual("unknown", size.lifecycle_status)
        self.assertIn("item_size_unknown", size.reason_codes)

    def test_timeout_has_distinct_unknown_reason(self) -> None:
        program, result = solved()
        dimensions = check_with_contract(program, result, (candidate(),), timeout_ms=0)

        self.assertTrue(all(item.lifecycle_status == "unknown" for item in dimensions))
        self.assertTrue(all("solver_timeout" in item.reason_codes for item in dimensions))

    def test_llm_proposed_invariant_cannot_prove_bounded(self) -> None:
        program, result = solved()
        dimensions = check_invariants(
            program,
            result,
            (candidate(source_kind="llm_proposed"),),
            timeout_ms=100,
            executor_contracts=(executor_contract(),),
        )

        self.assertEqual("unknown", dimensions[0].lifecycle_status)
        self.assertIn("untrusted_invariant_source", dimensions[0].reason_codes)

    def test_invariant_rejects_non_boolean_proof_flags(self) -> None:
        with self.assertRaisesRegex(ValueError, "boolean"):
            candidate(atomic="yes")

    def test_task_queue_invariant_rejects_missing_writer_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "contract, holder, and target identity"):
            candidate(writer_holder_id=None)

    def test_claimed_zero_bound_cannot_replace_population_model(self) -> None:
        program, result = solved()

        dimensions = check_with_contract(program, result, (candidate(upper_bound=0),))

        self.assertEqual("unknown", dimensions[0].lifecycle_status)
        self.assertIn("population_model_unavailable", dimensions[0].reason_codes)

    def test_symbolic_queue_bound_is_unknown_without_numeric_configuration(self) -> None:
        program, result = two_instance_queue_program(bound="K")

        dimensions = check_with_contract(
            program,
            result,
            (candidate(upper_bound="K"),),
            contract_bound="K",
        )
        held = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("unknown", held.lifecycle_status)
        self.assertIsNone(held.upper_bound)
        self.assertIn("executor_queue_capacity_unknown", held.reason_codes)

    def test_task_queue_candidate_requires_matching_dispatch_contract(self) -> None:
        program, result = solved(contract_bound=4)

        dimensions = check_with_contract(program, result, (candidate(upper_bound=3),))
        held = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("unknown", held.lifecycle_status)
        self.assertIn("population_model_unavailable", held.reason_codes)

    def test_self_reported_queue_flags_do_not_replace_program_structure(self) -> None:
        effects = (effect("create"), effect("retain", holder_id="holder:field"), effect("release"))
        program = program_for(
            (
                Transition(
                    "transition:normal",
                    "event:entry",
                    "event:normal",
                    "normal",
                    effects,
                    "normal",
                    (),
                ),
            )
        )
        program = replace(program, exit_event_ids=("event:normal",))
        result = solve(program, budget=AnalysisBudget())

        dimensions = check_with_contract(program, result, (candidate(),))
        held = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("unknown", held.lifecycle_status)
        self.assertIn("queue_writer_structure_unverified", held.reason_codes)

    def test_self_reported_nonqueue_flags_do_not_prove_a_bound(self) -> None:
        program, result = solved()
        field_candidate = InvariantCandidate(
            "candidate:field",
            "family:stream",
            "held_instances",
            "field",
            1,
            True,
            True,
            True,
            True,
            "trusted_contract",
            ("fixed field slot",),
            ("fact:field-candidate",),
        )

        dimensions = check_with_contract(program, result, (field_candidate,))
        held = next(item for item in dimensions if item.dimension == "held_instances")

        self.assertEqual("unknown", held.lifecycle_status)
        self.assertIn("derived_invariant_model_unavailable", held.reason_codes)

    def test_llm_proposed_resource_family_cannot_prove_dimensions(self) -> None:
        program, _ = solved(known_size=True)
        resource = replace(program.families[0], allocation=location("llm_proposed"))
        program = replace(program, families=(resource,))
        result = solve(program, budget=AnalysisBudget())

        dimensions = check_with_contract(program, result, (candidate(),))

        self.assertEqual(
            {("held_instances", "unknown"), ("item_size_bytes", "unknown"), ("close_obligation", "unknown")},
            {(item.dimension, item.lifecycle_status) for item in dimensions},
        )
        self.assertTrue(all("untrusted_resource_family" in item.reason_codes for item in dimensions))

    def test_close_coverage_gap_does_not_pollute_other_dimensions(self) -> None:
        program, _ = solved(known_size=True)
        program = replace(
            program,
            coverage_complete=False,
            coverage_gaps=(
                (
                    "close_obligation",
                    "family:stream",
                    "*",
                    "conditional_release_not_must",
                    "fact:conditional-release",
                ),
            ),
        )
        result = solve(program, budget=AnalysisBudget())

        dimensions = {
            item.dimension: item
            for item in check_with_contract(program, result, (candidate(),))
        }

        self.assertEqual("unknown", dimensions["held_instances"].lifecycle_status)
        self.assertIn(
            "executor_population_binding_unavailable",
            dimensions["held_instances"].reason_codes,
        )
        self.assertNotIn(
            "population_coverage_incomplete",
            dimensions["held_instances"].reason_codes,
        )
        self.assertEqual("bounded", dimensions["item_size_bytes"].lifecycle_status)
        self.assertEqual("unknown", dimensions["close_obligation"].lifecycle_status)
        self.assertIn("conditional_release_not_must", dimensions["close_obligation"].reason_codes)

    def test_non_closeable_family_ignores_unknown_call_for_close_dimension(self) -> None:
        base = program_for(())
        transition = Transition(
            "transition:ordinary-task-capture",
            "event:entry",
            "event:normal",
            "normal",
            (effect("create"), effect("unknown_call")),
            "normal",
            (),
        )
        program = replace(
            base,
            families=(family(requires_close=False),),
            transitions=(transition,),
            exit_event_ids=("event:normal",),
            coverage_complete=False,
            coverage_gaps=(
                (
                    "held_instances",
                    "family:stream",
                    "*",
                    "callee_resource_effects_unmodeled",
                    "fact:unknown_call",
                ),
                (
                    "item_size_bytes",
                    "family:stream",
                    "*",
                    "callee_resource_effects_unmodeled",
                    "fact:unknown_call",
                ),
            ),
        )

        dimensions = {
            item.dimension: item
            for item in check_invariants(
                program,
                solve(program, budget=AnalysisBudget()),
                (),
                timeout_ms=100,
            )
        }

        self.assertEqual("not_applicable", dimensions["close_obligation"].lifecycle_status)

    def test_repeated_recent_container_items_cannot_be_cleared_as_one_object(self) -> None:
        effects = (
            effect("create"),
            effect("retain", holder_id="holder:container"),
            effect("create"),
            effect("retain", holder_id="holder:container"),
            effect("drop", holder_id="holder:container"),
        )
        transition = Transition(
            "transition:repeat",
            "event:entry",
            "event:normal",
            "true",
            effects,
            "normal",
            (),
        )
        base = program_for(())
        program = replace(
            base,
            holders=base.holders + (Holder("holder:container", "container", "global", "exact"),),
            transitions=(transition,),
            exit_event_ids=("event:normal",),
        )
        result = solve(program, budget=AnalysisBudget())

        dimensions = check_invariants(program, result, (), timeout_ms=100)
        held = next(item for item in dimensions if item.dimension == "held_instances")
        interval = dict(result.exit_states["event:normal"].held_counts)["family:stream"]

        self.assertEqual("unknown", held.lifecycle_status)
        self.assertIn("repeated_abstract_instance:instance:stream", held.reason_codes)
        self.assertGreaterEqual(interval.lower, 1)

    def test_dispatch_with_unknown_identity_blocks_bounded_conclusions(self) -> None:
        base = program_for(())
        unknown_dispatch = Effect(
            "effect:dispatch:unknown",
            "dispatch",
            None,
            None,
            None,
            "event:normal",
            "true",
            location("static_verified"),
            ("fact:dispatch:unknown",),
            contract_id="bounded-queue-capacity:1",
        )
        program = replace(
            base,
            transitions=(
                Transition(
                    "transition:unknown-dispatch",
                    "event:entry",
                    "event:normal",
                    "true",
                    (unknown_dispatch,),
                    "normal",
                    (),
                ),
            ),
            exit_event_ids=("event:normal",),
        )
        result = solve(program, budget=AnalysisBudget())

        dimensions = check_invariants(program, result, (), timeout_ms=100)

        self.assertTrue(all(item.lifecycle_status == "unknown" for item in dimensions))
        self.assertTrue(all("dispatch_identity_unknown:effect:dispatch:unknown" in item.reason_codes for item in dimensions))


if __name__ == "__main__":
    unittest.main()
