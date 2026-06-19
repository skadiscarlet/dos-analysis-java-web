/**
 * @name Phase 3 OAuth Candidate Features
 * @description OAuth provider retained-state candidate extraction for Java Web client-state retention DoS.
 * @kind table
 * @id java/web-dos-phase3-oauth-candidate-features
 */

import java
import lib.CommonDoS
import lib.OAuthRetention

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

string entryFqn(OAuthRequestTokenEntry entry) {
  result = entry.getDeclaringType().getQualifiedName() + "." + entry.getName()
}

string sinkId(OAuthRequestTokenMapPut sink) {
  result = fileOf(sink) + ":" + lineOf(sink).toString() + ":" +
    sink.getMethod().getDeclaringType().getQualifiedName() + "." + sink.getMethod().getName()
}

string staticTokenMapProof(OAuthRequestTokenMapPut sink) {
  result = "static_field:" + sink.getEnclosingCallable().getDeclaringType().getQualifiedName() +
    ".requestTokenByTokenString"
}

from OAuthRequestTokenEntry entry, OAuthProviderNewRequestTokenCall bridge,
  OAuthRequestTokenMapPut sink, string call_path,
  string axis_r, string axis_v, string axis_m, string axis_c, string axis_l
where
  oauthRequestTokenFlow(entry, bridge, sink, call_path) and
  axis_r = "WeakGated" and
  axis_v = "Unlimited" and
  axis_m = "Amplifiable" and
  axis_c = axisC(sink.getEnclosingCallable()) and
  axis_l = "ProcessLifetime"
select
  "jersey" as framework,
  entryFqn(entry) as entry_fqn,
  fileOf(entry) as entry_file,
  lineOf(entry) as entry_line,
  "container_put" as sink_kind,
  fileOf(sink) as sink_file,
  lineOf(sink) as sink_line,
  "server_generated_per_request" as key_kind,
  "static_container" as container_kind,
  axis_r,
  axis_v,
  axis_m,
  axis_c,
  axis_l,
  drdVerdict(axis_v, axis_c, axis_l) as verdict_drd,
  exploitVerdict5(axis_r, axis_v, axis_m, axis_c, axis_l) as verdict,
  staticTokenMapProof(sink) as evidence,
  sinkId(sink) as sink_id,
  sink.getMethod().getDeclaringType().getQualifiedName() + "." + sink.getMethod().getName() as sink_fqn,
  "retained_map_put" as sink_shape,
  "token_cardinality" as growth_dimension,
  "request_token_key" as growth_driver_kind,
  sink.getGrowthDriver().toString() as growth_driver_expr,
  "0" as growth_driver_index,
  sink.getReceiverExpr().toString() as receiver_expr,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() as lifecycle_root,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() as retained_object,
  "requestTokenByTokenString" as retained_field,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + ".requestTokenByTokenString" as retention_path,
  staticTokenMapProof(sink) as receiver_proof,
  "static_field" as proof_source,
  "high" as proof_confidence,
  staticTokenMapProof(sink) as proof_evidence,
  "provider_field" as request_flow_kind,
  "provider_field:" + entryFqn(entry) + " -> " + bridge.getMethod().getName() +
    " -> requestTokenByTokenString.put" as request_flow_proof,
  call_path,
  "3" as call_path_depth,
  "jaxrs_request_context" as request_carrier_kind,
  "oauth_request_parameters" as source_kind,
  "OAuthServerRequest.getParameterNames/getParameterValues" as source_expr,
  "provider_state" as candidate_family,
  "oauth1_server_feature_enabled;valid_oauth_consumer_signature" as deployment_condition,
  "no request-token map quota modeled" as capacity_hint,
  "" as demotion_reason,
  oauthRequestTokenDebugNotes(entry, bridge, sink) as debug_notes
