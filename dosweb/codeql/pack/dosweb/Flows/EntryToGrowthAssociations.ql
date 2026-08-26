/**
 * @name Entry to growth call-graph associations
 * @description Conservative source-defined entry associations; cross-call links remain partial.
 * @kind table
 * @id dosweb/entry-to-growth-associations
 */
import java

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

predicate frameworkHandler(Method method) {
  exists(Annotation a | a = method.getAnAnnotation() and a.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping"]))
  or exists(Annotation a | a = method.getAnAnnotation() and a.getType().hasQualifiedName("javax.ws.rs", ["GET", "POST", "PUT", "DELETE", "PATCH", "Path"]))
  or exists(Annotation a | a = method.getAnAnnotation() and a.getType().hasQualifiedName("jakarta.ws.rs", ["GET", "POST", "PUT", "DELETE", "PATCH", "Path"]))
  or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and (method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet.http", "HttpServlet") or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServlet"))
  or method.getName() = "doFilter" and (method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet", "Filter") or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet", "Filter"))
  or method.getName() = ["channelRead", "channelRead0"] and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("io.netty.channel", ["ChannelInboundHandlerAdapter", "SimpleChannelInboundHandler"])
  or method.getName() = "messageArrived" and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("org.eclipse.paho.client.mqttv3", "IMqttMessageListener")
  or exists(Annotation a |
    a = method.getAnAnnotation() and
    (
      a.getType().hasQualifiedName("fixture.armeria", ["Post", "Get"])
      or a.getType().hasQualifiedName("com.linecorp.armeria.server.annotation", ["Post", "Get"])
    )
  )
}

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
// Growth sites mirror the actual Container/Async/Direct/Input growth queries so that
// a candidate link is only produced for a real, field-backed growth candidate; this
// keeps association cardinality bounded and avoids linking entries to irrelevant calls.
predicate growthSite(Expr site, Callable owner, string target) {
  exists(MethodCall call, FieldAccess receiver |
    site = call and owner = call.getEnclosingCallable() and receiver = call.getQualifier() and
    (
      call.getMethod().getName() = ["put", "computeIfAbsent", "putIfAbsent", "merge"] and call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util", "Map") and target = "key"
      or call.getMethod().getName() = "add" and call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util", "Collection") and target = "value"
      or call.getMethod().getName() = ["submit", "execute", "offer", "schedule"] and
        (
          call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "ExecutorService")
          or call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "BlockingQueue")
        ) and target = "value"
    )
  )
  or exists(MethodCall call |
    site = call and owner = call.getEnclosingCallable() and
    call.getMethod().getName() = ["getPayload", "allocate", "allocateDirect"] and target = "size"
  )
  or exists(MethodCall call |
    site = call and owner = call.getEnclosingCallable() and
    (readAllMaterialization(call) or armeriaAggregation(call) or byteArrayOutputCopy(call)) and
    target = "size"
  )
  or exists(MethodCall call |
    site = call and owner = call.getEnclosingCallable() and
    httpSessionAttributeWrite(call) and target = "value"
  )
  or exists(MethodCall stringify, MethodCall content, Expr request |
    site = stringify and owner = stringify.getEnclosingCallable() and
    nettyFullRequestStringMaterialization(stringify, content, request) and target = "size"
  )
  or exists(MethodCall append, Parameter request |
    site = append and owner = append.getEnclosingCallable() and
    servletRequestStringMaterialization(append, request) and target = "size"
  )
  or exists(ArrayCreationExpr allocation | site = allocation and owner = allocation.getEnclosingCallable() and target = "size")
  or exists(ClassInstanceExpr allocation |
    site = allocation and owner = allocation.getEnclosingCallable() and
    (
      allocation.getConstructedType().hasQualifiedName("java.awt.image", "BufferedImage")
      or allocation.getConstructedType().hasQualifiedName("com.wf.captcha", "SpecCaptcha")
    ) and target = "size"
  )
}

/**
 * Solr parses application/x-www-form-urlencoded request bodies before the
 * selected business handler.  This bounded framework model deliberately
 * requires the exact source-backed Solr pipeline and every named forwarding
 * stage.  The request is stored on HttpSolrCall and crosses interface dispatch,
 * so this is association evidence only: it must remain partial until a full
 * field/path-sensitive witness is available.
 */
