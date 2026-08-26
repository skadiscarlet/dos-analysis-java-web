/** Shared proof-carrying Entry -> Growth domain. */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

module EntryGrowthPathDomain {
  predicate readAllMaterialization(MethodCall call) {
    call.getMethod().hasQualifiedName("cn.hutool.core.io", "IoUtil", "readBytes")
    or call.getMethod().hasQualifiedName("org.apache.commons.io", "IOUtils", "toByteArray")
    or call.getMethod().hasQualifiedName("org.springframework.util", "StreamUtils", "copyToByteArray")
    or call.getMethod().hasQualifiedName("org.springframework.util", "StreamUtils", "copyToString")
    or call.getMethod().hasQualifiedName("cn.devezhao.commons.web", "ServletUtils", "getRequestString")
    or call.getMethod().getName() = "readAllBytes" and
      call.getMethod().getDeclaringType().getASupertype*().hasQualifiedName("java.io", "InputStream")
  }

  predicate isArmeriaRequestType(Type type) {
    type.(RefType).getASourceSupertype*().hasQualifiedName("fixture.armeria", "HttpRequest")
    or type.(RefType).getASourceSupertype*().hasQualifiedName("com.linecorp.armeria.common", "HttpRequest")
  }

  predicate isServletRequestType(Type type) {
    type.(RefType).getASupertype*().hasQualifiedName("javax.servlet.http", "HttpServletRequest")
    or type.(RefType).getASupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServletRequest")
  }

  predicate isInputStreamType(Type type) {
    type.(RefType).getASupertype*().hasQualifiedName("java.io", "InputStream")
  }

  /** Source-backed Entry extraction is authoritative when framework annotations
   * are unavailable in an incomplete application database. Exact file/line
   * reconciliation against normalized Entry facts happens in production. */
  predicate sourceInputStreamHandler(Method method) {
    method.fromSource() and
    method.getLocation().getFile().getRelativePath().matches("%.java") and
    exists(Parameter input |
      input = method.getAParameter() and isInputStreamType(input.getType())
    )
  }

  predicate armeriaAggregation(MethodCall call) {
    call.getMethod().getName() = "aggregateWithPooledObjects" and
    isArmeriaRequestType(call.getQualifier().getType())
  }

  predicate byteArrayOutputCopy(MethodCall call) {
    call.getMethod().hasQualifiedName("java.io", "ByteArrayOutputStream", "toByteArray")
  }

  predicate httpSessionAttributeWrite(MethodCall call) {
    call.getMethod().getName() = "setAttribute" and call.getNumArgument() = 2 and
    call.getMethod().getDeclaringType().getASupertype*().hasQualifiedName(
      ["fixture.spring", "javax.servlet.http", "jakarta.servlet.http"], "HttpSession"
    )
  }

  predicate isNettyFullHttpRequestType(Type type) {
    type.(RefType).getASupertype*().hasQualifiedName("io.netty.handler.codec.http", "FullHttpRequest")
  }

  predicate nettyFullRequestStringMaterialization(
    MethodCall stringify, MethodCall content, Expr request
  ) {
    stringify.getMethod().getName() = "toString" and
    stringify.getNumArgument() = 1 and
    stringify.getArgument(0).getType().(RefType).getASupertype*().hasQualifiedName("java.nio.charset", "Charset") and
    stringify.getQualifier() = content and
    content.getMethod().getName() = "content" and content.getNumArgument() = 0 and
    request = content.getQualifier() and isNettyFullHttpRequestType(request.getType())
  }
  // A switch body belongs to a case only until the next case label. This avoids
  // associating every service call in a dispatcher with every route literal.
  predicate elementInSwitchCase(SwitchStmt switchStmt, ConstCase switchCase, Expr element) {
    exists(int caseIndex, int elementIndex, Stmt elementStmt |
      switchStmt.getStmt(caseIndex) = switchCase and
      switchStmt.getStmt(elementIndex) = elementStmt and
      element.getParent*() = elementStmt and elementIndex > caseIndex and
      not exists(SwitchCase boundary, int boundaryIndex |
        switchStmt.getStmt(boundaryIndex) = boundary and
        boundaryIndex > caseIndex and boundaryIndex <= elementIndex
      )
    )
  }

