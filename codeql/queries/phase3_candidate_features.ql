/**
 * @name Phase 3 Candidate Features
 * @description Unified candidate feature extraction for Java Web client-state retention DoS.
 * @kind table
 * @id java/web-dos-phase3-candidate-features
 */

import java
import lib.CommonDoS
import lib.SessionState

string entryFqn(WebClientStateEntry entry) {
  result = entry.getDeclaringType().getQualifiedName() + "." + entry.getName()
}

string fileOf(Element element) {
  exists(Location location |
    location = element.getLocation() and
    result = location.getFile().getRelativePath()
  )
  or
  not exists(Location location | location = element.getLocation()) and
  result = "<unknown>"
}

int lineOf(Element element) {
  exists(Location location |
    location = element.getLocation() and
    result = location.getStartLine()
  )
  or
  not exists(Location location | location = element.getLocation()) and
  result = 0
}

string strongestEntryValueSpace(WebClientStateEntry entry) {
  exists(Parameter p |
    p = entry.getAnAttackerControlledParam() and
    paramValueSpace(p) = "Stream"
  ) and result = "Stream"
  or
  not exists(Parameter p |
    p = entry.getAnAttackerControlledParam() and
    paramValueSpace(p) = "Stream"
  ) and exists(Parameter p |
    p = entry.getAnAttackerControlledParam() and
    paramValueSpace(p) = "Unlimited"
  ) and result = "Unlimited"
  or
  not exists(Parameter p |
    p = entry.getAnAttackerControlledParam() and
    paramValueSpace(p) in ["Stream", "Unlimited"]
  ) and result = "Uncontrollable"
}

from WebClientStateWrite write, WebClientStateEntry entry,
  string axis_r, string axis_v, string axis_m, string axis_c, string axis_l
where
  entry = write.getWebEntry() and
  axis_r = entry.getReachability() and
  axis_v = axisV(strongestEntryValueSpace(entry), write.getKeyExpr()) and
  axis_m = axisM(write.getKeyExpr()) and
  axis_c = axisC(write.getEnclosingCallable()) and
  axis_l = write.getLifespan()
select
  entry.getFramework() as framework,
  entryFqn(entry) as entry_fqn,
  fileOf(entry) as entry_file,
  lineOf(entry) as entry_line,
  write.getSinkKind() as sink_kind,
  fileOf(write) as sink_file,
  lineOf(write) as sink_line,
  keyKind(write.getKeyExpr()) as key_kind,
  write.getContainerKind() as container_kind,
  axis_r,
  axis_v,
  axis_m,
  axis_c,
  axis_l,
  drdVerdict(axis_v, axis_c, axis_l) as verdict_drd,
  exploitVerdict5(axis_r, axis_v, axis_m, axis_c, axis_l) as verdict,
  write.getEvidence() as evidence
