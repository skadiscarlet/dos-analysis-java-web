/**
 * @name JettyRetention
 * @description Jetty ProxyServlet to HttpClient destination retained-state candidates.
 */

import java

class JettyProxyEntry extends Method {
  JettyProxyEntry() {
    this.getName() = "service" and
    this.getNumberOfParameters() = 2 and
    this.getDeclaringType().getQualifiedName() = "org.eclipse.jetty.proxy.ProxyServlet"
  }
}

class JettyProxyNewRequestCall extends MethodCall {
  JettyProxyNewRequestCall() {
    this.getMethod().getName() = "newProxyRequest" and
    exists(this.getArgument(0)) and
    exists(this.getArgument(1)) and
    this.getEnclosingCallable().getDeclaringType().getQualifiedName() =
      "org.eclipse.jetty.proxy.ProxyServlet" and
    this.getEnclosingCallable().getName() = "service"
  }
}

class JettyProxySendCall extends MethodCall {
  JettyProxySendCall() {
    this.getMethod().getName() = "sendProxyRequest" and
    exists(this.getArgument(0)) and
    exists(this.getArgument(1)) and
    exists(this.getArgument(2)) and
    this.getEnclosingCallable().getDeclaringType().getQualifiedName() =
      "org.eclipse.jetty.proxy.ProxyServlet" and
    this.getEnclosingCallable().getName() = "service"
  }
}

class JettyDestinationCompute extends MethodCall {
  JettyDestinationCompute() {
    this.getMethod().getName() = "compute" and
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    exists(this.getArgument(1)) and
    this.getEnclosingCallable().getDeclaringType().getQualifiedName() =
      "org.eclipse.jetty.client.HttpClient" and
    this.getEnclosingCallable().getName() = "resolveDestination" and
    this.getQualifier().toString() = "destinations"
  }

  Expr getReceiverExpr() { result = this.getQualifier() }

  Expr getGrowthDriver() { result = this.getArgument(0) }
}

predicate jettyProxyDestinationFlow(
  JettyProxyEntry entry,
  JettyProxyNewRequestCall newRequest,
  JettyProxySendCall send,
  JettyDestinationCompute sink,
  string callPath
) {
  newRequest.getEnclosingCallable() = entry and
  send.getEnclosingCallable() = entry and
  callPath = entry.getDeclaringType().getQualifiedName() + "." + entry.getName() +
    " -> " + newRequest.getMethod().getDeclaringType().getQualifiedName() + "." +
    newRequest.getMethod().getName() +
    " -> " + send.getMethod().getDeclaringType().getQualifiedName() + "." +
    send.getMethod().getName() +
    " -> org.eclipse.jetty.client.HttpRequest.send" +
    " -> " + sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + "." +
    sink.getEnclosingCallable().getName() +
    " -> " + sink.getMethod().getDeclaringType().getQualifiedName() + "." +
    sink.getMethod().getName()
}

string jettyProxyDebugNotes(
  JettyProxyEntry entry,
  JettyProxyNewRequestCall newRequest,
  JettyProxySendCall send,
  JettyDestinationCompute sink
) {
  result = "proxy_entry=" + entry.getName() +
    "; new_request=" + newRequest.getMethod().getName() +
    "; send_bridge=" + send.getMethod().getName() +
    "; retained_map=HttpClient.destinations" +
    "; growth_driver=" + sink.getGrowthDriver().toString() +
    "; dynamic_harness_maps_request_param_to_Request.tag"
}
