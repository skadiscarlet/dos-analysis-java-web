/**
 * @name Lifecycle guard candidates
 * @description Growth-anchored same-callable request rejection candidates with CFG and shared attacker-flow evidence.
 * @kind table
 * @id dosweb/guard-candidates
 */

import java
import semmle.code.java.controlflow.Guards
import semmle.code.java.dataflow.DataFlow

predicate directThrow(IfStmt site) {
  site.getThen() instanceof ThrowStmt
  or exists(BlockStmt block, ThrowStmt terminal |
    block = site.getThen() and block.getNumStmt() = 1 and terminal = block.getStmt(0)
  )
}

predicate terminalReject(IfStmt site) {
  (
    exists(ReturnStmt terminal | terminal = site.getThen())
    or exists(BlockStmt block, ReturnStmt terminal |
      block = site.getThen() and block.getNumStmt() = 1 and terminal = block.getStmt(0)
    )
    or directThrow(site)
  ) and
  not exists(TryStmt attempt, CatchClause caught |
    site.getParent*() = attempt.getBlock() and caught = attempt.getACatchClause()
  )
}

predicate cfgRejectsBeforeGrowth(IfStmt site, MethodCall growth) {
  exists(ConditionBlock block |
    block.getCondition() = site.getCondition() and
    block.dominates(growth.getBasicBlock()) and
    site.getCondition().getControlFlowNode().getASuccessor*() = growth.getControlFlowNode() and
    not growth.getControlFlowNode().getASuccessor*() = site.getCondition().getControlFlowNode() and
    not block.getTestSuccessor(true).getASuccessor*() = growth.getBasicBlock()
  )
}

predicate attackerParameter(Parameter input) {
  exists(Annotation annotation |
    annotation = input.getAnAnnotation() and
    annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestParam", "RequestBody", "PathVariable", "RequestHeader"])
  )
  or exists(Method method |
    input = method.getParameter(0) and method.getName() = ["service", "doGet", "doPost", "doPut", "doDelete", "doPatch"] and
    (method.getDeclaringType().getASourceSupertype*().hasQualifiedName("javax.servlet.http", "HttpServlet") or method.getDeclaringType().getASourceSupertype*().hasQualifiedName("jakarta.servlet.http", "HttpServlet"))
  )
  or exists(Method method |
    input = method.getParameter(1) and method.getName() = ["channelRead", "channelRead0", "messageArrived"]
  )
}

predicate derivedAttackerSource(Parameter input, MethodCall derived) {
  derived.getEnclosingCallable() = input.getCallable() and
  derived.getQualifier().(VarAccess).getVariable() = input and
  (
    derived.getMethod().getName() = ["body", "getParameter", "getParameterValues", "getInputStream", "getReader", "getPart", "getParts"]
    or derived.getMethod().getName() = "getPayload"
  )
}

predicate attackerOrigin(Parameter input, DataFlow::Node source) {
  attackerParameter(input) and source.asParameter() = input
  or exists(MethodCall derived | attackerParameter(input) and derivedAttackerSource(input, derived) and source.asExpr() = derived)
}

predicate attackerSourceNode(DataFlow::Node source) {
  exists(Parameter input | attackerOrigin(input, source))
}

/** The exact demand expression consumed by a modeled growth anchor. */
predicate growthDemand(MethodCall growth, Expr demand, string dimension, string scopeValue, string representationValue) {
  growth.getMethod().getName() = ["put", "add"] and demand = growth.getArgument(0) and
  dimension = "entries" and representationValue = "same" and
  exists(FieldAccess receiver |
    receiver = growth.getQualifier() and
    (receiver.getField().isStatic() and scopeValue = "global" or not receiver.getField().isStatic() and scopeValue = "instance")
  )
  or
  growth.getMethod().getName() = ["offer", "submit", "execute"] and demand = growth.getArgument(0) and
  dimension = "tasks" and representationValue = "same" and
  exists(FieldAccess receiver |
    receiver = growth.getQualifier() and
    (receiver.getField().isStatic() and scopeValue = "global" or not receiver.getField().isStatic() and scopeValue = "instance")
  )
  or
  growth.getMethod().getName() = ["allocate", "allocateDirect"] and demand = growth.getArgument(0) and
  dimension = "bytes" and scopeValue = "request" and representationValue = "raw_body"
  or
  growth.getMethod().getName() = "getPayload" and demand = growth.getQualifier() and
  dimension = "bytes" and scopeValue = "request" and representationValue = "raw_body"
}

