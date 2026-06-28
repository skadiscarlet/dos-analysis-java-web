# High-Probability Application DoS Disclosure Packages

Generated: 2026-06-28 01:36 Asia/Shanghai

This directory contains one private disclosure package per high-probability dynamically confirmed application DoS finding. Each package has a submission guide, a vulnerability report, and attachments.

| Candidate | Project | Directory | Requests | Heap | Report target |
| --- | --- | --- | ---: | --- | --- |
| `POWERJOB-APP-STATIC-0002` | `powerjob__powerjob` | `POWERJOB-APP-STATIC-0002__powerjob-preauth-body-cache-oom` | 8 | `192m` | https://github.com/PowerJob/PowerJob |
| `SMQTT-APP-STATIC-0001` | `quickmsg__smqtt` | `SMQTT-APP-STATIC-0001__smqtt-persistent-session-registry-oom` | 43706 | `96m` | https://github.com/quickmsg/smqtt |
| `SMQTT-APP-STATIC-0002` | `quickmsg__smqtt` | `SMQTT-APP-STATIC-0002__smqtt-retained-message-map-oom` | 100 | `96m` | https://github.com/quickmsg/smqtt |
| `SMQTT-APP-STATIC-0003` | `quickmsg__smqtt` | `SMQTT-APP-STATIC-0003__smqtt-empty-topic-key-oom` | 22325 | `96m` | https://github.com/quickmsg/smqtt |
| `SMQTT-APP-STATIC-0004` | `quickmsg__smqtt` | `SMQTT-APP-STATIC-0004__smqtt-offline-session-queue-oom` | 100 | `96m` | https://github.com/quickmsg/smqtt |
| `SMQTT-APP-STATIC-0005` | `quickmsg__smqtt` | `SMQTT-APP-STATIC-0005__smqtt-subscription-index-oom` | 105000 | `96m` | https://github.com/quickmsg/smqtt |
| `SMQTT-APP-STATIC-0006` | `quickmsg__smqtt` | `SMQTT-APP-STATIC-0006__smqtt-qos2-half-handshake-oom` | 140 | `96m` | https://github.com/quickmsg/smqtt |
| `JMQTT-APP-STATIC-0002` | `cicizz__jmqtt` | `JMQTT-APP-STATIC-0002__jmqtt-qos2-half-handshake-oom` | 230 | `128m` | https://github.com/Cicizz/jmqtt |
| `ERUPT-APP-STATIC-0001` + `ERUPT-APP-STATIC-0002` | `erupts__erupt` | `ERUPT-APP-STATIC-0001__erupt-captcha-height-bufferedimage-oom` | 1 / 2 | `128m` | https://github.com/erupts/erupt |
| `ERUPT-APP-STATIC-0002` | `erupts__erupt` | `ERUPT-APP-STATIC-0002__erupt-operation-log-json-body-copy-oom` | 2 | `128m` | merged into `ERUPT-APP-STATIC-0001` issue draft |
| `REBUILD-APP-STATIC-0002` | `getrebuild__rebuild` | `REBUILD-APP-STATIC-0002__rebuild-barcode-rendering-oom` | 3 | `128m` | https://github.com/getrebuild/rebuild |
| `REBUILD-APP-STATIC-0003` | `getrebuild__rebuild` | `REBUILD-APP-STATIC-0003__rebuild-api-gateway-preauth-json-oom` | 7 | `128m` | https://github.com/getrebuild/rebuild |
| `OPSLI-BOOT-APP-STATIC-0001` | `hiparker__opsli-boot` | `OPSLI-BOOT-APP-STATIC-0001__opsli-waf-json-body-copy-oom` | 8 | `160m` | https://github.com/hiparker/opsli-boot |
| `WGCLOUD-APP-STATIC-0002` | `tianshiyeben__wgcloud` | `WGCLOUD-APP-STATIC-0002__wgcloud-default-token-min-task-oom` | 16 | `160m` | https://github.com/tianshiyeben/wgcloud |
| `XXL-BOOT-APP-STATIC-0001` + `XXL-BOOT-APP-STATIC-0003` | `xuxueli__xxl-boot` | `XXL-BOOT-APP-STATIC-0001__xxl-boot-repeatablefilter-login-body-oom` | 3 / 383 | `128m` / `160m` | https://github.com/xuxueli/xxl-boot |
| `XXL-BOOT-APP-STATIC-0003` | `xuxueli__xxl-boot` | `XXL-BOOT-APP-STATIC-0003__xxl-boot-login-failure-async-queue-oom` | 383 | `160m` | merged into `XXL-BOOT-APP-STATIC-0001` issue draft |
