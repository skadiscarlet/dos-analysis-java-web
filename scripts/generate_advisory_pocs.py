#!/usr/bin/env python3
"""Generate bilingual security-advisory PoC bundles from binary truth records."""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TRUTH_JSON = ROOT / "results/applications_dynamic_validation/binary_truth_collection.json"
TRUTH_MD = ROOT / "results/applications_dynamic_validation/BINARY_TRUTH_COLLECTION.md"
OUTPUT_ROOT = ROOT / "poc"
MAX_ATTACHED_LOG_BYTES = 8 * 1024 * 1024


CASE_TEXT: dict[str, dict[str, str]] = {
    "apache__druid-DRUID-APP-STATIC-0001": {
        "title_zh": "Apache Druid Router SQL 请求体无上限导致 JVM OOM",
        "title_en": "Apache Druid Router SQL request body can exhaust JVM heap",
        "summary_zh": "默认未启用认证的 Druid Router `POST /druid/v2/sql/` 会在处理 SQL 请求前完整物化攻击者控制的请求体。1GiB Router heap 复测中，单个 512MiB `text/plain` SQL body 触发 `OutOfMemoryError: Java heap space` 并导致 Router 退出。",
        "summary_en": "The default unauthenticated Druid Router `POST /druid/v2/sql/` path materializes attacker-controlled SQL request bodies before processing. In the 1 GiB Router heap retest, one 512 MiB `text/plain` body triggered `OutOfMemoryError: Java heap space` and terminated the Router.",
        "trigger_zh": "向 Router SQL endpoint 顺序发送逐步增大的 `text/plain` SQL 请求体，失败样本为 512MiB body。",
        "trigger_en": "Send progressively larger `text/plain` SQL bodies to the Router SQL endpoint; the failing local sample used a 512 MiB body.",
        "root_zh": "`SqlQuery.from` 路径使用 `IOUtils.toByteArray(request.getInputStream())` 并构造完整字符串，缺少默认请求体大小上限。",
        "root_en": "The `SqlQuery.from` path reads the full input stream with `IOUtils.toByteArray(request.getInputStream())` and constructs a full string without a default body-size cap.",
        "conditions_zh": "匿名可达 Router；无前置账号；上游代理或 Druid 配置未在阈值以下拒绝大请求体。",
        "conditions_en": "Router is reachable anonymously; no account is required; no proxy or Druid setting rejects large bodies below the failure threshold.",
    },
    "apache__druid-DRUID-APP-STATIC-0002": {
        "title_zh": "Apache Druid Router Avatica protobuf 大请求导致 JVM OOM",
        "title_en": "Apache Druid Router Avatica protobuf requests can exhaust JVM heap",
        "summary_zh": "默认未启用认证的 Druid Router Avatica protobuf endpoint 可被匿名客户端提交大型合法 protobuf POST。1GiB Router heap 复测中，128MiB 请求后服务仍运行，256MiB 请求触发 Java heap OOM、Router exit 3 和健康检查连接拒绝。",
        "summary_en": "The default unauthenticated Druid Router Avatica protobuf endpoint accepts large valid protobuf POST bodies. In the 1 GiB Router heap retest, a 128 MiB request left the service running, while a 256 MiB request triggered Java heap OOM, Router exit code 3, and refused health checks.",
        "trigger_zh": "向 `/druid/v2/sql/avatica-protobuf/` 发送 `application/x-protobuf` Avatica OpenConnectionRequest，并附带大型 protobuf unknown field padding。",
        "trigger_en": "POST an `application/x-protobuf` Avatica OpenConnectionRequest to `/druid/v2/sql/avatica-protobuf/` with large protobuf unknown-field padding.",
        "root_zh": "Router 转发路径把 Avatica 请求完整读入 `byte[]` 并挂到 request attribute，缺少默认 body/bytes quota。",
        "root_en": "The Router forwarding path stores the full Avatica request body in a `byte[]` request attribute and lacks a default body/byte quota.",
        "conditions_zh": "匿名可达 Router Avatica endpoint；无前置账号；未由代理、认证或 body limit 拦截。",
        "conditions_en": "The Router Avatica endpoint is anonymously reachable and not blocked by authentication, proxy limits, or request body caps.",
    },
    "apache__hertzbeat-HERTZBEAT-DOS-0001": {
        "title_zh": "Apache HertzBeat Prometheus push 高基数 job/instance 导致 direct buffer OOM",
        "title_en": "Apache HertzBeat Prometheus push cardinality can exhaust direct memory",
        "summary_zh": "默认 HertzBeat 1.8.0 Docker 部署中，匿名 Prometheus push path 会根据唯一 job/instance 自动创建监控项。1GiB heap/direct、2GiB 容器复测中，约 21.7k 个最小 push 请求触发 direct-buffer OOM 并造成 push 面重复 HTTP 502。",
        "summary_en": "In the default HertzBeat 1.8.0 Docker deployment, the anonymous Prometheus push path auto-creates monitors from unique job/instance values. With 1 GiB heap/direct memory and a 2 GiB container, about 21.7k minimal push requests triggered direct-buffer OOM and repeated HTTP 502 responses on the push plane.",
        "trigger_zh": "对 `/api/push/prometheus/job/{job}/instance/{instance}` 发送最小 Prometheus text body，并不断变化 job/instance path segment。",
        "trigger_en": "Send minimal Prometheus text bodies to `/api/push/prometheus/job/{job}/instance/{instance}` while rotating job and instance path segments.",
        "root_zh": "job/instance 组合被用于自动创建和保留 push monitor 状态，默认未观察到认证、速率、基数或淘汰边界。",
        "root_en": "The job/instance pair drives automatic retained push-monitor state, and no default authentication, rate, cardinality, or eviction bound was observed.",
        "conditions_zh": "匿名可达 `/api/push/**`；push auto-create 开启；未限制 job/instance 基数或来源。",
        "conditions_en": "`/api/push/**` is reachable anonymously, push auto-create is enabled, and job/instance cardinality is not bounded per source.",
    },
    "apache__skywalking-SKYWALKING-APP-STATIC-0002": {
        "title_zh": "Apache SkyWalking OAP pprof collect 流可触发 heap OOM",
        "title_en": "Apache SkyWalking OAP pprof collect streams can exhaust heap",
        "summary_zh": "默认 OAP gRPC 11800 匿名可达且 pprof receiver 使用内存 parser 时，多个未完成 collect 流只需发送 metadata.contentSize 即可在上传内容和任务校验前分配堆内存。1GiB heap、2GiB 容器复测中 48 条流触发 OAP exit 3。",
        "summary_en": "When the default OAP gRPC port 11800 is anonymously reachable and the pprof receiver uses the memory parser, multiple unfinished collect streams can allocate heap from `metadata.contentSize` before content upload and task validation. In the 1 GiB heap, 2 GiB container retest, 48 streams caused OAP exit code 3.",
        "trigger_zh": "打开多个 `/skywalking.v10.PprofTask/collect` 双向 gRPC 流，发送 contentSize 接近默认 30MiB 的 metadata frame 后保持流未完成。",
        "trigger_en": "Open multiple bidirectional `/skywalking.v10.PprofTask/collect` gRPC streams, send metadata frames with contentSize near the default 30 MiB limit, and keep the streams unfinished.",
        "root_zh": "`PprofByteBufCollectionObserver.onNext` 在 contentSize 未超过默认上限时直接 `ByteBuffer.allocate(contentSize)`，并发流数量未被默认配额约束。",
        "root_en": "`PprofByteBufCollectionObserver.onNext` directly allocates `ByteBuffer.allocate(contentSize)` when contentSize is within the default limit, while concurrent streams are not bounded by a default quota.",
        "conditions_zh": "OAP gRPC receiver 暴露给低信任客户端；认证为空；pprof receiver 和 memory parser 可用。",
        "conditions_en": "The OAP gRPC receiver is exposed to low-trust clients, authentication is empty, and the pprof receiver memory parser is enabled.",
    },
    "apache__solr-SOLR-APP-STATIC-0001": {
        "title_zh": "Apache Solr form-urlencoded /select 大表单导致 JVM OOM",
        "title_en": "Apache Solr form-urlencoded /select requests can exhaust JVM heap",
        "summary_zh": "官方 Solr Docker 默认安全关闭部署中，匿名客户端可向默认 core 的 `/select` 发送大型 form-url-encoded POST。SOLR_HEAP=1g、2GiB 容器复测中，256MiB 表单请求触发 Java heap OOM 并导致服务退出。",
        "summary_en": "In the official Solr Docker deployment with default security disabled, an anonymous client can send a large form-url-encoded POST to a default core `/select` handler. With SOLR_HEAP=1g and a 2 GiB container, a 256 MiB form request triggered Java heap OOM and process exit.",
        "trigger_zh": "向 `/solr/{core}/select` POST `application/x-www-form-urlencoded`，包含 `q=*:*` 和大量攻击者控制参数。",
        "trigger_en": "POST `application/x-www-form-urlencoded` to `/solr/{core}/select` with `q=*:*` plus many attacker-controlled parameters.",
        "root_zh": "`SolrRequestParsers.parseFormDataContent` 在 handler 执行前累积 key/value bytes、解码字符串和参数数组，默认路径未在阈值以下拒绝大表单。",
        "root_en": "`SolrRequestParsers.parseFormDataContent` accumulates key/value bytes, decoded strings, and parameter arrays before handler execution, and the tested default path did not reject large forms below the failure threshold.",
        "conditions_zh": "Solr HTTP endpoint 匿名可达；默认 core 存在；未配置严格 formdataUploadLimit 或代理 body limit。",
        "conditions_en": "Solr HTTP endpoints are anonymously reachable, a core exists, and no strict `formdataUploadLimit` or proxy body limit blocks the request.",
    },
    "prestodb__presto-PRESTO-APP-STATIC-0001": {
        "title_zh": "Presto /v1/statement 未轮询查询保留导致默认 1GiB heap OOM",
        "title_en": "Presto /v1/statement abandoned submissions can exhaust the default 1 GiB heap",
        "summary_zh": "默认官方 Presto coordinator 无认证暴露 `/v1/statement` 时，匿名客户端连续提交约 700KiB SQL 且不轮询返回的 `nextUri`，会线性保留 Query/session 对象并触发默认 1GiB heap OOM。",
        "summary_en": "When the official Presto coordinator exposes `/v1/statement` without authentication, an anonymous client can repeatedly submit roughly 700 KiB SQL statements and never poll the returned `nextUri`, causing retained Query/session state to grow until the default 1 GiB heap is exhausted.",
        "trigger_zh": "POST `/v1/statement`，带 `X-Presto-User`，提交唯一 padded SQL，并故意不访问返回的 queued `nextUri`。",
        "trigger_en": "POST `/v1/statement` with `X-Presto-User`, submit unique padded SQL, and intentionally do not follow the returned queued `nextUri`.",
        "root_zh": "queued statement 被放入 `queries` map 并保留请求 SQL 与 session/header 状态，未轮询或未完成查询缺少有效默认保留上限。",
        "root_en": "Queued statements are stored in the `queries` map with SQL and session/header state; unpolled or unfinished queries lack an effective default retention quota.",
        "conditions_zh": "`/v1/statement` 匿名或低信任可达；未启用 HTTP auth；未由代理限制大 SQL 或提交速率。",
        "conditions_en": "`/v1/statement` is reachable by anonymous or low-trust clients, HTTP auth is disabled, and no proxy limits large SQL bodies or submission rate.",
    },
    "thingsboard__thingsboard-TB-APP-STATIC-0001": {
        "title_zh": "ThingsBoard device telemetry chunked JSON 在认证失败前可触发 OOM",
        "title_en": "ThingsBoard device telemetry chunked JSON can trigger OOM before token rejection",
        "summary_zh": "官方 ThingsBoard tb-node 单节点部署中，HTTP device telemetry path 在认证结果返回前读取并绑定 chunked JSON body。-Xmx1024m、2GiB 容器复测中，单个 512MiB timeseries-large-value 请求触发 Java heap OOM 并返回 HTTP 500。",
        "summary_en": "In the official ThingsBoard tb-node single-node deployment, the HTTP device telemetry path reads and binds chunked JSON request bodies before token rejection completes. With -Xmx1024m and a 2 GiB container, one 512 MiB timeseries-large-value request triggered Java heap OOM and HTTP 500.",
        "trigger_zh": "向 `/api/v1/{deviceToken}/telemetry` 发送无 Content-Length 的 chunked JSON，其中单个字符串值非常大。",
        "trigger_en": "Send chunked JSON without Content-Length to `/api/v1/{deviceToken}/telemetry`, with one very large string value.",
        "root_zh": "Spring `@RequestBody String` 和后续 JSON parser 在认证失败响应前完整物化请求体，默认 Content-Length 检查不能约束无 Content-Length chunked 请求。",
        "root_en": "Spring `@RequestBody String` and later JSON parsing materialize the request body before the authentication failure response; the default Content-Length check does not constrain no-Content-Length chunked requests.",
        "conditions_zh": "HTTP device transport 暴露；chunked body 未被网关/容器提前限制；无需有效 device token 即可触发 body binding。",
        "conditions_en": "HTTP device transport is exposed, chunked bodies are not limited by a gateway/container, and a valid device token is not needed to reach body binding.",
    },
    "thingsboard__thingsboard-TB-APP-STATIC-0002": {
        "title_zh": "ThingsBoard authenticated REST attributes chunked body 绕过默认大小检查导致 OOM",
        "title_en": "ThingsBoard authenticated REST attributes chunked bodies bypass default size checks and trigger OOM",
        "summary_zh": "官方单容器部署中，具备 TENANT_ADMIN 等低权限写设备属性能力的客户端，可用无 Content-Length 的 chunked attributes POST 绕过默认 `/api/**` 16MiB Content-Length 检查。1.5GiB heap 复测中，256MiB body 触发 Java heap OOM 并导致 HTTP 不可用。",
        "summary_en": "In the official single-container deployment, a client with a low-privilege role capable of writing device attributes, such as TENANT_ADMIN, can use a chunked attributes POST without Content-Length to bypass the default 16 MiB `/api/**` Content-Length check. With a 1.5 GiB heap, a 256 MiB body triggered Java heap OOM and HTTP unavailability.",
        "trigger_zh": "登录默认租户管理员账号后，对 `/api/plugins/telemetry/DEVICE/{deviceId}/SERVER_SCOPE` 发送带 JWT 的 chunked JSON attributes body。",
        "trigger_en": "After authenticating as the default tenant administrator, send a JWT-authenticated chunked JSON attributes body to `/api/plugins/telemetry/DEVICE/{deviceId}/SERVER_SCOPE`.",
        "root_zh": "PayloadSizeFilter 依赖 Content-Length，chunked no-Content-Length 请求进入 `@RequestBody String` 和 JSON 转换路径后才产生内存压力。",
        "root_en": "PayloadSizeFilter relies on Content-Length; chunked no-Content-Length requests reach `@RequestBody String` and JSON conversion before memory pressure is bounded.",
        "conditions_zh": "需要低权限/租户管理员写设备属性能力和可访问 deviceId；chunked body 未由网关限制。",
        "conditions_en": "Requires a low-privilege or tenant-admin account that can write device attributes for an accessible deviceId, and no gateway limit on chunked bodies.",
    },
    "dependencytrack__dependency-track-DTRACK-APP-STATIC-0001": {
        "title_zh": "Dependency-Track BOM multipart 上传可触发 apiserver JVM OOM",
        "title_en": "Dependency-Track BOM multipart upload can trigger apiserver JVM OOM",
        "summary_zh": "官方 Dependency-Track 5.0.2 compose 默认 apiserver 2GiB 内存下，持有 BOM_UPLOAD 的低权限 API key 可通过单个约 768MiB multipart BOM part 触发 Java heap OOM；请求返回 HTTP 500，日志确认 OOM。",
        "summary_en": "In the official Dependency-Track 5.0.2 compose deployment with the default 2 GiB apiserver memory limit, a low-privilege API key with BOM_UPLOAD can trigger Java heap OOM with a single roughly 768 MiB multipart BOM part; the request returns HTTP 500 and logs confirm OOM.",
        "trigger_zh": "使用仅具备 BOM_UPLOAD 的 API key 向 `/api/v1/bom` 发送包含大 BOM file part 的 multipart/form-data 请求。",
        "trigger_en": "Use a BOM_UPLOAD-only API key to POST multipart/form-data to `/api/v1/bom` with a large BOM file part.",
        "root_zh": "`BomResource` 在校验和处理前将 multipart part 读入 `byte[]`，缺少默认 BOM part 字节上限。",
        "root_en": "`BomResource` reads the multipart part into a `byte[]` before validation/processing and lacks a default BOM part byte limit.",
        "conditions_zh": "需要低权限 BOM_UPLOAD API key 和可访问 project；未由代理或应用限制 multipart/BOM 大小。",
        "conditions_en": "Requires a low-privilege BOM_UPLOAD API key and an accessible project; multipart/BOM size is not capped by a proxy or application limit.",
    },
    "openzipkin__zipkin-ZIPKIN-APP-STATIC-0001": {
        "title_zh": "Zipkin HTTP collector gzip 高解压比 spans 请求导致 JVM OOM",
        "title_en": "Zipkin HTTP collector gzip-expanded spans can exhaust JVM heap",
        "summary_zh": "默认 Zipkin HTTP collector 匿名开放时，小 wire-size 但大解压后体积的 Zipkin v2 spans gzip 请求可触发 Java heap OOM。1GiB heap、2GiB 容器复测中，约 3.37MiB gzip 请求解压为约 1.356GiB 后导致容器 exit 3 和持续 `/health` 502。",
        "summary_en": "When the default Zipkin HTTP collector is anonymously exposed, a small wire-size but highly expanded gzip Zipkin v2 spans request can trigger Java heap OOM. In the 1 GiB heap, 2 GiB container retest, a roughly 3.37 MiB gzip request expanded to about 1.356 GiB and caused container exit code 3 plus sustained `/health` 502.",
        "trigger_zh": "向 `/api/v2/spans` POST 合法 Zipkin v2 JSON span list，使用 `Content-Encoding: gzip` 放大解压后体积。",
        "trigger_en": "POST a valid Zipkin v2 JSON span list to `/api/v2/spans` with `Content-Encoding: gzip` to amplify decompressed size.",
        "root_zh": "collector 解压并解析完整 spans 列表，默认未对解压后大小、span 数量或 gzip ratio 做足够约束。",
        "root_en": "The collector decompresses and parses the complete spans list without an effective default bound on decompressed size, span count, or gzip ratio.",
        "conditions_zh": "HTTP collector 匿名可达；允许 gzip；未在 Zipkin 解码前限制解压后大小或 span 数量。",
        "conditions_en": "HTTP collector is anonymously reachable, gzip is allowed, and decompressed size/span count is not limited before Zipkin decodes the body.",
    },
    "CITRUS-APP-STATIC-0001": {
        "title_zh": "Citrus captcha session verification store 可导致 HttpSession 堆耗尽",
        "title_en": "Citrus captcha session verification store can exhaust heap through HttpSession state",
        "summary_zh": "完整 MySQL/Redis 环境启动并使用 session verification store 时，匿名 `/rest/verify/captcha` 请求会持续创建/保留 session captcha 状态。1GiB heap 复测中约 48.9k 次请求触发目标 JVM OOM。",
        "summary_en": "With the full MySQL/Redis environment and session verification store enabled, anonymous `/rest/verify/captcha` requests continuously create and retain session captcha state. In the 1 GiB heap retest, about 48.9k requests triggered target JVM OOM.",
        "trigger_zh": "重复请求 `/rest/verify/captcha`，不复用 cookie，使服务端创建大量带验证码状态的 HttpSession。",
        "trigger_en": "Repeatedly request `/rest/verify/captcha` without reusing cookies so the server creates many HttpSessions containing captcha state.",
        "root_zh": "验证码状态写入 HttpSession，默认未观察到足够的 session 数量、来源或总字节配额。",
        "root_en": "Captcha state is written to HttpSession, and no sufficient default quota was observed for session count, source, or aggregate bytes.",
        "conditions_zh": "验证码功能使用 session store；入口匿名可达；session 创建/保留未被网关或应用配额限制。",
        "conditions_en": "Captcha uses the session store, the entry is anonymous, and session creation/retention is not bounded by gateway or application quotas.",
    },
    "DCMP-STATIC-0001": {
        "title_zh": "DataCompare demo operate static map 可由登录用户触发 OOM",
        "title_en": "DataCompare demo operate static map can be exhausted by an authenticated user",
        "summary_zh": "默认 Shiro 登录后访问 `/demo/operate/add` 会写入 demo static map。1GiB heap 复测中约 40.3k 次请求触发目标 JVM OOM。",
        "summary_en": "After default Shiro login, requests to `/demo/operate/add` write into a demo static map. In the 1 GiB heap retest, about 40.3k requests triggered target JVM OOM.",
        "trigger_zh": "使用默认登录态重复调用 `/demo/operate/add`，让每次请求写入唯一 static map 项。",
        "trigger_en": "Use an authenticated default session to repeatedly call `/demo/operate/add`, causing each request to write a unique static-map entry.",
        "root_zh": "demo 操作路径存在进程级 static map retained state，缺少默认容量、TTL 或用户/IP 配额。",
        "root_en": "The demo operation path retains process-level static-map state without a default capacity, TTL, or user/IP quota.",
        "conditions_zh": "需要可登录默认应用；demo endpoint 对该登录用户可达。",
        "conditions_en": "Requires a login-capable default application state, and the demo endpoint must be reachable to that user.",
    },
    "DCMP-STATIC-0002": {
        "title_zh": "DataCompare Swagger test static map 可由登录用户触发 OOM",
        "title_en": "DataCompare Swagger test static map can be exhausted by an authenticated user",
        "summary_zh": "默认 Shiro 登录后访问 Swagger test `/test/user/save` 会写入 static map。1GiB heap 复测中约 15k 次请求触发目标 JVM OOM。",
        "summary_en": "After default Shiro login, requests to the Swagger test endpoint `/test/user/save` write into a static map. In the 1 GiB heap retest, about 15k requests triggered target JVM OOM.",
        "trigger_zh": "使用登录态重复 POST `/test/user/save`，提交带唯一字段/填充内容的请求。",
        "trigger_en": "Use an authenticated session to repeatedly POST `/test/user/save` with unique fields or padded content.",
        "root_zh": "测试接口把用户输入写入进程级 static map，未设置容量、TTL 或 per-user quota。",
        "root_en": "The test endpoint stores user input in a process-level static map without a capacity, TTL, or per-user quota.",
        "conditions_zh": "需要默认登录态；测试/Swagger endpoint 未在生产包中禁用。",
        "conditions_en": "Requires a default authenticated session, and the test/Swagger endpoint is not disabled in the deployed package.",
    },
    "POWERJOB-APP-STATIC-0002": {
        "title_zh": "PowerJob 预认证请求体缓存可由普通 POST 触发 OOM",
        "title_en": "PowerJob pre-auth request body caching can be exhausted by ordinary POST bodies",
        "summary_zh": "PowerJob `/container/downloadContainerTemplate` 等路径在鉴权前经过 request body caching filter。1GiB heap 复测中，少量大型非表单请求体触发目标 JVM OOM。",
        "summary_en": "PowerJob paths such as `/container/downloadContainerTemplate` pass through a request-body caching filter before authentication. In the 1 GiB heap retest, a small number of large non-form request bodies triggered target JVM OOM.",
        "trigger_zh": "向 `/container/downloadContainerTemplate` 发送 `Content-Type` 非 form/multipart 的大 POST body。",
        "trigger_en": "Send large POST bodies with a non-form, non-multipart Content-Type to `/container/downloadContainerTemplate`.",
        "root_zh": "`CachingRequestBodyFilter` 在鉴权前把完整 body 复制到 String/StringBuilder/byte[]，普通 JSON/text/raw body 默认未被 multipart 限制约束。",
        "root_en": "`CachingRequestBodyFilter` copies the full body into String/StringBuilder/byte[] before authentication, while ordinary JSON/text/raw bodies are not constrained by multipart limits.",
        "conditions_zh": "入口匿名或预认证可达；非 multipart/form body 未被 server/proxy 限制。",
        "conditions_en": "The entry is anonymous or pre-auth reachable, and non-multipart/form bodies are not limited by the server or proxy.",
    },
    "RYVF-APP-STATIC-0001": {
        "title_zh": "RuoYi-Vue-Fast test user static map 可由低权限登录态触发 OOM",
        "title_en": "RuoYi-Vue-Fast test user static map can be exhausted by a low-privilege session",
        "summary_zh": "默认数据库初始化后进入低权限登录态，`/test/user/save` static map sink 可被重复请求填充。1GiB heap 复测中约 2.9k 次请求触发目标 JVM OOM。",
        "summary_en": "After default database initialization and entry into a low-privilege authenticated session, the `/test/user/save` static-map sink can be filled by repeated requests. In the 1 GiB heap retest, about 2.9k requests triggered target JVM OOM.",
        "trigger_zh": "使用低权限登录 token 重复 POST `/test/user/save`，提交带 padding 的请求体。",
        "trigger_en": "Use a low-privilege login token to repeatedly POST `/test/user/save` with padded request bodies.",
        "root_zh": "测试 user save 路径写入进程级 static map，缺少容量、TTL 或账号/IP 级限额。",
        "root_en": "The test user-save path writes to a process-level static map without capacity, TTL, or account/IP quotas.",
        "conditions_zh": "需要登录态；本地复测为稳定进入该路径关闭了默认验证码配置项，advisory 中应单独标注这一利用条件。",
        "conditions_en": "Requires an authenticated session; the local retest disabled the default captcha setting to reliably enter the path, and that condition should be disclosed separately.",
    },
    "SMQTT-APP-STATIC-0002": {
        "title_zh": "SMQTT retained MQTT messages map 可由匿名 retain publish 触发 OOM",
        "title_en": "SMQTT retained MQTT message map can be exhausted by anonymous retained publishes",
        "summary_zh": "SMQTT 默认匿名 MQTT 客户端可发送 retain=true 的 PUBLISH。不同 topic 的大 retained payload 会进入 `retainMessages` map；1GiB heap 复测中 260 条消息触发 OOM。",
        "summary_en": "SMQTT accepts anonymous MQTT clients by default. Large retained PUBLISH messages with distinct topics are stored in the `retainMessages` map; in the 1 GiB heap retest, 260 messages triggered OOM.",
        "trigger_zh": "连接默认 MQTT TCP 1883，发送 retain=true、topic 唯一、payload 较大的 PUBLISH。",
        "trigger_en": "Connect to the default MQTT TCP 1883 port and send retained PUBLISH messages with unique topics and large payloads.",
        "root_zh": "单条消息受 messageMaxSize 限制，但 retained topic 总数和总字节数无默认上限。",
        "root_en": "Individual messages are capped by messageMaxSize, but retained topic count and aggregate retained bytes have no default bound.",
        "conditions_zh": "匿名 publish 被允许；retained messages 功能启用；没有 retained count/bytes quota。",
        "conditions_en": "Anonymous publish is allowed, retained messages are enabled, and no retained count/byte quota is enforced.",
    },
    "SMQTT-APP-STATIC-0004": {
        "title_zh": "SMQTT offline persistent session queue 可触发 OOM",
        "title_en": "SMQTT offline persistent session queues can exhaust heap",
        "summary_zh": "SMQTT 持久 session 订阅者离线后，后续发布到订阅 topic 的消息会进入离线队列。1GiB heap 复测中，少量离线订阅者配合大 payload 发布触发 OOM。",
        "summary_en": "After an SMQTT persistent-session subscriber goes offline, later publishes to subscribed topics are queued for that offline session. In the 1 GiB heap retest, a small number of offline subscribers plus large payload publishes triggered OOM.",
        "trigger_zh": "创建 cleanSession=false 的订阅者并断开，再向其订阅 topic 发布大消息。",
        "trigger_en": "Create cleanSession=false subscribers, disconnect them, then publish large messages to their subscribed topics.",
        "root_zh": "离线 session queue 只受单消息大小约束，默认未观察到 per-session/global queue bytes/count 上限或 TTL。",
        "root_en": "Offline session queues are constrained only by per-message size; no default per-session/global queue byte/count limit or TTL was observed.",
        "conditions_zh": "匿名 MQTT subscribe/publish 可用；持久 session 保留；离线队列未配置容量边界。",
        "conditions_en": "Anonymous MQTT subscribe/publish is available, persistent sessions are retained, and offline queues are not bounded.",
    },
    "XXL-JOB-APP-STATIC-0002": {
        "title_zh": "XXL-JOB executor trigger 参数队列可用默认 token 触发 OOM",
        "title_en": "XXL-JOB executor trigger parameter queues can be exhausted with the default token",
        "summary_zh": "默认 executor 9999 端口和 `default_token` 场景下，攻击者可通过 `/trigger` 提交大量带大 executorParams 的任务触发 retained queue/线程状态增长。1GiB heap 复测中 1025 次触发导致 OOM。",
        "summary_en": "With the default executor port 9999 and `default_token`, an attacker can submit many `/trigger` requests with large executorParams, growing retained queues and thread state. In the 1 GiB heap retest, 1025 triggers caused OOM.",
        "trigger_zh": "向 executor `/trigger` POST 默认 token header，使用唯一 jobId 或重复触发并携带大 executorParams。",
        "trigger_en": "POST to executor `/trigger` with the default token header, using unique jobIds or repeated triggers with large executorParams.",
        "root_zh": "executor 任务线程/队列保留 executorParams，默认 active job/thread 和排队参数总字节缺少硬上限。",
        "root_en": "Executor job threads/queues retain executorParams, and default active job/thread count plus queued parameter bytes lack a hard bound.",
        "conditions_zh": "executor 9999 暴露；默认 access token 未修改或攻击者持有 token；无触发速率和参数大小限制。",
        "conditions_en": "Executor port 9999 is exposed, the default access token is unchanged or known, and trigger rate/parameter size are not limited.",
    },
    "CITRUS-APP-STATIC-0002": {
        "title_zh": "Citrus 匿名认证 JSON body buffering 可触发 JVM OOM",
        "title_en": "Citrus anonymous authentication JSON body buffering can trigger JVM OOM",
        "summary_zh": "Citrus `/rest/authenticate` 匿名认证路径会缓冲/解析请求体。1GiB heap 复测中，约 20MiB JSON body 的并发/重复提交触发目标 JVM OOM。",
        "summary_en": "The Citrus anonymous `/rest/authenticate` path buffers/parses request bodies. In the 1 GiB heap retest, repeated or concurrent submissions of roughly 20 MiB JSON bodies triggered target JVM OOM.",
        "trigger_zh": "向 `/rest/authenticate` 发送大 JSON body，保持普通匿名认证请求形态。",
        "trigger_en": "Send large JSON bodies to `/rest/authenticate` in the ordinary anonymous authentication request shape.",
        "root_zh": "认证入口在拒绝前完整物化请求体和 JSON 结构，默认未对普通 JSON body 设置足够低的上限。",
        "root_en": "The authentication entry materializes the full request body and JSON structure before rejection, without a sufficiently low default cap for ordinary JSON bodies.",
        "conditions_zh": "匿名认证入口暴露；普通 JSON body 未被 server/proxy 体积限制拦截。",
        "conditions_en": "The anonymous authentication entry is exposed, and ordinary JSON bodies are not rejected by server/proxy size limits.",
    },
    "ERUPT-APP-STATIC-0001": {
        "title_zh": "Erupt captcha height 参数可驱动 BufferedImage 大对象 OOM",
        "title_en": "Erupt captcha height parameter can drive BufferedImage allocation OOM",
        "summary_zh": "Erupt sample 默认 H2 启动下，匿名 `/erupt-api/code-img` 接口的 height 参数可直接影响验证码图片高度。1GiB heap 复测中，极大 height 值触发 `BufferedImage` 分配并 OOM。",
        "summary_en": "In the Erupt sample default H2 deployment, the anonymous `/erupt-api/code-img` endpoint lets the `height` parameter directly affect captcha image height. In the 1 GiB heap retest, very large height values triggered `BufferedImage` allocation and OOM.",
        "trigger_zh": "GET `/erupt-api/code-img?mark=<x>&height=<large>`，逐步增大 height。",
        "trigger_en": "GET `/erupt-api/code-img?mark=<x>&height=<large>` while increasing height.",
        "root_zh": "height 未被限制在正常验证码范围内，传入 `new SpecCaptcha(150, height, 4)` 后创建巨大 `BufferedImage`。",
        "root_en": "The height value is not constrained to a normal captcha range and is passed to `new SpecCaptcha(150, height, 4)`, leading to huge `BufferedImage` allocation.",
        "conditions_zh": "匿名 captcha endpoint 暴露；未对 height/总像素数做上限校验。",
        "conditions_en": "The anonymous captcha endpoint is exposed and does not cap height or total pixels.",
    },
    "ERUPT-APP-STATIC-0002": {
        "title_zh": "Erupt operation-log filter 在鉴权前复制 JSON body 导致 OOM",
        "title_en": "Erupt operation-log filter copies JSON bodies before auth and can exhaust heap",
        "summary_zh": "匿名 POST `/erupt-api/data/table/EruptUser` 时，operation-log filter 会在权限拒绝前复制 JSON body。1GiB heap 复测中，约 36MiB body 的重复请求触发 Java heap OOM。",
        "summary_en": "On anonymous POST `/erupt-api/data/table/EruptUser`, the operation-log filter copies the JSON body before authorization rejection. In the 1 GiB heap retest, repeated roughly 36 MiB bodies triggered Java heap OOM.",
        "trigger_zh": "向 `/erupt-api/data/table/EruptUser` POST 大 JSON body，即使最终返回 401，也会先经过 body wrapper。",
        "trigger_en": "POST a large JSON body to `/erupt-api/data/table/EruptUser`; even if the final response is 401, the body wrapper runs first.",
        "root_zh": "`EruptRequestWrapper` 在 filter 中读取完整 JSON body，并保留 String/byte[] 多份副本，默认无 body 记录长度上限。",
        "root_en": "`EruptRequestWrapper` reads the full JSON body in the filter and retains multiple String/byte[] copies without a default recorded-body length cap.",
        "conditions_zh": "匿名 `/erupt-api/*` JSON path 可达；operation-log filter 启用；未由网关限制 body。",
        "conditions_en": "An anonymous `/erupt-api/*` JSON path is reachable, the operation-log filter is enabled, and no gateway body limit blocks the request.",
    },
    "JMQTT-APP-STATIC-0002": {
        "title_zh": "JMQTT QoS2 半握手保留消息可触发 OOM",
        "title_en": "JMQTT QoS2 half-handshake retained messages can trigger OOM",
        "summary_zh": "JMQTT 默认匿名 MQTT 客户端可发送 QoS2 PUBLISH。攻击者选择不同 packetId，收到 PUBREC 后不发送 PUBREL 并用 PINGREQ 保活，可保留 DeviceMessage。1GiB heap 复测中 2030 条触发 OOM。",
        "summary_en": "JMQTT accepts anonymous MQTT clients by default. An attacker can send QoS2 PUBLISH packets with distinct packetIds, omit PUBREL after PUBREC, and keep the connection alive with PINGREQ, retaining DeviceMessage objects. In the 1 GiB heap retest, 2030 messages triggered OOM.",
        "trigger_zh": "默认 MQTT TCP/WebSocket 上发送 payload 接近默认 maxMsgSize 的 QoS2 PUBLISH，保持半开放 QoS2 状态。",
        "trigger_en": "Send QoS2 PUBLISH packets with payload near the default maxMsgSize over the default MQTT TCP/WebSocket surface and keep QoS2 state half-open.",
        "root_zh": "`MqttSession.qos2Receiving` 保留 packetId 到 DeviceMessage 的映射，缺少 inflight count/bytes quota 和超时清理。",
        "root_en": "`MqttSession.qos2Receiving` retains packetId-to-DeviceMessage entries without an in-flight count/byte quota or timeout cleanup.",
        "conditions_zh": "匿名 MQTT 连接可用；QoS2 启用；连接可通过 keepalive 维持。",
        "conditions_en": "Anonymous MQTT connections are allowed, QoS2 is enabled, and the connection can be kept alive.",
    },
    "REBUILD-APP-STATIC-0002": {
        "title_zh": "Rebuild 匿名 barcode render 文本长度可触发图片渲染 OOM",
        "title_en": "Rebuild anonymous barcode rendering can exhaust heap through text length",
        "summary_zh": "Rebuild 匿名 `/commons/barcode/render` 会根据请求文本渲染 Code128 barcode。1GiB heap 复测中，较长文本触发图片/编码渲染大对象分配并 OOM。",
        "summary_en": "Rebuild anonymous `/commons/barcode/render` renders a Code128 barcode from request text. In the 1 GiB heap retest, long text values triggered large image/encoding allocations and OOM.",
        "trigger_zh": "GET 或 POST `/commons/barcode/render`，传入逐步增大的文本参数。",
        "trigger_en": "GET or POST `/commons/barcode/render` with progressively larger text parameters.",
        "root_zh": "barcode 渲染前未对文本长度、输出像素或编码复杂度设置足够低的默认上限。",
        "root_en": "Barcode rendering lacks a sufficiently low default bound on text length, output pixels, or encoding complexity before allocation.",
        "conditions_zh": "匿名 barcode endpoint 暴露；请求行/header 限制仍允许达到触发阈值。",
        "conditions_en": "The anonymous barcode endpoint is exposed, and request-line/header limits still permit the triggering length.",
    },
    "REBUILD-APP-STATIC-0003": {
        "title_zh": "Rebuild API gateway 在签名校验前解析大 JSON body 导致 OOM",
        "title_en": "Rebuild API gateway parses large JSON bodies before signature verification",
        "summary_zh": "Rebuild 匿名 `/gw/api/system-time?appid=bad&sign=bad` 会在签名拒绝前读取并解析 raw JSON body。1GiB heap 复测中，约 24MiB body 的重复请求触发 OOM。",
        "summary_en": "Rebuild anonymous `/gw/api/system-time?appid=bad&sign=bad` reads and parses the raw JSON body before signature rejection. In the 1 GiB heap retest, repeated roughly 24 MiB bodies triggered OOM.",
        "trigger_zh": "向存在的 `/gw/api/system-time` API 名称 POST 大 JSON body，appid/sign 使用无效值。",
        "trigger_en": "POST a large JSON body to an existing `/gw/api/system-time` API name with invalid appid/sign values.",
        "root_zh": "`ApiGateway.buildBaseApiContext` 在验证 appid/sign 之前调用 `ServletUtils.getRequestString` 和 `JSON.parse`。",
        "root_en": "`ApiGateway.buildBaseApiContext` calls `ServletUtils.getRequestString` and `JSON.parse` before verifying appid/sign.",
        "conditions_zh": "匿名 API gateway path 暴露；API 名称存在；未由 body limit 或 JSON limit 拦截。",
        "conditions_en": "The anonymous API gateway path is exposed, the API name exists, and no body or JSON limit blocks the request.",
    },
    "SMQTT-APP-STATIC-0003": {
        "title_zh": "SMQTT 长 topic 订阅索引可由匿名订阅触发 OOM",
        "title_en": "SMQTT long-topic subscription index can be exhausted by anonymous subscribes",
        "summary_zh": "SMQTT 默认匿名订阅路径可接收大量唯一或超长 topic filter。1GiB heap 复测中，约 127k 次请求触发目标 JVM OOM。",
        "summary_en": "SMQTT's default anonymous subscribe path accepts many unique or long topic filters. In the 1 GiB heap retest, about 127k requests triggered target JVM OOM.",
        "trigger_zh": "通过 MQTT SUBSCRIBE 创建大量唯一/长 topic filter，持续增长 broker 订阅索引。",
        "trigger_en": "Use MQTT SUBSCRIBE to create many unique or long topic filters, continuously growing broker subscription indexes.",
        "root_zh": "订阅 topic 索引的 key/节点数量缺少默认全局、per-client 或 per-IP 容量上限。",
        "root_en": "Subscription topic-index keys/nodes lack default global, per-client, or per-IP capacity limits.",
        "conditions_zh": "匿名 subscribe 允许；订阅索引未配置总量限制；连接/速率未被外部限制。",
        "conditions_en": "Anonymous subscribe is allowed, subscription indexes are not globally bounded, and connection/rate is not externally limited.",
    },
    "SMQTT-APP-STATIC-0006": {
        "title_zh": "SMQTT QoS2 半握手缓存 publish payload 可触发 OOM",
        "title_en": "SMQTT QoS2 half-handshake publish cache can exhaust heap",
        "summary_zh": "SMQTT QoS2 PUBLISH 路径会在收到 PUBREL 前缓存 publish payload 和 retry ack 状态。1GiB heap 复测中，5 条连接、payload 约 1MiB 的半握手消息触发 OOM。",
        "summary_en": "SMQTT's QoS2 PUBLISH path caches publish payloads and retry-ack state until PUBREL is received. In the 1 GiB heap retest, half-handshake messages across five connections with roughly 1 MiB payloads triggered OOM.",
        "trigger_zh": "发送不同 packetId 的 QoS2 PUBLISH 后省略 PUBREL，用 PINGREQ 保持连接。",
        "trigger_en": "Send QoS2 PUBLISH packets with distinct packetIds, omit PUBREL, and keep connections alive with PINGREQ.",
        "root_zh": "`MqttChannel.qos2MsgCache` 与 `TimeAckManager.ackMap` 缺少 per-connection inflight bytes/count 和超时释放。",
        "root_en": "`MqttChannel.qos2MsgCache` and `TimeAckManager.ackMap` lack per-connection in-flight byte/count limits and timeout-based release.",
        "conditions_zh": "匿名 QoS2 publish 允许；半开放 QoS2 状态可保留；未设置 inflight quota。",
        "conditions_en": "Anonymous QoS2 publish is allowed, half-open QoS2 state is retained, and no in-flight quota is enforced.",
    },
    "WGCLOUD-APP-STATIC-0002": {
        "title_zh": "WGCloud 默认 agent token minTask 大数组可触发静态列表 OOM",
        "title_en": "WGCloud default agent-token minTask arrays can exhaust static lists",
        "summary_zh": "完整 WGCloud server + MySQL 默认 token 环境中，`POST /wgcloud/agent/minTask` 可提交大数组并压迫 BatchData 静态列表。1GiB heap 复测中 175 次请求触发 OOM。",
        "summary_en": "In a full WGCloud server plus MySQL default-token environment, `POST /wgcloud/agent/minTask` accepts large arrays that pressure BatchData static lists. In the 1 GiB heap retest, 175 requests triggered OOM.",
        "trigger_zh": "使用默认 agent token 向 `/wgcloud/agent/minTask` POST 大数组 payload。",
        "trigger_en": "Use the default agent token to POST large array payloads to `/wgcloud/agent/minTask`.",
        "root_zh": "agent 上报数据进入进程级批处理静态列表，默认缺少 body、数组元素数、队列长度或 per-agent 配额。",
        "root_en": "Agent report data enters process-level batch static lists without default body, array-element, queue-length, or per-agent quotas.",
        "conditions_zh": "server agent endpoint 暴露；默认 token 未修改或被低信任方获得；未限制数组/body 大小。",
        "conditions_en": "The server agent endpoint is exposed, the default token is unchanged or known to a low-trust party, and array/body sizes are not limited.",
    },
    "XXL-JOB-APP-STATIC-0003": {
        "title_zh": "XXL-JOB GLUE_GROOVY 唯一 jobId 可造成线程耗尽",
        "title_en": "XXL-JOB GLUE_GROOVY unique jobIds can exhaust native threads",
        "summary_zh": "XXL-JOB default-token GLUE_GROOVY 路径使用唯一 jobId 与阻塞型 glueSource 创建大量 JobThread。1GiB heap 复测中 780 次触发导致 native thread exhaustion/可用性失败，作为确认资源耗尽真阳性。",
        "summary_en": "The XXL-JOB default-token GLUE_GROOVY path can create many JobThread instances by using unique jobIds and a blocking glueSource. In the 1 GiB heap retest, 780 triggers caused native thread exhaustion / availability failure and were confirmed as resource-exhaustion true positive.",
        "trigger_zh": "向 executor `/trigger` 发送默认 token，glueType=GLUE_GROOVY，使用唯一 jobId 和阻塞 glueSource。",
        "trigger_en": "POST to executor `/trigger` with the default token, glueType=GLUE_GROOVY, unique jobIds, and a blocking glueSource.",
        "root_zh": "`jobThreadRepository` 按 jobId 创建并保留 JobThread，默认无 active JobThread 上限，阻塞任务可快速耗尽 native threads。",
        "root_en": "`jobThreadRepository` creates and retains JobThread instances keyed by jobId; no default active JobThread cap prevents blocking tasks from exhausting native threads.",
        "conditions_zh": "executor 9999 暴露；默认 token 可用；GLUE_GROOVY 执行路径可达；未限制 jobId/thread 数。",
        "conditions_en": "Executor port 9999 is exposed, the default token is usable, the GLUE_GROOVY path is reachable, and jobId/thread counts are not limited.",
    },
    "XXL-JOB-APP-STATIC-0004": {
        "title_zh": "XXL-JOB /trigger 大 payload 可触发 executor JVM OOM",
        "title_en": "XXL-JOB /trigger large payloads can trigger executor JVM OOM",
        "summary_zh": "XXL-JOB executor `/trigger` 默认 token 路径可接收较大 payload。1GiB heap 复测中，约 4MiB payload 的 199 次请求触发目标 JVM OOM。",
        "summary_en": "The XXL-JOB executor `/trigger` path protected only by the default token accepts large payloads. In the 1 GiB heap retest, 199 requests with roughly 4 MiB payloads triggered target JVM OOM.",
        "trigger_zh": "向 `/trigger` POST 默认 token header，提交带大参数字段的 TriggerRequest。",
        "trigger_en": "POST a TriggerRequest with large parameter fields to `/trigger` using the default token header.",
        "root_zh": "trigger 请求参数在调度和执行队列中被保留，默认未限制单请求参数大小、排队总量或 per-token 速率。",
        "root_en": "Trigger request parameters are retained in scheduling/execution queues without default limits on per-request parameter size, queued aggregate bytes, or per-token rate.",
        "conditions_zh": "executor endpoint 暴露；默认 token 未修改或攻击者持有；无 body/参数大小和触发速率限制。",
        "conditions_en": "The executor endpoint is exposed, the default token is unchanged or known, and body/parameter size plus trigger rate are not limited.",
    },
}


