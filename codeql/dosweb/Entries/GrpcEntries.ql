/**
 * @name gRPC registered entries
 * @description Extracts generated RPC overrides only when identity, bounded registration and attacker-input handling are proven.
 * @kind table
 * @id dosweb/grpc-entries
 */

import java

predicate isBindableServiceType(Type type) {
  type.(RefType).getASupertype*().hasQualifiedName(["io.grpc"], "BindableService")
}

predicate isStreamObserverType(Type type) {
  type.(RefType).getASupertype*().hasQualifiedName(["io.grpc.stub"], "StreamObserver") or
  type.(RefType).getASourceSupertype*().hasQualifiedName(["io.grpc.stub"], "StreamObserver") or
  type.(ParameterizedType).getGenericType().(RefType).getASupertype*().hasQualifiedName(["io.grpc.stub"], "StreamObserver")
}

// Generic gRPC declarations render qualified names with type markers (for
// example ServerBuilder<>). Match the exact package and simple declaration name
// instead of arbitrary same-named methods or a rendered generic string.
predicate isGrpcBuilderDeclaration(RefType type) {
  type.getPackage().getName() = "io.grpc" and
  (
    type.getName() = "ServerBuilder" or type.getName().matches("ServerBuilder<%>") or
    type.getName() = "ForwardingServerBuilder" or type.getName().matches("ForwardingServerBuilder<%>")
  )
}

predicate isNativeServerRegistration(MethodCall call) {
  (call.getMethod().getName() = "addService" or call.getMethod().getName() = "addHandler") and
  exists(RefType declaring |
    declaring = call.getMethod().getDeclaringType() and
    isGrpcBuilderDeclaration(declaring)
  )
}

predicate hasSingleBindableParameter(Method method) {
  method.fromSource() and isBindableServiceType(method.getParameter(0).getType()) and
  not exists(Parameter other | other = method.getAParameter() and other != method.getParameter(0))
}

predicate parameterForwarded(Method method, MethodCall call) {
  call.getEnclosingCallable() = method and call.getNumArgument() > 0 and
  call.getArgument(0).(VarAccess).getVariable() = method.getParameter(0)
}

predicate uniqueConcreteTarget(Method declared, Method concrete) {
  // The selected target must be inspectable source, but any other concrete
  // dispatch target (including a dependency implementation) makes it ambiguous.
  concrete.fromSource() and not concrete.isAbstract() and
  (concrete = declared or concrete.overrides(declared)) and
  not exists(Method other |
    other != concrete and not other.isAbstract() and
    (other = declared or other.overrides(declared))
  )
}

// A forwarding method may retain its sole BindableService parameter on exactly
// one outbound call. This intentionally rejects every mixed direct/wrapper
// combination, regardless of the downstream registration depth.
predicate uniqueParameterForward(Method method, MethodCall call) {
  parameterForwarded(method, call) and
  not exists(MethodCall other | other != call and parameterForwarded(method, other))
}

predicate concreteDepth0(Method concrete) {
  hasSingleBindableParameter(concrete) and
  exists(MethodCall sink | uniqueParameterForward(concrete, sink) and isNativeServerRegistration(sink))
}

predicate methodDepth0(Method declared) {
  exists(Method concrete | uniqueConcreteTarget(declared, concrete) and concreteDepth0(concrete))
}

predicate concreteDepth1(Method concrete) {
  hasSingleBindableParameter(concrete) and
  exists(MethodCall edge | uniqueParameterForward(concrete, edge) and methodDepth0(edge.getMethod()))
}

predicate methodDepth1(Method declared) {
  exists(Method concrete | uniqueConcreteTarget(declared, concrete) and concreteDepth1(concrete))
}

predicate concreteDepth2(Method concrete) {
  hasSingleBindableParameter(concrete) and
  exists(MethodCall edge | uniqueParameterForward(concrete, edge) and methodDepth1(edge.getMethod()))
}

predicate methodDepth2(Method declared) {
  exists(Method concrete | uniqueConcreteTarget(declared, concrete) and concreteDepth2(concrete))
}

// Non-recursive union of already-proven bounded registration paths. The depth
// predicates themselves use uniqueParameterForward, so mixing any relevant
// native/wrapper path cannot become a second valid outbound edge.
predicate isRegistrationRelevantForward(MethodCall call) {
  isNativeServerRegistration(call) or methodDepth0(call.getMethod()) or
  methodDepth1(call.getMethod()) or methodDepth2(call.getMethod())
}

predicate isBoundRegistration(MethodCall call) { isRegistrationRelevantForward(call) }

predicate registrationBinds(MethodCall call, RefType service) {
  isBoundRegistration(call) and call.getNumArgument() > 0 and
  (
    call.getArgument(0).(ClassInstanceExpr).getConstructedType() = service or
    exists(Variable variable |
      call.getArgument(0).(VarAccess).getVariable() = variable and
      variable.getInitializer().(ClassInstanceExpr).getConstructedType() = service
    )
  )
}

