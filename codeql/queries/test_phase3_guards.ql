/**
 * @name Test Phase 3 Guards
 * @description Smoke test for WebGuards reachability classification.
 * @kind table
 * @id java/web-dos-test-phase3-guards
 */

import java
import lib.WebSources
import lib.WebGuards

from HttpEntryPoint entry
select entry, entry.getFramework(), entry.getEntryType(), reachabilityFor(entry)
