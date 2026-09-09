from __future__ import annotations

from dataclasses import replace
import unittest

from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.events import expand_dispatch
from dosweb.resource_lifecycle.models import Effect, Holder
from dosweb.resource_lifecycle.solver import apply_effect, initial_state
from tests.test_resource_lifecycle_solver import effect, location, program_for


def dispatch_effect() -> Effect:
    return Effect(
        effect_id="effect:dispatch",
        kind="dispatch",
        instance_id="instance:stream",
        family_id="family:stream",
        holder_id="holder:task",
        target_event_id="event:task",
        condition="accepted",
        location=location("trusted_contract"),
        evidence_ids=("fact:executor-submit",),
        contract_id="contract:bounded-executor",
    )


def contract(
    *,
    cancellation: str = "unknown",
    scheduling: str = "queued",
    rejection_policy: str = "abort",
    termination: str = "drops_capture",
) -> ExecutorContract:
    return ExecutorContract(
        contract_id="contract:bounded-executor",
        scheduling=scheduling,
        queue_capacity=4,
        capacity_atomic=True,
        completion_drops_capture=termination == "drops_capture",
        rejection_drops_capture=rejection_policy in {"abort", "discard"},
        cancellation=cancellation,
        source_kind="trusted_contract",
        version="executor-contract-v1",
        rejection_policy=rejection_policy,
        termination=termination,
    )


