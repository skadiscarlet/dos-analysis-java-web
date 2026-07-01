#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for apache__skywalking-SKYWALKING-APP-STATIC-0002

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002
docker compose -p sw-pprof-case up -d
python3 probe.py --streams 48 --content-size 31457280 --hold-seconds 35 --stagger-seconds 0.05 --sample-interval 0.5 --out logs/probe-failure-1g-48stream-30m.json
docker compose -p sw-pprof-case down -v
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
