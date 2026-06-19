/**
 * @name Phase 3 Undertow LearningPush Candidate Features
 * @description Undertow LearningPush callback candidate extraction for Java Web client-state retention DoS.
 * @kind table
 * @id java/web-dos-phase3-undertow-learning-push-candidate-features
 */

import java
import lib.CommonDoS
import lib.UndertowRetention

string fileOf(Element element) {
  exists(Location location |
    location = element.getLocation() and
    result = location.getFile().getRelativePath()
  )
  or
  not exists(Location location | location = element.getLocation()) and
  result = "<unknown>"
}

int lineOf(Element element) {
  exists(Location location |
    location = element.getLocation() and
    result = location.getStartLine()
  )
  or
  not exists(Location location | location = element.getLocation()) and
  result = 0
}

string callableFqn(Callable callable) {
  result = callable.getDeclaringType().getQualifiedName() + "." + callable.getName()
}

string learningPushSinkId(LearningPushMapPut sink) {
  result = fileOf(sink) + ":" + lineOf(sink).toString() + ":learning_push.pushes.put"
}

from LearningPushEntry entry, LearningPushMapPut sink, string call_path,
  string axis_r, string axis_v, string axis_m, string axis_c, string axis_l
where
  learningPushFlow(entry, sink, call_path) and
  axis_r = "Open" and
  axis_v = "Unlimited" and
  axis_m = "Amplifiable" and
  axis_c = "Unbounded" and
  axis_l = "ProcessLifetime"
select
  "undertow" as framework,
  callableFqn(entry) as entry_fqn,
  fileOf(entry) as entry_file,
  lineOf(entry) as entry_line,
  "container_put" as sink_kind,
  fileOf(sink) as sink_file,
  lineOf(sink) as sink_line,
  "request_derived" as key_kind,
  "lifecycle_field_container" as container_kind,
  axis_r,
  axis_v,
  axis_m,
  axis_c,
  axis_l,
  drdVerdict(axis_v, axis_c, axis_l) as verdict_drd,
  exploitVerdict5(axis_r, axis_v, axis_m, axis_c, axis_l) as verdict,
  "handler_field:LearningPushHandler.cache[referer].pushes" as evidence,
  learningPushSinkId(sink) as sink_id,
  sink.getMethod().getDeclaringType().getQualifiedName() + "." + sink.getMethod().getName() as sink_fqn,
  "nested_retained_map_put" as sink_shape,
  "key_cardinality" as growth_dimension,
  "nested_map_key" as growth_driver_kind,
  sink.getGrowthDriver().toString() as growth_driver_expr,
  "0" as growth_driver_index,
  sink.getReceiverExpr().toString() as receiver_expr,
  entry.getDeclaringType().getQualifiedName() as lifecycle_root,
  entry.getDeclaringType().getQualifiedName() as retained_object,
  "cache" as retained_field,
  entry.getDeclaringType().getQualifiedName() + ".cache.*" as retention_path,
  "handler_field:" + entry.getDeclaringType().getQualifiedName() + ".cache" as receiver_proof,
  "handler_field" as proof_source,
  "high" as proof_confidence,
  "handler_field:LearningPushHandler.cache -> pushes" as proof_evidence,
  "listener_callback" as request_flow_kind,
  "listener_callback:exchange request path/referer -> PushCompletionListener -> pushes.put" as request_flow_proof,
  call_path,
  "3" as call_path_depth,
  "undertow_exchange" as request_carrier_kind,
  "request_header_and_path" as source_kind,
  "referer/fullPath/requestPath from HttpServerExchange" as source_expr,
  "listener_state" as candidate_family,
  "learning_push_handler_enabled" as deployment_condition,
  "outer LRUCache bounded; inner per-referer map unbounded" as capacity_hint,
  "" as demotion_reason,
  learningPushDebugNotes(entry, sink) as debug_notes
