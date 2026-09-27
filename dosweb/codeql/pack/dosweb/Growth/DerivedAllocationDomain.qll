/** Generic derived extent -> dimensioned matrix/raster/image materialization domain. */

import java
import semmle.code.java.dataflow.DataFlow

predicate derivedContainerType(Type type) {
  type instanceof Array
  or
  exists(RefType reference |
    reference = type and
    (
      reference.getASupertype*().getName().matches("%Collection%")
      or reference.getASupertype*().getName().matches("%List%")
      or reference.getASupertype*().getName().matches("%Set%")
      or reference.getASupertype*().getName().matches("%Map%")
      or reference.getASupertype*().getName().matches("%Buffer%")
      or reference.getASupertype*().getName().matches("%Sequence%")
    )
  )
}

predicate derivedContainerProducer(MethodCall producer) {
  derivedContainerType(producer.getType())
}

/** An extent read from a freshly produced array/container. */
predicate derivedExtent(Expr extent, MethodCall producer) {
  derivedContainerProducer(producer) and
  (
    exists(FieldRead length |
      extent = length and length.getField() instanceof ArrayLengthField and
      (
        length.getQualifier() = producer
        or DataFlow::localFlow(
             DataFlow::exprNode(producer), DataFlow::exprNode(length.getQualifier())
           )
      )
    )
    or
    exists(MethodCall measure |
      extent = measure and measure.getMethod().getName() = ["size", "length"] and
      measure.getNumArgument() = 0 and
      (
        measure.getQualifier() = producer
        or DataFlow::localFlow(
             DataFlow::exprNode(producer), DataFlow::exprNode(measure.getQualifier())
           )
      )
    )
  )
}

predicate rasterMaterializationType(Type type) {
  exists(RefType reference |
    reference = type and
    (
      reference.getName().matches("%Matrix%")
      or reference.getName().matches("%Raster%")
      or reference.getName().matches("%Image%")
      or reference.getName().matches("%Bitmap%")
    )
  )
}

predicate derivedCallArgument(Expr call, int index, Expr argument) {
  exists(MethodCall methodCall |
    call = methodCall and argument = methodCall.getArgument(index)
  )
  or
  exists(ClassInstanceExpr constructorCall |
    call = constructorCall and argument = constructorCall.getArgument(index)
  )
}

predicate dimensionedMaterializer(Expr materializer) {
  (
    materializer instanceof MethodCall
    or materializer instanceof ClassInstanceExpr
  ) and
  exists(int firstIndex, int secondIndex, Expr first, Expr second |
    firstIndex != secondIndex and
    derivedCallArgument(materializer, firstIndex, first) and
    derivedCallArgument(materializer, secondIndex, second) and
    first.getType() instanceof IntegralType and second.getType() instanceof IntegralType
  ) and
  (
    rasterMaterializationType(materializer.getType())
    or
    exists(MethodCall consumer, int inputIndex |
      materializer.getType() instanceof RefType and
      rasterMaterializationType(consumer.getType()) and
      DataFlow::localFlow(
        DataFlow::exprNode(materializer),
        DataFlow::exprNode(consumer.getArgument(inputIndex))
      )
    )
  )
}

predicate extentWritesDimensionVariable(
  Expr extent, Variable dimensionVariable, Expr derivation
) {
  exists(LocalVariableDecl local |
    dimensionVariable = local and derivation = local.getInitializer() and
    extent.getParent*() = derivation
  )
  or
  exists(AssignExpr assignment, VarAccess destination |
    derivation = assignment and destination = assignment.getDest() and
    dimensionVariable = destination.getVariable() and
    extent.getParent*() = assignment.getSource()
  )
}

predicate cfgStrictlyBefore(Expr before, Expr after) {
  before.getEnclosingCallable() = after.getEnclosingCallable() and
  before.getBasicBlock().dominates(after.getBasicBlock()) and
  before.getControlFlowNode().getASuccessor*() = after.getControlFlowNode() and
  not after.getControlFlowNode().getASuccessor*() = before.getControlFlowNode()
}

predicate cfgCanReachAfter(Expr before, Expr after) {
  before.getEnclosingCallable() = after.getEnclosingCallable() and
  before.getControlFlowNode().getASuccessor*() = after.getControlFlowNode() and
  not after.getControlFlowNode().getASuccessor*() = before.getControlFlowNode()
}

/**
 * A produced array/container extent is transformed through a local numeric
 * variable and consumed as one of at least two integral materializer dimensions.
 */
predicate derivedDimensionMaterialization(
  Expr materializer, Expr dimension, Expr extent, MethodCall producer
) {
  derivedExtent(extent, producer) and dimensionedMaterializer(materializer) and
  exists(Variable dimensionVariable, Expr derivation, int dimensionIndex |
    extentWritesDimensionVariable(extent, dimensionVariable, derivation) and
    derivedCallArgument(materializer, dimensionIndex, dimension) and
    dimension instanceof VarAccess and
    dimension.(VarAccess).getVariable() = dimensionVariable and
    dimension.getType() instanceof IntegralType and
    cfgCanReachAfter(extent, materializer)
  )
}

predicate literalUpperCap(MethodCall cap, Variable variable) {
  cap.getMethod().getName() = ["min", "clamp", "coerceAtMost"] and
  exists(int valueIndex, int boundIndex, VarAccess value, CompileTimeConstantExpr bound |
    valueIndex != boundIndex and value = cap.getArgument(valueIndex) and
    value.getVariable() = variable and bound = cap.getArgument(boundIndex)
  )
}

/** The cap must overwrite the derived variable after derivation and dominate use. */
predicate postDerivationCap(
  Expr materializer, Expr dimension, Expr extent, MethodCall cap
) {
  exists(Variable dimensionVariable, AssignExpr capAssignment, VarAccess destination |
    dimension instanceof VarAccess and
    dimension.(VarAccess).getVariable() = dimensionVariable and
    destination = capAssignment.getDest() and destination.getVariable() = dimensionVariable and
    cap.getParent*() = capAssignment.getSource() and
    literalUpperCap(cap, dimensionVariable) and
    cfgStrictlyBefore(extent, cap) and cfgStrictlyBefore(cap, materializer)
  )
}

predicate derivedMaterializerIdentity(
  Expr materializer, string operation, string receiver
) {
  exists(MethodCall call |
    materializer = call and
    operation = call.getMethod().getDeclaringType().getQualifiedName() + "." +
      call.getMethod().getName() and
    receiver = call.getMethod().getDeclaringType().getQualifiedName()
  )
  or
  exists(ClassInstanceExpr creation |
    materializer = creation and
    operation = creation.getConstructedType().getQualifiedName() + ".<init>" and
    receiver = creation.getConstructedType().getQualifiedName()
  )
}
