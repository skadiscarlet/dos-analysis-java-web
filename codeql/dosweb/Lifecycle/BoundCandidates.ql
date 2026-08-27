/**
 * @name Lifecycle bound candidates
 * @description Growth-anchored finite queues and exact framework request limits.
 * @kind table
 * @id dosweb/bound-candidates
 */

import java
import FiniteQueueDomain
import FrameworkLimitDomain

// Framework domains are intentionally exact: Jackson StreamReadConstraints,
// Netty HttpObjectAggregator, Servlet MultipartConfig, and Solr's
// formdataUploadLimitInKB. Similar names or unbound configuration are omitted.

predicate boundRow(
  Element anchor, Element site, string boundKind, string dimension, string scopeValue,
  string behaviorValue, string receiverValue, string fieldPathValue, boolean checkedValue,
  string configurationKey, string configurationValue, string phaseValue,
  boolean coversValue, string requestEncoding, string queueResource,
  boolean productBound, string evidenceValue, string statusValue, string noteValue
) {
  exists(MethodCall call, Field fieldReceiver, string capacityValue |
    anchor = call and site = call and
    call.getLocation().getFile().getRelativePath().matches("%.java") and
    call.getMethod().getName() = "offer" and
    fieldReceiver = queueReceiverField(call) and
    capacityValue = finiteFieldQueueCapacity(fieldReceiver) and
    boundKind = "capacity" and dimension = "tasks" and scopeValue = "instance" and
    receiverValue = fieldReceiver.getDeclaringType().getQualifiedName() + "." + fieldReceiver.getName() and
    fieldPathValue = fieldReceiver.getName() and queueResource = fieldPathValue and
    configurationKey = "literal" and requestEncoding = "any" and productBound = true and
    (
      checkedFiniteQueueOffer(call) and checkedValue = true and
      configurationValue = capacityValue and evidenceValue = "same_callable_checked_finite_queue" and
      statusValue = "complete" and noteValue = "same_cfg_checked_queue_witness" and
      phaseValue = "inside_growth" and coversValue = true and behaviorValue = "reject"
      or
      not checkedFiniteQueueOffer(call) and checkedValue = false and
      configurationValue = "submission_result" and evidenceValue = "queue_submission_result" and
      statusValue = "partial" and noteValue = "ignored_offer_result" and
      phaseValue = "unknown" and coversValue = false and behaviorValue = "block"
    )
  )
  or
  exists(MethodCall growth |
    frameworkLimitCandidate(
      site, growth, configurationKey, configurationValue, requestEncoding,
      receiverValue, fieldPathValue, evidenceValue
    ) and
    anchor = growth and boundKind = "limit" and dimension = "bytes" and
    scopeValue = "request" and behaviorValue = "reject" and checkedValue = true and
    phaseValue = "before_growth" and coversValue = true and
    queueResource = fieldPathValue and productBound = true and
    statusValue = "complete" and noteValue = "framework_limit_exact_path_literal"
  )
}

from Element anchor, Element site, string boundKind, string dimension, string scopeValue,
  string behaviorValue, string receiverValue, string fieldPathValue, boolean checkedValue,
  string configurationKey, string configurationValue, string phaseValue,
  boolean coversValue, string requestEncoding, string queueResource,
  boolean productBound, string evidenceValue, string statusValue, string noteValue
where
  boundRow(
    anchor, site, boundKind, dimension, scopeValue, behaviorValue, receiverValue,
    fieldPathValue, checkedValue, configurationKey, configurationValue, phaseValue,
    coversValue, requestEncoding, queueResource, productBound, evidenceValue,
    statusValue, noteValue
  )
select
  anchor.getLocation().getFile().getRelativePath() as anchor_file,
  anchor.getLocation().getStartLine() as anchor_start_line,
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  boundKind as bound_kind,
  dimension as resource_dimension,
  scopeValue as scope,
  behaviorValue as behavior,
  receiverValue as receiver,
  fieldPathValue as field_path,
  checkedValue as result_checked,
  configurationKey as configuration_key,
  configurationValue as configuration_value,
  phaseValue as phase,
  coversValue as covers_flow,
  requestEncoding as request_encoding,
  queueResource as queue_resource,
  productBound as product_bound,
  evidenceValue as evidence,
  statusValue as coverage_status,
  noteValue as coverage_note
