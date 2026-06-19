/**
 * @name Phase 3 Parser Candidate Features
 * @description Parser/body candidate feature extraction for Java Web client-state retention DoS.
 * @kind table
 * @id java/web-dos-phase3-parser-candidate-features
 */

import java
import lib.CommonDoS
import lib.ParserRetention

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

string entryFqn(MultipartReaderEntry entry) {
  result = entry.getDeclaringType().getQualifiedName() + "." + entry.getName()
}

string sinkId(MultipartBodyPartAdd sink) {
  result = fileOf(sink) + ":" + lineOf(sink).toString() + ":" +
    sink.getMethod().getDeclaringType().getQualifiedName() + "." + sink.getMethod().getName()
}

from MultipartReaderEntry entry, MultipartBodyPartAdd sink, string call_path, string call_path_depth,
  string axis_r, string axis_v, string axis_m, string axis_c, string axis_l
where
  multipartReadFlow(entry, sink, call_path, call_path_depth) and
  axis_r = "Open" and
  axis_v = "Stream" and
  axis_m = "Amplifiable" and
  axis_c = axisC(sink.getEnclosingCallable()) and
  axis_l = "ProcessLifetime"
select
  "jersey" as framework,
  entryFqn(entry) as entry_fqn,
  fileOf(entry) as entry_file,
  lineOf(entry) as entry_line,
  "container_add" as sink_kind,
  fileOf(sink) as sink_file,
  lineOf(sink) as sink_line,
  "request_derived" as key_kind,
  "parser_transaction" as container_kind,
  axis_r,
  axis_v,
  axis_m,
  axis_c,
  axis_l,
  drdVerdict(axis_v, axis_c, axis_l) as verdict_drd,
  exploitVerdict5(axis_r, axis_v, axis_m, axis_c, axis_l) as verdict,
  "parser_lifetime:" + sink.getReceiverExpr().toString() as evidence,
  sinkId(sink) as sink_id,
  sink.getMethod().getDeclaringType().getQualifiedName() + "." + sink.getMethod().getName() as sink_fqn,
  "parser_part_accumulator" as sink_shape,
  "part_count" as growth_dimension,
  "part_metadata" as growth_driver_kind,
  sink.getGrowthDriver().toString() as growth_driver_expr,
  "0" as growth_driver_index,
  sink.getReceiverExpr().toString() as receiver_expr,
  "parser_transaction" as lifecycle_root,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() as retained_object,
  "<parser_accumulator>" as retained_field,
  sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + "." + sink.getReceiverExpr().toString() as retention_path,
  "parser_lifetime:" + sink.getEnclosingCallable().getDeclaringType().getQualifiedName() as receiver_proof,
  "parser_lifetime" as proof_source,
  "medium" as proof_confidence,
  "parser_lifetime:" + sink.getReceiverExpr().toString() as proof_evidence,
  "parser_body_flow" as request_flow_kind,
  "parser_body_flow:" + entry.getStreamParameter().getName() + " -> " + sink.getGrowthDriver().toString() as request_flow_proof,
  call_path,
  call_path_depth,
  "parser_stream" as request_carrier_kind,
  "stream_param" as source_kind,
  entry.getStreamParameter().getName() + ":" + entry.getStreamParameter().getType().getName() as source_expr,
  "parser_body" as candidate_family,
  "multipart_provider_enabled" as deployment_condition,
  "" as capacity_hint,
  "" as demotion_reason,
  parserDebugNotes(entry, sink) as debug_notes
