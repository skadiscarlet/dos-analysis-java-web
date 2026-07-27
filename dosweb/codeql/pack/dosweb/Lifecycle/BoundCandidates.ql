/**
 * @name Lifecycle bound candidates
 * @description Screens finite queues and unchecked blocking-queue submissions.
 * @kind table
 * @id dosweb/bound-candidates
 */

import java

// Exact candidate-only contract columns:
// "site_file", "site_start_line", "bound_kind", "resource_dimension",
// "scope", "behavior", "receiver", "field_path", "result_checked",
// "configuration_key", "configuration_value", "evidence",
// "coverage_status", "coverage_note"

predicate boundRow(
  Element site, string receiver, string fieldPath, boolean checked,
  string value, string evidence, string status, string note
) {
  exists(ClassInstanceExpr allocation |
    site = allocation and
    allocation.getConstructedType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "ArrayBlockingQueue") and
    receiver = allocation.getConstructedType().getQualifiedName() and fieldPath = "queue" and
    checked = false and value = allocation.getArgument(0).toString() and
    evidence = "finite_queue_capacity" and status = "complete" and
    note = "constructor_capacity_candidate"
  )
  or
  exists(MethodCall call |
    site = call and call.getMethod().getName() = ["offer", "add"] and
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "BlockingQueue") and
    receiver = call.getQualifier().toString() and fieldPath = receiver and checked = false and
    value = "submission_result" and evidence = "queue_submission_result" and status = "partial" and
    note = "result_check_not_modeled"
  )
}

from Element site, string receiverValue, string fieldPathValue, boolean checkedValue,
  string valueValue, string evidenceValue, string statusValue, string noteValue
where
  boundRow(site, receiverValue, fieldPathValue, checkedValue, valueValue, evidenceValue, statusValue, noteValue)
select
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  "capacity" as bound_kind,
  "tasks" as resource_dimension,
  "instance" as scope,
  "block" as behavior,
  receiverValue as receiver,
  fieldPathValue as field_path,
  checkedValue as result_checked,
  "queue.capacity" as configuration_key,
  valueValue as configuration_value,
  "unknown" as phase,
  false as covers_flow,
  "unknown" as request_encoding,
  fieldPathValue as queue_resource,
  false as product_bound,
  evidenceValue as evidence,
  "partial" as coverage_status,
  noteValue as coverage_note