STRICT_REPRO_COMMANDS: dict[str, list[str]] = {
    "apache__druid-DRUID-APP-STATIC-0001": [
        "cd results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0001",
        "docker compose -p druiddos_apache_druid up -d",
        "./probe.py --max-size 536870912 --size-steps 1048576,8388608,33554432,67108864,134217728,268435456,536870912 --content-types text/plain --concurrency 1 --timeout 360 --chunk-size 1048576 --stop-on-failure",
        "docker compose -p druiddos_apache_druid down -v",
    ],
    "apache__druid-DRUID-APP-STATIC-0002": [
        "cd results/applications_dynamic_validation/new/cases/apache__druid-DRUID-APP-STATIC-0002",
        "docker compose -p druid_avatica_case_1g -f docker-compose.yml up -d postgres zookeeper coordinator broker router",
        "python3 probe.py --case-dir \"$PWD\" --compose-project druid_avatica_case_1g --compose-file \"$PWD/docker-compose.yml\" --wait-only --ready-timeout 300",
        "python3 probe.py --case-dir \"$PWD\" --compose-project druid_avatica_case_1g --compose-file \"$PWD/docker-compose.yml\" --sizes 134217728,268435456,536870912,805306368 --request-timeout 300 --ready-timeout 60",
        "docker compose -p druid_avatica_case_1g -f docker-compose.yml down -v",
    ],
    "apache__hertzbeat-HERTZBEAT-DOS-0001": [
        "cd results/applications_dynamic_validation/new/cases/apache__hertzbeat-HERTZBEAT-DOS-0001",
        "docker run -d --name hbdos0001-hertzbeat --memory 2g --memory-swap 2g -e JAVA_OPTS=\"-Xms1g -Xmx1g -XX:MaxDirectMemorySize=1g --add-opens=java.base/java.nio=org.apache.arrow.memory.core,ALL-UNNAMED\" -p 2157:1157 -p 2158:1158 docker.m.daocloud.io/apache/hertzbeat:1.8.0",
        "./probe.py --count 30000 --start-index 1 --sample-every 250 --timeout 5 --concurrency 8 --case-dir .",
        "docker rm -f hbdos0001-hertzbeat",
    ],
    "apache__skywalking-SKYWALKING-APP-STATIC-0002": [
        "cd results/applications_dynamic_validation/new/cases/apache__skywalking-SKYWALKING-APP-STATIC-0002",
        "docker compose -p sw-pprof-case up -d",
        "python3 probe.py --streams 48 --content-size 31457280 --hold-seconds 35 --stagger-seconds 0.05 --sample-interval 0.5 --out logs/probe-failure-1g-48stream-30m.json",
        "docker compose -p sw-pprof-case down -v",
    ],
    "apache__solr-SOLR-APP-STATIC-0001": [
        "cd results/applications_dynamic_validation/new/cases/apache__solr-SOLR-APP-STATIC-0001",
        "docker run -d --name dos-solr-form-apache-solr-static-0001-1g --memory=2g --memory-swap=2g -e SOLR_HEAP=1g -p 127.0.0.1:28983:8983 solr:9.8.1 solr-precreate doscore",
        "python3 probe.py --case-dir \"$PWD\" --container dos-solr-form-apache-solr-static-0001-1g --base-url http://127.0.0.1:28983/solr --core doscore --sizes 134217728,268435456,536870912,805306368 --request-timeout 300 --ready-timeout 60",
        "docker rm -f -v dos-solr-form-apache-solr-static-0001-1g",
    ],
    "prestodb__presto-PRESTO-APP-STATIC-0001": [
        "cd results/applications_dynamic_validation/new/cases/prestodb__presto-PRESTO-APP-STATIC-0001",
        "docker run -d --name dos-presto-prestodb-presto-static-0001 --memory=2g --memory-swap=2g -p 127.0.0.1:18080:8080 prestodb/presto:0.298.1",
        "curl -fsS http://127.0.0.1:18080/v1/info",
        "./probe.py",
        "docker rm -f -v dos-presto-prestodb-presto-static-0001",
    ],
    "thingsboard__thingsboard-TB-APP-STATIC-0001": [
        "cd results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0001",
        "docker compose -p tb-dos-thingsboard-static-0001 up -d postgres",
        "docker compose -p tb-dos-thingsboard-static-0001 run --rm -e INSTALL_TB=true -e LOAD_DEMO=false -e JAVA_OPTS='-Xms512m -Xmx1024m -Xss384k' tb-node",
        "docker compose -p tb-dos-thingsboard-static-0001 up -d tb-node",
        "./probe.py --token <token-shaped-path-segment> --endpoint telemetry --payload-mode timeseries-large-value --sizes-mib 256,512 --timeout 240 --chunk-bytes 65536 --out logs/probe_results_reinforce_telemetry_large.jsonl",
        "docker compose -p tb-dos-thingsboard-static-0001 down -v",
    ],
    "thingsboard__thingsboard-TB-APP-STATIC-0002": [
        "cd results/applications_dynamic_validation/new/cases/thingsboard__thingsboard-TB-APP-STATIC-0002",
        "docker run -d --name tb-dos-thingsboard-static-0002 --memory=4096m --memory-swap=4096m -e JAVA_OPTS='-Xms512m -Xmx1536m -XX:+ExitOnOutOfMemoryError' -p 127.0.0.1:19090:9090 -v \"$PWD/data:/data\" -v \"$PWD/container-logs:/var/log/thingsboard\" thingsboard/tb-postgres:latest",
        "./probe.py --endpoint attributes --sizes-mib 17,64,128,256 --control-mib 17 --value-len 8192",
        "docker rm -f -v tb-dos-thingsboard-static-0002",
    ],
    "dependencytrack__dependency-track-DTRACK-APP-STATIC-0001": [
        "cd results/applications_dynamic_validation/new_retest/cases/dependencytrack__dependency-track-DTRACK-APP-STATIC-0001",
        "docker compose -p codex_dtrack_dos_retest_0001 -f docker-compose.yml up -d",
        "DTRACK_COMPOSE_PROJECT=codex_dtrack_dos_retest_0001 DTRACK_APISERVER_CONTAINER=codex_dtrack_dos_retest_0001-apiserver-1 DTRACK_PUT_DECODED_MIB= DTRACK_POST_PART_MIB=768 DTRACK_REQUEST_TIMEOUT=900 ./probe.py",
        "docker compose -p codex_dtrack_dos_retest_0001 -f docker-compose.yml down -v --remove-orphans",
    ],
    "openzipkin__zipkin-ZIPKIN-APP-STATIC-0001": [
        "cd results/applications_dynamic_validation/new_retest/cases/openzipkin__zipkin-ZIPKIN-APP-STATIC-0001",
        "docker run --name dosval-openzipkin-zipkin-static-0001-1g -d --memory=2g --memory-swap=2g -e JAVA_OPTS='-Xms256m -Xmx1g -XX:+ExitOnOutOfMemoryError' -p 127.0.0.1:29411:9411 docker.m.daocloud.io/openzipkin/zipkin-slim:latest",
        "python3 probe.py --base-url http://127.0.0.1:29411 --container dosval-openzipkin-zipkin-static-0001-1g --out logs/probe_results_1g_confirmed.jsonl --metrics-out evidence/metrics_snapshots_1g_confirmed.txt --mode plain --pause 1 --extra-gzip 160000:8192",
        "docker rm -f dosval-openzipkin-zipkin-static-0001-1g",
    ],
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "case"


def rel(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT))
    except (ValueError, FileNotFoundError):
        return str(path)


