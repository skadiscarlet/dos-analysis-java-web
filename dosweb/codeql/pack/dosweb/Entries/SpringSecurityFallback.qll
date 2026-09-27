/** Ordered fallback semantics for a deliberately closed single-chain DSL.
 * Unsupported/conditional/multiple-chain configurations produce partial facts.
 * This module never treats anyRequest as a global unauthenticated/low-role rule.
 */
import java

module SpringSecurityOrderedRules {
  private predicate dslCall(MethodCall call) {
    call.getMethod().getDeclaringType().getPackage().getName().matches(
      "org.springframework.security.config.annotation.web.configurers%"
    )
    or call.getMethod().getDeclaringType().getSourceDeclaration().hasQualifiedName(
      "org.springframework.security.config.annotation.web", "AbstractRequestMatcherRegistry"
    )
  }

  predicate authorization(LambdaExpr lambda, MethodCall configure, Method owner) {
    configure.getMethod().getDeclaringType().hasQualifiedName(
      "org.springframework.security.config.annotation.web.builders", "HttpSecurity"
    ) and configure.getMethod().getName() = "authorizeHttpRequests" and
    configure.getNumArgument() = 1 and lambda = configure.getArgument(0) and
    owner = configure.getEnclosingCallable() and owner.fromSource() and
    exists(MethodCall anyRule |
      anyRule.getEnclosingCallable() = lambda.asMethod() and dslCall(anyRule) and
      anyRule.getMethod().getName() = "anyRequest"
    )
  }

  /** Suppress the old unordered pattern rows only inside a managed fallback
   * lambda, including unsupported ones: a partial fact must not leak a grant. */
  predicate managedRule(MethodCall rule) {
    exists(LambdaExpr lambda, MethodCall configure, Method owner |
      authorization(lambda, configure, owner) and
      rule.getEnclosingCallable() = lambda.asMethod()
    )
  }

  private predicate annotated(Element element, string pkg, string name) {
    exists(Annotation a |
      (a = element.(Method).getAnAnnotation() or
       a = element.(RefType).getAnAnnotation()) and a.getType().hasQualifiedName(pkg, name)
    )
  }

  private predicate conditional(Element element) {
    exists(Annotation a |
      (a = element.(Method).getAnAnnotation() or
       a = element.(RefType).getAnAnnotation()) and
      (a.getType().getName() = "Profile" or a.getType().getName().matches("Conditional%"))
    )
  }

  private predicate filterChainMethod(Method method) {
    method.fromSource() and method.getReturnType().(RefType).getASupertype*()
      .hasQualifiedName("org.springframework.security.web", "SecurityFilterChain") and
    annotated(method, "org.springframework.context.annotation", "Bean")
  }

  bindingset[pattern]
  private predicate supportedPattern(string pattern) {
    pattern.regexpMatch("/[A-Za-z0-9/_.-]*") or
    pattern = "/**" or
    pattern.regexpMatch("/[A-Za-z0-9/_.-]+/\\*\\*")
  }

  private predicate matcher(MethodCall call) {
    dslCall(call) and (
      call.getMethod().getName() = "anyRequest" and call.getNumArgument() = 0
      or call.getMethod().getName() = "requestMatchers" and call.getNumArgument() > 0 and
         forall(Expr argument | argument = call.getAnArgument() |
           argument instanceof CompileTimeConstantExpr and
           supportedPattern(argument.(CompileTimeConstantExpr).getStringValue())
         )
    )
  }

  private predicate decision(MethodCall call, string value) {
    dslCall(call) and (
      call.getMethod().getName() = "permitAll" and call.getNumArgument() = 0 and
      value = "unauthenticated_filter"
      or call.getMethod().getName() = "authenticated" and call.getNumArgument() = 0 and
         value = "low_privilege_filter"
      or call.getMethod().getName() = "hasRole" and call.getNumArgument() = 1 and
         call.getArgument(0).(CompileTimeConstantExpr).getStringValue() = "ADMIN" and
         value = "privileged_filter"
      or call.getMethod().getName() = "hasAuthority" and call.getNumArgument() = 1 and
         call.getArgument(0).(CompileTimeConstantExpr).getStringValue() = "ROLE_ADMIN" and
         value = "privileged_filter"
    )
  }

  private predicate registryChain(Expr expression, Parameter registry) {
    expression.(VarAccess).getVariable() = registry
    or exists(MethodCall rule, MethodCall match |
      expression = rule and decision(rule, _) and match = rule.getQualifier() and
      matcher(match) and registryChain(match.getQualifier(), registry)
    )
  }

