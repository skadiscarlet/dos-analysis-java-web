#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for apache__druid-DRUID-APP-STATIC-0002

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002
docker compose -p druid_avatica_case_1g -f docker-compose.yml up -d postgres zookeeper coordinator broker router
python3 probe.py --case-dir "$PWD" --compose-project druid_avatica_case_1g --compose-file "$PWD/docker-compose.yml" --wait-only --ready-timeout 300
python3 probe.py --case-dir "$PWD" --compose-project druid_avatica_case_1g --compose-file "$PWD/docker-compose.yml" --sizes 134217728,268435456,536870912,805306368 --request-timeout 300 --ready-timeout 60
docker compose -p druid_avatica_case_1g -f docker-compose.yml down -v
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
