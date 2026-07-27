/**
 * @name Input materialization growth candidates
 * @description Screens recognized request-body and MQTT payload materialization without claiming verified growth.
 * @kind table
 * @id dosweb/input-materialization-growth
 */

import java

// Exact Task 3 contract:
// "site_file", "site_start_line", "growth_kind", "operation",
// "resource_dimension", "receiver", "field_path", "demand_input_name",
// "demand_input_role", "escape_scope", "candidate_evidence",
// "coverage_status", "coverage_note"

predicate isRequestBodyAnnotation(Annotation annotation) {
  annotation.getType().hasQualifiedName("fixture.spring", "RequestBody")
  or
  annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody")
}

predicate materializationRow(
  Element site, string operation, string receiver, string fieldPath,
  string demandName, string evidence, string note
) {
  exists(MethodCall call |
    site = call and
    call.getMethod().getName() = "getPayload" and
    (
      call.getMethod().getDeclaringType().hasQualifiedName("fixture.mqtt", "MqttMessage")
      or
      call.getMethod().getDeclaringType().hasQualifiedName("org.eclipse.paho.client.mqttv3", "MqttMessage")
    ) and
    operation = call.getMethod().getDeclaringType().getQualifiedName() + ".getPayload" and
    receiver = call.getQualifier().toString() and fieldPath = receiver and
    demandName = receiver and evidence = "mqtt_payload_materialization" and
    note = "recognized_mqtt_payload_api"
  )
  or
  exists(Parameter parameter, Annotation annotation |
    site = parameter and
    annotation = parameter.getAnAnnotation() and
    isRequestBodyAnnotation(annotation) and
    parameter.getType() instanceof Array and
    parameter.getType().(Array).getElementType().hasName("byte") and
    operation = "spring_request_body_materialization" and
    receiver = parameter.getCallable().getDeclaringType().getQualifiedName() + "." + parameter.getCallable().getName() and
    fieldPath = parameter.getName() and demandName = parameter.getName() and
    evidence = "spring_request_body_parameter" and
    note = "recognized_spring_request_body_bytes"
  )
}

from Element site, string operation, string receiver, string fieldPath,
  string demandName, string evidence, string note
where
  materializationRow(site, operation, receiver, fieldPath, demandName, evidence, note)
select
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  "input_materialization" as growth_kind,
  operation,
  "bytes" as resource_dimension,
  receiver,
  fieldPath as field_path,
  demandName as demand_input_name,
  "value" as demand_input_role,
  "request" as escape_scope,
  evidence as candidate_evidence,
  "complete" as coverage_status,
  note as coverage_note
