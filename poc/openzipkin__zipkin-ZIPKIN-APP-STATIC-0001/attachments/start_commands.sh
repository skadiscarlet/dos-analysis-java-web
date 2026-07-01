#!/usr/bin/env bash
set -euo pipefail

# Recorded start recipe only. This script was not executed during the paused
# validation because the user requested no further service start or probe.

CASE_DIR="/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001"
CONTAINER_NAME="dosval-openzipkin-zipkin-static-0001-retest"
IMAGE="${ZIPKIN_IMAGE:-docker.m.daocloud.io/openzipkin/zipkin-slim:latest}"
PORT="${ZIPKIN_PORT:-19411}"

docker run \
  --name "${CONTAINER_NAME}" \
  -d \
  --memory 384m \
  -p "127.0.0.1:${PORT}:9411" \
  "${IMAGE}"

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" > "${CASE_DIR}/logs/health_startup.txt"; then
    break
  fi
  sleep 1
done

docker logs "${CONTAINER_NAME}" > "${CASE_DIR}/logs/startup.log" 2>&1 || true
