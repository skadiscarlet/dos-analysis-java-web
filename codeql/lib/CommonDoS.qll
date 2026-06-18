/**
 * @name CommonDoS
 * @description Domain-neutral five-axis model for client-state retention DoS.
 */

import java

predicate isReachabilityAxis(string value) {
  value in ["Blocked", "PermGated", "WeakGated", "Open"]
}

predicate isValueSpaceAxis(string value) {
  value in ["Uncontrollable", "Limited", "Unlimited", "Stream"]
}

predicate isMultiplicityAxis(string value) {
  value in ["CallerBounded", "Amplifiable"]
}

predicate isCapacityAxis(string value) {
  value in ["Bounded", "PerElementUnbounded", "Unbounded"]
}

predicate isLifespanAxis(string value) {
  value in ["Evicted", "ProcessLifetime", "RebootPersistent"]
}

abstract class ClientStateEntry extends Method {
  abstract Parameter getAnAttackerControlledParam();
  abstract string getReachability();
}

abstract class StateContainer extends Field {
  abstract string getContainerKind();
  abstract string getLifespan();
  abstract predicate hasCapacityBound();
  abstract predicate hasEviction();
}

abstract class ClientStateWrite extends MethodCall {
  abstract ClientStateEntry getEntry();
  abstract Expr getKeyExpr();
  abstract Expr getValueExpr();
  abstract string getSinkKind();
  abstract string getContainerKind();
  abstract string getEvidence();
}

predicate isCompileTimeString(Expr expr) {
  expr instanceof CompileTimeConstantExpr and
  exists(string value | value = expr.(CompileTimeConstantExpr).getStringValue())
}

predicate isRequestDerivedExpr(Expr expr) {
  exists(MethodCall call |
    call = expr |
    call.getMethod().getName().regexpMatch("(?i).*(getParameter|getParameterNames|getParameterMap|getHeader|getHeaders|getHeaderNames|getQueryString|getRequestURI|getRequestURL|getPathInfo|getInputStream|getReader|getParts|getPart|getAttribute|getCookie|getCookies|getRequestPath|getRelativePath|getPath|getRequestBody|getRequestHeaders).*")
  )
  or exists(Parameter p |
    p.getAnAccess() = expr |
    p.getType().getName().regexpMatch(".*Request.*|.*Exchange.*|UriInfo|String|CharSequence")
  )
}

string keyKind(Expr key) {
  isCompileTimeString(key) and result = "constant"
  or not isCompileTimeString(key) and isRequestDerivedExpr(key) and result = "request_derived"
  or not isCompileTimeString(key) and not isRequestDerivedExpr(key) and result = "unknown"
}

string axisV(string paramValueSpace, Expr key) {
  isValueSpaceAxis(paramValueSpace) and
  (
    isCompileTimeString(key) and result = "Limited"
    or not isCompileTimeString(key) and paramValueSpace = "Stream" and result = "Stream"
    or not isCompileTimeString(key) and paramValueSpace = "Unlimited" and result = "Unlimited"
    or not isCompileTimeString(key) and paramValueSpace = "Limited" and result = "Limited"
    or not isCompileTimeString(key) and paramValueSpace = "Uncontrollable" and result = "Uncontrollable"
  )
}

string axisM(Expr key) {
  isCompileTimeString(key) and result = "CallerBounded"
  or not isCompileTimeString(key) and result = "Amplifiable"
}

predicate hasCapacityCheckNearby(Callable callable) {
  exists(MethodCall call |
    call.getEnclosingCallable() = callable and
    call.getMethod().getName().regexpMatch("(?i).*(max|limit|quota|cap|capacity|threshold|bound).*")
  )
  or exists(Variable v |
    v.getAnAccess().getEnclosingCallable() = callable and
    v.getName().regexpMatch("(?i).*(max|limit|quota|cap|capacity|threshold|bound).*")
  )
}

predicate hasElementSizeOnlyCheckNearby(Callable callable) {
  not hasCapacityCheckNearby(callable) and
  exists(MethodCall call |
    call.getEnclosingCallable() = callable and
    call.getMethod().getName().regexpMatch("(?i).*(length|size|getContentLength).*")
  )
}

string axisC(Callable callable) {
  hasCapacityCheckNearby(callable) and result = "Bounded"
  or not hasCapacityCheckNearby(callable) and hasElementSizeOnlyCheckNearby(callable) and result = "PerElementUnbounded"
  or not hasCapacityCheckNearby(callable) and not hasElementSizeOnlyCheckNearby(callable) and result = "Unbounded"
}

string drdVerdict(string axis_v, string axis_c, string axis_l) {
  isValueSpaceAxis(axis_v) and isCapacityAxis(axis_c) and isLifespanAxis(axis_l) and
  (
    axis_v in ["Uncontrollable", "Limited"] and result = "Unexploitable"
    or axis_v in ["Unlimited", "Stream"] and axis_c = "Bounded" and result = "Context-Constrained"
    or axis_v in ["Unlimited", "Stream"] and axis_c != "Bounded" and axis_l = "Evicted" and result = "Time-Constrained"
    or axis_v in ["Unlimited", "Stream"] and axis_c != "Bounded" and axis_l != "Evicted" and result = "Unconstrained"
  )
}

string exploitVerdict5(string axis_r, string axis_v, string axis_m, string axis_c, string axis_l) {
  isReachabilityAxis(axis_r) and isValueSpaceAxis(axis_v) and isMultiplicityAxis(axis_m) and
  isCapacityAxis(axis_c) and isLifespanAxis(axis_l) and
  (
    axis_m = "CallerBounded" and result = "Unexploitable"
    or axis_m = "Amplifiable" and axis_r = "Blocked" and result = "Unexploitable"
    or axis_m = "Amplifiable" and axis_r != "Blocked" and axis_v in ["Uncontrollable", "Limited"] and result = "Unexploitable"
    or axis_m = "Amplifiable" and axis_r != "Blocked" and axis_v in ["Unlimited", "Stream"] and axis_c = "Bounded" and result = "Context-Constrained"
    or axis_m = "Amplifiable" and axis_r != "Blocked" and axis_v in ["Unlimited", "Stream"] and axis_c != "Bounded" and axis_l = "Evicted" and result = "Time-Constrained"
    or axis_m = "Amplifiable" and axis_r != "Blocked" and axis_v in ["Unlimited", "Stream"] and axis_c != "Bounded" and axis_l = "ProcessLifetime" and result = "Unconstrained"
    or axis_m = "Amplifiable" and axis_r != "Blocked" and axis_v in ["Unlimited", "Stream"] and axis_c != "Bounded" and axis_l = "RebootPersistent" and result = "Irrecoverable"
  )
}
