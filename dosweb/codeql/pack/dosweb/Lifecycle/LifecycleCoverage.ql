/**
 * @name Lifecycle modeled-domain coverage
 * @description Explicit growth-anchor/family coverage. Candidate absence is usable only for a complete row.
 * @kind table
 * @id dosweb/lifecycle-coverage
 */

import java
import FiniteQueueDomain
import FrameworkLimitDomain

// Bound coverage includes only exact StreamReadConstraints,
// HttpObjectAggregator, MultipartConfig, and formdataUploadLimitInKB domains.

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

predicate springRequestBodyMaterialization(Parameter parameter) {
  exists(Annotation annotation |
    annotation = parameter.getAnAnnotation() and
    annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody")
  ) and
  (
    parameter.getType() instanceof Array and
    parameter.getType().(Array).getElementType().hasName("byte")
    or parameter.getType().(RefType).hasQualifiedName("java.lang", "String")
  )
}

predicate fieldBackedGrowth(MethodCall call) {
  exists(FieldAccess receiver | receiver = call.getQualifier())
  or exists(VarAccess receiver | receiver = call.getQualifier() and receiver.getVariable() instanceof Field)
}

predicate handler(Method method) {
  exists(Annotation a | a = method.getAnAnnotation() and a.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping"]))
  or exists(Annotation a | a = method.getAnAnnotation() and a.getType().hasQualifiedName("javax.ws.rs", ["GET", "POST", "PUT", "DELETE", "PATCH", "Path"]))
  or exists(Annotation a | a = method.getAnAnnotation() and a.getType().hasQualifiedName("jakarta.ws.rs", ["GET", "POST", "PUT", "DELETE", "PATCH", "Path"]))
  or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and (method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet.http", "HttpServlet") or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServlet"))
  or method.getName() = ["channelRead", "channelRead0"] and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("io.netty.channel", ["ChannelInboundHandlerAdapter", "SimpleChannelInboundHandler"])
  or method.getName() = "messageArrived" and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("org.eclipse.paho.client.mqttv3", "IMqttMessageListener")
  or method.getName() = "doFilter" and
    (
      method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet", "Filter")
      or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet", "Filter")
    )
  or exists(Annotation a |
    a = method.getAnAnnotation() and
    (
      a.getType().hasQualifiedName("fixture.armeria", ["Post", "Get"])
      or a.getType().hasQualifiedName("com.linecorp.armeria.server.annotation", ["Post", "Get"])
    )
  )
  or sourceInputStreamHandler(method)
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

predicate callsWithin(Callable source, Callable sink, int depth) {
  depth in [0..3] and (
    source = sink and depth = 0
    or exists(MethodCall edge, Method middle |
      edge.getEnclosingCallable() = source and middle = edge.getMethod() and middle.fromSource() and
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

predicate modeledGrowth(Element growth) {
  exists(MethodCall call |
    growth = call and call.getLocation().getFile().getRelativePath().matches("%.java") and
    (
      call.getMethod().getName() = ["put", "computeIfAbsent", "putIfAbsent", "merge"] and call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util", "Map") and fieldBackedGrowth(call)
      or call.getMethod().getName() = "add" and call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util", "Collection") and fieldBackedGrowth(call)
      or call.getMethod().getName() = ["submit", "execute", "offer", "schedule"] and
        (
          call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "ExecutorService")
          or call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("java.util.concurrent", "BlockingQueue")
        ) and fieldBackedGrowth(call)
      or call.getMethod().getName() = ["allocate", "allocateDirect"] and call.getMethod().getDeclaringType().hasQualifiedName("java.nio", "ByteBuffer")
      or call.getMethod().getName() = "getPayload" and call.getMethod().getDeclaringType().hasQualifiedName("org.eclipse.paho.client.mqttv3", "MqttMessage")
      or readAllMaterialization(call)
      or armeriaAggregation(call)
      or byteArrayOutputCopy(call)
      or httpSessionAttributeWrite(call)
      or exists(MethodCall content, Expr request |
        nettyFullRequestStringMaterialization(call, content, request)
      )
    )
  )
  or exists(ArrayCreationExpr allocation |
    growth = allocation and allocation.getLocation().getFile().getRelativePath().matches("%.java")
  )
  or exists(ClassInstanceExpr allocation |
    growth = allocation and
    (
      allocation.getConstructedType().hasQualifiedName("java.awt.image", "BufferedImage")
      or allocation.getConstructedType().hasQualifiedName("com.wf.captcha", "SpecCaptcha")
    )
  )
  or exists(Parameter parameter | growth = parameter and springRequestBodyMaterialization(parameter))
  or exists(MethodCall append, Parameter request |
    growth = append and servletRequestStringMaterialization(append, request)
  )
}

Callable growthCallable(Element growth) {
  exists(Expr expression | growth = expression and result = expression.getEnclosingCallable())
  or exists(Parameter parameter | growth = parameter and result = parameter.getCallable())
}

predicate entryReachableGrowth(Element growth) {
  exists(Method entry, Callable owner, int depth |
    handler(entry) and owner = growthCallable(growth) and callsWithin(entry, owner, depth)
  )
  or nettyProtocolDispatchGrowth(growth)
}

predicate nettyProtocolDispatchGrowth(Element growth) {
  exists(Method entry, Parameter message, string route, Method serviceTarget, Callable owner |
    handler(entry) and message = entry.getParameter(1) and
    nettyJsonSwitchDispatch(entry, message, route, serviceTarget) and
    owner = growthCallable(growth) and callsWithin(serviceTarget, owner, _)
  )
}

predicate reflectiveLifecycleDispatch(Element growth) {
  exists(MethodCall call |
    call.getEnclosingCallable() = growthCallable(growth) and
    call.getMethod().getName() = ["forName", "getMethod", "getDeclaredMethod", "invoke"]
  )
}

predicate lifecycleShape(Method method, string family) {
  family = "guard" and exists(IfStmt site |
    site.getEnclosingCallable() = method and
    (exists(ReturnStmt terminal | terminal.getParent*() = site.getThen()) or exists(ThrowStmt terminal | terminal.getParent*() = site.getThen()))
  )
  or family = "bound" and exists(MethodCall call | call.getEnclosingCallable() = method and call.getMethod().getName() = "offer")
  or family = "release" and exists(MethodCall call | call.getEnclosingCallable() = method and call.getMethod().getName() = ["remove", "clear", "evict", "close"])
}

predicate unmodeledLifecycleDispatch(Element growth, string family) {
  exists(MethodCall call, Method helper |
    call.getEnclosingCallable() = growthCallable(growth) and helper = call.getMethod() and helper.fromSource() and lifecycleShape(helper, family)
  )
  or
  exists(MethodCall outer, Method middle, MethodCall inner, Method nested |
    family = ["guard", "bound", "release"] and
    outer.getEnclosingCallable() = growthCallable(growth) and middle = outer.getMethod() and middle.fromSource() and
    inner.getEnclosingCallable() = middle and nested = inner.getMethod() and nested.fromSource() and
    lifecycleShape(nested, family)
  )
}

predicate unresolvedFiniteQueueOffer(Element growth) {
  exists(MethodCall call, Field field |
    growth = call and call.getMethod().getName() = "offer" and
    field = queueReceiverField(call) and finiteFieldQueueType(field) and
    not exists(string capacity | capacity = finiteFieldQueueCapacity(field))
  )
}

predicate guardModeledDomain(Element growth) {
  exists(MethodCall call |
    growth = call and
    (
      call.getMethod().getName() = ["put", "add"]
      or call.getMethod().getName() = ["offer", "submit", "execute"]
      or call.getMethod().getName() = ["allocate", "allocateDirect"] and
         call.getMethod().getDeclaringType().hasQualifiedName("java.nio", "ByteBuffer")
      or call.getMethod().getName() = "getPayload" and
         call.getMethod().getDeclaringType().hasQualifiedName(
           "org.eclipse.paho.client.mqttv3", "MqttMessage"
         )
    )
  )
}

predicate boundModeledDomain(Element growth) {
  exists(MethodCall call, Field field |
    growth = call and call.getMethod().getName() = "offer" and
    field = queueReceiverField(call) and finiteFieldQueueType(field)
  )
  or exists(Element site, MethodCall call, string key, string value,
            string encoding, string receiver, string fieldPath, string evidence |
    growth = call and frameworkLimitCandidate(
      site, call, key, value, encoding, receiver, fieldPath, evidence
    )
  )
}

predicate releaseModeledDomain(Element growth) {
  exists(MethodCall call |
    growth = call and call.getMethod().getName() = ["put", "add", "offer", "submit"]
  )
}

predicate familyModeledDomain(Element growth, string family) {
  family = "guard" and guardModeledDomain(growth)
  or family = "bound" and boundModeledDomain(growth)
  or family = "release" and releaseModeledDomain(growth)
}

from Element growth, string familyValue, string statusValue, string noteValue
where
  modeledGrowth(growth) and entryReachableGrowth(growth) and familyValue = ["guard", "bound", "release"] and
  (
    nettyProtocolDispatchGrowth(growth) and
    statusValue = "partial" and noteValue = "netty_async_json_dispatch_lifecycle_unresolved"
    or not nettyProtocolDispatchGrowth(growth) and
    (
      (reflectiveLifecycleDispatch(growth) or unmodeledLifecycleDispatch(growth, familyValue)) and
      statusValue = "partial" and noteValue = "reflection_or_custom_dispatch_not_modeled"
      or
      familyValue = "bound" and unresolvedFiniteQueueOffer(growth) and
      statusValue = "partial" and noteValue = "finite_queue_capacity_not_statically_attested"
      or
      not reflectiveLifecycleDispatch(growth) and
      not unmodeledLifecycleDispatch(growth, familyValue) and
      not familyModeledDomain(growth, familyValue) and
      statusValue = "partial" and noteValue = "lifecycle_family_api_domain_unmodeled"
      or
      not reflectiveLifecycleDispatch(growth) and not unmodeledLifecycleDispatch(growth, familyValue) and
      not (familyValue = "bound" and unresolvedFiniteQueueOffer(growth)) and
      familyModeledDomain(growth, familyValue) and
      statusValue = "complete" and noteValue = "same_callable_modeled_domain_scanned"
    )
  )
select
  growth.getLocation().getFile().getRelativePath() as anchor_file,
  growth.getLocation().getStartLine() as anchor_start_line,
  familyValue as family,
  statusValue as coverage_status,
  noteValue as coverage_note
