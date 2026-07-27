/**
 * @name Lifecycle guard candidates
 * @description Screens request-size and input rejection branches near growth handlers.
 * @kind table
 * @id dosweb/guard-candidates
 */

import java

// Exact candidate-only contract columns:
// "site_file", "site_start_line", "guard_kind", "resource_dimension",
// "scope", "behavior", "dominates_growth", "reject_path_reaches_growth",
// "configuration_key", "configuration_value", "evidence",
// "coverage_status", "coverage_note"

from IfStmt site, string behaviorValue, boolean dominatesValue, boolean rejectReachesValue, string keyValue, string valueValue, string evidenceValue, string noteValue
where
  site.getEnclosingCallable() instanceof Method and
  site.getCondition().toString().regexpMatch(".*(>|>=|max|limit|length).*" ) and
  (
    site.getThen().toString().regexpMatch(".*return.*") and behaviorValue = "reject" and dominatesValue = true and rejectReachesValue = false
    or
    not site.getThen().toString().regexpMatch(".*return.*") and behaviorValue = "reject" and dominatesValue = false and rejectReachesValue = true
  ) and
  keyValue = "request.max-bytes" and valueValue = site.getCondition().toString() and
  evidenceValue = "conditional_input_limit" and noteValue = "branch_shape_candidate"
select
  site.getLocation().getFile().getRelativePath() as site_file,
  site.getLocation().getStartLine() as site_start_line,
  "input_validation" as guard_kind,
  "bytes" as resource_dimension,
  "request" as scope,
  behaviorValue as behavior,
  dominatesValue as dominates_growth,
  rejectReachesValue as reject_path_reaches_growth,
  keyValue as configuration_key,
  valueValue as configuration_value,
  "unknown" as representation,
  "unknown" as phase,
  false as covers_materialization,
  false as authorization_only,
  evidenceValue as evidence,
  "partial" as coverage_status,
  noteValue as coverage_note
