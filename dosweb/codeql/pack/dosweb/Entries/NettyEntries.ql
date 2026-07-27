/**
 * @name Netty registered entries
 * @description Extracts channelRead callbacks with statically recoverable pipeline registration.
 * @kind table
 * @id dosweb/netty-entries
 */

import java

// Exact Task 3 contract:
// "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
// "registration_kind", "registration_fqn", "registration_file",
// "registration_start_line", "route_or_event", "auth_context",
// "attacker_input_name", "attacker_input_type", "attacker_input_kind",
// "materialization_phase", "coverage_status", "coverage_note"

predicate isNettyType(RefType type, string simpleName) {
  type.getASourceSupertype*().hasQualifiedName("fixture.netty", simpleName)
  or
  type.getASourceSupertype*().hasQualifiedName("io.netty.channel", simpleName)
}

predicate nettyRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method callback, Method init, MethodCall addLast, ClassInstanceExpr handler, Parameter message |
    callback.getName() = "channelRead" and
    isNettyType(callback.getDeclaringType(), "ChannelInboundHandlerAdapter") and
    message = callback.getParameter(1) and
    init.getName() = "initChannel" and
    isNettyType(init.getDeclaringType(), "ChannelInitializer") and
    addLast.getEnclosingCallable() = init and
    addLast.getMethod().getName() = "addLast" and
    isNettyType(addLast.getMethod().getDeclaringType(), "ChannelPipeline") and
    handler = addLast.getArgument(0) and
    handler.getConstructedType().getSourceDeclaration() = callback.getDeclaringType() and
    framework = "netty" and protocol = "tcp" and
    handlerFqn = callback.getDeclaringType().getQualifiedName() + "." + callback.getName() and
    handlerFile = callback.getLocation().getFile().getRelativePath() and
    handlerLine = callback.getLocation().getStartLine() and
    registrationKind = "pipeline_registration" and
    registrationFqn = init.getDeclaringType().getQualifiedName() + "." + init.getName() and
    registrationFile = addLast.getLocation().getFile().getRelativePath() and
    registrationLine = addLast.getLocation().getStartLine() and
    routeOrEvent = "channelRead" and authContext = "unknown" and
    inputName = message.getName() and inputType = message.getType().toString() and
    inputKind = "message_payload" and materializationPhase = "streaming" and
    coverageStatus = "complete" and coverageNote = "netty_pipeline_registration"
  )
  or
  exists(MethodCall addLast, Method enclosing |
    addLast.getMethod().getName() = "addLast" and
    isNettyType(addLast.getMethod().getDeclaringType(), "ChannelPipeline") and
    enclosing = addLast.getEnclosingCallable() and
    not addLast.getArgument(0) instanceof ClassInstanceExpr and
    framework = "netty" and protocol = "tcp" and
    handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and
    handlerFile = enclosing.getLocation().getFile().getRelativePath() and
    handlerLine = enclosing.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = addLast.getLocation().getFile().getRelativePath() and
    registrationLine = addLast.getLocation().getStartLine() and
    routeOrEvent = "channelRead" and authContext = "unknown" and
    inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and
    materializationPhase = "unknown" and coverageStatus = "partial" and
    coverageNote = "unresolved_pipeline_handler"
  )
  or
  exists(MethodCall call, Method enclosing |
    call.getMethod().hasQualifiedName("java.lang", "Class", "forName") and
    enclosing = call.getEnclosingCallable() and
    isNettyType(enclosing.getDeclaringType(), "ChannelInitializer") and
    framework = "netty" and protocol = "tcp" and
    handlerFqn = enclosing.getDeclaringType().getQualifiedName() + "." + enclosing.getName() and
    handlerFile = enclosing.getLocation().getFile().getRelativePath() and
    handlerLine = enclosing.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = call.getLocation().getFile().getRelativePath() and
    registrationLine = call.getLocation().getStartLine() and
    routeOrEvent = "channelRead" and authContext = "unknown" and
    inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and
    materializationPhase = "unknown" and coverageStatus = "partial" and
    coverageNote = "reflection_pipeline_registration"
  )
}

from
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
where
  nettyRow(
    framework, protocol, handlerFqn, handlerFile, handlerLine, registrationKind,
    registrationFqn, registrationFile, registrationLine, routeOrEvent, authContext,
    inputName, inputType, inputKind, materializationPhase, coverageStatus, coverageNote
  )
select
  framework, protocol, handlerFqn as handler_fqn,
  handlerFile as handler_file, handlerLine as handler_start_line,
  registrationKind as registration_kind, registrationFqn as registration_fqn,
  registrationFile as registration_file, registrationLine as registration_start_line,
  routeOrEvent as route_or_event, authContext as auth_context,
  inputName as attacker_input_name, inputType as attacker_input_type,
  inputKind as attacker_input_kind, materializationPhase as materialization_phase,
  coverageStatus as coverage_status, coverageNote as coverage_note
