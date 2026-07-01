#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for apache__solr-SOLR-APP-STATIC-0001

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
cd results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001
docker run -d --name dos-solr-form-apache-solr-static-0001-1g --memory=2g --memory-swap=2g -e SOLR_HEAP=1g -p 127.0.0.1:28983:8983 solr:9.8.1 solr-precreate doscore
python3 probe.py --case-dir "$PWD" --container dos-solr-form-apache-solr-static-0001-1g --base-url http://127.0.0.1:28983/solr --core doscore --sizes 134217728,268435456,536870912,805306368 --request-timeout 300 --ready-timeout 60
docker rm -f -v dos-solr-form-apache-solr-static-0001-1g
MSG

echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
