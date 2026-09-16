/**
 * @name Resource lifecycle callable inventory
 * @description Source callable identities and diagnostic call coverage, independent of allocation recognition.
 * @kind table
 * @id dosweb/resource-lifecycle-callables
 */
import java

string identity(Callable callable) {
  result = "java-callable-v1:" + callable.getQualifiedName() + callable.getMethodDescriptor()
}

predicate diagnosticCall(Callable owner, MethodCall call) {
  call.getEnclosingCallable() = owner
}

string callTargets(Callable owner) {
  exists(string targets |
    targets = concat(MethodCall call | diagnosticCall(owner, call) |
      identity(call.getMethod()), "\n") and
    (targets.length() <= 2048 and result = targets or
      targets.length() > 2048 and result = targets.substring(0, 2048))
  )
}

from Callable callable, boolean hasBody, string callableKind
where
  callable.fromSource() and
  callable.getLocation().getFile().getRelativePath().matches("%.java") and
  not exists(LambdaExpr lambda | lambda.asMethod() = callable) and
  (exists(callable.getBody()) and hasBody = true or not exists(callable.getBody()) and hasBody = false) and
  (callable instanceof Constructor and callableKind = "constructor" or not callable instanceof Constructor and callableKind = "method")
select
  identity(callable) as unit_id,
  callable.getLocation().getFile().getRelativePath() as source_file,
  callable.getLocation().getStartLine() as start_line,
  callable.getLocation().getStartColumn() as start_column,
  callable.getLocation().getEndLine() as end_line,
  callable.getLocation().getEndColumn() as end_column,
  callableKind as callable_kind,
  hasBody as has_body,
  count(MethodCall call | diagnosticCall(callable, call)) as call_count,
  count(MethodCall call | diagnosticCall(callable, call) and
    not (call.getMethod().fromSource() and exists(call.getMethod().getBody()))
  ) as external_call_count,
  callTargets(callable) as call_targets
