/**
 * @name Container growth candidates
 * @description Screens field-backed and exact request-local container writes with open-world multiplicity evidence.
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

predicate containerDemand(MethodCall call, Expr demand, string demandRole) {
  demand = call.getArgument(0) and
  (
    call.getMethod().getName() = ["put", "computeIfAbsent", "putIfAbsent", "merge"] and
    demandRole = "key"
    or call.getMethod().getName() = "add" and demandRole = "value"
  )
}

predicate containerMultiplicity(MethodCall call, string multiplicityNote) {
  not exists(LoopStmt loop | growthInLoopBody(call, loop)) and
  multiplicityNote = "single_operation_no_enclosing_loop"
  or exists(LoopStmt loop, Parameter bound, VarAccess boundAccess |
    provenAttackerLoopMultiplicity(call, loop, bound, boundAccess)
  ) and
  multiplicityNote = "attacker_controlled_loop_multiplicity_proven"
  or exists(LoopStmt loop |
    growthInLoopBody(call, loop) and
    not exists(Parameter bound, VarAccess boundAccess |
      provenAttackerLoopMultiplicity(call, loop, bound, boundAccess)
    )
  ) and
  multiplicityNote = "loop_bound_not_attacker_proven"
}

predicate requestLocalContainer(
  MethodCall call, LocalVariableDecl local, VarAccess localAccess, Method handler,
  ClassInstanceExpr allocation
) {
  handler = call.getEnclosingCallable() and p0Handler(handler) and
  localAccess = call.getQualifier() and localAccess.getVariable() = local and
  local.getCallable() = handler and
  allocation = local.getInitializer() and
  allocation.getConstructedType().getASupertype*().getSourceDeclaration().hasQualifiedName(
    "java.util", ["Map", "Collection"]
  )
}

predicate stableRequestLocalInstance(
  MethodCall call, LocalVariableDecl local, VarAccess localAccess,
  ClassInstanceExpr allocation, LoopStmt loop
) {
  growthInLoopBody(call, loop) and
  not exists(LocalVariableDeclStmt declaration |
    declaration.getAVariable() = local.getDeclExpr() and
    declaration.getParent*() = loop.getBody()
  ) and
  dominates(allocation.getControlFlowNode(), loop.getControlFlowNode()) and
  not exists(VarAccess otherAccess |
    otherAccess.getVariable() = local and otherAccess != localAccess
  )
}

predicate emptyHashMapAllocation(ClassInstanceExpr allocation) {
  allocation.getNumArgument() = 0 and
  allocation.getConstructedType().getSourceDeclaration().hasQualifiedName(
    "java.util", "HashMap"
  )
}

predicate emptyArrayListAllocation(ClassInstanceExpr allocation) {
  allocation.getNumArgument() = 0 and
  allocation.getConstructedType().getSourceDeclaration().hasQualifiedName(
    "java.util", "ArrayList"
  )
}

/** The growth call is the loop's only top-level body statement. This admits
 * both an unbraced expression statement and a one-statement braced block,
 * while rejecting conditional, early-exit, continue, and multi-statement
 * bodies whose per-iteration execution is not statically proven here. */
predicate requestLocalUnconditionalIteration(MethodCall call, LoopStmt loop) {
  unconditionalTopLevelGrowthInLoop(call, loop)
}

predicate requestLocalGrowthShape(
  MethodCall call, LocalVariableDecl local, VarAccess localAccess,
  ClassInstanceExpr allocation, Expr demand, string demandRole, LoopStmt loop
) {
  stableRequestLocalInstance(call, local, localAccess, allocation, loop) and
  exists(ForStmt forLoop, Variable induction, Parameter bound,
         VarAccess boundAccess |
    loop = forLoop and
    canonicalAttackerBoundForLoop(
      forLoop, induction, bound, boundAccess
    ) and
    (
      demandRole = "key" and
      call.getMethod().getName() = "put" and
      emptyHashMapAllocation(allocation) and
      demand.(VarAccess).getVariable() = induction
      or
      demandRole = "value" and call.getMethod().getName() = "add" and
      call.getNumArgument() = 1 and
      emptyArrayListAllocation(allocation)
    )
  )
}

predicate requestLocalPerIterationGrowth(
  MethodCall call, LocalVariableDecl local, VarAccess localAccess,
  ClassInstanceExpr allocation, Expr demand, string demandRole, LoopStmt loop
) {
  requestLocalGrowthShape(
    call, local, localAccess, allocation, demand, demandRole, loop
  ) and
  requestLocalUnconditionalIteration(call, loop)
}

