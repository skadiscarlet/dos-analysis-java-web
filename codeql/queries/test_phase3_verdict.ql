/**
 * @name Test Phase 3 Verdict
 * @description Smoke test for CommonDoS verdict functions.
 * @kind table
 * @id java/web-dos-test-phase3-verdict
 */

import java
import lib.CommonDoS

from string r, string v, string m, string c, string l
where
  r = "Open" and
  v = "Unlimited" and
  m = "Amplifiable" and
  c = "Unbounded" and
  l = "ProcessLifetime"
select "phase3-verdict-smoke", r, v, m, c, l, drdVerdict(v, c, l), exploitVerdict5(r, v, m, c, l)
