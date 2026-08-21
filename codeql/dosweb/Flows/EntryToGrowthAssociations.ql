/**
 * @name Entry to growth call-graph associations
 * @description Conservative source-defined entry associations; cross-call links remain partial.
 * @kind table
 * @id dosweb/entry-to-growth-associations
 */
import java

predicate handler(Method method) {
  exists(Annotation a | a = method.getAnAnnotation() and a.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping"]))
  or exists(Annotation a | a = method.getAnAnnotation() and a.getType().hasQualifiedName("javax.ws.rs", ["GET", "POST", "PUT", "DELETE", "PATCH", "Path"]))
  or exists(Annotation a | a = method.getAnAnnotation() and a.getType().hasQualifiedName("jakarta.ws.rs", ["GET", "POST", "PUT", "DELETE", "PATCH", "Path"]))
  or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and (method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet.http", "HttpServlet") or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServlet"))
  or method.getName() = "doFilter" and (method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet", "Filter") or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet", "Filter"))
  or method.getName() = ["channelRead", "channelRead0"] and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("io.netty.channel", ["ChannelInboundHandlerAdapter", "SimpleChannelInboundHandler"])
  or method.getName() = "messageArrived" and method.getDeclaringType().getASourceSupertype*().hasQualifiedName("org.eclipse.paho.client.mqttv3", "IMqttMessageListener")
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
  or exists(ArrayCreationExpr allocation | site = allocation and owner = allocation.getEnclosingCallable() and target = "size")
  or exists(ClassInstanceExpr allocation |
    site = allocation and owner = allocation.getEnclosingCallable() and
    (
      allocation.getConstructedType().hasQualifiedName("java.awt.image", "BufferedImage")
      or allocation.getConstructedType().hasQualifiedName("com.wf.captcha", "SpecCaptcha")
    ) and target = "size"
  )
}
// Resolve only a concrete source-defined direct target or the one unique
// source-defined implementation of an abstract/interface call. Multiple
// implementations, reflection and unresolved dispatch intentionally yield no edge.
predicate uniqueSourceTarget(MethodCall edge, Method target) {
  target = edge.getMethod() and target.fromSource() and not target.isAbstract()
  or target.fromSource() and not target.isAbstract() and target.overrides(edge.getMethod()) and
    not exists(Method other |
      other != target and other.fromSource() and not other.isAbstract() and other.overrides(edge.getMethod())
    )
}

// Bounded transitive call reachability: at most depth 3 source-defined hops.  Deeper,
// reflection, or ambiguous dispatch is not a provable association and must not be
// emitted, which also bounds cardinality on large handlers.
predicate callsWithin(Method source, Method sink, int depth) {
  depth in [0..3] and (
    source = sink and depth = 0
    or exists(MethodCall edge, Method middle |
      edge.getEnclosingCallable() = source and uniqueSourceTarget(edge, middle) and
      callsWithin(middle, sink, depth - 1)
    )
  )
}
predicate bodyMaterialization(Method method, Parameter body) {
  handler(method) and body = method.getAParameter() and exists(Annotation a | a = body.getAnAnnotation() and a.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody") and body.getType() instanceof Array and body.getType().(Array).getElementType().hasName("byte"))
}

predicate associationRow(Method entry, Element site, string target, string sink, string path, string phase, string confidence, string coverage, string note) {
  exists(Expr growth, Callable owner |
    handler(entry) and growthSite(growth, owner, target) and owner instanceof Method and callsWithin(entry, owner.(Method), _) and site = growth and
    sink = owner.getQualifiedName() and path = entry.getQualifiedName() + ">" + sink and phase = "entry>callgraph>growth" and
    (
      entry = owner and confidence = "proven" and coverage = "complete" and note = "same_handler_registration_association"
      or entry != owner and confidence = "partial" and coverage = "partial" and note = "transitive_callgraph_association_requires_flow_witness"
    )
  )
  or exists(Parameter body | bodyMaterialization(entry, body) and site = body and target = "size" and sink = entry.getQualifiedName() and path = entry.getQualifiedName() and phase = "entry>materialization" and confidence = "proven" and coverage = "complete" and note = "same_handler_request_body_materialization")
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
