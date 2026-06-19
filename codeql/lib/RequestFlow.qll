/**
 * @name RequestFlow
 * @description Bounded request-data flow proof for proof-carrying Web retention sinks.
 */

import java
import lib.CommonDoS
import lib.WebSources
import lib.RetentionSinks

predicate requestFlowSameClassOrPackage(Callable caller, Callable callee) {
  caller.getDeclaringType() = callee.getDeclaringType()
  or
  caller.getDeclaringType().getPackage() = callee.getDeclaringType().getPackage()
}

abstract class RequestCarrier extends Element {
  abstract HttpEntryPoint getEntry();
  abstract Expr getCarrierExpr();
  abstract string getCarrierKind();
  abstract string getSourceKind();
  abstract string getEvidence();
}

class ParameterRequestCarrier extends RequestCarrier {
  HttpEntryPoint entry;
  Parameter param;

  ParameterRequestCarrier() {
    param = entry.getAParameter() and
    paramValueSpace(param) in ["Stream", "Unlimited"] and
    not entry.isServerControlledParam(param) and
    this = param
  }

  override HttpEntryPoint getEntry() { result = entry }

  override Expr getCarrierExpr() {
    result = param.getAnAccess() and
    result.getEnclosingCallable() = entry
  }

  override string getCarrierKind() { result = "param" }

  override string getSourceKind() {
    paramValueSpace(param) = "Stream" and result = "stream_param"
    or paramValueSpace(param) != "Stream" and result = "request_param"
  }

  override string getEvidence() {
    result = param.getName() + ":" + param.getType().getName()
  }
}

predicate helperCallCarriesRequestData(HttpEntryPoint entry, MethodCall helperCall) {
  exists(ParameterRequestCarrier carrier |
    carrier.getEntry() = entry and
    helperCall.getAnArgument() = carrier.getCarrierExpr()
  )
  or
  exists(Expr arg |
    arg = helperCall.getAnArgument() and
    isRequestDerivedExpr(arg)
  )
}

predicate directRequestFlowFields(
  HttpEntryPoint entry,
  WebRetentionSink sink,
  string requestFlowKind,
  string requestFlowProof,
  string callPath,
  string callPathDepth,
  string requestCarrierKind,
  string sourceKind,
  string sourceExpr
) {
  exists(ParameterRequestCarrier carrier |
    sink.getEnclosingCallable() = entry and
    carrier.getEntry() = entry and
    requestFlowKind = "direct" and
    requestFlowProof = "direct:" + carrier.getEvidence() + " -> " +
      sink.getGrowthDriver().toString() and
    callPath = entry.getDeclaringType().getQualifiedName() + "." + entry.getName() +
      " -> " + sink.getMethod().getDeclaringType().getQualifiedName() + "." +
      sink.getMethod().getName() and
    callPathDepth = "1" and
    requestCarrierKind = carrier.getCarrierKind() and
    sourceKind = carrier.getSourceKind() and
    sourceExpr = carrier.getEvidence()
  )
}

predicate oneHopRequestFlowFields(
  HttpEntryPoint entry,
  WebRetentionSink sink,
  string requestFlowKind,
  string requestFlowProof,
  string callPath,
  string callPathDepth,
  string requestCarrierKind,
  string sourceKind,
  string sourceExpr
) {
  exists(MethodCall helperCall, Callable helper, ParameterRequestCarrier carrier |
    helperCall.getEnclosingCallable() = entry and
    helperCall.getCallee() = helper and
    helper != entry and
    helperCallCarriesRequestData(entry, helperCall) and
    sink.getEnclosingCallable() = helper and
    requestFlowSameClassOrPackage(entry, helper) and
    carrier.getEntry() = entry and
    requestFlowKind = "one_hop_helper" and
    requestFlowProof = "one_hop_helper:" + helperCall.getMethod().getName() +
      " carries request data" and
    callPath = entry.getDeclaringType().getQualifiedName() + "." + entry.getName() +
      " -> " + helper.getDeclaringType().getQualifiedName() + "." + helper.getName() +
      " -> " + sink.getMethod().getDeclaringType().getQualifiedName() + "." +
      sink.getMethod().getName() and
    callPathDepth = "2" and
    requestCarrierKind = carrier.getCarrierKind() and
    sourceKind = carrier.getSourceKind() and
    sourceExpr = carrier.getEvidence()
  )
}

predicate requestFlowFields(
  HttpEntryPoint entry,
  WebRetentionSink sink,
  string requestFlowKind,
  string requestFlowProof,
  string callPath,
  string callPathDepth,
  string requestCarrierKind,
  string sourceKind,
  string sourceExpr
) {
  directRequestFlowFields(
    entry, sink, requestFlowKind, requestFlowProof, callPath, callPathDepth,
    requestCarrierKind, sourceKind, sourceExpr
  )
  or
  oneHopRequestFlowFields(
    entry, sink, requestFlowKind, requestFlowProof, callPath, callPathDepth,
    requestCarrierKind, sourceKind, sourceExpr
  )
}
