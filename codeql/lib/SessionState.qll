/**
 * @name SessionState
 * @description Web client-state write model for session/context/container retention DoS analysis.
 */

import java
import lib.CommonDoS
import lib.WebSources
import lib.WebGuards
import lib.Persistence
import lib.RetentionSinks
import lib.RequestFlow

class WebClientStateEntry extends ClientStateEntry, HttpEntryPoint {
  WebClientStateEntry() { this instanceof HttpEntryPoint }

  override Parameter getAnAttackerControlledParam() {
    result = this.getAParameter() and
    paramValueSpace(result) in ["Stream", "Unlimited"] and
    not this.isServerControlledParam(result)
  }

  override string getReachability() { result = reachabilityFor(this) }

  override string getFramework() {
    this instanceof ServletHttpEntryPoint and result = "servlet"
    or this instanceof SpringHttpEntryPoint and result = "spring"
    or this instanceof JettyHttpEntryPoint and result = "jetty"
    or this instanceof UndertowHttpEntryPoint and result = "undertow"
    or this instanceof JAXRSHttpEntryPoint and result = "jaxrs"
  }

  override string getEntryType() {
    this instanceof ServletHttpEntryPoint and result = "servlet:" + this.getName()
    or this instanceof SpringHttpEntryPoint and result = "spring:controller"
    or this instanceof JettyHttpEntryPoint and result = "jetty:handler"
    or this instanceof UndertowHttpEntryPoint and result = "undertow:handler"
    or this instanceof JAXRSHttpEntryPoint and result = "jaxrs:" + this.(JAXRSHttpEntryPoint).getHttpMethod().toLowerCase()
  }
}

class SessionAttributeWrite extends MethodCall {
  SessionAttributeWrite() {
    this.getMethod().hasName("setAttribute") and
    this.getMethod().getNumberOfParameters() = 2 and
    isHttpSessionType(this.getMethod().getDeclaringType())
  }

  Expr getKeyExpr() { result = this.getArgument(0) }

  Expr getValueExpr() { result = this.getArgument(1) }
}

class ServletContextAttributeWrite extends MethodCall {
  ServletContextAttributeWrite() {
    this.getMethod().hasName("setAttribute") and
    this.getMethod().getNumberOfParameters() = 2 and
    isServletContextType(this.getMethod().getDeclaringType())
  }

  Expr getKeyExpr() { result = this.getArgument(0) }

  Expr getValueExpr() { result = this.getArgument(1) }
}

class WebContainerWrite extends MethodCall {
  WebContainerWrite() {
    (
      this.getMethod().getName() in ["put", "putIfAbsent", "computeIfAbsent", "add", "addAll", "register"] and
      this.getMethod().getDeclaringType().getName().regexpMatch(
        ".*(Map|List|Set|Collection|Queue|Deque|Registry|Store|Cache).*"
      )
      or
      this.getMethod().hasName("set") and
      this.getMethod().getDeclaringType().getName().regexpMatch(
        ".*(Map|List|Set|Collection|Registry|Store|Cache).*"
      )
    ) and
    exists(this.getArgument(0))
  }

  Expr getKeyExpr() { result = this.getArgument(0) }

  Expr getValueExpr() {
    exists(this.getArgument(1)) and result = this.getArgument(1)
    or
    not exists(this.getArgument(1)) and result = this.getArgument(0)
  }
}

predicate isHttpSessionType(RefType type) {
  type.hasQualifiedName("javax.servlet.http", "HttpSession")
  or
  type.hasQualifiedName("jakarta.servlet.http", "HttpSession")
  or
  type.getASupertype*().hasQualifiedName("javax.servlet.http", "HttpSession")
  or
  type.getASupertype*().hasQualifiedName("jakarta.servlet.http", "HttpSession")
  or
  type.getPackage().getName().regexpMatch("(javax|jakarta)\\.servlet\\.http") and
  type.getName() = "HttpSession"
}

