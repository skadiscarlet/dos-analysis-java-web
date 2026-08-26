/**
 * @name Entry security and deployment facts
 * @description Extracts source-backed method authorization, Servlet constraints, static Spring Security matchers, and default deployment gates.
 * @kind table
 * @id dosweb/entry-security
 */

import java

// Exact independent decoder contract:
// "handler_fqn", "handler_file", "handler_start_line", "route_or_event",
// "fact_file", "fact_start_line", "kind", "value", "coverage_status",
// "coverage_note"

predicate sourceAnnotation(Annotation annotation) {
  annotation.getLocation().getFile().getRelativePath().matches("%.java")
}

predicate namedAnnotation(Annotation annotation, string name) {
  annotation.getType().hasName(name)
}

predicate methodOrTypeAnnotation(Method method, Annotation annotation) {
  annotation = method.getAnAnnotation()
  or annotation = method.getDeclaringType().getAnAnnotation()
}

predicate profileDeployment(
  Method method, Annotation annotation, string value,
  string coverageStatus, string coverageNote
) {
  methodOrTypeAnnotation(method, annotation) and sourceAnnotation(annotation) and
  annotation.getType().hasQualifiedName("org.springframework.context.annotation", "Profile") and
  exists(string profile |
    profile = annotation.getAStringArrayValue("value") and profile != "" and
    value = "profile:" + profile and coverageStatus = "complete" and
    coverageNote = "explicit_spring_profile_gate"
  )
}

predicate conditionalPropertyDeployment(
  Method method, Annotation annotation, string value,
  string coverageStatus, string coverageNote
) {
  methodOrTypeAnnotation(method, annotation) and sourceAnnotation(annotation) and
  annotation.getType().hasQualifiedName(
    "org.springframework.boot.autoconfigure.condition", "ConditionalOnProperty"
  ) and
  (
    exists(string key, string expected |
      (key = annotation.getAStringArrayValue("name") or
       key = annotation.getAStringArrayValue("value")) and
      key != "" and expected = annotation.getStringValue("havingValue") and
      expected != "" and value = "conditional_property:" + key + "=" + expected and
      coverageStatus = "complete" and
      coverageNote = "explicit_conditional_property_gate"
    )
    or not exists(string key, string expected |
         (key = annotation.getAStringArrayValue("name") or
          key = annotation.getAStringArrayValue("value")) and
         key != "" and expected = annotation.getStringValue("havingValue") and
         expected != ""
       ) and
       value = "conditional_property_unknown" and coverageStatus = "partial" and
       coverageNote = "conditional_property_requires_static_name_and_value"
  )
}

predicate optionalDeployment(
  Method method, Annotation annotation, string value,
  string coverageStatus, string coverageNote
) {
  methodOrTypeAnnotation(method, annotation) and sourceAnnotation(annotation) and
  (
    annotation.getType().hasQualifiedName(
      "org.springframework.boot.autoconfigure.condition",
      ["ConditionalOnBean", "ConditionalOnClass", "ConditionalOnExpression"]
    )
    or annotation.getType().hasQualifiedName(
         "org.springframework.context.annotation", "Conditional"
       )
  ) and
  value = "optional" and coverageStatus = "complete" and
  coverageNote = "explicit_optional_component_gate"
}

predicate deploymentAnnotation(
  Method method, Annotation annotation, string value,
  string coverageStatus, string coverageNote
) {
  profileDeployment(method, annotation, value, coverageStatus, coverageNote)
  or conditionalPropertyDeployment(
       method, annotation, value, coverageStatus, coverageNote
     )
  or optionalDeployment(method, annotation, value, coverageStatus, coverageNote)
}

predicate annotationAuth(
  Method method, Annotation annotation, string value,
  string coverageStatus, string coverageNote
) {
  methodOrTypeAnnotation(method, annotation) and sourceAnnotation(annotation) and
  (
    namedAnnotation(annotation, ["PermitAll", "AnonymousAllowed"]) and
    value = "unauthenticated_annotation" and coverageStatus = "complete" and
    coverageNote = "permit_all"
    or namedAnnotation(annotation, "PreAuthorize") and
       annotation.getStringValue("value") = "permitAll()" and
       value = "unauthenticated_annotation" and coverageStatus = "complete" and
       coverageNote = "preauthorize_permit_all"
    or namedAnnotation(annotation, "PreAuthorize") and
       annotation.getStringValue("value") = "isAuthenticated()" and
       value = "low_privilege_annotation" and coverageStatus = "complete" and
       coverageNote = "preauthorize_authenticated"
    or namedAnnotation(annotation, ["RolesAllowed", "Secured"]) and
       value = "privileged_annotation" and coverageStatus = "complete" and
       coverageNote = "role_annotation"
    or namedAnnotation(annotation, "PreAuthorize") and
       (annotation.getStringValue("value").matches("%hasRole%") or
        annotation.getStringValue("value").matches("%hasAuthority%")) and
       value = "privileged_annotation" and coverageStatus = "complete" and
       coverageNote = "preauthorize_static_role"
    or namedAnnotation(annotation, "PreAuthorize") and
       not annotation.getStringValue("value") = "permitAll()" and
       not annotation.getStringValue("value") = "isAuthenticated()" and
       not annotation.getStringValue("value").matches("%hasRole%") and
       not annotation.getStringValue("value").matches("%hasAuthority%") and
       value = "security_matcher_unknown" and coverageStatus = "partial" and
       coverageNote = "dynamic_security_matcher_partial"
  )
}

