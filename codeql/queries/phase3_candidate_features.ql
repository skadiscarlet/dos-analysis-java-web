/**
 * @name Phase 3 Candidate Features
 * @description Unified candidate feature extraction for Java Web client-state retention DoS.
 * @kind table
 * @id java/web-dos-phase3-candidate-features
 */

import java
import lib.CommonDoS
import lib.SessionState

string entryFqn(WebClientStateEntry entry) {
  result = entry.getDeclaringType().getQualifiedName() + "." + entry.getName()
}

string callableFqn(Callable callable) {
  result = callable.getDeclaringType().getQualifiedName() + "." + callable.getName()
}

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

string strongestEntryValueSpace(WebClientStateEntry entry) {
  exists(Parameter p |
    p = entry.getAnAttackerControlledParam() and
    paramValueSpace(p) = "Stream"
  ) and result = "Stream"
  or
  not exists(Parameter p |
    p = entry.getAnAttackerControlledParam() and
    paramValueSpace(p) = "Stream"
  ) and exists(Parameter p |
    p = entry.getAnAttackerControlledParam() and
    paramValueSpace(p) = "Unlimited"
  ) and result = "Unlimited"
  or
  not exists(Parameter p |
    p = entry.getAnAttackerControlledParam() and
    paramValueSpace(p) in ["Stream", "Unlimited"]
  ) and result = "Uncontrollable"
}

string sinkId(WebClientStateWrite write) {
  result = fileOf(write) + ":" + lineOf(write).toString() + ":" +
    write.getMethod().getDeclaringType().getQualifiedName() + "." + write.getMethod().getName()
}

from WebClientStateWrite write, WebClientStateEntry entry,
  string axis_r, string axis_v, string axis_m, string axis_c, string axis_l,
  string request_flow_kind, string request_flow_proof, string call_path,
  string call_path_depth, string request_carrier_kind, string source_kind, string source_expr
where
  entry = write.getWebEntry() and
  flowOutputFields(
    write, request_flow_kind, request_flow_proof, call_path, call_path_depth,
    request_carrier_kind, source_kind, source_expr
  ) and
  axis_r = entry.getReachability() and
  axis_v = axisV(strongestEntryValueSpace(entry), write.getKeyExpr()) and
  axis_m = axisM(write.getKeyExpr()) and
  axis_c = axisC(write.getEnclosingCallable()) and
  axis_l = write.getLifespan()
select
  entry.getFramework() as framework,
  entryFqn(entry) as entry_fqn,
  fileOf(entry) as entry_file,
  lineOf(entry) as entry_line,
  write.getSinkKind() as sink_kind,
  fileOf(write) as sink_file,
  lineOf(write) as sink_line,
  keyKind(write.getKeyExpr()) as key_kind,
  write.getContainerKind() as container_kind,
  axis_r,
  axis_v,
  axis_m,
  axis_c,
  axis_l,
  drdVerdict(axis_v, axis_c, axis_l) as verdict_drd,
  exploitVerdict5(axis_r, axis_v, axis_m, axis_c, axis_l) as verdict,
  write.getEvidence() as evidence,
  sinkId(write) as sink_id,
  callableFqn(write.getMethod()) as sink_fqn,
  write.getSinkShape() as sink_shape,
  write.getGrowthDimension() as growth_dimension,
  write.getGrowthDriverKind() as growth_driver_kind,
  write.getGrowthDriver().toString() as growth_driver_expr,
  "0" as growth_driver_index,
  write.getReceiverExprText() as receiver_expr,
  write.getLifecycleRoot() as lifecycle_root,
  write.getRetainedObject() as retained_object,
  write.getRetainedField() as retained_field,
  write.getRetentionPath() as retention_path,
  write.getReceiverProof() as receiver_proof,
  write.getProofSource() as proof_source,
  write.getProofConfidence() as proof_confidence,
  write.getEvidence() as proof_evidence,
  request_flow_kind,
  request_flow_proof,
  call_path,
  call_path_depth,
  request_carrier_kind,
  source_kind,
  source_expr,
  write.getCandidateFamily() as candidate_family,
  write.getDeploymentCondition() as deployment_condition,
  write.getCapacityHint() as capacity_hint,
  "" as demotion_reason,
  "" as debug_notes
