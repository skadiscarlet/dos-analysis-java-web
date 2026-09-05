/**
 * @name Lifecycle one-wrapper summaries
 * @description Direct-call lifecycle summaries. Only a strict Guard summary is complete; Bound/Release wrappers are explicit partial audit rows.
 * @kind table
 * @id dosweb/lifecycle-summary
 */

import java
import semmle.code.java.controlflow.Guards
import semmle.code.java.dataflow.DataFlow

predicate callerAttackerParameter(Parameter input) {
  exists(Annotation annotation |
    annotation = input.getAnAnnotation() and
    annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", ["RequestParam", "RequestBody", "PathVariable", "RequestHeader"])
  )
}

predicate callerDemand(MethodCall growth, Expr demand, string dimension, string scopeValue, string representationValue) {
  growth.getMethod().getName() = ["put", "add"] and demand = growth.getArgument(0) and dimension = "entries" and representationValue = "same" and
  exists(FieldAccess receiver | receiver = growth.getQualifier() and (receiver.getField().isStatic() and scopeValue = "global" or not receiver.getField().isStatic() and scopeValue = "instance"))
  or growth.getMethod().getName() = ["offer", "submit", "execute"] and demand = growth.getArgument(0) and dimension = "tasks" and representationValue = "same" and
  exists(FieldAccess receiver | receiver = growth.getQualifier() and (receiver.getField().isStatic() and scopeValue = "global" or not receiver.getField().isStatic() and scopeValue = "instance"))
  or growth.getMethod().getName() = ["allocate", "allocateDirect"] and demand = growth.getArgument(0) and dimension = "bytes" and scopeValue = "request" and representationValue = "raw_body"
  or growth.getMethod().getName() = "getPayload" and demand = growth.getQualifier() and dimension = "bytes" and scopeValue = "request" and representationValue = "raw_body"
}

/** A helper return does not reject the caller path. Only an uncaught throw
 * can make a void guard wrapper terminal without a caller-side result check. */
predicate terminalReject(IfStmt site) {
  (
    site.getThen() instanceof ThrowStmt
    or exists(BlockStmt block, ThrowStmt terminal |
      block = site.getThen() and block.getNumStmt() = 1 and terminal = block.getStmt(0)
    )
  ) and
  not exists(TryStmt attempt, CatchClause caught |
    site.getParent*() = attempt.getBlock() and caught = attempt.getACatchClause()
  )
}

predicate terminalReturn(IfStmt site) {
  exists(ReturnStmt terminal | terminal.getParent*() = site.getThen())
}

predicate calleeParamIntoGuard(Method callee, IfStmt guard) {
  exists(Parameter parameter, DataFlow::Node source, DataFlow::Node sink, Expr conditionPart |
    parameter = callee.getParameter(0) and source.asParameter() = parameter and
    sink.asExpr() = conditionPart and conditionPart.getParent*() = guard.getCondition() and
    DataFlow::localFlow(source, sink)
  )
}

string guardLiteral(IfStmt site) {
  exists(CompileTimeConstantExpr limit | limit.getParent*() = site.getCondition() and result = limit.toString())
}

module CallerWrapperFlowConfig implements DataFlow::ConfigSig {
  predicate isSource(DataFlow::Node source) { exists(Parameter input | callerAttackerParameter(input) and source.asParameter() = input) }
  predicate isSink(DataFlow::Node sink) {
    exists(MethodCall callsite | sink.asExpr() = callsite.getArgument(0))
    or exists(MethodCall growth, Expr demand, string d, string s, string r | callerDemand(growth, demand, d, s, r) and sink.asExpr() = demand)
  }
}
module CallerWrapperFlow = DataFlow::Global<CallerWrapperFlowConfig>;

predicate strictGuardWrapper(MethodCall growth, MethodCall callsite, Method callee, IfStmt guard, Expr argument, Expr demand, string dimension, string scopeValue, string representationValue) {
  callerDemand(growth, demand, dimension, scopeValue, representationValue) and
  callsite.getEnclosingCallable() = growth.getEnclosingCallable() and
  callsite.getCallee() = callee and argument = callsite.getArgument(0) and
  callsite.getBasicBlock().dominates(growth.getBasicBlock()) and
  callsite.getControlFlowNode().getASuccessor*() = growth.getControlFlowNode() and
  not growth.getControlFlowNode().getASuccessor*() = callsite.getControlFlowNode() and
  not exists(TryStmt attempt, CatchClause caught |
    callsite.getParent*() = attempt.getBlock() and caught = attempt.getACatchClause()
  ) and
  guard.getEnclosingCallable() = callee and terminalReject(guard) and calleeParamIntoGuard(callee, guard) and
  exists(DataFlow::Node source, DataFlow::Node argumentSink, DataFlow::Node demandSink |
    argumentSink.asExpr() = argument and demandSink.asExpr() = demand and
    CallerWrapperFlow::flow(source, argumentSink) and CallerWrapperFlow::flow(source, demandSink)
  )
}

