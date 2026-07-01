#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for XXL-JOB-APP-STATIC-0004

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
python3 scripts/run_application_p1_dynamic_validation.py --case XXL-JOB-APP-STATIC-0004 --min-heap 1g
MSG

if [[ "${RUN_LOCAL_DOS_POC:-}" == "1" ]]; then
  cd "$REPO_ROOT"
  python3 scripts/run_application_p1_dynamic_validation.py --case XXL-JOB-APP-STATIC-0004 --min-heap 1g
else
  echo "Set RUN_LOCAL_DOS_POC=1 to execute the local disposable harness."
fi
