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

/** One task AST-level CFG step; synthetic CFG nodes may be traversed, AST nodes may not. */
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

/**
 * `first` has already been selected as a typed CFG successor. It may itself
 * be the AST target; otherwise only non-AST nodes may be bridged. This avoids
 * both dropping direct normal/exception edges and skipping an intervening AST
 * program point.
 */
predicate initialSuccessorAfterNonAstNodes(ControlFlowNode first, ControlFlowNode target) {
  first = target and isAstControlFlowNode(target)
  or
  not isAstControlFlowNode(first) and successorAfterNonAstNodes(first, target)
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
  exists(ClassInstanceExpr pool, ClassInstanceExpr queue, CompileTimeConstantExpr capacity, int value |
    pool = threadPoolConstruction(executor) and queue = pool.getArgument(4) and
    queue.getConstructedType().getErasure().(RefType).hasQualifiedName(
      "java.util.concurrent", "ArrayBlockingQueue"
    ) and
    capacity = queue.getArgument(0) and value = capacity.getIntValue() and
    result = value.toString()
  )
}

string threadPoolMaxWorkers(Field executor) {
  exists(ClassInstanceExpr pool, CompileTimeConstantExpr workers, int value |
    pool = threadPoolConstruction(executor) and workers = pool.getArgument(1) and
    value = workers.getIntValue() and result = value.toString()
  )
}

