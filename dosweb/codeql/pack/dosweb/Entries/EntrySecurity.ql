/**
 * @name Entry security and deployment facts
 * @description Extracts source-backed method authorization, Servlet constraints, static Spring Security matchers, and deployment-gate evidence.
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

predicate methodOrTypeAnnotation(Method method, Annotation annotation) {
  annotation = method.getAnAnnotation()
  or annotation = method.getDeclaringType().getAnAnnotation()
}

predicate simplePositiveProfile(Annotation annotation, string profile) {
  profile = annotation.getAStringArrayValue("value") and
  profile.regexpMatch("[A-Za-z0-9][A-Za-z0-9._-]*")
}

predicate exactAdministrativeRole(string role) {
  role = ["ADMIN", "ROLE_ADMIN"]
}

predicate onlyExactAdministrativeAnnotationRoles(Annotation annotation) {
  exists(string role |
    role = annotation.getAStringArrayValue("value") and
    exactAdministrativeRole(role)
  ) and
  not exists(string role |
    role = annotation.getAStringArrayValue("value") and
    not exactAdministrativeRole(role)
  )
}

predicate exactAdministrativePreAuthorizeExpression(string expression) {
  expression = [
    "hasRole('ADMIN')", "hasRole(\"ADMIN\")",
    "hasAuthority('ROLE_ADMIN')", "hasAuthority(\"ROLE_ADMIN\")"
  ]
}

predicate exactPermitAllAnnotation(Annotation annotation) {
  annotation.getType().hasQualifiedName("javax.annotation.security", "PermitAll")
  or annotation.getType().hasQualifiedName("jakarta.annotation.security", "PermitAll")
  or annotation.getType().hasQualifiedName("com.vaadin.flow.server.auth", "AnonymousAllowed")
}

predicate exactRoleAnnotation(Annotation annotation) {
  annotation.getType().hasQualifiedName("javax.annotation.security", "RolesAllowed")
  or annotation.getType().hasQualifiedName("jakarta.annotation.security", "RolesAllowed")
  or annotation.getType().hasQualifiedName("org.springframework.security.access.annotation", "Secured")
}

predicate exactPreAuthorizeAnnotation(Annotation annotation) {
  annotation.getType().hasQualifiedName("org.springframework.security.access.prepost", "PreAuthorize")
}

predicate profileDeployment(
  Method method, Annotation annotation, string value,
  string coverageStatus, string coverageNote
) {
  methodOrTypeAnnotation(method, annotation) and sourceAnnotation(annotation) and
  annotation.getType().hasQualifiedName("org.springframework.context.annotation", "Profile") and
  exists(string profile |
    profile = annotation.getAStringArrayValue("value") and profile != "" and
    value = "profile:" + profile and
    (
      simplePositiveProfile(annotation, profile) and
      not exists(string other |
        other = annotation.getAStringArrayValue("value") and other != profile
      ) and
      coverageStatus = "complete" and coverageNote = "explicit_spring_profile_gate"
      or
      (not simplePositiveProfile(annotation, profile)
       or exists(string other |
            other = annotation.getAStringArrayValue("value") and other != profile
          )) and
      coverageStatus = "partial" and
      coverageNote = "spring_profile_expression_presence_unresolved"
    )
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
    exists(string key, string prefix, string canonicalKey, string expected |
      (key = annotation.getAStringArrayValue("name") or
       key = annotation.getAStringArrayValue("value")) and key != "" and
      not exists(string other |
        (other = annotation.getAStringArrayValue("name") or
         other = annotation.getAStringArrayValue("value")) and
        other != "" and other != key
      ) and
      prefix = annotation.getStringValue("prefix") and
      (
        prefix = "" and canonicalKey = key
        or prefix != "" and prefix.matches("%.") and canonicalKey = prefix + key
        or prefix != "" and not prefix.matches("%.") and
           canonicalKey = prefix + "." + key
      ) and
      expected = annotation.getStringValue("havingValue") and expected != "" and
      annotation.getBooleanValue("matchIfMissing") = false and
      value = "conditional_property:" + canonicalKey + "=" + expected and
      coverageStatus = "complete" and
      coverageNote = "explicit_conditional_property_gate"
    )
    or not exists(string key, string prefix, string canonicalKey, string expected |
         (key = annotation.getAStringArrayValue("name") or
          key = annotation.getAStringArrayValue("value")) and key != "" and
         not exists(string other |
           (other = annotation.getAStringArrayValue("name") or
            other = annotation.getAStringArrayValue("value")) and
           other != "" and other != key
         ) and
         prefix = annotation.getStringValue("prefix") and
         (
           prefix = "" and canonicalKey = key
           or prefix != "" and prefix.matches("%.") and canonicalKey = prefix + key
           or prefix != "" and not prefix.matches("%.") and
              canonicalKey = prefix + "." + key
         ) and
         expected = annotation.getStringValue("havingValue") and expected != "" and
         annotation.getBooleanValue("matchIfMissing") = false
       ) and
       value = "conditional_property_unknown" and coverageStatus = "partial" and
       coverageNote =
         "conditional_property_requires_static_name_value_prefix_and_absence_semantics"
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
  value = "optional" and coverageStatus = "partial" and
  coverageNote = "conditional_presence_default_distribution_unresolved"
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
    exactPermitAllAnnotation(annotation) and
    value = "unauthenticated_annotation" and coverageStatus = "complete" and
    coverageNote = "permit_all"
    or exactPreAuthorizeAnnotation(annotation) and
       annotation.getStringValue("value") = "permitAll()" and
       value = "unauthenticated_annotation" and coverageStatus = "complete" and
       coverageNote = "preauthorize_permit_all"
    or exactPreAuthorizeAnnotation(annotation) and
       annotation.getStringValue("value") = "isAuthenticated()" and
       value = "low_privilege_annotation" and coverageStatus = "complete" and
       coverageNote = "preauthorize_authenticated"
    or exactRoleAnnotation(annotation) and
       onlyExactAdministrativeAnnotationRoles(annotation) and
       value = "privileged_annotation" and coverageStatus = "complete" and
       coverageNote = "exact_administrative_role"
    or exactPreAuthorizeAnnotation(annotation) and
       exactAdministrativePreAuthorizeExpression(annotation.getStringValue("value")) and
       value = "privileged_annotation" and coverageStatus = "complete" and
       coverageNote = "preauthorize_exact_administrative_role"
    or exactRoleAnnotation(annotation) and
       not onlyExactAdministrativeAnnotationRoles(annotation) and
       value = "security_matcher_unknown" and coverageStatus = "partial" and
       coverageNote = "role_requirement_not_proven_administrative"
    or exactPreAuthorizeAnnotation(annotation) and
       not annotation.getStringValue("value") = "permitAll()" and
       not annotation.getStringValue("value") = "isAuthenticated()" and
       not exactAdministrativePreAuthorizeExpression(annotation.getStringValue("value")) and
       value = "security_matcher_unknown" and coverageStatus = "partial" and
       coverageNote = "role_requirement_not_proven_administrative"
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
      exactAdministrativeRole(role) and
      not exists(string other |
        other = constraint.getAStringArrayValue("rolesAllowed") and
        not exactAdministrativeRole(other)
      ) and
      value = "privileged_constraint" and coverageStatus = "complete" and
      coverageNote = "exact_administrative_role"
    )
    or not exists(Annotation constraint, string role |
         constraint = annotation.getValue("value") and
         role = constraint.getAStringArrayValue("rolesAllowed") and role != "" and
         exactAdministrativeRole(role) and
         not exists(string other |
           other = constraint.getAStringArrayValue("rolesAllowed") and
           not exactAdministrativeRole(other)
         )
       ) and
       value = "security_matcher_unknown" and coverageStatus = "partial" and
       coverageNote = "role_requirement_not_proven_administrative"
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
    or rule.getMethod().getName() = "hasRole" and
       rule.getArgument(0) instanceof CompileTimeConstantExpr and
       rule.getArgument(0).(CompileTimeConstantExpr).getStringValue() = "ADMIN" and
       value = "privileged_filter" and coverageStatus = "complete" and
       coverageNote = "static_request_matcher_exact_administrative_role"
    or rule.getMethod().getName() = "hasAuthority" and
       rule.getArgument(0) instanceof CompileTimeConstantExpr and
       rule.getArgument(0).(CompileTimeConstantExpr).getStringValue() = "ROLE_ADMIN" and
       value = "privileged_filter" and coverageStatus = "complete" and
       coverageNote = "static_request_matcher_exact_administrative_role"
    or rule.getMethod().getName() = ["hasRole", "hasAuthority"] and
       not (
         rule.getMethod().getName() = "hasRole" and
         rule.getArgument(0) instanceof CompileTimeConstantExpr and
         rule.getArgument(0).(CompileTimeConstantExpr).getStringValue() = "ADMIN"
         or rule.getMethod().getName() = "hasAuthority" and
            rule.getArgument(0) instanceof CompileTimeConstantExpr and
            rule.getArgument(0).(CompileTimeConstantExpr).getStringValue() = "ROLE_ADMIN"
       ) and
       value = "security_matcher_unknown" and coverageStatus = "partial" and
       coverageNote = "role_requirement_not_proven_administrative"
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
