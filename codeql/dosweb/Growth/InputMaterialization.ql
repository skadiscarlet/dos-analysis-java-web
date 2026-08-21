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
  annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestBody")
}

predicate isArmeriaRequestType(Type type) {
  type.(RefType).getASourceSupertype*().hasQualifiedName("fixture.armeria", "HttpRequest")
  or type.(RefType).getASourceSupertype*().hasQualifiedName("com.linecorp.armeria.common", "HttpRequest")
}

predicate isServletRequestWrapper(RefType type) {
  type.getASupertype*().hasQualifiedName("javax.servlet.http", "HttpServletRequestWrapper") or
  type.getASupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServletRequestWrapper")
}

predicate materializationRow(
  Element site, string operation, string receiver, string fieldPath,
  string demandName, string evidence, string coverage, string note
) {
  exists(MethodCall call |
    site = call and
    call.getMethod().getName() = "getPayload" and
    call.getMethod().getDeclaringType().hasQualifiedName("org.eclipse.paho.client.mqttv3", "MqttMessage") and
    operation = call.getMethod().getDeclaringType().getQualifiedName() + ".getPayload" and
    receiver = call.getQualifier().toString() and fieldPath = receiver and
    demandName = receiver and evidence = "mqtt_payload_materialization" and coverage = "complete" and
    note = "recognized_mqtt_payload_api"
  )
  or
  exists(MethodCall call |
    site = call and
    call.getMethod().getName() = "aggregateWithPooledObjects" and
    isArmeriaRequestType(call.getQualifier().getType()) and
    operation = call.getMethod().getDeclaringType().getQualifiedName() + ".aggregateWithPooledObjects" and
    receiver = call.getQualifier().toString() and fieldPath = receiver and
    demandName = receiver and evidence = "armeria_request_aggregation" and coverage = "complete" and
    note = "recognized_armeria_request_aggregation"
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
    evidence = "spring_request_body_parameter" and coverage = "complete" and
    note = "recognized_spring_request_body_bytes"
  )
  or
  exists(MethodCall call, Expr input |
    site = call and input = call.getArgument(0) and
    (
      call.getMethod().hasQualifiedName("cn.hutool.core.io", "IoUtil", "readBytes")
      or call.getMethod().hasQualifiedName("org.apache.commons.io", "IOUtils", "toByteArray")
      or call.getMethod().hasQualifiedName("org.springframework.util", "StreamUtils", "copyToByteArray")
    ) and
    operation = call.getMethod().getDeclaringType().getQualifiedName() + "." + call.getMethod().getName() and
    receiver = input.toString() and fieldPath = receiver and demandName = receiver and
    evidence = "request_stream_read_all" and coverage = "complete" and
    note = "recognized_read_all_materialization_api"
  )
  or
  exists(MethodCall call |
    site = call and call.getMethod().getName() = "readAllBytes" and
    call.getMethod().getDeclaringType().getASupertype*().hasQualifiedName("java.io", "InputStream") and
    operation = call.getMethod().getDeclaringType().getQualifiedName() + ".readAllBytes" and
    receiver = call.getQualifier().toString() and fieldPath = receiver and demandName = receiver and
    evidence = "request_stream_read_all" and coverage = "complete" and
    note = "recognized_read_all_materialization_api"
  )
  or
  exists(Constructor constructor, Parameter request, MethodCall inputStream, MethodCall read, MethodCall append, WhileStmt loop |
    isServletRequestWrapper(constructor.getDeclaringType()) and
    request = constructor.getAParameter() and
    (request.getType().(RefType).getASupertype*().hasQualifiedName("javax.servlet.http", "HttpServletRequest") or
     request.getType().(RefType).getASupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServletRequest")) and
    inputStream.getEnclosingCallable() = constructor and inputStream.getMethod().getName() = "getInputStream" and
    exists(VarAccess requestAccess |
      requestAccess.getVariable() = request and requestAccess.getParent*() = inputStream.getQualifier()
    ) and
    append.getEnclosingCallable() = constructor and append.getMethod().getName() = "append" and
    append.getQualifier().getType().hasName("StringBuilder") and
    append.getAnEnclosingStmt() = loop.getBody() and
    read.getParent*() = loop.getCondition() and read.getMethod().getName() = "read" and
    site = append and operation = "servlet_request_string_builder_materialization" and
    receiver = append.getQualifier().toString() and fieldPath = receiver and demandName = append.getArgument(0).toString() and
    evidence = "servlet_request_reader_loop" and coverage = "complete" and
    note = "recognized_request_wrapper_string_materialization"
  )
}

from Element site, string operation, string receiver, string fieldPath,
  string demandName, string evidence, string coverage, string note
where
  materializationRow(site, operation, receiver, fieldPath, demandName, evidence, coverage, note)
select
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  "input_materialization" as growth_kind,
  operation,
  "bytes" as resource_dimension,
  receiver,
  fieldPath as field_path,
  demandName as demand_input_name,
  // Materializing an attacker-controlled body is byte demand, not merely a value flow.
  "size" as demand_input_role,
  "request" as escape_scope,
  evidence as candidate_evidence,
  coverage as coverage_status,
  note as coverage_note
