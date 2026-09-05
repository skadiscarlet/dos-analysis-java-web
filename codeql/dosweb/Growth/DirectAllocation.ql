/**
 * @name Direct allocation growth candidates
 * @description Screens explicit attacker-sized buffer and array allocation operations.
 * @kind table
 * @id dosweb/direct-allocation-growth
 */

import java
import LoopAmplification

// Exact Task 3 contract:
// "site_file", "site_start_line", "growth_kind", "operation",
// "resource_dimension", "receiver", "field_path", "demand_input_name",
// "demand_input_role", "escape_scope", "candidate_evidence",
// "coverage_status", "coverage_note"

predicate allocationCall(MethodCall call) {
  call.getMethod().getName() = ["allocate", "allocateDirect"] and
  (
    call.getMethod().getDeclaringType().hasQualifiedName("java.nio", "ByteBuffer")
  )
}

predicate sizeUsesAttackerParameter(Expr allocation, Expr size) {
  exists(Method method, Parameter input, VarAccess access |
    method = allocation.getEnclosingCallable() and
    p0AttackerParameter(method, input) and access.getVariable() = input and
    (access = size or access.getParent+() = size)
  )
}

predicate allocationSizeDriver(
  Expr allocation, Expr size, string operation, string receiver, string evidence
) {
  (
    allocation instanceof MethodCall and
    allocationCall(allocation.(MethodCall)) and
    size = allocation.(MethodCall).getArgument(0) and
    operation = allocation.(MethodCall).getMethod().getDeclaringType().getQualifiedName() + "." + allocation.(MethodCall).getMethod().getName() and
    receiver = allocation.(MethodCall).getMethod().getDeclaringType().getQualifiedName() and
    evidence = "allocation_size_argument"
    or
    allocation instanceof ArrayCreationExpr and
    size = allocation.(ArrayCreationExpr).getADimension() and
    operation = "array_creation" and receiver = allocation.getType().toString() and
    evidence = "array_dimension_size"
    or
    allocation instanceof ClassInstanceExpr and
    (
      allocation.(ClassInstanceExpr).getConstructedType().hasQualifiedName("java.awt.image", "BufferedImage")
      or allocation.(ClassInstanceExpr).getConstructedType().hasQualifiedName("com.wf.captcha", "SpecCaptcha")
    ) and
    size = [allocation.(ClassInstanceExpr).getArgument(0), allocation.(ClassInstanceExpr).getArgument(1)] and
    operation = allocation.(ClassInstanceExpr).getConstructedType().getQualifiedName() + ".<init>" and
    receiver = allocation.(ClassInstanceExpr).getConstructedType().getQualifiedName() and
    evidence = "image_dimension_size"
  )
}

predicate directAllocationIdentity(Expr allocation, string operation, string receiver) {
  exists(Expr size, string evidence |
    allocationSizeDriver(allocation, size, operation, receiver, evidence)
  )
}

/** Syntactic containment is deliberately broader than an expression statement:
 * allocations in returns, arguments, assignments, and initializers all count.
 * The loop-control source is proved separately by the shared global-flow model.
 */
predicate allocationInLoopBody(Expr allocation, LoopStmt loop) {
  growthLexicallyInLoopBody(allocation, loop)
}

string unmodeledLoopDemand(LoopStmt loop) {
  exists(Expr condition |
    condition = loop.getCondition() and result = condition.toString()
  )
  or
  not exists(Expr condition | condition = loop.getCondition()) and
  result = "enclosing_loop"
}

from Expr allocation, string operation, string receiver, string evidence,
     string demandName, string demandRole, string coverageStatus, string note
where
  (
    exists(Expr size |
      allocationSizeDriver(allocation, size, operation, receiver, evidence) and
      demandName = size.toString() and demandRole = "size" and
      (
        sizeUsesAttackerParameter(allocation, size) and
        coverageStatus = "complete" and
        note = "direct_allocation:handler_parameter_size"
        or not sizeUsesAttackerParameter(allocation, size) and
           size instanceof CompileTimeConstantExpr and
           coverageStatus = "complete" and
           note = "direct_allocation:server_controlled_fixed_size"
        or not sizeUsesAttackerParameter(allocation, size) and
           not size instanceof CompileTimeConstantExpr and
           coverageStatus = "partial" and
           note = "direct_allocation:size_origin_unclassified"
      )
    )
    or
    directAllocationIdentity(allocation, operation, receiver) and
    evidence = "allocation_loop_multiplicity" and
    demandRole = "iteration_count" and
    exists(LoopStmt loop |
      allocationInLoopBody(allocation, loop) and
      (
        exists(Parameter bound, VarAccess boundAccess |
          provenAttackerLoopMultiplicityForDirectAllocation(
            allocation, loop, bound, boundAccess
          ) and
          demandName = bound.getName() and
          coverageStatus = "complete" and
          note = "direct_allocation:attacker_controlled_loop_multiplicity_proven"
        )
        or
        not exists(Parameter provenBound, VarAccess provenAccess |
          provenAttackerLoopMultiplicityForDirectAllocation(
            allocation, loop, provenBound, provenAccess
          )
        ) and
        demandName = unmodeledLoopDemand(loop) and
        coverageStatus = "partial" and
        note = "direct_allocation:loop_multiplicity_unmodeled"
      )
    )
  )
select
  allocation.getLocation().getFile().getRelativePath() as site_file,
  allocation.getLocation().getStartLine() as site_start_line,
  "direct_allocation" as growth_kind,
  operation,
  "bytes" as resource_dimension,
  receiver,
  "allocation" as field_path,
  demandName as demand_input_name,
  demandRole as demand_input_role,
  "request" as escape_scope,
  evidence as candidate_evidence,
  coverageStatus as coverage_status,
  note as coverage_note
