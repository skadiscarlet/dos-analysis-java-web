/**
 * @name Resource lifecycle facts
 * @description Raw allocation, holder, release, dispatch, and finite-capacity facts.
 * @kind table
 * @id dosweb/resource-lifecycle-facts
 */

import java
import semmle.code.java.dataflow.DataFlow

predicate allocationFlowsTo(Expr allocation, Expr sink) {
  exists(DataFlow::Node sourceNode, DataFlow::Node sinkNode |
    sourceNode.asExpr() = allocation and sinkNode.asExpr() = sink and
    DataFlow::localFlow(sourceNode, sinkNode)
  )
}

predicate allocationRequiresClose(Expr allocation) {
  exists(ClassInstanceExpr creation |
    allocation = creation and
    creation.getConstructedType().(RefType).getASupertype*().hasQualifiedName(
      "java.lang", "AutoCloseable"
    )
  )
}

string canonicalCallableIdentity(Callable callable) {
  result = "java-callable-v1:" + callable.getQualifiedName() + callable.getMethodDescriptor()
}

bindingset[site]
string programPointIdentity(Expr site) {
  exists(Callable callable |
    callable = site.getEnclosingCallable() and
    result = canonicalCallableIdentity(callable) + "#site:" +
      site.getLocation().getFile().getRelativePath() + ":" +
      site.getLocation().getStartLine().toString() + ":" +
      site.getLocation().getStartColumn().toString() + ":" +
      site.getLocation().getEndLine().toString() + ":" +
      site.getLocation().getEndColumn().toString()
  )
}

predicate exactSourceCallee(Method method) {
  method.fromSource() and
  (
    method.isStatic() or method.isPrivate() or method.isFinal() or
    method.getDeclaringType().(Class).isFinal()
  )
}

predicate knownContainerOrTaskCapture(MethodCall call, Expr captured) {
  (
    call.getMethod().getName() = ["add", "offer"] and call.getNumArgument() = 1 and
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName(
      "java.util", "Collection"
    ) and
    captured = call.getArgument(0)
  )
  or
  (
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName(
      "java.util", "Map"
    ) and
    (
      call.getMethod().getName() = ["put", "putIfAbsent", "replace"] and
      call.getNumArgument() = 2 and captured = call.getArgument(1)
      or
      call.getMethod().getName() = "replace" and call.getNumArgument() = 3 and
      captured = call.getArgument(2)
      or
      call.getMethod().getName() = "merge" and call.getNumArgument() = 3 and
      captured = call.getArgument(1)
    )
  )
  or
  (
    call.getMethod().getName() = ["execute", "submit", "schedule"] and
    call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName(
      "java.util.concurrent", "Executor"
    ) and
    captured = call.getArgument(0)
  )
}

predicate allocationEscapesToTrackedHolder(Expr allocation) {
  exists(Field field | field.getInitializer() = allocation)
  or
  exists(AssignExpr assignment, FieldAccess destination |
    assignment.getDest() = destination and
    allocationFlowsTo(allocation, assignment.getSource()) and
    not exists(Field field | field.getInitializer() = allocation)
  )
  or
  exists(MethodCall capture, Expr captured |
    knownContainerOrTaskCapture(capture, captured) and
    allocationFlowsTo(allocation, captured)
  )
}

predicate trackedAllocation(Expr allocation) {
  allocation.getLocation().getFile().getRelativePath().matches("%.java") and
  (allocation instanceof ClassInstanceExpr or allocation instanceof ArrayCreationExpr) and
  (allocationRequiresClose(allocation) or allocationEscapesToTrackedHolder(allocation))
}

Field queueReceiver(MethodCall call) {
  exists(VarAccess receiver |
    receiver = call.getQualifier() and result = receiver.getVariable().(Field)
  )
  or
  exists(FieldAccess receiver |
    receiver = call.getQualifier() and result = receiver.getField()
  )
}

