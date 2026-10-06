/** Exact local byte-materialization scan domain; never a whole-server bound. */
import java
import semmle.code.java.dataflow.DataFlow
import dosweb.Growth.LoopAmplification
import dosweb.Growth.RequestMaterializationDomain

/** Reuse the supported API names, but reject length-limited overloads and
 * source-defined readAllBytes overrides whose behavior is not the JDK API. */
predicate exactReadAllStreamInput(MethodCall call, Expr input) {
  call.getMethod().hasQualifiedName("java.io", "InputStream", "readAllBytes") and
  call.getNumArgument() = 0 and input = call.getQualifier()
  or
  call.getMethod().hasQualifiedName("cn.hutool.core.io", "IoUtil", "readBytes") and
  call.getNumArgument() = 1 and input = call.getArgument(0)
  or
  call.getMethod().hasQualifiedName("org.apache.commons.io", "IOUtils", "toByteArray") and
  call.getNumArgument() = 1 and input = call.getArgument(0)
  or
  call.getMethod().hasQualifiedName("org.springframework.util", "StreamUtils", "copyToByteArray") and
  call.getNumArgument() = 1 and input = call.getArgument(0)
  or
  call.getMethod().hasQualifiedName("org.springframework.util", "StreamUtils", "copyToString") and
  call.getNumArgument() = 2 and input = call.getArgument(0)
}

/** The stream expression must be the exact getter of the unchanged request
 * parameter. In particular, a wrapper/cap/local unrelated stream is not that
 * stream merely because its class is an InputStream. */
predicate exactReadAllRequest(
  MethodCall call, MethodCall getter, Parameter request
) {
  exactReadAllStreamInput(call, getter) and
  getter.getEnclosingCallable() = call.getEnclosingCallable() and
  request.getCallable() = call.getEnclosingCallable() and
  request.getType().(RefType).hasQualifiedName(
    ["javax.servlet.http", "jakarta.servlet.http"], "HttpServletRequest"
  ) and
  getter.getMethod().hasQualifiedName(
    ["javax.servlet.http", "jakarta.servlet.http", "javax.servlet", "jakarta.servlet"],
    ["HttpServletRequest", "ServletRequest"], "getInputStream"
  ) and getter.getNumArgument() = 0 and
  getter.getQualifier().(VarAccess).getVariable() = request and
  not exists(request.getAnAssignedValue()) and
  (
    exists(Method method |
      method = call.getEnclosingCallable() and p0AttackerParameter(method, request)
    )
    or requestWrapperConstructorStream(getter, request)
  )
}

private predicate lombokSneakyThrowsAnnotation(Callable owner, Annotation annotation) {
  annotation = owner.getAnAnnotation() and
  annotation.getType().hasQualifiedName("lombok", "SneakyThrows")
}

/** Normalize only a transparent exception shell: one catch, one throw of
 * the unchanged caught value, no resources/finally. A shared source line with
 * @SneakyThrows is not by itself proof that source-written effects are absent. */
private predicate lombokTransparentShell(
  TryStmt attempt, ThrowStmt thrown, MethodCall call, Callable owner
) {
  attempt.getEnclosingCallable() = owner and
  not exists(attempt.getFinally()) and not exists(attempt.getAResource()) and
  exists(Annotation annotation, CatchClause caught, LocalVariableDecl exception |
    lombokSneakyThrowsAnnotation(owner, annotation) and
    attempt.getLocation().getStartLine() = annotation.getLocation().getStartLine() and
    caught = attempt.getACatchClause() and
    not exists(CatchClause other | other = attempt.getACatchClause() and other != caught) and
    caught.getBlock().getNumStmt() = 1 and thrown = caught.getBlock().getStmt(0) and
    call = thrown.getExpr() and call.getEnclosingCallable() = owner and
    call.getMethod().hasQualifiedName("lombok", "Lombok", "sneakyThrow") and
    not call.getMethod().fromSource() and call.getNumArgument() = 1 and
    exception = caught.getVariable().getVariable() and
    not exists(exception.getAnAssignedValue()) and
    call.getArgument(0).(VarAccess).getVariable() = exception and
    thrown.getLocation().getStartLine() = annotation.getLocation().getStartLine() and
    call.getLocation().getStartLine() = annotation.getLocation().getStartLine()
  )
}

private predicate lombokGeneratedSneakyThrowCall(MethodCall call, Callable owner) {
  exists(TryStmt attempt, ThrowStmt thrown |
    lombokTransparentShell(attempt, thrown, call, owner)
  )
}

private predicate lombokGeneratedThrow(ThrowStmt thrown, Callable owner) {
  exists(TryStmt attempt, MethodCall call |
    lombokTransparentShell(attempt, thrown, call, owner)
  )
}

private predicate lombokGeneratedTry(TryStmt attempt, Callable owner) {
  exists(ThrowStmt thrown, MethodCall call |
    lombokTransparentShell(attempt, thrown, call, owner)
  )
}

