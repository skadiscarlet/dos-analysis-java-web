#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for dependencytrack__dependency-track-DTRACK-APP-STATIC-0001

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001
docker compose -p codex_dtrack_dos_retest_0001 -f docker-compose.yml up -d
DTRACK_COMPOSE_PROJECT=codex_dtrack_dos_retest_0001 DTRACK_APISERVER_CONTAINER=codex_dtrack_dos_retest_0001-apiserver-1 DTRACK_PUT_DECODED_MIB= DTRACK_POST_PART_MIB=768 DTRACK_REQUEST_TIMEOUT=900 ./probe.py
docker compose -p codex_dtrack_dos_retest_0001 -f docker-compose.yml down -v --remove-orphans
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