predicate supportedQueueFieldType(Field field) {
  (
    field.getType().getErasure().(RefType).hasQualifiedName("java.util", "Queue")
    or
    field.getType().getErasure().(RefType).hasQualifiedName("java.util.concurrent", "BlockingQueue")
    or
    field.getType().getErasure().(RefType).hasQualifiedName(
      "java.util.concurrent", ["ArrayBlockingQueue", "LinkedBlockingQueue"]
    )
  )
}

predicate queueSubmission(MethodCall call, Field field) {
  field = queueReceiver(call) and supportedQueueFieldType(field) and
  call.getMethod().getName() = ["add", "offer"] and call.getNumArgument() = 1
}

string finiteQueueCapacity(Field field) {
  exists(ClassInstanceExpr creation, CompileTimeConstantExpr capacity |
    field.isFinal() and
    creation = field.getInitializer() and
    creation.getConstructedType().getErasure().(RefType).hasQualifiedName(
      "java.util.concurrent", ["ArrayBlockingQueue", "LinkedBlockingQueue"]
    ) and
    capacity = creation.getArgument(0) and
    result = capacity.toString()
  )
}

string fieldHolderScope(Field field) {
  field.isStatic() and result = "global"
  or
  not field.isStatic() and result = "instance"
}

predicate autoCloseableReleaseMethod(Method method) {
  method.getName() = "close" and method.getNumberOfParameters() = 0 and
  exists(Method contract |
    contract.getDeclaringType().hasQualifiedName("java.lang", "AutoCloseable") and
    contract.getName() = "close" and contract.getNumberOfParameters() = 0 and
    (method = contract or method.getAnOverride() = contract)
  )
}

predicate singleExecutionAllocationContext(Expr allocation) {
  not exists(LoopStmt loop | allocation.getParent*() = loop)
}

predicate exactLocalReleaseBinding(MethodCall release, Expr allocation) {
  exists(VarAccess receiver, LocalVariableDecl local |
    receiver = release.getQualifier() and receiver.getVariable() = local and
    (
      local.getInitializer() = allocation and
      forall(Expr assigned | local.getAnAssignedValue() = assigned | assigned = allocation)
      or
      exists(AssignExpr binding |
        binding.getSource() = allocation and binding.getDest().(VarAccess).getVariable() = local and
        (not exists(local.getInitializer()) or local.getInitializer() instanceof NullLiteral) and
        forall(Expr assigned | local.getAnAssignedValue() = assigned |
          assigned = allocation
          or
          assigned = local.getInitializer() and assigned instanceof NullLiteral
        )
      )
    )
  )
}

predicate mustReleaseInFinally(MethodCall release, Expr allocation) {
  exactLocalReleaseBinding(release, allocation) and singleExecutionAllocationContext(allocation) and
  release.getEnclosingCallable() = allocation.getEnclosingCallable() and
  exists(TryStmt attempt, BlockStmt cleanup |
    cleanup = attempt.getFinally() and cleanup.getNumStmt() = 1 and
    cleanup.getStmt(0) = release.getEnclosingStmt() and
    attempt.getBlock().(BlockStmt).getAStmt() = allocation.getEnclosingStmt()
  )
}

predicate exactNormalRelease(MethodCall release, Expr allocation) {
  exactLocalReleaseBinding(release, allocation) and singleExecutionAllocationContext(allocation) and
  (
    release.getBasicBlock().postDominates(allocation.getBasicBlock())
    or
    mustReleaseInFinally(release, allocation)
  )
}