def source_file_path(record: dict[str, Any]) -> Path | None:
    source_file = record.get("source_file")
    if not source_file or source_file.endswith("findings.jsonl"):
        return None
    return ROOT / "results/applications_dynamic_validation" / source_file


def load_result(record: dict[str, Any]) -> tuple[dict[str, Any] | None, Path | None]:
    path = source_file_path(record)
    if path and path.exists():
        return read_json(path), path.parent
    return None, None


def load_dynamic_finding(record: dict[str, Any]) -> dict[str, Any] | None:
    batch = record.get("source_batch")
    if batch not in {"p0", "p1", "p2"}:
        return None
    path = ROOT / f"results/applications_dynamic_validation/{batch}/findings.jsonl"
    for item in read_jsonl(path):
        if item.get("candidate_id") == record.get("record_id"):
            return item
    return None


def load_static_finding(record: dict[str, Any]) -> dict[str, Any] | None:
    app = str(record.get("app") or "")
    if "/" in app:
        return None
    path = ROOT / "results/applications_static_analysis" / app / "findings.jsonl"
    for item in read_jsonl(path):
        if item.get("finding_id") == record.get("record_id") or item.get("candidate_id") == record.get("record_id"):
            return item
    return None


def get_text(record_id: str) -> dict[str, str]:
    default = {
        "title_zh": f"{record_id} 资源耗尽 DoS",
        "title_en": f"{record_id} resource-exhaustion denial of service",
        "summary_zh": "该二值真相记录已在 1GiB 或以上目标 JVM/容器内存口径下确认外部请求可触发目标资源失败。",
        "summary_en": "This binary-truth record confirms that external requests can trigger target resource failure with at least a 1 GiB target JVM heap or equivalent memory evidence.",
        "trigger_zh": "参考动态验证记录中的 request_shape 或原始 harness。",
        "trigger_en": "See the dynamic validation record request_shape or original harness.",
        "root_zh": "参考静态 traceability 的 source/sink/driver 字段。",
        "root_en": "See the static traceability source/sink/driver fields.",
        "conditions_zh": "仅在授权、本地、隔离环境中复现。",
        "conditions_en": "Reproduce only in an authorized, local, isolated environment.",
    }
    default.update(CASE_TEXT.get(record_id, {}))
    return default


