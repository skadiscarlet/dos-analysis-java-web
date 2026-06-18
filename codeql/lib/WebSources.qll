/**
 * @name WebSources
 * @description HTTP entry point detection and session/context attribute write detection for web application DoS analysis
 */

import java
import semmle.code.java.frameworks.Servlets
import semmle.code.java.frameworks.spring.Spring

/**
 * Servlet entry method: doGet, doPost, doPut, doDelete, service, etc.
 */
class ServletEntryMethod extends Method {
  ServletEntryMethod() {
    this.getDeclaringType().getASupertype*().hasQualifiedName("javax.servlet.http", "HttpServlet") and
    (
      this.hasName("doGet") or
      this.hasName("doPost") or
      this.hasName("doPut") or
      this.hasName("doDelete") or
      this.hasName("doHead") or
      this.hasName("doOptions") or
      this.hasName("doTrace") or
      this.hasName("service")
    ) and
    this.getNumberOfParameters() = 2 and
    this.getParameter(0).getType().(RefType).hasQualifiedName("javax.servlet.http", "HttpServletRequest") and
    this.getParameter(1).getType().(RefType).hasQualifiedName("javax.servlet.http", "HttpServletResponse")
  }

  /** Get the HttpServletRequest parameter */
  Parameter getRequestParameter() { result = this.getParameter(0) }

  /** Get the HttpServletResponse parameter */
  Parameter getResponseParameter() { result = this.getParameter(1) }
}

/**
 * HttpSession.setAttribute call
 */
class SessionAttributeWrite extends MethodCall {
  SessionAttributeWrite() {
    this.getMethod().hasName("setAttribute") and
    this.getMethod().getDeclaringType().hasQualifiedName("javax.servlet.http", "HttpSession") and
    this.getMethod().getNumberOfParameters() = 2
  }

  /** Get the attribute name expression */
  Expr getAttributeName() { result = this.getArgument(0) }

  /** Get the attribute value expression */
  Expr getAttributeValue() { result = this.getArgument(1) }

  /** Get the attribute name if it's a compile-time constant */
  string getAttributeNameString() { result = this.getAttributeName().(CompileTimeConstantExpr).getStringValue() }
}

/**
 * ServletContext.setAttribute call
 */
class ServletContextAttributeWrite extends MethodCall {
  ServletContextAttributeWrite() {
    this.getMethod().hasName("setAttribute") and
    this.getMethod().getDeclaringType().hasQualifiedName("javax.servlet", "ServletContext") and
    this.getMethod().getNumberOfParameters() = 2
  }

  /** Get the attribute name expression */
  Expr getAttributeName() { result = this.getArgument(0) }

  /** Get the attribute value expression */
  Expr getAttributeValue() { result = this.getArgument(1) }

  /** Get the attribute name if it's a compile-time constant */
  string getAttributeNameString() { result = this.getAttributeName().(CompileTimeConstantExpr).getStringValue() }
}

/**
 * Spring Controller method (simplified detection for Phase 1)
 */
class SpringControllerMethod extends Method {
  SpringControllerMethod() {
    (
      this.getDeclaringType().getAnAnnotation().getType().hasQualifiedName("org.springframework.stereotype", "Controller") or
      this.getDeclaringType().getAnAnnotation().getType().hasQualifiedName("org.springframework.web.bind.annotation", "RestController")
    ) and
    (
      this.getAnAnnotation().getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestMapping") or
      this.getAnAnnotation().getType().hasQualifiedName("org.springframework.web.bind.annotation", "GetMapping") or
      this.getAnAnnotation().getType().hasQualifiedName("org.springframework.web.bind.annotation", "PostMapping") or
      this.getAnAnnotation().getType().hasQualifiedName("org.springframework.web.bind.annotation", "PutMapping") or
      this.getAnAnnotation().getType().hasQualifiedName("org.springframework.web.bind.annotation", "DeleteMapping") or
      this.getAnAnnotation().getType().hasQualifiedName("org.springframework.web.bind.annotation", "PatchMapping")
    )
  }

  /** Check if this method has a path parameter */
  predicate hasPathVariable() {
    exists(Parameter p |
      p = this.getAParameter() and
      p.getAnAnnotation().getType().hasQualifiedName("org.springframework.web.bind.annotation", "PathVariable")
    )
  }

  /** Check if this method has a request parameter */
  predicate hasRequestParam() {
    exists(Parameter p |
      p = this.getAParameter() and
      p.getAnAnnotation().getType().hasQualifiedName("org.springframework.web.bind.annotation", "RequestParam")
    )
  }
}

/**
 * Unified HTTP entry point abstraction
 */
abstract class HttpEntryPoint extends Method {
  /** Get the framework: servlet, spring, jetty, undertow, or jaxrs */
  abstract string getFramework();

  /** Get the entry type for the specific framework */
  abstract string getEntryType();

  /** Check if a parameter is clearly server-controlled output/context. */
  predicate isServerControlledParam(Parameter p) {
    p.getType().getName().regexpMatch(".*(Response|ServletResponse|Model|BindingResult|Principal|Authentication|SessionStatus|Errors|Writer|OutputStream).*")
    or p.getName().regexpMatch("(?i).*(response|resp|model|bindingResult|principal|authentication|sessionStatus|errors|writer|output).*")
  }

  /** Get an attacker-controlled parameter with Stream or Unlimited value space */
  Parameter getAnAttackerControlledParam() {
    result = this.getAParameter() and
    paramValueSpace(result) in ["Stream", "Unlimited"] and
    not this.isServerControlledParam(result)
  }