predicate lifecycleFact(
  Expr allocation, Expr site, Callable owner, string factKind, boolean requiresClose,
  string holderKind, string holderScope, string holderKey, string targetEvent, string capacityValue,
  boolean normalPath, boolean exceptionalPath, string evidence,
  string coverageStatus, string coverageNote
) {
  trackedAllocation(allocation) and owner = allocation.getEnclosingCallable() and owner.fromSource() and
  (
    allocationRequiresClose(allocation) and requiresClose = true
    or
    not allocationRequiresClose(allocation) and requiresClose = false
  ) and
  (
    site = allocation and factKind = "create" and
    holderKind = "none" and holderScope = "none" and holderKey = "none" and
    targetEvent = "none" and capacityValue = "unknown" and
    normalPath = true and exceptionalPath = true and
    (
      requiresClose = true and evidence = "codeql_auto_closeable_allocation"
      or
      requiresClose = false and evidence = "codeql_escaping_heap_allocation"
    ) and
    coverageStatus = "complete" and coverageNote = "allocation_identity_exact"
    or
    exists(LocalVariableDecl local |
      local.getInitializer() = allocation and site = allocation and factKind = "retain" and
      holderKind = "local" and holderScope = "instance" and
      holderKey = canonicalCallableIdentity(owner) + ":local:" + local.getName() and
      targetEvent = "none" and capacityValue = "unknown" and normalPath = true and exceptionalPath = true and
      evidence = "codeql_local_initializer_binding" and coverageStatus = "complete" and
      coverageNote = "local_holder_identity_exact"
    )
    or
    exists(Field field |
      field.getInitializer() = allocation and site = allocation and factKind = "retain" and
      holderKind = "field" and holderScope = fieldHolderScope(field) and
      holderKey = field.getDeclaringType().getQualifiedName() + "." + field.getName() and
      targetEvent = "none" and capacityValue = "unknown" and
      normalPath = true and exceptionalPath = false and
      evidence = "codeql_field_initializer_binding" and coverageStatus = "complete" and
      coverageNote = "field_initializer_identity_exact"
    )
    or
    exists(AssignExpr assignment, FieldAccess destination |
      assignment.getDest() = destination and allocationFlowsTo(allocation, assignment.getSource()) and
      not exists(Field field | field.getInitializer() = allocation) and
      assignment.getEnclosingCallable() = owner and site = assignment and factKind = "retain" and
      holderKind = "field" and holderScope = fieldHolderScope(destination.getField()) and
      holderKey = destination.getField().getDeclaringType().getQualifiedName() + "." + destination.getField().getName() and
      targetEvent = "none" and capacityValue = "unknown" and normalPath = true and exceptionalPath = false and
      evidence = "codeql_allocation_to_field_assignment" and coverageStatus = "complete" and
      coverageNote = "same_callable_local_flow_to_field"
    )
    or
    exists(MethodCall release |
      release.getEnclosingCallable() = owner and release.getNumArgument() = 0 and
      autoCloseableReleaseMethod(release.getMethod()) and
      allocationFlowsTo(allocation, release.getQualifier()) and site = release and factKind = "release" and
      holderKind = "none" and holderScope = "none" and holderKey = "none" and
      targetEvent = "none" and capacityValue = "unknown" and
      (
        exactNormalRelease(release, allocation) and normalPath = true
        or
        not exactNormalRelease(release, allocation) and normalPath = false
      ) and
      (
        mustReleaseInFinally(release, allocation) and exceptionalPath = true
        or
        not mustReleaseInFinally(release, allocation) and exceptionalPath = false
      ) and
      evidence = "codeql_close_receiver_local_flow_candidate" and
      (
        not singleExecutionAllocationContext(allocation) and coverageStatus = "partial" and
        coverageNote = "allocation_in_loop_release_not_must"
        or
        mustReleaseInFinally(release, allocation) and coverageStatus = "complete" and
        coverageNote = "singleton_finally_exact_local_release"
        or
        exactNormalRelease(release, allocation) and not mustReleaseInFinally(release, allocation) and
        coverageStatus = "partial" and coverageNote = "release_missing_exceptional_path"
        or
        singleExecutionAllocationContext(allocation) and not exactNormalRelease(release, allocation) and
        coverageStatus = "partial" and
        coverageNote = "conditional_release_not_must"
      )
    )
    or
    exists(MethodCall submit, Field queue |
      submit.getEnclosingCallable() = owner and queueSubmission(submit, queue) and
      allocationFlowsTo(allocation, submit.getArgument(0)) and site = submit and factKind = "dispatch" and
      holderKind = "queue" and holderScope = "task" and
      holderKey = queue.getDeclaringType().getQualifiedName() + "." + queue.getName() and
      targetEvent = canonicalCallableIdentity(owner) + "#queue" and
      (
        capacityValue = finiteQueueCapacity(queue)
        or
        not exists(finiteQueueCapacity(queue)) and capacityValue = "unknown"
      ) and
      normalPath = true and exceptionalPath = false and evidence = "codeql_queue_argument_local_flow" and
      coverageStatus = "complete" and coverageNote = "queue_capture_on_success"
    )
    or
    exists(MethodCall unknown |
      unknown.getEnclosingCallable() = owner and
      (
        allocationFlowsTo(allocation, unknown.getAnArgument())
        or allocationFlowsTo(allocation, unknown.getQualifier()) and
        not autoCloseableReleaseMethod(unknown.getMethod())
      ) and
      not exists(Field queue | queueSubmission(unknown, queue)) and
      site = unknown and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(unknown.getMethod()) and capacityValue = "unknown" and
      normalPath = true and exceptionalPath = true and evidence = "codeql_unmodeled_argument_escape" and
      coverageStatus = "partial" and
      (
        exactSourceCallee(unknown.getMethod()) and
        coverageNote = "callee_resource_effects_unmodeled"
        or
        unknown.getMethod().fromSource() and not exactSourceCallee(unknown.getMethod()) and
        coverageNote = "source_callee_dispatch_target_unresolved"
        or
        not unknown.getMethod().fromSource() and
        coverageNote = "external_callee_resource_effects_unmodeled"
      )
    )
    or
    exists(ReturnStmt returned |
      returned.getEnclosingCallable() = owner and allocationFlowsTo(allocation, returned.getExpr()) and
      site = returned.getExpr() and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and targetEvent = "none" and capacityValue = "unknown" and
      normalPath = true and exceptionalPath = false and evidence = "codeql_resource_return_escape" and
      coverageStatus = "partial" and coverageNote = "returned_resource_ownership_unmodeled"
    )
    or
    exists(MethodCall submit, Field queue |
      submit.getEnclosingCallable() = owner and queueSubmission(submit, queue) and
      allocationFlowsTo(allocation, submit.getArgument(0)) and exists(finiteQueueCapacity(queue)) and
      site = submit and factKind = "invariant" and holderKind = "queue" and
      holderScope = "task" and
      holderKey = queue.getDeclaringType().getQualifiedName() + "." + queue.getName() and
      targetEvent = canonicalCallableIdentity(owner) + "#queue" and capacityValue = finiteQueueCapacity(queue) and
      normalPath = true and exceptionalPath = false and evidence = "codeql_finite_queue_capacity" and
      coverageStatus = "complete" and coverageNote = "exact_bounded_queue_constructor_capacity"
    )
  )
}

