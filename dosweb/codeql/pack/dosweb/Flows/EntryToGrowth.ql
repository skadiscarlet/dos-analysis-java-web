/**
 * @name Entry to growth data flow
 * @description Proves attacker input flow from real framework handlers to a growth demand.
 * @kind table
 * @id dosweb/entry-to-growth
 */

import java
import EntryGrowthDomain

from Method source, Parameter input, Element sinkSite, string target, string sinkText,
     string path, string phase, string confidence, string coverage, string note
where EntryGrowthPathDomain::entryGrowthPath(
  source, input, sinkSite, target, sinkText, path, phase, confidence, coverage, note
)
select source.getLocation().getFile().getRelativePath() as source_file,
  source.getLocation().getStartLine() as source_start_line,
  sinkSite.getLocation().getFile().getRelativePath() as sink_file,
  sinkSite.getLocation().getStartLine() as sink_start_line,
  target as attacker_target, input.getName() as attacker_source, sinkText as attacker_sink,
  path as call_path, phase as phase_sequence, "data_flow" as flow_kind,
  confidence, coverage as coverage_status, note as coverage_note
