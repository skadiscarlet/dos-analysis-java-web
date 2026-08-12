/**
 * @name MQTT registered entries
 * @description Extracts statically recoverable MQTT client subscriptions and broker protocol registrations.
 * @kind table
 * @id dosweb/mqtt-entries
 */

import java

// Exact Task 3 contract:
// "framework", "protocol", "handler_fqn", "handler_file", "handler_start_line",
// "registration_kind", "registration_fqn", "registration_file",
// "registration_start_line", "route_or_event", "auth_context",
// "attacker_input_name", "attacker_input_type", "attacker_input_kind",
// "materialization_phase", "coverage_status", "coverage_note"

predicate isMqttType(RefType type, string simpleName) {
  type.getASourceSupertype*().hasQualifiedName("fixture.mqtt", simpleName)
  or
  type.getASourceSupertype*().hasQualifiedName("org.eclipse.paho.client.mqttv3", simpleName)
}

predicate isNettyBrokerType(RefType type, string simpleName) {
  type.getASourceSupertype*().hasQualifiedName("fixture.mqtt", simpleName)
  or
  type.getASourceSupertype*().hasQualifiedName("io.netty.channel", simpleName)
}

predicate isMqttMessageType(Type type) {
  type.(RefType).getASourceSupertype*().hasQualifiedName("fixture.mqtt", "BrokerMqttMessage")
  or
  type.(RefType).getASourceSupertype*().hasQualifiedName("io.netty.handler.codec.mqtt", "MqttMessage")
}

predicate jmqttBrokerRegistration(
  Method callback, Method register, MethodCall addLast, Parameter message
) {
  callback.getName() = "channelRead" and
  isNettyBrokerType(callback.getDeclaringType(), "ChannelDuplexHandler") and
  message = callback.getParameter(1) and
  register.getName() = "initChannel" and
  register.getDeclaringType() instanceof AnonymousClass and
  isNettyBrokerType(register.getDeclaringType(), "ChannelInitializer") and
  addLast.getEnclosingCallable() = register and
  addLast.getMethod().getName() = "addLast" and
  isNettyBrokerType(addLast.getMethod().getDeclaringType(), "ChannelPipeline") and
  addLast.getNumArgument() = 2 and
  addLast.getArgument(0) instanceof CompileTimeConstantExpr and
  addLast.getArgument(1).(ClassInstanceExpr).getConstructedType().getSourceDeclaration() =
    callback.getDeclaringType() and
  isMqttMessageType(message.getType())
}

predicate jmqttObjectCallback(Method callback, Method register, MethodCall addLast, Parameter message) {
  callback.getName() = "channelRead" and
  isNettyBrokerType(callback.getDeclaringType(), "ChannelDuplexHandler") and
  message = callback.getParameter(1) and message.getType().(RefType).hasQualifiedName("java.lang", "Object") and
  register.getName() = "initChannel" and register.getDeclaringType() instanceof AnonymousClass and
  isNettyBrokerType(register.getDeclaringType(), "ChannelInitializer") and
  addLast.getEnclosingCallable() = register and addLast.getMethod().getName() = "addLast" and
  isNettyBrokerType(addLast.getMethod().getDeclaringType(), "ChannelPipeline") and
  addLast.getNumArgument() = 2 and addLast.getArgument(0) instanceof CompileTimeConstantExpr and
  addLast.getArgument(1).(ClassInstanceExpr).getConstructedType().getSourceDeclaration() = callback.getDeclaringType() and
  exists(CastExpr cast, MethodCall processor |
    cast.getEnclosingCallable() = callback and
    cast.getExpr().(VarAccess).getVariable() = message and
    isMqttMessageType(cast.getType()) and
    processor.getEnclosingCallable() = callback and processor.getNumArgument() > 0 and
    (processor.getArgument(0) = cast or
     processor.getArgument(0).(VarAccess).getVariable().getInitializer() = cast) and
    processor.getMethod().getName() = "process"
  )
}

