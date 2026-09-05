/**
 * @name JAX-RS registered entries
 * @description Extracts JAX-RS resources only when annotation routes are statically bound to a registration call.
 * @kind table
 * @id dosweb/jax-rs-entries
 */

import java

// Entry rows must originate from source, not dependency bytecode. A class
// resolved from a compiled JAR (e.g. a target/.../Foo.class) has no source
// location, so `getStartLine()` yields 0 and the shared decoder rejects the row
// (LINE_INVALID), failing the entire query closed. `fromSource()` filters those.
predicate isSourceMethod(Method method) {
  method.fromSource()
}

predicate isSourceCall(MethodCall call) {
  call.getLocation().getFile().getRelativePath().matches("%.java")
}

predicate isSourceAnnotation(Annotation annotation) {
  annotation.getLocation().getFile().getRelativePath().matches("%.java")
}

// Exact shared Entry contract: 17 columns.
// "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
// "registration_kind", "registration_fqn", "registration_file", "registration_start_line",
// "route_or_event", "auth_context", "attacker_input_name", "attacker_input_type",
// "attacker_input_kind", "materialization_phase", "coverage_status", "coverage_note"

predicate isPathAnnotation(Annotation annotation) {
  annotation.getType().hasQualifiedName(["javax.ws.rs", "jakarta.ws.rs"], "Path")
}