  /** Check if this entry point is externally accessible (no strong auth guard) */
  predicate isExternallyAccessible() {
    // Phase 1: simplified - all HTTP entry points are considered externally accessible
    // Phase 2 will add auth guard detection
    any()
  }
}

/**
 * Servlet-based HTTP entry point
 */
class ServletHttpEntryPoint extends HttpEntryPoint, ServletEntryMethod {
  override string getFramework() { result = "servlet" }

  override string getEntryType() { result = "servlet:" + this.getName() }
}

/**
 * Spring-based HTTP entry point
 */
class SpringHttpEntryPoint extends HttpEntryPoint, SpringControllerMethod {
  override string getFramework() { result = "spring" }

  override string getEntryType() { result = "spring:controller" }
}

/**
 * Jetty handler method: handle(String, Request, HttpServletRequest, HttpServletResponse)
 */
class JettyHandlerMethod extends Method {
  JettyHandlerMethod() {
    this.getDeclaringType().getASupertype*()
      .hasQualifiedName("org.eclipse.jetty.server.handler", "AbstractHandler") and
    this.hasName("handle") and
    this.getNumberOfParameters() = 4 and
    this.getParameter(0).getType().(RefType).hasQualifiedName("java.lang", "String") and
    this.getParameter(1).getType().getName().matches("%Request%") and
    this.getParameter(2).getType().(RefType).hasQualifiedName("javax.servlet.http", "HttpServletRequest") and
    this.getParameter(3).getType().(RefType).hasQualifiedName("javax.servlet.http", "HttpServletResponse")
  }

  /** Get the target parameter (URL path) */
  Parameter getTargetParameter() { result = this.getParameter(0) }

  /** Get the base Request parameter */
  Parameter getBaseRequestParameter() { result = this.getParameter(1) }

  /** Get the HttpServletRequest parameter */
  Parameter getRequestParameter() { result = this.getParameter(2) }

  /** Get the HttpServletResponse parameter */
  Parameter getResponseParameter() { result = this.getParameter(3) }
}

/**
 * Jetty-based HTTP entry point
 */
class JettyHttpEntryPoint extends HttpEntryPoint, JettyHandlerMethod {
  override string getFramework() { result = "jetty" }

  override string getEntryType() { result = "jetty:handler" }
}

/**
 * Undertow HTTP handler: handleRequest(HttpServerExchange)
 */
class UndertowHttpHandler extends Method {
  UndertowHttpHandler() {
    this.getDeclaringType().getASupertype*()
      .hasQualifiedName("io.undertow.server", "HttpHandler") and
    this.hasName("handleRequest") and
    this.getNumberOfParameters() = 1 and
    this.getParameter(0).getType().(RefType).hasQualifiedName("io.undertow.server", "HttpServerExchange")
  }

  /** Get the HttpServerExchange parameter */
  Parameter getExchangeParameter() { result = this.getParameter(0) }
}

/**
 * Undertow-based HTTP entry point
 */
class UndertowHttpEntryPoint extends HttpEntryPoint, UndertowHttpHandler {
  override string getFramework() { result = "undertow" }

  override string getEntryType() { result = "undertow:handler" }
}

/**
 * JAX-RS resource method: @GET, @POST, @PUT, @DELETE, @PATCH
 */
class JAXRSResourceMethod extends Method {
  JAXRSResourceMethod() {
    exists(Annotation a | a = this.getAnAnnotation() |
      (a.getType().getPackage().getName().matches("javax.ws.rs%") or a.getType().getPackage().getName().matches("jakarta.ws.rs%")) and
      a.getType().getName() in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
    )
  }

  /** Get the HTTP method annotation */
  Annotation getHttpMethodAnnotation() {
    result = this.getAnAnnotation() and
    (result.getType().getPackage().getName().matches("javax.ws.rs%") or result.getType().getPackage().getName().matches("jakarta.ws.rs%")) and
    result.getType().getName() in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
  }

  /** Get the HTTP method name */
  string getHttpMethod() {
    result = this.getHttpMethodAnnotation().getType().getName()
  }
}

/**
 * JAX-RS-based HTTP entry point
 */
class JAXRSHttpEntryPoint extends HttpEntryPoint, JAXRSResourceMethod {
  override string getFramework() { result = "jaxrs" }

  override string getEntryType() { result = "jaxrs:" + this.getHttpMethod().toLowerCase() }
}

/**
 * L2: 参数值空间分类
 * 基于参数类型判断：Stream / Unlimited / Limited
 */
string paramValueSpace(Parameter p) {
  exists(string tn | tn = p.getType().getName() |
    // Stream: 单次请求可灌入任意大小数据
    (tn.regexpMatch(".*Stream|MultipartFile|Part|.*Channel|ReadableByteChannel")
      and result = "Stream")
    or
    // Unlimited: 攻击者可构造无限多个不同值
    (tn.regexpMatch("String|CharSequence|.*\\[\\]|Map|List|Set|Object|JsonNode|Bundle")
      and not tn.regexpMatch(".*Stream|MultipartFile|Part|.*Channel")
      and result = "Unlimited")
    or
    // Limited: 有限值集合
    ((tn in ["boolean", "Boolean"] or p.getType() instanceof EnumType)
      and result = "Limited")
    or
    // 数值类型默认 Limited
    (tn in ["int", "long", "Integer", "Long", "short", "byte", "float", "double"]
      and result = "Limited")
    or
    // 兜底：复杂对象视为 Unlimited
    result = "Unlimited"
  )
}
