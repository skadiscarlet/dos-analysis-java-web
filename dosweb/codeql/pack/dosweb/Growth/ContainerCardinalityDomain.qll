/** Conservative same-map cardinality proof for persistent Map.put writes. */

import java

predicate mapPut(MethodCall call) {
  call.getMethod().getName() = "put" and call.getNumArgument() = 2 and
  call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName(
    "java.util", "Map"
  )
}

predicate exactFieldReceiver(MethodCall call, Field field) {
  call.getQualifier().(FieldAccess).getField() = field
}

predicate emptyStableMapField(Field field) {
  field.isFinal() and
  exists(ClassInstanceExpr allocation |
    field.getInitializer() = allocation and allocation.getNumArgument() = 0 and
    allocation.getConstructedType().getASupertype*().getSourceDeclaration()
      .hasQualifiedName("java.util", "Map")
  )
}

predicate initializerForField(Field field, InitializerMethod initializer) {
  initializer.getDeclaringType() = field.getDeclaringType()
}

predicate denseSeedPut(Field field, MethodCall seed, IntegerLiteral key) {
  mapPut(seed) and exactFieldReceiver(seed, field) and
  initializerForField(field, seed.getEnclosingCallable().(InitializerMethod)) and
  key = seed.getArgument(0)
}

predicate initializerReferencesFieldInCall(
  Field field, MethodCall call
) {
  initializerForField(field, call.getEnclosingCallable().(InitializerMethod)) and
  exists(FieldAccess access |
    access.getField() = field and access.getParent*() = call
  )
}

/** Every initializer-time call that mentions the field must be one exact
 * positive integer-key put, and those seed keys must be the dense set 1..N. */
predicate denselySeededMapField(Field field) {
  emptyStableMapField(field) and
  exists(int seedCount |
    seedCount = count(MethodCall seed, IntegerLiteral key |
      denseSeedPut(field, seed, key)
    ) and
    seedCount > 0 and
    forall(MethodCall call |
      initializerReferencesFieldInCall(field, call)
      |
      exists(IntegerLiteral key | denseSeedPut(field, call, key))
    ) and
    forall(MethodCall seed, IntegerLiteral key |
      denseSeedPut(field, seed, key)
      |
      key.getIntValue() > 0 and key.getIntValue() <= seedCount
    ) and
    forall(int expected |
      expected in [1 .. seedCount]
      |
      exists(MethodCall seed, IntegerLiteral key |
        denseSeedPut(field, seed, key) and key.getIntValue() = expected
      )
    )
  )
}

predicate directOrSingleInitializerKey(
  MethodCall put, Expr key, Expr expression
) {
  key = expression
  or exists(LocalVariableDecl local, VarAccess use |
    key = use and use.getVariable() = local and
    local.getCallable() = put.getEnclosingCallable() and
    expression = local.getInitializer() and
    not exists(Assignment write |
      write.getDest().(VarAccess).getVariable() = local
    ) and
    not exists(UnaryAssignExpr write |
      write.getOperand().(VarAccess).getVariable() = local
    )
  )
}

predicate sameMapSizePlusPositiveConstant(
  Field field, Expr expression
) {
  exists(AddExpr addition, MethodCall size, IntegerLiteral offset |
    expression = addition and
    addition.getLeftOperand() = size and addition.getRightOperand() = offset and
    size.getMethod().getName() = "size" and size.getNumArgument() = 0 and
    exactFieldReceiver(size, field) and offset.getIntValue() > 0
  )
}

predicate mapMutation(MethodCall call) {
  call.getMethod().getName() = [
    "put", "putAll", "putIfAbsent", "remove", "clear", "replace",
    "replaceAll", "compute", "computeIfAbsent", "computeIfPresent", "merge"
  ] and
  call.getMethod().getDeclaringType().getASourceSupertype*().hasQualifiedName(
    "java.util", "Map"
  )
}

predicate noOtherSameReceiverMutation(MethodCall selected, Field field) {
  not exists(MethodCall other |
    other != selected and
    other.getEnclosingCallable() = selected.getEnclosingCallable() and
    mapMutation(other) and exactFieldReceiver(other, field)
  )
}

/** A dense 1..N Map seeded from an empty final field remains fresh under a
 * selected handler's sole mutation when its key is size()+positiveConstant. */
predicate provenServerDerivedFreshMapKey(MethodCall put, Expr key) {
  exists(Field field, Expr expression |
    mapPut(put) and key = put.getArgument(0) and
    exactFieldReceiver(put, field) and denselySeededMapField(field) and
    directOrSingleInitializerKey(put, key, expression) and
    sameMapSizePlusPositiveConstant(field, expression) and
    noOtherSameReceiverMutation(put, field)
  )
}