predicate isServletContextType(RefType type) {
  type.hasQualifiedName("javax.servlet", "ServletContext")
  or
  type.hasQualifiedName("jakarta.servlet", "ServletContext")
  or
  type.getASupertype*().hasQualifiedName("javax.servlet", "ServletContext")
  or
  type.getASupertype*().hasQualifiedName("jakarta.servlet", "ServletContext")
  or
  type.getPackage().getName().regexpMatch("(javax|jakarta)\\.servlet") and
  type.getName() = "ServletContext"
}

predicate sameClassOrPackage(Callable caller, Callable callee) {
  caller.getDeclaringType() = callee.getDeclaringType()
  or
  caller.getDeclaringType().getPackage() = callee.getDeclaringType().getPackage()
}

string sinkKind(MethodCall write) {
  write instanceof SessionAttributeWrite and result = "session_attribute"
  or
  write instanceof ServletContextAttributeWrite and result = "servlet_context_attribute"
  or
  write instanceof WebContainerWrite and
  write.getMethod().getName() in ["put", "putIfAbsent", "computeIfAbsent", "set", "register"] and
  result = "container_put"
  or
  write instanceof WebContainerWrite and
  write.getMethod().getName() in ["add", "addAll"] and
  result = "container_add"
}

Expr retainedWriteKey(MethodCall write) {
  write instanceof SessionAttributeWrite and result = write.(SessionAttributeWrite).getKeyExpr()
  or
  write instanceof ServletContextAttributeWrite and result = write.(ServletContextAttributeWrite).getKeyExpr()
  or
  write instanceof WebContainerWrite and result = write.(WebContainerWrite).getKeyExpr()
  or
  write instanceof WebRetentionSink and result = write.(WebRetentionSink).getGrowthDriver()
}

Expr retainedWriteValue(MethodCall write) {
  write instanceof SessionAttributeWrite and result = write.(SessionAttributeWrite).getValueExpr()
  or
  write instanceof ServletContextAttributeWrite and result = write.(ServletContextAttributeWrite).getValueExpr()
  or
  write instanceof WebContainerWrite and result = write.(WebContainerWrite).getValueExpr()
  or
  write instanceof WebRetentionSink and result = write.(WebRetentionSink).getGrowthDriver()
}

string containerKind(MethodCall write) {
  isPersistentStoreWrite(write) and result = "persistent_store"
  or
  not isPersistentStoreWrite(write) and write instanceof WebRetentionSink and
  result = write.(WebRetentionSink).getContainerKind()
  or
  not isPersistentStoreWrite(write) and
  not write instanceof WebRetentionSink and
  write instanceof SessionAttributeWrite and result = "session"
  or
  not isPersistentStoreWrite(write) and
  not write instanceof WebRetentionSink and
  write instanceof ServletContextAttributeWrite and result = "servlet_context"
  or
  not isPersistentStoreWrite(write) and
  not write instanceof WebRetentionSink and
  write instanceof WebContainerWrite and
  write.getMethod().getDeclaringType().getName().regexpMatch("(?i).*(Session|Store|Cache).*") and
  result = "session_store"
  or
  not isPersistentStoreWrite(write) and
  not write instanceof WebRetentionSink and
  write instanceof WebContainerWrite and
  not write.getMethod().getDeclaringType().getName().regexpMatch("(?i).*(Session|Store|Cache).*") and
  result = "unknown_container"
}

predicate isPersistentStoreWrite(MethodCall write) {
  isPersistentWebStoreName(write.getMethod().getDeclaringType().getName())
  or
  exists(RefType enclosingType |
    enclosingType = write.getEnclosingCallable().getDeclaringType() and
    isPersistentWebStoreName(enclosingType.getName())
  )
}

predicate hasEvictionNearby(MethodCall write) {
  exists(MethodCall call |
    call.getEnclosingCallable() = write.getEnclosingCallable() and
    isEvictionLikeCallable(call.getMethod())
  )
}

