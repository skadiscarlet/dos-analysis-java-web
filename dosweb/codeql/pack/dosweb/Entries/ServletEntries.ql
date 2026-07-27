/**
 * @name Servlet registered entries
 * @description Extracts annotation-registered Servlet handlers and explicit dynamic-registration gaps.
 * @kind table
 * @id dosweb/servlet-entries
 */

import java

// Exact Task 3 contract:
// "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
// "registration_kind", "registration_fqn", "registration_file",
// "registration_start_line", "route_or_event", "auth_context",
// "attacker_input_name", "attacker_input_type", "attacker_input_kind",
// "materialization_phase", "coverage_status", "coverage_note"

predicate servletHandlerName(string name) {
  name = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"]
}

predicate isServletType(RefType type, string simpleName) {
  type.getASourceSupertype*().hasQualifiedName("fixture.servlet", simpleName)
  or
  type.getASourceSupertype*().hasQualifiedName("javax.servlet.http", simpleName)
  or
  type.getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", simpleName)
  or
  type.getASourceSupertype*().hasQualifiedName("javax.servlet", simpleName)
  or
  type.getASourceSupertype*().hasQualifiedName("jakarta.servlet", simpleName)
}

predicate isWebServletAnnotation(Annotation annotation) {
  annotation.getType().hasQualifiedName("fixture.servlet", "WebServlet")
  or
  annotation.getType().hasQualifiedName("javax.servlet.annotation", "WebServlet")
  or
  annotation.getType().hasQualifiedName("jakarta.servlet.annotation", "WebServlet")
}

predicate servletRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method method, Annotation registration, Parameter request |
    servletHandlerName(method.getName()) and
    isServletType(method.getDeclaringType(), "HttpServlet") and
    registration = method.getDeclaringType().getAnAnnotation() and
    isWebServletAnnotation(registration) and
    routeOrEvent = registration.getStringValue("value") and
    request = method.getParameter(0) and
    isServletType(request.getType().(RefType), "HttpServletRequest") and
    framework = "servlet" and protocol = "http" and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and
    registrationKind = "annotation_mapping" and
    registrationFqn = method.getDeclaringType().getQualifiedName() and
    registrationFile = registration.getLocation().getFile().getRelativePath() and
    registrationLine = registration.getLocation().getStartLine() and
    authContext = "unknown" and inputName = request.getName() and
    inputType = request.getType().toString() and inputKind = "stream" and
    materializationPhase = "in_handler" and coverageStatus = "complete" and
    coverageNote = "servlet_annotation_mapping"
  )
  or
  exists(MethodCall addServlet, Method enclosing |
    addServlet.getMethod().getName() = "addServlet" and
    isServletType(addServlet.getMethod().getDeclaringType(), "ServletContext") and
    enclosing = addServlet.getEnclosingCallable() and
    framework = "servlet" and protocol = "http" and
    handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and
    handlerFile = enclosing.getLocation().getFile().getRelativePath() and
    handlerLine = enclosing.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = addServlet.getLocation().getFile().getRelativePath() and
    registrationLine = addServlet.getLocation().getStartLine() and
    routeOrEvent = "dynamic_servlet_mapping" and authContext = "unknown" and
    inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and
    materializationPhase = "unknown" and coverageStatus = "partial" and
    coverageNote = "unresolved_static_servlet_registration"
  )
  or
  exists(MethodCall call, Method enclosing |
    call.getMethod().hasQualifiedName("java.lang", "Class", "forName") and
    enclosing = call.getEnclosingCallable() and
    exists(MethodCall addServlet |
      addServlet.getEnclosingCallable() = enclosing and
      addServlet.getMethod().getName() = "addServlet" and
      isServletType(addServlet.getMethod().getDeclaringType(), "ServletContext")
    ) and
    framework = "servlet" and protocol = "http" and
    handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and
    handlerFile = enclosing.getLocation().getFile().getRelativePath() and
    handlerLine = enclosing.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = call.getLocation().getFile().getRelativePath() and
    registrationLine = call.getLocation().getStartLine() and
    routeOrEvent = "dynamic_servlet_mapping" and authContext = "unknown" and
    inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and
    materializationPhase = "unknown" and coverageStatus = "partial" and
    coverageNote = "reflection_servlet_registration"
  )
}

from
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
where
  servletRow(
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
