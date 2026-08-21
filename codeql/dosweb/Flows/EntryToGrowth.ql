/**
 * @name Entry to growth data flow
 * @description Proves attacker input flow from real framework handlers to a growth demand.
 * @kind table
 * @id dosweb/entry-to-growth
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

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
}

predicate attackerInput(Method method, Parameter input) {
  input = method.getAParameter() and handlerMethod(method) and
  (
    exists(Annotation annotation |
      annotation = input.getAnAnnotation() and annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestBody", "RequestParam", "PathVariable", "RequestHeader"])
    )
    or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch", "doFilter"] and input = method.getParameter(0)
    or method.getName() = ["channelRead", "channelRead0", "messageArrived"] and input = method.getParameter(1)
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
    annotation = input.getAnAnnotation() and annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody") and
    input.getType() instanceof Array and input.getType().(Array).getElementType().hasName("byte")
  )
}

/** Results of supported Servlet request accessors are attacker-controlled values. */
predicate servletDerivedInput(Method method, Parameter input, MethodCall derived) {
  attackerInput(method, input) and method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch", "doFilter"] and
  derived.getEnclosingCallable() = method and
  derived.getMethod().getName() = ["body", "getParameter", "getParameterValues", "getInputStream", "getReader", "getPart", "getParts", "getRequestURI"] and
  derived.getQualifier().(VarAccess).getVariable() = input
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
  predicate isSink(DataFlow::Node sink) { exists(Expr site, string target, Expr demand | growthDemand(site, target, demand) and sink.asExpr() = demand) }
  predicate isAdditionalFlowStep(DataFlow::Node pred, DataFlow::Node succ) {
    exists(MethodCall call, Method target, int index |
      uniqueSourceTarget(call, target) and pred.asExpr() = call.getArgument(index) and
      succ.asParameter() = target.getParameter(index)
    )
  }
}
module EntryToGrowthFlow = TaintTracking::Global<EntryToGrowthConfig>;

/** Resolve only concrete direct calls or one unique source-defined implementation. */
predicate uniqueSourceTarget(MethodCall edge, Method target) {
  target = edge.getMethod() and target.fromSource() and not target.isAbstract()
  or target.fromSource() and not target.isAbstract() and target.overrides(edge.getMethod()) and
    not exists(Method other |
      other != target and other.fromSource() and not other.isAbstract() and other.overrides(edge.getMethod())
    )
}

/** Bounded source-defined call graph witness. Any cross-call witness is partial. */
predicate callsWithin(Method source, Method sink, int depth) {
  depth in [0..3] and (
    source = sink and depth = 0
    or exists(MethodCall edge, Method middle |
      edge.getEnclosingCallable() = source and uniqueSourceTarget(edge, middle) and
      callsWithin(middle, sink, depth - 1)
    )
  )
}

predicate flowRow(Method source, Parameter input, Element sinkSite, string target, string sinkText,
                  string path, string phase, string confidence, string coverage, string note) {
  exists(DataFlow::Node sourceNode, DataFlow::Node sinkNode, Expr sink, Expr demand |
    EntryToGrowthFlow::flow(sourceNode, sinkNode) and attackerSourceNode(source, input, sourceNode) and
    growthDemand(sink, target, demand) and sinkNode.asExpr() = demand and callsWithin(source, sink.getEnclosingCallable(), _) and
    sinkSite = sink and sinkText = demand.toString() and
    (
      source = sink.getEnclosingCallable() and path = source.getQualifiedName() + ">" + sink.getEnclosingCallable().getQualifiedName() and
      phase = "entry>global_dataflow>growth" and confidence = "proven" and coverage = "complete" and note = "same_handler_global_dataflow"
      or
      source != sink.getEnclosingCallable() and path = source.getQualifiedName() + ">" + sink.getEnclosingCallable().getQualifiedName() and
      phase = "entry>global_dataflow>growth" and confidence = "partial" and coverage = "partial" and note = "transitive_callgraph_witness_requires_path_coverage"
    )
  )
  or materializationParameter(source, input) and sinkSite = input and target = "size" and sinkText = input.getName() and
     path = source.getQualifiedName() and phase = "entry>materialization" and confidence = "proven" and coverage = "complete" and note = "request_body_parameter_materialization"
}

from Method source, Parameter input, Element sinkSite, string target, string sinkText, string path, string phase, string confidence, string coverage, string note
where flowRow(source, input, sinkSite, target, sinkText, path, phase, confidence, coverage, note)
select source.getLocation().getFile().getRelativePath() as source_file,
  source.getLocation().getStartLine() as source_start_line,
  sinkSite.getLocation().getFile().getRelativePath() as sink_file,
  sinkSite.getLocation().getStartLine() as sink_start_line,
  target as attacker_target, input.getName() as attacker_source, sinkText as attacker_sink,
  path as call_path, phase as phase_sequence, "data_flow" as flow_kind,
  confidence, coverage as coverage_status, note as coverage_note