predicate strictReturnWrapper(MethodCall growth, MethodCall callsite, Method callee, IfStmt guard, Expr argument, Expr demand, string dimension, string scopeValue, string representationValue) {
  callerDemand(growth, demand, dimension, scopeValue, representationValue) and
  callsite.getEnclosingCallable() = growth.getEnclosingCallable() and
  callsite.getCallee() = callee and argument = callsite.getArgument(0) and
  callsite.getBasicBlock().dominates(growth.getBasicBlock()) and
  callsite.getControlFlowNode().getASuccessor*() = growth.getControlFlowNode() and
  not growth.getControlFlowNode().getASuccessor*() = callsite.getControlFlowNode() and
  guard.getEnclosingCallable() = callee and terminalReturn(guard) and calleeParamIntoGuard(callee, guard) and
  exists(DataFlow::Node source, DataFlow::Node argumentSink, DataFlow::Node demandSink |
    argumentSink.asExpr() = argument and demandSink.asExpr() = demand and
    CallerWrapperFlow::flow(source, argumentSink) and CallerWrapperFlow::flow(source, demandSink)
  )
}

from MethodCall growth, MethodCall callsite, Method callee, Element candidate, string familyValue,
  string dimension, string scopeValue, string representationValue, string configurationKey, string configurationValue,
  string phaseValue, boolean coversValue, boolean dominatesValue, boolean rejectReachesValue, string evidenceValue,
  string relationValue, string statusValue, string noteValue
where
  growth.getLocation().getFile().getRelativePath().matches("%.java") and
  callsite.getCallee() = callee and
  (
    exists(IfStmt guard, Expr argument, Expr demand |
      candidate = guard and strictGuardWrapper(growth, callsite, callee, guard, argument, demand, dimension, scopeValue, representationValue) and
      configurationKey = "literal" and configurationValue = guardLiteral(guard) and
      familyValue = "guard" and phaseValue = "before_growth" and coversValue = true and dominatesValue = true and rejectReachesValue = false and
      evidenceValue = "one_wrapper_shared_source_guard_cfg_witness" and relationValue = "one_wrapper" and statusValue = "complete" and noteValue = "direct_wrapper_guard_shared_source"
    )
    or
    exists(IfStmt guard, Expr argument, Expr demand |
      candidate = guard and strictReturnWrapper(growth, callsite, callee, guard, argument, demand, dimension, scopeValue, representationValue) and
      configurationKey = "literal" and configurationValue = guardLiteral(guard) and
      familyValue = "guard" and phaseValue = "before_growth" and coversValue = true and dominatesValue = false and rejectReachesValue = true and
      evidenceValue = "one_wrapper_return_does_not_reject_caller" and relationValue = "one_wrapper" and statusValue = "complete" and noteValue = "direct_wrapper_return_ineffective"
    )
  )
select
  growth.getLocation().getFile().getRelativePath() as anchor_file,
  growth.getLocation().getStartLine() as anchor_start_line,
  familyValue as family,
  candidate.getLocation().getFile().getRelativePath() as candidate_file,
  candidate.getLocation().getStartLine() as candidate_start_line,
  callsite.getLocation().getFile().getRelativePath() as callsite_file,
  callsite.getLocation().getStartLine() as callsite_start_line,
  callsite.getArgument(0).getLocation().getFile().getRelativePath() as receiver_file,
  callsite.getArgument(0).getLocation().getStartLine() as receiver_start_line,
  0 as argument_index,
  dimension as resource_dimension,
  scopeValue as scope,
  configurationKey as configuration_key,
  configurationValue as configuration_value,
  representationValue as representation,
  phaseValue as phase,
  coversValue as covers_materialization,
  dominatesValue as dominates_growth,
  rejectReachesValue as reject_path_reaches_growth,
  evidenceValue as evidence,
  relationValue as cfg_relation,
  statusValue as coverage_status,
  noteValue as coverage_note
