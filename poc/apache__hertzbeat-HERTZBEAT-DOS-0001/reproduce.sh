#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for apache__hertzbeat-HERTZBEAT-DOS-0001

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001
docker run -d --name hbdos0001-hertzbeat --memory 2g --memory-swap 2g -e JAVA_OPTS="-Xms1g -Xmx1g -XX:MaxDirectMemorySize=1g --add-opens=java.base/java.nio=org.apache.arrow.memory.core,ALL-UNNAMED" -p 2157:1157 -p 2158:1158 docker.m.daocloud.io/apache/hertzbeat:1.8.0
./probe.py --count 30000 --start-index 1 --sample-every 250 --timeout 5 --concurrency 8 --case-dir .
docker rm -f hbdos0001-hertzbeat
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