predicate uniqueRegistration(MethodCall registration, RefType service) {
  registrationBinds(registration, service) and
  not exists(MethodCall other | other != registration and registrationBinds(other, service))
}

// Exact shared Entry contract: "framework", "protocol", "handler_fqn", "handler_file",
// "handler_start_line", "registration_kind", "registration_fqn", "registration_file",
// "registration_start_line", "route_or_event", "auth_context", "attacker_input_name",
// "attacker_input_type", "attacker_input_kind", "materialization_phase", "coverage_status",
// "coverage_note".
// Keep override proof independent from service identity so that missing generated
// metadata remains a concrete partial gap rather than silently disappearing.
// Modern AsyncService is a common generated shape, but its conventional name is
// forgeable. Require the generator's type annotation in addition to the outer
// *Grpc naming convention; legacy *ImplBase compatibility stays unchanged.
predicate isGeneratedAsyncService(RefType generatedBase) {
  generatedBase.getName() = "AsyncService" and generatedBase instanceof NestedType and
  exists(RefType outer, Annotation annotation |
    outer = generatedBase.(NestedType).getEnclosingType() and
    annotation = outer.getAnAnnotation() and
    annotation.getType().hasQualifiedName(["io.grpc.stub.annotations"], "GrpcGenerated")
  )
}

predicate generatedRpcOverride(Method implementation, Method generatedMethod, RefType generatedBase) {
  implementation.fromSource() and implementation.overrides(generatedMethod) and
  generatedBase = generatedMethod.getDeclaringType() and
  generatedBase instanceof NestedType and
  generatedBase.(NestedType).getEnclosingType().getName().matches("%Grpc") and
  (generatedBase.getName().matches("%ImplBase") or isGeneratedAsyncService(generatedBase))
}

predicate generatedServiceIdentity(Method implementation, Method generatedMethod, string serviceName) {
  exists(RefType base, RefType outer, Field field |
    generatedRpcOverride(implementation, generatedMethod, base) and
    outer = base.(NestedType).getEnclosingType() and field = outer.getAField() and
    field.getName() = "SERVICE_NAME" and field.getInitializer() instanceof CompileTimeConstantExpr and
    serviceName = field.getInitializer().(CompileTimeConstantExpr).getStringValue() and serviceName != "" and
    not exists(Field other | other != field and other = outer.getAField() and other.getName() = "SERVICE_NAME")
  )
}

string grpcRoute(Method implementation) {
  exists(Method generatedMethod, string serviceName |
    generatedServiceIdentity(implementation, generatedMethod, serviceName) and
    result = "/" + serviceName + "/" + generatedMethod.getName()
  )
}

string partialGrpcRoute(Method implementation) {
  generatedServiceIdentity(implementation, _, _) and result = grpcRoute(implementation)
  or
  not exists(Method generatedMethod, string serviceName | generatedServiceIdentity(implementation, generatedMethod, serviceName)) and
  result = implementation.getDeclaringType().getQualifiedName() + "." + implementation.getName()
}

predicate hasUnaryOrServerStreamingInput(Method method, Parameter request) {
  exists(Parameter observer |
    observer = method.getAParameter() and isStreamObserverType(observer.getType()) and
    request = method.getAParameter() and request != observer and not isStreamObserverType(request.getType())
  )
}

predicate hasClientOrBidiStreamingSignature(Method method) {
  isStreamObserverType(method.getReturnType()) and
  exists(Parameter observer | observer = method.getAParameter() and isStreamObserverType(observer.getType()))
}

predicate conditionalLeaf(Expr root, Expr leaf) {
  root = leaf and not root instanceof ConditionalExpr
  or exists(ConditionalExpr conditional |
    conditional = root and (conditionalLeaf(conditional.getThen(), leaf) or conditionalLeaf(conditional.getElse(), leaf))
  )
}

predicate returnedLeaf(Method method, Expr leaf) {
  exists(ReturnStmt returned | returned.getEnclosingCallable() = method and conditionalLeaf(returned.getExpr(), leaf))
}

predicate sourceObserverLeaf(Method method, RefType observerType, ClassInstanceExpr construction) {
  returnedLeaf(method, construction) and observerType = construction.getConstructedType() and
  observerType.fromSource() and isStreamObserverType(observerType)
}

predicate sourceObserverOnNext(RefType observerType, Method onNext, Parameter request) {
  onNext.fromSource() and onNext.getDeclaringType() = observerType and onNext.getName() = "onNext" and
  request = onNext.getParameter(0) and not exists(Parameter other | other = onNext.getAParameter() and other != onNext.getParameter(0)) and
  // The observer type is proven to implement StreamObserver; its single source
  // onNext(Request) declaration is therefore the interface implementation.
  not exists(Method other |
    other != onNext and other.fromSource() and other.getDeclaringType() = observerType and other.getName() = "onNext" and
    not exists(Parameter extra | extra = other.getAParameter() and extra != other.getParameter(0))
  )
}

