#!/usr/bin/env bash
set -euo pipefail

CASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="tb-dos-thingsboard-static-0001"

cd "$CASE_DIR"
mkdir -p logs evidence runtime/tb-logs runtime/postgres
chmod 0777 runtime/tb-logs

docker compose -p "$PROJECT" up -d postgres
docker compose -p "$PROJECT" run --rm \
  -e INSTALL_TB=true \
  -e LOAD_DEMO=false \
  -e JAVA_OPTS="-Xms512m -Xmx1024m -Xss384k" \
  tb-node
docker compose -p "$PROJECT" up -d tb-node

for i in $(seq 1 120); do
  if curl -fsS -m 5 http://127.0.0.1:18080/login >/dev/null; then
    echo "ThingsBoard is ready on http://127.0.0.1:18080"
    exit 0
  fi
  sleep 5
done

echo "ThingsBoard did not become ready within 600 seconds" >&2
docker compose -p "$PROJECT" ps >&2 || true
exit 1
