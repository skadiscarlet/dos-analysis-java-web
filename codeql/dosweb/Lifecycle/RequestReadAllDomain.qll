/** Exact local byte-materialization scan domain; never a whole-server bound. */
import java
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

/** Unsupported control or hidden computation must keep local coverage open.
 * This is deliberately a closed syntax subset, not an absence heuristic for
 * methods named guard/bound/close. */
predicate readAllHasUnmodeledControl(Callable owner) {
  exists(Stmt control |
    control.getEnclosingCallable() = owner and
    (control instanceof IfStmt or control instanceof LoopStmt or
     control instanceof SwitchStmt or control instanceof TryStmt or
     control instanceof SynchronizedStmt or control instanceof ThrowStmt or
     control instanceof AssertStmt)
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

predicate readAllOwnerAdmitted(Callable owner) {
  owner instanceof Method and readAllMappedMethod(owner.(Method))
  or exists(Constructor target |
    owner = target and httpServletRequestWrapperType(target.getDeclaringType()) and
    exists(ClassInstanceExpr call | readAllPlainWrapperCall(call, target)) and
    not exists(ConstructorCall other |
      other.getConstructor() = target and
      not (other instanceof ClassInstanceExpr and
           readAllPlainWrapperCall(other.(ClassInstanceExpr), target))
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
      other.getEnclosingCallable() = owner and other != call and other != getter
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
