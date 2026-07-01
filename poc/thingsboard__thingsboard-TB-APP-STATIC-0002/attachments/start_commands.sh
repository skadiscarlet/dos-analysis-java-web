#!/usr/bin/env bash
set -euo pipefail

# Reproduction commands recorded for this case. Do not run against shared systems.
CASE_DIR="/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002"

docker pull thingsboard/tb-postgres:latest

docker run -d \
  --name tb-dos-thingsboard-static-0002 \
  --memory=4096m \
  --memory-swap=4096m \
  -e JAVA_OPTS='-Xms512m -Xmx1536m -XX:+ExitOnOutOfMemoryError' \
  -p 127.0.0.1:19090:9090 \
  -p 127.0.0.1:11883:1883 \
  -p 127.0.0.1:15683:5683/udp \
  -p 127.0.0.1:15685:5685/udp \
  -p 127.0.0.1:15686:5686/udp \
  -v "${CASE_DIR}/data:/data" \
  -v "${CASE_DIR}/container-logs:/var/log/thingsboard" \
  thingsboard/tb-postgres:latest

"${CASE_DIR}/probe.py" \
  --endpoint attributes \
  --sizes-mib 17,64,128,256,384,512 \
  --control-mib 17 \
  --value-len 8192

docker rm -f tb-dos-thingsboard-static-0002
