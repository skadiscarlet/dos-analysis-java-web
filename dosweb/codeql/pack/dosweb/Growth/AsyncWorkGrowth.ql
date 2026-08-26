/**
 * @name Asynchronous work growth candidates
 * @description Screens executor and queue submissions, retaining explicit queue-capacity context.
 * @kind table
 * @id dosweb/async-work-growth
 */

import java
import LoopAmplification
import FiniteQueueDomain

// Exact Task 3 contract:
// "site_file", "site_start_line", "growth_kind", "operation",
// "resource_dimension", "receiver", "field_path", "demand_input_name",
// "demand_input_role", "escape_scope", "candidate_evidence",
// "coverage_status", "coverage_note"

predicate hardFiniteSubmission(MethodCall call) {
  exists(Field field, string capacity |
    field = queueReceiverField(call) and capacity = finiteFieldQueueCapacity(field)
  )
}

predicate asyncSubmission(MethodCall call) {
  call.getMethod().getName() = ["submit", "execute", "offer", "add", "schedule"] and
  (
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "ExecutorService")
    or
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "BlockingQueue")
  )
}

from MethodCall call, FieldAccess fieldReceiver, Expr work, string receiver,
     string fieldPath, string escapeScope, string demandName, string demandRole,
     string coverageStatus, string coverageNote, string capacityNote
where
  asyncSubmission(call) and
  fieldReceiver = call.getQualifier() and
  work = call.getArgument(0) and
  receiver = fieldReceiver.getField().getDeclaringType().getQualifiedName() + "." + fieldReceiver.getField().getName() and
  fieldPath = fieldReceiver.getField().getName() and
  (
    fieldReceiver.getField().isStatic() and escapeScope = "global"
    or
    not fieldReceiver.getField().isStatic() and escapeScope = "instance"
  ) and
  (
    hardFiniteSubmission(call) and
    coverageStatus = "complete" and capacityNote = "finite_queue_submission_candidate"
    or
    not hardFiniteSubmission(call) and
    coverageStatus = "partial" and capacityNote = "queue_or_executor_capacity_requires_contract"
  ) and
  (
    not exists(LoopStmt loop | growthInLoopBody(call, loop)) and
    demandName = work.toString() and demandRole = "value" and
    coverageNote = capacityNote + ":single_submission_no_enclosing_loop"
    or
    exists(LoopStmt loop |
      growthInLoopBody(call, loop) and attackerControlsLoop(loop) and
      demandName = attackerLoopDemand(loop)
    ) and demandRole = "submission_count" and capacityNote != "finite_queue_submission_candidate" and
    coverageNote = capacityNote + ":attacker_controlled_loop_multiplicity_proven"
    or
    exists(LoopStmt loop |
      growthInLoopBody(call, loop) and attackerControlsLoop(loop) and
      demandName = attackerLoopDemand(loop)
    ) and demandRole = "submission_count" and capacityNote = "finite_queue_submission_candidate" and
    coverageNote = capacityNote + ":finite_capacity_prevents_amplification"
    or
    exists(LoopStmt loop | growthInLoopBody(call, loop) and not attackerControlsLoop(loop)) and
    demandName = work.toString() and demandRole = "value" and
    coverageNote = capacityNote + ":loop_bound_not_attacker_proven"
  )
select
  call.getLocation().getFile().getRelativePath() as site_file,
  call.getLocation().getStartLine() as site_start_line,
  "async_work_growth" as growth_kind,
  call.getMethod().getDeclaringType().getQualifiedName() + "." + call.getMethod().getName() as operation,
  "tasks" as resource_dimension,
  receiver,
  fieldPath as field_path,
  demandName as demand_input_name,
  demandRole as demand_input_role,
  escapeScope as escape_scope,
  "async_submission" as candidate_evidence,
  coverageStatus as coverage_status,
  coverageNote as coverage_note
