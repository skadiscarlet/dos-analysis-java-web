#!/usr/bin/env bash
set -euo pipefail

CASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="druid_avatica_case"

docker compose -p "$PROJECT" -f "$CASE_DIR/docker-compose.yml" up -d postgres zookeeper coordinator broker router
python3 "$CASE_DIR/probe.py" --case-dir "$CASE_DIR" --compose-project "$PROJECT" --compose-file "$CASE_DIR/docker-compose.yml" --wait-only
python3 "$CASE_DIR/probe.py" --case-dir "$CASE_DIR" --compose-project "$PROJECT" --compose-file "$CASE_DIR/docker-compose.yml"

# Cleanup command used after evidence collection:
# docker compose -p "$PROJECT" -f "$CASE_DIR/docker-compose.yml" down -v
