/**
 * @name Test JAX-RS Resource Method Detection
 * @description Find all JAX-RS resource methods (@GET, @POST, etc.)
 * @kind table
 */

import java

from Method m, Annotation a
where
  a = m.getAnAnnotation() and
  (
    a.getType().hasQualifiedName("javax.ws.rs", ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]) or
    a.getType().hasQualifiedName("jakarta.ws.rs", ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
  )
select m, "JAX-RS resource method: " + m.getDeclaringType().getQualifiedName() + "." + m.getName()