  predicate uniqueConcreteServiceTarget(MethodCall call, Method target) {
    target = call.getMethod() and target.fromSource() and not target.isAbstract()
    or
    target.fromSource() and not target.isAbstract() and
    target.getSignature() = call.getMethod().getSignature() and
    target.getDeclaringType().getASupertype*() = call.getMethod().getDeclaringType() and
    not exists(Method other |
      other != target and other.fromSource() and not other.isAbstract() and
      other.getSignature() = call.getMethod().getSignature() and
      other.getDeclaringType().getASupertype*() = call.getMethod().getDeclaringType()
    )
  }

  /**
   * Bounded Netty HTTP dispatcher model:
   * FullHttpRequest.uri/body locals -> direct or one anonymous callback ->
   * private switch helper -> fromJson(String, Class) -> unique concrete service.
   * JSON conversion, captured async state and interface dispatch keep the proof
   * partial; this predicate only establishes the exact source-backed skeleton.
   */
  predicate nettyJsonSwitchDispatch(
    Method callback, Parameter message, string route, Method serviceTarget
  ) {
    callback.getName() = ["channelRead", "channelRead0"] and
    message = callback.getParameter(1) and isNettyFullHttpRequestType(message.getType()) and
    exists(
      MethodCall uriCall, LocalVariableDecl uriLocal,
      MethodCall stringify, MethodCall content, Expr bodyRequest, LocalVariableDecl bodyLocal,
      MethodCall dispatchCall, Callable dispatchOwner, Method helper,
      int uriIndex, int bodyIndex, Parameter uriParameter, Parameter bodyParameter,
      SwitchStmt routeSwitch, ConstCase routeCase, CompileTimeConstantExpr routeValue,
      MethodCall jsonCall, LocalVariableDecl dtoLocal, MethodCall serviceCall, int dtoIndex |
      uriCall.getEnclosingCallable() = callback and uriCall.getMethod().getName() = "uri" and
      uriCall.getNumArgument() = 0 and
      uriCall.getQualifier().(VarAccess).getVariable() = message and
      uriLocal.getInitializer() = uriCall and
      nettyFullRequestStringMaterialization(stringify, content, bodyRequest) and
      stringify.getEnclosingCallable() = callback and
      bodyRequest.(VarAccess).getVariable() = message and bodyLocal.getInitializer() = stringify and
      dispatchOwner = dispatchCall.getEnclosingCallable() and
      (
        dispatchOwner = callback
        or dispatchOwner.getDeclaringType() instanceof AnonymousClass and
          dispatchOwner.getDeclaringType().(AnonymousClass).getClassInstanceExpr().getEnclosingCallable() = callback
      ) and
      dispatchCall.getMethod() = helper and helper.fromSource() and helper.isPrivate() and
      helper.getDeclaringType() = callback.getDeclaringType() and
      uriIndex != bodyIndex and
      dispatchCall.getArgument(uriIndex).(VarAccess).getVariable() = uriLocal and
      dispatchCall.getArgument(bodyIndex).(VarAccess).getVariable() = bodyLocal and
      uriParameter = helper.getParameter(uriIndex) and bodyParameter = helper.getParameter(bodyIndex) and
      routeSwitch.getEnclosingCallable() = helper and
      routeSwitch.getExpr().(VarAccess).getVariable() = uriParameter and
      routeCase = routeSwitch.getAConstCase() and routeValue = routeCase.getValue() and
      route = routeValue.getStringValue() and route.matches("/%") and
      jsonCall.getEnclosingCallable() = helper and jsonCall.getMethod().getName() = "fromJson" and
      jsonCall.getNumArgument() = 2 and
      jsonCall.getArgument(0).(VarAccess).getVariable() = bodyParameter and
      jsonCall.getArgument(1) instanceof TypeLiteral and
      dtoLocal.getInitializer() = jsonCall and elementInSwitchCase(routeSwitch, routeCase, jsonCall) and
      serviceCall.getEnclosingCallable() = helper and
      serviceCall.getArgument(dtoIndex).(VarAccess).getVariable() = dtoLocal and
      elementInSwitchCase(routeSwitch, routeCase, serviceCall) and
      uniqueConcreteServiceTarget(serviceCall, serviceTarget)
    )
  }