predicate sourceMethod(string packageName, string typeName, string methodName, Method method) {
  method.fromSource() and method.getDeclaringType().getPackage().getName() = packageName and
  method.getDeclaringType().getName() = typeName and method.getName() = methodName
}

predicate sourceCall(Method caller, Method callee, MethodCall call) {
  call.getEnclosingCallable() = caller and call.getMethod() = callee and
  call.getLocation().getFile().getRelativePath().matches("%.java")
}

predicate solrFormPrehandlerAssociation(Method entry, MethodCall sink) {
  exists(
    Method dispatch, Method callMethod, Method init, Method parse,
    Method parserDispatch, Method formDispatch, Method parseForm,
    MethodCall entryDispatch, MethodCall dispatchCall, MethodCall callInit,
    MethodCall initParse, MethodCall parseDispatch, MethodCall standardForm,
    MethodCall formSink, CompileTimeConstantExpr contentType |
    sourceMethod("org.apache.solr.servlet", "SolrServlet", "service", entry) and
    sourceMethod("org.apache.solr.servlet", "SolrServlet", "dispatch", dispatch) and
    sourceMethod("org.apache.solr.servlet", "HttpSolrCall", "call", callMethod) and
    sourceMethod("org.apache.solr.servlet", "HttpSolrCall", "init", init) and
    sourceMethod("org.apache.solr.servlet", "SolrRequestParsers", "parse", parse) and
    sourceMethod("org.apache.solr.servlet", "StandardRequestParser", "parseParamsAndFillStreams", parserDispatch) and
    sourceMethod("org.apache.solr.servlet", "FormDataRequestParser", "parseParamsAndFillStreams", formDispatch) and
    sourceMethod("org.apache.solr.servlet", "SolrRequestParsers", "parseFormDataContent", parseForm) and
    sourceCall(entry, dispatch, entryDispatch) and
    sourceCall(dispatch, callMethod, dispatchCall) and
    sourceCall(callMethod, init, callInit) and
    sourceCall(init, parse, initParse) and
    parseDispatch.getEnclosingCallable() = parse and
    parseDispatch.getMethod().getName() = "parseParamsAndFillStreams" and
    sourceCall(parserDispatch, formDispatch, standardForm) and
    sourceCall(formDispatch, parseForm, formSink) and
    contentType.getEnclosingCallable().getDeclaringType() = formDispatch.getDeclaringType() and
    contentType.getStringValue() = "application/x-www-form-urlencoded" and
    sink.getEnclosingCallable() = parseForm and byteArrayOutputCopy(sink)
  )
}

/**
 * JMQTT receives a decoded MQTT message on Netty, dispatches it through an
 * asynchronous RequestProcessor table, and lets PublishProcessor route QoS 2
 * publishes to the per-session receiving map.  The processor-table lookup and
 * asynchronous interface dispatch are not a complete path witness, so this
 * source-backed skeleton is association evidence only and must stay partial.
 */
predicate jmqttValidatedProtocolDispatch(Method entry, Method processProtocol) {
  sourceMethod(
    ["fixture.mqtt", "org.jmqtt.mqtt.netty"],
    ["ConvertedNettyMqttHandler", "NettyMqttHandler"],
    "channelRead",
    entry
  ) and
  sourceMethod(
    ["fixture.mqtt", "org.jmqtt.mqtt"], "MQTTConnection", "processProtocol",
    processProtocol
  ) and
  exists(
    Parameter message, MethodCall validate, LocalVariableDecl typedMessage,
    MethodCall dispatch, int messageIndex |
    message = entry.getParameter(1) and
    message.getType().(RefType).hasQualifiedName("java.lang", "Object") and
    validate.getEnclosingCallable() = entry and
    validate.getMethod().hasQualifiedName(
      ["fixture.mqtt", "org.jmqtt.mqtt.netty"], "MqttNettyUtils", "validateMessage"
    ) and
    validate.getNumArgument() = 1 and
    validate.getArgument(0).(VarAccess).getVariable() = message and
    typedMessage.getInitializer() = validate and
    dispatch.getEnclosingCallable() = entry and dispatch.getMethod() = processProtocol and
    dispatch.getArgument(messageIndex).(VarAccess).getVariable() = typedMessage
  )
}

