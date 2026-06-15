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
  /** Get the entry type: "servlet" or "spring" */
  abstract string getEntryType();

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
  override string getEntryType() { result = "servlet" }
}

/**
 * Spring-based HTTP entry point
 */
class SpringHttpEntryPoint extends HttpEntryPoint, SpringControllerMethod {
  override string getEntryType() { result = "spring" }
}