  predicate isServletRequestWrapper(RefType type) {
    type.getASupertype*().hasQualifiedName("javax.servlet.http", "HttpServletRequestWrapper")
    or type.getASupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServletRequestWrapper")
  }

  predicate servletRequestStringMaterialization(MethodCall append, Parameter request) {
    exists(Constructor constructor, MethodCall inputStream, MethodCall read, WhileStmt loop |
      isServletRequestWrapper(constructor.getDeclaringType()) and
      request = constructor.getAParameter() and
      (
        request.getType().(RefType).getASupertype*().hasQualifiedName("javax.servlet.http", "HttpServletRequest")
        or request.getType().(RefType).getASupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServletRequest")
      ) and
      inputStream.getEnclosingCallable() = constructor and
      inputStream.getMethod().getName() = "getInputStream" and
      exists(VarAccess requestAccess |
        requestAccess.getVariable() = request and requestAccess.getParent*() = inputStream.getQualifier()
      ) and
      append.getEnclosingCallable() = constructor and append.getMethod().getName() = "append" and
      append.getQualifier().getType().hasName("StringBuilder") and
      append.getAnEnclosingStmt() = loop.getBody() and
      read.getParent*() = loop.getCondition() and read.getMethod().getName() = "read"
    )
  }

  /** Only supported real framework APIs are sources; fixtures provide package-accurate stubs. */
  predicate handlerMethod(Method method) {
    exists(Annotation mapping |
      mapping = method.getAnAnnotation() and
      mapping.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping"])
    )
    or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and
      (method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet.http", "HttpServlet") or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServlet"))
    or method.getName() = "doFilter" and
      (method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet", "Filter") or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet", "Filter"))
    or method.getName() = ["channelRead", "channelRead0"] and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("io.netty.channel", ["ChannelInboundHandlerAdapter", "SimpleChannelInboundHandler"])
    or method.getName() = "messageArrived" and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("org.eclipse.paho.client.mqttv3", "IMqttMessageListener")
    or exists(Annotation mapping |
      mapping = method.getAnAnnotation() and
      (
        mapping.getType().hasQualifiedName("fixture.armeria", ["Post", "Get"])
        or mapping.getType().hasQualifiedName("com.linecorp.armeria.server.annotation", ["Post", "Get"])
      )
    )
    or sourceInputStreamHandler(method)
  }

  predicate attackerInput(Method method, Parameter input) {
    input = method.getAParameter() and handlerMethod(method) and
    (
      exists(Annotation annotation |
        annotation = input.getAnAnnotation() and annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestBody", "RequestParam", "PathVariable", "RequestHeader"])
      )
      or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch", "doFilter"] and input = method.getParameter(0)
      or method.getName() = ["channelRead", "channelRead0", "messageArrived"] and input = method.getParameter(1)
      or isServletRequestType(input.getType())
      or isArmeriaRequestType(input.getType())
      or sourceInputStreamHandler(method) and isInputStreamType(input.getType())
    )
  }

  /** submit(task) carries a task value, never a submission count without a loop/batch proof. */
  predicate growthDemand(Expr site, string target, Expr demand) {
    exists(MethodCall call |
      site = call and
      (
        call.getMethod().getName() = ["allocate", "allocateDirect"] and target = "size" and demand = call.getArgument(0)
        or call.getMethod().getName() = ["put", "computeIfAbsent", "putIfAbsent", "merge"] and
          call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util", "Map") and
          target = "key" and demand = call.getArgument(0)
        or call.getMethod().getName() = ["add", "offer"] and target = "value" and demand = call.getArgument(0)
        or call.getMethod().getName() = ["submit", "execute", "schedule"] and target = "value" and demand = call.getArgument(0)
        or call.getMethod().getName() = "getPayload" and target = "size" and demand = call.getQualifier()
        or readAllMaterialization(call) and target = "size" and
          (
            call.getMethod().getName() = "readAllBytes" and demand = call.getQualifier()
            or call.getMethod().getName() != "readAllBytes" and demand = call.getArgument(0)
          )
        or armeriaAggregation(call) and target = "size" and demand = call.getQualifier()
        or byteArrayOutputCopy(call) and target = "size" and demand = call.getQualifier()
        or httpSessionAttributeWrite(call) and target = "value" and demand = call.getArgument(1)
        or exists(MethodCall content, Expr request |
          nettyFullRequestStringMaterialization(call, content, request) and
          target = "size" and demand = request
        )
      )
    )
    or exists(ArrayCreationExpr allocation |
      site = allocation and target = "size" and demand = allocation.getDimension(0)
    )
    or exists(ClassInstanceExpr allocation |
      site = allocation and
      (
        allocation.getConstructedType().hasQualifiedName("java.awt.image", "BufferedImage")
        or allocation.getConstructedType().hasQualifiedName("com.wf.captcha", "SpecCaptcha")
      ) and
      target = "size" and demand = [allocation.getArgument(0), allocation.getArgument(1)]
    )
  }

  predicate materializationParameter(Method method, Parameter input) {
    attackerInput(method, input) and exists(Annotation annotation |
      annotation = input.getAnAnnotation() and
      annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody")
    ) and
    (
      input.getType() instanceof Array and input.getType().(Array).getElementType().hasName("byte")
      or input.getType().(RefType).hasQualifiedName("java.lang", "String")
    )
  }

  /** Results of supported Servlet request accessors are attacker-controlled values. */
  predicate servletDerivedInput(Method method, Parameter input, MethodCall derived) {
    attackerInput(method, input) and method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch", "doFilter"] and
    derived.getEnclosingCallable() = method and
    derived.getMethod().getName() = ["body", "getParameter", "getParameterValues", "getInputStream", "getReader", "getPart", "getParts", "getRequestURI"] and
    derived.getQualifier().(VarAccess).getVariable() = input
  }

  predicate servletRequestAccessor(MethodCall call) {
    call.getMethod().getName() = ["body", "getParameter", "getParameterValues", "getInputStream", "getReader", "getPart", "getParts", "getRequestURI"] and
    isServletRequestType(call.getQualifier().getType())
  }

  /** A regex group is attacker-controlled only when its Matcher is locally
   * derived from this filter request's getRequestURI() value. */
  predicate filterPathGroupInput(Method method, Parameter input, MethodCall group) {
    attackerInput(method, input) and method.getName() = "doFilter" and
    group.getEnclosingCallable() = method and group.getMethod().hasQualifiedName("java.util.regex", "Matcher", "group") and
    exists(MethodCall uri, MethodCall matcher, DataFlow::Node inputNode, DataFlow::Node uriQualifier,
           DataFlow::Node uriResult, DataFlow::Node matcherArgument, DataFlow::Node matcherResult,
           DataFlow::Node groupQualifier |
      uri.getEnclosingCallable() = method and uri.getMethod().getName() = "getRequestURI" and
      matcher.getEnclosingCallable() = method and matcher.getMethod().hasQualifiedName("java.util.regex", "Pattern", "matcher") and
      inputNode.asParameter() = input and uriQualifier.asExpr() = uri.getQualifier() and
      uriResult.asExpr() = uri and matcherArgument.asExpr() = matcher.getArgument(0) and
      matcherResult.asExpr() = matcher and groupQualifier.asExpr() = group.getQualifier() and
      DataFlow::localFlow(inputNode, uriQualifier) and
      DataFlow::localFlow(uriResult, matcherArgument) and
      DataFlow::localFlow(matcherResult, groupQualifier)
    )
  }

  predicate attackerSourceNode(Method method, Parameter input, DataFlow::Node source) {
    attackerInput(method, input) and source.asParameter() = input
    or exists(MethodCall derived | servletDerivedInput(method, input, derived) and source.asExpr() = derived)
    or exists(MethodCall group | filterPathGroupInput(method, input, group) and source.asExpr() = group)
  }

  module EntryToGrowthConfig implements DataFlow::ConfigSig {
    predicate isSource(DataFlow::Node source) { exists(Method method, Parameter input | attackerSourceNode(method, input, source)) }
    predicate isSink(DataFlow::Node sink) {
      exists(Expr site, string target, Expr demand |
        growthDemand(site, target, demand) and sink.asExpr() = demand
      )
      or exists(MethodCall append, Parameter request |
        servletRequestStringMaterialization(append, request) and sink.asParameter() = request
      )
    }
    predicate isAdditionalFlowStep(DataFlow::Node pred, DataFlow::Node succ) {
      exists(MethodCall call, Method target, int index |
        uniqueSourceTarget(call, target) and pred.asExpr() = call.getArgument(index) and
        succ.asParameter() = target.getParameter(index)
      )
      or exists(ClassInstanceExpr call, Constructor target, int index |
        constructorCall(call, target) and pred.asExpr() = call.getArgument(index) and
        succ.asParameter() = target.getParameter(index)
      )
      or exists(MethodCall call |
        servletRequestAccessor(call) and pred.asExpr() = call.getQualifier() and succ.asExpr() = call
      )
      or exists(Parameter captured, VarAccess use, LambdaExpr lambda |
        pred.asParameter() = captured and succ.asExpr() = use and use.getVariable() = captured and
        use.getEnclosingCallable() = lambda.asMethod() and
        lambda.getEnclosingCallable() = captured.getCallable()
      )
    }
  }
  module EntryToGrowthFlow = TaintTracking::Global<EntryToGrowthConfig>;

  /** Resolve only concrete direct calls or an exact final-field receiver whose
   * source implementation remains unambiguous for the invoked signature.  This
   * avoids materializing the database-wide Method.overrides cross product. */
  predicate uniqueSourceTarget(MethodCall edge, Method target) {
    target = edge.getMethod() and target.fromSource() and not target.isAbstract()
    or exists(FieldAccess receiver, Field field, ClassInstanceExpr initializer |
      edge.getQualifier() = receiver and receiver.getField() = field and
      field.isFinal() and field.getInitializer() = initializer and
      target.getDeclaringType() = initializer.getConstructedType() and
      target.getSignature() = edge.getMethod().getSignature() and
      target.fromSource() and not target.isAbstract() and
      not exists(Method other |
        other != target and other.fromSource() and not other.isAbstract() and
        other.getSignature() = edge.getMethod().getSignature() and
        other.getDeclaringType().getASupertype*() = edge.getMethod().getDeclaringType()
      )
    )
  }

  predicate constructorCall(ClassInstanceExpr edge, Constructor target) {
    target = edge.getConstructor() and target.fromSource()
  }

  predicate lexicalLambdaCall(Callable source, Method target) {
    exists(LambdaExpr lambda |
      lambda.getEnclosingCallable() = source and target = lambda.asMethod() and
      lambda.getLocation().getFile().getRelativePath().matches("%.java")
    )
  }

  string callEdgeId(Expr edge, Callable source, Callable target) {
    result = source.getQualifiedName() + "~" + target.getQualifiedName() + "@" +
      edge.getLocation().getFile().getRelativePath() + ":" +
      edge.getLocation().getStartLine().toString()
  }

  /** One exact source-backed edge. Interface dispatch is accepted only when
   * uniqueSourceTarget resolves one concrete implementation. */
  predicate uniqueCallableEdge(Callable source, Callable target, string edgeId) {
    exists(MethodCall edge, Method method |
      edge.getEnclosingCallable() = source and uniqueSourceTarget(edge, method) and
      target = method and edgeId = callEdgeId(edge, source, target)
    )
    or exists(ClassInstanceExpr edge, Constructor constructor |
      edge.getEnclosingCallable() = source and constructorCall(edge, constructor) and
      target = constructor and edgeId = callEdgeId(edge, source, target)
    )
    or exists(LambdaExpr edge, Method method |
      edge.getEnclosingCallable() = source and method = edge.asMethod() and
      lexicalLambdaCall(source, method) and target = method and
      edgeId = callEdgeId(edge, source, target)
    )
  }

  /** Carries the stable source location of every bounded callable edge.
   * Keep the depth bound explicitly unrolled: a recursive string-valued path
   * relation makes the evaluator materialize every source-callable path and
   * can exhaust the predicate cache even for the fixture database. */
  predicate boundedCallPath(Callable source, Callable sink, int depth, string path) {
    depth = 0 and source = sink and path = source.getQualifiedName()
    or exists(Callable first, string firstEdge |
      depth = 1 and uniqueCallableEdge(source, first, firstEdge) and
      first = sink and path = source.getQualifiedName() + ">" + firstEdge
    )
    or exists(Callable first, Callable second, string firstEdge, string secondEdge |
      depth = 2 and uniqueCallableEdge(source, first, firstEdge) and
      uniqueCallableEdge(first, second, secondEdge) and second = sink and
      path = source.getQualifiedName() + ">" + firstEdge + ">" + secondEdge
    )
    or exists(Callable first, Callable second, Callable third,
              string firstEdge, string secondEdge, string thirdEdge |
      depth = 3 and uniqueCallableEdge(source, first, firstEdge) and
      uniqueCallableEdge(first, second, secondEdge) and
      uniqueCallableEdge(second, third, thirdEdge) and third = sink and
      path = source.getQualifiedName() + ">" + firstEdge + ">" + secondEdge +
        ">" + thirdEdge
    )
  }

  predicate entryGrowthPath(Method source, Parameter input, Element sinkSite, string target, string sinkText,
                    string path, string phase, string confidence, string coverage, string note) {
    exists(DataFlow::Node sourceNode, DataFlow::Node sinkNode, Expr sink, Expr demand,
           int depth |
      EntryToGrowthFlow::flow(sourceNode, sinkNode) and attackerSourceNode(source, input, sourceNode) and
      growthDemand(sink, target, demand) and sinkNode.asExpr() = demand and
      boundedCallPath(source, sink.getEnclosingCallable(), depth, path) and
      sinkSite = sink and sinkText = demand.toString() and
      phase = "entry>global_dataflow>growth" and confidence = "proven" and
      coverage = "complete" and
      (
        source = sink.getEnclosingCallable() and note = "same_handler_global_dataflow"
        or
        source != sink.getEnclosingCallable() and
        note = "unique_bounded_call_path_global_dataflow"
      )
    )
    or materializationParameter(source, input) and sinkSite = input and target = "size" and sinkText = input.getName() and
       path = source.getQualifiedName() and phase = "entry>materialization" and confidence = "proven" and coverage = "complete" and note = "request_body_parameter_materialization"
    or exists(DataFlow::Node sourceNode, DataFlow::Node sinkNode, MethodCall append,
              Parameter request, int depth |
      EntryToGrowthFlow::flow(sourceNode, sinkNode) and attackerSourceNode(source, input, sourceNode) and
      servletRequestStringMaterialization(append, request) and sinkNode.asParameter() = request and
      boundedCallPath(source, append.getEnclosingCallable(), depth, path) and
      sinkSite = append and target = "size" and
      sinkText = append.getArgument(0).toString() and
      phase = "entry>global_dataflow>growth" and confidence = "proven" and
      coverage = "complete" and
      (
        source = append.getEnclosingCallable() and note = "same_handler_global_dataflow"
        or source != append.getEnclosingCallable() and
        note = "unique_bounded_call_path_global_dataflow"
      )
    )
    or exists(Expr sink, Expr demand, Method serviceTarget, string route,
              string servicePath, int depth |
      nettyJsonSwitchDispatch(source, input, route, serviceTarget) and
      growthDemand(sink, target, demand) and
      boundedCallPath(serviceTarget, sink.getEnclosingCallable(), depth, servicePath) and
      sinkSite = sink and sinkText = demand.toString() and
      path = source.getQualifiedName() + "[" + route + "]>" + servicePath and
      phase = "entry>netty_json_switch>async>service>growth" and
      confidence = "partial" and coverage = "partial" and
      note = "netty_json_switch_async_dispatch_requires_path_coverage"
    )
  }
}
