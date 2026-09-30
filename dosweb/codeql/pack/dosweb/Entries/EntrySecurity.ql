/**
 * @name Entry security and deployment facts
 * @description Extracts source-backed method authorization, Servlet constraints, static Spring Security matchers, and deployment-gate evidence.
 * @kind table
 * @id dosweb/entry-security
 */

import java
import SpringSecurityFallback
import SpringMvcFieldRegistration

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
    or exists(string key, string prefix, string canonicalKey, string expected |
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
      annotation.getBooleanValue("matchIfMissing") = true and
      value = "default_enabled" and coverageStatus = "complete" and
      coverageNote = "conditional_property_match_if_missing_default_enabled"
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
         annotation.getBooleanValue("matchIfMissing") = [false, true]
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
  not SpringSecurityOrderedRules::managedRule(matcher) and
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

predicate exactDefaultStringExpr(Expr expression, string value) {
  expression instanceof StringLiteral and value = expression.(StringLiteral).getValue()
  or exists(FieldAccess access, Field constant |
    expression = access and constant = access.getField() and
    constant.isStatic() and constant.isFinal() and
    exactDefaultStringExpr(constant.getInitializer(), value)
  )
}

predicate propertyGetterDefaultString(
  MethodCall getter, Field sourceField, string value
) {
  getter.getNumArgument() = 0 and getter.getMethod().fromSource() and
  exists(ReturnStmt returned, FieldAccess access |
    returned.getEnclosingCallable() = getter.getMethod() and returned.getExpr() = access and
    sourceField = access.getField() and sourceField.fromSource() and
    not sourceField.isStatic() and
    sourceField.getDeclaringType() = getter.getMethod().getDeclaringType() and
    exactDefaultStringExpr(sourceField.getInitializer(), value) and value != "" and
    not exists(ReturnStmt other |
      other.getEnclosingCallable() = getter.getMethod() and other != returned
    )
  )
}

predicate propertyBackedPermitAllRule(
  MethodCall matcher, MethodCall rule, Field sourceField, string route
) {
  not SpringSecurityOrderedRules::managedRule(matcher) and
  matcher.getMethod().getName() = ["requestMatchers", "antMatchers", "mvcMatchers"] and
  springSecurityDslCall(matcher) and springSecurityDslCall(rule) and
  matcher.getArgument(0) instanceof MethodCall and
  propertyGetterDefaultString(
    matcher.getArgument(0).(MethodCall), sourceField, route
  ) and
  rule.getQualifier() = matcher and rule.getMethod().getName() = "permitAll"
}

predicate dynamicSecurityRule(MethodCall matcher, string coverageNote) {
  not SpringSecurityOrderedRules::managedRule(matcher) and
  matcher.getMethod().getName() = ["requestMatchers", "antMatchers", "mvcMatchers"] and
  springSecurityDslCall(matcher) and
  not matcher.getArgument(0) instanceof CompileTimeConstantExpr and
  coverageNote = "dynamic_security_matcher_partial"
}

predicate hswebExactAnnotation(Annotation annotation, string name) {
  annotation.getType().hasQualifiedName(
    "org.hswebframework.web.authorization.annotation", name
  ) and
  name = ["Authorize", "Dimension", "Resource", "ResourceAction", "Dimensions"]
}

predicate hswebAnnotationOrMeta(Annotation annotation, string name) {
  hswebExactAnnotation(annotation, name)
  or exists(Annotation meta |
    meta = annotation.getType().getAnAnnotation() and
    hswebAnnotationOrMeta(meta, name)
  )
}

predicate hswebEffectiveAnnotation(Method method, Annotation annotation) {
  annotation = method.getAnAnnotation()
  or annotation = method.getAnOverride().getAnAnnotation()
  or exists(RefType owner |
    owner = method.getDeclaringType().getASupertype*() and
    annotation = owner.getAnAnnotation()
  )
}

predicate hswebEffectiveMethodAuthorize(Method method, Annotation annotation) {
  hswebExactAnnotation(annotation, "Authorize") and
  (
    annotation = method.getAnAnnotation()
    or annotation = method.getAnOverride().getAnAnnotation()
  )
}

predicate hswebEffectiveClassAuthorize(Method method, Annotation annotation) {
  hswebExactAnnotation(annotation, "Authorize") and
  exists(RefType owner |
    owner = method.getDeclaringType().getASupertype*() and
    annotation = owner.getAnAnnotation()
  )
}

predicate hswebDefaultRuntimeAvailable() {
  exists(RefType parserContract, RefType defaultParser, RefType customizerContract,
         RefType authorizingController, RefType authorizeType,
         Method anonymousMember, Method ignoreMember, Method customizerSetter |
    parserContract.hasQualifiedName(
      "org.hswebframework.web.authorization.basic.aop",
      "AopMethodAuthorizeDefinitionParser"
    ) and
    defaultParser.hasQualifiedName(
      "org.hswebframework.web.authorization.basic.aop",
      "DefaultAopMethodAuthorizeDefinitionParser"
    ) and
    customizerContract.hasQualifiedName(
      "org.hswebframework.web.authorization.basic.aop",
      "AopMethodAuthorizeDefinitionCustomizerParser"
    ) and
    authorizingController.hasQualifiedName(
      "org.hswebframework.web.authorization.basic.aop", "AopAuthorizingController"
    ) and
    authorizeType.hasQualifiedName(
      "org.hswebframework.web.authorization.annotation", "Authorize"
    ) and
    anonymousMember.getDeclaringType() = authorizeType and
    anonymousMember.getName() = "anonymous" and
    ignoreMember.getDeclaringType() = authorizeType and ignoreMember.getName() = "ignore" and
    customizerSetter.getDeclaringType() = defaultParser and
    customizerSetter.getName() = "setParserCustomizers" and
    forall(string name |
      name = ["Dimension", "Resource", "ResourceAction"]
      |
      exists(RefType annotationType |
        annotationType.hasQualifiedName(
          "org.hswebframework.web.authorization.annotation", name
        )
      )
    )
  )
}

predicate hswebSourceCustomizerPresent() {
  exists(RefType type |
    type.fromSource() and
    not type.hasQualifiedName(
      "org.hswebframework.web.authorization.basic.aop",
      "AopMethodAuthorizeDefinitionCustomizerParser"
    ) and
    type.getASupertype+().hasQualifiedName(
      "org.hswebframework.web.authorization.basic.aop",
      "AopMethodAuthorizeDefinitionCustomizerParser"
    )
  )
}

predicate hswebSourceParserOverridePresent() {
  exists(RefType type |
    type.fromSource() and
    not type.hasQualifiedName(
      "org.hswebframework.web.authorization.basic.aop",
      ["AopMethodAuthorizeDefinitionParser", "DefaultAopMethodAuthorizeDefinitionParser"]
    ) and
    type.getASupertype+().hasQualifiedName(
      "org.hswebframework.web.authorization.basic.aop",
      "AopMethodAuthorizeDefinitionParser"
    )
  )
}

predicate hswebComposedAnnotation(Method method, Annotation annotation) {
  hswebEffectiveAnnotation(method, annotation) and sourceAnnotation(annotation) and
  not hswebExactAnnotation(annotation, _) and
  exists(string name | hswebAnnotationOrMeta(annotation, name))
}

predicate hswebConflictingSecurityAnnotation(Method method, Annotation annotation) {
  sourceAnnotation(annotation) and
  exists(string value, string coverageStatus, string coverageNote |
    annotationAuth(method, annotation, value, coverageStatus, coverageNote)
  )
}

predicate springMappedHandler(Method method) {
  exists(Annotation mapping |
    mapping = method.getAnAnnotation() and
    mapping.getType().hasQualifiedName(
      "org.springframework.web.bind.annotation",
      ["RequestMapping", "GetMapping", "PostMapping", "PutMapping",
       "DeleteMapping", "PatchMapping"]
    )
  )
}

predicate hswebEffectiveIgnore(Method method, Annotation annotation) {
  annotation.getBooleanValue("ignore") = true and
  (
    hswebEffectiveMethodAuthorize(method, annotation) and
    not exists(Annotation other |
      hswebEffectiveMethodAuthorize(method, other) and
      other.getBooleanValue("ignore") = false
    )
    or hswebEffectiveClassAuthorize(method, annotation) and
       not exists(Annotation methodAnnotation |
         hswebEffectiveMethodAuthorize(method, methodAnnotation)
       ) and
       not exists(Annotation other |
         hswebEffectiveClassAuthorize(method, other) and
         other.getBooleanValue("ignore") = false
       )
  )
}

predicate hswebEffectiveAnonymous(Method method, Annotation annotation) {
  hswebEffectiveAnnotation(method, annotation) and
  hswebExactAnnotation(annotation, "Authorize") and
  annotation.getBooleanValue("anonymous") = true
}

predicate hswebHandlerSecurity(
  Method method, string factFile, int factLine, string kind, string value,
  string coverageStatus, string coverageNote
) {
  method.fromSource() and springMappedHandler(method) and
  hswebDefaultRuntimeAvailable() and
  (
    hswebSourceCustomizerPresent() and
    factFile = method.getLocation().getFile().getRelativePath() and
    factLine = method.getLocation().getStartLine() and
    kind = "dependency_coverage" and value = "hsweb_customizer_unmodeled" and
    coverageStatus = "partial" and
    coverageNote = "hsweb_customizer_precedes_default_parser"
    or not hswebSourceCustomizerPresent() and hswebSourceParserOverridePresent() and
       factFile = method.getLocation().getFile().getRelativePath() and
       factLine = method.getLocation().getStartLine() and
       kind = "dependency_coverage" and value = "hsweb_parser_override_unmodeled" and
       coverageStatus = "partial" and coverageNote = "hsweb_default_parser_replaced"
    or not hswebSourceCustomizerPresent() and not hswebSourceParserOverridePresent() and
       exists(Annotation annotation |
         hswebConflictingSecurityAnnotation(method, annotation) and
         factFile = annotation.getLocation().getFile().getRelativePath() and
         factLine = annotation.getLocation().getStartLine() and
         kind = "dependency_coverage" and
         value = "hsweb_conflicting_security_model_unmodeled" and
         coverageStatus = "partial" and coverageNote = "hsweb_conflicting_security_model"
       )
    or not hswebSourceCustomizerPresent() and not hswebSourceParserOverridePresent() and
       not exists(Annotation conflict |
         hswebConflictingSecurityAnnotation(method, conflict)
       ) and
       exists(Annotation annotation |
         hswebComposedAnnotation(method, annotation) and
         factFile = annotation.getLocation().getFile().getRelativePath() and
         factLine = annotation.getLocation().getStartLine() and
         kind = "dependency_coverage" and value = "hsweb_composed_annotation_unmodeled" and
         coverageStatus = "partial" and coverageNote = "hsweb_composed_annotation_unmodeled"
       )
    or not hswebSourceCustomizerPresent() and not hswebSourceParserOverridePresent() and
       not exists(Annotation conflict |
         hswebConflictingSecurityAnnotation(method, conflict)
       ) and
       not exists(Annotation composed | hswebComposedAnnotation(method, composed)) and
       exists(Annotation annotation |
         hswebEffectiveIgnore(method, annotation) and
         factFile = annotation.getLocation().getFile().getRelativePath() and
         factLine = annotation.getLocation().getStartLine() and kind = "annotation" and
         value = "unauthenticated_annotation" and coverageStatus = "complete" and
         coverageNote = "hsweb_authorize_ignore"
       )
    or not hswebSourceCustomizerPresent() and not hswebSourceParserOverridePresent() and
       not exists(Annotation conflict |
         hswebConflictingSecurityAnnotation(method, conflict)
       ) and
       not exists(Annotation composed | hswebComposedAnnotation(method, composed)) and
       not exists(Annotation ignored | hswebEffectiveIgnore(method, ignored)) and
       exists(Annotation annotation |
         hswebEffectiveAnonymous(method, annotation) and
         factFile = annotation.getLocation().getFile().getRelativePath() and
         factLine = annotation.getLocation().getStartLine() and kind = "annotation" and
         value = "unauthenticated_annotation" and coverageStatus = "complete" and
         coverageNote = "hsweb_authorize_anonymous"
       )
    or not hswebSourceCustomizerPresent() and not hswebSourceParserOverridePresent() and
       not exists(Annotation conflict |
         hswebConflictingSecurityAnnotation(method, conflict)
       ) and
       not exists(Annotation composed | hswebComposedAnnotation(method, composed)) and
       not exists(Annotation annotation, string name |
         hswebEffectiveAnnotation(method, annotation) and
         hswebAnnotationOrMeta(annotation, name)
       ) and
       factFile = method.getLocation().getFile().getRelativePath() and
       factLine = method.getLocation().getStartLine() and kind = "annotation" and
       value = "unauthenticated_annotation" and coverageStatus = "complete" and
       coverageNote = "hsweb_default_parser_empty_definition"
    or not hswebSourceCustomizerPresent() and not hswebSourceParserOverridePresent() and
       not exists(Annotation conflict |
         hswebConflictingSecurityAnnotation(method, conflict)
       ) and
       not exists(Annotation composed | hswebComposedAnnotation(method, composed)) and
       not exists(Annotation ignored | hswebEffectiveIgnore(method, ignored)) and
       not exists(Annotation anonymous | hswebEffectiveAnonymous(method, anonymous)) and
       exists(Annotation annotation, string name |
         hswebEffectiveAnnotation(method, annotation) and
         hswebExactAnnotation(annotation, name) and
         factFile = annotation.getLocation().getFile().getRelativePath() and
         factLine = annotation.getLocation().getStartLine() and
         kind = "dependency_coverage" and value = "hsweb_authorization_unmodeled" and
         coverageStatus = "partial" and coverageNote = "hsweb_authorization_requires_auth"
       )
  )
}

predicate springMvcHandlerInterceptorType(RefType type) {
  type.getASupertype*().hasQualifiedName(
    "org.springframework.web.servlet", ["HandlerInterceptor", "AsyncHandlerInterceptor"]
  )
}

predicate springMvcUnauthorizedStatus(Expr status) {
  status.(CompileTimeConstantExpr).getIntValue() = 401
  or exists(MethodCall valueCall, FieldAccess statusField |
    status = valueCall and valueCall.getMethod().getName() = "value" and
    valueCall.getMethod().getDeclaringType().hasQualifiedName(
      "org.springframework.http", "HttpStatus"
    ) and
    valueCall.getQualifier() = statusField and
    statusField.getField().getName() = "UNAUTHORIZED"
  )
}

predicate springMvcUnauthorizedRejection(MethodCall rejection) {
  rejection.getMethod().getName() = "sendError" and
  springMvcUnauthorizedStatus(rejection.getArgument(0))
}

predicate springMvcRejectBranch(Method preHandle, IfStmt guard) {
  exists(MethodCall rejection, ReturnStmt rejected |
    rejection.getEnclosingCallable() = preHandle and
    springMvcUnauthorizedRejection(rejection) and
    rejected.getEnclosingCallable() = preHandle and
    rejected.getExpr().(BooleanLiteral).getBooleanValue() = false and
    rejected.getParent*() = guard.getThen()
  )
}

predicate springMvcSecurityPreHandle(RefType interceptorType, Method preHandle) {
  springMvcHandlerInterceptorType(interceptorType) and preHandle.fromSource() and
  preHandle.getName() = "preHandle" and
  interceptorType.getASupertype*() = preHandle.getDeclaringType() and
  exists(IfStmt guard | springMvcRejectBranch(preHandle, guard))
}

predicate springMvcAddSecurityInterceptor(
  MethodCall addInterceptor, RefType interceptorType, Method preHandle
) {
  SpringMvcFieldBindings::registrationSemanticsKnown(addInterceptor) and
  addInterceptor.getMethod().hasQualifiedName(
    "org.springframework.web.servlet.config.annotation",
    "InterceptorRegistry", "addInterceptor"
  ) and
  (
    addInterceptor.getArgument(0) instanceof ClassInstanceExpr and
    interceptorType = addInterceptor.getArgument(0).(ClassInstanceExpr).getConstructedType()
    or SpringMvcFieldBindings::target(addInterceptor, interceptorType)
  ) and
  springMvcSecurityPreHandle(interceptorType, preHandle)
}

predicate springMvcInterceptorRegistrationChain(
  MethodCall registration, MethodCall addInterceptor,
  RefType interceptorType, Method preHandle
) {
  registration = addInterceptor and
  springMvcAddSecurityInterceptor(addInterceptor, interceptorType, preHandle)
  or exists(MethodCall previous |
    registration.getMethod().getDeclaringType().hasQualifiedName(
      "org.springframework.web.servlet.config.annotation", "InterceptorRegistration"
    ) and
    registration.getQualifier() = previous and
    springMvcInterceptorRegistrationChain(
      previous, addInterceptor, interceptorType, preHandle
    )
  )
}

predicate springMvcExcludedSecurityRoute(
  MethodCall exclusion, Method preHandle, string route
) {
  exists(MethodCall registration, MethodCall addInterceptor, RefType interceptorType,
         CompileTimeConstantExpr pattern |
    exclusion.getMethod().hasQualifiedName(
      "org.springframework.web.servlet.config.annotation",
      "InterceptorRegistration", "excludePathPatterns"
    ) and
    exclusion.getQualifier() = registration and
    springMvcInterceptorRegistrationChain(
      registration, addInterceptor, interceptorType, preHandle
    ) and
    pattern = exclusion.getAnArgument() and route = pattern.getStringValue() and route != ""
  )
}

predicate springMvcNegatedHelperBypassesRejection(
  Method preHandle, Method helper
) {
  exists(IfStmt guard, LogNotExpr negation, MethodCall helperCall,
         ReturnStmt allowed |
    springMvcSecurityPreHandle(preHandle.getDeclaringType(), preHandle) and
    guard.getEnclosingCallable() = preHandle and
    guard.getCondition() = negation and negation.getOperand() = helperCall and
    helperCall.getMethod() = helper and helper.isPrivate() and helper.fromSource() and
    helper.getNumberOfParameters() = 1 and
    helper.getParameter(0).getType().hasName("String") and
    springMvcRejectBranch(preHandle, guard) and
    allowed.getEnclosingCallable() = preHandle and
    allowed.getExpr().(BooleanLiteral).getBooleanValue() = true and
    not allowed.getParent*() = guard.getThen()
  )
}

predicate springMvcHelperStringCheck(
  Method helper, MethodCall check, string comparison, string mode
) {
  check.getEnclosingCallable() = helper and
  (
    check.getMethod().hasQualifiedName("java.lang", "String", "startsWith") and
    check.getQualifier().(VarAccess).getVariable() = helper.getParameter(0) and
    comparison = check.getArgument(0).(CompileTimeConstantExpr).getStringValue() and
    mode = "prefix"
    or check.getMethod().hasQualifiedName("java.lang", "String", "equals") and
       check.getQualifier().(VarAccess).getVariable() = helper.getParameter(0) and
       comparison = check.getArgument(0).(CompileTimeConstantExpr).getStringValue() and
       mode = "exact"
    or check.getMethod().hasQualifiedName("java.lang", "String", "equals") and
       check.getQualifier() instanceof CompileTimeConstantExpr and
       comparison = check.getQualifier().(CompileTimeConstantExpr).getStringValue() and
       check.getArgument(0).(VarAccess).getVariable() = helper.getParameter(0) and
       mode = "exact"
  ) and
  comparison != ""
}

predicate springMvcStaticMappingRoute(Annotation annotation, string route) {
  sourceAnnotation(annotation) and
  annotation.getType().hasQualifiedName(
    "org.springframework.web.bind.annotation",
    ["RequestMapping", "GetMapping", "PostMapping", "PutMapping",
     "DeleteMapping", "PatchMapping"]
  ) and
  (route = annotation.getAStringArrayValue("value") or
   route = annotation.getAStringArrayValue("path")) and
  route != ""
}

string springMvcMappingPath(Annotation annotation) {
  result = annotation.getAStringArrayValue("value")
  or result = annotation.getAStringArrayValue("path")
  or result = "" and
     not exists(string value |
       value = annotation.getAStringArrayValue("value") or
       value = annotation.getAStringArrayValue("path")
     )
}

string springMvcClassMappingPath(Method method) {
  exists(Annotation annotation |
    annotation = method.getDeclaringType().getAnAnnotation() and
    annotation.getType().hasQualifiedName(
      "org.springframework.web.bind.annotation", "RequestMapping"
    ) and
    result = springMvcMappingPath(annotation)
  )
  or result = "" and
     not exists(Annotation annotation |
       annotation = method.getDeclaringType().getAnAnnotation() and
       annotation.getType().hasQualifiedName(
         "org.springframework.web.bind.annotation", "RequestMapping"
       ) and
       springMvcMappingPath(annotation) != ""
     )
}

predicate springMvcHandlerRoute(Method method, string route) {
  exists(Annotation mapping, string classPath, string methodPath |
    method.fromSource() and mapping = method.getAnAnnotation() and
    springMvcStaticMappingRoute(mapping, methodPath) and
    classPath = springMvcClassMappingPath(method) and
    (
      classPath = "" and route = methodPath
      or methodPath = "" and route = classPath
      or classPath != "" and methodPath != "" and
         classPath.matches("%/") and methodPath.matches("/%") and
         route = classPath + methodPath.substring(1, methodPath.length())
      or classPath != "" and methodPath != "" and
         not (classPath.matches("%/") and methodPath.matches("/%")) and
         not classPath.matches("%/") and not methodPath.matches("/%") and
         route = classPath + "/" + methodPath
      or classPath != "" and methodPath != "" and
         (classPath.matches("%/") or methodPath.matches("/%")) and
         not (classPath.matches("%/") and methodPath.matches("/%")) and
         route = classPath + methodPath
    ) and
    route != ""
  )
}

predicate springMvcHelperAllowlistRoute(
  Method helper, MethodCall check, string route, string coverageNote
) {
  exists(string comparison |
    springMvcHelperStringCheck(helper, check, comparison, "exact") and
    route = comparison and
    coverageNote = "spring_mvc_security_interceptor_helper_exact_allowlist"
  )
  or exists(string prefix |
    springMvcHelperStringCheck(helper, check, prefix, "prefix") and
    exists(Method mapped |
      springMvcHandlerRoute(mapped, route) and route.matches(prefix + "%")
    ) and
    coverageNote = "spring_mvc_security_interceptor_helper_prefix_allowlist"
  )
  or exists(string prefix |
    springMvcHelperStringCheck(helper, check, prefix, "prefix") and
    prefix.matches("%/") and route = prefix + "**" and
    coverageNote = "spring_mvc_security_interceptor_helper_prefix_allowlist"
  )
}

predicate methodCallStoredInLocal(MethodCall call, LocalVariableDecl variable) {
  variable.getInitializer() = call
  or exists(AssignExpr assignment, VarAccess destination |
    assignment.getSource() = call and assignment.getDest() = destination and
    destination.getVariable() = variable
  )
}

predicate springMvcAnnotationLookupAllowsMissing(
  Method preHandle, RefType targetAnnotation, MethodCall lookup
) {
  exists(LocalVariableDecl annotationVariable, TypeLiteral annotationLiteral,
         IfStmt missingGuard, EQExpr missing,
         ReturnStmt allowed |
    lookup.getEnclosingCallable() = preHandle and
    // Preserve supported inherited framework APIs, but never borrow their
    // summary for a user-defined overriding implementation.
    (
      lookup.getMethod().hasQualifiedName(
        "org.springframework.web.method", "HandlerMethod", "getMethodAnnotation"
      )
      or lookup.getMethod().hasQualifiedName(
        "org.springframework.core.annotation", "AnnotatedMethod", "getMethodAnnotation"
      )
    ) and
    lookup.getQualifier().getType().getErasure().(RefType).getASupertype*()
      .hasQualifiedName("org.springframework.web.method", "HandlerMethod") and
    annotationLiteral = lookup.getArgument(0) and
    targetAnnotation = annotationLiteral.getReferencedType().(RefType) and
    methodCallStoredInLocal(lookup, annotationVariable) and
    annotationVariable.getEnclosingCallable() = preHandle and
    missingGuard.getEnclosingCallable() = preHandle and missingGuard.getCondition() = missing and
    (
      missing.getLeftOperand().(VarAccess).getVariable() = annotationVariable and
      missing.getRightOperand() instanceof NullLiteral
      or missing.getRightOperand().(VarAccess).getVariable() = annotationVariable and
         missing.getLeftOperand() instanceof NullLiteral
    ) and
    allowed.getEnclosingCallable() = preHandle and
    allowed.getExpr().(BooleanLiteral).getBooleanValue() = true and
    allowed.getParent*() = missingGuard.getThen()
  )
}

predicate springMvcAnnotationAbsentBypass(
  Method handler, string route, Method preHandle, MethodCall lookup
) {
  exists(MethodCall registration, RefType interceptorType, RefType targetAnnotation |
    springMvcAddSecurityInterceptor(registration, interceptorType, preHandle) and
    springMvcAnnotationLookupAllowsMissing(preHandle, targetAnnotation, lookup) and
    springMvcHandlerRoute(handler, route) and
    springMvcRouteCoveredByRegisteredServletFilter(route) and
    not exists(Annotation annotation |
      annotation = handler.getAnAnnotation() and annotation.getType() = targetAnnotation
    )
  )
}

predicate filterRegistrationLocal(LocalVariableDecl registration) {
  registration.getInitializer() instanceof ClassInstanceExpr and
  registration.getInitializer().(ClassInstanceExpr).getConstructedType().getErasure().(RefType)
    .hasQualifiedName(
      "org.springframework.boot.web.servlet", "FilterRegistrationBean"
    )
}

predicate filterRegistrationCall(
  LocalVariableDecl registration, MethodCall call, string name
) {
  filterRegistrationLocal(registration) and
  call.getQualifier().(VarAccess).getVariable() = registration and
  call.getEnclosingCallable() = registration.getEnclosingCallable() and
  call.getMethod().getName() = name
}

bindingset[route]
predicate springMvcRouteCoveredByRegisteredServletFilter(string route) {
  exists(LocalVariableDecl registration, MethodCall addPattern,
         CompileTimeConstantExpr pattern |
    filterRegistrationCall(registration, addPattern, "addUrlPatterns") and
    pattern = addPattern.getAnArgument() and
    servletPatternMatchesRoute(pattern.getStringValue(), route)
  )
}

bindingset[pattern, route]
predicate servletPatternMatchesRoute(string pattern, string route) {
  pattern = route
  or pattern = "/*" and route.matches("/%")
  or exists(string prefix |
    pattern = prefix + "/*" and prefix != "" and
    (route = prefix or route.matches(prefix + "/%"))
  )
  or exists(string suffix |
    pattern = "*." + suffix and suffix != "" and route.matches("%." + suffix)
  )
}

predicate orderedServletFilterWithAnnotationBypassWitness(
  Method filterMethod, MethodCall orderCall, Method publicHandler, string publicRoute
) {
  exists(LocalVariableDecl registration, MethodCall setFilter, MethodCall addPattern,
         ClassInstanceExpr filterInstance, RefType filterType,
         CompileTimeConstantExpr pattern, int orderValue |
    filterRegistrationCall(registration, setFilter, "setFilter") and
    filterInstance = setFilter.getArgument(0) and
    filterType = filterInstance.getConstructedType().getErasure().(RefType).getSourceDeclaration() and
    filterMethod.fromSource() and filterMethod.getDeclaringType() = filterType and
    filterMethod.getName() = "doFilter" and filterMethod.getNumberOfParameters() = 3 and
    filterRegistrationCall(registration, addPattern, "addUrlPatterns") and
    pattern = addPattern.getAnArgument() and
    servletPatternMatchesRoute(pattern.getStringValue(), publicRoute) and
    filterRegistrationCall(registration, orderCall, "setOrder") and
    orderValue = orderCall.getArgument(0).(CompileTimeConstantExpr).getIntValue() and
    exists(Method preHandle, MethodCall lookup |
      springMvcAnnotationAbsentBypass(publicHandler, publicRoute, preHandle, lookup)
    )
  )
}

predicate componentOncePerRequestFilterMethod(Method filterMethod) {
  exists(RefType filterType, Annotation component |
    filterMethod.fromSource() and filterMethod.getName() = "doFilterInternal" and
    filterType = filterMethod.getDeclaringType() and
    filterType.getASupertype*().hasQualifiedName(
      "org.springframework.web.filter", "OncePerRequestFilter"
    ) and
    component = filterType.getAnAnnotation() and
    component.getType().hasQualifiedName(
      "org.springframework.stereotype", "Component"
    ) and
    (
      not exists(Method skip |
        skip.fromSource() and skip.getDeclaringType() = filterType and
        skip.getName() = "shouldNotFilter"
      )
      or exists(Method skip, ReturnStmt returned |
        skip.fromSource() and skip.getDeclaringType() = filterType and
        skip.getName() = "shouldNotFilter" and
        returned.getEnclosingCallable() = skip and
        returned.getExpr().(BooleanLiteral).getBooleanValue() = false and
        forall(ReturnStmt other |
          other.getEnclosingCallable() = skip
          |
          other.getExpr().(BooleanLiteral).getBooleanValue() = false
        )
      )
    )
  )
}

predicate shiroCommittedOrderedMap(
  LocalVariableDecl map, MethodCall setter
) {
  map.getInitializer() instanceof ClassInstanceExpr and
  map.getInitializer().(ClassInstanceExpr).getConstructedType().getErasure().(RefType)
    .hasQualifiedName("java.util", "LinkedHashMap") and
  setter.getMethod().getName() = "setFilterChainDefinitionMap" and
  setter.getMethod().getDeclaringType().getASupertype*().hasQualifiedName(
    "org.apache.shiro.spring.web", "ShiroFilterFactoryBean"
  ) and
  setter.getArgument(0).(VarAccess).getVariable() = map and
  setter.getEnclosingCallable() = map.getEnclosingCallable()
}

predicate shiroMapCall(LocalVariableDecl map, MethodCall call) {
  call.getQualifier().(VarAccess).getVariable() = map and
  call.getEnclosingCallable() = map.getEnclosingCallable()
}

predicate shiroStaticRule(
  LocalVariableDecl map, MethodCall put, string pattern, string chain
) {
  shiroMapCall(map, put) and put.getMethod().getName() = "put" and
  pattern = put.getArgument(0).(CompileTimeConstantExpr).getStringValue() and
  chain = put.getArgument(1).(CompileTimeConstantExpr).getStringValue() and
  pattern != "" and chain != ""
}

predicate shiroCallBefore(MethodCall earlier, MethodCall later) {
  earlier.getLocation().getFile() = later.getLocation().getFile() and
  (
    earlier.getLocation().getStartLine() < later.getLocation().getStartLine()
    or earlier.getLocation().getStartLine() = later.getLocation().getStartLine() and
       earlier.getLocation().getStartColumn() < later.getLocation().getStartColumn()
  )
}

bindingset[pattern, route]
predicate shiroPatternMatches(string pattern, string route) {
  pattern = route
  or pattern = "/**" and route.matches("/%")
  or exists(string prefix |
    pattern = prefix + "/**" and prefix != "" and
    (route = prefix or route.matches(prefix + "/%"))
  )
  or exists(string prefix |
    pattern = prefix + "**" and prefix != "" and route.matches(prefix + "%")
  )
}

bindingset[route]
predicate shiroFirstStaticRule(
  LocalVariableDecl map, MethodCall selected, MethodCall setter,
  string route, string pattern, string chain
) {
  shiroCommittedOrderedMap(map, setter) and
  shiroStaticRule(map, selected, pattern, chain) and
  shiroCallBefore(selected, setter) and shiroPatternMatches(pattern, route) and
  not exists(MethodCall earlier, string earlierPattern, string earlierChain |
    shiroStaticRule(map, earlier, earlierPattern, earlierChain) and
    shiroCallBefore(earlier, selected) and shiroPatternMatches(earlierPattern, route)
  )
}

bindingset[chain]
predicate shiroAnonymousToken(string chain) {
  chain.regexpMatch("(^|.*,)[ ]*anon[ ]*(,.*|$)")
}

bindingset[chain]
predicate shiroLowPrivilegeToken(string chain) {
  chain.regexpMatch("(^|.*,)[ ]*(user|authc)[ ]*(,.*|$)")
}

bindingset[chain]
predicate shiroPrivilegedToken(string chain) {
  chain.regexpMatch(
    "(^|.*,)[ ]*(roles\\[[^]]*\\]|perms\\[[^]]*\\]|admin)[ ]*(,.*|$)"
  )
}

bindingset[chain]
predicate shiroChainClassification(
  string chain, string value, string coverageStatus, string coverageNote
) {
  shiroAnonymousToken(chain) and not shiroLowPrivilegeToken(chain) and
  not shiroPrivilegedToken(chain) and value = "unauthenticated_filter" and
  coverageStatus = "complete" and coverageNote = "shiro_ordered_anon_rule"
  or shiroLowPrivilegeToken(chain) and not shiroAnonymousToken(chain) and
     not shiroPrivilegedToken(chain) and value = "low_privilege_filter" and
     coverageStatus = "complete" and coverageNote = "shiro_ordered_authenticated_rule"
  or shiroPrivilegedToken(chain) and not shiroAnonymousToken(chain) and
     not shiroLowPrivilegeToken(chain) and value = "privileged_filter" and
     coverageStatus = "complete" and coverageNote = "shiro_ordered_privileged_rule"
  or (
       shiroAnonymousToken(chain) and shiroLowPrivilegeToken(chain)
       or shiroAnonymousToken(chain) and shiroPrivilegedToken(chain)
       or shiroLowPrivilegeToken(chain) and shiroPrivilegedToken(chain)
     ) and
     value = "security_matcher_unknown" and coverageStatus = "partial" and
     coverageNote = "shiro_conflicting_filter_chain"
  or not shiroAnonymousToken(chain) and not shiroLowPrivilegeToken(chain) and
     not shiroPrivilegedToken(chain) and value = "security_matcher_unknown" and
     coverageStatus = "partial" and coverageNote = "shiro_filter_chain_unmodeled"
}

predicate shiroDynamicMapMutation(LocalVariableDecl map, MethodCall mutation) {
  shiroMapCall(map, mutation) and
  (
    mutation.getMethod().getName() = "putAll"
    or mutation.getMethod().getName() = "put" and
       not (
         mutation.getArgument(0) instanceof CompileTimeConstantExpr and
         mutation.getArgument(1) instanceof CompileTimeConstantExpr
       )
    or mutation.getMethod().getName() = ["clear", "remove", "replace", "replaceAll"]
  )
}

predicate authRow(
  string handlerFqn, string handlerFile, int handlerLine, string routeOrEvent,
  string factFile, int factLine, string kind, string value,
  string coverageStatus, string coverageNote
) {
  exists(MethodCall exclusion, MethodCall add, Method owner, CompileTimeConstantExpr pattern |
    add.getMethod().hasQualifiedName(
      "org.springframework.web.servlet.config.annotation", "InterceptorRegistry", "addInterceptor"
    ) and
    exclusion.getMethod().hasQualifiedName(
      "org.springframework.web.servlet.config.annotation", "InterceptorRegistration", "excludePathPatterns"
    ) and SpringMvcFieldBindings::rootedRegistrationCall(exclusion, add) and
    not SpringMvcFieldBindings::registrationSemanticsKnown(add) and
    pattern = exclusion.getAnArgument() and routeOrEvent = pattern.getStringValue() and
    owner = add.getEnclosingCallable() and owner.fromSource() and
    handlerFqn = owner.getDeclaringType().getQualifiedName() + "." + owner.getName() and
    handlerFile = owner.getLocation().getFile().getRelativePath() and
    handlerLine = owner.getLocation().getStartLine() and
    factFile = exclusion.getLocation().getFile().getRelativePath() and
    factLine = exclusion.getLocation().getStartLine() and
    kind = "dependency_coverage" and value = "mvc_interceptor_registration_unmodeled" and
    coverageStatus = "partial" and coverageNote = "mvc_interceptor_matching_strategy_or_registration_unresolved"
  ) or

  exists(Method mapped, MethodCall evidence |
    springMvcHandlerRoute(mapped, routeOrEvent) and
    SpringSecurityOrderedRules::routeFact(routeOrEvent, evidence, value, coverageStatus, coverageNote) and
    handlerFqn = mapped.getDeclaringType().getQualifiedName() + "." + mapped.getName() and
    handlerFile = mapped.getLocation().getFile().getRelativePath() and
    handlerLine = mapped.getLocation().getStartLine() and
    factFile = evidence.getLocation().getFile().getRelativePath() and
    factLine = evidence.getLocation().getStartLine() and
    kind = "security_filter_chain"
  ) or

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
  or exists(MethodCall matcher, MethodCall rule, Field sourceField, Method method |
    propertyBackedPermitAllRule(matcher, rule, sourceField, routeOrEvent) and
    method = matcher.getEnclosingCallable() and method.fromSource() and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and
    factFile = sourceField.getLocation().getFile().getRelativePath() and
    factLine = sourceField.getLocation().getStartLine() and kind = "security_filter_chain" and
    value = "unauthenticated_filter" and coverageStatus = "complete" and
    coverageNote = "property_backed_default_request_matcher_permitAll"
  )
  or exists(Method method |
    hswebHandlerSecurity(
      method, factFile, factLine, kind, value, coverageStatus, coverageNote
    ) and
    handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and
    handlerLine = method.getLocation().getStartLine() and routeOrEvent = ""
  )
  or exists(MethodCall exclusion, Method preHandle |
    springMvcExcludedSecurityRoute(exclusion, preHandle, routeOrEvent) and
    handlerFqn = preHandle.getDeclaringType().getQualifiedName() + "." +
      preHandle.getName() and
    handlerFile = preHandle.getLocation().getFile().getRelativePath() and
    handlerLine = preHandle.getLocation().getStartLine() and
    factFile = exclusion.getLocation().getFile().getRelativePath() and
    factLine = exclusion.getLocation().getStartLine() and
    kind = "security_filter_chain" and value = "unauthenticated_filter" and
    coverageStatus = "complete" and
    coverageNote = "spring_mvc_security_interceptor_excluded_path"
  )
  or exists(Method preHandle, Method helper, MethodCall check |
    springMvcNegatedHelperBypassesRejection(preHandle, helper) and
    springMvcHelperAllowlistRoute(helper, check, routeOrEvent, coverageNote) and
    handlerFqn = preHandle.getDeclaringType().getQualifiedName() + "." +
      preHandle.getName() and
    handlerFile = preHandle.getLocation().getFile().getRelativePath() and
    handlerLine = preHandle.getLocation().getStartLine() and
    factFile = check.getLocation().getFile().getRelativePath() and
    factLine = check.getLocation().getStartLine() and
    kind = "security_filter_chain" and value = "unauthenticated_filter" and
    coverageStatus = "complete"
  )
  or exists(Method mapped, Method preHandle, MethodCall lookup |
    springMvcAnnotationAbsentBypass(mapped, routeOrEvent, preHandle, lookup) and
    handlerFqn = mapped.getDeclaringType().getQualifiedName() + "." + mapped.getName() and
    handlerFile = mapped.getLocation().getFile().getRelativePath() and
    handlerLine = mapped.getLocation().getStartLine() and
    factFile = lookup.getLocation().getFile().getRelativePath() and
    factLine = lookup.getLocation().getStartLine() and kind = "security_filter_chain" and
    value = "unauthenticated_filter" and coverageStatus = "complete" and
    coverageNote = "spring_mvc_annotation_absent_interceptor_bypass"
  )
  or exists(Method filterMethod, MethodCall orderCall, Method publicHandler,
            string publicRoute |
    orderedServletFilterWithAnnotationBypassWitness(
      filterMethod, orderCall, publicHandler, publicRoute
    ) and
    handlerFqn = filterMethod.getDeclaringType().getQualifiedName() + "." +
      filterMethod.getName() and
    handlerFile = filterMethod.getLocation().getFile().getRelativePath() and
    handlerLine = filterMethod.getLocation().getStartLine() and routeOrEvent = "" and
    factFile = orderCall.getLocation().getFile().getRelativePath() and
    factLine = orderCall.getLocation().getStartLine() and kind = "security_filter_chain" and
    value = "unauthenticated_filter" and coverageStatus = "complete" and
    coverageNote =
      "ordered_servlet_filter_precedes_annotation_gated_mvc_interceptor"
  )
  or exists(Method filterMethod, MethodCall matcher, MethodCall rule, Field sourceField,
            string permitAllRoute |
    componentOncePerRequestFilterMethod(filterMethod) and
    propertyBackedPermitAllRule(
      matcher, rule, sourceField, permitAllRoute
    ) and
    handlerFqn = filterMethod.getDeclaringType().getQualifiedName() + "." +
      filterMethod.getName() and
    handlerFile = filterMethod.getLocation().getFile().getRelativePath() and
    handlerLine = filterMethod.getLocation().getStartLine() and routeOrEvent = "" and
    factFile = rule.getLocation().getFile().getRelativePath() and
    factLine = rule.getLocation().getStartLine() and kind = "security_filter_chain" and
    value = "unauthenticated_filter" and coverageStatus = "complete" and
    coverageNote = "component_once_filter_has_permit_all_route_witness"
  )
  or exists(LocalVariableDecl map, MethodCall selected, MethodCall setter,
            Method mapped, string pattern, string chain |
    springMvcHandlerRoute(mapped, routeOrEvent) and
    shiroFirstStaticRule(
      map, selected, setter, routeOrEvent, pattern, chain
    ) and
    shiroChainClassification(chain, value, coverageStatus, coverageNote) and
    handlerFqn = mapped.getDeclaringType().getQualifiedName() + "." + mapped.getName() and
    handlerFile = mapped.getLocation().getFile().getRelativePath() and
    handlerLine = mapped.getLocation().getStartLine() and
    factFile = selected.getLocation().getFile().getRelativePath() and
    factLine = selected.getLocation().getStartLine() and kind = "security_filter_chain"
  )
  or exists(LocalVariableDecl map, MethodCall setter, MethodCall mutation, Method mapped |
    shiroCommittedOrderedMap(map, setter) and shiroDynamicMapMutation(map, mutation) and
    shiroCallBefore(mutation, setter) and springMvcHandlerRoute(mapped, routeOrEvent) and
    handlerFqn = mapped.getDeclaringType().getQualifiedName() + "." + mapped.getName() and
    handlerFile = mapped.getLocation().getFile().getRelativePath() and
    handlerLine = mapped.getLocation().getStartLine() and
    factFile = mutation.getLocation().getFile().getRelativePath() and
    factLine = mutation.getLocation().getStartLine() and kind = "security_filter_chain" and
    value = "security_matcher_unknown" and coverageStatus = "partial" and
    coverageNote = "shiro_dynamic_rule_precedence_unresolved"
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
