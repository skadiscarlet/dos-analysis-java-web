from dataclasses import replace
import unittest

from dosweb.resource_lifecycle.adapters import AnalysisUnit, ExtractedFacts
from dosweb.resource_lifecycle.commands import _analyze_payload
from dosweb.resource_lifecycle.models import AbstractInstance, AnalysisBudget, Transition
from dosweb.resource_lifecycle.source_evaluation import SourceExpectedOutcome, _observation
from tests.test_resource_lifecycle_solver import effect, family, program_for


class PublishedPropertiesTests(unittest.TestCase):
    def fixture(self):
        effects = (effect("create"), effect("release"))
        second = tuple(replace(item, effect_id=item.effect_id + ":other",
                               instance_id="instance:other", family_id="family:other")
                       for item in effects)
        transitions = tuple(
            Transition("edge:" + kind, "event:entry", target, kind, effects + second, kind, ())
            for kind, target in (("normal", "event:normal"), ("exceptional", "event:error"))
        )
        program = program_for(())
        program = replace(program, transitions=transitions, families=(family(), replace(family(), family_id="family:other")),
                          instances=program.instances + (AbstractInstance("instance:other", "family:other", "recent", "exact"),))
        unit = AnalysisUnit("Fixture.handle", program, (), ())
        facts = ExtractedFacts("manual_fixture", "a" * 64, "fixture-v1", AnalysisBudget(), (unit,), (), {})
        return unit, facts

    def test_multiple_resources_oracle_independence_and_order(self):
        unit, facts = self.fixture()
        payload = _analyze_payload(facts)
        result = payload["units"][0]
        properties = result["properties"]
        self.assertEqual({"family:stream", "family:other"}, {p["resource_family_id"] for p in properties})
        self.assertEqual(len(properties), len({p["property_id"] for p in properties}))
        expected = SourceExpectedOutcome("full", "close_obligation", "all_exits", "all_modeled_exits", "bounded", 0, None)
        for family_id in ("family:stream", "family:other"):
            actual = _observation(expected, result, unit, family_id)
            altered = _observation(replace(expected, lifecycle_status="obligation_gap", upper_bound=42), result, unit, family_id)
            self.assertEqual(actual, altered)
            self.assertEqual("bounded", actual["lifecycle_status"])
            self.assertIn(actual["property_id"], {p["property_id"] for p in properties})
        self.assertIn("expected_property_ambiguous", _observation(expected, result, unit)["reason_codes"])
        reordered = replace(unit, program=replace(unit.program, families=tuple(reversed(unit.program.families))))
        self.assertEqual(properties, _analyze_payload(replace(facts, units=(reordered,)))["units"][0]["properties"])

    def test_state_only_zero_does_not_publish_a_bound(self):
        unit, _ = self.fixture()
        expected = SourceExpectedOutcome("full", "held_instances", "resource_family", "all_tasks_terminated_after_request", "bounded", 0, None)
        result = {"property_states": {"all_tasks_terminated_after_request": {"exit": {"held_counts": []}}}}
        observed = _observation(expected, result, unit, "family:stream")
        self.assertEqual("unknown", observed["lifecycle_status"])
        self.assertIsNone(observed["upper_bound"])
        self.assertIn("missing_property", observed["reason_codes"])


class ConditionalScopeTests(unittest.TestCase):
    def test_only_exact_queue_progress_gap_is_excluded_at_task_exit(self):
        from dosweb.resource_lifecycle.invariants import queue_result_scope
        from tests.test_resource_lifecycle_async_solver import task_program, dimensions
        base = task_program()
        binding = base.task_bindings[0]
        queue_scope = queue_result_scope(binding.executor_contract_id, binding.holder_id, binding.queued_event_id)
        gap = ("close_obligation", "family:stream", queue_scope, "async_consumer_contract_unmodeled", "gap:queue")
        program = replace(base, coverage_complete=False, coverage_gaps=(gap,))
        rows = dimensions(program)
        self.assertEqual("bounded", rows["after_task_termination:task:0:normal", "close_obligation", "family:stream"].lifecycle_status)
        self.assertEqual("unknown", rows["all_exits", "close_obligation", "family:stream"].lifecycle_status)
        for updated in (replace(program, coverage_gaps=(gap[:2] + ("*",) + gap[3:],)),
                        replace(program, coverage_gaps=(gap[:2] + (queue_scope + ":other",) + gap[3:],)),
                        replace(program, coverage_gaps=(gap, ("close_obligation", "family:stream", "*", "task_close_cfg_unknown", "gap:close")))):
            self.assertEqual("unknown", dimensions(updated)["after_task_termination:task:0:normal", "close_obligation", "family:stream"].lifecycle_status)
