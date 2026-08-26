/**
 * @name Container growth candidates
 * @description Screens writes to field-backed containers and excludes request-local collections.
 * @kind table
 * @id dosweb/container-growth
 */

import java
import LoopAmplification

// Exact Task 3 contract:
// "site_file", "site_start_line", "growth_kind", "operation",
// "resource_dimension", "receiver", "field_path", "demand_input_name",
// "demand_input_role", "escape_scope", "candidate_evidence",
// "coverage_status", "coverage_note"

predicate containerWrite(MethodCall call) {
  call.getMethod().getName() = ["put", "add", "computeIfAbsent", "putIfAbsent", "merge"] and
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util", ["Map", "Collection"])
}

predicate httpSessionAttributeWrite(MethodCall call) {
  call.getMethod().getName() = "setAttribute" and call.getNumArgument() = 2 and
  call.getMethod().getDeclaringType().getASupertype*().hasQualifiedName(
    ["fixture.spring", "javax.servlet.http", "jakarta.servlet.http"], "HttpSession"
  )
}

predicate demandUsesAttackerParameter(MethodCall call, Expr demand) {
  exists(Method method, Parameter input, VarAccess access |
    method = call.getEnclosingCallable() and p0AttackerParameter(method, input) and
    access.getVariable() = input and (access = demand or access.getParent+() = demand)
  )
}

predicate fixedDemand(Expr demand) {
  demand instanceof CompileTimeConstantExpr
}

predicate containerGrowthRow(
  MethodCall call, string operation, string resourceDimension, string receiver,
  string fieldPath, Expr demand, string demandRole, string escapeScope,
  string evidence, string coverageStatus, string coverageNote
) {
  exists(FieldAccess fieldReceiver, string multiplicityNote |
    containerWrite(call) and fieldReceiver = call.getQualifier() and
    demand = call.getArgument(0) and
    (
      call.getMethod().getName() = ["put", "computeIfAbsent", "putIfAbsent", "merge"] and
      demandRole = "key"
      or call.getMethod().getName() = "add" and demandRole = "value"
    ) and
    (
      fieldReceiver.getField().isStatic() and escapeScope = "global"
      or not fieldReceiver.getField().isStatic() and escapeScope = "instance"
    ) and
    (
      not exists(LoopStmt loop | growthInLoopBody(call, loop)) and
      multiplicityNote = "single_operation_no_enclosing_loop"
      or exists(LoopStmt loop | growthInLoopBody(call, loop) and attackerControlsLoop(loop)) and
      multiplicityNote = "attacker_controlled_loop_multiplicity_proven"
      or exists(LoopStmt loop | growthInLoopBody(call, loop) and not attackerControlsLoop(loop)) and
      multiplicityNote = "loop_bound_not_attacker_proven"
    ) and
    operation = call.getMethod().getDeclaringType().getQualifiedName() + "." + call.getMethod().getName() and
    resourceDimension = "entries" and
    receiver = fieldReceiver.getField().getDeclaringType().getQualifiedName() + "." +
      fieldReceiver.getField().getName() and
    fieldPath = fieldReceiver.getField().getName() and evidence = "field_backed_container_write" and
    (
      demandRole = "key" and fixedDemand(demand) and
      coverageStatus = "complete" and
      coverageNote = "persistent_field_container_write:fixed_key:" + multiplicityNote
      or demandRole = "key" and demandUsesAttackerParameter(call, demand) and
         coverageStatus = "complete" and
         coverageNote = "persistent_field_container_write:attacker_key_driver:" + multiplicityNote
      or demandRole = "value" and demandUsesAttackerParameter(call, demand) and
         coverageStatus = "complete" and
         coverageNote = "persistent_field_container_write:attacker_value_driver:" + multiplicityNote
      or demandRole = "key" and not fixedDemand(demand) and
         not demandUsesAttackerParameter(call, demand) and
         coverageStatus = "partial" and
         coverageNote = "persistent_field_container_write:key_driver_unclassified:" + multiplicityNote
      or demandRole = "value" and not demandUsesAttackerParameter(call, demand) and
         coverageStatus = "partial" and
         coverageNote = "persistent_field_container_write:value_driver_unclassified:" + multiplicityNote
    )
  )
  or
  httpSessionAttributeWrite(call) and demand = call.getArgument(1) and demandRole = "value" and
  operation = call.getMethod().getDeclaringType().getQualifiedName() + "." + call.getMethod().getName() and
  resourceDimension = "objects" and
  receiver = call.getMethod().getDeclaringType().getQualifiedName() and
  fieldPath = call.getArgument(0).toString() and escapeScope = "session" and
  evidence = "http_session_attribute_write" and coverageStatus = "partial" and
  coverageNote = "http_session_attribute_write:fixed_attribute_fresh_session_unproven"
}

from MethodCall call, Expr demand, string operationText, string resourceDimension,
     string receiverText, string fieldPath, string demandRole, string escapeScope,
     string evidence, string coverageStatus, string coverageNote
where containerGrowthRow(
  call, operationText, resourceDimension, receiverText, fieldPath, demand, demandRole,
  escapeScope, evidence, coverageStatus, coverageNote
)
select
  call.getLocation().getFile().getRelativePath() as site_file,
  call.getLocation().getStartLine() as site_start_line,
  "container_growth" as growth_kind,
  operationText as operation,
  resourceDimension as resource_dimension,
  receiverText as receiver,
  fieldPath as field_path,
  demand.toString() as demand_input_name,
  demandRole as demand_input_role,
  escapeScope as escape_scope,
  evidence as candidate_evidence,
  coverageStatus as coverage_status,
  coverageNote as coverage_note
