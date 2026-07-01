#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for thingsboard__thingsboard-TB-APP-STATIC-0001

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001
docker compose -p tb-dos-thingsboard-static-0001 up -d postgres
docker compose -p tb-dos-thingsboard-static-0001 run --rm -e INSTALL_TB=true -e LOAD_DEMO=false -e JAVA_OPTS='-Xms512m -Xmx1024m -Xss384k' tb-node
docker compose -p tb-dos-thingsboard-static-0001 up -d tb-node
./probe.py --token <token-shaped-path-segment> --endpoint telemetry --payload-mode timeseries-large-value --sizes-mib 256,512 --timeout 240 --chunk-bytes 65536 --out logs/probe_results_reinforce_telemetry_large.jsonl
docker compose -p tb-dos-thingsboard-static-0001 down -v
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
