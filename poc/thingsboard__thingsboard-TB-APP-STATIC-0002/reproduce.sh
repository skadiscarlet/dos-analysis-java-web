#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for thingsboard__thingsboard-TB-APP-STATIC-0002

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002
docker run -d --name tb-dos-thingsboard-static-0002 --memory=4096m --memory-swap=4096m -e JAVA_OPTS='-Xms512m -Xmx1536m -XX:+ExitOnOutOfMemoryError' -p 127.0.0.1:19090:9090 -v "$PWD/data:/data" -v "$PWD/container-logs:/var/log/thingsboard" thingsboard/tb-postgres:latest
./probe.py --endpoint attributes --sizes-mib 17,64,128,256 --control-mib 17 --value-len 8192
docker rm -f -v tb-dos-thingsboard-static-0002
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
