/** Shared conservative attacker-controlled loop witness for G3/G4. */
import java
import semmle.code.java.dataflow.DataFlow

predicate p0Handler(Method method) {
  exists(Annotation mapping |
    mapping = method.getAnAnnotation() and
    mapping.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping"])
  )
  or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and
    (method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet.http", "HttpServlet") or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServlet"))
  or method.getName() = ["channelRead", "channelRead0"] and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("io.netty.channel", ["ChannelInboundHandlerAdapter", "SimpleChannelInboundHandler"])
  or method.getName() = "messageArrived" and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("org.eclipse.paho.client.mqttv3", "IMqttMessageListener")
}

predicate p0AttackerParameter(Method method, Parameter input) {
  input = method.getAParameter() and p0Handler(method) and
  (
    exists(Annotation annotation |
      annotation = input.getAnAnnotation() and annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestBody", "RequestParam", "PathVariable", "RequestHeader"])
    )
    or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and input = method.getParameter(0)
    or method.getName() = ["channelRead", "channelRead0", "messageArrived"] and input = method.getParameter(1)
  )
}

predicate p0ServletDerived(Method method, Parameter request, MethodCall derived) {
  p0AttackerParameter(method, request) and
  method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and
  derived.getEnclosingCallable() = method and
  derived.getMethod().getName() = ["getParameter", "getParameterValues", "getInputStream", "getReader", "getPart", "getParts", "body"] and
  derived.getQualifier().(VarAccess).getVariable() = request
}

predicate p0SourceNode(DataFlow::Node source) {
  exists(Method method, Parameter input | p0AttackerParameter(method, input) and source.asParameter() = input)
  or exists(Method method, Parameter request, MethodCall derived | p0ServletDerived(method, request, derived) and source.asExpr() = derived)
}

predicate loopConditionExpr(LoopStmt loop, Expr expression) {
  expression = loop.getCondition()
  or exists(BinaryExpr condition |
    condition = loop.getCondition() and expression = [condition.getLeftOperand(), condition.getRightOperand()]
  )
}

module P0LoopFlowConfig implements DataFlow::ConfigSig {
  predicate isSource(DataFlow::Node source) { p0SourceNode(source) }
  predicate isSink(DataFlow::Node sink) {
    exists(LoopStmt loop, Expr expression | loopConditionExpr(loop, expression) and sink.asExpr() = expression)
  }
}
module P0LoopFlow = DataFlow::Global<P0LoopFlowConfig>;

/** True only when a supported attacker value flows to the actual loop condition. */
predicate attackerControlsLoop(LoopStmt loop) {
  exists(DataFlow::Node source, DataFlow::Node sink, Expr expression |
    loopConditionExpr(loop, expression) and sink.asExpr() = expression and
    P0LoopFlow::flow(source, sink)
  )
}

/** The call is syntactically contained by the selected loop; its condition is
 * separately required to have a real global-flow witness. Growth operations
 * are restricted by the caller query, so a condition-side helper is not a G.
 */
predicate growthInLoopBody(MethodCall growth, LoopStmt loop) {
  exists(ExprStmt statement |
    statement.getExpr() = growth and statement.getParent*() = loop.getBody()
  )
}
