/**
 * @name Servlet registered entries
 * @description Extracts statically registered Servlet and Filter handlers and explicit dynamic-registration gaps.
 * @kind table
 * @id dosweb/servlet-entries
 */

import java

// Entry rows must originate from source, not dependency bytecode.
predicate isSourceMethod(Method method) {
  method.fromSource()
}

predicate isSourceExpr(Expr expr) {
  expr.getLocation().getFile().getRelativePath().matches("%.java")
}

// Exact Task 3 contract:
// "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
// "registration_kind", "registration_fqn", "registration_file",
// "registration_start_line", "route_or_event", "auth_context",
// "attacker_input_name", "attacker_input_type", "attacker_input_kind",
// "materialization_phase", "coverage_status", "coverage_note"

predicate servletHandlerName(string name) {
  name = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch", "doHead", "doOptions"]
}

predicate isServletType(RefType type, string simpleName) {
  type.getASourceSupertype*().hasQualifiedName("fixture.servlet", simpleName)
  or type.getASourceSupertype*().hasQualifiedName("javax.servlet.http", simpleName)
  or type.getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", simpleName)
  or type.getASourceSupertype*().hasQualifiedName("javax.servlet", simpleName)
  or type.getASourceSupertype*().hasQualifiedName("jakarta.servlet", simpleName)
}

predicate isWebServletAnnotation(Annotation annotation) {
  annotation.getType().hasQualifiedName("fixture.servlet", "WebServlet")
  or annotation.getType().hasQualifiedName("javax.servlet.annotation", "WebServlet")
  or annotation.getType().hasQualifiedName("jakarta.servlet.annotation", "WebServlet")
}

predicate isHolderType(RefType type) {
  type.hasQualifiedName("fixture.servlet", "ServletHolder")
  or type.hasQualifiedName("org.eclipse.jetty.servlet", "ServletHolder")
}

predicate isContextHandlerType(RefType type) {
  type.hasQualifiedName("fixture.servlet", "ServletContextHandler")
  or type.hasQualifiedName("org.eclipse.jetty.servlet", "ServletContextHandler")
}

predicate holderBinds(MethodCall addServlet, Type handlerType) {
  exists(ClassInstanceExpr holder, Expr bound |
    holder = addServlet.getArgument(0) and isHolderType(holder.getConstructedType()) and
    bound = holder.getArgument(0) and
    ((bound instanceof TypeLiteral and bound.(TypeLiteral).getReferencedType() = handlerType) or
     (bound instanceof ClassInstanceExpr and bound.(ClassInstanceExpr).getConstructedType() = handlerType))
  )
}

predicate isFilterType(RefType type) {
  type.getASourceSupertype*().hasQualifiedName("fixture.servlet", "Filter")
  or type.getASourceSupertype*().hasQualifiedName("javax.servlet", "Filter")
  or type.getASourceSupertype*().hasQualifiedName("jakarta.servlet", "Filter")
}

predicate isFilterRegistrationBean(RefType type) {
  type.hasQualifiedName("fixture.servlet", "FilterRegistrationBean")
  or type.hasQualifiedName("org.springframework.boot.web.servlet", "FilterRegistrationBean")
  or type.(ParameterizedType).getGenericType().hasQualifiedName("fixture.servlet", "FilterRegistrationBean")
  or type.(ParameterizedType).getGenericType().hasQualifiedName("org.springframework.boot.web.servlet", "FilterRegistrationBean")
}

predicate filterBinds(MethodCall setFilter, Type handlerType) {
  setFilter.getMethod().getName() = "setFilter" and
  isFilterRegistrationBean(setFilter.getMethod().getDeclaringType()) and
  setFilter.getArgument(0) instanceof ClassInstanceExpr and
  setFilter.getArgument(0).(ClassInstanceExpr).getConstructedType() = handlerType
}