private predicate lombokGeneratedControl(Stmt control, Callable owner) {
  control instanceof ThrowStmt and lombokGeneratedThrow(control.(ThrowStmt), owner)
  or control instanceof TryStmt and lombokGeneratedTry(control.(TryStmt), owner)
}

/** Unsupported control or hidden computation must keep local coverage open.
 * This is deliberately a closed syntax subset, not an absence heuristic for
 * methods named guard/bound/close. */
predicate readAllHasUnmodeledControl(Callable owner) {
  exists(Stmt control |
    control.getEnclosingCallable() = owner and
    (control instanceof IfStmt or control instanceof LoopStmt or
     control instanceof SwitchStmt or control instanceof TryStmt or
     control instanceof SynchronizedStmt or control instanceof ThrowStmt or
     control instanceof AssertStmt) and
    not lombokGeneratedControl(control, owner)
  )
  or exists(ConditionalExpr conditional | conditional.getEnclosingCallable() = owner)
  or exists(LambdaExpr lambda | lambda.getEnclosingCallable() = owner)
}

predicate readAllMappedMethod(Method method) {
  exists(Annotation mapping |
    mapping = method.getAnAnnotation() and
    mapping.getType().hasQualifiedName(
      "org.springframework.web.bind.annotation",
      ["RequestMapping", "GetMapping", "PostMapping", "PutMapping", "PatchMapping", "DeleteMapping"]
    )
  )
  or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and
     method.getDeclaringType().getASupertype*().hasQualifiedName(
       ["javax.servlet.http", "jakarta.servlet.http"], "HttpServlet"
     )
}

/** A constructor is admitted only through direct, straight-line, unchanged
 * request forwarding at every source call site. A guard in a caller cannot
 * disappear just because the materialization sits in its callee constructor. */
predicate readAllPlainWrapperCall(ClassInstanceExpr call, Constructor target) {
  call.getConstructor() = target and call.getNumArgument() = 1 and
  exists(Method caller, Parameter parameter |
    caller = call.getEnclosingCallable() and readAllMappedMethod(caller) and
    parameter = caller.getParameter(0) and caller.getNumberOfParameters() = 1 and
    httpServletRequestParameter(parameter) and
    not exists(parameter.getAnAssignedValue()) and
    call.getArgument(0).(VarAccess).getVariable() = parameter and
    not readAllHasUnmodeledControl(caller) and
    not exists(MethodCall other | other.getEnclosingCallable() = caller) and
    not exists(ConstructorCall other |
      other.getEnclosingCallable() = caller and other != call
    )
  )
}

predicate servletFilterMethod(Method caller, Parameter request) {
  caller.fromSource() and caller.getName() = "doFilter" and
  caller.getNumberOfParameters() = 3 and
  caller.getDeclaringType().getASupertype*().hasQualifiedName(
    ["javax.servlet", "jakarta.servlet"], "Filter"
  ) and request = caller.getParameter(0) and
  request.getType().(RefType).hasQualifiedName(["javax.servlet", "jakarta.servlet"], "ServletRequest") and
  caller.getParameter(1).getType().(RefType).hasQualifiedName(["javax.servlet", "jakarta.servlet"], "ServletResponse") and
  caller.getParameter(2).getType().(RefType).hasQualifiedName(["javax.servlet", "jakarta.servlet"], "FilterChain") and
  not exists(Parameter parameter |
    parameter.getCallable() = caller and exists(parameter.getAnAssignedValue())
  )
}

/** Track object identity through Object-typed aliases as well. Static type
 * erasure must not conceal a request passed to an unknown helper. */
predicate requestObjectFlow(Parameter request, Expr value) {
  DataFlow::localFlow(DataFlow::parameterNode(request), DataFlow::exprNode(value))
}

/** Require an unchanged parameter or declaration-initialized cast/alias at
 * the wrapper argument. A may-flow through reassignment is insufficient. */
private predicate unchangedRequestAlias(Parameter request, Expr value) {
  value.(VarAccess).getVariable() = request
  or exists(CastExpr cast |
    value = cast and unchangedRequestAlias(request, cast.getExpr())
  )
  or exists(LocalVariableDecl local |
    value.(VarAccess).getVariable() = local and
    local.getEnclosingCallable() = request.getCallable() and
    unchangedRequestAlias(request, local.getInitializer()) and
    not exists(AssignExpr changed |
      changed.getDest().(VarAccess).getVariable() = local and
      not changed.getSource() = local.getInitializer()
    )
  )
}

/** Metadata summary belongs to the Servlet API, not arbitrary overrides
 * sharing a method name. No size/stream/body accessor is admitted. */
predicate filterMetadataRequestAccess(MethodCall call, Parameter request) {
  requestObjectFlow(request, call.getQualifier()) and call.getNumArgument() = 0 and
  call.getMethod().hasQualifiedName(
    ["javax.servlet.http", "jakarta.servlet.http", "javax.servlet", "jakarta.servlet"],
    ["HttpServletRequest", "ServletRequest"],
    ["getServletPath", "getRequestURI", "getContextPath", "getPathInfo", "getContentType", "getMethod"]
  )
}

