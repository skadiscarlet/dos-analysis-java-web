/**
 * @name Test Undertow Entry Detection
 * @description 验证 Undertow handler 识别
 * @kind problem
 */

import java

class UndertowHttpHandler extends Method {
  UndertowHttpHandler() {
    this.getDeclaringType().getASupertype*()
      .hasQualifiedName("io.undertow.server", "HttpHandler") and
    this.hasName("handleRequest") and
    this.getNumberOfParameters() = 1
  }
}

from UndertowHttpHandler m
select m, "Undertow handler: " + m.getDeclaringType().getQualifiedName() + "." + m.getName()
