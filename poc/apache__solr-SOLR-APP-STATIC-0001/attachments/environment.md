# Environment

- Case ID: `apache__solr-SOLR-APP-STATIC-0001`
- Host workspace: `/home/furina/new_tool/dos-analysis-web`
- Deployment source: official Docker image
- Image: `solr:9.8.1`
- Image digest: `solr@sha256:86a7f3fbec6596b4ee1122b6a862f41eb4b7f41a164abbc169ba9ee03e41525b`
- Local image ID: `sha256:a1baaa74c3a2a77258bfcea71c9db12c11f7a76423d32bb0bc5afa48bf27fe5e`
- Platform: `linux/amd64`
- Docker registry mirror observed: `https://docker.1panelproxy.com/`
- Container name: written to `evidence/container_name.txt` at runtime
- Port binding: `127.0.0.1:18983 -> 8983/tcp`
- Core: `doscore`, created by `solr-precreate`
- Heap/container limit: `SOLR_HEAP=256m`, Docker `--memory 768m --memory-swap 768m`
- Config changes: no Solr configset or application changes. The heap and container memory limits are validation harness safety limits. An initial dry run with Docker `--memory 512m --memory-swap 512m` showed baseline cgroup memory near the limit, so the container limit was raised to 768MiB before running the probe to avoid confusing cgroup pressure with target JVM heap pressure.
- Auth: default Solr Docker deployment has security off for this local quickstart-style core.
- Static source checkout: `/home/furina/new_tool/dos-analysis-web/frameworks/applications/apache__solr`, commit `138f1737e8ea2ffd0bf5629563a54310c1dbb460`, dirty, base version in `build.gradle` is `11.0.0-SNAPSHOT`.

## Commands

Start command:

```bash
/home/furina/new_tool/dos-analysis-web/results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001/start_commands.sh dos-solr-form-apache-solr-static-0001
```

Readiness checks:

```bash
curl -fsS http://127.0.0.1:18983/solr/admin/info/system
curl -fsS http://127.0.0.1:18983/solr/doscore/select?q=*:*
```

Cleanup command:

```bash
docker rm -f -v dos-solr-form-apache-solr-static-0001
```

Runtime logs and evidence are stored under `logs/` and `evidence/`.
