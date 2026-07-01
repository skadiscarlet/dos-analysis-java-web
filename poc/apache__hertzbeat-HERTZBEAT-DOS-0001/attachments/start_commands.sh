#!/usr/bin/env bash
set -euo pipefail

docker pull docker.m.daocloud.io/apache/hertzbeat:1.8.0
docker run -d \
  --name hbdos0001-hertzbeat \
  --memory 2g \
  --memory-swap 2g \
  -e JAVA_OPTS="-Xms1g -Xmx1g -XX:MaxDirectMemorySize=1g --add-opens=java.base/java.nio=org.apache.arrow.memory.core,ALL-UNNAMED" \
  -p 2157:1157 \
  -p 2158:1158 \
  docker.m.daocloud.io/apache/hertzbeat:1.8.0

for _ in $(seq 1 90); do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:2157/ || true)"
  [ "$code" != "000" ] && break
  sleep 2
done
