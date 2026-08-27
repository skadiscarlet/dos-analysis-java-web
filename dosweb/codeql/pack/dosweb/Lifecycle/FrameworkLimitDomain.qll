/** Exact, source-backed framework request-limit domains. */
import java
import semmle.code.java.controlflow.Guards

predicate frameworkTerminalReject(IfStmt site) {
  site.getThen() instanceof ThrowStmt
  or site.getThen() instanceof ReturnStmt
  or exists(BlockStmt block, Stmt terminal |
    block = site.getThen() and block.getNumStmt() = 1 and
    terminal = block.getStmt(0) and
    (terminal instanceof ThrowStmt or terminal instanceof ReturnStmt)
  )
}

predicate byteGrowthIdentity(MethodCall growth, string receiver, string fieldPath) {
  growth.getMethod().getName() = ["allocate", "allocateDirect"] and
  growth.getMethod().getDeclaringType().hasQualifiedName("java.nio", "ByteBuffer") and
  receiver = growth.getMethod().getDeclaringType().getQualifiedName() and fieldPath = "allocation"
  or
  growth.getMethod().hasQualifiedName("java.io", "ByteArrayOutputStream", "toByteArray") and
  receiver = growth.getQualifier().toString() and fieldPath = receiver
  or
  growth.getMethod().getName() = "readAllBytes" and
  growth.getMethod().getDeclaringType().getASupertype*().hasQualifiedName("java.io", "InputStream") and
  receiver = growth.getQualifier().toString() and fieldPath = receiver
  or
  growth.getMethod().hasQualifiedName("cn.hutool.core.io", "IoUtil", "readBytes") and
  receiver = growth.getArgument(0).toString() and fieldPath = receiver
  or
  growth.getMethod().hasQualifiedName("org.apache.commons.io", "IOUtils", "toByteArray") and
  receiver = growth.getArgument(0).toString() and fieldPath = receiver
  or
  growth.getMethod().hasQualifiedName("org.springframework.util", "StreamUtils", ["copyToByteArray", "copyToString"]) and
  receiver = growth.getArgument(0).toString() and fieldPath = receiver
}

predicate byteAllocationGrowth(
  MethodCall growth, Expr demand, string receiver, string fieldPath
) {
  growth.getMethod().getName() = ["allocate", "allocateDirect"] and
  growth.getMethod().getDeclaringType().hasQualifiedName("java.nio", "ByteBuffer") and
  growth.getNumArgument() = 1 and demand = growth.getArgument(0) and
  receiver = growth.getMethod().getDeclaringType().getQualifiedName() and
  fieldPath = "allocation"
}

predicate sameDemandDriver(Expr left, Expr right) {
  left = right
  or exists(VarAccess leftAccess, VarAccess rightAccess |
    left = leftAccess and right = rightAccess and
    leftAccess.getVariable() = rightAccess.getVariable()
  )
}

predicate jacksonStreamReadConstraintsLimit(
  Element site, MethodCall growth, string value, string receiver, string fieldPath
) {
  exists(MethodCall limit, MethodCall build, CompileTimeConstantExpr configured,
         MethodCall validation, Expr demand |
    site = limit and limit.getMethod().getName() = "maxStringLength" and
    limit.getMethod().getDeclaringType().getQualifiedName().matches("%StreamReadConstraints%") and
    configured = limit.getArgument(0) and value = configured.toString() and
    validation.getMethod().hasQualifiedName(
      "com.fasterxml.jackson.core", "StreamReadConstraints", "validateStringLength"
    ) and validation.getNumArgument() = 1 and
    validation.getQualifier() = build and build.getMethod().getName() = "build" and
    build.getQualifier() = limit and
    sameDemandDriver(demand, validation.getArgument(0)) and
    validation.getEnclosingCallable() = growth.getEnclosingCallable() and
    validation.getBasicBlock().dominates(growth.getBasicBlock()) and
    byteAllocationGrowth(growth, demand, receiver, fieldPath)
  )
}

predicate nettyAggregatedRequestDemand(MethodCall growth, Method handler) {
  exists(Expr demand, MethodCall readable, MethodCall content, Parameter request,
         VarAccess requestAccess |
    byteAllocationGrowth(growth, demand, _, _) and demand = readable and
    readable.getMethod().getName() = "readableBytes" and readable.getNumArgument() = 0 and
    readable.getQualifier() = content and content.getMethod().getName() = "content" and
    content.getNumArgument() = 0 and content.getQualifier() = requestAccess and
    requestAccess.getVariable() = request and request = handler.getParameter(1) and
    request.getType().(RefType).getASupertype*().hasQualifiedName(
      "io.netty.handler.codec.http", "FullHttpRequest"
    )
  )
}