predicate jmqttAsyncProcessorDispatch(Method processProtocol) {
  exists(LambdaExpr task, MethodCall processRequest, MethodCall submit |
    task.getEnclosingCallable() = processProtocol and
    processRequest.getEnclosingCallable() = task.asMethod() and
    processRequest.getMethod().getName() = "processRequest" and
    processRequest.getMethod().getDeclaringType().hasQualifiedName(
      ["fixture.mqtt", "org.jmqtt.mqtt.protocol"],
      ["PublishProcessor", "RequestProcessor"]
    ) and
    submit.getEnclosingCallable() = processProtocol and
    submit.getMethod().getName() = "submit" and
    submit.getNumArgument() = 1 and
    submit.getArgument(0).(VarAccess).getVariable().getInitializer() = task
  )
}

predicate jmqttQos2Dispatch(Method entry, MethodCall growth) {
  exists(
    Method processProtocol, Method publishRequest, Method processPublish,
    Method processQos2, Method receiveQos2, MethodCall publishCall,
    MethodCall qos2Call, MethodCall receiveCall, FieldAccess receiver |
    jmqttValidatedProtocolDispatch(entry, processProtocol) and
    jmqttAsyncProcessorDispatch(processProtocol) and
    sourceMethod(
      ["fixture.mqtt", "org.jmqtt.mqtt.protocol.impl"], "PublishProcessor",
      "processRequest", publishRequest
    ) and
    sourceMethod(
      ["fixture.mqtt", "org.jmqtt.mqtt"], "MQTTConnection",
      "processPublishMessage", processPublish
    ) and
    sourceMethod(
      ["fixture.mqtt", "org.jmqtt.mqtt"], "MQTTConnection", "processQos2",
      processQos2
    ) and
    sourceMethod(
      ["fixture.mqtt", "org.jmqtt.mqtt.session"], "MqttSession",
      "receivedPublishQos2", receiveQos2
    ) and
    sourceCall(publishRequest, processPublish, publishCall) and
    sourceCall(processPublish, processQos2, qos2Call) and
    sourceCall(processQos2, receiveQos2, receiveCall) and
    growth.getEnclosingCallable() = receiveQos2 and
    growth.getMethod().getName() = "put" and
    receiver = growth.getQualifier() and receiver.getField().getName() = "qos2Receiving" and
    growthSite(growth, receiveQos2, "key")
  )
}

predicate sourceConstructor(
  string packageName, string typeName, Constructor constructor
) {
  constructor.fromSource() and
  constructor.getDeclaringType().getPackage().getName() = packageName and
  constructor.getDeclaringType().getName() = typeName
}

/**
 * Citrus registers RequestWrapperFilter as a component-wide servlet filter.
 * Spring's runtime filter ordering is not recovered here, so the exact source
 * wrapper construction and read-all sink establish only a partial pre-handler
 * association with the source-default authentication route.
 */
predicate citrusAuthenticationPrehandler(Method entry, MethodCall growth) {
  exists(Method filter, Constructor wrapper, ClassInstanceExpr construction |
    sourceMethod(
      ["fixture.spring", "com.github.yiuman.citrus.security.authenticate"],
      ["CitrusAuthenticateController", "AuthenticateController"],
      "authenticate", entry
    ) and
    sourceMethod(
      ["fixture.spring", "com.github.yiuman.citrus.support.http"],
      ["CitrusRequestWrapperFilter", "RequestWrapperFilter"],
      "doFilterInternal", filter
    ) and
    sourceConstructor(
      ["fixture.spring", "com.github.yiuman.citrus.support.http"],
      "RequestWrapper", wrapper
    ) and
    construction.getEnclosingCallable() = filter and construction.getConstructor() = wrapper and
    growth.getEnclosingCallable() = wrapper and
    growth.getMethod().hasQualifiedName("cn.hutool.core.io", "IoUtil", "readBytes") and
    growth.getNumArgument() = 1
  )
}

/**
 * The verification controller selects a processor from a runtime collection;
 * CaptchaProcessor and SessionVerificationRepository are exact source-backed
 * implementations, but both interface dispatches remain unresolved.  The
 * resulting HttpSession retention association is therefore fixed partial.
 */
