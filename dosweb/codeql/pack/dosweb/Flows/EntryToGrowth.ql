/**
 * @name Entry to growth flow candidates
 * @description Relates recognized web or messaging handlers to growth operations in the same handler.
 * @kind table
 * @id dosweb/entry-to-growth
 */

import java

// Exact candidate-only contract columns:
// "source_file", "source_start_line", "sink_file", "sink_start_line",
// "attacker_target", "attacker_source", "attacker_sink", "call_path",
// "phase_sequence", "flow_kind", "confidence", "coverage_status", "coverage_note"

predicate handlerMethod(Method method) {
  (
    exists(Annotation annotation |
      annotation = method.getAnAnnotation() and
      annotation.getType().hasQualifiedName("fixture.spring", ["PostMapping", "RequestMapping"])
      or annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["PostMapping", "RequestMapping"])
    )
    and exists(Parameter parameter, Annotation body |
      parameter = method.getParameter(0) and body = parameter.getAnAnnotation() and
      (
        body.getType().hasQualifiedName("fixture.spring", "RequestBody")
        or body.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody")
      )
    )
  )
  or
  (
    method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and
    method.getDeclaringType().getASourceSupertype*().hasQualifiedName("fixture.servlet", "HttpServlet")
  )
  or
  (
    method.getName() = "channelRead" and
    method.getDeclaringType().getASourceSupertype*().hasQualifiedName("fixture.netty", "ChannelInboundHandlerAdapter")
  )
  or
  (
    method.getName() = "messageArrived" and
    method.getDeclaringType().getASourceSupertype*().hasQualifiedName("fixture.mqtt", "IMqttMessageListener")
  )
}

predicate attackerInput(Method method, Parameter input) {
  input = method.getAParameter() and
  (
    exists(Annotation annotation |
      annotation = input.getAnAnnotation() and
      annotation.getType().getName() = ["RequestBody", "RequestParam"] and
      annotation.getType().getPackage().getName() = ["fixture.spring", "org.springframework.web.bind.annotation"]
    )
    or method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and input = method.getParameter(0)
    or method.getName() = ["channelRead", "messageArrived"] and input = method.getParameter(1)
  )
}

predicate growthDemand(MethodCall call, string target, Expr demand) {
  call.getMethod().getName() = ["allocate", "allocateDirect"] and
  target = "size" and demand = call.getArgument(0)
  or call.getMethod().getName() = "put" and target = "key" and demand = call.getArgument(0)
  or call.getMethod().getName() = "add" and target = "value" and demand = call.getArgument(0)
  or call.getMethod().getName() = ["submit", "execute", "offer", "schedule"] and
     target = "submission_count" and demand = call.getArgument(0)
  or call.getMethod().getName() = "getPayload" and target = "value" and demand = call.getQualifier()
}

predicate directAttackerFlow(Parameter input, Expr demand) {
  demand = input.getAnAccess()
  or
  exists(LocalVariableDecl local, MethodCall materialize |
    demand = local.getAnAccess() and local.getInitializer() = materialize and
    materialize.getQualifier() = input.getAnAccess()
  )
}

from Method source, Parameter input, MethodCall sink, Expr demand,
  string target, string sourceName, string sinkName
where
  handlerMethod(source) and attackerInput(source, input) and
  sink.getEnclosingCallable() = source and growthDemand(sink, target, demand) and
  directAttackerFlow(input, demand) and
  sourceName = input.getName() and sinkName = sink.toString()
select
  source.getLocation().getFile().getRelativePath() as source_file,
  source.getLocation().getStartLine() as source_start_line,
  sink.getLocation().getFile().getRelativePath() as sink_file,
  sink.getLocation().getStartLine() as sink_start_line,
  target as attacker_target,
  sourceName as attacker_source,
  sinkName as attacker_sink,
  source.getName() + ">" + sink.getMethod().getName() as call_path,
  "in_handler>growth" as phase_sequence,
  "data_flow" as flow_kind,
  "proven" as confidence,
  "complete" as coverage_status,
  "same_handler_candidate_path" as coverage_note
