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
  or annotation.getType().hasQualifiedName("org.springframework.stereotype", name)
  or annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", name)
}

predicate isControllerAnnotation(Annotation annotation) {
  isSpringAnnotation(annotation, ["Controller", "RestController"])
}

predicate isMappingAnnotation(Annotation annotation) {
  isSpringAnnotation(annotation, [
    "RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping"
  ])
}

string getMappingPath(Annotation annotation) {
  result = annotation.getAStringArrayValue("value") or
  result = annotation.getAStringArrayValue("path")
}

string getMappingVerb(Annotation annotation) {
  annotation.getType().hasName("GetMapping") and result = "GET"
  or annotation.getType().hasName("PostMapping") and result = "POST"
  or annotation.getType().hasName("PutMapping") and result = "PUT"
  or annotation.getType().hasName("DeleteMapping") and result = "DELETE"
  or annotation.getType().hasName("PatchMapping") and result = "PATCH"
  or annotation.getType().hasName("RequestMapping") and
    result = annotation.getAnEnumConstantArrayValue("method").getName()
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

predicate hasExplicitSpringInputAnnotation(Parameter parameter) {
  exists(Annotation annotation |
    annotation = parameter.getAnAnnotation() and
    isSpringAnnotation(annotation, [
      "RequestBody", "RequestParam", "PathVariable", "RequestHeader", "ModelAttribute"
    ])
  )
}

string getInputKind(Parameter parameter) {
  isSpringAnnotation(parameter.getAnAnnotation(), "RequestBody") and result = "request_body"
  or isSpringAnnotation(parameter.getAnAnnotation(), "RequestParam") and result = "request_parameter"
  or isSpringAnnotation(parameter.getAnAnnotation(), "PathVariable") and result = "path_parameter"
  or isSpringAnnotation(parameter.getAnAnnotation(), "RequestHeader") and result = "header"
  or isSpringAnnotation(parameter.getAnAnnotation(), "ModelAttribute") and result = "model_attribute"
  or (
    parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("javax.servlet.http", "HttpServletRequest")
    or parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServletRequest")
  ) and result = "request_parameter"
  or
  parameter.getType() instanceof RefType and
  not hasExplicitSpringInputAnnotation(parameter) and
  not parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("javax.servlet.http", "HttpServletRequest") and
  not parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServletRequest") and
  not parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("org.springframework.validation", "BindingResult") and
  not parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("org.springframework.ui", "Model") and
  not parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("java.security", "Principal") and
  not parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("javax.servlet", "ServletResponse") and
  not parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("jakarta.servlet", "ServletResponse") and
  not parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("javax.servlet.http", "HttpSession") and
  not parameter.getType().(RefType).getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", "HttpSession") and
  not parameter.getType().hasName(["java.lang.String", "java.lang.Integer", "java.lang.Long", "java.lang.Boolean", "java.lang.Short", "java.lang.Byte", "java.lang.Float", "java.lang.Double", "java.lang.Character"]) and
  result = "model_attribute"
}

predicate isArmeriaAnnotation(Annotation annotation) {
  annotation.getType().hasQualifiedName("fixture.armeria", ["Post", "Get"])
  or annotation.getType().hasQualifiedName("com.linecorp.armeria.server.annotation", ["Post", "Get"])
}

predicate isArmeriaRequestType(Type type) {
  type.(RefType).getASourceSupertype*().hasQualifiedName("fixture.armeria", "HttpRequest")
  or type.(RefType).getASourceSupertype*().hasQualifiedName("com.linecorp.armeria.common", "HttpRequest")
}

predicate armeriaRegistration(Method method, Method register, Expr annotatedService) {
  exists(MethodCall call, MethodCall get, Parameter service |
    call = annotatedService and call.getMethod().getName() = "annotatedService" and
    (call.getMethod().getDeclaringType().hasQualifiedName("fixture.armeria", "ServerBuilder") or
     call.getMethod().getDeclaringType().hasQualifiedName("com.linecorp.armeria.server", "ServerBuilder")) and
    register = call.getEnclosingCallable() and get = call.getArgument(0) and
    get.getMethod().getName() = "get" and get.getQualifier().(VarAccess).getVariable() = service and
    service.getType().(ParameterizedType).getTypeArgument(0).(RefType).getSourceDeclaration() = method.getDeclaringType()
  )
  or exists(MethodCall ifPresent, MemberRefExpr reference, Parameter service |
    register = ifPresent.getEnclosingCallable() and ifPresent.getMethod().getName() = "ifPresent" and
    reference = ifPresent.getArgument(0) and reference.getReferencedCallable().getName() = "annotatedService" and
    reference.getReferencedCallable().getDeclaringType().hasQualifiedName("com.linecorp.armeria.server", "ServerBuilder") and
    ifPresent.getQualifier().(VarAccess).getVariable() = service and
    service.getType().(ParameterizedType).getTypeArgument(0).(RefType).getSourceDeclaration() = method.getDeclaringType() and
    annotatedService = reference
  )
}

predicate springRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method method, Annotation mapping, Parameter parameter, string classPath, string methodPath, string verb |
    method.getDeclaringType().getAnAnnotation() = any(Annotation controller | isControllerAnnotation(controller)) and
    mapping = method.getAnAnnotation() and isMappingAnnotation(mapping) and
    methodPath = getMappingPath(mapping) and classPath = getClassPath(method) and
    parameter = method.getAParameter() and inputKind = getInputKind(parameter) and
    framework = "spring_mvc" and protocol = "http" and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and handlerLine = method.getLocation().getStartLine() and
    registrationKind = "annotation_mapping" and registrationFqn = handlerFqn and
    registrationFile = mapping.getLocation().getFile().getRelativePath() and registrationLine = mapping.getLocation().getStartLine() and
    (verb = getMappingVerb(mapping) and routeOrEvent = verb + " " + classPath + "/" + methodPath or
     verb = "" and routeOrEvent = classPath + "/" + methodPath) and
    authContext = "unknown" and inputName = parameter.getName() and inputType = parameter.getType().toString() and
    materializationPhase = "before_handler" and coverageStatus = "complete" and coverageNote = "spring_annotation_mapping"
  )
  or exists(Method method, Annotation mapping, Parameter parameter, Method register, Expr annotatedService |
    mapping = method.getAnAnnotation() and isArmeriaAnnotation(mapping) and routeOrEvent = mapping.getStringValue("value") and
    parameter = method.getAParameter() and isArmeriaRequestType(parameter.getType()) and
    armeriaRegistration(method, register, annotatedService) and framework = "spring_mvc" and protocol = "http" and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and registrationKind = "static_registration" and
    registrationFqn = register.getDeclaringType().getQualifiedName() + "." + register.getName() and registrationFile = annotatedService.getLocation().getFile().getRelativePath() and
    registrationLine = annotatedService.getLocation().getStartLine() and authContext = "unknown" and inputName = parameter.getName() and
    inputType = parameter.getType().toString() and inputKind = "request_body" and materializationPhase = "before_handler" and
    coverageStatus = "complete" and coverageNote = "armeria_annotated_service_registration"
  )
  or exists(MethodCall call, Method enclosing |
    call.getMethod().hasQualifiedName("java.lang", "Class", "forName") and enclosing = call.getEnclosingCallable() and
    enclosing.getDeclaringType().getAnAnnotation() = any(Annotation controller | isControllerAnnotation(controller)) and
    framework = "spring_mvc" and protocol = "http" and handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and
    handlerFile = enclosing.getLocation().getFile().getRelativePath() and handlerLine = enclosing.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and registrationFile = call.getLocation().getFile().getRelativePath() and
    registrationLine = call.getLocation().getStartLine() and routeOrEvent = "dynamic_route" and authContext = "unknown" and
    inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and materializationPhase = "unknown" and
    coverageStatus = "partial" and coverageNote = "reflection_controller_registration"
  )
}

from string framework, string protocol, string handlerFqn, string handlerFile, int handlerLine, string registrationKind, string registrationFqn,
     string registrationFile, int registrationLine, string routeOrEvent, string authContext, string inputName, string inputType, string inputKind,
     string materializationPhase, string coverageStatus, string coverageNote
where springRow(framework, protocol, handlerFqn, handlerFile, handlerLine, registrationKind, registrationFqn, registrationFile, registrationLine,
                routeOrEvent, authContext, inputName, inputType, inputKind, materializationPhase, coverageStatus, coverageNote)
select framework, protocol, handlerFqn as handler_fqn, handlerFile as handler_file, handlerLine as handler_start_line,
       registrationKind as registration_kind, registrationFqn as registration_fqn, registrationFile as registration_file,
       registrationLine as registration_start_line, routeOrEvent as route_or_event, authContext as auth_context,
       inputName as attacker_input_name, inputType as attacker_input_type, inputKind as attacker_input_kind,
       materializationPhase as materialization_phase, coverageStatus as coverage_status, coverageNote as coverage_note