predicate citrusVerificationSessionDispatch(Method entry, MethodCall growth) {
  exists(
    Method captchaSend, Method sessionSave, MethodCall sendCall, MethodCall saveCall |
    sourceMethod(
      ["fixture.spring", "com.github.yiuman.citrus.security.verify"],
      ["CitrusVerificationController", "VerificationController"],
      "image", entry
    ) and
    sourceMethod(
      ["fixture.spring", "com.github.yiuman.citrus.security.verify.captcha"],
      ["CitrusCaptchaProcessor", "CaptchaProcessor"], "send", captchaSend
    ) and
    sourceMethod(
      ["fixture.spring", "com.github.yiuman.citrus.security.verify"],
      ["CitrusSessionVerificationRepository", "SessionVerificationRepository"],
      "save", sessionSave
    ) and
    sendCall.getEnclosingCallable() = entry and sendCall.getMethod().getName() = "send" and
    (
      sendCall.getMethod().getDeclaringType().hasQualifiedName(
        ["fixture.spring", "com.github.yiuman.citrus.security.verify"],
        ["CitrusVerificationProcessor", "VerificationProcessor"]
      )
      or sendCall.getMethod().getDeclaringType().(ParameterizedType).getGenericType().hasQualifiedName(
        ["fixture.spring", "com.github.yiuman.citrus.security.verify"],
        ["CitrusVerificationProcessor", "VerificationProcessor"]
      )
    ) and
    saveCall.getEnclosingCallable() = captchaSend and saveCall.getMethod().getName() = "save" and
    saveCall.getMethod().getDeclaringType().hasQualifiedName(
      ["fixture.spring", "com.github.yiuman.citrus.security.verify"],
      ["CitrusVerificationRepository", "VerificationRepository"]
    ) and
    growth.getEnclosingCallable() = sessionSave and httpSessionAttributeWrite(growth)
  )
}
// Resolve only a concrete source-defined direct target or an exact concrete
// receiver fixed by a source field initializer.  Enumerating every override of
// every call target makes large application databases explode quadratically;
// exact signature/type constraints preserve the database-wide ambiguity check
// without materializing that cross product.  Local/parameter dispatch,
// reassigned fields, reflection and unresolved receivers intentionally yield no
// edge.
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

// Bounded transitive call reachability: at most depth 3 source-defined hops.  Deeper,
// reflection, or ambiguous dispatch is not a provable association and must not be
// emitted, which also bounds cardinality on large handlers.
predicate callsWithin(Callable source, Callable sink, int depth) {
  depth in [0..3] and (
    source = sink and depth = 0
    or exists(MethodCall edge, Method middle |
      edge.getEnclosingCallable() = source and uniqueSourceTarget(edge, middle) and
      callsWithin(middle, sink, depth - 1)
    )
    or exists(ClassInstanceExpr edge, Constructor middle |
      edge.getEnclosingCallable() = source and constructorCall(edge, middle) and
      callsWithin(middle, sink, depth - 1)
    )
    or exists(Method middle |
      lexicalLambdaCall(source, middle) and callsWithin(middle, sink, depth - 1)
    )
  )
}

/**
 * Annotation-less source InputStream methods are only a reconciliation aid for
 * already-normalized entries.  Keeping them out of the full depth-3 closure
 * avoids treating every utility/parser InputStream method in a large database
 * as a framework root.  Same-callable and one uniquely resolved hop cover the
 * approved fallback; deeper paths remain explicit partial coverage gaps.
 */
predicate sourceInputStreamCallsWithinOne(Method source, Callable sink) {
  source = sink
  or exists(MethodCall edge, Method target |
    edge.getEnclosingCallable() = source and uniqueSourceTarget(edge, target) and sink = target
  )
  or exists(ClassInstanceExpr edge, Constructor target |
    edge.getEnclosingCallable() = source and constructorCall(edge, target) and sink = target
  )
  or exists(Method target | lexicalLambdaCall(source, target) and sink = target)
}
predicate bodyMaterialization(Method method, Parameter body) {
  frameworkHandler(method) and body = method.getAParameter() and
  exists(Annotation a |
    a = body.getAnAnnotation() and
    a.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody")
  ) and
  (
    body.getType() instanceof Array and body.getType().(Array).getElementType().hasName("byte")
    or body.getType().(RefType).hasQualifiedName("java.lang", "String")
  )
}

