/**
 * @name MQTT registered entries
 * @description Extracts statically recoverable MQTT subscribe/listener callback registrations.
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
