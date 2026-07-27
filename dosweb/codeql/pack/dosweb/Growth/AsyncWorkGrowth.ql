/**
 * @name Asynchronous work growth candidates
 * @description Screens executor and queue submissions, retaining explicit queue-capacity context.
 * @kind table
 * @id dosweb/async-work-growth
 */

import java

// Exact Task 3 contract:
// "site_file", "site_start_line", "growth_kind", "operation",
// "resource_dimension", "receiver", "field_path", "demand_input_name",
// "demand_input_role", "escape_scope", "candidate_evidence",
// "coverage_status", "coverage_note"

predicate asyncSubmission(MethodCall call) {
  call.getMethod().getName() = ["submit", "execute", "offer", "add", "schedule"] and
  (
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "ExecutorService")
    or
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "BlockingQueue")
  )
}

from MethodCall call, FieldAccess fieldReceiver, Expr work, string receiver, string fieldPath, string escapeScope, string coverageStatus, string coverageNote
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
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "ArrayBlockingQueue") and
    coverageStatus = "complete" and coverageNote = "finite_queue_submission_candidate"
    or
    not call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "ArrayBlockingQueue") and
    coverageStatus = "partial" and coverageNote = "queue_or_executor_capacity_requires_contract"
  )
select
  call.getLocation().getFile().getRelativePath() as site_file,
  call.getLocation().getStartLine() as site_start_line,
  "async_work_growth" as growth_kind,
  call.getMethod().getDeclaringType().getQualifiedName() + "." + call.getMethod().getName() as operation,
  "tasks" as resource_dimension,
  receiver,
  fieldPath as field_path,
  work.toString() as demand_input_name,
  "submission_count" as demand_input_role,
  escapeScope as escape_scope,
  "async_submission" as candidate_evidence,
  coverageStatus as coverage_status,
  coverageNote as coverage_note
