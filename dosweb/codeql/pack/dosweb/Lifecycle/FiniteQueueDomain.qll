/** Shared exact finite-queue/reject domain for BoundCandidates and LifecycleCoverage. */
import java
import semmle.code.java.controlflow.Guards

predicate terminalReject(IfStmt branch) {
  exists(ReturnStmt terminal | terminal.getParent*() = branch.getThen()) or
  exists(ThrowStmt terminal | terminal.getParent*() = branch.getThen())
}

/** Only `if (!queue.offer(x)) { return|throw; }` is a modeled hard reject.
 * No string/pretty-print matching is used. */
predicate checkedFiniteQueueOffer(MethodCall call) {
  call.getMethod().getName() = "offer" and
  exists(IfStmt branch, LogNotExpr negation |
    branch.getCondition() = negation and
    call.getParent*() = negation and
    terminalReject(branch)
  )
}

Field queueReceiverField(MethodCall call) {
  exists(FieldAccess receiver | receiver = call.getQualifier() and result = receiver.getField())
  or
  exists(VarAccess receiver | receiver = call.getQualifier() and result = receiver.getVariable().(Field))
}

predicate finiteFieldQueueType(Field field) {
  field.getType().(RefType).hasQualifiedName("java.util.concurrent", "ArrayBlockingQueue") or
  field.getType().(RefType).hasQualifiedName("java.util.concurrent", "LinkedBlockingQueue") or
  field.getType().(RefType).getASourceSupertype*().hasQualifiedName("java.util.concurrent", "ArrayBlockingQueue") or
  field.getType().(RefType).getASourceSupertype*().hasQualifiedName("java.util.concurrent", "LinkedBlockingQueue") or
  field.getType().(ParameterizedType).getGenericType().hasQualifiedName("java.util.concurrent", "ArrayBlockingQueue") or
  field.getType().(ParameterizedType).getGenericType().hasQualifiedName("java.util.concurrent", "LinkedBlockingQueue")
}

string finiteFieldQueueCapacity(Field field) {
  finiteFieldQueueType(field) and
  exists(ClassInstanceExpr creation, CompileTimeConstantExpr capacity |
    creation = field.getInitializer() and
    capacity = creation.getArgument(0) and
    result = capacity.toString()
  )
}

predicate modeledFiniteQueueOffer(MethodCall call) {
  exists(Field receiver, string capacity |
    receiver = queueReceiverField(call) and
    capacity = finiteFieldQueueCapacity(receiver) and
    checkedFiniteQueueOffer(call)
  )
}