predicate servletConstraint(
  Method method, Annotation annotation, string value,
  string coverageStatus, string coverageNote
) {
  methodOrTypeAnnotation(method, annotation) and sourceAnnotation(annotation) and
  annotation.getType().hasQualifiedName(
    ["javax.servlet.annotation", "jakarta.servlet.annotation"], "ServletSecurity"
  ) and
  (
    exists(Annotation constraint, string role |
      constraint = annotation.getValue("value") and
      constraint.getType().hasQualifiedName(
        ["javax.servlet.annotation", "jakarta.servlet.annotation"], "HttpConstraint"
      ) and
      role = constraint.getAStringArrayValue("rolesAllowed") and role != "" and
      value = "privileged_constraint" and coverageStatus = "complete" and
      coverageNote = "servlet_security_roles_allowed"
    )
    or not exists(Annotation constraint, string role |
         constraint = annotation.getValue("value") and
         role = constraint.getAStringArrayValue("rolesAllowed") and role != ""
       ) and
       value = "security_matcher_unknown" and coverageStatus = "partial" and
       coverageNote = "servlet_security_constraint_partial"
  )
}

predicate springSecurityDslCall(MethodCall call) {
  call.getMethod().getDeclaringType().getPackage().getName().matches(
    "org.springframework.security%"
  )
}

predicate staticSecurityRule(
  MethodCall matcher, MethodCall rule, string route, string value,
  string coverageStatus, string coverageNote
) {
  matcher.getMethod().getName() = ["requestMatchers", "antMatchers", "mvcMatchers"] and
  springSecurityDslCall(matcher) and springSecurityDslCall(rule) and
  matcher.getArgument(0) instanceof CompileTimeConstantExpr and
  route = matcher.getArgument(0).(CompileTimeConstantExpr).getStringValue() and
  rule.getQualifier() = matcher and
  (
    rule.getMethod().getName() = "permitAll" and
    value = "unauthenticated_filter" and coverageStatus = "complete" and
    coverageNote = "static_request_matcher_permitAll"
    or rule.getMethod().getName() = "authenticated" and
       value = "low_privilege_filter" and coverageStatus = "complete" and
       coverageNote = "static_request_matcher_authenticated"
    or rule.getMethod().getName() = ["hasRole", "hasAuthority"] and
       rule.getArgument(0) instanceof CompileTimeConstantExpr and
       value = "privileged_filter" and coverageStatus = "complete" and
       coverageNote = "static_request_matcher_hasRole"
  )
}

predicate dynamicSecurityRule(MethodCall matcher, string coverageNote) {
  matcher.getMethod().getName() = ["requestMatchers", "antMatchers", "mvcMatchers"] and
  springSecurityDslCall(matcher) and
  not matcher.getArgument(0) instanceof CompileTimeConstantExpr and
  coverageNote = "dynamic_security_matcher_partial"
}

predicate authRow(
  string handlerFqn, string handlerFile, int handlerLine, string routeOrEvent,
  string factFile, int factLine, string kind, string value,
  string coverageStatus, string coverageNote
) {
  exists(Method method, Annotation annotation |
    method.fromSource() and
    annotationAuth(method, annotation, value, coverageStatus, coverageNote) and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and routeOrEvent = "" and
    factFile = annotation.getLocation().getFile().getRelativePath() and
    factLine = annotation.getLocation().getStartLine() and kind = "annotation"
  )
  or exists(Method method, Annotation annotation |
    method.fromSource() and
    servletConstraint(method, annotation, value, coverageStatus, coverageNote) and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and routeOrEvent = "" and
    factFile = annotation.getLocation().getFile().getRelativePath() and
    factLine = annotation.getLocation().getStartLine() and kind = "servlet_constraint"
  )
  or exists(MethodCall matcher, MethodCall rule, Method method |
    staticSecurityRule(matcher, rule, routeOrEvent, value, coverageStatus, coverageNote) and
    method = matcher.getEnclosingCallable() and method.fromSource() and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and
    factFile = rule.getLocation().getFile().getRelativePath() and
    factLine = rule.getLocation().getStartLine() and kind = "security_filter_chain"
  )
  or exists(MethodCall matcher, Method method |
    dynamicSecurityRule(matcher, coverageNote) and
    method = matcher.getEnclosingCallable() and method.fromSource() and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and routeOrEvent = "dynamic_matcher" and
    factFile = matcher.getLocation().getFile().getRelativePath() and
    factLine = matcher.getLocation().getStartLine() and kind = "security_filter_chain" and
    value = "security_matcher_unknown" and coverageStatus = "partial"
  )
}

predicate securityRow(
  string handlerFqn, string handlerFile, int handlerLine, string routeOrEvent,
  string factFile, int factLine, string kind, string value,
  string coverageStatus, string coverageNote
) {
  authRow(handlerFqn, handlerFile, handlerLine, routeOrEvent, factFile, factLine,
          kind, value, coverageStatus, coverageNote)
  or exists(Method method, Annotation annotation |
    method.fromSource() and
    deploymentAnnotation(method, annotation, value, coverageStatus, coverageNote) and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and routeOrEvent = "" and
    factFile = annotation.getLocation().getFile().getRelativePath() and
    factLine = annotation.getLocation().getStartLine() and kind = "deployment_gate"
  )
}

from string handlerFqn, string handlerFile, int handlerLine, string routeOrEvent,
     string factFile, int factLine, string factKind, string factValue,
     string coverageStatus, string coverageNote
where securityRow(handlerFqn, handlerFile, handlerLine, routeOrEvent, factFile,
                  factLine, factKind, factValue, coverageStatus, coverageNote)
select handlerFqn as handler_fqn, handlerFile as handler_file,
       handlerLine as handler_start_line, routeOrEvent as route_or_event,
       factFile as fact_file, factLine as fact_start_line, factKind as kind,
       factValue as value, coverageStatus as coverage_status,
       coverageNote as coverage_note