predicate isVerbAnnotation(Annotation annotation) {
  annotation.getType().hasQualifiedName(["javax.ws.rs", "jakarta.ws.rs"], ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
}

predicate getPath(Annotation annotation, string path) {
  isPathAnnotation(annotation) and (
    path = annotation.getStringValue("value")
    or exists(Field field |
      field.getAnAccess() = annotation.getValue("value") and
      path = field.getInitializer().(CompileTimeConstantExpr).getStringValue()
    )
  )
}

string getClassPath(Method method) {
  exists(Annotation annotation |
    annotation = method.getDeclaringType().getAnAnnotation() and getPath(annotation, result)
  )
  or result = "" and not exists(Annotation annotation |
    annotation = method.getDeclaringType().getAnAnnotation() and getPath(annotation, _)
  )
}

string getMethodPath(Method method) {
  exists(Annotation annotation |
    annotation = method.getAnAnnotation() and getPath(annotation, result)
  )
  or result = "" and not exists(Annotation annotation |
    annotation = method.getAnAnnotation() and getPath(annotation, _)
  )
}

string getVerb(Method method) {
  exists(Annotation annotation |
    annotation = method.getAnAnnotation() and isVerbAnnotation(annotation) and result = annotation.getType().getName()
  )
}

string canonicalClassPath(Method method) {
  exists(string path, string withoutLeading |
    path = getClassPath(method) and
    (if path.matches("/%")
     then withoutLeading = path.substring(1, path.length())
     else withoutLeading = path) and
    (if withoutLeading.matches("%/")
     then result = withoutLeading.substring(0, withoutLeading.length() - 1)
     else result = withoutLeading)
  )
}

string canonicalMethodPath(Method method) {
  exists(string path, string withoutLeading |
    path = getMethodPath(method) and
    (if path.matches("/%")
     then withoutLeading = path.substring(1, path.length())
     else withoutLeading = path) and
    (if withoutLeading.matches("%/")
     then result = withoutLeading.substring(0, withoutLeading.length() - 1)
     else result = withoutLeading)
  )
}

string joinJaxRsPath(Method method) {
  exists(string canonicalClass, string canonicalMethod |
    canonicalClass = canonicalClassPath(method) and
    canonicalMethod = canonicalMethodPath(method) and
    (
      canonicalClass = "" and canonicalMethod = "" and result = "/"
      or canonicalClass = "" and canonicalMethod != "" and result = "/" + canonicalMethod
      or canonicalClass != "" and canonicalMethod = "" and result = "/" + canonicalClass
      or canonicalClass != "" and canonicalMethod != "" and
        result = "/" + canonicalClass + "/" + canonicalMethod
    )
  )
}

predicate isResourceClass(RefType type) {
  exists(Annotation annotation |
    annotation = type.getAnAnnotation() and isPathAnnotation(annotation)
  )
}

predicate isRegistrationCall(MethodCall call) {
  call.getMethod().hasQualifiedName(["fixture.jax_rs", "org.glassfish.jersey.server"], "ResourceConfig", "register")
  or call.getMethod().hasQualifiedName(["fixture.jax_rs", "org.glassfish.jersey.server"], "ResourceConfig", "registerClasses")
  or call.getMethod().hasQualifiedName(["fixture.jax_rs", "io.airlift.jaxrs", "com.facebook.airlift.jaxrs"], "JaxrsBinder", "bind")
  or call.getMethod().hasQualifiedName("org.apache.druid.guice", "Jerseys", "addResource")
}

predicate isGuiceBinderType(Type type) {
  type.(RefType).getASupertype*().hasQualifiedName("com.google.inject", "Binder")
}

predicate isClassType(Type type) {
  type.(ParameterizedType).getGenericType().hasQualifiedName("java.lang", "Class")
}

predicate helperDirectClassBinding(
  Method helper, Parameter binder, Parameter resource, MethodCall bind
) {
  bind.getEnclosingCallable() = helper and bind.getMethod().getName() = "bind" and
  bind.getQualifier().(VarAccess).getVariable() = binder and
  bind.getArgument(0).(VarAccess).getVariable() = resource and
  exists(MethodCall scoped, Field singleton |
    scoped.getEnclosingCallable() = helper and scoped.getMethod().getName() = "in" and
    scoped.getQualifier() = bind and
    scoped.getArgument(0).(VarAccess).getVariable() = singleton and
    singleton.getDeclaringType().hasQualifiedName("com.google.inject", "Scopes") and
    singleton.getName() = "SINGLETON"
  )
}

predicate helperComponentClassBinding(
  Method helper, Parameter binder, Parameter resource, MethodCall terminal
) {
  exists(MethodCall setBinder, MethodCall addBinding |
    setBinder.getEnclosingCallable() = helper and
    setBinder.getMethod().hasQualifiedName(
      "com.google.inject.multibindings", "Multibinder", "newSetBinder"
    ) and
    setBinder.getArgument(0).(VarAccess).getVariable() = binder and
    setBinder.getArgument(1) instanceof TypeLiteral and
    addBinding.getEnclosingCallable() = helper and
    addBinding.getMethod().getName() = "addBinding" and
    addBinding.getQualifier() = setBinder and
    terminal.getEnclosingCallable() = helper and terminal.getMethod().getName() = "to" and
    terminal.getQualifier() = addBinding and
    terminal.getArgument(0).(VarAccess).getVariable() = resource
  )
}

/** A source-defined helper is a registration primitive only when its two
 * parameters are a Guice Binder and Class, and it performs exactly one
 * singleton bind plus one Component multibinding of that Class parameter. */
predicate sourceHelperRegistrationBinds(MethodCall call, Type resourceType) {
  exists(Method helper, Parameter binder, Parameter resource,
         MethodCall directBind, MethodCall componentBind |
    helper = call.getMethod() and helper.fromSource() and helper.isStatic() and
    binder = helper.getParameter(0) and resource = helper.getParameter(1) and
    not exists(Parameter extra |
      extra = helper.getAParameter() and extra != binder and extra != resource
    ) and
    isGuiceBinderType(binder.getType()) and isClassType(resource.getType()) and
    call.getNumArgument() = 2 and
    call.getArgument(0).getType().(RefType).getASupertype*().hasQualifiedName(
      "com.google.inject", "Binder"
    ) and
    call.getArgument(1).(TypeLiteral).getReferencedType() = resourceType and
    helperDirectClassBinding(helper, binder, resource, directBind) and
    helperComponentClassBinding(helper, binder, resource, componentBind) and
    not exists(MethodCall other |
      other != directBind and helperDirectClassBinding(helper, binder, resource, other)
    ) and
    not exists(MethodCall other |
      other != componentBind and helperComponentClassBinding(helper, binder, resource, other)
    )
  )
}

predicate registrationBinds(MethodCall call, Type resource) {
  isRegistrationCall(call) and exists(Expr argument |
    argument = call.getAnArgument() and
    ((argument instanceof TypeLiteral and argument.(TypeLiteral).getReferencedType() = resource) or
     (argument instanceof ClassInstanceExpr and argument.(ClassInstanceExpr).getConstructedType() = resource))
  )
  or sourceHelperRegistrationBinds(call, resource)
}

predicate packageRegistrationBinds(MethodCall call, Type resource) {
  call.getMethod().hasQualifiedName(["fixture.jax_rs", "org.glassfish.jersey.server"], "ResourceConfig", "packages") and
  exists(Expr argument, string pkg |
    argument = call.getAnArgument() and
    pkg = argument.(CompileTimeConstantExpr).getStringValue() and
    resource.(RefType).getPackage().getName() = pkg
  )
}

predicate anyRegistrationBinds(MethodCall call, Type resource) {
  registrationBinds(call, resource)
  or packageRegistrationBinds(call, resource)
}

predicate hasJaxRsParameterAnnotation(Parameter parameter) {
  exists(Annotation annotation |
    annotation = parameter.getAnAnnotation() and
    annotation.getType().getPackage().getName() = ["javax.ws.rs", "jakarta.ws.rs"]
  )
}

string getInputKind(Parameter parameter) {
  parameter.getAnAnnotation().getType().hasQualifiedName(["javax.ws.rs", "jakarta.ws.rs"], "PathParam") and result = "path_parameter"
  or parameter.getAnAnnotation().getType().hasQualifiedName(["javax.ws.rs", "jakarta.ws.rs"], "QueryParam") and result = "request_parameter"
  or parameter.getAnAnnotation().getType().hasQualifiedName(["javax.ws.rs", "jakarta.ws.rs"], ["HeaderParam", "CookieParam", "MatrixParam", "FormParam"]) and result = "request_parameter"
  or parameter.getAnAnnotation().getType().hasQualifiedName(["javax.ws.rs", "jakarta.ws.rs"], "BeanParam") and result = "model_attribute"
  or not hasJaxRsParameterAnnotation(parameter) and
    parameter.getType().(RefType).getASupertype*().hasQualifiedName("java.io", "InputStream") and
    result = "stream"
  or not hasJaxRsParameterAnnotation(parameter) and
    not parameter.getType().(RefType).getASupertype*().hasQualifiedName("java.io", "InputStream") and
    result = "request_body"
}

predicate jaxRsRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method method, Parameter parameter, MethodCall registration, Type resource, string classPath, string methodPath, string verb |
    isResourceClass(resource) and method.getDeclaringType() = resource and
    isSourceMethod(method) and isSourceCall(registration) and
    method.getAnAnnotation() = any(Annotation mapping | isVerbAnnotation(mapping)) and
    parameter = method.getAParameter() and getInputKind(parameter) = inputKind and
    anyRegistrationBinds(registration, resource) and
    classPath = getClassPath(method) and methodPath = getMethodPath(method) and verb = getVerb(method) and
    framework = "jax_rs" and protocol = "http" and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and handlerLine = method.getLocation().getStartLine() and
    registrationKind = "static_registration" and registrationFqn = registration.getMethod().getDeclaringType().getQualifiedName() + "." + registration.getMethod().getName() and
    registrationFile = registration.getLocation().getFile().getRelativePath() and registrationLine = registration.getLocation().getStartLine() and
    routeOrEvent = verb + " " + joinJaxRsPath(method) and authContext = "unknown" and
    inputName = parameter.getName() and inputType = parameter.getType().toString() and
    materializationPhase = "before_handler" and coverageStatus = "complete" and coverageNote = "jax_rs_static_registration"
  )
  or exists(Method method, Annotation mapping, Parameter parameter, string classPath, string methodPath, string verb |
    method.getAnAnnotation() = mapping and isVerbAnnotation(mapping) and parameter = method.getAParameter() and
    isSourceMethod(method) and isSourceAnnotation(mapping) and
    isResourceClass(method.getDeclaringType()) and
    not exists(MethodCall registration | anyRegistrationBinds(registration, method.getDeclaringType())) and
    getInputKind(parameter) = inputKind and
    classPath = getClassPath(method) and methodPath = getMethodPath(method) and verb = getVerb(method) and
    framework = "jax_rs" and protocol = "http" and handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and handlerLine = method.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and registrationFile = mapping.getLocation().getFile().getRelativePath() and
    registrationLine = mapping.getLocation().getStartLine() and routeOrEvent = verb + " " + joinJaxRsPath(method) and authContext = "unknown" and
    inputName = parameter.getName() and inputType = parameter.getType().toString() and inputKind = inputKind and
    materializationPhase = "unknown" and coverageStatus = "partial" and coverageNote = "annotation_only_jax_rs_resource"
  )
}

from string framework, string protocol, string handlerFqn, string handlerFile, int handlerLine, string registrationKind, string registrationFqn,
     string registrationFile, int registrationLine, string routeOrEvent, string authContext, string inputName, string inputType, string inputKind,
     string materializationPhase, string coverageStatus, string coverageNote
where jaxRsRow(framework, protocol, handlerFqn, handlerFile, handlerLine, registrationKind, registrationFqn, registrationFile, registrationLine,
               routeOrEvent, authContext, inputName, inputType, inputKind, materializationPhase, coverageStatus, coverageNote)
select framework, protocol, handlerFqn as handler_fqn, handlerFile as handler_file, handlerLine as handler_start_line,
       registrationKind as registration_kind, registrationFqn as registration_fqn, registrationFile as registration_file,
       registrationLine as registration_start_line, routeOrEvent as route_or_event, authContext as auth_context,
       inputName as attacker_input_name, inputType as attacker_input_type, inputKind as attacker_input_kind,
       materializationPhase as materialization_phase, coverageStatus as coverage_status, coverageNote as coverage_note
