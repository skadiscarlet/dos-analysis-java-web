/**
 * @name SessionState
 * @description Web client-state write model for session/context/container retention DoS analysis.
 */

import java
import lib.CommonDoS
import lib.WebSources
import lib.WebGuards
import lib.Persistence

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

predicate helperCallCarriesEntryData(WebClientStateEntry entry, MethodCall helperCall) {
  exists(Expr arg, Parameter entryParam |
    arg = helperCall.getAnArgument() and
    entryParam = entry.getAnAttackerControlledParam() and
    arg = entryParam.getAnAccess()
  )
  or
  exists(Expr arg |
    arg = helperCall.getAnArgument() and
    isRequestDerivedExpr(arg)
  )
}

predicate writeInEntryOrOneHop(WebClientStateEntry entry, MethodCall write, string pathKind) {
  write.getEnclosingCallable() = entry and pathKind = "direct"
  or
  exists(Callable helper, MethodCall helperCall |
    helperCall.getEnclosingCallable() = entry and
    helperCall.getCallee() = helper and
    helperCallCarriesEntryData(entry, helperCall) and
    write.getEnclosingCallable() = helper and
    sameClassOrPackage(entry, helper) and
    pathKind = "one_hop_helper"
  )
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
}

Expr retainedWriteValue(MethodCall write) {
  write instanceof SessionAttributeWrite and result = write.(SessionAttributeWrite).getValueExpr()
  or
  write instanceof ServletContextAttributeWrite and result = write.(ServletContextAttributeWrite).getValueExpr()
  or
  write instanceof WebContainerWrite and result = write.(WebContainerWrite).getValueExpr()
}

string containerKind(MethodCall write) {
  isPersistentStoreWrite(write) and result = "persistent_store"
  or
  not isPersistentStoreWrite(write) and write instanceof SessionAttributeWrite and result = "session"
  or
  not isPersistentStoreWrite(write) and write instanceof ServletContextAttributeWrite and result = "servlet_context"
  or
  not isPersistentStoreWrite(write) and
  write instanceof WebContainerWrite and
  write.getMethod().getDeclaringType().getName().regexpMatch("(?i).*(Session|Store|Cache).*") and
  result = "session_store"
  or
  not isPersistentStoreWrite(write) and
  write instanceof WebContainerWrite and
  not write.getMethod().getDeclaringType().getName().regexpMatch("(?i).*(Session|Store|Cache).*") and
  result = "static_container"
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
  string pathKind;

  WebClientStateWrite() {
    (
      this instanceof SessionAttributeWrite or
      this instanceof ServletContextAttributeWrite or
      this instanceof WebContainerWrite
    ) and
    writeInEntryOrOneHop(entry, this, pathKind)
  }

  override ClientStateEntry getEntry() { result = entry }

  WebClientStateEntry getWebEntry() { result = entry }

  string getPathKind() { result = pathKind }

  string getLifespan() { result = lifespanFor(this) }

  override Expr getKeyExpr() { result = retainedWriteKey(this) }

  override Expr getValueExpr() { result = retainedWriteValue(this) }

  override string getSinkKind() { result = sinkKind(this) }

  override string getContainerKind() { result = containerKind(this) }

  override string getEvidence() {
    result = this.getMethod().getDeclaringType().getName() + "." + this.getMethod().getName()
  }
}
