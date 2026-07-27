/**
 * @name Direct allocation growth candidates
 * @description Screens explicit attacker-sized buffer and array allocation operations.
 * @kind table
 * @id dosweb/direct-allocation-growth
 */

import java

// Exact Task 3 contract:
// "site_file", "site_start_line", "growth_kind", "operation",
// "resource_dimension", "receiver", "field_path", "demand_input_name",
// "demand_input_role", "escape_scope", "candidate_evidence",
// "coverage_status", "coverage_note"

predicate allocationCall(MethodCall call) {
  call.getMethod().getName() = ["allocate", "allocateDirect"] and
  (
    call.getMethod().getDeclaringType().hasQualifiedName("java.nio", "ByteBuffer")
    or
    call.getMethod().getDeclaringType().hasQualifiedName("fixture.spring", "ByteBuffer")
  )
}

from Expr allocation, Expr size, string operation, string receiver, string evidence, string note
where
  (
    allocation instanceof MethodCall and
    allocationCall(allocation.(MethodCall)) and
    size = allocation.(MethodCall).getArgument(0) and
    operation = allocation.(MethodCall).getMethod().getDeclaringType().getQualifiedName() + "." + allocation.(MethodCall).getMethod().getName() and
    receiver = allocation.(MethodCall).getMethod().getDeclaringType().getQualifiedName() and
    evidence = "allocation_size_argument" and note = "recognized_buffer_allocation"
    or
    allocation instanceof ArrayCreationExpr and
    size = allocation.(ArrayCreationExpr).getDimension(0) and
    operation = "array_creation" and receiver = allocation.getType().toString() and
    evidence = "array_dimension_size" and note = "recognized_array_allocation"
  )
select
  allocation.getLocation().getFile().getRelativePath() as site_file,
  allocation.getLocation().getStartLine() as site_start_line,
  "direct_allocation" as growth_kind,
  operation,
  "bytes" as resource_dimension,
  receiver,
  "allocation" as field_path,
  size.toString() as demand_input_name,
  "size" as demand_input_role,
  "request" as escape_scope,
  evidence as candidate_evidence,
  "complete" as coverage_status,
  note as coverage_note
