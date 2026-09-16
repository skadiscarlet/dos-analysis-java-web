/**
 * @name Resource lifecycle facts
 * @description Raw allocation, holder, release, dispatch, and finite-capacity facts.
 * @kind table
 * @id dosweb/resource-lifecycle-facts
 */

import java
import semmle.code.java.dataflow.DataFlow
private import codeql.controlflow.SuccessorType

predicate allocationFlowsTo(Expr allocation, Expr sink) {
  exists(DataFlow::Node sourceNode, DataFlow::Node sinkNode |
    sourceNode.asExpr() = allocation and sinkNode.asExpr() = sink and
    DataFlow::localFlow(sourceNode, sinkNode)
  )
  or
  exists(MethodCall returned, Parameter parameter, int depth |
    depth in [1 .. 2] and returnsParameterAtDepth(returned.getMethod(), parameter, depth) and
    DataFlow::localFlow(DataFlow::exprNode(allocation), DataFlow::exprNode(returned.getArgument(parameter.getPosition()))) and
    DataFlow::localFlow(DataFlow::exprNode(returned), DataFlow::exprNode(sink))
  )
}

/** Finite nonrecursive summary: every normal return preserves this parameter identity. */
predicate returnsParameterAtDepth(Method method, Parameter parameter, int depth) {
  exactSourceCallee(method) and parameter.getCallable() = method and depth in [1 .. 2] and
  not exists(parameter.getAnAssignedValue()) and
  exists(ReturnStmt returned | returned.getEnclosingCallable() = method) and
  forall(ReturnStmt returned | returned.getEnclosingCallable() = method |
    returned.getExpr().(VarAccess).getVariable() = parameter
    or
    exists(MethodCall nested, Parameter nestedParameter |
      depth = 2 and nested = returned.getExpr() and nested.getMethod() != method and
      returnsParameterAtDepth(nested.getMethod(), nestedParameter, 1) and
      nested.getArgument(nestedParameter.getPosition()).(VarAccess).getVariable() = parameter
    )
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

string declaredCallableIdentity(Callable callable) {
  result = "java-callable-v1:" + callable.getQualifiedName() + callable.getMethodDescriptor()
}

string canonicalCallableIdentity(Callable callable) {
  exists(LambdaExpr lambda |
    lambda.asMethod() = callable and
    result = declaredCallableIdentity(lambda.getEnclosingCallable()) + "#lambda:" +
      lambda.getLocation().getFile().getRelativePath() + ":" +
      lambda.getLocation().getStartLine().toString() + ":" +
      lambda.getLocation().getStartColumn().toString() + ":" +
      lambda.getLocation().getEndLine().toString() + ":" +
      lambda.getLocation().getEndColumn().toString() + callable.getMethodDescriptor()
  )
  or
  not exists(LambdaExpr lambda | lambda.asMethod() = callable) and
  result = declaredCallableIdentity(callable)
}

Callable enclosingCallable(ExprParent site) {
  site instanceof Expr and result = site.(Expr).getEnclosingCallable()
  or
  site instanceof Stmt and result = site.(Stmt).getEnclosingCallable()
}

ControlFlowNode controlFlowNode(ExprParent site) {
  site instanceof Expr and result = site.(Expr).getControlFlowNode()
  or
  site instanceof Stmt and result = site.(Stmt).getControlFlowNode()
}

/** One AST-level CFG step; synthetic CFG nodes may be traversed, AST nodes may not. */
predicate isAstControlFlowNode(ControlFlowNode node) {
  node.injects(_) or
  node instanceof ControlFlow::EntryNode or
  node instanceof ControlFlow::AnnotatedExitNode or
  node instanceof ControlFlow::ExitNode
}

predicate successorAfterNonAstNodes(ControlFlowNode source, ControlFlowNode target) {
  target = source.getASuccessor() and isAstControlFlowNode(target)
  or
  exists(ControlFlowNode middle |
    middle = source.getASuccessor() and
    not isAstControlFlowNode(middle) and
    successorAfterNonAstNodes(middle, target)
  )
}

predicate normalSuccessorAfterNonAstNodes(ControlFlowNode source, ControlFlowNode target) {
  target = source.getASuccessor(any(SuccessorType kind | not kind instanceof ExceptionSuccessor)) and
  isAstControlFlowNode(target)
  or
  exists(ControlFlowNode middle |
    middle = source.getASuccessor(any(SuccessorType kind | not kind instanceof ExceptionSuccessor)) and
    not isAstControlFlowNode(middle) and
    // Only the operation's first edge classifies its outcome. A synthetic
    // finally bridge can subsequently restore an already-pending exception.
    successorAfterNonAstNodes(middle, target)
  )
}

predicate exceptionalSuccessorAfterNonAstNodes(ControlFlowNode source, ControlFlowNode target) {
  target = source.getAnExceptionSuccessor() and isAstControlFlowNode(target)
  or
  exists(ControlFlowNode middle |
    middle = source.getAnExceptionSuccessor() and not isAstControlFlowNode(middle) and
    successorAfterNonAstNodes(middle, target)
  )
}

bindingset[site]
string programPointIdentity(ExprParent site) {
  exists(Callable callable |
    callable = enclosingCallable(site) and
    result = canonicalCallableIdentity(callable) + "#site:" +
      site.getLocation().getFile().getRelativePath() + ":" +
      site.getLocation().getStartLine().toString() + ":" +
      site.getLocation().getStartColumn().toString() + ":" +
      site.getLocation().getEndLine().toString() + ":" +
      site.getLocation().getEndColumn().toString()
  )
}

bindingset[parameter]
string parameterPointIdentity(Parameter parameter) {
  result = canonicalCallableIdentity(parameter.getCallable()) + "#site:" +
    parameter.getLocation().getFile().getRelativePath() + ":" +
    parameter.getLocation().getStartLine().toString() + ":" +
    parameter.getLocation().getStartColumn().toString() + ":" +
    parameter.getLocation().getEndLine().toString() + ":" +
    parameter.getLocation().getEndColumn().toString()
}

string allocationInstanceKey(Expr allocation) {
  result = allocation.getLocation().getFile().getRelativePath() + ":" +
    allocation.getLocation().getStartLine().toString() + ":" +
    allocation.getLocation().getStartColumn().toString()
}

predicate exactSourceCallee(Method method) {
  method.fromSource() and not method.isNative() and
  (
    method.isStatic() or method.isPrivate() or method.isFinal() or
    method.getDeclaringType().(Class).isFinal()
  )
}

predicate exactArgumentBinding(Expr value, MethodCall call, Parameter parameter) {
  exists(int position |
    position = parameter.getPosition() and position >= 0 and
    parameter = call.getMethod().getParameter(position) and
    exactSourceCallee(call.getMethod()) and
    allocationFlowsTo(value, call.getArgument(position))
  )
}

predicate rootCallBinding(
  Expr allocation, MethodCall call, Parameter parameter, int depth
) {
  (
    depth = 1 and exactArgumentBinding(allocation, call, parameter) and
    call.getEnclosingCallable() = allocation.getEnclosingCallable() and
    call.getMethod() != call.getEnclosingCallable()
  )
  or
  exists(MethodCall firstCall, Parameter firstParameter, int position |
    depth = 2 and exactArgumentBinding(allocation, firstCall, firstParameter) and
    firstCall.getEnclosingCallable() = allocation.getEnclosingCallable() and
    firstCall.getMethod() != firstCall.getEnclosingCallable() and
    position = parameter.getPosition() and parameter = call.getMethod().getParameter(position) and
    exactSourceCallee(call.getMethod()) and
    DataFlow::localFlow(DataFlow::parameterNode(firstParameter), DataFlow::exprNode(call.getArgument(position))) and
    call.getEnclosingCallable() = firstParameter.getCallable() and
    call.getMethod() != call.getEnclosingCallable() and
    call.getMethod() != firstCall.getEnclosingCallable()
  )
}

predicate rootDepthLimitExceeded(Expr allocation, MethodCall thirdCall) {
  exists(
    MethodCall secondCall, Parameter secondParameter, VarAccess parameterAccess,
    int depth, Parameter thirdParameter
  |
    depth = 2 and rootCallBinding(allocation, secondCall, secondParameter, depth) and
    parameterAccess.getVariable() = secondParameter and
    parameterAccess.getEnclosingCallable() = secondParameter.getCallable() and
    exactArgumentBinding(parameterAccess, thirdCall, thirdParameter) and
    thirdCall.getEnclosingCallable() = secondParameter.getCallable()
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
  not exists(LoopStmt loop | allocation.getEnclosingStmt().getEnclosingStmt*() = loop)
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

/** A loop-local slot whose only reads are exact close receivers. Null writes
 * retire that slot explicitly; aliases, escapes and any other assignments are
 * deliberately outside this small recency-preserving model. */
predicate isolatedLoopLocal(Expr allocation, LocalVariableDecl local) {
  local.getInitializer() = allocation and
  exists(LoopStmt loop | allocation.getEnclosingStmt().getEnclosingStmt*() = loop) and
  forall(Expr assigned | local.getAnAssignedValue() = assigned |
    assigned = allocation or assigned instanceof NullLiteral
  ) and
  forall(VarAccess access | access.getVariable() = local |
    access.getEnclosingCallable() = allocation.getEnclosingCallable() and (
    exists(MethodCall release |
      release.getQualifier() = access and release.getNumArgument() = 0 and
      autoCloseableReleaseMethod(release.getMethod())
    )
    or
    exists(AssignExpr reset | reset.getDest() = access and reset.getSource() instanceof NullLiteral)
    )
  )
}

predicate exactLoopLocalRelease(MethodCall release, Expr allocation) {
  exists(LocalVariableDecl local |
    isolatedLoopLocal(allocation, local) and
    release.getQualifier().(VarAccess).getVariable() = local
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
    exists(AssignExpr reset, LocalVariableDecl local |
      isolatedLoopLocal(allocation, local) and reset.getDest().(VarAccess).getVariable() = local and
      reset.getSource() instanceof NullLiteral and reset.getEnclosingCallable() = owner and
      site = reset and factKind = "drop" and holderKind = "none" and holderScope = "none" and
      holderKey = "none" and targetEvent = "none" and capacityValue = "unknown" and
      normalPath = true and exceptionalPath = false and evidence = "codeql_isolated_loop_local_null_drop" and
      coverageStatus = "complete" and coverageNote = "isolated_loop_local_explicit_null"
    )
    or
    exists(MethodCall release |
      release.getEnclosingCallable() = owner and release.getNumArgument() = 0 and
      autoCloseableReleaseMethod(release.getMethod()) and
      allocationFlowsTo(allocation, release.getQualifier()) and site = release and factKind = "release" and
      holderKind = "none" and holderScope = "none" and holderKey = "none" and
      targetEvent = "none" and capacityValue = "unknown" and
      (
        (exactNormalRelease(release, allocation) or exactLoopLocalRelease(release, allocation)) and normalPath = true
        or
        not exactNormalRelease(release, allocation) and not exactLoopLocalRelease(release, allocation) and normalPath = false
      ) and
      (
        mustReleaseInFinally(release, allocation) and exceptionalPath = true
        or
        not mustReleaseInFinally(release, allocation) and exceptionalPath = false
      ) and
      evidence = "codeql_close_receiver_local_flow_candidate" and
      (
        exactLoopLocalRelease(release, allocation) and coverageStatus = "complete" and
        coverageNote = "isolated_loop_local_exact_release"
        or
        not singleExecutionAllocationContext(allocation) and not exactLoopLocalRelease(release, allocation) and
        coverageStatus = "partial" and coverageNote = "allocation_in_loop_release_not_must"
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
      not exists(Parameter parameter, int depth |
        rootCallBinding(allocation, unknown, parameter, depth)
      ) and
      site = unknown and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(unknown.getMethod()) and capacityValue = "unknown" and
      normalPath = true and exceptionalPath = true and evidence = "codeql_unmodeled_argument_escape" and
      coverageStatus = "partial" and
      (
        unknown.getMethod() = owner and
        coverageNote = "recursive_call_target_unresolved"
        or
        unknown.getMethod().isNative() and
        coverageNote = "native_callee_resource_effects_unmodeled"
        or
        unknown.getMethod().getDeclaringType().hasQualifiedName(
          "java.lang.reflect", ["Method", "Constructor"]
        ) and
        coverageNote = "reflection_dispatch_target_unresolved"
        or
        exactSourceCallee(unknown.getMethod()) and unknown.getMethod() != owner and
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

predicate allocationCloseFlag(Expr allocation, boolean requiresClose) {
  allocationRequiresClose(allocation) and requiresClose = true
  or
  not allocationRequiresClose(allocation) and requiresClose = false
}

predicate lifecycleRelationFact(
  Expr allocation, ExprParent site, Callable owner, string factKind,
  boolean requiresClose, string holderKind, string holderScope, string holderKey,
  string targetEvent, string capacityValue, string coreWorkersValue, string maxWorkersValue,
  string rejectionPolicyValue, boolean normalPath, boolean exceptionalPath,
  string evidence, string coverageStatus, string coverageNote,
  string programPoint, string relatedPoint, Parameter relatedParameter,
  int relationDepth, int bindingIndex
) {
  trackedAllocation(allocation) and owner = allocation.getEnclosingCallable() and
  owner.fromSource() and allocationCloseFlag(allocation, requiresClose) and
  (
    exists(MethodCall call, Parameter parameter, int depth |
      rootCallBinding(allocation, call, parameter, depth) and site = call and
      factKind = "call_binding" and holderKind = "none" and holderScope = "none" and
      holderKey = "none" and targetEvent = canonicalCallableIdentity(call.getMethod()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = true and
      evidence = "codeql_exact_argument_parameter_binding" and
      coverageStatus = "complete" and coverageNote = "exact_non_virtual_source_callee" and
      programPoint = programPointIdentity(call) and
      relatedPoint = parameterPointIdentity(parameter) and
      relatedParameter = parameter and relationDepth = depth and
      bindingIndex = parameter.getPosition()
    )
    or
    exists(
      MethodCall call, Parameter parameter, int depth, AssignExpr assignment,
      FieldAccess destination, VarAccess parameterAccess
    |
      rootCallBinding(allocation, call, parameter, depth) and
      parameterAccess.getVariable() = parameter and
      parameterAccess.getEnclosingCallable() = parameter.getCallable() and
      DataFlow::localFlow(DataFlow::parameterNode(parameter), DataFlow::exprNode(parameterAccess)) and
      assignment.getSource() = parameterAccess and assignment.getDest() = destination and
      assignment.getEnclosingCallable() = parameter.getCallable() and
      site = assignment and factKind = "retain" and
      targetEvent = "none" and capacityValue = "unknown" and
      coreWorkersValue = "unknown" and maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = false and
      holderKind = "field" and
      (
        destination.getField().isStatic() and holderScope = "global" and
        holderKey = destination.getField().getDeclaringType().getQualifiedName() + "." +
          destination.getField().getName() + "#static" and
        evidence = "codeql_parameter_to_static_field_effect" and coverageStatus = "complete" and
        coverageNote = "exact_static_field_identity"
        or
        not destination.getField().isStatic() and holderScope = "instance" and
        holderKey = destination.getField().getDeclaringType().getQualifiedName() + "." +
          destination.getField().getName() and
        evidence = "codeql_parameter_to_instance_field_effect" and coverageStatus = "partial" and
        coverageNote = "field_receiver_identity_unresolved"
      ) and
      programPoint = programPointIdentity(assignment) and
      relatedPoint = parameterPointIdentity(parameter) and relatedParameter = parameter and
      relationDepth = depth and bindingIndex = parameter.getPosition()
    )
    or
    exists(
      MethodCall call, Parameter parameter, int depth, MethodCall release,
      VarAccess receiver
    |
      rootCallBinding(allocation, call, parameter, depth) and
      receiver = release.getQualifier() and receiver.getVariable() = parameter and
      release.getEnclosingCallable() = parameter.getCallable() and
      DataFlow::localFlow(DataFlow::parameterNode(parameter), DataFlow::exprNode(receiver)) and
      release.getNumArgument() = 0 and autoCloseableReleaseMethod(release.getMethod()) and
      site = release and factKind = "release" and
      holderKind = "none" and holderScope = "none" and holderKey = "none" and
      targetEvent = "none" and capacityValue = "unknown" and
      coreWorkersValue = "unknown" and maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = false and
      evidence = "codeql_parameter_close_effect" and coverageStatus = "partial" and
      coverageNote = "conditional_release_not_must" and
      programPoint = programPointIdentity(release) and
      relatedPoint = parameterPointIdentity(parameter) and relatedParameter = parameter and
      relationDepth = depth and bindingIndex = parameter.getPosition()
    )
    or
    exists(
      MethodCall call, Parameter parameter, int depth, ReturnStmt returned,
      VarAccess returnedValue
    |
      rootCallBinding(allocation, call, parameter, depth) and
      returned.getExpr() = returnedValue and returnedValue.getVariable() = parameter and
      returned.getEnclosingCallable() = parameter.getCallable() and
      DataFlow::localFlow(DataFlow::parameterNode(parameter), DataFlow::exprNode(returnedValue)) and
      site = returned and factKind = "retain" and
      holderKind = "local" and holderScope = "instance" and
      holderKey = canonicalCallableIdentity(parameter.getCallable()) + "#return" and
      targetEvent = "none" and capacityValue = "unknown" and
      coreWorkersValue = "unknown" and maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = false and
      evidence = "codeql_parameter_return_binding" and coverageStatus = "complete" and
      coverageNote = "returned_resource_identity_bound" and
      programPoint = programPointIdentity(returned) and
      relatedPoint = parameterPointIdentity(parameter) and relatedParameter = parameter and
      relationDepth = depth and bindingIndex = parameter.getPosition()
    )
    or
    exists(
      MethodCall call, Parameter parameter, int depth, MethodCall unknown, Expr value
    |
      rootCallBinding(allocation, call, parameter, depth) and
      unknown.getEnclosingCallable() = parameter.getCallable() and
      (value = unknown.getAnArgument() or value = unknown.getQualifier()) and
      DataFlow::localFlow(DataFlow::parameterNode(parameter), DataFlow::exprNode(value)) and
      not autoCloseableReleaseMethod(unknown.getMethod()) and
      not exists(Parameter targetParameter, int targetDepth |
        rootCallBinding(allocation, unknown, targetParameter, targetDepth)
      ) and
      not rootDepthLimitExceeded(allocation, unknown) and
      site = unknown and factKind = "unknown_call" and
      holderKind = "none" and holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(unknown.getMethod()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and rejectionPolicyValue = "unknown" and
      normalPath = true and exceptionalPath = true and
      evidence = "codeql_parameter_unknown_call" and coverageStatus = "partial" and
      coverageNote = "callee_resource_effects_unmodeled" and
      programPoint = programPointIdentity(unknown) and
      relatedPoint = parameterPointIdentity(parameter) and relatedParameter = parameter and
      relationDepth = depth and bindingIndex = -1
    )
    or
    exists(MethodCall call, Parameter parameter |
      rootDepthLimitExceeded(allocation, call) and
      parameter = call.getMethod().getParameter(parameter.getPosition()) and
      site = call and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(call.getMethod()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = true and
      evidence = "codeql_call_depth_coverage_gap" and coverageStatus = "partial" and
      coverageNote = "exact_call_depth_exceeds_2" and
      programPoint = programPointIdentity(call) and
      relatedPoint = parameterPointIdentity(parameter) and
      relatedParameter = parameter and relationDepth = 2 and
      bindingIndex = parameter.getPosition()
    )
  )
}

/** The root and its finite, exact, nonrecursive callee scopes. */
predicate resourceCallableScope(Expr allocation, Callable callable, int depth) {
  callable = allocation.getEnclosingCallable() and depth = 0
  or
  exists(MethodCall call, Parameter parameter |
    rootCallBinding(allocation, call, parameter, depth) and callable = parameter.getCallable()
  )
}

/** Executor rejection is unchecked and is omitted by the standard CFG when
 * there is no enclosing handler. Add only its unhandled operation outcome;
 * catch/finally/try-with-resources continuations remain standard CFG edges.
 */
predicate handlerFreeCall(MethodCall call) {
  not exists(TryStmt attempt |
    call.getEnclosingStmt().getEnclosingStmt*() = attempt or
    call.getParent*() = attempt
  )
}

predicate executorRejectionCall(MethodCall call) {
  call.getMethod().getName() = ["execute", "submit"] and
  call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName(
    "java.util.concurrent", "Executor"
  )
}

/** The same finite exact-call depth used by resource argument bindings. */
predicate unhandledExecutorRejection(MethodCall call, int depth) {
  handlerFreeCall(call) and
  (
    depth = 0 and executorRejectionCall(call)
    or
    depth in [1 .. 2] and exactSourceCallee(call.getMethod()) and
    exists(MethodCall inner |
      inner.getEnclosingCallable() = call.getMethod() and
      inner.getMethod() != call.getMethod() and
      unhandledExecutorRejection(inner, depth - 1)
    )
  )
}

/** Real CFG edges and explicit boundary nodes; source coordinates are evidence only. */
predicate callableCfgFact(
  Expr allocation, ExprParent site, ExprParent relatedSite, Callable owner,
  string programPoint, string relatedPoint, string targetEvent, int depth,
  boolean normalPath, boolean exceptionalPath, string evidence
) {
  trackedAllocation(allocation) and owner = allocation.getEnclosingCallable() and owner.fromSource() and
  exists(Callable callable |
    resourceCallableScope(allocation, callable, depth) and exists(callable.getBody()) and
    targetEvent = canonicalCallableIdentity(callable) and
    (
      enclosingCallable(site) = callable and enclosingCallable(relatedSite) = callable and
      site != relatedSite and
      successorAfterNonAstNodes(controlFlowNode(site), controlFlowNode(relatedSite)) and
      programPoint = programPointIdentity(site) and relatedPoint = programPointIdentity(relatedSite) and
      (
        normalSuccessorAfterNonAstNodes(controlFlowNode(site), controlFlowNode(relatedSite)) and
        normalPath = true and exceptionalPath = false
        or
        exceptionalSuccessorAfterNonAstNodes(controlFlowNode(site), controlFlowNode(relatedSite)) and
        normalPath = false and exceptionalPath = true
      ) and evidence = "codeql_callable_cfg_edge"
      or
      exists(ControlFlow::EntryNode entry |
        entry.getEnclosingCallable() = callable and
        successorAfterNonAstNodes(entry, controlFlowNode(relatedSite)) and
        site = callable.getBody() and
        programPoint = targetEvent + "#cfg_entry" and relatedPoint = programPointIdentity(relatedSite) and
        normalPath = true and exceptionalPath = false and evidence = "codeql_callable_cfg_entry"
      )
      or
      exists(ControlFlow::AnnotatedExitNode terminal |
        terminal.getEnclosingCallable() = callable and enclosingCallable(site) = callable and
        successorAfterNonAstNodes(controlFlowNode(site), terminal) and relatedSite = callable.getBody() and
        programPoint = programPointIdentity(site) and
        (
          terminal instanceof ControlFlow::NormalExitNode and normalPath = true and exceptionalPath = false and
          relatedPoint = targetEvent + "#cfg_normal_exit"
          or
          terminal instanceof ControlFlow::ExceptionalExitNode and normalPath = false and exceptionalPath = true and
          relatedPoint = targetEvent + "#cfg_exceptional_exit"
        ) and
        (
          normalSuccessorAfterNonAstNodes(controlFlowNode(site), terminal) and
          evidence = "codeql_callable_cfg_exit_after_success"
          or
          exceptionalSuccessorAfterNonAstNodes(controlFlowNode(site), terminal) and
          evidence = "codeql_callable_cfg_exit_after_exception"
        )
      )
      or
      exists(MethodCall rejected, int wrapperDepth |
        rejected.getEnclosingCallable() = callable and
        unhandledExecutorRejection(rejected, wrapperDepth) and
        not exists(rejected.getControlFlowNode().getAnExceptionSuccessor()) and
        site = rejected and relatedSite = callable.getBody() and
        programPoint = programPointIdentity(rejected) and
        relatedPoint = targetEvent + "#cfg_exceptional_exit" and
        normalPath = false and exceptionalPath = true and
        evidence = "codeql_callable_cfg_modeled_rejection_exit"
      )
      or
      exists(MethodCall call, Parameter parameter |
        rootCallBinding(allocation, call, parameter, depth) and parameter.getCallable() = callable and
        site = callable.getBody() and relatedSite = callable.getBody() and
        programPoint = parameterPointIdentity(parameter) and relatedPoint = targetEvent + "#cfg_entry" and
        normalPath = true and exceptionalPath = false and evidence = "codeql_parameter_cfg_entry"
      )
    )
  )
}

predicate resourceLifecycleRow(
  Expr allocation, ExprParent site, Callable owner, string factKind,
  boolean requiresClose, string holderKind, string holderScope, string holderKey,
  string targetEvent, string capacityValue, string coreWorkersValue, string maxWorkersValue,
  string rejectionPolicyValue, boolean normalPath, boolean exceptionalPath,
  string evidence, string coverageStatus, string coverageNote,
  string programPoint, string relatedPoint, string relatedFile, int relatedStartLine,
  int relatedStartColumn, int relationDepth, int bindingIndex
) {
  exists(Expr expressionSite |
    site = expressionSite and
    lifecycleFact(
      allocation, expressionSite, owner, factKind, requiresClose, holderKind,
      holderScope, holderKey, targetEvent, capacityValue, normalPath, exceptionalPath,
      evidence, coverageStatus, coverageNote
    ) and
    programPoint = programPointIdentity(expressionSite) and relatedPoint = "none" and
    relatedFile = expressionSite.getLocation().getFile().getRelativePath() and
    relatedStartLine = expressionSite.getLocation().getStartLine() and
    relatedStartColumn = expressionSite.getLocation().getStartColumn() and
    relationDepth = 0 and bindingIndex = -1 and maxWorkersValue = "unknown" and
    coreWorkersValue = "unknown" and rejectionPolicyValue = "unknown"
  )
  or
  exists(Parameter relatedParameter |
    lifecycleRelationFact(
      allocation, site, owner, factKind, requiresClose, holderKind, holderScope, holderKey,
      targetEvent, capacityValue, coreWorkersValue, maxWorkersValue, rejectionPolicyValue, normalPath,
      exceptionalPath, evidence, coverageStatus, coverageNote, programPoint, relatedPoint,
      relatedParameter, relationDepth, bindingIndex
    ) and
    (
      factKind != "cfg_edge" and
      relatedFile = relatedParameter.getLocation().getFile().getRelativePath() and
      relatedStartLine = relatedParameter.getLocation().getStartLine() and
      relatedStartColumn = relatedParameter.getLocation().getStartColumn()
      or
      factKind = "cfg_edge" and exists(ExprParent target |
        enclosingCallable(target) = relatedParameter.getCallable() and
        programPointIdentity(target) = relatedPoint and
        relatedFile = target.getLocation().getFile().getRelativePath() and
        relatedStartLine = target.getLocation().getStartLine() and
        relatedStartColumn = target.getLocation().getStartColumn()
      )
    )
  )
  or
  exists(ExprParent target |
    callableCfgFact(allocation, site, target, owner, programPoint, relatedPoint,
      targetEvent, relationDepth, normalPath, exceptionalPath, evidence) and
    allocationCloseFlag(allocation, requiresClose) and factKind = "cfg_edge" and
    holderKind = "none" and holderScope = "none" and holderKey = "none" and
    capacityValue = "unknown" and coreWorkersValue = "unknown" and maxWorkersValue = "unknown" and
    rejectionPolicyValue = "unknown" and bindingIndex = -1 and
    coverageStatus = "complete" and coverageNote = evidence and
    relatedFile = target.getLocation().getFile().getRelativePath() and
    relatedStartLine = target.getLocation().getStartLine() and
    relatedStartColumn = target.getLocation().getStartColumn()
  )
}

from Expr allocation, ExprParent site, Callable owner, string factKind, boolean requiresClose,
  string holderKind, string holderScope, string holderKey, string targetEvent,
  string capacityValue, string coreWorkersValue, string maxWorkersValue, string rejectionPolicyValue,
  boolean normalPath, boolean exceptionalPath, string evidence,
  string coverageStatus, string coverageNote, string programPoint, string relatedPoint,
  string relatedFile, int relatedStartLine, int relatedStartColumn,
  int relationDepth, int bindingIndex
where resourceLifecycleRow(
  allocation, site, owner, factKind, requiresClose, holderKind, holderScope, holderKey,
  targetEvent, capacityValue, coreWorkersValue, maxWorkersValue, rejectionPolicyValue, normalPath,
  exceptionalPath, evidence, coverageStatus, coverageNote, programPoint, relatedPoint,
  relatedFile, relatedStartLine, relatedStartColumn, relationDepth, bindingIndex
)
select
  canonicalCallableIdentity(owner) as unit_id,
  canonicalCallableIdentity(enclosingCallable(site)) as site_callable,
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  site.getLocation().getStartColumn() as site_start_column,
  programPoint as program_point,
  relatedPoint as related_point,
  relatedFile as related_file,
  relatedStartLine as related_start_line,
  relatedStartColumn as related_start_column,
  relationDepth as relation_depth,
  bindingIndex as binding_index,
  factKind as fact_kind,
  allocationInstanceKey(allocation) as instance_key,
  allocation.getType().toString() as resource_type,
  requiresClose as requires_close,
  holderKind as holder_kind,
  holderScope as holder_scope,
  holderKey as holder_key,
  targetEvent as target_event,
  capacityValue as capacity,
  coreWorkersValue as core_workers,
  maxWorkersValue as max_workers,
  rejectionPolicyValue as rejection_policy,
  normalPath as normal_path,
  exceptionalPath as exceptional_path,
  evidence as source_evidence,
  coverageStatus as coverage_status,
  coverageNote as coverage_note
