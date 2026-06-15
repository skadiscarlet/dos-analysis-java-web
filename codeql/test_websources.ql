/**
 * @name Test WebSources library
 * @description Simple test query to verify WebSources.qll compiles correctly
 * @kind problem
 * @id dos-web/test-websources
 */

import lib.WebSources

from ServletEntryMethod m
select m, "Found servlet entry method: " + m.getName()