class ResourceLifecycleEventTests(unittest.TestCase):
    def test_executor_contract_rejects_boolean_enum_conflicts(self) -> None:
        values = {
            "contract_id": "contract:bounded-executor",
            "scheduling": "queued",
            "queue_capacity": 4,
            "capacity_atomic": True,
            "completion_drops_capture": True,
            "rejection_drops_capture": True,
            "cancellation": "unknown",
            "source_kind": "trusted_contract",
            "version": "executor-contract-v1",
            "rejection_policy": "abort",
            "termination": "drops_capture",
        }
        cases = (
            ("termination_unknown", {"termination": "unknown"}, "termination"),
            (
                "termination_retains",
                {"termination": "retains_capture"},
                "termination",
            ),
            (
                "termination_drops_false",
                {"completion_drops_capture": False},
                "termination",
            ),
            (
                "abort_retains",
                {"rejection_drops_capture": False},
                "rejection policy",
            ),
            (
                "discard_retains",
                {
                    "rejection_policy": "discard",
                    "rejection_drops_capture": False,
                },
                "rejection policy",
            ),
            (
                "caller_runs_drops",
                {"rejection_policy": "caller_runs"},
                "rejection policy",
            ),
            (
                "discard_oldest_drops",
                {"rejection_policy": "discard_oldest"},
                "rejection policy",
            ),
        )

        for name, overrides, message in cases:
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, message):
                ExecutorContract(**{**values, **overrides})  # type: ignore[arg-type]

    def test_dispatch_consumes_termination_enum(self) -> None:
        retained = expand_dispatch(
            self._state(),
            dispatch_effect(),
            contract(termination="retains_capture"),
        )
        unknown = expand_dispatch(
            self._state(), dispatch_effect(), contract(termination="unknown")
        )

        self.assertIn(("instance:stream", "holder:task"), retained.completed.held_edges)
        self.assertNotIn(
            "completion_contract_unknown:contract:bounded-executor",
            retained.completed.unknown_reasons,
        )
        self.assertIn("task_completion_retains_capture", retained.rule_ids)
        self.assertIn(
            "completion_contract_unknown:contract:bounded-executor",
            unknown.completed.unknown_reasons,
        )

    def test_dispatch_consumes_rejection_policy_without_trusting_legacy_flag(self) -> None:
        for policy in ("abort", "discard"):
            expansion = expand_dispatch(
                self._state(),
                dispatch_effect(),
                contract(rejection_policy=policy),
            )
            with self.subTest(policy=policy):
                self.assertNotIn(
                    ("instance:stream", "holder:task"), expansion.rejected.held_edges
                )
                self.assertIn(
                    f"task_rejection_{policy}_does_not_capture", expansion.rule_ids
                )

        for policy in ("caller_runs", "discard_oldest", "unknown"):
            current = contract(rejection_policy=policy)
            if policy == "unknown":
                current = replace(current, rejection_drops_capture=True)
            expansion = expand_dispatch(self._state(), dispatch_effect(), current)
            with self.subTest(policy=policy):
                self.assertIn(
                    ("instance:stream", "holder:task"), expansion.rejected.held_edges
                )
                self.assertIn(
                    f"rejection_policy_conservative:contract:bounded-executor:{policy}",
                    expansion.rejected.unknown_reasons,
                )

    def test_executor_contract_carries_worker_and_rejection_semantics(self) -> None:
        current = contract()
        self.assertTrue(hasattr(current, "max_workers"), "missing max_workers")
        self.assertTrue(
            hasattr(current, "rejection_policy"), "missing rejection_policy"
        )
        configured = replace(
            current,
            max_workers=2,
            rejection_policy="abort",
        )

        self.assertEqual(2, configured.max_workers)
        self.assertEqual("abort", configured.rejection_policy)
        with self.assertRaisesRegex(ValueError, "worker limit"):
            replace(configured, max_workers=0)
        with self.assertRaisesRegex(ValueError, "rejection policy"):
            replace(configured, rejection_policy="guessed")

    def _state(self):
        base = program_for(())
        value = type(base)(
            schema_version=base.schema_version,
            families=base.families,
            instances=base.instances,
            holders=base.holders + (Holder("holder:task", "task", "task", "exact"),),
            events=base.events,
            transitions=base.transitions,
            entry_event_ids=base.entry_event_ids,
            exit_event_ids=base.exit_event_ids,
            coverage_complete=base.coverage_complete,
            contracts_version=base.contracts_version,
        )
        state = initial_state(value)
        for current in (effect("create"), effect("retain", holder_id="holder:request")):
            state = apply_effect(state, current).state
        return state

    def test_submit_captures_resource_and_start_does_not_release_it(self) -> None:
        expansion = expand_dispatch(self._state(), dispatch_effect(), contract())

        self.assertIn(("instance:stream", "holder:task"), expansion.submitted.held_edges)
        self.assertIn(("instance:stream", "holder:task"), expansion.started.held_edges)
        self.assertEqual(expansion.submitted, expansion.started)
        self.assertIn("task_dequeue_is_phase_change", expansion.rule_ids)

    def test_dispatch_effect_itself_adds_a_conservative_capture_edge(self) -> None:
        state = apply_effect(self._state(), dispatch_effect()).state

        self.assertIn(("instance:stream", "holder:task"), state.held_edges)
        self.assertNotIn("dispatch_contract_unknown:effect:dispatch", state.unknown_reasons)

    def test_dispatch_without_contract_still_may_capture_and_is_unknown(self) -> None:
        current = dispatch_effect()
        current = Effect(
            current.effect_id,
            current.kind,
            current.instance_id,
            current.family_id,
            current.holder_id,
            current.target_event_id,
            current.condition,
            current.location,
            current.evidence_ids,
        )

        state = apply_effect(self._state(), current).state

        self.assertIn(("instance:stream", "holder:task"), state.held_edges)
        self.assertIn("dispatch_contract_unknown:effect:dispatch", state.unknown_reasons)

    def test_request_return_drops_only_request_holder(self) -> None:
        expansion = expand_dispatch(self._state(), dispatch_effect(), contract())
        returned = apply_effect(expansion.submitted, effect("drop", holder_id="holder:request")).state

        self.assertNotIn(("instance:stream", "holder:request"), returned.held_edges)
        self.assertIn(("instance:stream", "holder:task"), returned.held_edges)

    def test_completion_releases_task_capture_but_not_close_obligation(self) -> None:
        expansion = expand_dispatch(self._state(), dispatch_effect(), contract())

        self.assertNotIn(("instance:stream", "holder:task"), expansion.completed.held_edges)
        self.assertIn("instance:stream", expansion.completed.open_obligations)
        self.assertIn("task_completion_drops_capture", expansion.rule_ids)

    def test_rejected_submission_does_not_retain_task_capture(self) -> None:
        expansion = expand_dispatch(self._state(), dispatch_effect(), contract())

        self.assertNotIn(("instance:stream", "holder:task"), expansion.rejected.held_edges)
        self.assertIn(("instance:stream", "holder:request"), expansion.rejected.held_edges)

    def test_unknown_cancellation_preserves_capture_and_records_unknown(self) -> None:
        expansion = expand_dispatch(self._state(), dispatch_effect(), contract(cancellation="unknown"))

        self.assertIn(("instance:stream", "holder:task"), expansion.cancelled.held_edges)
        self.assertIn("cancel_contract_unknown:contract:bounded-executor", expansion.cancelled.unknown_reasons)

    def test_explicit_cancel_drop_contract_removes_only_task_capture(self) -> None:
        expansion = expand_dispatch(self._state(), dispatch_effect(), contract(cancellation="drops_capture"))

        self.assertNotIn(("instance:stream", "holder:task"), expansion.cancelled.held_edges)
        self.assertIn(("instance:stream", "holder:request"), expansion.cancelled.held_edges)

    def test_untrusted_contract_cannot_drive_dispatch_semantics(self) -> None:
        invalid = ExecutorContract(
            contract_id="contract:bounded-executor",
            scheduling="queued",
            queue_capacity=4,
            capacity_atomic=True,
            completion_drops_capture=True,
            rejection_drops_capture=True,
            cancellation="drops_capture",
            source_kind="llm_proposed",
            version="executor-contract-v1",
            rejection_policy="abort",
            termination="drops_capture",
        )
        with self.assertRaisesRegex(ValueError, "trusted"):
            expand_dispatch(self._state(), dispatch_effect(), invalid)

    def test_executor_contract_rejects_non_boolean_semantic_flags(self) -> None:
        with self.assertRaisesRegex(ValueError, "boolean"):
            ExecutorContract(
                contract_id="contract:bad",
                scheduling="queued",
                queue_capacity=4,
                capacity_atomic="yes",  # type: ignore[arg-type]
                completion_drops_capture=True,
                rejection_drops_capture=True,
                cancellation="unknown",
                source_kind="trusted_contract",
                version="executor-contract-v1",
            )

    def test_executor_contract_identity_fields_are_strict_bounded_strings(self) -> None:
        for field_name, value in (("contract_id", 7), ("version", 7), ("contract_id", "x" * 513)):
            with self.subTest(field_name=field_name, value_type=type(value).__name__):
                values = {
                    "contract_id": "contract:bounded-executor",
                    "scheduling": "queued",
                    "queue_capacity": 4,
                    "capacity_atomic": True,
                    "completion_drops_capture": True,
                    "rejection_drops_capture": True,
                    "cancellation": "unknown",
                    "source_kind": "trusted_contract",
                    "version": "executor-contract-v1",
                }
                values[field_name] = value
                with self.assertRaisesRegex(ValueError, "identity"):
                    ExecutorContract(**values)  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "version"):
            ExecutorContract(
                contract_id="contract:future",
                scheduling="queued",
                queue_capacity=4,
                capacity_atomic=True,
                completion_drops_capture=False,
                rejection_drops_capture=True,
                cancellation="unknown",
                source_kind="trusted_contract",
                version="executor-contract-v999",
            )

    def test_dispatch_rejects_mismatched_contract_identity(self) -> None:
        invalid = contract()
        invalid = ExecutorContract(
            contract_id="contract:other",
            scheduling=invalid.scheduling,
            queue_capacity=invalid.queue_capacity,
            capacity_atomic=invalid.capacity_atomic,
            completion_drops_capture=invalid.completion_drops_capture,
            rejection_drops_capture=invalid.rejection_drops_capture,
            cancellation=invalid.cancellation,
            source_kind=invalid.source_kind,
            version=invalid.version,
            rejection_policy=invalid.rejection_policy,
            termination=invalid.termination,
        )

        with self.assertRaisesRegex(ValueError, "does not match"):
            expand_dispatch(self._state(), dispatch_effect(), invalid)

    def test_dispatch_with_unknown_capture_identity_returns_conservative_stages(self) -> None:
        current = dispatch_effect()
        unknown_identity = Effect(
            effect_id=current.effect_id,
            kind=current.kind,
            instance_id=None,
            family_id=None,
            holder_id=None,
            target_event_id=current.target_event_id,
            condition=current.condition,
            location=current.location,
            evidence_ids=current.evidence_ids,
            contract_id=None,
        )

        expansion = expand_dispatch(self._state(), unknown_identity, None)

        for state in (
            expansion.submitted,
            expansion.started,
            expansion.completed,
            expansion.rejected,
            expansion.cancelled,
        ):
            self.assertIn("dispatch_identity_unknown:effect:dispatch", state.unknown_reasons)
        self.assertIn("dispatch_identity_unknown", expansion.rule_ids)


if __name__ == "__main__":
    unittest.main()