  private predicate nestedRule(MethodCall later, MethodCall earlier) {
    later = earlier
    or exists(MethodCall match, MethodCall previous |
      match = later.getQualifier() and matcher(match) and
      previous = match.getQualifier() and nestedRule(previous, earlier)
    )
  }

  private predicate tailRule(LambdaExpr lambda, MethodCall tail) {
    lambda.asMethod().getNumberOfParameters() = 1 and
    lambda.asMethod().getBody().getNumStmt() = 1 and
    (tail = lambda.getExprBody() or
     tail = lambda.asMethod().getBody().getStmt(0).(ExprStmt).getExpr() or
     tail = lambda.asMethod().getBody().getStmt(0).(ReturnStmt).getExpr())
  }

  private predicate completeChain(
    LambdaExpr lambda, MethodCall configure, Method owner, MethodCall tail
  ) {
    authorization(lambda, configure, owner) and filterChainMethod(owner) and
    annotated(owner.getDeclaringType(), "org.springframework.context.annotation", "Configuration") and
    annotated(owner.getDeclaringType(),
      "org.springframework.security.config.annotation.web.configuration", "EnableWebSecurity") and
    not conditional(owner) and not conditional(owner.getDeclaringType()) and
    not exists(Method other | other != owner and filterChainMethod(other)) and
    owner.getNumberOfParameters() = 1 and
    owner.getParameter(0).getType().(RefType).hasQualifiedName(
      "org.springframework.security.config.annotation.web.builders", "HttpSecurity"
    ) and
    configure.getQualifier().(VarAccess).getVariable() = owner.getParameter(0) and
    owner.getBody().getNumStmt() = 2 and
    owner.getBody().getStmt(0).(ExprStmt).getExpr() = configure and
    exists(MethodCall build |
      owner.getBody().getStmt(1).(ReturnStmt).getExpr() = build and
      build.getMethod().getName() = "build" and build.getNumArgument() = 0 and
      build.getQualifier().(VarAccess).getVariable() = owner.getParameter(0)
    ) and tailRule(lambda, tail) and
    registryChain(tail, lambda.asMethod().getParameter(0)) and
    tail.getQualifier().(MethodCall).getMethod().getName() = "anyRequest" and
    not exists(MethodCall other |
      other.getEnclosingCallable() = lambda.asMethod() and
      other.getMethod().getName() = "anyRequest" and other != tail.getQualifier()
    )
  }

  bindingset[pattern, route]
  private predicate pathMatches(string pattern, string route) {
    pattern = route or pattern = "/**"
    or exists(string prefix |
      pattern = prefix + "/**" and
      (route = prefix or route.substring(0, prefix.length() + 1) = prefix + "/")
    )
  }

  bindingset[match, route]
  private predicate matchesRoute(MethodCall match, string route) {
    match.getMethod().getName() = "anyRequest"
    or exists(CompileTimeConstantExpr argument |
      argument = match.getAnArgument() and pathMatches(argument.getStringValue(), route)
    )
  }

  /** route supplied by a source-backed mapped handler in EntrySecurity. */
  bindingset[route]
  predicate routeFact(
    string route, MethodCall evidence, string value, string coverage, string note
  ) {
    exists(LambdaExpr lambda, MethodCall configure, Method owner, MethodCall tail |
      completeChain(lambda, configure, owner, tail) and
      route.regexpMatch("/[A-Za-z0-9/_.-]*") and
      nestedRule(tail, evidence) and decision(evidence, value) and
      matchesRoute(evidence.getQualifier().(MethodCall), route) and
      not exists(MethodCall earlier |
        earlier != evidence and nestedRule(evidence, earlier) and
        decision(earlier, _) and matchesRoute(earlier.getQualifier().(MethodCall), route)
      ) and coverage = "complete" and note = "spring_security_ordered_single_chain"
    )
    or exists(LambdaExpr lambda, Method owner |
      authorization(lambda, evidence, owner) and
      (not exists(MethodCall tail | completeChain(lambda, evidence, owner, tail)) or
       not route.regexpMatch("/[A-Za-z0-9/_.-]*")) and
      value = "security_matcher_unknown" and coverage = "partial" and
      note = "spring_security_ordered_chain_scope_or_shape_unresolved"
    )
  }
}