def infer_entry(record: dict[str, Any], result: dict[str, Any] | None, dynamic: dict[str, Any] | None) -> str:
    if record.get("entry"):
        return str(record["entry"])
    if result:
        reachability = result.get("reachability") or {}
        if reachability.get("entry"):
            return str(reachability["entry"])
    if dynamic:
        evidence = dynamic.get("evidence") or {}
        endpoint = evidence.get("endpoint")
        port = evidence.get("port")
        if endpoint:
            return str(endpoint)
        if port:
            return f"protocol service on port {port}"
    return "See reproduction section"


def auth_label(record: dict[str, Any], result: dict[str, Any] | None) -> tuple[str, str, str]:
    if result:
        reach = result.get("reachability") or {}
        if reach.get("attacker_model") == "low_privilege" or reach.get("auth_required"):
            roles = ", ".join(reach.get("required_roles") or [])
            extra = f"; roles: {roles}" if roles else ""
            return "低权限账号或默认 token/API key", "low-privilege account or default token/API key", "PR:L"
        if reach.get("attacker_model") == "anonymous":
            return "匿名", "anonymous", "PR:N"
    text = " ".join(str(record.get(k) or "") for k in ("reason", "entry", "app", "record_id"))
    if any(marker in text for marker in ("登录", "低权限", "TENANT_ADMIN", "BOM_UPLOAD", "default token", "token")):
        return "低权限账号或默认 token/API key", "low-privilege account or default token/API key", "PR:L"
    return "匿名或默认开放协议客户端", "anonymous or default-open protocol client", "PR:N"


