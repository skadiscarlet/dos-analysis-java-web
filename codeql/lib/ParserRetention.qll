/**
 * @name ParserRetention
 * @description Parser/body retention candidates for Web DoS analysis.
 */

import java

class MultipartReaderEntry extends Method {
  MultipartReaderEntry() {
    this.getName() in ["readFrom", "readMultiPart"] and
    this.getDeclaringType().getQualifiedName().regexpMatch(
      ".*jersey\\.media\\.multipart\\.internal\\..*MultiPartReader.*"
    ) and
    exists(Parameter p |
      p = this.getAParameter() and
      p.getType().getName().regexpMatch(".*InputStream")
    )
  }

  Parameter getStreamParameter() {
    result = this.getAParameter() and
    result.getType().getName().regexpMatch(".*InputStream")
  }
}

class MultipartBodyPartAdd extends MethodCall {
  MultipartBodyPartAdd() {
    this.getMethod().getName() = "add" and
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    this.getEnclosingCallable().getDeclaringType().getQualifiedName().regexpMatch(
      ".*jersey\\.media\\.multipart\\.internal\\..*MultiPartReader.*"
    ) and
    (
      exists(MethodCall bodyParts |
        bodyParts = this.getQualifier() and
        bodyParts.getMethod().getName() = "getBodyParts"
      )
      or
      this.getQualifier().toString().regexpMatch("(?i).*bodyParts.*")
    )
  }

  Expr getGrowthDriver() { result = this.getArgument(0) }

  Expr getReceiverExpr() { result = this.getQualifier() }
}

predicate multipartReadFlow(
  MultipartReaderEntry entry,
  MultipartBodyPartAdd sink,
  string callPath,
  string callPathDepth
) {
  sink.getEnclosingCallable() = entry and
  callPath = entry.getDeclaringType().getQualifiedName() + "." + entry.getName() +
    " -> " + sink.getMethod().getDeclaringType().getQualifiedName() + "." +
    sink.getMethod().getName() and
  callPathDepth = "1"
  or
  exists(MethodCall call |
    call.getEnclosingCallable() = entry and
    call.getCallee() = sink.getEnclosingCallable() and
    callPath = entry.getDeclaringType().getQualifiedName() + "." + entry.getName() +
      " -> " + sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + "." +
      sink.getEnclosingCallable().getName() + " -> " +
      sink.getMethod().getDeclaringType().getQualifiedName() + "." + sink.getMethod().getName() and
    callPathDepth = "2"
  )
}

predicate multipartHasMimeLoop(MultipartReaderEntry entry) {
  exists(MethodCall call |
    call.getEnclosingCallable() = entry and
    call.getMethod().getName() in ["getMimeParts", "getAttachments"]
  )
  or
  exists(MethodCall call, Callable helper |
    call.getEnclosingCallable() = entry and
    call.getCallee() = helper and
    exists(MethodCall inner |
      inner.getEnclosingCallable() = helper and
      inner.getMethod().getName() in ["getMimeParts", "getAttachments"]
    )
  )
}

string parserDebugNotes(MultipartReaderEntry entry, MultipartBodyPartAdd sink) {
  multipartHasMimeLoop(entry) and
  result = "body_source=InputStream; parser_loop=getMimeParts/getAttachments; " +
    "part_accumulator=" + sink.getReceiverExpr().toString() +
    "; bound_check=not_modeled"
  or
  not multipartHasMimeLoop(entry) and
  result = "body_source=InputStream; parser_loop=unknown; part_accumulator=" +
    sink.getReceiverExpr().toString() + "; bound_check=not_modeled"
}
