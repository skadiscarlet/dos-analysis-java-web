/** Generic Servlet request-body helper -> structured parser materialization domain. */

import java
import semmle.code.java.dataflow.DataFlow

predicate servletRequestRole(Type type) {
  exists(RefType requestType |
    requestType = type and
    requestType.getASupertype*().getName() = ["HttpServletRequest", "ServletRequest"]
  )
}

predicate httpServletRequestWrapperType(RefType type) {
  type.getASupertype*().hasQualifiedName(
    "javax.servlet.http", "HttpServletRequestWrapper"
  )
  or
  type.getASupertype*().hasQualifiedName(
    "jakarta.servlet.http", "HttpServletRequestWrapper"
  )
}

predicate httpServletRequestParameter(Parameter request) {
  request.getType().(RefType).getASupertype*().hasQualifiedName(
    "javax.servlet.http", "HttpServletRequest"
  )
  or
  request.getType().(RefType).getASupertype*().hasQualifiedName(
    "jakarta.servlet.http", "HttpServletRequest"
  )
}

/** A request stream is owned by a wrapper constructor only when the exact
 * getter receiver is that constructor's Servlet request parameter. */
predicate requestWrapperConstructorStream(
  MethodCall getter, Parameter request
) {
  exists(Constructor constructor, VarAccess receiver |
    httpServletRequestWrapperType(constructor.getDeclaringType()) and
    request = constructor.getAParameter() and
    httpServletRequestParameter(request) and
    getter.getEnclosingCallable() = constructor and
    getter.getMethod().getName() = ["getInputStream", "getReader"] and
    getter.getNumArgument() = 0 and
    receiver = getter.getQualifier() and receiver.getVariable() = request
  )
}

predicate requestBodyValueType(Type type) {
  type.(RefType).hasQualifiedName("java.lang", "String")
  or
  type instanceof Array and type.(Array).getElementType().hasName(["byte", "char"])
}

predicate requestMetadataAccessorName(string name) {
  name = [
    "getRequestURI", "getRequestURL", "getQueryString", "getHeader", "getHeaders",
    "getHeaderNames", "getCookie", "getCookies", "getSession", "getParameter",
    "getParameterMap", "getParameterNames", "getParameterValues", "getPathInfo",
    "getPathTranslated", "getServletPath", "getContextPath"
  ]
}

predicate requestBodyHelperName(string name) {
  name = [
    "getRequestString", "readRequestBody", "readBody", "readAll", "readAllBytes",
    "copyToString", "bodyAsString", "bodyAsBytes"
  ]
}

/** A bounded helper role: it directly accepts a Servlet request and returns body-shaped data. */
predicate requestBodyHelperCall(MethodCall helper, Expr request) {
  exists(int requestIndex |
    request = helper.getArgument(requestIndex) and servletRequestRole(request.getType())
  ) and
  requestBodyHelperName(helper.getMethod().getName()) and
  not requestMetadataAccessorName(helper.getMethod().getName()) and
  requestBodyValueType(helper.getType())
}

predicate structuredParserCall(MethodCall parser) {
  parser.getMethod().getName() = [
    "parse", "readValue", "fromJson", "parseObject", "parseArray"
  ]
}

/** The helper result must be consumed as parser input in the same callable. */
predicate structuredParserConsumes(
  MethodCall parser, MethodCall helper, Expr parserInput
) {
  structuredParserCall(parser) and
  parser.getEnclosingCallable() = helper.getEnclosingCallable() and
  exists(int inputIndex |
    parserInput = parser.getArgument(inputIndex) and
    DataFlow::localFlow(
      DataFlow::exprNode(helper), DataFlow::exprNode(parserInput)
    )
  )
}

predicate requestBodyHelperParserMaterialization(
  MethodCall helper, MethodCall parser, Expr request, Expr parserInput
) {
  requestBodyHelperCall(helper, request) and
  structuredParserConsumes(parser, helper, parserInput)
}
