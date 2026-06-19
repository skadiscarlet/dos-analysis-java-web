/**
 * @name RetentionSinks
 * @description Proof-carrying Web retention sink model.
 */

import java
import lib.Persistence

abstract class WebRetentionSink extends MethodCall {
  abstract Expr getReceiverExpr();
  abstract Expr getGrowthDriver();
  abstract string getSinkShape();
  abstract string getGrowthDimension();
  abstract string getGrowthDriverKind();
  abstract string getLifecycleRoot();
  abstract string getRetainedObject();
  abstract string getRetainedField();
  abstract string getRetentionPath();
  abstract string getReceiverProof();
  abstract string getProofSource();
  abstract string getProofConfidence();

  string getContainerKind() {
    getProofSource() = "static_field" and result = "static_container"
    or getSinkShape().regexpMatch(".*attribute_set") and result = "session"
    or getSinkShape().regexpMatch("registry_.*") and result = "framework_registry"
    or getSinkShape().regexpMatch("parser_.*") and result = "parser_transaction"
    or not getProofSource() = "static_field" and
      not getSinkShape().regexpMatch(".*attribute_set|registry_.*|parser_.*") and
      result = "lifecycle_field_container"
  }

  string getSinkKind() {
    getSinkShape().regexpMatch(".*attribute_set") and result = "session_attribute"
    or getSinkShape().regexpMatch(".*map_.*|registry_.*") and result = "container_put"
    or getSinkShape().regexpMatch(".*collection_add|parser_.*|protocol_.*") and
      result = "container_add"
  }
}

class CollectionMutationCall extends MethodCall {
  CollectionMutationCall() {
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    (
      this.getMethod().getName() in [
        "put", "putIfAbsent", "compute", "computeIfAbsent", "computeIfPresent", "merge",
        "add", "addAll", "offer"
      ] and
      isContainerTypeName(this.getMethod().getDeclaringType().getName())
    )
  }

  Expr getCollectionReceiverExpr() { result = this.getQualifier() }

  Expr getPrimaryGrowthDriver() { result = this.getArgument(0) }
}

class CollectionRetainedSink extends WebRetentionSink, CollectionMutationCall {
  ReceiverProof proof;

  CollectionRetainedSink() {
    proof.getReceiverExpr() = this.getCollectionReceiverExpr() and
    isContainerTypeName(proof.getRetainedField().getType().getName())
  }

  override Expr getReceiverExpr() { result = this.getCollectionReceiverExpr() }

  override Expr getGrowthDriver() { result = this.getPrimaryGrowthDriver() }

  override string getSinkShape() {
    this.getMethod().getName() in ["put", "putIfAbsent"] and result = "retained_map_put"
    or this.getMethod().getName() in ["compute", "computeIfAbsent", "computeIfPresent", "merge"] and
      result = "retained_map_compute"
    or this.getMethod().getName() in ["add", "addAll", "offer"] and
      result = "retained_collection_add"
  }

  override string getGrowthDimension() {
    this.getMethod().getName() in [
      "put", "putIfAbsent", "compute", "computeIfAbsent", "computeIfPresent", "merge"
    ] and result = "key_cardinality"
    or this.getMethod().getName() in ["add", "addAll", "offer"] and result = "element_count"
  }

  override string getGrowthDriverKind() {
    this.getMethod().getName() in [
      "put", "putIfAbsent", "compute", "computeIfAbsent", "computeIfPresent", "merge"
    ] and result = "map_key"
    or this.getMethod().getName() in ["add", "addAll", "offer"] and result = "stored_value"
  }

  override string getLifecycleRoot() { result = proof.getLifecycleRoot() }

  override string getRetainedObject() { result = proof.getRetainedObject() }

  override string getRetainedField() { result = proof.getRetainedField().getName() }

  override string getRetentionPath() { result = proof.getRetentionPath() }

  override string getReceiverProof() { result = proof.getEvidence() }

  override string getProofSource() { result = proof.getProofSource() }

  override string getProofConfidence() { result = proof.getConfidence() }
}

class NestedRetentionSink extends WebRetentionSink, CollectionMutationCall {
  ReceiverProof outerProof;

  NestedRetentionSink() {
    exists(MethodCall outerGet |
      outerGet = this.getCollectionReceiverExpr() and
      outerGet.getMethod().getName().regexpMatch("(?i)(get|getOrDefault|computeIfAbsent)") and
      outerProof.getReceiverExpr() = outerGet.getQualifier()
    )
    or
    exists(Variable v, MethodCall outerGet |
      v.getAnAccess() = this.getCollectionReceiverExpr() and
      outerGet.getMethod().getName().regexpMatch("(?i)(get|getOrDefault|computeIfAbsent)") and
      outerProof.getReceiverExpr() = outerGet.getQualifier() and
      exists(AssignExpr assign |
        assign.getDest() = v.getAnAccess() and
        assign.getSource() = outerGet and
        assign.getEnclosingCallable() = this.getEnclosingCallable()
      )
    )
  }

  override Expr getReceiverExpr() { result = this.getCollectionReceiverExpr() }

  override Expr getGrowthDriver() { result = this.getPrimaryGrowthDriver() }

  override string getSinkShape() { result = "nested_retained_map_put" }

  override string getGrowthDimension() { result = "key_cardinality" }

  override string getGrowthDriverKind() { result = "nested_map_key" }

  override string getLifecycleRoot() { result = outerProof.getLifecycleRoot() }

