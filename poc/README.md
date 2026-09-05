# Advisory PoC Bundles

- Source JSON: `results/applications_dynamic_validation/binary_truth_collection.json`
- Source Markdown: `results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md`
- Confirmed true positives: `33`

Each case directory contains:

- `SECURITY_ADVISORY.zh-CN.md`
- `SECURITY_ADVISORY.en.md`
- `reproduce.sh` with local-only harness commands
- `attachments/` with source truth/evidence records and copied small artifacts

| ID | App | Batch | Status | Directory |
| --- | --- | --- | --- | --- |
| `apache__druid-DRUID-APP-STATIC-0001` | `apache/druid` | `new` | `confirmed_oom` | [目录](apache__druid-DRUID-APP-STATIC-0001/) |
| `apache__druid-DRUID-APP-STATIC-0002` | `apache/druid` | `new` | `confirmed_oom` | [目录](apache__druid-DRUID-APP-STATIC-0002/) |
| `apache__hertzbeat-HERTZBEAT-DOS-0001` | `apache/hertzbeat` | `new` | `confirmed_oom` | [目录](apache__hertzbeat-HERTZBEAT-DOS-0001/) |
| `apache__skywalking-SKYWALKING-APP-STATIC-0002` | `apache/skywalking` | `new` | `confirmed_oom` | [目录](apache__skywalking-SKYWALKING-APP-STATIC-0002/) |
| `apache__solr-SOLR-APP-STATIC-0001` | `apache/solr` | `new` | `confirmed_oom` | [目录](apache__solr-SOLR-APP-STATIC-0001/) |
| `prestodb__presto-PRESTO-APP-STATIC-0001` | `prestodb/presto` | `new` | `confirmed_oom` | [目录](prestodb__presto-PRESTO-APP-STATIC-0001/) |
| `thingsboard__thingsboard-TB-APP-STATIC-0001` | `thingsboard/thingsboard` | `new` | `confirmed_oom` | [目录](thingsboard__thingsboard-TB-APP-STATIC-0001/) |
| `thingsboard__thingsboard-TB-APP-STATIC-0002` | `thingsboard/thingsboard` | `new` | `confirmed_oom` | [目录](thingsboard__thingsboard-TB-APP-STATIC-0002/) |
| `dependencytrack__dependency-track-DTRACK-APP-STATIC-0001` | `DependencyTrack/dependency-track` | `new_retest` | `confirmed_oom` | [目录](dependencytrack__dependency-track-DTRACK-APP-STATIC-0001/) |
| `openzipkin__zipkin-ZIPKIN-APP-STATIC-0001` | `openzipkin/zipkin` | `new_retest` | `confirmed_oom` | [目录](openzipkin__zipkin-ZIPKIN-APP-STATIC-0001/) |
| `CITRUS-APP-STATIC-0001` | `yiuman__citrus` | `p0` | `verified_oom` | [目录](CITRUS-APP-STATIC-0001/) |
| `DCMP-STATIC-0001` | `dromara__datacompare` | `p0` | `verified_oom` | [目录](DCMP-STATIC-0001/) |
| `DCMP-STATIC-0002` | `dromara__datacompare` | `p0` | `verified_oom` | [目录](DCMP-STATIC-0002/) |
| `POWERJOB-APP-STATIC-0002` | `powerjob__powerjob` | `p0` | `verified_oom` | [目录](POWERJOB-APP-STATIC-0002/) |
| `RYVF-APP-STATIC-0001` | `yangzongzhuan__ruoyi-vue-fast` | `p0` | `verified_oom` | [目录](RYVF-APP-STATIC-0001/) |
| `SMQTT-APP-STATIC-0002` | `quickmsg__smqtt` | `p0` | `verified_oom` | [目录](SMQTT-APP-STATIC-0002/) |
| `SMQTT-APP-STATIC-0004` | `quickmsg__smqtt` | `p0` | `verified_oom` | [目录](SMQTT-APP-STATIC-0004/) |
| `XXL-JOB-APP-STATIC-0002` | `xuxueli__xxl-job` | `p0` | `verified_oom` | [目录](XXL-JOB-APP-STATIC-0002/) |
| `CITRUS-APP-STATIC-0002` | `yiuman__citrus` | `p1` | `verified_oom` | [目录](CITRUS-APP-STATIC-0002/) |
| `ERUPT-APP-STATIC-0001` | `erupts__erupt` | `p1` | `verified_oom` | [目录](ERUPT-APP-STATIC-0001/) |
| `ERUPT-APP-STATIC-0002` | `erupts__erupt` | `p1` | `verified_oom` | [目录](ERUPT-APP-STATIC-0002/) |
| `JMQTT-APP-STATIC-0002` | `cicizz__jmqtt` | `p1` | `verified_oom` | [目录](JMQTT-APP-STATIC-0002/) |
| `REBUILD-APP-STATIC-0002` | `getrebuild__rebuild` | `p1` | `verified_oom` | [目录](REBUILD-APP-STATIC-0002/) |
| `REBUILD-APP-STATIC-0003` | `getrebuild__rebuild` | `p1` | `verified_oom` | [目录](REBUILD-APP-STATIC-0003/) |
| `SMQTT-APP-STATIC-0003` | `quickmsg__smqtt` | `p1` | `verified_oom` | [目录](SMQTT-APP-STATIC-0003/) |
| `SMQTT-APP-STATIC-0006` | `quickmsg__smqtt` | `p1` | `verified_oom` | [目录](SMQTT-APP-STATIC-0006/) |
| `WGCLOUD-APP-STATIC-0002` | `tianshiyeben__wgcloud` | `p1` | `verified_oom` | [目录](WGCLOUD-APP-STATIC-0002/) |
| `XXL-JOB-APP-STATIC-0003` | `xuxueli__xxl-job` | `p1` | `confirmed_thread_exhaustion` | [目录](XXL-JOB-APP-STATIC-0003/) |
| `XXL-JOB-APP-STATIC-0004` | `xuxueli__xxl-job` | `p1` | `verified_oom` | [目录](XXL-JOB-APP-STATIC-0004/) |
| `grobidorg__grobid-GROBID-STATIC-001` | `grobidorg/grobid` | `new_confirmed_20260812` | `confirmed_oom` | [目录](grobidorg__grobid-GROBID-STATIC-001/) |
| `grobidorg__grobid-GROBID-STATIC-002` | `grobidorg/grobid` | `new_confirmed_20260812` | `confirmed_oom` | [目录](grobidorg__grobid-GROBID-STATIC-002/) |
| `jetlinks__jetlinks-community-JL-STAGEA-0001` | `jetlinks/jetlinks-community` | `new_confirmed_20260812` | `confirmed_oom` | [目录](jetlinks__jetlinks-community-JL-STAGEA-0001/) |
| `walmartlabs__concord-fnd3` | `walmartlabs/concord` | `new_confirmed_20260812` | `confirmed_oom` | [目录](walmartlabs__concord-fnd3/) |