def trace_fields(result: dict[str, Any] | None, static: dict[str, Any] | None) -> dict[str, Any]:
    if result and result.get("static_traceability"):
        return result["static_traceability"]
    if static:
        return {
            "source": static.get("source") or static.get("entry"),
            "sink": static.get("sink"),
            "driver": static.get("driver") or static.get("static_trigger_shape"),
            "bound": static.get("bound"),
            "evidence": static.get("evidence"),
        }
    return {}


def evidence_object(record: dict[str, Any], result: dict[str, Any] | None, dynamic: dict[str, Any] | None) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "record_id": record.get("record_id"),
        "app": record.get("app"),
        "source_batch": record.get("source_batch"),
        "status": record.get("status"),
        "failure_signal": record.get("failure_signal"),
        "heap_or_limit": record.get("heap_or_limit"),
        "requests_sent": record.get("requests_sent"),
        "strict_1g_evidence": record.get("strict_1g_evidence"),
        "log_path": record.get("log_path"),
        "evidence_summary": record.get("evidence_summary"),
    }
    if result:
        obj["resource_observation"] = result.get("resource_observation")
        obj["utilization_conditions"] = result.get("utilization_conditions")
        obj["default_deployment"] = result.get("default_deployment")
        obj["trigger"] = result.get("trigger")
    if dynamic:
        obj["dynamic_finding"] = dynamic
    return obj


