/**
 * @name Synchronous release candidates
 * @description Same-callable CFG-anchored synchronous reductions.
 * @kind table
 * @id dosweb/synchronous-release-candidates
 */

import java

predicate releaseOperation(string name) { name = ["remove", "clear", "evict", "close"] }

predicate sameTryFinally(MethodCall release, MethodCall growth) {
  exists(TryStmt attempt |
    release.getParent*() = attempt.getFinally() and
    growth.getParent*() = attempt.getBlock() and
    release.getBasicBlock().postDominates(growth.getBasicBlock())
  )
}

// A direct release can be proved to occur on a normal path, but without a
// finally/exceptional CFG witness it remains a complete *ineffective* row.
predicate successOnlyAfter(MethodCall release, MethodCall growth) {
  growth.getBasicBlock().dominates(release.getBasicBlock()) and
  not exists(TryStmt attempt | release.getParent*() = attempt.getFinally())
}

from MethodCall call, MethodCall growth, FieldAccess fieldReceiver, string receiverValue,
  string keyValue, boolean normalPathValue, boolean exceptionalPathValue,
  boolean reductionValue, boolean afterValue, string evidenceValue, string noteValue,
  string statusValue
where
  call.getLocation().getFile().getRelativePath().matches("%.java") and
  releaseOperation(call.getMethod().getName()) and
  fieldReceiver = call.getQualifier() and
  receiverValue = fieldReceiver.getField().getDeclaringType().getQualifiedName() + "." + fieldReceiver.getField().getName() and
  growth.getEnclosingCallable() = call.getEnclosingCallable() and
  growth.getLocation().getFile() = call.getLocation().getFile() and
  growth.getMethod().getName() = ["put", "add", "offer", "submit"] and
  (keyValue = call.getArgument(0).toString() or keyValue = "none") and
  (
    sameTryFinally(call, growth) and
    normalPathValue = true and exceptionalPathValue = true and
    reductionValue = true and afterValue = true and
    evidenceValue = "cfg_finally_reduction_postdominates_growth" and
    noteValue = "same_cfg_finally_release_witness" and statusValue = "complete"
    or
    successOnlyAfter(call, growth) and
    normalPathValue = true and exceptionalPathValue = false and
    reductionValue = true and afterValue = true and
    evidenceValue = "cfg_success_only_reduction" and
    noteValue = "success_only_exception_path_missing" and statusValue = "complete"
  )
select
  growth.getLocation().getFile().getRelativePath() as anchor_file,
  growth.getLocation().getStartLine() as anchor_start_line,
  call.getLocation().getFile().getRelativePath() as site_file,
  call.getLocation().getStartLine() as site_start_line,
  call.getMethod().getName() as release_kind,
  "entries" as resource_dimension,
  "instance" as scope,
  receiverValue as receiver,
  keyValue as key_identity,
  true as synchronous,
  normalPathValue as normal_path,
  exceptionalPathValue as exceptional_path,
  reductionValue as actual_reduction,
  afterValue as after_growth,
  false as transfer_only,
  "none" as async_kind,
  evidenceValue as evidence,
  statusValue as coverage_status,
  noteValue as coverage_note
