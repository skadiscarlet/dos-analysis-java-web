/**
 * Test query for Persistence.qll - finds Web long-lived containers
 */

import java
import lib.Persistence

from WebLongLivedContainer wc
select wc, wc.getPersistenceKind() as kind
