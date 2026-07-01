#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for prestodb__presto-PRESTO-APP-STATIC-0001

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001
docker run -d --name dos-presto-prestodb-presto-static-0001 --memory=2g --memory-swap=2g -p 127.0.0.1:18080:8080 prestodb/presto:0.298.1
curl -fsS http://127.0.0.1:18080/v1/info
./probe.py
docker rm -f -v dos-presto-prestodb-presto-static-0001
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