module GuardDemandFlowConfig implements DataFlow::ConfigSig {
  predicate isSource(DataFlow::Node source) { attackerSourceNode(source) }
  predicate isSink(DataFlow::Node sink) {
    exists(IfStmt site, Expr conditionPart |
      sink.asExpr() = conditionPart and conditionPart.getParent*() = site.getCondition()
    )
    or exists(MethodCall growth, Expr demand, string dimension, string scoped, string represented |
      growthDemand(growth, demand, dimension, scoped, represented) and sink.asExpr() = demand
    )
  }
}
module GuardDemandFlow = DataFlow::Global<GuardDemandFlowConfig>;

/** A complete guard needs the *same* source to reach condition and demand. */
predicate sameAttackerSource(IfStmt site, MethodCall growth, Expr demand, string dimension, string scopeValue, string representationValue) {
  growthDemand(growth, demand, dimension, scopeValue, representationValue) and
  exists(Parameter input, DataFlow::Node conditionSource, DataFlow::Node demandSource,
         DataFlow::Node conditionSink, DataFlow::Node demandSink, Expr conditionPart |
    attackerOrigin(input, conditionSource) and attackerOrigin(input, demandSource) and
    conditionSink.asExpr() = conditionPart and conditionPart.getParent*() = site.getCondition() and
    demandSink.asExpr() = demand and
    GuardDemandFlow::flow(conditionSource, conditionSink) and
    GuardDemandFlow::flow(demandSource, demandSink)
  )
}

string guardLiteral(IfStmt site) {
  exists(CompileTimeConstantExpr limit |
    limit.getParent*() = site.getCondition() and result = limit.toString()
  )
}

from IfStmt site, MethodCall growth, Expr demand, string dimension, string scopeValue, string representationValue,
  string keyValue, string valueValue, string evidenceValue, string noteValue, string phaseValue, boolean coversValue,
  string statusValue, boolean dominatesValue, boolean rejectReachesValue
where
  site.getEnclosingCallable() instanceof Method and
  growth.getEnclosingCallable() = site.getEnclosingCallable() and
  growth.getLocation().getFile() = site.getLocation().getFile() and
  site.getLocation().getFile().getRelativePath().matches("%.java") and
  growthDemand(growth, demand, dimension, scopeValue, representationValue) and
  terminalReject(site) and sameAttackerSource(site, growth, demand, dimension, scopeValue, representationValue) and
  (
    cfgRejectsBeforeGrowth(site, growth) and
    valueValue = guardLiteral(site) and keyValue = "literal" and
    evidenceValue = "cfg_shared_attacker_source_terminal_reject" and
    noteValue = "same_cfg_shared_source_guard_witness" and phaseValue = "before_growth" and
    coversValue = true and statusValue = "complete" and dominatesValue = true and rejectReachesValue = false
    or
    not cfgRejectsBeforeGrowth(site, growth) and
    valueValue = guardLiteral(site) and keyValue = "literal" and
    evidenceValue = "cfg_shared_attacker_source_guard_after_growth" and
    noteValue = "same_cfg_guard_ineffective_after_growth" and phaseValue = "after_growth" and
    coversValue = false and statusValue = "complete" and dominatesValue = false and rejectReachesValue = true
    or
    not exists(string ignored | ignored = guardLiteral(site)) and
    keyValue = "request.max-bytes" and valueValue = "unknown" and
    evidenceValue = "guard_configuration_unproven" and
    noteValue = "guard_configuration_unproven" and phaseValue = "unknown" and
    coversValue = false and statusValue = "partial" and dominatesValue = false and rejectReachesValue = true
  )
select
  growth.getLocation().getFile().getRelativePath() as anchor_file,
  growth.getLocation().getStartLine() as anchor_start_line,
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  "input_validation" as guard_kind,
  dimension as resource_dimension,
  scopeValue as scope,
  "reject" as behavior,
  dominatesValue as dominates_growth,
  rejectReachesValue as reject_path_reaches_growth,
  keyValue as configuration_key,
  valueValue as configuration_value,
  representationValue as representation,
  phaseValue as phase,
  coversValue as covers_materialization,
  false as authorization_only,
  evidenceValue as evidence,
  statusValue as coverage_status,
  noteValue as coverage_note
