#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for openzipkin__zipkin-ZIPKIN-APP-STATIC-0001

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001
docker run --name dosval-openzipkin-zipkin-static-0001-1g -d --memory=2g --memory-swap=2g -e JAVA_OPTS='-Xms256m -Xmx1g -XX:+ExitOnOutOfMemoryError' -p 127.0.0.1:29411:9411 docker.m.daocloud.io/openzipkin/zipkin-slim:latest
python3 probe.py --base-url http://127.0.0.1:29411 --container dosval-openzipkin-zipkin-static-0001-1g --out logs/probe_results_1g_confirmed.jsonl --metrics-out evidence/metrics_snapshots_1g_confirmed.txt --mode plain --pause 1 --extra-gzip 160000:8192
docker rm -f dosval-openzipkin-zipkin-static-0001-1g
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
