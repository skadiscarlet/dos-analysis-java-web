/**
 * @name Lifecycle bound candidates
 * @description Growth-anchored finite queue submissions with checked rejection.
 * @kind table
 * @id dosweb/bound-candidates
 */

import java
import FiniteQueueDomain

// Initial capacities of Map implementations are deliberately excluded: they
// are allocation hints, not hard maximum capacities. The imported domain only
// accepts Array/LinkedBlockingQueue explicit capacities and AST reject shape.

from MethodCall call, Field fieldReceiver, string receiverValue, string fieldPathValue,
  boolean checkedValue, string valueValue, string evidenceValue, string statusValue, string noteValue,
  string phaseValue, boolean coversValue, string behaviorValue, string capacityValue
where
  call.getLocation().getFile().getRelativePath().matches("%.java") and
  // offer returns a rejection signal. add is not accepted as a checked bound
  // because its exception-only contract is not yet path-modeled.
  call.getMethod().getName() = "offer" and
  fieldReceiver = queueReceiverField(call) and capacityValue = finiteFieldQueueCapacity(fieldReceiver) and
  receiverValue = fieldReceiver.getDeclaringType().getQualifiedName() + "." + fieldReceiver.getName() and
  fieldPathValue = fieldReceiver.getName() and
  (
    checkedFiniteQueueOffer(call) and checkedValue = true and valueValue = capacityValue and
    evidenceValue = "same_callable_checked_finite_queue" and statusValue = "complete" and
    noteValue = "same_cfg_checked_queue_witness" and phaseValue = "inside_growth" and
    coversValue = true and behaviorValue = "reject"
    or
    not checkedFiniteQueueOffer(call) and checkedValue = false and valueValue = "submission_result" and
    evidenceValue = "queue_submission_result" and statusValue = "partial" and
    noteValue = "ignored_offer_result" and phaseValue = "unknown" and
    coversValue = false and behaviorValue = "block"
  )
select
  call.getLocation().getFile().getRelativePath() as anchor_file,
  call.getLocation().getStartLine() as anchor_start_line,
  call.getLocation().getFile().getRelativePath() as site_file,
  call.getLocation().getStartLine() as site_start_line,
  "capacity" as bound_kind,
  "tasks" as resource_dimension,
  "instance" as scope,
  behaviorValue as behavior,
  receiverValue as receiver,
  fieldPathValue as field_path,
  checkedValue as result_checked,
  "literal" as configuration_key,
  valueValue as configuration_value,
  phaseValue as phase,
  coversValue as covers_flow,
  "any" as request_encoding,
  fieldPathValue as queue_resource,
  true as product_bound,
  evidenceValue as evidence,
  statusValue as coverage_status,
  noteValue as coverage_note
