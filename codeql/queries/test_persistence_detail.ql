/**
 * Detailed test for Persistence.qll - shows declaring type and field type
 */

import java
import lib.Persistence

from WebLongLivedContainer wc
select wc,
       wc.getDeclaringType().getQualifiedName() as declaring_type,
       wc.getName() as field_name,
       wc.getType().getName() as field_type,
       wc.getPersistenceKind() as kind
