from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from dosweb.resource_lifecycle.models import (
    AbstractInstance,
    AnalysisBudget,
    Effect,
    Event,
    Holder,
    Program,
    ResourceFamily,
    ResourceState,
    SourceLocation,
    Transition,
)
from dosweb.resource_lifecycle.solver import apply_effect, initial_state, merge_states, solve


_SOURCE_HASH = hashlib.sha256(b"class Fixture {}").hexdigest()


def location(source_kind: str = "manual_fixture") -> SourceLocation:
    return SourceLocation(
        path="src/main/java/Fixture.java",
        start_line=3,
        end_line=3,
        source_sha256=_SOURCE_HASH,
        extractor_version="fixture-v1",
        source_kind=source_kind,
    )


class SourceLocationContractTests(unittest.TestCase):
    def test_source_lines_require_exact_positive_integers(self) -> None:
        baseline = location()
        for updates in (
            {"start_line": 3.0},
            {"end_line": 3.0},
            {"start_line": True},
            {"end_line": True},
        ):
            with self.subTest(updates=updates), self.assertRaisesRegex(
                ValueError, "line range"
            ):
                replace(baseline, **updates)


def family(*, requires_close: bool = True) -> ResourceFamily:
    return ResourceFamily(
        family_id="family:stream",
        allocation=location(),
        context=("Fixture.handle",),
        resource_type="java.io.InputStream",
        requires_close=requires_close,
    )


def program_for(transitions: tuple[Transition, ...], *, summary: bool = False) -> Program:
    return Program(
        schema_version="1.0",
        families=(family(),),
        instances=(
            AbstractInstance(
                instance_id="instance:stream",
                family_id="family:stream",
                abstraction="summary" if summary else "recent",
                identity_confidence="family" if summary else "exact",
            ),
        ),
        holders=(
            Holder("holder:request", "request_stack", "request", "exact"),
            Holder("holder:field", "field", "instance", "exact"),
        ),
        events=(
            Event("event:entry", "request", "Fixture.handle", "true"),
            Event("event:normal", "request_exit", "Fixture.handle#normal", "normal"),
            Event("event:error", "request_exit", "Fixture.handle#error", "exceptional"),
        ),
        transitions=transitions,
        entry_event_ids=("event:entry",),
        exit_event_ids=("event:normal", "event:error"),
        coverage_complete=True,
        contracts_version="contracts-v1",
    )


def effect(kind: str, *, holder_id: str | None = None) -> Effect:
    return Effect(
        effect_id=f"effect:{kind}:{holder_id or 'none'}",
        kind=kind,
        instance_id="instance:stream",
        family_id="family:stream",
        holder_id=holder_id,
        target_event_id=None,
        condition="true",
        location=location(),
        evidence_ids=(f"fact:{kind}",),
    )


