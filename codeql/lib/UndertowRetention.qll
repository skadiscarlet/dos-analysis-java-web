/**
 * @name UndertowRetention
 * @description Undertow callback and management retained-state candidates.
 */

import java

class LearningPushEntry extends Method {
  LearningPushEntry() {
    this.getName() = "handleRequest" and
    this.getDeclaringType().getQualifiedName() = "io.undertow.server.handlers.LearningPushHandler"
  }
}

class LearningPushMapPut extends MethodCall {
  LearningPushMapPut() {
    this.getMethod().getName() = "put" and
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    exists(this.getArgument(1)) and
    this.getEnclosingCallable().getName() = "exchangeEvent" and
    this.getEnclosingCallable().getDeclaringType().getQualifiedName().regexpMatch(
      "io\\.undertow\\.server\\.handlers\\.LearningPushHandler\\$PushCompletionListener"
    ) and
    this.getQualifier().toString() = "pushes"
  }

  Expr getReceiverExpr() { result = this.getQualifier() }

  Expr getGrowthDriver() { result = this.getArgument(0) }
}

predicate learningPushFlow(LearningPushEntry entry, LearningPushMapPut sink, string callPath) {
  callPath = entry.getDeclaringType().getQualifiedName() + "." + entry.getName() +
    " -> addExchangeCompleteListener(PushCompletionListener)" +
    " -> " + sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + "." +
    sink.getEnclosingCallable().getName() +
    " -> " + sink.getMethod().getDeclaringType().getQualifiedName() + "." +
    sink.getMethod().getName()
}

string learningPushDebugNotes(LearningPushEntry entry, LearningPushMapPut sink) {
  result = "completion_listener=PushCompletionListener; outer_cache=LearningPushHandler.cache[referer]; " +
    "inner_map=pushes; growth_driver=" + sink.getGrowthDriver().toString() +
    "; entry=" + entry.getName()
}

class MCMPEntry extends Method {
  MCMPEntry() {
    this.getName() = "handleRequest" and
    this.getNumberOfParameters() = 1 and
    this.getDeclaringType().getQualifiedName() =
      "io.undertow.server.handlers.proxy.mod_cluster.MCMPHandler"
  }
}

class MCMPContainerAddNodeCall extends MethodCall {
  MCMPContainerAddNodeCall() {
    this.getMethod().getName() = "addNode" and
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    this.getEnclosingCallable().getName() = "processConfig" and
    this.getEnclosingCallable().getDeclaringType().getQualifiedName() =
      "io.undertow.server.handlers.proxy.mod_cluster.MCMPHandler"
  }
}

class MCMPRegistryPut extends MethodCall {
  MCMPRegistryPut() {
    this.getMethod().getName() = "put" and
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    exists(this.getArgument(1)) and
    this.getEnclosingCallable().getName() = "addNode" and
    this.getEnclosingCallable().getDeclaringType().getQualifiedName() =
      "io.undertow.server.handlers.proxy.mod_cluster.ModClusterContainer" and
    this.getQualifier().toString() in ["balancers", "nodes"]
  }

  Expr getReceiverExpr() { result = this.getQualifier() }

  Expr getGrowthDriver() { result = this.getArgument(0) }

  string getRetainedFieldName() { result = this.getQualifier().toString() }

  string getGrowthDimension() {
    getRetainedFieldName() = "nodes" and result = "node_count"
    or getRetainedFieldName() = "balancers" and result = "balancer_count"
  }
}

predicate mcmpAddNodeFlow(
  MCMPEntry entry,
  MCMPContainerAddNodeCall bridge,
  MCMPRegistryPut sink,
  string callPath
) {
  callPath = entry.getDeclaringType().getQualifiedName() + "." + entry.getName() +
    " -> " + bridge.getEnclosingCallable().getDeclaringType().getQualifiedName() + "." +
    bridge.getEnclosingCallable().getName() +
    " -> " + bridge.getMethod().getDeclaringType().getQualifiedName() + "." +
    bridge.getMethod().getName() +
    " -> " + sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + "." +
    sink.getEnclosingCallable().getName() +
    " -> " + sink.getMethod().getDeclaringType().getQualifiedName() + "." +
    sink.getMethod().getName()
}

string mcmpDebugNotes(MCMPEntry entry, MCMPContainerAddNodeCall bridge, MCMPRegistryPut sink) {
  result = "management_entry=" + entry.getName() +
    "; request_data=parseFormData(exchange)" +
    "; bridge=" + bridge.getMethod().getName() +
    "; retained_registry=" + sink.getRetainedFieldName() +
    "; deployment_condition=management_endpoint_exposed"
}
