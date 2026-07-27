/**
 * @name Container growth candidates
 * @description Screens writes to field-backed containers and excludes request-local collections.
 * @kind table
 * @id dosweb/container-growth
 */

import java

// Exact Task 3 contract:
// "site_file", "site_start_line", "growth_kind", "operation",
// "resource_dimension", "receiver", "field_path", "demand_input_name",
// "demand_input_role", "escape_scope", "candidate_evidence",
// "coverage_status", "coverage_note"

predicate containerWrite(MethodCall call) {
  call.getMethod().getName() = ["put", "add"] and
  call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util", ["Map", "Collection"])
}

from MethodCall call, FieldAccess fieldReceiver, Expr demand, string demandRole, string escapeScope
where
  containerWrite(call) and
  fieldReceiver = call.getQualifier() and
  demand = call.getArgument(0) and
  (
    call.getMethod().getName() = "put" and demandRole = "key"
    or
    call.getMethod().getName() = "add" and demandRole = "value"
  ) and
  (
    fieldReceiver.getField().isStatic() and escapeScope = "global"
    or
    not fieldReceiver.getField().isStatic() and escapeScope = "instance"
  )
select
  call.getLocation().getFile().getRelativePath() as site_file,
  call.getLocation().getStartLine() as site_start_line,
  "container_growth" as growth_kind,
  call.getMethod().getDeclaringType().getQualifiedName() + "." + call.getMethod().getName() as operation,
  "entries" as resource_dimension,
  fieldReceiver.getField().getDeclaringType().getQualifiedName() + "." + fieldReceiver.getField().getName() as receiver,
  fieldReceiver.getField().getName() as field_path,
  demand.toString() as demand_input_name,
  demandRole as demand_input_role,
  escapeScope as escape_scope,
  "field_backed_container_write" as candidate_evidence,
  "complete" as coverage_status,
  "persistent_field_container_write" as coverage_note
