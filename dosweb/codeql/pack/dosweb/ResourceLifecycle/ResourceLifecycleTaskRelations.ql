/**
 * @name Resource lifecycle task relations
 * @description Raw task capture, executor contract, task CFG, and task exit facts.
 * @kind table
 * @id dosweb/resource-lifecycle-task-relations
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
  exists(MethodCall firstCall, Parameter firstParameter, VarAccess parameterAccess |
    depth = 2 and exactArgumentBinding(allocation, firstCall, firstParameter) and
    firstCall.getEnclosingCallable() = allocation.getEnclosingCallable() and
    firstCall.getMethod() != firstCall.getEnclosingCallable() and
    parameterAccess.getVariable() = firstParameter and
    parameterAccess.getEnclosingCallable() = firstParameter.getCallable() and
    exactArgumentBinding(parameterAccess, call, parameter) and
    call.getEnclosingCallable() = firstParameter.getCallable() and
    call.getMethod() != call.getEnclosingCallable() and
    call.getMethod() != firstCall.getEnclosingCallable()
  )
}

predicate rootBoundParameter(Expr allocation, Parameter parameter, int depth) {
  exists(MethodCall call | rootCallBinding(allocation, call, parameter, depth))
}

Field executorReceiver(MethodCall call) {
  exists(VarAccess receiver |
    receiver = call.getQualifier() and result = receiver.getVariable().(Field)
  )
  or
  exists(FieldAccess receiver |
    receiver = call.getQualifier() and result = receiver.getField()
  )
}

predicate exactThreadPoolSubmission(MethodCall submit, Field executor) {
  executor = executorReceiver(submit) and executor.isFinal() and executor.isStatic() and
  submit.getMethod().hasQualifiedName(
    "java.util.concurrent", "ThreadPoolExecutor", "execute"
  ) and
  submit.getNumArgument() = 1
}

ClassInstanceExpr threadPoolConstruction(Field executor) {
  result = executor.getInitializer() and
  result.getConstructedType().getErasure().(RefType).hasQualifiedName(
    "java.util.concurrent", "ThreadPoolExecutor"
  ) and
  result.getNumArgument() = 6
}

string threadPoolCapacity(Field executor) {
  exists(ClassInstanceExpr pool, ClassInstanceExpr queue, CompileTimeConstantExpr capacity |
    pool = threadPoolConstruction(executor) and queue = pool.getArgument(4) and
    queue.getConstructedType().getErasure().(RefType).hasQualifiedName(
      "java.util.concurrent", "ArrayBlockingQueue"
    ) and
    capacity = queue.getArgument(0) and result = capacity.toString()
  )
}

string threadPoolMaxWorkers(Field executor) {
  exists(ClassInstanceExpr pool, CompileTimeConstantExpr workers |
    pool = threadPoolConstruction(executor) and workers = pool.getArgument(1) and
    result = workers.toString()
  )
}

string threadPoolRejectionPolicy(Field executor) {
  exists(ClassInstanceExpr pool, ClassInstanceExpr policy |
    pool = threadPoolConstruction(executor) and policy = pool.getArgument(5) and
    (
      policy.getConstructedType().hasQualifiedName(
        "java.util.concurrent", "ThreadPoolExecutor$AbortPolicy"
      ) and result = "abort"
      or
      policy.getConstructedType().hasQualifiedName(
        "java.util.concurrent", "ThreadPoolExecutor$CallerRunsPolicy"
      ) and result = "caller_runs"
      or
      policy.getConstructedType().hasQualifiedName(
        "java.util.concurrent", "ThreadPoolExecutor$DiscardPolicy"
      ) and result = "discard"
      or
      policy.getConstructedType().hasQualifiedName(
        "java.util.concurrent", "ThreadPoolExecutor$DiscardOldestPolicy"
      ) and result = "discard_oldest"
    )
  )
}

string exactExecutorIdentity(MethodCall submit, Field executor) {
  exactThreadPoolSubmission(submit, executor) and
  result = executor.getDeclaringType().getQualifiedName() + "." + executor.getName() +
    "#static"
}

predicate lambdaCapturesParameter(LambdaExpr lambda, Parameter parameter) {
  parameter.getCallable() != lambda.asMethod() and
  exists(VarAccess access |
    access.getVariable() = parameter and access.getEnclosingCallable() = lambda.asMethod()
  )
}

predicate capturedTaskCandidate(
  Expr allocation, MethodCall submit, Field executor, LambdaExpr lambda,
  Parameter captured, int depth
) {
  rootBoundParameter(allocation, captured, depth) and
  lambdaCapturesParameter(lambda, captured) and
  executor = executorReceiver(submit) and
  submit.getMethod().hasQualifiedName(
    "java.util.concurrent", "ThreadPoolExecutor", "execute"
  ) and submit.getNumArgument() = 1 and
  allocation.getEnclosingCallable() != lambda.asMethod() and
  allocationFlowsTo(lambda, submit.getArgument(0)) and
  submit.getEnclosingCallable() = captured.getCallable()
}

predicate exactCapturedTask(
  Expr allocation, MethodCall submit, Field executor, LambdaExpr lambda,
  Parameter captured, int depth
) {
  capturedTaskCandidate(allocation, submit, executor, lambda, captured, depth) and
  exactThreadPoolSubmission(submit, executor) and
  exists(threadPoolCapacity(executor)) and
  exists(threadPoolMaxWorkers(executor)) and
  exists(threadPoolRejectionPolicy(executor))
}

Stmt taskEntry(LambdaExpr lambda) {
  lambda.hasStmtBody() and result = lambda.getStmtBody().getStmt(0)
}

predicate taskTerminal(LambdaExpr lambda, Stmt terminal, string kind) {
  terminal.getEnclosingCallable() = lambda.asMethod() and
  (
    terminal instanceof ReturnStmt and kind = "normal"
    or
    terminal instanceof ThrowStmt and kind = "exceptional"
  )
}

predicate relevantTaskPoint(LambdaExpr lambda, ExprParent point) {
  point = taskEntry(lambda)
  or
  exists(Stmt terminal, string kind |
    taskTerminal(lambda, terminal, kind) and point = terminal
  )
  or
  exists(MethodCall call |
    call.getEnclosingCallable() = lambda.asMethod() and point = call
  )
}

predicate taskCfgEdge(LambdaExpr lambda, ExprParent source, ExprParent target) {
  relevantTaskPoint(lambda, source) and relevantTaskPoint(lambda, target) and
  source != target and
  controlFlowNode(target) = controlFlowNode(source).getASuccessor+()
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

predicate allocationCloseFlag(Expr allocation, boolean requiresClose) {
  allocationRequiresClose(allocation) and requiresClose = true
  or
  not allocationRequiresClose(allocation) and requiresClose = false
}

predicate lifecycleTaskRelationFact(
  Expr allocation, ExprParent site, Callable owner, string factKind,
  boolean requiresClose, string holderKind, string holderScope, string holderKey,
  string targetEvent, string capacityValue, string maxWorkersValue,
  string rejectionPolicyValue, boolean normalPath, boolean exceptionalPath,
  string evidence, string coverageStatus, string coverageNote,
  string programPoint, string relatedPoint, int relationDepth, int bindingIndex
) {
  trackedAllocation(allocation) and owner = allocation.getEnclosingCallable() and
  owner.fromSource() and allocationCloseFlag(allocation, requiresClose) and
  (
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      site = submit and factKind = "dispatch" and holderKind = "queue" and
      holderScope = "task" and holderKey = exactExecutorIdentity(submit, executor) and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = threadPoolCapacity(executor) and
      maxWorkersValue = threadPoolMaxWorkers(executor) and
      rejectionPolicyValue = threadPoolRejectionPolicy(executor) and
      normalPath = true and exceptionalPath = true and
      evidence = "codeql_lambda_capture_to_executor" and coverageStatus = "complete" and
      coverageNote = "exact_static_thread_pool_executor_capture" and
      programPoint = programPointIdentity(submit) and
      relatedPoint = programPointIdentity(taskEntry(lambda)) and relationDepth = depth and
      bindingIndex = 0
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      site = submit and factKind = "invariant" and holderKind = "queue" and
      holderScope = "task" and holderKey = exactExecutorIdentity(submit, executor) and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = threadPoolCapacity(executor) and
      maxWorkersValue = threadPoolMaxWorkers(executor) and
      rejectionPolicyValue = threadPoolRejectionPolicy(executor) and
      normalPath = true and exceptionalPath = true and
      evidence = "codeql_thread_pool_executor_contract" and coverageStatus = "complete" and
      coverageNote = "exact_array_blocking_queue_capacity" and
      programPoint = programPointIdentity(submit) and
      relatedPoint = programPointIdentity(taskEntry(lambda)) and relationDepth = depth and
      bindingIndex = 0
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth,
      ExprParent source, ExprParent target
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      taskCfgEdge(lambda, source, target) and site = source and factKind = "cfg_edge" and
      holderKind = "none" and holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = true and
      evidence = "codeql_task_cfg_successor" and coverageStatus = "complete" and
      coverageNote = "reachable_task_cfg_edge" and
      programPoint = programPointIdentity(source) and
      relatedPoint = programPointIdentity(target) and relationDepth = depth and
      bindingIndex = -1
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth,
      Stmt terminal, string terminalKind
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      taskTerminal(lambda, terminal, terminalKind) and site = terminal and
      factKind = "task_exit" and holderKind = "none" and holderScope = "none" and
      holderKey = "none" and targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and
      (
        terminalKind = "normal" and normalPath = true and exceptionalPath = false
        or
        terminalKind = "exceptional" and normalPath = false and exceptionalPath = true
      ) and
      evidence = "codeql_explicit_task_terminal" and coverageStatus = "complete" and
      coverageNote = terminalKind + "_task_terminal" and
      programPoint = programPointIdentity(terminal) and
      relatedPoint = programPointIdentity(taskEntry(lambda)) and relationDepth = depth and
      bindingIndex = -1
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      (
        not exists(Stmt normal | taskTerminal(lambda, normal, "normal"))
        or
        not exists(Stmt exceptional | taskTerminal(lambda, exceptional, "exceptional"))
      ) and
      site = submit and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = true and
      evidence = "codeql_task_terminal_coverage_gap" and coverageStatus = "partial" and
      coverageNote = "task_terminal_coverage_incomplete" and
      programPoint = programPointIdentity(submit) and
      relatedPoint = programPointIdentity(taskEntry(lambda)) and relationDepth = depth and
      bindingIndex = 0
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth
    |
      capturedTaskCandidate(allocation, submit, executor, lambda, captured, depth) and
      not exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      site = submit and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = true and
      evidence = "codeql_executor_contract_coverage_gap" and coverageStatus = "partial" and
      (
        not executor.isStatic() and coverageNote = "executor_receiver_identity_unresolved"
        or
        executor.isStatic() and coverageNote = "executor_contract_unresolved"
      ) and
      programPoint = programPointIdentity(submit) and
      relatedPoint = programPointIdentity(lambda) and relationDepth = depth and
      bindingIndex = 0
    )
  )
}

predicate resourceLifecycleRow(
  Expr allocation, ExprParent site, Callable owner, string factKind,
  boolean requiresClose, string holderKind, string holderScope, string holderKey,
  string targetEvent, string capacityValue, string maxWorkersValue,
  string rejectionPolicyValue, boolean normalPath, boolean exceptionalPath,
  string evidence, string coverageStatus, string coverageNote,
  string programPoint, string relatedPoint, int relationDepth, int bindingIndex
) {
  lifecycleTaskRelationFact(
    allocation, site, owner, factKind, requiresClose, holderKind, holderScope, holderKey,
    targetEvent, capacityValue, maxWorkersValue, rejectionPolicyValue, normalPath,
    exceptionalPath, evidence, coverageStatus, coverageNote, programPoint, relatedPoint,
    relationDepth, bindingIndex
  )
}

from Expr allocation, ExprParent site, Callable owner, string factKind, boolean requiresClose,
  string holderKind, string holderScope, string holderKey, string targetEvent,
  string capacityValue, string maxWorkersValue, string rejectionPolicyValue,
  boolean normalPath, boolean exceptionalPath, string evidence,
  string coverageStatus, string coverageNote, string programPoint, string relatedPoint,
  int relationDepth, int bindingIndex
where resourceLifecycleRow(
  allocation, site, owner, factKind, requiresClose, holderKind, holderScope, holderKey,
  targetEvent, capacityValue, maxWorkersValue, rejectionPolicyValue, normalPath,
  exceptionalPath, evidence, coverageStatus, coverageNote, programPoint, relatedPoint,
  relationDepth, bindingIndex
)
select
  canonicalCallableIdentity(owner) as unit_id,
  canonicalCallableIdentity(enclosingCallable(site)) as site_callable,
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  site.getLocation().getStartColumn() as site_start_column,
  programPoint as program_point,
  relatedPoint as related_point,
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
  maxWorkersValue as max_workers,
  rejectionPolicyValue as rejection_policy,
  normalPath as normal_path,
  exceptionalPath as exceptional_path,
  evidence as source_evidence,
  coverageStatus as coverage_status,
  coverageNote as coverage_note