predicate staticUrlPattern(MethodCall call, string route) {
  (call.getMethod().getName() = "addUrlPatterns" or call.getMethod().getName() = "setUrlPatterns") and
  (
    call.getArgument(0) instanceof CompileTimeConstantExpr and
    route = call.getArgument(0).(CompileTimeConstantExpr).getStringValue()
    or exists(Field field, CompileTimeConstantExpr initializer |
      call.getArgument(0).(VarAccess).getVariable() = field and
      initializer = field.getInitializer() and
      route = initializer.getStringValue()
    )
  )
}

predicate servletRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method method, Annotation registration, Parameter request |
    servletHandlerName(method.getName()) and isServletType(method.getDeclaringType(), "HttpServlet") and
    isSourceMethod(method) and isSourceExpr(registration) and
    registration = method.getDeclaringType().getAnAnnotation() and isWebServletAnnotation(registration) and
    routeOrEvent = registration.getStringValue("value") and request = method.getParameter(0) and
    isServletType(request.getType().(RefType), "HttpServletRequest") and framework = "servlet" and protocol = "http" and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and registrationKind = "annotation_mapping" and
    registrationFqn = method.getDeclaringType().getQualifiedName() and registrationFile = registration.getLocation().getFile().getRelativePath() and
    registrationLine = registration.getLocation().getStartLine() and
    routeOrEvent = registration.getStringValue("value") and authContext = "unknown" and inputName = request.getName() and inputType = request.getType().toString() and
    inputKind = "stream" and materializationPhase = "in_handler" and coverageStatus = "complete" and coverageNote = "servlet_annotation_mapping"
  )
  or exists(Method method, MethodCall addServlet, Parameter request, string route |
    servletHandlerName(method.getName()) and isServletType(method.getDeclaringType(), "HttpServlet") and
    isSourceMethod(method) and isSourceExpr(addServlet) and
    addServlet.getMethod().getName() = "addServlet" and isContextHandlerType(addServlet.getMethod().getDeclaringType()) and
    holderBinds(addServlet, method.getDeclaringType()) and addServlet.getArgument(1) instanceof CompileTimeConstantExpr and
    route = addServlet.getArgument(1).(CompileTimeConstantExpr).getStringValue() and request = method.getParameter(0) and
    isServletType(request.getType().(RefType), "HttpServletRequest") and framework = "servlet" and protocol = "http" and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and registrationKind = "static_registration" and
    registrationFqn = addServlet.getMethod().getDeclaringType().getQualifiedName() + "." + addServlet.getMethod().getName() and
    registrationFile = addServlet.getLocation().getFile().getRelativePath() and registrationLine = addServlet.getLocation().getStartLine() and
    routeOrEvent = route and authContext = "unknown" and inputName = request.getName() and inputType = request.getType().toString() and inputKind = "stream" and
    materializationPhase = "in_handler" and coverageStatus = "complete" and coverageNote = "jetty_servlet_holder_registration"
  )
  or exists(Method callback, MethodCall setFilter, MethodCall urls, Parameter request |
    callback.getName() = "doFilter" and isFilterType(callback.getDeclaringType()) and request = callback.getParameter(0) and
    isSourceMethod(callback) and isSourceExpr(setFilter) and isSourceExpr(urls) and
    isServletType(request.getType().(RefType), "ServletRequest") and filterBinds(setFilter, callback.getDeclaringType()) and
    urls.getQualifier().(VarAccess).getVariable() = setFilter.getQualifier().(VarAccess).getVariable() and
    staticUrlPattern(urls, routeOrEvent) and framework = "servlet" and protocol = "http" and
    handlerFqn = callback.getDeclaringType().getQualifiedName() + "." + callback.getName() and handlerFile = callback.getLocation().getFile().getRelativePath() and
    handlerLine = callback.getLocation().getStartLine() and registrationKind = "static_registration" and
    registrationFqn = setFilter.getMethod().getDeclaringType().getQualifiedName() + "." + setFilter.getMethod().getName() and
    registrationFile = setFilter.getLocation().getFile().getRelativePath() and registrationLine = setFilter.getLocation().getStartLine() and
    authContext = "unknown" and inputName = request.getName() and inputType = request.getType().toString() and inputKind = "stream" and
    materializationPhase = "in_handler" and coverageStatus = "complete" and coverageNote = "filter_registration_bean"
  )
  or exists(Method method, Parameter request, Parameter response |
    // Deployment descriptors are not in the Java AST. This is deliberately a
    // source-backed candidate only; Python resolves it against web.xml before
    // normalisation and never publishes the candidate as an EntryFact.
    method.getName() = "service" and isServletType(method.getDeclaringType(), "HttpServlet") and
    isSourceMethod(method) and request = method.getParameter(0) and response = method.getParameter(1) and
    isServletType(request.getType().(RefType), "HttpServletRequest") and
    isServletType(response.getType().(RefType), "HttpServletResponse") and
    framework = "servlet" and protocol = "http" and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and handlerLine = method.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = handlerFile and registrationLine = handlerLine and
    routeOrEvent = "web_xml_servlet_mapping" and authContext = "unknown" and
    inputName = request.getName() and inputType = request.getType().toString() and inputKind = "stream" and
    materializationPhase = "unknown" and coverageStatus = "partial" and
    coverageNote = "web_xml_servlet_mapping_requires_descriptor_binding"
  )
  or exists(MethodCall addServlet, Method enclosing |
    addServlet.getMethod().getName() = "addServlet" and isContextHandlerType(addServlet.getMethod().getDeclaringType()) and
    enclosing = addServlet.getEnclosingCallable() and not exists(Type handlerType | holderBinds(addServlet, handlerType)) and
    isSourceMethod(enclosing) and isSourceExpr(addServlet) and framework = "servlet" and protocol = "http" and
    handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and handlerFile = enclosing.getLocation().getFile().getRelativePath() and
    handlerLine = enclosing.getLocation().getStartLine() and registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = addServlet.getLocation().getFile().getRelativePath() and registrationLine = addServlet.getLocation().getStartLine() and
    routeOrEvent = "dynamic_servlet_mapping" and authContext = "unknown" and inputName = "unknown" and inputType = "unknown" and
    inputKind = "unknown" and materializationPhase = "unknown" and coverageStatus = "partial" and coverageNote = "unresolved_static_servlet_registration"
  )
  or exists(MethodCall call, Method enclosing |
    call.getMethod().hasQualifiedName("java.lang", "Class", "forName") and enclosing = call.getEnclosingCallable() and
    isSourceMethod(enclosing) and isSourceExpr(call) and
    framework = "servlet" and protocol = "http" and handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and
    handlerFile = enclosing.getLocation().getFile().getRelativePath() and handlerLine = enclosing.getLocation().getStartLine() and registrationKind = "dynamic_unresolved" and
    registrationFqn = handlerFqn and registrationFile = call.getLocation().getFile().getRelativePath() and registrationLine = call.getLocation().getStartLine() and
    routeOrEvent = "dynamic_servlet_mapping" and authContext = "unknown" and inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and
    materializationPhase = "unknown" and coverageStatus = "partial" and coverageNote = "reflection_servlet_registration"
  )
}

from string framework, string protocol, string handlerFqn, string handlerFile, int handlerLine, string registrationKind, string registrationFqn,
     string registrationFile, int registrationLine, string routeOrEvent, string authContext, string inputName, string inputType, string inputKind,
     string materializationPhase, string coverageStatus, string coverageNote
where servletRow(framework, protocol, handlerFqn, handlerFile, handlerLine, registrationKind, registrationFqn, registrationFile, registrationLine,
                 routeOrEvent, authContext, inputName, inputType, inputKind, materializationPhase, coverageStatus, coverageNote)
select framework, protocol, handlerFqn as handler_fqn, handlerFile as handler_file, handlerLine as handler_start_line,
       registrationKind as registration_kind, registrationFqn as registration_fqn, registrationFile as registration_file,
       registrationLine as registration_start_line, routeOrEvent as route_or_event, authContext as auth_context,
       inputName as attacker_input_name, inputType as attacker_input_type, inputKind as attacker_input_kind,
       materializationPhase as materialization_phase, coverageStatus as coverage_status, coverageNote as coverage_note