def reproduction_commands(record: dict[str, Any], result: dict[str, Any] | None) -> list[str]:
    batch = record.get("source_batch")
    record_id = str(record.get("record_id"))
    if record_id in STRICT_REPRO_COMMANDS:
        return STRICT_REPRO_COMMANDS[record_id]
    if batch == "p0":
        return [f"python3 scripts/run_application_p0_dynamic_validation.py --case {record_id} --min-heap 1g"]
    if batch == "p1":
        return [f"python3 scripts/run_application_p1_dynamic_validation.py --case {record_id} --min-heap 1g"]
    if batch == "p2":
        return [f"python3 scripts/run_application_p2_dynamic_validation.py --case {record_id} --min-heap 1g --runnable-only"]
    if result:
        default_deployment = result.get("default_deployment") or {}
        commands = default_deployment.get("commands") or []
        if commands:
            case_dir = source_file_path(record)
            prefix: list[str] = []
            if case_dir:
                prefix.append(f"cd {case_dir.parent}")
            return prefix + [str(command) for command in commands]
    return ["See the original dynamic validation case and attached evidence."]


def copy_attachment(src: Path, dst: Path, attachments: list[tuple[str, str]]) -> None:
    if not src.exists() or not src.is_file():
        attachments.append((rel(src), "missing; referenced only"))
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    attachments.append((rel(dst), f"copied from {rel(src)}"))