predicate associationRow(Method entry, Element site, string target, string sink, string path, string phase, string confidence, string coverage, string note) {
  exists(Expr growth, Callable owner |
    growthSite(growth, owner, target) and
    (
      frameworkHandler(entry) and callsWithin(entry, owner, _)
      or sourceInputStreamHandler(entry) and sourceInputStreamCallsWithinOne(entry, owner)
    ) and site = growth and
    sink = owner.getQualifiedName() and path = entry.getQualifiedName() + ">" + sink and phase = "entry>callgraph>growth" and
    (
      entry = owner and confidence = "proven" and coverage = "complete" and note = "same_handler_registration_association"
      or entry != owner and confidence = "partial" and coverage = "partial" and note = "transitive_callgraph_association_requires_flow_witness"
    )
  )
  or exists(MethodCall growth |
    solrFormPrehandlerAssociation(entry, growth) and site = growth and target = "size" and
    sink = growth.getEnclosingCallable().getQualifiedName() and
    path = entry.getQualifiedName() + ">" + sink and
    phase = "entry>pre_handler_form_parser>growth" and confidence = "partial" and
    coverage = "partial" and note = "solr_form_prehandler_dispatch_requires_path_coverage"
  )
  or exists(MethodCall growth |
    jmqttQos2Dispatch(entry, growth) and site = growth and target = "key" and
    sink = growth.getEnclosingCallable().getQualifiedName() and
    path = entry.getQualifiedName() + ">" + sink and
    phase = "entry>mqtt_decode>async_processor>publish_qos2>growth" and
    confidence = "partial" and coverage = "partial" and
    note = "jmqtt_async_processor_qos2_dispatch_requires_path_coverage"
  )
  or exists(MethodCall growth |
    citrusAuthenticationPrehandler(entry, growth) and site = growth and target = "size" and
    sink = growth.getEnclosingCallable().getQualifiedName() and
    path = entry.getQualifiedName() + ">component_filter>" + sink and
    phase = "entry>component_filter>request_wrapper>growth" and
    confidence = "partial" and coverage = "partial" and
    note = "citrus_component_request_wrapper_prehandler_requires_path_coverage"
  )
  or exists(MethodCall growth |
    citrusVerificationSessionDispatch(entry, growth) and site = growth and target = "value" and
    sink = growth.getEnclosingCallable().getQualifiedName() and
    path = entry.getQualifiedName() + ">verification_processor>repository>" + sink and
    phase = "entry>verification_processor>session_repository>growth" and
    confidence = "partial" and coverage = "partial" and
    note = "citrus_verification_session_dispatch_requires_path_coverage"
  )
  or exists(Parameter body | bodyMaterialization(entry, body) and site = body and target = "size" and sink = entry.getQualifiedName() and path = entry.getQualifiedName() and phase = "entry>materialization" and confidence = "proven" and coverage = "complete" and note = "same_handler_request_body_materialization")
  or exists(Expr growth, Callable owner, Method serviceTarget, string route |
    frameworkHandler(entry) and nettyJsonSwitchDispatch(entry, entry.getParameter(1), route, serviceTarget) and
    growthSite(growth, owner, target) and callsWithin(serviceTarget, owner, _) and
    site = growth and sink = owner.getQualifiedName() and
    path = entry.getQualifiedName() + "[" + route + "]>" + serviceTarget.getQualifiedName() + ">" + sink and
    phase = "entry>netty_json_switch>async>service>growth" and
    confidence = "partial" and coverage = "partial" and
    note = "netty_json_switch_async_dispatch_requires_path_coverage"
  )
}
from Method entry, Element site, string target, string sink, string path, string phase, string confidence, string coverage, string note
where associationRow(entry, site, target, sink, path, phase, confidence, coverage, note)
select entry.getLocation().getFile().getRelativePath() as source_file,
       entry.getLocation().getStartLine() as source_start_line,
       site.getLocation().getFile().getRelativePath() as sink_file,
       site.getLocation().getStartLine() as sink_start_line,
       target as attacker_target,
       entry.getQualifiedName() as attacker_source,
       sink as attacker_sink,
       path as call_path,
       phase as phase_sequence,
       "data_flow" as flow_kind,
       confidence,
       coverage as coverage_status,
       note as coverage_note
