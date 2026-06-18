/**
 * @name WebGuards
 * @description Authentication and authorization guard detection for web HTTP entry points.
 */

import java
import lib.WebSources

/** Annotation on the callable itself or on its declaring type with a matching simple name. */
bindingset[nameRegex]
predicate hasAnnotationNamed(Callable callable, string nameRegex) {
  exists(Annotation annotation |
    annotation = callable.getAnAnnotation() and
    annotation.getType().getName().regexpMatch(nameRegex)
  )
  or
  exists(Annotation annotation |
    annotation = callable.getDeclaringType().getAnAnnotation() and
    annotation.getType().getName().regexpMatch(nameRegex)
  )
}

/** Annotation on the callable itself or on its declaring type with matching package and simple name. */
bindingset[packageRegex, nameRegex]
predicate hasAnnotationQualified(Callable callable, string packageRegex, string nameRegex) {
  exists(Annotation annotation |
    annotation = callable.getAnAnnotation() and
    annotation.getType().getPackage().getName().regexpMatch(packageRegex) and
    annotation.getType().getName().regexpMatch(nameRegex)
  )
  or
  exists(Annotation annotation |
    annotation = callable.getDeclaringType().getAnAnnotation() and
    annotation.getType().getPackage().getName().regexpMatch(packageRegex) and
    annotation.getType().getName().regexpMatch(nameRegex)
  )
}

/** Auth-related annotation that suggests gated reachability but may still be satisfiable. */
predicate hasWeakAuthAnnotation(Callable callable) {
  hasAnnotationQualified(callable, "(?i).*(security|annotation).*",
    "(?i).*(PreAuthorize|PostAuthorize|Secured|RolesAllowed|DeclareRoles|ServletSecurity|Authenticated|RequiresAuthentication|RequiresRoles).*"
  )
  or
  hasAnnotationNamed(callable,
    "(?i).*(PreAuthorize|PostAuthorize|Secured|RolesAllowed|DeclareRoles|ServletSecurity|Authenticated|RequiresAuthentication|RequiresRoles).*"
  )
}

/** Annotation that explicitly denies access to the entry. */
predicate hasBlockedAnnotation(Callable callable) {
  hasAnnotationQualified(callable, "(?i).*(security|annotation).*", "(?i).*DenyAll.*")
  or hasAnnotationNamed(callable, "(?i).*DenyAll.*")
}

/** Explicit authentication or authorization check call inside the callable body. */
predicate hasExplicitAuthCall(Callable callable) {
  exists(MethodCall call |
    call.getEnclosingCallable() = callable and
    call.getMethod().getName().regexpMatch(
      "(?i).*(isUserInRole|checkPermission|hasRole|hasAuthority|denyAccess|accessDenied).*"
    )
  )
}

/** Throw that appears to block unauthorized or forbidden access. */
predicate hasBlockingThrow(Callable callable) {
  hasExplicitAuthCall(callable) and
  exists(ThrowStmt throwStmt |
    throwStmt.getEnclosingCallable() = callable and
    throwStmt.getExpr().getType().getName().regexpMatch(
      "(?i).*(AccessDenied|Forbidden|SecurityException|Unauthorized|NotAuthorized).*"
    )
  )
}

/** Reachability classification for a web HTTP entry point. */
string reachabilityFor(HttpEntryPoint entry) {
  hasBlockedAnnotation(entry) and result = "Blocked"
  or
  not hasBlockedAnnotation(entry) and
  (
    hasWeakAuthAnnotation(entry) or
    hasExplicitAuthCall(entry) or
    hasBlockingThrow(entry)
  ) and
  result = "WeakGated"
  or
  not hasBlockedAnnotation(entry) and
  not hasWeakAuthAnnotation(entry) and
  not hasExplicitAuthCall(entry) and
  not hasBlockingThrow(entry) and
  result = "Open"
}
