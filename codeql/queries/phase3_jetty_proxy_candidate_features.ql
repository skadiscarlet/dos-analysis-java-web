/**
 * @name Phase 3 Jetty Proxy Candidate Features
 * @description Jetty ProxyServlet client destination candidate extraction for Java Web client-state retention DoS.
 * @kind table
 * @id java/web-dos-phase3-jetty-proxy-candidate-features
 */

import java
import lib.CommonDoS
import lib.JettyRetention

string fileOf(Element element) {
  exists(Location location |
    location = element.getLocation() and
    result = location.getFile().getRelativePath()
  )
  or
  not exists(Location location | element.getLocation() = location) and
  result = "<unknown>"
}

int lineOf(Element element) {
  exists(Location location |
    location = element.getLocation() and
    result = location.getStartLine()
  )
  or
  not exists(Location location | element.getLocation() = location) and
  result = 0
}

string callableFqn(Callable callable) {
  result = callable.getDeclaringType().getQualifiedName() + "." + callable.getName()
}

string jettyProxySinkId(JettyDestinationCompute sink) {
  result = fileOf(sink) + ":" + lineOf(sink).toString() + ":jetty.httpclient.destinations.compute"
}

string jettyDestinationProof(JettyDestinationCompute sink) {
  result = "servlet_field:org.eclipse.jetty.proxy.AbstractProxyServlet._client -> " +
    sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + ".destinations"
}

from JettyProxyEntry entry, JettyProxyNewRequestCall newRequest, JettyProxySendCall send,
  JettyDestinationCompute sink, string call_path,
  string axis_r, string axis_v, string axis_m, string axis_c, string axis_l
where
  jettyProxyDestinationFlow(entry, newRequest, send, sink, call_path) and
  axis_r = "Open" and
  axis_v = "Unlimited" and
  axis_m = "Amplifiable" and
  axis_c = "Unbounded" and
  axis_l = "ProcessLifetime"
select
  "jetty" as framework,
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
  jettyDestinationProof(sink) as evidence,
  jettyProxySinkId(sink) as sink_id,
  sink.getMethod().getDeclaringType().getQualifiedName() + "." + sink.getMethod().getName() as sink_fqn,
  "retained_map_compute" as sink_shape,
  "destination_count" as growth_dimension,
  "origin_key" as growth_driver_kind,
  sink.getGrowthDriver().toString() as growth_driver_expr,
  "0" as growth_driver_index,
  sink.getReceiverExpr().toString() as receiver_expr,
  "org.eclipse.jetty.proxy.AbstractProxyServlet._client" as lifecycle_root,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() as retained_object,
  "destinations" as retained_field,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + ".destinations" as retention_path,
  jettyDestinationProof(sink) as receiver_proof,
  "servlet_field" as proof_source,
  "high" as proof_confidence,
  jettyDestinationProof(sink) as proof_evidence,
  "client_request_flow" as request_flow_kind,
  "client_request_flow:HttpServletRequest target/tag/host -> ProxyServlet newProxyRequest -> " +
    "HttpClient.resolveDestination -> destinations.compute" as request_flow_proof,
  call_path,
  "5" as call_path_depth,
  "servlet_request" as request_carrier_kind,
  "proxy_target_or_request_tag" as source_kind,
  "HttpServletRequest rewriteTarget / Request.tag / Origin host" as source_expr,
  "client_destination" as candidate_family,
  "proxy_servlet_deployed" as deployment_condition,
  "no destination map quota modeled; idle destination removal disabled by default" as capacity_hint,
  "" as demotion_reason,
  jettyProxyDebugNotes(entry, newRequest, send, sink) as debug_notes
