/**
 * @name Phase 3 Undertow MCMP Candidate Features
 * @description Undertow MCMP management candidate extraction for Java Web client-state retention DoS.
 * @kind table
 * @id java/web-dos-phase3-undertow-mcmp-candidate-features
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

string mcmpSinkId(MCMPRegistryPut sink) {
  result = fileOf(sink) + ":" + lineOf(sink).toString() + ":mcmp." +
    sink.getRetainedFieldName() + ".put"
}

from MCMPEntry entry, MCMPContainerAddNodeCall bridge, MCMPRegistryPut sink, string call_path,
  string axis_r, string axis_v, string axis_m, string axis_c, string axis_l
where
  mcmpAddNodeFlow(entry, bridge, sink, call_path) and
  axis_r = "WeakGated" and
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
  "framework_registry" as container_kind,
  axis_r,
  axis_v,
  axis_m,
  axis_c,
  axis_l,
  drdVerdict(axis_v, axis_c, axis_l) as verdict_drd,
  exploitVerdict5(axis_r, axis_v, axis_m, axis_c, axis_l) as verdict,
  "framework_registry:ModClusterContainer." + sink.getRetainedFieldName() as evidence,
  mcmpSinkId(sink) as sink_id,
  sink.getMethod().getDeclaringType().getQualifiedName() + "." + sink.getMethod().getName() as sink_fqn,
  "registry_register" as sink_shape,
  sink.getGrowthDimension() as growth_dimension,
  "registry_key" as growth_driver_kind,
  sink.getGrowthDriver().toString() as growth_driver_expr,
  "0" as growth_driver_index,
  sink.getReceiverExpr().toString() as receiver_expr,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() as lifecycle_root,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() as retained_object,
  sink.getRetainedFieldName() as retained_field,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + "." +
    sink.getRetainedFieldName() as retention_path,
  "framework_registry:" + sink.getEnclosingCallable().getDeclaringType().getQualifiedName() +
    "." + sink.getRetainedFieldName() as receiver_proof,
  "framework_lifecycle" as proof_source,
  "high" as proof_confidence,
  "MCMPHandler.processConfig -> ModClusterContainer.addNode -> " +
    sink.getRetainedFieldName() + ".put" as proof_evidence,
  "bounded_call_path" as request_flow_kind,
  "bounded_call_path:parseFormData(exchange) -> processConfig -> container.addNode -> " +
    sink.getRetainedFieldName() + ".put" as request_flow_proof,
  call_path,
  "4" as call_path_depth,
  "undertow_exchange" as request_carrier_kind,
  "mcmp_form_data" as source_kind,
  "RequestData from parseFormData(exchange)" as source_expr,
  "management_state" as candidate_family,
  "mcmp_management_endpoint_exposed" as deployment_condition,
  "no node/balancer registry quota modeled" as capacity_hint,
  "" as demotion_reason,
  mcmpDebugNotes(entry, bridge, sink) as debug_notes