class ResourceLifecycleSchemaTests(unittest.TestCase):
    def test_source_location_rejects_non_relative_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "relative"):
            SourceLocation(
                path="/tmp/Fixture.java",
                start_line=1,
                end_line=1,
                source_sha256=_SOURCE_HASH,
                extractor_version="fixture-v1",
                source_kind="manual_fixture",
            )

    def test_source_location_rejects_untrusted_source_kind(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_kind"):
            location("model_decided_safe")

    def test_program_rejects_missing_exit(self) -> None:
        value = program_for(())
        with self.assertRaisesRegex(ValueError, "exit event"):
            Program(
                schema_version=value.schema_version,
                families=value.families,
                instances=value.instances,
                holders=value.holders,
                events=value.events,
                transitions=value.transitions,
                entry_event_ids=value.entry_event_ids,
                exit_event_ids=("event:missing",),
                coverage_complete=value.coverage_complete,
                contracts_version=value.contracts_version,
            )

    def test_schema_rejects_non_boolean_resource_and_coverage_flags(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires_close"):
            ResourceFamily("family:bad", location(), ("Fixture.handle",), "Resource", "yes")  # type: ignore[arg-type]
        base = program_for(())
        with self.assertRaisesRegex(ValueError, "coverage_complete"):
            Program(
                base.schema_version,
                base.families,
                base.instances,
                base.holders,
                base.events,
                base.transitions,
                base.entry_event_ids,
                base.exit_event_ids,
                "yes",  # type: ignore[arg-type]
                base.contracts_version,
            )

    def test_coverage_gaps_require_family_and_scope(self) -> None:
        base = program_for(())
        scoped = replace(
            base,
            coverage_complete=False,
            coverage_gaps=(
                (
                    "held_instances",
                    "family:stream",
                    "*",
                    "coverage_partial",
                    "fact:partial",
                ),
            ),
        )

        self.assertEqual("family:stream", scoped.coverage_gaps[0][1])
        self.assertEqual("*", scoped.coverage_gaps[0][2])
        with self.assertRaisesRegex(ValueError, "family, scope"):
            replace(
                base,
                coverage_complete=False,
                coverage_gaps=(
                    ("held_instances", "coverage_partial", "fact:partial"),  # type: ignore[arg-type]
                ),
            )
        with self.assertRaisesRegex(ValueError, "unknown resource family"):
            replace(
                base,
                coverage_complete=False,
                coverage_gaps=(
                    (
                        "held_instances",
                        "family:missing",
                        "*",
                        "coverage_partial",
                        "fact:partial",
                    ),
                ),
            )


class ResourceLifecycleStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.program = program_for(())

    def test_drop_removes_only_the_named_holder(self) -> None:
        state = initial_state(self.program)
        for current in (
            effect("create"),
            effect("retain", holder_id="holder:request"),
            effect("retain", holder_id="holder:field"),
            effect("drop", holder_id="holder:request"),
        ):
            state = apply_effect(state, current).state

        self.assertNotIn(("instance:stream", "holder:request"), state.held_edges)
        self.assertIn(("instance:stream", "holder:field"), state.held_edges)
        self.assertIn("instance:stream", state.open_obligations)

    def test_close_does_not_drop_heap_holder(self) -> None:
        state = initial_state(self.program)
        for current in (
            effect("create"),
            effect("retain", holder_id="holder:field"),
            effect("release"),
        ):
            state = apply_effect(state, current).state

        self.assertNotIn("instance:stream", state.open_obligations)
        self.assertIn(("instance:stream", "holder:field"), state.held_edges)

    def test_summary_release_is_a_weak_update(self) -> None:
        summary_program = program_for((), summary=True)
        state = initial_state(summary_program)
        state = apply_effect(state, effect("create")).state
        released = apply_effect(state, effect("release"))

        self.assertIn("instance:stream", released.state.open_obligations)
        self.assertIn("weak_release_summary", released.rule_ids)
        self.assertIn("weak_update:instance:stream", released.state.unknown_reasons)

    def test_llm_proposed_release_preserves_close_obligation(self) -> None:
        state = apply_effect(initial_state(self.program), effect("create")).state
        untrusted = replace(effect("release"), location=location("llm_proposed"))

        released = apply_effect(state, untrusted)

        self.assertIn("instance:stream", released.state.open_obligations)
        self.assertEqual(1, dict(released.state.obligation_counts)["family:stream"].upper)
        self.assertIn("untrusted_release_preserves_obligation", released.rule_ids)
        self.assertIn(
            "untrusted_negative_effect:effect:release:none",
            released.state.unknown_reasons,
        )

    def test_llm_proposed_drop_preserves_may_hold_edge(self) -> None:
        state = initial_state(self.program)
        for current in (effect("create"), effect("retain", holder_id="holder:field")):
            state = apply_effect(state, current).state
        untrusted = replace(
            effect("drop", holder_id="holder:field"),
            location=location("llm_proposed"),
        )

        dropped = apply_effect(state, untrusted)

        self.assertIn(("instance:stream", "holder:field"), dropped.state.held_edges)
        self.assertEqual(1, dict(dropped.state.held_counts)["family:stream"].upper)
        self.assertIn("untrusted_drop_preserves_may_hold", dropped.rule_ids)
        self.assertIn(
            "untrusted_negative_effect:effect:drop:holder:field",
            dropped.state.unknown_reasons,
        )

    def test_conditional_release_does_not_prove_close_obligation(self) -> None:
        state = apply_effect(initial_state(self.program), effect("create")).state
        conditional = replace(effect("release"), condition="flag")

        released = apply_effect(state, conditional)

        self.assertIn("instance:stream", released.state.open_obligations)
        self.assertIn("conditional_release_preserves_obligation", released.rule_ids)
        self.assertIn(
            "conditional_negative_effect:effect:release:none",
            released.state.unknown_reasons,
        )

    def test_two_creates_and_one_release_leave_one_close_obligation(self) -> None:
        state = initial_state(self.program)
        for current in (effect("create"), effect("create"), effect("release")):
            state = apply_effect(state, current).state

        obligations = dict(state.obligation_counts)["family:stream"]
        self.assertEqual((1, 1), (obligations.lower, obligations.upper))
        self.assertIn("instance:stream", state.open_obligations)
        self.assertNotIn("instance:stream", state.must_released)

    def test_repeated_dispatch_preserves_abstract_instance_multiplicity(self) -> None:
        task_program = replace(
            self.program,
            holders=self.program.holders + (Holder("holder:task", "task", "task", "exact"),),
        )
        dispatch = Effect(
            effect_id="effect:dispatch:task",
            kind="dispatch",
            instance_id="instance:stream",
            family_id="family:stream",
            holder_id="holder:task",
            target_event_id="event:normal",
            condition="accepted",
            location=location(),
            evidence_ids=("fact:dispatch",),
            contract_id="bounded-queue-capacity:4",
        )
        state = initial_state(task_program)
        for current in (effect("create"), dispatch, effect("create"), dispatch):
            state = apply_effect(state, current).state

        held = dict(state.held_counts)["family:stream"]
        self.assertEqual(2, held.lower)
        self.assertIsNone(held.upper)
        self.assertIn("repeated_abstract_instance:instance:stream", state.unknown_reasons)

    def test_unknown_holder_scope_identity_is_preserved_as_precision_loss(self) -> None:
        uncertain_holders = tuple(
            replace(holder, identity_precision="unknown")
            if holder.holder_id == "holder:field"
            else holder
            for holder in self.program.holders
        )
        uncertain_program = replace(self.program, holders=uncertain_holders)
        state = initial_state(uncertain_program)
        for current in (effect("create"), effect("retain", holder_id="holder:field")):
            state = apply_effect(state, current).state

        self.assertIn("holder_scope_identity_unknown:holder:field", state.unknown_reasons)

    def test_unknown_call_keeps_relevant_state_and_reason(self) -> None:
        state = initial_state(self.program)
        for current in (
            effect("create"),
            effect("retain", holder_id="holder:field"),
            effect("unknown_call"),
        ):
            result = apply_effect(state, current)
            state = result.state

        self.assertIn(("instance:stream", "holder:field"), state.held_edges)
        self.assertIn("unknown_call:effect:unknown_call:none", state.unknown_reasons)

    def test_branch_merge_unions_may_hold_and_open_obligations(self) -> None:
        base = initial_state(self.program)
        held = apply_effect(apply_effect(base, effect("create")).state, effect("retain", holder_id="holder:field")).state
        released = apply_effect(apply_effect(base, effect("create")).state, effect("release")).state

        merged = merge_states((held, released))

        self.assertIn(("instance:stream", "holder:field"), merged.held_edges)
        self.assertIn("instance:stream", merged.open_obligations)
        self.assertNotIn("instance:stream", merged.must_released)

    def test_empty_merge_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "state"):
            merge_states(())


class ResourceLifecycleSolverTests(unittest.TestCase):
    def test_normal_and_exceptional_exits_remain_distinct(self) -> None:
        transitions = (
            Transition(
                "transition:normal",
                "event:entry",
                "event:normal",
                "normal",
                (effect("create"), effect("retain", holder_id="holder:request"), effect("release")),
                "normal",
                (),
            ),
            Transition(
                "transition:error",
                "event:entry",
                "event:error",
                "exception",
                (effect("create"), effect("retain", holder_id="holder:field")),
                "exceptional",
                (),
            ),
        )

        result = solve(program_for(transitions), budget=AnalysisBudget(max_steps=32, max_updates_per_event=8, timeout_ms=1000))

        normal = result.exit_states["event:normal"]
        exceptional = result.exit_states["event:error"]
        self.assertNotIn("instance:stream", normal.open_obligations)
        self.assertIn("instance:stream", exceptional.open_obligations)
        self.assertIn(("instance:stream", "holder:field"), exceptional.held_edges)
        self.assertEqual(("transition:normal",), result.traces["event:normal"].transition_ids)
        self.assertEqual(("transition:error",), result.traces["event:error"].transition_ids)
        self.assertTrue(result.terminated)

    def test_step_budget_returns_unknown_instead_of_unbounded(self) -> None:
        loop_event = Event("event:loop", "method", "Fixture.loop", "true")
        base = program_for(())
        loop = Transition(
            "transition:loop",
            "event:loop",
            "event:loop",
            "true",
            (effect("create"),),
            "normal",
            (),
        )
        value = Program(
            schema_version=base.schema_version,
            families=base.families,
            instances=base.instances,
            holders=base.holders,
            events=base.events + (loop_event,),
            transitions=(loop,),
            entry_event_ids=("event:loop",),
            exit_event_ids=("event:normal",),
            coverage_complete=True,
            contracts_version=base.contracts_version,
        )

        result = solve(value, budget=AnalysisBudget(max_steps=2, max_updates_per_event=2, timeout_ms=1000))

        self.assertFalse(result.terminated)
        self.assertIn("analysis_budget_exhausted", result.unknown_reasons)
        self.assertNotIn("unbounded", result.lifecycle_statuses)

    def test_unreachable_declared_exit_is_unknown_not_bounded(self) -> None:
        result = solve(program_for(()), budget=AnalysisBudget())

        self.assertIn("exit_state_missing:event:normal", result.unknown_reasons)
        self.assertIn("exit_state_missing:event:error", result.unknown_reasons)
        self.assertEqual(("unknown",), result.lifecycle_statuses)

    def test_step_budget_is_enforced_within_one_source_fanout(self) -> None:
        transitions = tuple(
            Transition(
                f"transition:fanout:{index}",
                "event:entry",
                "event:normal",
                "true",
                (effect("create"),),
                "normal",
                (),
            )
            for index in range(5)
        )

        result = solve(
            program_for(transitions),
            budget=AnalysisBudget(max_steps=2, max_updates_per_event=8, timeout_ms=1000),
        )

        self.assertFalse(result.terminated)
        self.assertEqual(2, result.steps)
        self.assertIn("analysis_budget_exhausted", result.unknown_reasons)


if __name__ == "__main__":
    unittest.main()