predicate mqttRow(
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
) {
  exists(Method callback, Method register, MethodCall subscribe, ClassInstanceExpr listener,
         CompileTimeConstantExpr topic, Parameter message |
    callback.getName() = "messageArrived" and
    isMqttType(callback.getDeclaringType(), "IMqttMessageListener") and
    message = callback.getParameter(1) and
    subscribe.getMethod().getName() = "subscribe" and
    isMqttType(subscribe.getMethod().getDeclaringType(), "MqttAsyncClient") and
    register = subscribe.getEnclosingCallable() and
    topic = subscribe.getArgument(0) and listener = subscribe.getArgument(2) and
    listener.getConstructedType().getSourceDeclaration() = callback.getDeclaringType() and
    framework = "mqtt" and protocol = "mqtt" and
    handlerFqn = callback.getDeclaringType().getQualifiedName() + "." + callback.getName() and
    handlerFile = callback.getLocation().getFile().getRelativePath() and
    handlerLine = callback.getLocation().getStartLine() and
    registrationKind = "subscription_registration" and
    registrationFqn = register.getDeclaringType().getQualifiedName() + "." + register.getName() and
    registrationFile = subscribe.getLocation().getFile().getRelativePath() and
    registrationLine = subscribe.getLocation().getStartLine() and
    routeOrEvent = topic.getStringValue() and authContext = "unknown" and
    inputName = message.getName() and inputType = message.getType().toString() and
    inputKind = "message_payload" and materializationPhase = "streaming" and
    coverageStatus = "complete" and coverageNote = "mqtt_subscription_registration"
  )
  or
  exists(Method callback, Method register, MethodCall registration, Parameter message |
    jmqttBrokerRegistration(callback, register, registration, message) and
    coverageNote = "jmqtt_anonymous_channel_initializer" and
    framework = "mqtt" and protocol = "mqtt" and
    handlerFqn = callback.getDeclaringType().getQualifiedName() + "." + callback.getName() and
    handlerFile = callback.getLocation().getFile().getRelativePath() and
    handlerLine = callback.getLocation().getStartLine() and
    registrationKind = "broker_registration" and
    registrationFqn = register.getDeclaringType().getQualifiedName() + "." + register.getName() and
    registrationFile = registration.getLocation().getFile().getRelativePath() and
    registrationLine = registration.getLocation().getStartLine() and
    routeOrEvent = "mqtt_protocol" and authContext = "unknown" and
    inputName = message.getName() and inputType = message.getType().toString() and
    inputKind = "message_payload" and materializationPhase = "streaming" and
    coverageStatus = "complete"
  )
  or
  exists(Method callback, Method register, MethodCall registration, Parameter message |
    jmqttObjectCallback(callback, register, registration, message) and
    framework = "mqtt" and protocol = "mqtt" and
    handlerFqn = callback.getDeclaringType().getQualifiedName() + "." + callback.getName() and
    handlerFile = callback.getLocation().getFile().getRelativePath() and handlerLine = callback.getLocation().getStartLine() and
    registrationKind = "broker_registration" and registrationFqn = register.getDeclaringType().getQualifiedName() + "." + register.getName() and
    registrationFile = registration.getLocation().getFile().getRelativePath() and registrationLine = registration.getLocation().getStartLine() and
    routeOrEvent = "mqtt_protocol" and authContext = "unknown" and inputName = message.getName() and
    inputType = message.getType().toString() and inputKind = "message_payload" and materializationPhase = "streaming" and
    coverageStatus = "complete" and coverageNote = "jmqtt_object_callback_mqtt_conversion"
  )
  or
  exists(Method register, MethodCall doOnConnection |
    register.getDeclaringType().hasQualifiedName(
      ["fixture.mqtt", "io.github.quickmsg.core.mqtt"], "MqttReceiver"
    ) and
    doOnConnection.getEnclosingCallable() = register and
    doOnConnection.getMethod().getName() = "doOnConnection" and
    doOnConnection.getMethod().getDeclaringType().hasQualifiedName(
      ["fixture.mqtt", "reactor.netty.tcp"], "TcpServer"
    ) and
    framework = "mqtt" and protocol = "mqtt" and
    handlerFqn = register.getDeclaringType().getQualifiedName() + "." + register.getName() and
    handlerFile = register.getLocation().getFile().getRelativePath() and
    handlerLine = register.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = doOnConnection.getLocation().getFile().getRelativePath() and
    registrationLine = doOnConnection.getLocation().getStartLine() and
    routeOrEvent = "mqtt_protocol" and authContext = "unknown" and
    inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and
    materializationPhase = "unknown" and coverageStatus = "partial" and
    coverageNote = "smqtt_protocol_dispatch_binding_unresolved"
  )
  or
  exists(MethodCall subscribe, Method register |
    subscribe.getMethod().getName() = "subscribe" and
    isMqttType(subscribe.getMethod().getDeclaringType(), "MqttAsyncClient") and
    register = subscribe.getEnclosingCallable() and
    (
      not subscribe.getArgument(0) instanceof CompileTimeConstantExpr
      or
      not subscribe.getArgument(2) instanceof ClassInstanceExpr
    ) and
    framework = "mqtt" and protocol = "mqtt" and
    handlerFqn = register.getDeclaringType().getQualifiedName() + "." + register.getName() and
    handlerFile = register.getLocation().getFile().getRelativePath() and
    handlerLine = register.getLocation().getStartLine() and
    registrationKind = "dynamic_unresolved" and registrationFqn = handlerFqn and
    registrationFile = subscribe.getLocation().getFile().getRelativePath() and
    registrationLine = subscribe.getLocation().getStartLine() and
    routeOrEvent = "dynamic_topic" and authContext = "unknown" and
    inputName = "unknown" and inputType = "unknown" and inputKind = "unknown" and
    materializationPhase = "unknown" and coverageStatus = "partial" and
    coverageNote = "dynamic_mqtt_subscription"
  )
}

from
  string framework, string protocol, string handlerFqn, string handlerFile,
  int handlerLine, string registrationKind, string registrationFqn,
  string registrationFile, int registrationLine, string routeOrEvent,
  string authContext, string inputName, string inputType, string inputKind,
  string materializationPhase, string coverageStatus, string coverageNote
where
  mqttRow(
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
