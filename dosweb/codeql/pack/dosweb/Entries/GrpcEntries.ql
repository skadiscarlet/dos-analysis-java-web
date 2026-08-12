/**
 * @name gRPC registered entries
 * @description Extracts BindableService handlers only when a service is statically bound to a server registration call.
 * @kind table
 * @id dosweb/grpc-entries
 */

import java

// Exact shared Entry contract: 17 columns.
// "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
// "registration_kind", "registration_fqn", "registration_file", "registration_start_line",
// "route_or_event", "auth_context", "attacker_input_name", "attacker_input_type",
// "attacker_input_kind", "materialization_phase", "coverage_status", "coverage_note"

predicate isBindableType(Type type) {
  type.(RefType).hasQualifiedName(["io.grpc"], "BindableService")
  or type.(RefType).getASourceSupertype*().hasQualifiedName(["io.grpc"], "BindableService")
}

predicate isStreamObserverType(Type type) {
  type.(RefType).hasQualifiedName(["io.grpc.stub"], "StreamObserver")
  or type.(ParameterizedType).getGenericType().(RefType).hasQualifiedName(["io.grpc.stub"], "StreamObserver")
  or type.(RefType).getASourceSupertype*().hasQualifiedName(["io.grpc.stub"], "StreamObserver")
}

predicate isServerRegistration(MethodCall call) {
  (call.getMethod().getName() = "addService" or call.getMethod().getName() = "addHandler") and
  (call.getMethod().getDeclaringType().hasQualifiedName(["io.grpc"], "ServerBuilder") or
   call.getMethod().getDeclaringType().hasQualifiedName(["io.grpc"], "Server"))
}

predicate registeredType(MethodCall call, Type service) {
  isServerRegistration(call) and exists(Expr argument |
    argument = call.getArgument(0) and
    ((argument instanceof TypeLiteral and argument.(TypeLiteral).getReferencedType() = service) or
     (argument instanceof ClassInstanceExpr and argument.(ClassInstanceExpr).getConstructedType() = service) or
     (argument instanceof VarAccess and argument.(VarAccess).getVariable().getInitializer() instanceof ClassInstanceExpr and
      argument.(VarAccess).getVariable().getInitializer().(ClassInstanceExpr).getConstructedType() = service))
  )
}

predicate hasRequestAndObserver(Method method, Parameter request, Parameter observer) {
  observer = method.getAParameter() and isStreamObserverType(observer.getType()) and
  request = method.getAParameter() and request != observer and not isStreamObserverType(request.getType())
}

predicate grpcRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method method, Parameter request, Parameter observer, MethodCall registration, Type service |
    isBindableType(service) and method.getDeclaringType() = service and
    hasRequestAndObserver(method, request, observer) and registeredType(registration, service) and
    framework = "grpc" and protocol = "grpc" and
    handlerFqn = service.(RefType).getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and handlerLine = method.getLocation().getStartLine() and
    registrationKind = "static_registration" and registrationFqn = registration.getMethod().getDeclaringType().getQualifiedName() + "." + registration.getMethod().getName() and
    registrationFile = registration.getLocation().getFile().getRelativePath() and registrationLine = registration.getLocation().getStartLine() and
    routeOrEvent = "/" + service.(RefType).getQualifiedName() + "/" + method.getName() and authContext = "unknown" and
    inputName = request.getName() and inputType = request.getType().toString() and inputKind = "request_body" and
    materializationPhase = "in_handler" and
    coverageStatus = "complete" and coverageNote = "grpc_bindable_service_registration"
  )
  or exists(Method method, Parameter request, Parameter observer |
    isBindableType(method.getDeclaringType()) and hasRequestAndObserver(method, request, observer) and
    not exists(MethodCall registration | registeredType(registration, method.getDeclaringType())) and
    framework = "grpc" and protocol = "grpc" and handlerFqn = method.getDeclaringType().getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and handlerLine = method.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and registrationFile = method.getLocation().getFile().getRelativePath() and
    registrationLine = method.getLocation().getStartLine() and routeOrEvent = "/" + method.getDeclaringType().getQualifiedName() + "/" + method.getName() and
    authContext = "unknown" and inputName = request.getName() and inputType = request.getType().toString() and inputKind = "request_body" and
    materializationPhase = "unknown" and coverageStatus = "partial" and coverageNote = "unregistered_bindable_service"
  )
}

from string framework, string protocol, string handlerFqn, string handlerFile, int handlerLine, string registrationKind, string registrationFqn,
     string registrationFile, int registrationLine, string routeOrEvent, string authContext, string inputName, string inputType, string inputKind,
     string materializationPhase, string coverageStatus, string coverageNote
where grpcRow(framework, protocol, handlerFqn, handlerFile, handlerLine, registrationKind, registrationFqn, registrationFile, registrationLine,
              routeOrEvent, authContext, inputName, inputType, inputKind, materializationPhase, coverageStatus, coverageNote)
select framework, protocol, handlerFqn as handler_fqn, handlerFile as handler_file, handlerLine as handler_start_line,
       registrationKind as registration_kind, registrationFqn as registration_fqn, registrationFile as registration_file,
       registrationLine as registration_start_line, routeOrEvent as route_or_event, authContext as auth_context,
       inputName as attacker_input_name, inputType as attacker_input_type, inputKind as attacker_input_kind,
       materializationPhase as materialization_phase, coverageStatus as coverage_status, coverageNote as coverage_note