predicate filterChainForward(MethodCall call) {
  call.getMethod().hasQualifiedName(
    ["javax.servlet", "jakarta.servlet"], "FilterChain", "doFilter"
  ) and call.getNumArgument() = 2
}

private predicate filterPureStringTest(MethodCall call) {
  call.getMethod().hasQualifiedName("java.lang", "String",
    ["equals", "equalsIgnoreCase", "contains", "startsWith", "endsWith"]) and
  call.getNumArgument() = 1
}

/** A chain may alter/consume the request. Only a chain call unable to reach
 * this wrapper (after it, or on a disjoint return path) is outside its prefix. */
private predicate filterForwardAfterWrapper(MethodCall use, ClassInstanceExpr wrapper, Method caller) {
  filterChainForward(use) and
  use.getQualifier().(VarAccess).getVariable() = caller.getParameter(2) and
  exists(use.getControlFlowNode()) and exists(wrapper.getControlFlowNode()) and
  not use.getControlFlowNode().getASuccessor*() = wrapper.getControlFlowNode()
}

/** Closed caller subset for local peak-byte reasoning. Unknown calls,
 * constructors, field/array stores and complex control keep coverage open;
 * absence of a direct request argument alone cannot prove no hidden effect. */
predicate readAllFilterWrapperCall(ClassInstanceExpr call, Constructor target) {
  call.getConstructor() = target and call.getNumArgument() = 1 and
  exists(Method caller, Parameter request |
    caller = call.getEnclosingCallable() and servletFilterMethod(caller, request) and
    requestObjectFlow(request, call.getArgument(0)) and
    unchangedRequestAlias(request, call.getArgument(0)) and
    not exists(MethodCall use |
      use.getEnclosingCallable() = caller and
      not (filterMetadataRequestAccess(use, request) or filterPureStringTest(use) or
           filterForwardAfterWrapper(use, call, caller))
    ) and
    not exists(ConstructorCall other |
      other.getEnclosingCallable() = caller and other != call
    ) and
    not exists(Assignment store |
      store.getEnclosingCallable() = caller and
      (store.getDest() instanceof FieldAccess or store.getDest() instanceof ArrayAccess)
    ) and
    not exists(Stmt control |
      control.getEnclosingCallable() = caller and
      (control instanceof LoopStmt or control instanceof SwitchStmt or
       control instanceof TryStmt or control instanceof SynchronizedStmt or
       control instanceof ThrowStmt or control instanceof AssertStmt)
    ) and
    not exists(ConditionalExpr conditional | conditional.getEnclosingCallable() = caller) and
    not exists(LambdaExpr lambda | lambda.getEnclosingCallable() = caller)
  )
}

predicate readAllAdmittedWrapperCall(ClassInstanceExpr call, Constructor target) {
  readAllPlainWrapperCall(call, target)
  or readAllFilterWrapperCall(call, target)
}

predicate readAllOwnerAdmitted(Callable owner) {
  owner instanceof Method and readAllMappedMethod(owner.(Method))
  or exists(Constructor target |
    owner = target and httpServletRequestWrapperType(target.getDeclaringType()) and
    exists(ClassInstanceExpr call | readAllAdmittedWrapperCall(call, target)) and
    not exists(ConstructorCall other |
      other.getConstructor() = target and
      not (other instanceof ClassInstanceExpr and
           readAllAdmittedWrapperCall(other.(ClassInstanceExpr), target))
    )
  )
}

/** Only the known read-all/getter computation, local storage, and an exact
 * Servlet wrapper super call are closed. Extra calls/allocations stay partial.
 * Closing the stream is intentionally not accepted as a heap-byte reduction. */
predicate requestReadAllLocalDomain(MethodCall call) {
  exists(MethodCall getter, Parameter request, Callable owner |
    exactReadAllRequest(call, getter, request) and
    owner = call.getEnclosingCallable() and readAllOwnerAdmitted(owner) and
    not exists(Parameter other |
      other.getCallable() = owner and other != request and httpServletRequestParameter(other)
    ) and
    not readAllHasUnmodeledControl(owner) and
    not exists(MethodCall other |
      other.getEnclosingCallable() = owner and other != call and other != getter and
      not lombokGeneratedSneakyThrowCall(other, owner)
    ) and
    not exists(ArrayCreationExpr allocation | allocation.getEnclosingCallable() = owner) and
    not exists(ConstructorCall other |
      other.getEnclosingCallable() = owner and
      not (
        other.callsSuper() and
        other.getConstructor().getDeclaringType().hasQualifiedName(
          ["javax.servlet.http", "jakarta.servlet.http"], "HttpServletRequestWrapper"
        ) and other.getNumArgument() = 1 and
        other.getArgument(0).(VarAccess).getVariable() = request
      )
    )
  )
}
