/**
 * @name Phase 1 Web DoS Candidates
 * @description Find HTTP entry points that reach state writes (session/context attributes).
 *              Uses 2-hop call graph reachability for Phase 1.
 * @kind problem
 * @problem.severity warning
 * @id java/web-dos-phase1
 * @tags security
 *       web
 *       dos
 */

import java
import semmle.code.java.dataflow.DataFlow
import lib.WebSources
import lib.Persistence

/**
 * StateWrite abstraction: writes to session or context attributes.
 * These are the accumulation points we're interested in for Web DoS.
 */
abstract class StateWrite extends MethodCall {
  /** Get a descriptive label for the write type */
  abstract string getWriteType();

  /** Get the key/name expression used for storage */
  abstract Expr getKeyExpr();

  /** Get the value expression being stored */
  abstract Expr getValueExpr();
}

/**
 * Session attribute write: HttpSession.setAttribute(name, value)
 */
class SessionWrite extends StateWrite, SessionAttributeWrite {
  override string getWriteType() { result = "session" }

  override Expr getKeyExpr() { result = this.getAttributeName() }

  override Expr getValueExpr() { result = this.getAttributeValue() }
}

/**
 * Context attribute write: ServletContext.setAttribute(name, value)
 */
class ContextWrite extends StateWrite, ServletContextAttributeWrite {
  override string getWriteType() { result = "context" }

  override Expr getKeyExpr() { result = this.getAttributeName() }

  override Expr getValueExpr() { result = this.getAttributeValue() }
}

/**
 * 2-hop reachability: entry -> intermediate -> write.
 * This is a simplified call graph traversal without full dataflow.
 */
predicate reaches2Hop(Callable entry, Callable write) {
  // Direct call (1-hop)
  exists(MethodCall ma |
    ma.getEnclosingCallable() = entry and
    ma.getCallee() = write
  )
  or
  // Via one intermediate method (2-hop)
  exists(Callable intermediate, MethodCall ma1, MethodCall ma2 |
    ma1.getEnclosingCallable() = entry and
    ma1.getCallee() = intermediate and
    ma2.getEnclosingCallable() = intermediate and
    ma2.getCallee() = write
  )
}

from HttpEntryPoint entry, StateWrite write
where
  reaches2Hop(entry, write.getEnclosingCallable()) and
  entry.isExternallyAccessible()
select write,
  "DoS candidate: $@ reaches state write (" + write.getWriteType() + ")",
  entry,
  entry.getDeclaringType().getName() + "." + entry.getName()