  override string getRetainedObject() { result = outerProof.getRetainedObject() }

  override string getRetainedField() { result = outerProof.getRetainedField().getName() }

  override string getRetentionPath() { result = outerProof.getRetentionPath() + ".*" }

  override string getReceiverProof() { result = outerProof.getEvidence() }

  override string getProofSource() { result = outerProof.getProofSource() }

  override string getProofConfidence() { result = outerProof.getConfidence() }
}

class AttributeRetentionSink extends WebRetentionSink {
  AttributeRetentionSink() {
    this.getMethod().hasName("setAttribute") and
    this.getMethod().getNumberOfParameters() = 2 and
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    (
      this.getMethod().getDeclaringType().getName().regexpMatch("(?i).*(HttpSession|ServletContext).*") or
      this.getMethod().getDeclaringType().getQualifiedName().regexpMatch(
        ".*(javax|jakarta)\\.servlet\\..*(HttpSession|ServletContext).*"
      )
    )
  }

  override Expr getReceiverExpr() { result = this.getQualifier() }

  override Expr getGrowthDriver() { result = this.getArgument(0) }

  override string getSinkShape() {
    this.getMethod().getDeclaringType().getName().matches("%ServletContext%") and
    result = "servlet_context_attribute_set"
    or
    not this.getMethod().getDeclaringType().getName().matches("%ServletContext%") and
    result = "session_attribute_set"
  }

  override string getGrowthDimension() { result = "key_cardinality" }

  override string getGrowthDriverKind() { result = "attribute_name" }

  override string getLifecycleRoot() {
    getSinkShape() = "servlet_context_attribute_set" and result = "servlet_context"
    or getSinkShape() = "session_attribute_set" and result = "http_session"
  }

  override string getRetainedObject() { result = getLifecycleRoot() }

  override string getRetainedField() { result = "<framework_attribute_map>" }

  override string getRetentionPath() { result = getLifecycleRoot() + ".attributes" }

  override string getReceiverProof() { result = getLifecycleRoot() + ":setAttribute" }

  override string getProofSource() {
    getSinkShape() = "servlet_context_attribute_set" and result = "servlet_context"
    or getSinkShape() = "session_attribute_set" and result = "session"
  }

  override string getProofConfidence() { result = "high" }
}

class RegistryRetentionSink extends WebRetentionSink {
  ReceiverProof proof;

  RegistryRetentionSink() {
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    this.getMethod().getName().regexpMatch(
      "(?i)(register|addNode|addHost|addBalancer|addDestination|addProvider|addContext|addRoute)"
    ) and
    proof.getReceiverExpr() = this.getQualifier()
  }

  override Expr getReceiverExpr() { result = this.getQualifier() }

  override Expr getGrowthDriver() { result = this.getArgument(0) }

  override string getSinkShape() { result = "registry_register" }

  override string getGrowthDimension() {
    this.getMethod().getName().regexpMatch("(?i).*Host.*") and result = "host_count"
    or this.getMethod().getName().regexpMatch("(?i).*Node.*") and result = "node_count"
    or not this.getMethod().getName().regexpMatch("(?i).*(Host|Node).*") and
      result = "key_cardinality"
  }

  override string getGrowthDriverKind() { result = "registry_key" }

  override string getLifecycleRoot() { result = proof.getLifecycleRoot() }

  override string getRetainedObject() { result = proof.getRetainedObject() }

  override string getRetainedField() { result = proof.getRetainedField().getName() }

  override string getRetentionPath() { result = proof.getRetentionPath() }

  override string getReceiverProof() { result = proof.getEvidence() }

  override string getProofSource() { result = proof.getProofSource() }

  override string getProofConfidence() { result = proof.getConfidence() }
}

class ParserRetentionSink extends WebRetentionSink {
  ParserRetentionSink() {
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    this.getMethod().getName() in ["add", "addAll", "offer", "put"] and
    not this.getMethod().getDeclaringType().getName().regexpMatch("(?i).*(HeaderMap|Headers).*") and
    not this.getQualifier().toString().regexpMatch("(?i).*get(Response|Request)Headers.*") and
    (
      isParserContainerName(this.getEnclosingCallable().getDeclaringType().getName()) or
      isParserContainerName(this.getMethod().getDeclaringType().getName()) or
      this.getQualifier().toString().regexpMatch("(?i).*(bodyParts|mimeParts|parts).*")
    )
  }

  override Expr getReceiverExpr() { result = this.getQualifier() }

  override Expr getGrowthDriver() { result = this.getArgument(0) }

  override string getSinkShape() { result = "parser_part_accumulator" }

  override string getGrowthDimension() {
    this.getQualifier().toString().regexpMatch("(?i).*header.*") and result = "header_count"
    or not this.getQualifier().toString().regexpMatch("(?i).*header.*") and result = "part_count"
  }

  override string getGrowthDriverKind() { result = "part_metadata" }

  override string getLifecycleRoot() { result = "parser_transaction" }

  override string getRetainedObject() {
    result = this.getEnclosingCallable().getDeclaringType().getQualifiedName()
  }

  override string getRetainedField() { result = "<parser_accumulator>" }

  override string getRetentionPath() {
    result = this.getEnclosingCallable().getDeclaringType().getQualifiedName() + "." +
      this.getQualifier().toString()
  }

  override string getReceiverProof() { result = "parser_lifetime:" + getRetentionPath() }

  override string getProofSource() { result = "parser_lifetime" }

  override string getProofConfidence() { result = "medium" }
}
