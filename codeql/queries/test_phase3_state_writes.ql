/**
 * @name Test Phase 3 State Writes
 * @description Smoke test for Web session/context/container client-state writes.
 * @kind table
 * @id java/web-dos-test-phase3-state-writes
 */

import java
import lib.SessionState

from WebClientStateWrite write
select write,
  write.getWebEntry().getFramework(),
  write.getWebEntry().getQualifiedName(),
  write.getSinkKind(),
  write.getContainerKind(),
  write.getLifespan(),
  write.getPathKind(),
  keyKind(write.getKeyExpr()),
  write.getKeyExpr(),
  write.getValueExpr(),
  write.getEvidence()
