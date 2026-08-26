/**
 * @name Netty registered entries
 * @description Extracts channelRead callbacks with statically recoverable pipeline registration.
 * @kind table
 * @id dosweb/netty-entries
 */

import java

// Entry rows must originate from source, not dependency bytecode. Bytecode-only
// elements (a target/.../Foo.class resolved from a JAR) have no source line, so
// `getStartLine()` yields 0 and the shared decoder fails the query closed.
predicate isSourceMethod(Method method) {
  method.fromSource()
}

predicate isSourceCall(MethodCall call) {
  call.getLocation().getFile().getRelativePath().matches("%.java")
}

// Exact Task 3 contract:
// "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
// "registration_kind", "registration_fqn", "registration_file",
// "registration_start_line", "route_or_event", "auth_context",
// "attacker_input_name", "attacker_input_type", "attacker_input_kind",
// "materialization_phase", "coverage_status", "coverage_note"

predicate isNettyType(RefType type, string simpleName) {
  type.getASourceSupertype*().hasQualifiedName("fixture.netty", simpleName)
  or type.getASourceSupertype*().hasQualifiedName("io.netty.channel", simpleName)
}

predicate isInboundCallback(Method callback, Parameter message) {
  (callback.getName() = "channelRead" and message = callback.getParameter(1)) or
  (callback.getName() = "channelRead0" and message = callback.getParameter(1))
}

predicate isNettyFullHttpRequestType(Type type) {
  type.(RefType).getASupertype*().hasQualifiedName("io.netty.handler.codec.http", "FullHttpRequest")
}

/**
 * Recover a concrete HTTP route only when the registered FullHttpRequest
 * callback reads request.uri() into one local, forwards that exact captured
 * local to a private source helper, and the corresponding helper parameter is
 * the selector of a compile-time string switch.  Direct callback calls and one
 * lexically nested anonymous callback are supported; arbitrary field/virtual
 * dispatch remains unresolved.
 */
predicate sourceBackedSwitchRoute(Method callback, Parameter message, string route) {
  isNettyFullHttpRequestType(message.getType()) and
  exists(
    MethodCall uriCall, LocalVariableDecl uriLocal, MethodCall dispatchCall,
    Callable dispatchOwner, Method helper, int argumentIndex, Parameter routeParameter,
    SwitchStmt routeSwitch, ConstCase routeCase, CompileTimeConstantExpr routeValue |
    uriCall.getEnclosingCallable() = callback and uriCall.getMethod().getName() = "uri" and
    uriCall.getNumArgument() = 0 and
    uriCall.getQualifier().(VarAccess).getVariable() = message and
    uriLocal.getInitializer() = uriCall and
    dispatchOwner = dispatchCall.getEnclosingCallable() and
    (
      dispatchOwner = callback
      or dispatchOwner.getDeclaringType() instanceof AnonymousClass and
        dispatchOwner.getDeclaringType().(AnonymousClass).getClassInstanceExpr().getEnclosingCallable() = callback
    ) and
    dispatchCall.getMethod() = helper and helper.fromSource() and helper.isPrivate() and
    helper.getDeclaringType() = callback.getDeclaringType() and
    dispatchCall.getArgument(argumentIndex).(VarAccess).getVariable() = uriLocal and
    routeParameter = helper.getParameter(argumentIndex) and
    routeSwitch.getEnclosingCallable() = helper and
    routeSwitch.getExpr().(VarAccess).getVariable() = routeParameter and
    routeCase = routeSwitch.getAConstCase() and routeValue = routeCase.getValue() and
    route = routeValue.getStringValue() and route.matches("/%")
  )
}

/** A pipeline initializer is externally reachable only after a ServerBootstrap installs it. */
predicate bootstrapInstalls(Method init, MethodCall bootstrap) {
  bootstrap.getMethod().getName() = ["childHandler", "handler"] and
  bootstrap.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName("io.netty.bootstrap", "ServerBootstrap") and
  exists(ClassInstanceExpr initializer |
    initializer = bootstrap.getArgument(0) and
    initializer.getConstructedType().getSourceDeclaration() = init.getDeclaringType()
  )
}