def copy_log_attachment(record: dict[str, Any], case_dir: Path | None, attachment_dir: Path, attachments: list[tuple[str, str]]) -> None:
    log_path = record.get("log_path")
    if not log_path:
        return
    candidates: list[Path] = []
    raw = Path(str(log_path))
    if raw.is_absolute():
        candidates.append(raw)
    else:
        if case_dir:
            candidates.append(case_dir / raw)
        candidates.append(ROOT / raw)
    src = next((p for p in candidates if p.exists() and p.is_file()), None)
    if not src:
        attachments.append((str(log_path), "log path referenced by truth record; file not found during generation"))
        return
    size = src.stat().st_size
    if size > MAX_ATTACHED_LOG_BYTES:
        attachments.append((rel(src), f"not copied; log is {size} bytes, above {MAX_ATTACHED_LOG_BYTES} byte attachment threshold"))
        return
    dst = attachment_dir / f"{sanitize_filename(str(record.get('record_id')))}.log.gz"
    if src.suffix == ".gz":
        shutil.copy2(src, dst)
    else:
        with src.open("rb") as in_fh, gzip.open(dst, "wb", compresslevel=9) as out_fh:
            shutil.copyfileobj(in_fh, out_fh)
    attachments.append((rel(dst), f"gzip copy of {rel(src)}"))


def markdown_table(rows: list[tuple[str, str]]) -> str:
    lines = ["| Field | Value |", "| --- | --- |"]
    for key, value in rows:
        safe_value = str(value).replace("\n", "<br>")
        lines.append(f"| {key} | {safe_value} |")
    return "\n".join(lines)


def code_block(lines: list[str], lang: str = "bash") -> str:
    body = "\n".join(lines) if lines else "See attached evidence."
    return f"```{lang}\n{body}\n```"


def bullets(items: list[str]) -> str:
    values = [str(item) for item in items if item]
    if not values:
        return "- None recorded."
    return "\n".join(f"- {item}" for item in values)


def normalize_limits(record_id: str, limits: list[str]) -> list[str]:
    if record_id == "apache__solr-SOLR-APP-STATIC-0001":
        filtered = [item for item in limits if "768MiB" not in item and "768m" not in item.lower()]
        filtered.append(
            "Strict binary-truth reproduction used SOLR_HEAP=1g and Docker memory/swap limits of 2g; "
            "the confirmed signal is Java heap OOM, not Docker OOMKilled."
        )
        return filtered
    return limits


def advisory_zh(
    record: dict[str, Any],
    result: dict[str, Any] | None,
    dynamic: dict[str, Any] | None,
    static: dict[str, Any] | None,
    attachment_rows: list[tuple[str, str]],
) -> str:
    record_id = str(record["record_id"])
    text = get_text(record_id)
    entry = infer_entry(record, result, dynamic)
    auth_zh, _auth_en, pr = auth_label(record, result)
    cvss = f"CVSS:3.1/AV:N/AC:L/{pr}/UI:N/S:U/C:N/I:N/A:H"
    trace = trace_fields(result, static)
    commands = reproduction_commands(record, result)
    limits = []
    not_affected = []
    if result:
        cond = result.get("utilization_conditions") or {}
        limits = [str(x) for x in cond.get("limits_or_mitigations") or []]
        not_affected = [str(x) for x in cond.get("not_affected_when") or []]
    limits = normalize_limits(record_id, limits)
    return f"""
# Security Advisory PoC：{text["title_zh"]}

## 摘要

{text["summary_zh"]}

## 影响对象

{markdown_table([
    ("项目", f"`{record.get('app')}`"),
    ("本地真阳性 ID", f"`{record_id}`"),
    ("动态批次", f"`{record.get('source_batch')}`"),
    ("动态状态", f"`{record.get('status')}`"),
    ("入口", f"`{entry}`"),
    ("权限前置", auth_zh),
    ("建议 CVSS 3.1", f"`{cvss}`"),
])}

## 技术细节

- 触发方式：{text["trigger_zh"]}
- 根因摘要：{text["root_zh"]}
- 利用条件：{text["conditions_zh"]}
- 静态 source：`{trace.get("source", "见附件 source_record.json")}`
- 静态 sink：`{trace.get("sink", "见附件 source_record.json")}`
- 攻击者驱动变量：`{trace.get("driver", "见附件 source_record.json")}`

## 受控 PoC

只在本机、授权、一次性测试环境中运行。不要把这些命令或脚本指向公网、第三方服务或生产系统。建议先阅读附件中的原始动态结果，再执行复测。

从仓库根目录运行：

{code_block(commands)}

如果只需要提交 advisory，可引用本目录的 `attachments/source_record.json`、`attachments/evidence.json` 和 `attachments/ATTACHMENTS.md`，无需公开原始大 payload 或完整日志。

## 动态证据

{markdown_table([
    ("失败信号", f"`{record.get('failure_signal')}`"),
    ("堆/内存口径", f"`{record.get('heap_or_limit')}`"),
    ("请求数", f"`{record.get('requests_sent')}`"),
    ("1GiB 严格证据", f"`{record.get('strict_1g_evidence')}`"),
    ("原始日志路径", f"`{record.get('log_path')}`"),
])}

证据摘要：

```text
{record.get('reason') or record.get('evidence_summary') or 'See attachments.'}
```

## 修复建议

- 在入口处增加请求体大小、对象数量、topic/job/key cardinality、队列长度或线程数量硬上限。
- 在昂贵的 body 读取、解压、JSON/protobuf 解析、图片渲染、任务创建或状态保留前完成认证和配额检查。
- 对匿名或低权限入口增加 per-IP、per-user、per-token、per-client 的速率和资源配额。
- 超限时尽早返回 400/413/429，并避免保留完整请求体、payload 或未完成协议状态。

已记录的限制/缓解因素：

{bullets(limits)}

不受影响或风险显著降低的情况：

{bullets(not_affected)}

## 附件

{markdown_table(attachment_rows)}

## 披露备注

建议通过项目 security advisory、私有 issue 或安全邮箱先行披露。公开前不建议附带完整大 payload、自动化压测脚本或可直接攻击非授权目标的命令。
"""