string lifespanFor(MethodCall write) {
  result = webContainerLifespan(containerKind(write), write.getEnclosingCallable())
}

class WebClientStateWrite extends ClientStateWrite {
  WebClientStateEntry entry;
  string requestFlowKind;
  string requestFlowProof;
  string callPath;
  string callPathDepth;
  string requestCarrierKind;
  string sourceKind;
  string sourceExpr;

  WebClientStateWrite() {
    this instanceof WebRetentionSink and
    requestFlowFields(
      entry, this, requestFlowKind, requestFlowProof, callPath, callPathDepth,
      requestCarrierKind, sourceKind, sourceExpr
    )
  }

  override ClientStateEntry getEntry() { result = entry }

  WebClientStateEntry getWebEntry() { result = entry }

  string getPathKind() { result = requestFlowKind }

  string getLifespan() { result = lifespanFor(this) }

  override Expr getKeyExpr() { result = retainedWriteKey(this) }

  override Expr getValueExpr() { result = retainedWriteValue(this) }

  override string getSinkKind() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getSinkKind()
    or not this instanceof WebRetentionSink and result = sinkKind(this)
  }

  override string getContainerKind() { result = containerKind(this) }

  override string getEvidence() {
    this instanceof WebRetentionSink and
    result = this.(WebRetentionSink).getReceiverProof()
    or
    not this instanceof WebRetentionSink and
    result = this.getMethod().getDeclaringType().getName() + "." + this.getMethod().getName()
  }

  string getSinkShape() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getSinkShape()
    or not this instanceof WebRetentionSink and result = getSinkKind()
  }

  string getGrowthDimension() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getGrowthDimension()
    or not this instanceof WebRetentionSink and result = "unknown"
  }

  string getGrowthDriverKind() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getGrowthDriverKind()
    or not this instanceof WebRetentionSink and result = "unknown"
  }

  Expr getGrowthDriver() { result = retainedWriteKey(this) }

  string getReceiverExprText() {
    this instanceof WebRetentionSink and
    result = this.(WebRetentionSink).getReceiverExpr().toString()
    or not this instanceof WebRetentionSink and result = "<unknown>"
  }

  string getLifecycleRoot() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getLifecycleRoot()
    or not this instanceof WebRetentionSink and result = "<unknown>"
  }

  string getRetainedObject() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getRetainedObject()
    or not this instanceof WebRetentionSink and result = "<unknown>"
  }

  string getRetainedField() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getRetainedField()
    or not this instanceof WebRetentionSink and result = "<unknown>"
  }

  string getRetentionPath() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getRetentionPath()
    or not this instanceof WebRetentionSink and result = "<unknown>"
  }

  string getReceiverProof() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getReceiverProof()
    or not this instanceof WebRetentionSink and result = "<missing>"
  }

  string getProofSource() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getProofSource()
    or not this instanceof WebRetentionSink and result = "<missing>"
  }

  string getProofConfidence() {
    this instanceof WebRetentionSink and result = this.(WebRetentionSink).getProofConfidence()
    or not this instanceof WebRetentionSink and result = "debug"
  }

  string getRequestFlowProof() { result = requestFlowProof }

  string getCallPath() { result = callPath }

  string getCallPathDepth() { result = callPathDepth }

  string getRequestCarrierKind() { result = requestCarrierKind }

  string getSourceKind() { result = sourceKind }

  string getSourceExprText() { result = sourceExpr }

  string getCandidateFamily() { result = "retained_state" }

  string getDeploymentCondition() { result = "" }

  string getCapacityHint() { result = "" }
}

predicate flowOutputFields(
  WebClientStateWrite write,
  string requestFlowKind,
  string requestFlowProof,
  string callPath,
  string callPathDepth,
  string requestCarrierKind,
  string sourceKind,
  string sourceExpr
) {
  requestFlowFields(
    write.getWebEntry(), write, requestFlowKind, requestFlowProof, callPath,
    callPathDepth, requestCarrierKind, sourceKind, sourceExpr
  )
}