from Expr allocation, Expr site, Callable owner, string factKind, boolean requiresClose,
  string holderKind, string holderScope, string holderKey, string targetEvent, string capacityValue,
  boolean normalPath, boolean exceptionalPath, string evidence,
  string coverageStatus, string coverageNote
where lifecycleFact(
  allocation, site, owner, factKind, requiresClose, holderKind, holderScope, holderKey, targetEvent, capacityValue,
  normalPath, exceptionalPath, evidence, coverageStatus, coverageNote
)
select
  canonicalCallableIdentity(owner) as unit_id,
  canonicalCallableIdentity(site.getEnclosingCallable()) as site_callable,
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  site.getLocation().getStartColumn() as site_start_column,
  programPointIdentity(site) as program_point,
  "none" as related_point,
  0 as relation_depth,
  -1 as binding_index,
  factKind as fact_kind,
  allocation.getLocation().getFile().getRelativePath() + ":" +
    allocation.getLocation().getStartLine().toString() + ":" +
    allocation.getLocation().getStartColumn().toString() as instance_key,
  allocation.getType().toString() as resource_type,
  requiresClose as requires_close,
  holderKind as holder_kind,
  holderScope as holder_scope,
  holderKey as holder_key,
  targetEvent as target_event,
  capacityValue as capacity,
  "unknown" as max_workers,
  "unknown" as rejection_policy,
  normalPath as normal_path,
  exceptionalPath as exceptional_path,
  evidence as source_evidence,
  coverageStatus as coverage_status,
  coverageNote as coverage_note
