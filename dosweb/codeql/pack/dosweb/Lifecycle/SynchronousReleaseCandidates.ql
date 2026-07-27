/**
 * @name Synchronous release candidates
 * @description Screens direct synchronous removal, clear, eviction, and close operations.
 * @kind table
 * @id dosweb/synchronous-release-candidates
 */

import java

// Exact candidate-only contract columns:
// "site_file", "site_start_line", "release_kind", "resource_dimension",
// "scope", "receiver", "key_identity", "synchronous", "normal_path",
// "exceptional_path", "actual_reduction", "evidence", "coverage_status",
// "coverage_note"

predicate releaseOperation(string name) {
  name = ["remove", "clear", "evict", "close"]
}

from MethodCall call, string receiverValue, string keyValue, boolean normalPathValue, boolean exceptionalPathValue, string evidenceValue, string noteValue
where
  releaseOperation(call.getMethod().getName()) and
  receiverValue = call.getQualifier().toString() and
  (
    keyValue = call.getArgument(0).toString() or keyValue = "none"
  ) and normalPathValue = true and exceptionalPathValue = false and
  evidenceValue = "direct_release_operation" and noteValue = "exceptional_path_requires_review"
select
  call.getLocation().getFile().getRelativePath() as site_file,
  call.getLocation().getStartLine() as site_start_line,
  call.getMethod().getName() as release_kind,
  "unknown" as resource_dimension,
  "instance" as scope,
  receiverValue as receiver,
  keyValue as key_identity,
  true as synchronous,
  normalPathValue as normal_path,
  exceptionalPathValue as exceptional_path,
  true as actual_reduction,
  false as after_growth,
  false as transfer_only,
  "none" as async_kind,
  evidenceValue as evidence,
  "partial" as coverage_status,
  noteValue as coverage_note
