#!/usr/bin/env bash
set -euo pipefail

CASE_DIR="/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001"
CONTAINER_NAME="${1:-dos-solr-form-apache-solr-static-0001}"
IMAGE="solr:9.8.1"
PORT="18983"
CORE="doscore"

docker run -d \
  --name "${CONTAINER_NAME}" \
  --memory 768m \
  --memory-swap 768m \
  -e SOLR_HEAP=256m \
  -p "127.0.0.1:${PORT}:8983" \
  "${IMAGE}" \
  solr-precreate "${CORE}"

echo "${CONTAINER_NAME}" > "${CASE_DIR}/evidence/container_name.txt"
echo "http://127.0.0.1:${PORT}/solr/${CORE}" > "${CASE_DIR}/evidence/base_url.txt"