def advisory_en(
    record: dict[str, Any],
    result: dict[str, Any] | None,
    dynamic: dict[str, Any] | None,
    static: dict[str, Any] | None,
    attachment_rows: list[tuple[str, str]],
) -> str:
    record_id = str(record["record_id"])
    text = get_text(record_id)
    entry = infer_entry(record, result, dynamic)
    _auth_zh, auth_en, pr = auth_label(record, result)
    cvss = f"CVSS:3.1/AV:N/AC:L/{pr}/UI:N/S:U/C:N/I:N/A:H"
    trace = trace_fields(result, static)
    commands = reproduction_commands(record, result)
    limits = []
    not_affected = []
    if result:
        cond = result.get("utilization_conditions") or {}
        limits = [str(x) for x in cond.get("limits_or_mitigations") or []]
        not_affected = [str(x) for x in cond.get("not_affected_when") or []]
    limits = normalize_limits(record_id, limits)
    return f"""
# Security Advisory PoC: {text["title_en"]}

## Summary

{text["summary_en"]}

## Affected Project

{markdown_table([
    ("Project", f"`{record.get('app')}`"),
    ("Local true-positive ID", f"`{record_id}`"),
    ("Dynamic batch", f"`{record.get('source_batch')}`"),
    ("Dynamic status", f"`{record.get('status')}`"),
    ("Entry", f"`{entry}`"),
    ("Required privilege", auth_en),
    ("Suggested CVSS 3.1", f"`{cvss}`"),
])}

## Technical Details

- Trigger shape: {text["trigger_en"]}
- Root cause summary: {text["root_en"]}
- Exploitation conditions: {text["conditions_en"]}
- Static source: `{trace.get("source", "see attachments/source_record.json")}`
- Static sink: `{trace.get("sink", "see attachments/source_record.json")}`
- Attacker-controlled driver: `{trace.get("driver", "see attachments/source_record.json")}`

## Controlled PoC

Run this only in a local, authorized, disposable test environment. Do not point these commands or scripts at public, third-party, or production systems. Review the attached dynamic result before retesting.

From the repository root:

{code_block(commands)}

For advisory submission, the useful evidence is in `attachments/source_record.json`, `attachments/evidence.json`, and `attachments/ATTACHMENTS.md`. The full large payloads or raw stress scripts do not need to be published publicly.

## Dynamic Evidence

{markdown_table([
    ("Failure signal", f"`{record.get('failure_signal')}`"),
    ("Heap / memory evidence", f"`{record.get('heap_or_limit')}`"),
    ("Requests sent", f"`{record.get('requests_sent')}`"),
    ("Strict 1 GiB evidence", f"`{record.get('strict_1g_evidence')}`"),
    ("Original log path", f"`{record.get('log_path')}`"),
])}

Evidence summary:

```text
{text["summary_en"]}
```

## Suggested Remediation

- Add hard limits for request body size, object count, topic/job/key cardinality, queue length, active thread count, or aggregate retained bytes at the vulnerable entry.
- Enforce authentication and quota checks before expensive body reads, decompression, JSON/protobuf parsing, image rendering, task creation, or state retention.
- Add per-IP, per-user, per-token, or per-client rate and resource quotas for anonymous or low-privilege entries.
- Return 400/413/429 as early as possible and avoid retaining complete request bodies, payloads, or incomplete protocol state after rejection.

Recorded limits or mitigations:

{bullets(limits)}

Not affected or substantially reduced risk when:

{bullets(not_affected)}

## Attachments

{markdown_table(attachment_rows)}

## Disclosure Notes

Submit through the project's security advisory, private issue, or security contact first. Before coordinated disclosure, avoid publishing full large payloads, automated stress scripts, or commands that can be directly aimed at non-authorized targets.
"""


def reproduce_script(record: dict[str, Any], result: dict[str, Any] | None) -> str:
    record_id = str(record["record_id"])
    commands = reproduction_commands(record, result)
    joined = "\n".join(commands)
    runner = ""
    if record.get("source_batch") in {"p0", "p1", "p2"} and len(commands) == 1:
        runner = f"""
if [[ "${{RUN_LOCAL_DOS_POC:-}}" == "1" ]]; then
  cd "$REPO_ROOT"
  {commands[0]}
else
  echo "Set RUN_LOCAL_DOS_POC=1 to execute the local disposable harness."
fi
"""
    else:
        runner = """
echo "This case uses case-local Docker/probe commands. Review the printed commands and run them manually from the repository root or original case directory."
"""
    return f"""#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cat <<'MSG'
Local advisory PoC for {record_id}

Safety:
- Run only against local, authorized, disposable targets.
- Do not run against production or third-party systems.
- The commands are derived from the repository's existing dynamic validation harness.

Commands:
{joined}
MSG
{runner}
"""


def build_case(record: dict[str, Any]) -> dict[str, Any]:
    record_id = str(record["record_id"])
    output_dir = OUTPUT_ROOT / sanitize_filename(record_id)
    attachment_dir = output_dir / "attachments"
    output_dir.mkdir(parents=True, exist_ok=True)
    attachment_dir.mkdir(parents=True, exist_ok=True)

    result, case_dir = load_result(record)
    dynamic = load_dynamic_finding(record)
    static = load_static_finding(record)

    attachments: list[tuple[str, str]] = []
    source_record_path = attachment_dir / "source_record.json"
    write_json(source_record_path, record)
    attachments.append((rel(source_record_path), "binary truth record"))

    evidence_path = attachment_dir / "evidence.json"
    write_json(evidence_path, evidence_object(record, result, dynamic))
    attachments.append((rel(evidence_path), "normalized advisory evidence"))

    if result:
        result_path = attachment_dir / "source_result.json"
        write_json(result_path, result)
        attachments.append((rel(result_path), "copied dynamic result.json content"))

    if dynamic:
        dynamic_path = attachment_dir / "dynamic_finding.json"
        write_json(dynamic_path, dynamic)
        attachments.append((rel(dynamic_path), "copied P0/P1 dynamic finding"))

    if static:
        static_path = attachment_dir / "static_finding.json"
        write_json(static_path, static)
        attachments.append((rel(static_path), "copied application static finding"))

    if case_dir:
        for name in ("probe.py", "probe.sh", "docker-compose.yml", "start_commands.sh", "case_plan.json", "environment.md"):
            src = case_dir / name
            if src.exists() and src.is_file():
                copy_attachment(src, attachment_dir / name, attachments)

    copy_log_attachment(record, case_dir, attachment_dir, attachments)

    write_text(attachment_dir / "ATTACHMENTS.md", "# Attachments\n\n" + markdown_table(attachments))
    write_text(output_dir / "SECURITY_ADVISORY.zh-CN.md", advisory_zh(record, result, dynamic, static, attachments))
    write_text(output_dir / "SECURITY_ADVISORY.en.md", advisory_en(record, result, dynamic, static, attachments))
    reproduce_path = output_dir / "reproduce.sh"
    write_text(reproduce_path, reproduce_script(record, result))
    os.chmod(reproduce_path, 0o755)

    return {
        "record_id": record_id,
        "app": record.get("app"),
        "source_batch": record.get("source_batch"),
        "status": record.get("status"),
        "output_dir": rel(output_dir),
        "entry": infer_entry(record, result, dynamic),
    }


def build_index(generated: list[dict[str, Any]]) -> str:
    rows = [
        (
            f"`{item['record_id']}`",
            f"`{item['app']}`",
            f"`{item['source_batch']}`",
            f"`{item['status']}`",
            f"[目录]({Path(str(item['output_dir'])).name}/)",
        )
        for item in generated
    ]
    lines = [
        "# Advisory PoC Bundles",
        "",
        f"- Source JSON: `{rel(TRUTH_JSON)}`",
        f"- Source Markdown: `{rel(TRUTH_MD)}`",
        f"- Confirmed true positives: `{len(generated)}`",
        "",
        "Each case directory contains:",
        "",
        "- `SECURITY_ADVISORY.zh-CN.md`",
        "- `SECURITY_ADVISORY.en.md`",
        "- `reproduce.sh` with local-only harness commands",
        "- `attachments/` with source truth/evidence records and copied small artifacts",
        "",
        "| ID | App | Batch | Status | Directory |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in rows)
    return "\n".join(lines)


def main() -> None:
    data = read_json(TRUTH_JSON)
    records = data.get("confirmed_true_positive") or []
    if not records:
        raise SystemExit("No confirmed_true_positive records found.")

    generated = [build_case(record) for record in records]
    write_text(OUTPUT_ROOT / "README.md", build_index(generated))
    write_json(OUTPUT_ROOT / "manifest.json", generated)
    print(f"generated {len(generated)} advisory PoC bundles under {rel(OUTPUT_ROOT)}")


if __name__ == "__main__":
    main()
