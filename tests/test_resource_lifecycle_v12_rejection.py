"""A caller exception fact cannot invent the missing callee rejection CFG.

The source regression exposed a wrapper call with a caller exceptional-exit
fact, but only an execute-success fact inside the callee.  Its argument binding
proves resource identity, not how rejection traverses callee catch/finally or
returns to the caller.  Completed accepted-task paths cannot fill that gap.
These manual IR counterexamples deliberately make no source extraction claim.
"""
from dataclasses import replace

import pytest

from dosweb.resource_lifecycle.invariants import check_invariants
from dosweb.resource_lifecycle.models import AnalysisBudget
from dosweb.resource_lifecycle.solver import solve
from tests.test_resource_lifecycle_task4_review import caller_outcome_program


@pytest.mark.parametrize("missing", ["edge", "cfg_evidence", "task_identity"])
def test_missing_rejection_proof_keeps_conditional_result_unknown(missing):
    program = caller_outcome_program()
    rejected = next(edge for edge in program.transitions if edge.transition_id == "caller:reject")
    if missing == "edge":
        transitions = tuple(edge for edge in program.transitions if edge != rejected)
    else:
        prefix = "cfg_fact:" if missing == "cfg_evidence" else "task_binding:"
        weakened = replace(rejected, assumptions=tuple(
            value for value in rejected.assumptions if not value.startswith(prefix)))
        transitions = tuple(weakened if edge == rejected else edge for edge in program.transitions)
    program = replace(program, transitions=transitions)
    result = solve(program, budget=AnalysisBudget(max_steps=10000))

    assert result.terminated
    assert "event:error" not in result.exit_states
    assert "task_rejection_continuation_unknown:task:0" in result.unknown_reasons
    assert "exit_state_missing:event:error" in result.unknown_reasons
    assert result.property_derivations["all_tasks_terminated_after_request"]["event:normal"]
    rows = [row for row in check_invariants(program, result, (), timeout_ms=1000)
            if row.scope == "all_tasks_terminated_after_request"]
    assert rows
    assert all(row.lifecycle_status == "unknown" for row in rows)
    assert all("exit_state_missing:event:error" in row.reason_codes for row in rows)


def test_explicit_rejection_cfg_reaches_exit_without_closing_resource():
    program = caller_outcome_program()
    result = solve(program, budget=AnalysisBudget(max_steps=10000))
    assert set(result.exit_states) == set(program.exit_event_ids)
    assert not any(reason.startswith("exit_state_missing:") for reason in result.unknown_reasons)
    rejected = result.exit_states["event:error"]
    assert rejected.open_obligations
    assert ("instance:stream", "holder:rejected") in rejected.held_edges
    assert ("instance:stream", "task:0:holder") not in rejected.held_edges
    for paths in result.property_derivations["all_tasks_terminated_after_request"].values():
        for path in paths:
            assert "caller:reject" not in path.trace.transition_ids
            assert "task:0:edge:reject" not in path.trace.transition_ids