string threadPoolCoreWorkers(Field executor) {
  exists(ClassInstanceExpr pool, CompileTimeConstantExpr workers, int value |
    pool = threadPoolConstruction(executor) and workers = pool.getArgument(0) and
    value = workers.getIntValue() and result = value.toString()
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

predicate supportedThreadPoolRejectionPolicy(Field executor) {
  threadPoolRejectionPolicy(executor) = "abort"
}

/**
 * A static-final field freezes the reference, not the ThreadPoolExecutor's
 * mutable scheduling configuration. Only model the constructor contract when
 * every later configuration write and externally-visible alias is absent.
 */
predicate executorReference(Expr reference, Field executor) {
  reference instanceof VarAccess and reference.(VarAccess).getVariable() = executor
  or
  reference instanceof FieldAccess and reference.(FieldAccess).getField() = executor
  or
  exists(VarAccess fieldRead |
    fieldRead.getVariable() = executor and allocationFlowsTo(fieldRead, reference)
  )
}

predicate threadPoolConfigurationMutator(MethodCall call) {
  call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName(
    "java.util.concurrent", "ThreadPoolExecutor"
  ) and
  call.getMethod().getName() = [
    "setCorePoolSize", "setMaximumPoolSize", "setRejectedExecutionHandler",
    "setKeepAliveTime", "allowCoreThreadTimeOut", "setThreadFactory"
  ]
}

predicate threadPoolConfigurationMutation(Field executor) {
  exists(MethodCall mutation, Expr receiver |
    threadPoolConfigurationMutator(mutation) and receiver = mutation.getQualifier() and
    executorReference(receiver, executor)
  )
}

predicate executorEscapes(Field executor) {
  exists(MethodCall call, int position, Expr argument |
    position >= 0 and argument = call.getArgument(position) and
    executorReference(argument, executor)
  )
  or
  exists(AssignExpr assignment, Expr destination |
    executorReference(assignment.getSource(), executor) and destination = assignment.getDest() and
    destination instanceof FieldAccess
  )
  or
  exists(ReturnStmt returned, Expr value |
    value = returned.getExpr() and executorReference(value, executor)
  )
}

predicate stableThreadPoolConfiguration(Field executor) {
  not threadPoolConfigurationMutation(executor) and not executorEscapes(executor)
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
  lambda.hasStmtBody() and
  exactThreadPoolSubmission(submit, executor) and
  stableThreadPoolConfiguration(executor) and
  exists(threadPoolCapacity(executor)) and
  exists(threadPoolCoreWorkers(executor)) and
  exists(threadPoolMaxWorkers(executor)) and
  supportedThreadPoolRejectionPolicy(executor)
}

predicate rootTaskSubmission(
  Expr allocation, MethodCall submit, Parameter captured, int depth
) {
  rootBoundParameter(allocation, captured, depth) and
  submit.getEnclosingCallable() = captured.getCallable() and
  submit.getNumArgument() = 1 and
  submit.getMethod().getName() = ["execute", "submit"] and
  submit.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName(
    "java.util.concurrent", "Executor"
  )
}

predicate lambdaTaskArgument(
  MethodCall submit, LambdaExpr lambda, Parameter captured
) {
  lambdaCapturesParameter(lambda, captured) and
  allocationFlowsTo(lambda, submit.getArgument(0))
}

predicate unsupportedTaskForm(
  Expr allocation, MethodCall submit, Parameter captured, int depth,
  string coverageNote
) {
  rootTaskSubmission(allocation, submit, captured, depth) and
  (
    submit.getMethod().getName() = "submit" and
    exists(LambdaExpr lambda |
      lambdaTaskArgument(submit, lambda, captured)
    ) and
    coverageNote = "unsupported_submit_callable"
    or
    submit.getMethod().hasQualifiedName(
      "java.util.concurrent", "ThreadPoolExecutor", "execute"
    ) and
    exists(ClassInstanceExpr task, Class anonymous, VarAccess access |
      task = submit.getArgument(0) and anonymous = task.getAnonymousClass() and
      not exists(LambdaExpr lambda | lambda = submit.getArgument(0)) and
      not exists(MemberRefExpr reference | reference = submit.getArgument(0)) and
      access.getVariable() = captured and
      access.getEnclosingCallable().getDeclaringType() = anonymous
    ) and
    coverageNote = "unsupported_anonymous_runnable"
    or
    submit.getMethod().hasQualifiedName(
      "java.util.concurrent", "ThreadPoolExecutor", "execute"
    ) and
    exists(MemberRefExpr reference, VarAccess receiver |
      reference = submit.getArgument(0) and receiver = reference.getReceiverExpr() and
      receiver.getVariable() = captured
    ) and
    coverageNote = "unsupported_method_reference"
    or
    submit.getMethod().hasQualifiedName(
      "java.util.concurrent", "ThreadPoolExecutor", "execute"
    ) and
    exists(VarAccess receiver, LocalVariableDecl executorAlias, LambdaExpr lambda |
      receiver = submit.getQualifier() and receiver.getVariable() = executorAlias and
      lambdaTaskArgument(submit, lambda, captured)
    ) and
    coverageNote = "executor_receiver_identity_unresolved"
    or
    submit.getMethod().hasQualifiedName(
      "java.util.concurrent", "ThreadPoolExecutor", "execute"
    ) and
    exists(
      LambdaExpr lambda, LocalVariableDecl localCapture, VarAccess initializer,
      VarAccess access
    |
      allocationFlowsTo(lambda, submit.getArgument(0)) and
      not lambdaCapturesParameter(lambda, captured) and
      initializer = localCapture.getInitializer() and
      initializer.getVariable() = captured and
      access.getVariable() = localCapture and
      access.getEnclosingCallable() = lambda.asMethod()
    ) and
    coverageNote = "unsupported_local_capture"
  )
}

Stmt taskEntry(LambdaExpr lambda) {
  lambda.hasStmtBody() and result = lambda.getStmtBody().getStmt(0)
}

predicate relevantTaskPoint(LambdaExpr lambda, ExprParent point) {
  enclosingCallable(point) = lambda.asMethod() and
  (
    point instanceof Expr
    or
    point instanceof Stmt
  )
}

predicate taskCfgEdge(LambdaExpr lambda, ExprParent source, ExprParent target) {
  relevantTaskPoint(lambda, source) and relevantTaskPoint(lambda, target) and
  source != target and
  successorAfterNonAstNodes(controlFlowNode(source), controlFlowNode(target))
}

/** A task CFG edge whose first step is a successful completion of `source`. */
predicate taskCfgNormalEdge(LambdaExpr lambda, ExprParent source, ExprParent target) {
  relevantTaskPoint(lambda, source) and relevantTaskPoint(lambda, target) and
  source != target and
  initialSuccessorAfterNonAstNodes(
    controlFlowNode(source).getANormalSuccessor(), controlFlowNode(target)
  )
}

/** A task CFG edge whose first step is a call exception from `source`. */
predicate taskCfgExceptionalEdge(LambdaExpr lambda, ExprParent source, ExprParent target) {
  relevantTaskPoint(lambda, source) and relevantTaskPoint(lambda, target) and
  source != target and
  initialSuccessorAfterNonAstNodes(
    controlFlowNode(source).getAnExceptionSuccessor(), controlFlowNode(target)
  )
}

/**
 * The site is the real AST predecessor of the CFG annotated exit. This is the
 * post-finally point for abrupt returns/throws routed through a finally block;
 * the annotated node itself has no source location that the raw schema can emit.
 */
predicate taskAnnotatedExitSource(
  LambdaExpr lambda, ExprParent source, ControlFlow::AnnotatedExitNode exit
) {
  relevantTaskPoint(lambda, source) and exit.getEnclosingCallable() = lambda.asMethod() and
  successorAfterNonAstNodes(controlFlowNode(source), exit)
}

predicate taskExitSource(
  LambdaExpr lambda, ExprParent source, ControlFlow::AnnotatedExitNode exit, string kind
) {
  taskAnnotatedExitSource(lambda, source, exit) and
  (
    exit instanceof ControlFlow::NormalExitNode and kind = "normal"
    or
    exit instanceof ControlFlow::ExceptionalExitNode and kind = "exceptional"
  )
}

/**
 * The CFG exits must all have source-backed task facts. The Java CFG only
 * models selected unchecked call exceptions; absence of a typed exception
 * successor is not proof that a callback call cannot exit exceptionally.
 */
predicate taskExitCoverageGap(LambdaExpr lambda) {
  exists(ControlFlow::AnnotatedExitNode exit |
    exit.getEnclosingCallable() = lambda.asMethod() and
    not exists(ExprParent source | taskAnnotatedExitSource(lambda, source, exit))
  )
  or
  exists(MethodCall call |
    call.getEnclosingCallable() = lambda.asMethod() and
    exists(call.getControlFlowNode()) and
    not exists(call.getControlFlowNode().getAnExceptionSuccessor())
  )
}

predicate autoCloseableReleaseMethod(Method method) {
  method.getName() = "close" and method.getNumberOfParameters() = 0 and
  exists(Method contract |
    contract.getDeclaringType().hasQualifiedName("java.lang", "AutoCloseable") and
    contract.getName() = "close" and contract.getNumberOfParameters() = 0 and
    (method = contract or method.getAnOverride() = contract)
  )
}

/** A captured resource has one direct close statement in the task's finally block. */
predicate exactCapturedFinallyClose(
  LambdaExpr lambda, Parameter captured, MethodCall release
) {
  release.getEnclosingCallable() = lambda.asMethod() and
  release.getNumArgument() = 0 and autoCloseableReleaseMethod(release.getMethod()) and
  exists(VarAccess receiver |
    receiver = release.getQualifier() and receiver.getVariable() = captured
  ) and
  exists(TryStmt attempt, BlockStmt cleanup |
    cleanup = attempt.getFinally() and cleanup.getNumStmt() = 1 and
    cleanup.getStmt(0) = release.getEnclosingStmt() and
    attempt.getEnclosingCallable() = lambda.asMethod()
  )
}

/**
 * A close only releases after its normal CFG successor. An exception from the
 * close is deliberately not treated as a release and reaches a task exit (or a
 * coverage gap) independently.
 */
predicate exactCapturedFinallyCloseSuccess(
  LambdaExpr lambda, Parameter captured, MethodCall release, ExprParent target
) {
  exactCapturedFinallyClose(lambda, captured, release) and
  not (
    target instanceof Expr and target.(Expr).getParent*() = release
  ) and
  taskCfgNormalEdge(lambda, release, target)
}

/**
 * Successful close completion may resume a pending normal or exceptional task
 * exit without another AST point. Its distinct continuation point makes the
 * successful release edge independent of an exception thrown by close itself.
 */
predicate exactCapturedFinallyCloseTerminalSuccess(
  LambdaExpr lambda, Parameter captured, MethodCall release
) {
  exactCapturedFinallyClose(lambda, captured, release) and
  exists(ControlFlow::AnnotatedExitNode exit |
    closeNormalSuccessAnnotatedExit(lambda, release, exit)
  )
}

/** A close's typed normal successor reaches an annotated task exit without another AST point. */
predicate closeNormalSuccessAnnotatedExit(
  LambdaExpr lambda, MethodCall release, ControlFlow::AnnotatedExitNode exit
) {
  exit.getEnclosingCallable() = lambda.asMethod() and
  initialSuccessorAfterNonAstNodes(controlFlowNode(release).getANormalSuccessor(), exit)
}

/** A close exception reaches the task exit independently of the successful-close continuation. */
predicate closeExceptionalSuccessAnnotatedExit(
  LambdaExpr lambda, MethodCall release, ControlFlow::AnnotatedExitNode exit
) {
  exit.getEnclosingCallable() = lambda.asMethod() and
  initialSuccessorAfterNonAstNodes(controlFlowNode(release).getAnExceptionSuccessor(), exit)
}

/** Synthetic but source-backed continuation after the `close` call returned normally. */
string closeNormalSuccessProgramPointIdentity(MethodCall release) {
  result = programPointIdentity(release) + "#normal-success:call-cfg-v1"
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
  string targetEvent, string capacityValue, string coreWorkersValue, string maxWorkersValue,
  string rejectionPolicyValue, boolean normalPath, boolean exceptionalPath,
  string evidence, string coverageStatus, string coverageNote,
  string programPoint, string relatedPoint, ExprParent relatedSite,
  int relationDepth, int bindingIndex
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
      coreWorkersValue = threadPoolCoreWorkers(executor) and
      maxWorkersValue = threadPoolMaxWorkers(executor) and
      rejectionPolicyValue = threadPoolRejectionPolicy(executor) and
      normalPath = true and exceptionalPath = true and
      evidence = "codeql_lambda_capture_to_executor" and coverageStatus = "complete" and
      coverageNote = "exact_static_thread_pool_executor_capture" and
      programPoint = programPointIdentity(submit) and
      relatedSite = taskEntry(lambda) and relatedPoint = programPointIdentity(relatedSite) and
      relationDepth = depth and
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
      coreWorkersValue = threadPoolCoreWorkers(executor) and
      maxWorkersValue = threadPoolMaxWorkers(executor) and
      rejectionPolicyValue = threadPoolRejectionPolicy(executor) and
      normalPath = true and exceptionalPath = true and
      evidence = "codeql_thread_pool_executor_contract" and coverageStatus = "complete" and
      coverageNote = "exact_array_blocking_queue_capacity" and
      programPoint = programPointIdentity(submit) and
      relatedSite = taskEntry(lambda) and relatedPoint = programPointIdentity(relatedSite) and
      relationDepth = depth and
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
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and
      (
        taskCfgNormalEdge(lambda, source, target) and
        normalPath = true and exceptionalPath = false
        or
        taskCfgExceptionalEdge(lambda, source, target) and
        normalPath = false and exceptionalPath = true
        or
        not taskCfgNormalEdge(lambda, source, target) and
        not taskCfgExceptionalEdge(lambda, source, target) and
        normalPath = true and exceptionalPath = true
      ) and
      evidence = "codeql_task_cfg_successor" and coverageStatus = "complete" and
      coverageNote = "reachable_task_cfg_edge" and
      programPoint = programPointIdentity(source) and
      relatedSite = target and relatedPoint = programPointIdentity(relatedSite) and
      relationDepth = depth and
      bindingIndex = -1
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth,
      MethodCall release, ControlFlow::AnnotatedExitNode exit
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      exactCapturedFinallyClose(lambda, captured, release) and
      closeNormalSuccessAnnotatedExit(lambda, release, exit) and
      site = release and factKind = "cfg_edge" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and rejectionPolicyValue = "unknown" and
      normalPath = true and exceptionalPath = false and
      evidence = "codeql_task_close_normal_successor" and coverageStatus = "complete" and
      coverageNote = "exact_close_normal_success_continuation" and
      programPoint = programPointIdentity(release) and
      relatedSite = release and relatedPoint = closeNormalSuccessProgramPointIdentity(release) and
      relationDepth = depth and bindingIndex = -1
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth,
      MethodCall release, ExprParent successor
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      (
        exactCapturedFinallyCloseSuccess(lambda, captured, release, successor) and
        relatedSite = successor and relatedPoint = programPointIdentity(relatedSite)
        or
        exactCapturedFinallyCloseTerminalSuccess(lambda, captured, release) and successor = release and
        relatedSite = release and relatedPoint = closeNormalSuccessProgramPointIdentity(release)
      ) and
      site = release and factKind = "release" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and rejectionPolicyValue = "unknown" and
      normalPath = true and exceptionalPath = false and
      evidence = "codeql_task_callback_close_finally" and coverageStatus = "complete" and
      coverageNote = "exact_captured_task_finally_close" and
      programPoint = programPointIdentity(release) and
      relationDepth = depth and bindingIndex = -1
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth,
      MethodCall release
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      exactCapturedFinallyClose(lambda, captured, release) and
      not exists(ExprParent successor |
        exactCapturedFinallyCloseSuccess(lambda, captured, release, successor)
      ) and
      not exactCapturedFinallyCloseTerminalSuccess(lambda, captured, release) and
      site = release and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and rejectionPolicyValue = "unknown" and
      normalPath = true and exceptionalPath = true and
      evidence = "codeql_task_callback_close_coverage_gap" and coverageStatus = "partial" and
      coverageNote = "task_finally_close_normal_successor_unresolved" and
      programPoint = programPointIdentity(release) and
      relatedSite = release and relatedPoint = programPointIdentity(relatedSite) and
      relationDepth = depth and bindingIndex = -1
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth,
      ExprParent source, ControlFlow::AnnotatedExitNode exit, string terminalKind
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      taskExitSource(lambda, source, exit, terminalKind) and site = source and
      factKind = "task_exit" and holderKind = "none" and holderScope = "none" and
      holderKey = "none" and targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and
      (
        terminalKind = "normal" and normalPath = true and exceptionalPath = false
        or
        terminalKind = "exceptional" and normalPath = false and exceptionalPath = true
      ) and
      evidence = "codeql_task_annotated_cfg_exit" and coverageStatus = "complete" and
      coverageNote = terminalKind + "_task_annotated_cfg_exit" and
      (
        exists(MethodCall release |
          source = release and exactCapturedFinallyClose(lambda, captured, release) and
          closeNormalSuccessAnnotatedExit(lambda, release, exit) and
          programPoint = closeNormalSuccessProgramPointIdentity(release)
        )
        or
        exists(MethodCall release |
          source = release and exactCapturedFinallyClose(lambda, captured, release) and
          closeExceptionalSuccessAnnotatedExit(lambda, release, exit) and
          programPoint = programPointIdentity(release)
        )
        or
        not exists(MethodCall release |
          source = release and exactCapturedFinallyClose(lambda, captured, release) and
          (
            closeNormalSuccessAnnotatedExit(lambda, release, exit) or
            closeExceptionalSuccessAnnotatedExit(lambda, release, exit)
          )
        ) and
        programPoint = programPointIdentity(source)
      ) and
      relatedSite = taskEntry(lambda) and relatedPoint = programPointIdentity(relatedSite) and
      relationDepth = depth and
      bindingIndex = -1
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      not exists(MethodCall release | exactCapturedFinallyClose(lambda, captured, release)) and
      site = submit and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and rejectionPolicyValue = "unknown" and
      normalPath = true and exceptionalPath = true and
      evidence = "codeql_task_callback_effect_coverage_gap" and coverageStatus = "partial" and
      coverageNote = "task_callback_effect_unmodeled" and
      programPoint = programPointIdentity(submit) and
      relatedSite = lambda and relatedPoint = programPointIdentity(relatedSite) and
      relationDepth = depth and bindingIndex = 0
    )
    or
    exists(
      MethodCall submit, Field executor, LambdaExpr lambda, Parameter captured, int depth
    |
      exactCapturedTask(allocation, submit, executor, lambda, captured, depth) and
      taskExitCoverageGap(lambda) and
      site = submit and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(lambda.asMethod()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = true and
      evidence = "codeql_task_terminal_coverage_gap" and coverageStatus = "partial" and
      coverageNote = "task_terminal_coverage_incomplete" and
      programPoint = programPointIdentity(submit) and
      relatedSite = taskEntry(lambda) and relatedPoint = programPointIdentity(relatedSite) and
      relationDepth = depth and
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
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and
      rejectionPolicyValue = "unknown" and normalPath = true and exceptionalPath = true and
      (
        not lambda.hasStmtBody() and
        evidence = "codeql_unsupported_task_form" and coverageStatus = "unsupported" and
        coverageNote = "unsupported_expression_body_lambda_caller_bound"
        or
        lambda.hasStmtBody() and not executor.isStatic() and
        evidence = "codeql_executor_contract_coverage_gap" and coverageStatus = "partial" and
        coverageNote = "executor_receiver_identity_unresolved"
        or
        lambda.hasStmtBody() and executor.isStatic() and
        exists(string policy |
          threadPoolRejectionPolicy(executor) = policy and policy != "abort" and
          evidence = "codeql_unsupported_executor_rejection_policy" and
          coverageStatus = "unsupported" and
          coverageNote = "unsupported_rejection_policy_" + policy
        )
        or
        lambda.hasStmtBody() and executor.isStatic() and
        not stableThreadPoolConfiguration(executor) and
        evidence = "codeql_executor_configuration_coverage_gap" and coverageStatus = "partial" and
        coverageNote = "executor_configuration_mutable_or_escaped"
        or
        lambda.hasStmtBody() and executor.isStatic() and stableThreadPoolConfiguration(executor) and
        not exists(string policy |
          threadPoolRejectionPolicy(executor) = policy and policy != "abort"
        ) and
        evidence = "codeql_executor_contract_coverage_gap" and coverageStatus = "partial" and
        coverageNote = "executor_contract_unresolved"
      ) and
      programPoint = programPointIdentity(submit) and
      relatedSite = lambda and relatedPoint = programPointIdentity(relatedSite) and
      relationDepth = depth and
      bindingIndex = 0
    )
    or
    exists(MethodCall submit, Parameter captured, int depth, string unsupportedNote |
      unsupportedTaskForm(allocation, submit, captured, depth, unsupportedNote) and
      site = submit and factKind = "unknown_call" and holderKind = "none" and
      holderScope = "none" and holderKey = "none" and
      targetEvent = canonicalCallableIdentity(submit.getEnclosingCallable()) and
      capacityValue = "unknown" and coreWorkersValue = "unknown" and
      maxWorkersValue = "unknown" and rejectionPolicyValue = "unknown" and
      normalPath = true and exceptionalPath = true and
      evidence = "codeql_unsupported_task_form" and coverageStatus = "unsupported" and
      coverageNote = unsupportedNote and
      programPoint = programPointIdentity(submit) and
      relatedSite = submit.getArgument(0) and relatedPoint = programPointIdentity(relatedSite) and
      relationDepth = depth and bindingIndex = 0
    )
  )
}

predicate resourceLifecycleRow(
  Expr allocation, ExprParent site, Callable owner, string factKind,
  boolean requiresClose, string holderKind, string holderScope, string holderKey,
  string targetEvent, string capacityValue, string coreWorkersValue, string maxWorkersValue,
  string rejectionPolicyValue, boolean normalPath, boolean exceptionalPath,
  string evidence, string coverageStatus, string coverageNote,
  string programPoint, string relatedPoint, ExprParent relatedSite,
  int relationDepth, int bindingIndex
) {
  lifecycleTaskRelationFact(
    allocation, site, owner, factKind, requiresClose, holderKind, holderScope, holderKey,
    targetEvent, capacityValue, coreWorkersValue, maxWorkersValue, rejectionPolicyValue, normalPath,
    exceptionalPath, evidence, coverageStatus, coverageNote, programPoint, relatedPoint,
    relatedSite, relationDepth, bindingIndex
  )
}

from Expr allocation, ExprParent site, Callable owner, string factKind, boolean requiresClose,
  string holderKind, string holderScope, string holderKey, string targetEvent,
  string capacityValue, string coreWorkersValue, string maxWorkersValue, string rejectionPolicyValue,
  boolean normalPath, boolean exceptionalPath, string evidence,
  string coverageStatus, string coverageNote, string programPoint, string relatedPoint,
  ExprParent relatedSite, int relationDepth, int bindingIndex
where resourceLifecycleRow(
  allocation, site, owner, factKind, requiresClose, holderKind, holderScope, holderKey,
  targetEvent, capacityValue, coreWorkersValue, maxWorkersValue, rejectionPolicyValue, normalPath,
  exceptionalPath, evidence, coverageStatus, coverageNote, programPoint, relatedPoint,
  relatedSite, relationDepth, bindingIndex
)
select
  canonicalCallableIdentity(owner) as unit_id,
  canonicalCallableIdentity(enclosingCallable(site)) as site_callable,
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  site.getLocation().getStartColumn() as site_start_column,
  programPoint as program_point,
  relatedPoint as related_point,
  relatedSite.getLocation().getFile().getRelativePath() as related_file,
  relatedSite.getLocation().getStartLine() as related_start_line,
  relatedSite.getLocation().getStartColumn() as related_start_column,
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
