/**
 * @name Phase 2 Source Discovery
 * @description 自动识别 HTTP entry points 及参数值空间
 * @kind problem
 * @id java/web-dos-phase2-source-discovery
 */

import java
import semmle.code.java.frameworks.Servlets
import semmle.code.java.frameworks.spring.Spring

// Servlet Entry
class ServletEntryMethod extends Method {
  ServletEntryMethod() {
    this.getDeclaringType().getASupertype*().hasQualifiedName("javax.servlet.http", "HttpServlet") and
    this.hasName(["doGet", "doPost", "doPut", "doDelete", "doHead", "doOptions", "doTrace", "service"]) and
    this.getNumberOfParameters() = 2
  }
}

// Spring Controller Entry
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
}

// Jetty Handler
class JettyHandlerMethod extends Method {
  JettyHandlerMethod() {
    this.getDeclaringType().getASupertype*()
      .hasQualifiedName("org.eclipse.jetty.server.handler", "AbstractHandler") and
    this.hasName("handle") and
    this.getNumberOfParameters() = 4
  }
}

// Undertow Handler
class UndertowHttpHandler extends Method {
  UndertowHttpHandler() {
    this.getDeclaringType().getASupertype*()
      .hasQualifiedName("io.undertow.server", "HttpHandler") and
    this.hasName("handleRequest") and
    this.getNumberOfParameters() = 1
  }
}

// JAX-RS Resource
class JAXRSResourceMethod extends Method {
  JAXRSResourceMethod() {
    exists(Annotation a | a = this.getAnAnnotation() |
      (a.getType().getPackage().getName().matches("javax.ws.rs%") or a.getType().getPackage().getName().matches("jakarta.ws.rs%")) and
      a.getType().getName() in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
    )
  }
}

// Unified Entry Point
class HttpEntryPoint extends Method {
  string framework;
  string entryType;

  HttpEntryPoint() {
    (this instanceof ServletEntryMethod and framework = "servlet" and entryType = "servlet:" + this.getName()) or
    (this instanceof SpringControllerMethod and framework = "spring" and entryType = "spring:controller") or
    (this instanceof JettyHandlerMethod and framework = "jetty" and entryType = "jetty:handler") or
    (this instanceof UndertowHttpHandler and framework = "undertow" and entryType = "undertow:handler") or
    (this instanceof JAXRSResourceMethod and framework = "jaxrs" and entryType = "jaxrs:resource")
  }

  string getFramework() { result = framework }
  string getEntryType() { result = entryType }
}

// Parameter Value Space Classification
string paramValueSpace(Parameter p) {
  exists(string tn | tn = p.getType().getName() |
    (tn.regexpMatch(".*Stream|MultipartFile|Part|.*Channel") and result = "Stream")
    or
    (tn.regexpMatch("String|CharSequence|.*\\[\\]|Map|List|Set|Object|JsonNode|Bundle")
      and not tn.regexpMatch(".*Stream|MultipartFile|Part|.*Channel")
      and result = "Unlimited")
    or
    ((tn in ["boolean", "Boolean"] or p.getType() instanceof EnumType) and result = "Limited")
    or
    (tn in ["int", "long", "Integer", "Long", "short", "byte", "float", "double"] and result = "Limited")
    or
    result = "Unlimited"
  )
}

// Main Query
from HttpEntryPoint entry, Parameter p, int idx
where
  p = entry.getParameter(idx) and
  idx < entry.getNumberOfParameters()
select
  entry,
  "Framework: " + entry.getFramework() +
  " | Class: " + entry.getDeclaringType().getQualifiedName() +
  " | Method: " + entry.getName() +
  " | EntryType: " + entry.getEntryType() +
  " | Param[" + idx.toString() + "]: " + p.getName() +
  " | Type: " + p.getType().getName() +
  " | ValueSpace: " + paramValueSpace(p)