predicate allReturnedLeavesSupported(Method method) {
  exists(Expr leaf | returnedLeaf(method, leaf)) and
  not exists(Expr leaf |
    returnedLeaf(method, leaf) and
    not exists(RefType observerType, ClassInstanceExpr construction, Method onNext, Parameter request |
      leaf = construction and sourceObserverLeaf(method, observerType, construction) and
      sourceObserverOnNext(observerType, onNext, request)
    )
  )
}

predicate streamingComplete(Method method, RefType service, MethodCall registration) {
  hasClientOrBidiStreamingSignature(method) and generatedServiceIdentity(method, _, _) and
  uniqueRegistration(registration, service) and allReturnedLeavesSupported(method)
}

predicate grpcRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method method, Method generatedMethod, Parameter request, MethodCall registration, RefType service |
    method.getDeclaringType() = service and generatedServiceIdentity(method, generatedMethod, _) and
    hasUnaryOrServerStreamingInput(method, request) and uniqueRegistration(registration, service) and
    framework = "grpc" and protocol = "grpc" and handlerFqn = service.getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and handlerLine = method.getLocation().getStartLine() and
    registrationKind = "static_registration" and registrationFqn = registration.getMethod().getDeclaringType().getQualifiedName() + "." + registration.getMethod().getName() and
    registrationFile = registration.getLocation().getFile().getRelativePath() and registrationLine = registration.getLocation().getStartLine() and
    routeOrEvent = grpcRoute(method) and authContext = "unknown" and inputName = request.getName() and
    inputType = request.getType().toString() and inputKind = "request_body" and materializationPhase = "in_handler" and
    coverageStatus = "complete" and coverageNote = "grpc_generated_rpc_static_registration"
  )
  or exists(Method method, Method generatedMethod, RefType service, MethodCall registration, RefType observerType, ClassInstanceExpr construction, Method onNext, Parameter request |
    method.getDeclaringType() = service and generatedServiceIdentity(method, generatedMethod, _) and
    streamingComplete(method, service, registration) and sourceObserverLeaf(method, observerType, construction) and
    sourceObserverOnNext(observerType, onNext, request) and
    framework = "grpc" and protocol = "grpc" and handlerFqn = observerType.getQualifiedName() + "." + onNext.getName() and
    handlerFile = onNext.getLocation().getFile().getRelativePath() and handlerLine = onNext.getLocation().getStartLine() and
    registrationKind = "static_registration" and registrationFqn = registration.getMethod().getDeclaringType().getQualifiedName() + "." + registration.getMethod().getName() and
    registrationFile = registration.getLocation().getFile().getRelativePath() and registrationLine = registration.getLocation().getStartLine() and
    routeOrEvent = grpcRoute(method) and authContext = "unknown" and inputName = request.getName() and inputType = request.getType().toString() and
    inputKind = "stream" and materializationPhase = "streaming" and coverageStatus = "complete" and coverageNote = "grpc_generated_client_or_bidi_streaming_registration"
  )
  or exists(Method method, Method generatedMethod, RefType generatedBase, RefType service |
    method.getDeclaringType() = service and generatedRpcOverride(method, generatedMethod, generatedBase) and
    hasUnaryOrServerStreamingInput(method, _) and
    not exists(MethodCall registration | uniqueRegistration(registration, service) and generatedServiceIdentity(method, _, _)) and
    framework = "grpc" and protocol = "grpc" and handlerFqn = service.getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and handlerLine = method.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and registrationFile = handlerFile and registrationLine = handlerLine and
    routeOrEvent = partialGrpcRoute(method) and authContext = "unknown" and inputName = "unknown" and inputType = "unknown" and
    inputKind = "unknown" and materializationPhase = "unknown" and coverageStatus = "partial" and coverageNote = "grpc_generated_rpc_registration_or_identity_unproven"
  )
  or exists(Method method, Method generatedMethod, RefType generatedBase, RefType service |
    method.getDeclaringType() = service and generatedRpcOverride(method, generatedMethod, generatedBase) and hasClientOrBidiStreamingSignature(method) and
    not exists(MethodCall registration | streamingComplete(method, service, registration)) and
    framework = "grpc" and protocol = "grpc" and handlerFqn = service.getQualifiedName() + "." + method.getName() and
    handlerFile = method.getLocation().getFile().getRelativePath() and handlerLine = method.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and registrationFile = handlerFile and registrationLine = handlerLine and
    routeOrEvent = partialGrpcRoute(method) and authContext = "unknown" and inputName = "unknown" and inputType = "unknown" and
    inputKind = "unknown" and materializationPhase = "unknown" and coverageStatus = "partial" and coverageNote = "grpc_generated_streaming_registration_identity_or_observer_unproven"
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
