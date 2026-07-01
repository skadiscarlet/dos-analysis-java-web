#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for apache__druid-DRUID-APP-STATIC-0001

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001
docker compose -p druiddos_apache_druid up -d
./probe.py --max-size 536870912 --size-steps 1048576,8388608,33554432,67108864,134217728,268435456,536870912 --content-types text/plain --concurrency 1 --timeout 360 --chunk-size 1048576 --stop-on-failure
docker compose -p druiddos_apache_druid down -v
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
