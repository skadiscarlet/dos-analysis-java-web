/**
 * @name Lifecycle modeled-domain coverage
 * @description Explicit growth-anchor/family coverage. Candidate absence is usable only for a complete row.
 * @kind table
 * @id dosweb/lifecycle-coverage
 */

import java
import FiniteQueueDomain

predicate springRequestBodyMaterialization(Parameter parameter) {
  parameter.getType() instanceof Array and
  parameter.getType().(Array).getElementType().hasName("byte") and
  exists(Annotation annotation |
    annotation = parameter.getAnAnnotation() and
    annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody")
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
}

predicate callsWithin(Method source, Method sink, int depth) {
  depth in [0..3] and (
    source = sink and depth = 0
    or exists(MethodCall edge, Method middle |
      edge.getEnclosingCallable() = source and middle = edge.getMethod() and middle.fromSource() and
      callsWithin(middle, sink, depth - 1)
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
}

Callable growthCallable(Element growth) {
  exists(Expr expression | growth = expression and result = expression.getEnclosingCallable())
  or exists(Parameter parameter | growth = parameter and result = parameter.getCallable())
}

predicate entryReachableGrowth(Element growth) {
  exists(Method entry, Callable owner, int depth |
    handler(entry) and owner = growthCallable(growth) and owner instanceof Method and callsWithin(entry, owner.(Method), depth)
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
    inner.getEnclosingCallable() = middle and nested = inner.getMethod() and nested.fromSource()
  )
}

predicate unresolvedFiniteQueueOffer(Element growth) {
  exists(MethodCall call, Field field |
    growth = call and call.getMethod().getName() = "offer" and
    field = queueReceiverField(call) and finiteFieldQueueType(field) and
    not exists(string capacity | capacity = finiteFieldQueueCapacity(field))
  )
}

from Element growth, string familyValue, string statusValue, string noteValue
where
  modeledGrowth(growth) and entryReachableGrowth(growth) and familyValue = ["guard", "bound", "release"] and
  (
    (reflectiveLifecycleDispatch(growth) or unmodeledLifecycleDispatch(growth, familyValue)) and
    statusValue = "partial" and noteValue = "reflection_or_custom_dispatch_not_modeled"
    or
    familyValue = "bound" and unresolvedFiniteQueueOffer(growth) and
    statusValue = "partial" and noteValue = "finite_queue_capacity_not_statically_attested"
    or
    not reflectiveLifecycleDispatch(growth) and not unmodeledLifecycleDispatch(growth, familyValue) and
    not (familyValue = "bound" and unresolvedFiniteQueueOffer(growth)) and
    statusValue = "complete" and noteValue = "same_callable_modeled_domain_scanned"
  )
select
  growth.getLocation().getFile().getRelativePath() as anchor_file,
  growth.getLocation().getStartLine() as anchor_start_line,
  familyValue as family,
  statusValue as coverage_status,
  noteValue as coverage_note
