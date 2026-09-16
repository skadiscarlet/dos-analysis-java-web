"""Real-source rejection propagation through precise wrappers and caller cleanup.

The input source is never executed: javac and CodeQL extract static evidence.
"""
from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from dosweb.resource_lifecycle.commands import _codeql_facts
from dosweb.resource_lifecycle.models import AnalysisBudget
from dosweb.resource_lifecycle.solver import solve
from tests.support.fixture_database import fixture_database

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/resource_lifecycle_rc1_exceptions/src/main/java"
RUN = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"


@unittest.skipUnless(RUN and shutil.which("codeql") and shutil.which("javac"),
                     "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with CodeQL and javac.")
class WrapperExceptionSourceTests(unittest.TestCase):
    def test_rejection_returns_through_caller_cleanup_and_preserves_holders(self):
        database = fixture_database(str(SOURCE))
        names = ("noCleanup", "callerFinallyCleanup", "callerCatchHolder", "extraHolder")
        entries = ["java-callable-v1:fixture.rc1.WrapperExceptions." + name + "()V"
                   for name in names]
        with tempfile.TemporaryDirectory() as directory:
            extracted = _codeql_facts({
                "schema_version": "1.1", "mode": "codeql_database",
                "database": str(database.path), "entry_methods": entries,
                "budget": asdict(AnalysisBudget()),
            }, {}, Path(directory))
        units = {unit.unit_id: unit for unit in extracted.units if unit.unit_id in entries}
        self.assertEqual(set(entries), set(units))
        results = {}
        for name, entry in zip(names, entries):
            unit = units[entry]
            result = solve(unit.program, budget=extracted.budget)
            results[name] = result
            self.assertTrue(result.terminated, (name, result.unknown_reasons))
            self.assertFalse(any(reason.startswith("task_rejection_continuation_unknown:")
                                 for reason in result.unknown_reasons), name)
            self.assertTrue(unit.program.call_bindings)
            self.assertTrue(unit.program.task_bindings)
            for transition in unit.program.transitions:
                if transition.guard == "task_submit_exceptional":
                    self.assertFalse(any(effect.kind == "dispatch" for effect in transition.effects))
        # A rejected task was never captured or started. Its open resource flows
        # through the wrapper exceptional exit and caller finally close.
        def exceptional(name):
            unit = units[entries[names.index(name)]]
            events = [event.event_id for event in unit.program.events
                      if event.kind == "request_exit" and event.activation_condition == "exceptional"]
            self.assertEqual(1, len(events))
            self.assertIn(events[0], results[name].exit_states)
            return results[name].exit_states[events[0]]
        missing_cleanup = exceptional("noCleanup")
        cleaned = exceptional("callerFinallyCleanup")
        self.assertTrue(missing_cleanup.open_obligations)
        self.assertFalse(cleaned.open_obligations)
        task_holders = {holder.holder_id for holder in units[entries[0]].program.holders
                        if holder.kind == "task"}
        self.assertTrue(task_holders)
        self.assertFalse(any(holder in task_holders for _, holder in missing_cleanup.held_edges))
        # A caller catch is not bypassed by an invented direct exceptional exit.
        caught_unit = units[entries[2]]
        caught_result = results["callerCatchHolder"]
        field_ids = {holder.holder_id for holder in caught_unit.program.holders if holder.kind == "field"}
        self.assertTrue(field_ids)
        self.assertTrue(any(holder in field_ids for state in caught_result.exit_states.values()
                            for _, holder in state.held_edges))
        # Additional holders survive accepted task completion; close is not drop.
        for name, expected in (("noCleanup", 0), ("extraHolder", 1)):
            states = results[name].property_states["all_tasks_terminated_after_request"]
            self.assertTrue(states)
            self.assertEqual({expected}, {count.upper for state in states.values()
                                         for _, count in state.held_counts})
