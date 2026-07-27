/**
 * @name Spring MVC registered entries
 * @description Extracts statically registered Spring MVC handlers and explicit dynamic-registration gaps.
 * @kind table
 * @id dosweb/spring-mvc-entries
 */

import java

// Exact Task 3 contract:
// "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
// "registration_kind", "registration_fqn", "registration_file",
// "registration_start_line", "route_or_event", "auth_context",
// "attacker_input_name", "attacker_input_type", "attacker_input_kind",
// "materialization_phase", "coverage_status", "coverage_note"

predicate isSpringAnnotation(Annotation annotation, string name) {
  annotation.getType().hasQualifiedName("fixture.spring", name)
  or
  annotation.getType().hasQualifiedName("org.springframework.stereotype", name)
  or
  annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", name)
}

predicate isControllerAnnotation(Annotation annotation) {
  isSpringAnnotation(annotation, ["Controller", "RestController"])
}

predicate isMappingAnnotation(Annotation annotation) {
  isSpringAnnotation(
    annotation,
    ["RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping"]
  )
}

string getMappingPath(Annotation annotation) {
  result = annotation.getStringValue("value") or
  result = annotation.getStringValue("path")
}

string getClassPath(Method method) {
  exists(Annotation annotation |
    annotation = method.getDeclaringType().getAnAnnotation() and
    isSpringAnnotation(annotation, "RequestMapping") and
    result = getMappingPath(annotation)
  )
  or
  result = "" and
  not exists(Annotation annotation |
    annotation = method.getDeclaringType().getAnAnnotation() and
    isSpringAnnotation(annotation, "RequestMapping") and
    getMappingPath(annotation) != ""
  )
}

string getInputKind(Parameter parameter) {
  isSpringAnnotation(parameter.getAnAnnotation(), "RequestBody") and result = "request_body"
  or
  isSpringAnnotation(parameter.getAnAnnotation(), "RequestParam") and
  result = "request_parameter"
  or
  isSpringAnnotation(parameter.getAnAnnotation(), "PathVariable") and
  result = "path_parameter"
  or
  isSpringAnnotation(parameter.getAnAnnotation(), "RequestHeader") and result = "header"
}

predicate springRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method method, Annotation mapping, Parameter parameter, string classPath, string methodPath |
    method.getDeclaringType().getAnAnnotation() = any(Annotation controller |
      isControllerAnnotation(controller)
    ) and
    mapping = method.getAnAnnotation() and
    isMappingAnnotation(mapping) and
    methodPath = getMappingPath(mapping) and
    classPath = getClassPath(method) and
    parameter = method.getAParameter() and
    inputKind = getInputKind(parameter) and
    framework = "spring_mvc" and protocol = "http" and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and
    registrationKind = "annotation_mapping" and registrationFqn = handlerFqn and
    registrationFile = mapping.getLocation().getFile().getRelativePath() and
    registrationLine = mapping.getLocation().getStartLine() and
    routeOrEvent = classPath + "/" + methodPath and authContext = "unknown" and
    inputName = parameter.getName() and inputType = parameter.getType().toString() and
    materializationPhase = "before_handler" and coverageStatus = "complete" and
    coverageNote = "spring_annotation_mapping"
  )
  or
  exists(MethodCall call, Method enclosing |
    call.getMethod().hasQualifiedName("java.lang", "Class", "forName") and
    enclosing = call.getEnclosingCallable() and
    enclosing.getDeclaringType().getAnAnnotation() = any(Annotation controller |
      isControllerAnnotation(controller)
    ) and
    framework = "spring_mvc" and protocol = "http" and
    handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and
    handlerFile = enclosing.getLocation().getFile().getRelativePath() and
    handlerLine = enclosing.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = call.getLocation().getFile().getRelativePath() and
    registrationLine = call.getLocation().getStartLine() and
    routeOrEvent = "dynamic_route" and authContext = "unknown" and
    inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and
    materializationPhase = "unknown" and coverageStatus = "partial" and
    coverageNote = "reflection_controller_registration"
  )
}

from
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
where
  springRow(
    framework, protocol, handlerFqn, handlerFile, handlerLine, registrationKind,
    registrationFqn, registrationFile, registrationLine, routeOrEvent, authContext,
    inputName, inputType, inputKind, materializationPhase, coverageStatus, coverageNote
  )
select
  framework, protocol, handlerFqn as handler_fqn,
  handlerFile as handler_file, handlerLine as handler_start_line,
  registrationKind as registration_kind, registrationFqn as registration_fqn,
  registrationFile as registration_file, registrationLine as registration_start_line,
  routeOrEvent as route_or_event, authContext as auth_context,
  inputName as attacker_input_name, inputType as attacker_input_type,
  inputKind as attacker_input_kind, materializationPhase as materialization_phase,
  coverageStatus as coverage_status, coverageNote as coverage_note
