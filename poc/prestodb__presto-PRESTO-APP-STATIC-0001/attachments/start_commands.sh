#!/usr/bin/env bash
set -euo pipefail

docker pull prestodb/presto:0.298.1

docker run -d \
  --name dos-presto-prestodb-presto-static-0001 \
  --memory=2g \
  --memory-swap=2g \
  -p 127.0.0.1:18080:8080 \
  prestodb/presto:0.298.1

for _ in $(seq 1 120); do
  if curl -fsS --max-time 2 http://127.0.0.1:18080/v1/info >/dev/null; then
    curl -fsS --max-time 5 http://127.0.0.1:18080/v1/info
    break
  fi
  sleep 2
done

./probe.py

docker logs dos-presto-prestodb-presto-static-0001 > logs/container_final.log 2>&1 || true
docker inspect dos-presto-prestodb-presto-static-0001 > evidence/container_inspect_final.json || true
docker rm -v dos-presto-prestodb-presto-static-0001 || true
