/**
 * @name Test Jetty Entry Detection
 * @description 验证 Jetty handler 识别
 * @kind problem
 */

import java
import semmle.code.java.frameworks.Servlets

// Jetty Handler Detection
class JettyHandlerMethod extends Method {
  JettyHandlerMethod() {
    this.getDeclaringType().getASupertype*()
      .hasQualifiedName("org.eclipse.jetty.server.handler", "AbstractHandler") and
    this.hasName("handle") and
    this.getNumberOfParameters() = 4
  }
}

from JettyHandlerMethod m
select m, "Jetty handler: " + m.getDeclaringType().getQualifiedName() + "." + m.getName()