predicate requestLocalCardinality(
  MethodCall call, LocalVariableDecl local, VarAccess localAccess,
  ClassInstanceExpr allocation, Expr demand, string demandRole,
  string cardinalityNote, string coverageStatus
) {
  demandRole = ["key", "value"] and
  (
  exists(LoopStmt loop, Parameter bound, VarAccess boundAccess |
    provenAttackerLoopMultiplicity(call, loop, bound, boundAccess) and
    requestLocalPerIterationGrowth(
      call, local, localAccess, allocation, demand, demandRole, loop
    )
  ) and
  cardinalityNote = "attacker_controlled_loop_cardinality_proven" and
  coverageStatus = "complete"
  or
  not exists(LoopStmt loop |
    attackerControlsLoop(loop) and
    requestLocalPerIterationGrowth(
      call, local, localAccess, allocation, demand, demandRole, loop
    )
  ) and
  exists(LoopStmt loop |
    attackerControlsLoop(loop) and
    requestLocalGrowthShape(
      call, local, localAccess, allocation, demand, demandRole, loop
    )
  ) and
  cardinalityNote = "attacker_controlled_loop_per_iteration_execution_unproven" and
  coverageStatus = "partial"
  or
  not exists(LoopStmt loop |
    attackerControlsLoop(loop) and
    requestLocalGrowthShape(
      call, local, localAccess, allocation, demand, demandRole, loop
    )
  ) and
  exists(LoopStmt loop |
    attackerControlsLoop(loop) and
    stableRequestLocalInstance(call, local, localAccess, allocation, loop)
  ) and
  cardinalityNote = "attacker_controlled_loop_new_entry_unproven" and
  coverageStatus = "partial"
  or
  exists(LoopStmt loop |
    growthInLoopBody(call, loop) and attackerControlsLoop(loop)
  ) and
  not exists(LoopStmt loop |
    attackerControlsLoop(loop) and
    stableRequestLocalInstance(call, local, localAccess, allocation, loop)
  ) and
  cardinalityNote = "attacker_controlled_loop_instance_stability_unproven" and
  coverageStatus = "partial"
  or
  not exists(LoopStmt loop |
    growthInLoopBody(call, loop) and attackerControlsLoop(loop)
  ) and
  containerMultiplicity(call, cardinalityNote) and coverageStatus = "partial"
  )
}

predicate containerGrowthRow(
  MethodCall call, string operation, string resourceDimension, string receiver,
  string fieldPath, Expr demand, string demandRole, string escapeScope,
  string evidence, string coverageStatus, string coverageNote
) {
  exists(FieldAccess fieldReceiver, string multiplicityNote |
    containerWrite(call) and fieldReceiver = call.getQualifier() and
    containerDemand(call, demand, demandRole) and
    (
      fieldReceiver.getField().isStatic() and escapeScope = "global"
      or not fieldReceiver.getField().isStatic() and escapeScope = "instance"
    ) and
    containerMultiplicity(call, multiplicityNote) and
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
  exists(LocalVariableDecl local, VarAccess localAccess, Method handler,
         ClassInstanceExpr allocation, string driverNote, string cardinalityNote |
    containerWrite(call) and
    requestLocalContainer(call, local, localAccess, handler, allocation) and
    containerDemand(call, demand, demandRole) and
    requestLocalCardinality(
      call, local, localAccess, allocation, demand, demandRole,
      cardinalityNote, coverageStatus
    ) and
    (
      demandRole = "key" and demandUsesAttackerParameter(call, demand) and
      driverNote = "attacker_key_driver"
      or demandRole = "value" and demandUsesAttackerParameter(call, demand) and
      driverNote = "attacker_value_driver"
      or demandRole = "key" and fixedDemand(demand) and driverNote = "fixed_key"
      or demandRole = "key" and not fixedDemand(demand) and
         not demandUsesAttackerParameter(call, demand) and
         driverNote = "key_driver_unclassified"
      or demandRole = "value" and not demandUsesAttackerParameter(call, demand) and
         driverNote = "value_driver_unclassified"
    ) and
    operation = call.getMethod().getDeclaringType().getQualifiedName() + "." +
      call.getMethod().getName() and
    resourceDimension = "entries" and
    receiver = handler.getDeclaringType().getQualifiedName() + "." + local.getName() and
    fieldPath = local.getName() and escapeScope = "request" and
    evidence = "request_local_container_write" and
    coverageNote = "request_local_container_write:" + driverNote + ":" + cardinalityNote
  )
  or
  exists(LocalVariableDecl local, VarAccess localAccess, Method handler,
         ClassInstanceExpr allocation, Expr elementDemand, string elementRole,
         LoopStmt loop, Parameter bound, VarAccess boundAccess |
    containerWrite(call) and
    requestLocalContainer(call, local, localAccess, handler, allocation) and
    containerDemand(call, elementDemand, elementRole) and
    provenAttackerLoopMultiplicity(call, loop, bound, boundAccess) and
    requestLocalPerIterationGrowth(
      call, local, localAccess, allocation, elementDemand, elementRole, loop
    ) and
    demand = boundAccess and demandRole = "iteration_count" and
    operation = call.getMethod().getDeclaringType().getQualifiedName() + "." +
      call.getMethod().getName() and
    resourceDimension = "entries" and
    receiver = handler.getDeclaringType().getQualifiedName() + "." + local.getName() and
    fieldPath = local.getName() and escapeScope = "request" and
    evidence = "request_local_container_write" and coverageStatus = "complete" and
    coverageNote = "request_local_container_write:iteration_count:" +
      "attacker_controlled_loop_cardinality_proven"
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