predicate nettyHttpObjectAggregatorLimit(
  Element site, MethodCall growth, string value, string receiver, string fieldPath
) {
  exists(
    ClassInstanceExpr aggregator, CompileTimeConstantExpr configured,
    MethodCall aggregatorRegistration, MethodCall handlerRegistration,
    ClassInstanceExpr handlerConstruction, Callable registration, Method handler |
    site = aggregator and
    aggregator.getConstructedType().hasQualifiedName(
      "io.netty.handler.codec.http", "HttpObjectAggregator"
    ) and
    configured = aggregator.getArgument(0) and value = configured.toString() and
    aggregatorRegistration.getMethod().getName() = "addLast" and
    aggregatorRegistration.getArgument(0) = aggregator and
    handlerRegistration.getMethod().getName() = "addLast" and
    handlerRegistration.getArgument(0) = handlerConstruction and
    registration = aggregatorRegistration.getEnclosingCallable() and
    registration = handlerRegistration.getEnclosingCallable() and
    aggregatorRegistration.getQualifier().toString() = handlerRegistration.getQualifier().toString() and
    aggregatorRegistration.getBasicBlock().dominates(handlerRegistration.getBasicBlock()) and
    handler = growth.getEnclosingCallable() and
    handler.getDeclaringType() = handlerConstruction.getConstructedType() and
    nettyAggregatedRequestDemand(growth, handler) and
    byteAllocationGrowth(growth, _, receiver, fieldPath)
  )
}

predicate servletRequestDemand(Expr demand, Method handler) {
  exists(Parameter request, VarAccess requestAccess |
    request = handler.getAParameter() and
    request.getType().(RefType).getASupertype*().hasQualifiedName(
      ["javax.servlet.http", "jakarta.servlet.http"], "HttpServletRequest"
    ) and requestAccess.getVariable() = request and requestAccess.getParent*() = demand
  )
}

predicate servletMultipartLimit(
  Element site, MethodCall growth, string value, string receiver, string fieldPath
) {
  exists(Method handler, Annotation config, CompileTimeConstantExpr configured,
         Expr demand |
    handler = growth.getEnclosingCallable() and
    config = handler.getDeclaringType().getAnAnnotation() and site = config and
    config.getType().hasQualifiedName(
      ["javax.servlet.annotation", "jakarta.servlet.annotation"], "MultipartConfig"
    ) and
    configured = config.getValue("maxRequestSize") and value = configured.toString() and
    servletRequestDemand(demand, handler) and
    byteAllocationGrowth(growth, demand, receiver, fieldPath)
  )
}

predicate solrFormDataLimit(
  Element site, MethodCall growth, string value, string receiver, string fieldPath
) {
  exists(IfStmt check, Field limit, FieldAccess access, CompileTimeConstantExpr configured,
         CompileTimeConstantExpr contentType |
    site = check and growth.getMethod().hasQualifiedName(
      "java.io", "ByteArrayOutputStream", "toByteArray"
    ) and
    check.getEnclosingCallable() = growth.getEnclosingCallable() and
    access.getField() = limit and limit.getName() = "formdataUploadLimitInKB" and
    access.getParent*() = check.getCondition() and
    configured = limit.getInitializer() and value = configured.toString() and
    contentType.getEnclosingCallable() = growth.getEnclosingCallable() and
    contentType.getStringValue() = "application/x-www-form-urlencoded" and
    frameworkTerminalReject(check) and check.getBasicBlock().dominates(growth.getBasicBlock()) and
    not check.getThen().getControlFlowNode().getASuccessor*() = growth.getControlFlowNode() and
    byteGrowthIdentity(growth, receiver, fieldPath)
  )
}

predicate frameworkLimitCandidate(
  Element site, MethodCall growth, string configurationKey, string configurationValue,
  string requestEncoding, string receiver, string fieldPath, string evidence
) {
  jacksonStreamReadConstraintsLimit(site, growth, configurationValue, receiver, fieldPath) and
  configurationKey = "literal" and requestEncoding = "json" and
    evidence = "jackson_stream_read_constraints_literal"
  or
  nettyHttpObjectAggregatorLimit(site, growth, configurationValue, receiver, fieldPath) and
  configurationKey = "literal" and requestEncoding = "aggregated_http" and
  evidence = "netty_http_object_aggregator_literal"
  or
  servletMultipartLimit(site, growth, configurationValue, receiver, fieldPath) and
  configurationKey = "literal" and requestEncoding = "multipart" and
    evidence = "servlet_multipart_config_literal"
  or
  solrFormDataLimit(site, growth, configurationValue, receiver, fieldPath) and
  configurationKey = "literal" and requestEncoding = "form_urlencoded" and
    evidence = "solr_formdata_upload_limit_literal"
}