predicate nettyRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method callback, Method init, MethodCall addLast, ClassInstanceExpr handler, Parameter message |
    isInboundCallback(callback, message) and isSourceMethod(callback) and isSourceCall(addLast) and
    (isNettyType(callback.getDeclaringType(), "ChannelInboundHandlerAdapter") or
     isNettyType(callback.getDeclaringType(), "SimpleChannelInboundHandler")) and
    init.getName() = "initChannel" and isNettyType(init.getDeclaringType(), "ChannelInitializer") and
    exists(MethodCall bootstrap | isSourceCall(bootstrap) and bootstrapInstalls(init, bootstrap)) and
    addLast.getEnclosingCallable() = init and addLast.getMethod().getName() = "addLast" and
    isNettyType(addLast.getMethod().getDeclaringType(), "ChannelPipeline") and
    handler = addLast.getArgument(addLast.getNumArgument() - 1) and
    handler.getConstructedType().getSourceDeclaration() = callback.getDeclaringType() and
    framework = "netty" and protocol = "tcp" and
    handlerFqn = callback.getDeclaringType().getQualifiedName() + "." + callback.getName() and
    handlerFile = callback.getLocation().getFile().getRelativePath() and handlerLine = callback.getLocation().getStartLine() and
    registrationKind = "pipeline_registration" and registrationFqn = init.getDeclaringType().getQualifiedName() + "." + init.getName() and
    registrationFile = addLast.getLocation().getFile().getRelativePath() and registrationLine = addLast.getLocation().getStartLine() and
    authContext = "unknown" and inputName = message.getName() and
    inputType = message.getType().toString() and inputKind = "message_payload" and materializationPhase = "streaming" and
    coverageStatus = "complete" and
    (
      routeOrEvent = "channelRead" and coverageNote = "netty_pipeline_registration"
      or sourceBackedSwitchRoute(callback, message, routeOrEvent) and
        coverageNote = "netty_source_switch_route_alias"
    )
  )
  or exists(Method callback, Method init, MethodCall addLast, ClassInstanceExpr handler, Parameter message |
    isInboundCallback(callback, message) and isSourceMethod(callback) and isSourceCall(addLast) and
    init.getName() = "initChannel" and isNettyType(init.getDeclaringType(), "ChannelInitializer") and
    addLast.getEnclosingCallable() = init and addLast.getMethod().getName() = "addLast" and
    isNettyType(addLast.getMethod().getDeclaringType(), "ChannelPipeline") and
    handler = addLast.getArgument(addLast.getNumArgument() - 1) and
    handler.getConstructedType().getSourceDeclaration() = callback.getDeclaringType() and
    not exists(MethodCall bootstrap | isSourceCall(bootstrap) and bootstrapInstalls(init, bootstrap)) and
    framework = "netty" and protocol = "tcp" and
    handlerFqn = callback.getDeclaringType().getQualifiedName() + "." + callback.getName() and
    handlerFile = callback.getLocation().getFile().getRelativePath() and handlerLine = callback.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = init.getDeclaringType().getQualifiedName() + "." + init.getName() and
    registrationFile = addLast.getLocation().getFile().getRelativePath() and registrationLine = addLast.getLocation().getStartLine() and
    routeOrEvent = "channelRead" and authContext = "unknown" and inputName = message.getName() and
    inputType = message.getType().toString() and inputKind = "message_payload" and materializationPhase = "streaming" and
    coverageStatus = "partial" and coverageNote = "netty_initializer_not_installed_by_bootstrap"
  )
  or exists(MethodCall addLast, Method enclosing |
    addLast.getMethod().getName() = "addLast" and isNettyType(addLast.getMethod().getDeclaringType(), "ChannelPipeline") and
    enclosing = addLast.getEnclosingCallable() and not addLast.getArgument(addLast.getNumArgument() - 1) instanceof ClassInstanceExpr and
    isSourceMethod(enclosing) and isSourceCall(addLast) and
    framework = "netty" and protocol = "tcp" and handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and
    handlerFile = enclosing.getLocation().getFile().getRelativePath() and handlerLine = enclosing.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and registrationFile = addLast.getLocation().getFile().getRelativePath() and
    registrationLine = addLast.getLocation().getStartLine() and routeOrEvent = "channelRead" and authContext = "unknown" and
    inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and materializationPhase = "unknown" and
    coverageStatus = "partial" and coverageNote = "unresolved_pipeline_handler"
  )
  or exists(MethodCall call, Method enclosing |
    call.getMethod().hasQualifiedName("java.lang", "Class", "forName") and enclosing = call.getEnclosingCallable() and
    isSourceMethod(enclosing) and isSourceCall(call) and
    isNettyType(enclosing.getDeclaringType(), "ChannelInitializer") and framework = "netty" and protocol = "tcp" and
    handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and handlerFile = enclosing.getLocation().getFile().getRelativePath() and
    handlerLine = enclosing.getLocation().getStartLine() and registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = call.getLocation().getFile().getRelativePath() and registrationLine = call.getLocation().getStartLine() and routeOrEvent = "channelRead" and
    authContext = "unknown" and inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and materializationPhase = "unknown" and
    coverageStatus = "partial" and coverageNote = "reflection_pipeline_registration"
  )
}

from string framework, string protocol, string handlerFqn, string handlerFile, int handlerLine, string registrationKind, string registrationFqn,
     string registrationFile, int registrationLine, string routeOrEvent, string authContext, string inputName, string inputType, string inputKind,
     string materializationPhase, string coverageStatus, string coverageNote
where nettyRow(framework, protocol, handlerFqn, handlerFile, handlerLine, registrationKind, registrationFqn, registrationFile, registrationLine,
               routeOrEvent, authContext, inputName, inputType, inputKind, materializationPhase, coverageStatus, coverageNote)
select framework, protocol, handlerFqn as handler_fqn, handlerFile as handler_file, handlerLine as handler_start_line,
       registrationKind as registration_kind, registrationFqn as registration_fqn, registrationFile as registration_file,
       registrationLine as registration_start_line, routeOrEvent as route_or_event, authContext as auth_context,
       inputName as attacker_input_name, inputType as attacker_input_type, inputKind as attacker_input_kind,
       materializationPhase as materialization_phase, coverageStatus as coverage_status, coverageNote as coverage_note
