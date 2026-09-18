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

/** Gets the concrete attacker-derived value that controls this loop. */
string attackerLoopDemand(LoopStmt loop) {
  exists(DataFlow::Node source, DataFlow::Node sink, Expr expression |
    loopConditionExpr(loop, expression) and sink.asExpr() = expression and
    P0LoopFlow::flow(source, sink) and
    (
      exists(Parameter input | source.asParameter() = input and result = input.getName())
      or exists(MethodCall derived | source.asExpr() = derived and result = derived.toString())
    )
  )
}

/** Broad lexical containment used only to retain incomplete multiplicity
 * obligations. Nested lambdas and anonymous callables are deliberately
 * included here, but they can never satisfy the exact complete witness below.
 */
predicate growthLexicallyInLoopBody(Expr growth, LoopStmt loop) {
  loop.getBody().getAChild*() = growth.getEnclosingStmt()
  or exists(LambdaExpr lambda |
    growth.getEnclosingCallable() = lambda.asMethod() and
    loop.getBody().getAChild*() = lambda.getEnclosingStmt()
  )
  or exists(Method nested, AnonymousClass anonymous, ClassInstanceExpr creator |
    growth.getEnclosingCallable() = nested and
    nested.getDeclaringType() = anonymous and
    creator = anonymous.getClassInstanceExpr() and
    loop.getBody().getAChild*() = creator.getEnclosingStmt()
  )
}

predicate variableUpdatedInLoopBody(Variable variable, LoopStmt loop) {
  exists(Assignment update |
    update.getDest().(VarAccess).getVariable() = variable and
    loop.getBody().getAChild*() = update.getEnclosingStmt()
  )
  or
  exists(UnaryAssignExpr update |
    update.getOperand().(VarAccess).getVariable() = variable and
    loop.getBody().getAChild*() = update.getEnclosingStmt()
  )
}

/** A bounded, non-wrapping P0 induction domain. The only complete syntax is
 * `for (int i = 0; i < directAttackerIntParameter; i++|++i)`.
 */
predicate canonicalAttackerBoundForLoop(
  ForStmt loop, Variable induction, Parameter bound, VarAccess boundAccess
) {
  induction.getType().hasName("int") and
  exists(LocalVariableDeclExpr declaration, IntegerLiteral zero |
    declaration = loop.getAnInit() and
    declaration.getVariable() = induction and
    declaration.getInit() = zero and zero.getIntValue() = 0 and
    not exists(Expr otherInit |
      otherInit = loop.getAnInit() and otherInit != declaration
    )
  ) and
  exists(LTExpr condition, VarAccess inductionAccess, Method handler |
    condition = loop.getCondition() and
    condition.getLeftOperand() = inductionAccess and
    inductionAccess.getVariable() = induction and
    condition.getRightOperand() = boundAccess and
    boundAccess.getVariable() = bound and
    handler = loop.getEnclosingCallable() and
    p0AttackerParameter(handler, bound) and bound.getType().hasName("int")
  ) and
  exists(UnaryAssignExpr update |
    update = loop.getAnUpdate() and
    (update instanceof PostIncExpr or update instanceof PreIncExpr) and
    update.getOperand().(VarAccess).getVariable() = induction and
    not exists(Expr otherUpdate |
      otherUpdate = loop.getAnUpdate() and otherUpdate != update
    )
  ) and
  not variableUpdatedInLoopBody(induction, loop) and
  not variableUpdatedInLoopBody(bound, loop)
}

predicate soleTopLevelStatement(Stmt statement, LoopStmt loop) {
  (
    loop.getBody() = statement
    or exists(SingletonBlock block |
      loop.getBody() = block and block.getStmt() = statement
    )
  )
}

/** The growth expression is the whole expression of the loop's only
 * top-level expression statement. This positive shape admits calls such as
 * `map.put(...)` and `executor.execute(...)`, while rejecting return, throw,
 * conditional/argument subexpressions, multi-statement bodies, and callbacks.
 */
predicate unconditionalTopLevelGrowthInLoop(Expr growth, LoopStmt loop) {
  growth.getEnclosingCallable() = loop.getEnclosingCallable() and
  exists(ExprStmt statement |
    soleTopLevelStatement(statement, loop) and statement.getExpr() = growth
  )
}

/** Direct allocation additionally admits one simple `=` assignment whose RHS
 * is exactly the allocation. Compound/derived assignments and allocations in
 * arguments or conditional RHS expressions remain unmodeled.
 */
predicate unconditionalTopLevelDirectAllocationInLoop(
  Expr growth, LoopStmt loop
) {
  unconditionalTopLevelGrowthInLoop(growth, loop)
  or
  growth.getEnclosingCallable() = loop.getEnclosingCallable() and
  exists(ExprStmt statement, AssignExpr assignment |
    soleTopLevelStatement(statement, loop) and
    statement.getExpr() = assignment and assignment.getSource() = growth
  )
}

predicate canonicalAttackerLoopMultiplicityShape(
  Expr growth, LoopStmt loop, Parameter bound, VarAccess boundAccess
) {
  exists(ForStmt forLoop, Variable induction |
    loop = forLoop and
    canonicalAttackerBoundForLoop(forLoop, induction, bound, boundAccess) and
    growthLexicallyInLoopBody(growth, loop)
  )
}

/** Exact shared complete multiplicity witness consumed by Container/Async and
 * their Flow demands. Only a whole top-level call expression is accepted.
 */
predicate provenAttackerLoopMultiplicity(
  Expr growth, LoopStmt loop, Parameter bound, VarAccess boundAccess
) {
  canonicalAttackerLoopMultiplicityShape(
    growth, loop, bound, boundAccess
  ) and
  unconditionalTopLevelGrowthInLoop(growth, loop)
}

/** Direct-allocation witness with the one explicitly supported assignment
 * shape. It shares the same canonical header and immutability proof.
 */
predicate provenAttackerLoopMultiplicityForDirectAllocation(
  Expr growth, LoopStmt loop, Parameter bound, VarAccess boundAccess
) {
  canonicalAttackerLoopMultiplicityShape(
    growth, loop, bound, boundAccess
  ) and
  unconditionalTopLevelDirectAllocationInLoop(growth, loop)
}

/** The call is lexically contained by the selected loop. This predicate alone
 * is never a complete multiplicity proof.
 */
predicate growthInLoopBody(MethodCall growth, LoopStmt loop) {
  growthLexicallyInLoopBody(growth, loop)
}
