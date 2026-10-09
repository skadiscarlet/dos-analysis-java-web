# PoC-33 chain-level recall report

Format: `dosweb-poc33-recall-oracle-v3`
Total truth records: 33

## Disposition counts

- `full_chain_finding`: 2
- `not_in_run`: 31

## Execution scope

Scope counts: `{"in_run": 2, "not_in_run": 31, "unverified_scope": 0}`
`in_run` means selected by a verified plan, not necessarily completed. `not_in_run` is not a failed analysis. No plan means unverified scope.
The full truth denominator is retained. Historical runs and unknown findings are not additional positives.

## Per-record disposition

| record_id | repository | execution_scope | status | verdicts | reason_codes |
|---|---|---|---|---|---|
| apache__druid-DRUID-APP-STATIC-0001 | apache/druid | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| apache__druid-DRUID-APP-STATIC-0002 | apache/druid | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| apache__hertzbeat-HERTZBEAT-DOS-0001 | apache/hertzbeat | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| apache__skywalking-SKYWALKING-APP-STATIC-0002 | apache/skywalking | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| apache__solr-SOLR-APP-STATIC-0001 | apache/solr | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| prestodb__presto-PRESTO-APP-STATIC-0001 | prestodb/presto | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| thingsboard__thingsboard-TB-APP-STATIC-0001 | thingsboard/thingsboard | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| thingsboard__thingsboard-TB-APP-STATIC-0002 | thingsboard/thingsboard | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| dependencytrack__dependency-track-DTRACK-APP-STATIC-0001 | dependencytrack/dependency-track | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| openzipkin__zipkin-ZIPKIN-APP-STATIC-0001 | openzipkin/zipkin | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| CITRUS-APP-STATIC-0001 | yiuman/citrus | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| DCMP-STATIC-0001 | dromara/datacompare | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| DCMP-STATIC-0002 | dromara/datacompare | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| POWERJOB-APP-STATIC-0002 | powerjob/powerjob | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| RYVF-APP-STATIC-0001 | yangzongzhuan/ruoyi-vue-fast | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| SMQTT-APP-STATIC-0002 | quickmsg/smqtt | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| SMQTT-APP-STATIC-0004 | quickmsg/smqtt | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| XXL-JOB-APP-STATIC-0002 | xuxueli/xxl-job | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| CITRUS-APP-STATIC-0002 | yiuman/citrus | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| ERUPT-APP-STATIC-0001 | erupts/erupt | in_run | full_chain_finding | static_vulnerable | FINDING_CERTIFICATE_BACKED |
| ERUPT-APP-STATIC-0002 | erupts/erupt | in_run | full_chain_finding | static_unknown | FINDING_CERTIFICATE_BACKED |
| JMQTT-APP-STATIC-0002 | cicizz/jmqtt | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| REBUILD-APP-STATIC-0002 | getrebuild/rebuild | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| REBUILD-APP-STATIC-0003 | getrebuild/rebuild | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| SMQTT-APP-STATIC-0003 | quickmsg/smqtt | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| SMQTT-APP-STATIC-0006 | quickmsg/smqtt | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| WGCLOUD-APP-STATIC-0002 | tianshiyeben/wgcloud | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| XXL-JOB-APP-STATIC-0003 | xuxueli/xxl-job | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| XXL-JOB-APP-STATIC-0004 | xuxueli/xxl-job | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| grobidorg__grobid-GROBID-STATIC-001 | grobidorg/grobid | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| grobidorg__grobid-GROBID-STATIC-002 | grobidorg/grobid | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| jetlinks__jetlinks-community-JL-STAGEA-0001 | jetlinks/jetlinks-community | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |
| walmartlabs__concord-fnd3 | walmartlabs/concord | not_in_run | not_in_run | - | PROJECT_NOT_SELECTED_IN_VERIFIED_PLAN |

