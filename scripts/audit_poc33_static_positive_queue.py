#!/usr/bin/env python3
"""Independent static-positive audit for PoC-33 real-LLM full batch findings.

Joins 1,277 certificate-backed findings with entry/growth/flow/lifecycle
evidence, deduplicates by resource cluster, and emits an independent static
positive queue for dynamic validation. Pipeline verdicts stay untouched.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/home/furina/new_tool/dos-analysis-web")
BATCH = ROOT / "results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233"
RECALL = ROOT / "results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-recall-p0-final"
POC_MANIFEST = ROOT / "poc/manifest.json"
OUT = ROOT / "results/java_web_dos_batch/poc33-real-llm-full-v2-20260824_110233-static-positive-audit"

TEST_PATH_RE = re.compile(
    r"(^|/)(src/test|src/tests|src/jmh|benchmarks?/|examples?/|demo/|samples?/)(/|$)|"
    r"Test\.java$|Tests\.java$|Benchmark\.java$|IT\.java$",
    re.I,
)
ADMIN_ROUTE_RE = re.compile(
    r"/admin(/|$)|/actuator|/manage(ment)?(/|$)|/swagger|/druid/coordinator|"
    r"/internal(/|$)|/debug(/|$)",
    re.I,
)
CLI_PATH_RE = re.compile(r"/cli/|ExportTool\.java|CommandLine", re.I)

STREAM_KINDS = {"stream", "entity", "payload", "part", "file"}
BODY_TYPES = (
    "string",
    "byte",
    "bytes",
    "inputstream",
    "reader",
    "json",
    "multipart",
    "part",
    "file",
    "body",
    "payload",
    "entity",
)
NON_BODY_TYPES = ("httpservletrequest", "servletrequest", "httpcontext", "httpservletresponse")
ARRAY_CREATION_OPS = {"array_creation"}
RETENTION_SCOPES = {"instance", "global", "session", "static"}
DOS_KINDS = {
    "input_materialization",
    "direct_allocation",
    "container_growth",
    "async_work_growth",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def index_by(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], dict[str, Any]]:
    out: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        out[tuple(row.get(k) for k in keys)] = row
    return out


def index_multi(rows: list[dict[str, Any]], *keys: str) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    out: defaultdict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[tuple(row.get(k) for k in keys)].append(row)
    return out


def is_test_path(path: str | None) -> bool:
    if not path:
        return False
    normalized = path.replace("\\", "/")
    return bool(TEST_PATH_RE.search(normalized))


def attacker_has_stream(inputs: list[dict[str, Any]] | None) -> bool:
    for item in inputs or []:
        kind = str(item.get("kind") or "").lower()
        typ = str(item.get("type") or "").lower()
        name = str(item.get("name") or "").lower()
        if any(tok in typ for tok in NON_BODY_TYPES) and kind not in STREAM_KINDS:
            continue
        if kind in STREAM_KINDS:
            return True
        if "inputstream" in typ or "servletinputstream" in typ:
            return True
        if kind == "request_body" and any(tok in typ for tok in BODY_TYPES):
            return True
        if kind == "request_body" and name in {"body", "payload", "content", "json", "xml", "data"}:
            return True
    return False


def evidence_score(rec: dict[str, Any]) -> tuple[int, ...]:
    return (
        1 if rec["recall_status"] == "full_chain_finding" else 0,
        1 if rec["recall_status"] in {"growth_only", "association_missing", "entry_only"} else 0,
        1 if rec["verified_growth_status"] == "verified" else 0,
        1 if rec["contract_is_resource_growth"] == "yes" else 0,
        1 if rec["flow_kind"] == "data_flow" else 0,
        1 if rec["flow_coverage"] == "complete" else 0,
        1 if rec["link_status"] == "complete" else 0,
        1 if rec["growth_kind"] == "input_materialization" else 0,
        1 if rec["has_stream_input"] else 0,
        1 if rec["escape_scope"] in RETENTION_SCOPES else 0,
        rec.get("member_count", 1),
        -len(rec.get("reason_codes") or []),
    )


def classify(rec: dict[str, Any]) -> tuple[str, str, str, str]:
    """Return (disposition, reason, amplification_class, dynamic_priority).

    disposition:
      independent_static_positive | independent_static_unknown | reject
    """
    reasons: list[str] = []
    entry_file = rec.get("entry_file") or ""
    growth_file = rec.get("growth_file") or ""
    route = rec.get("route") or ""
    handler = rec.get("handler_callable") or ""

    if is_test_path(entry_file) or is_test_path(growth_file):
        return "reject", "test_or_benchmark_path", "low_amplification", "exclude"
    if CLI_PATH_RE.search(growth_file) or CLI_PATH_RE.search(entry_file):
        return "reject", "cli_or_non_service_path", "low_amplification", "exclude"
    if "TestController" in handler or "/tool/swagger/" in (entry_file + growth_file):
        return "reject", "swagger_or_test_controller", "low_amplification", "exclude"
    if rec.get("protocol") not in {"http", "mqtt", "tcp", "grpc"}:
        return "reject", "unsupported_protocol", "low_amplification", "exclude"
    if not rec.get("route") and rec.get("framework") not in {"netty", "mqtt", "servlet"}:
        reasons.append("route_missing")
    if ADMIN_ROUTE_RE.search(route) and rec.get("recall_status") not in {
        "full_chain_finding",
        "growth_only",
        "association_missing",
        "entry_only",
    }:
        return "reject", "admin_or_management", "low_amplification", "exclude"
    if rec.get("verified_growth_status") == "rejected":
        return "reject", "growth_contract_negated", "low_amplification", "exclude"
    if rec.get("growth_kind") not in DOS_KINDS:
        return "reject", "growth_kind_out_of_scope", "low_amplification", "exclude"

    a1_single = "A1_SINGLE_OPERATION_NOT_AMPLIFYING" in (rec.get("reason_codes") or [])
    request_local = rec.get("escape_scope") == "request"
    stream = rec.get("has_stream_input")
    dim = rec.get("resource_dimension")
    kind = rec.get("growth_kind")
    op = rec.get("growth_operation") or ""
    receiver = rec.get("resource_receiver") or ""
    growth_file = rec.get("growth_file") or ""
    retained = rec.get("escape_scope") in RETENTION_SCOPES
    materialization = kind == "input_materialization"
    async_work = kind == "async_work_growth"
    contract_yes = rec.get("contract_is_resource_growth") == "yes"
    verified = rec.get("verified_growth_status") == "verified"
    data_flow = rec.get("flow_kind") == "data_flow"
    recall_hit = rec.get("recall_status") in {
        "full_chain_finding",
        "growth_only",
        "association_missing",
        "entry_only",
    }
    route_l = route.lower()
    get_only = route.upper().startswith("GET ") or (
        rec.get("framework") in {"spring_mvc", "jax_rs"} and "GET" in route.upper() and "POST" not in route.upper()
    )
    captcha_like = any(
        tok in (op + receiver + growth_file + route_l + handler).lower()
        for tok in ("captcha", "speccaptcha", "bufferedimage", "verifyutils", "codecontroller", "code-img")
    )
    server_file_read = any(
        tok in (op + growth_file + route_l)
        for tok in ("FileUtils", "FileDownloader", "OshiUtils", "OmsFileUtils", "OpenApiResource", "/common/download", "/commons/theme")
    )
    domain_array = op == "array_creation" and not stream and dim in {"bytes", "objects", "entries", None}

    if not recall_hit:
        if captcha_like:
            return "reject", "captcha_or_fixed_image", "low_amplification", "exclude"
        if server_file_read:
            return "reject", "server_controlled_file_read", "low_amplification", "exclude"
        if domain_array:
            return "reject", "request_local_array_allocation", "low_amplification", "exclude"
        if async_work and ("AsyncManager" in receiver or "TaskExecutors" in receiver or "schedule" in op):
            return "reject", "one_shot_async_schedule", "low_amplification", "exclude"
        if "base64image" in route_l or "VerificationController" in handler:
            return "reject", "captcha_or_fixed_image", "low_amplification", "exclude"
        if op == "array_creation" and "byte[]" not in receiver:
            return "reject", "request_local_array_allocation", "low_amplification", "exclude"
        if kind == "container_growth" and "HttpSession.setAttribute" in op and not stream:
            return "reject", "single_session_attribute", "low_amplification", "exclude"

    # Request-local tiny/single-op allocations without attacker-sized input.
    if (
        request_local
        and kind == "direct_allocation"
        and not stream
        and not materialization
        and not recall_hit
    ):
        return "reject", "request_local_bounded", "low_amplification", "exclude"
    if (
        request_local
        and kind == "container_growth"
        and a1_single
        and dim == "entries"
        and not stream
        and not recall_hit
        and not contract_yes
    ):
        return "reject", "request_local_collection", "low_amplification", "exclude"
    if materialization and get_only and not stream and not recall_hit:
        return "reject", "server_side_materialization", "low_amplification", "exclude"

    attacker_bytes = materialization and (stream or not get_only)
    large_single = attacker_bytes or (stream and dim in {"bytes", "objects"} and kind != "container_growth")
    retention = retained and kind in {"container_growth", "direct_allocation", "async_work_growth"}
    queue_instability = async_work and retained

    if large_single:
        amp = "large_single_request"
        prio = "P0"
    elif queue_instability:
        amp = "queue_instability"
        prio = "P0"
    elif retention and dim in {"bytes", "objects", "tasks"}:
        amp = "concurrent_retention"
        prio = "P1"
    elif retention:
        amp = "high_cardinality_retention"
        prio = "P2"
    elif contract_yes and stream:
        amp = "large_single_request"
        prio = "P0"
    elif contract_yes:
        amp = "high_cardinality_retention"
        prio = "P2"
    else:
        amp = "low_amplification"
        prio = "exclude"

    strong = any(
        [
            recall_hit,
            verified,
            contract_yes and (large_single or retention or async_work),
            data_flow and (large_single or retention or async_work),
            materialization and stream,
            stream and dim == "bytes" and rec.get("link_status") in {"complete", "partial"},
            async_work,
            retention and rec.get("link_status") == "complete",
        ]
    )
    plausible = large_single or retention or async_work or contract_yes or recall_hit

    if not plausible or prio == "exclude":
        return "reject", "growth_not_dos_relevant", amp, "exclude"

    # Independent positive: concrete E, G, flow, DoS-relevant growth, no effective bound.
    bound_effective = rec.get("bound_decision") == "effective"
    if bound_effective:
        return "reject", "effective_bound", amp, "exclude"

    has_entry = bool(rec.get("entry_id") and (rec.get("route") or rec.get("framework") in {"netty", "mqtt", "servlet"}))
    has_growth = bool(rec.get("growth_id") and rec.get("growth_file"))
    has_flow = bool(rec.get("flow_id"))
    if not (has_entry and has_growth and has_flow):
        if recall_hit:
            return "independent_static_unknown", "recall_partial_chain", amp, prio
        return "reject", "path_not_proven", amp, "exclude"

    if strong and prio in {"P0", "P1"}:
        return "independent_static_positive", "dos_relevant_unbounded_path", amp, prio
    if strong:
        return "independent_static_positive", "retention_unbounded_path", amp, prio
    if plausible and prio in {"P0", "P1"}:
        return "independent_static_unknown", "high_severity_unresolved_lifecycle", amp, prio
    return "independent_static_unknown", "unresolved_static_evidence", amp, prio


def probe_plan(rec: dict[str, Any]) -> dict[str, Any]:
    route = rec.get("route") or ""
    method = "POST"
    if route:
        parts = route.split(None, 1)
        if parts and parts[0].upper() in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"}:
            method = parts[0].upper()
            route = parts[1] if len(parts) > 1 else route
    loop = "body_size" if rec.get("has_stream_input") or rec.get("resource_dimension") == "bytes" else "request_count"
    metric = {
        "bytes": "heap",
        "objects": "heap",
        "entries": "heap",
        "tasks": "threads",
    }.get(rec.get("resource_dimension") or "", "heap")
    return {
        "probe_id": f"PROBE-{rec['cluster_id']}",
        "finding_id": rec["finding_id"],
        "prerequisite_defaults": ["official_or_documented_default_start"],
        "request_shape": f"{method} {route or rec.get('handler_callable')}",
        "parameters": {
            "framework": rec.get("framework"),
            "attacker_inputs": rec.get("attacker_inputs"),
        },
        "loop_variable": loop,
        "resource_metric": metric,
        "expected_growth": rec.get("amplification_class"),
        "failure_signal": "OOM|GC death|thread/connection exhaustion|sustained 5xx",
        "request_budget_rationale": "bounded ramp until failure or effective bound",
        "safety_limit": "cap requests/time/container memory; stop on first strong failure",
        "isolation_requirements": ["local_or_disposable_container", "no_production"],
        "success_condition": "target JVM resource failure under default deployment",
        "stop_condition": "confirmed_failure or safety_cap or effective_bound",
        "cleanup": "stop container and remove case network/volumes",
        "unresolved_static_question": rec.get("audit_reason"),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    findings = load_jsonl(BATCH / "aggregate_findings.jsonl")
    entries = load_jsonl(BATCH / "aggregate_entries.jsonl")
    growths = load_jsonl(BATCH / "aggregate_growth_candidates.jsonl")
    flows = load_jsonl(BATCH / "aggregate_flows.jsonl")
    contracts = load_jsonl(BATCH / "aggregate_growth_contracts.jsonl")
    verified = load_jsonl(BATCH / "aggregate_verified_growth.jsonl")
    links = load_jsonl(BATCH / "aggregate_candidate_entry_links.jsonl")
    certs = load_jsonl(BATCH / "aggregate_lifecycle_certificates.jsonl")
    life_results = load_jsonl(BATCH / "aggregate_lifecycle_results.jsonl")
    reach = load_jsonl(BATCH / "aggregate_reachability_decisions.jsonl")
    amp = load_jsonl(BATCH / "aggregate_amplification_decisions.jsonl")
    recall = load_jsonl(RECALL / "truth_dispositions.jsonl")
    poc_manifest = json.loads(POC_MANIFEST.read_text(encoding="utf-8"))

    entry_ix = index_by(entries, "batch_target_slug", "entry_id")
    growth_ix = index_by(growths, "batch_target_slug", "growth_id")
    flow_ix = index_by(flows, "batch_target_slug", "entry_id", "growth_id")
    contract_ix = index_by(contracts, "batch_target_slug", "growth_id")
    verified_ix = index_by(verified, "batch_target_slug", "growth_id")
    link_ix = index_by(links, "batch_target_slug", "entry_id", "growth_id")
    cert_ix = index_by(certs, "batch_target_slug", "entry_id", "growth_id")
    life_ix = index_by(life_results, "batch_target_slug", "entry_id", "growth_id")
    reach_ix = index_by(reach, "batch_target_slug", "entry_id")
    amp_ix = index_by(amp, "batch_target_slug", "entry_id", "growth_id")

    finding_to_truth: dict[str, list[dict[str, Any]]] = defaultdict(list)
    growth_to_truth: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    entry_to_truth: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    slug_alias = {
        "yiuman/citrus": "yiuman__citrus",
        "dromara/datacompare": "dromara__datacompare",
        "DependencyTrack/dependency-track": "dependencytrack__dependency-track",
        "dependencytrack/dependency-track": "dependencytrack__dependency-track",
    }
    for row in recall:
        repo = row.get("repository") or ""
        slug = slug_alias.get(repo, repo.replace("/", "__"))
        for fid in row.get("matched_finding_ids") or []:
            finding_to_truth[fid].append(row)
        for gid in row.get("matched_growth_ids") or []:
            growth_to_truth[(slug, gid)].append(row)
        for eid in row.get("matched_entry_ids") or []:
            entry_to_truth[(slug, eid)].append(row)

    joined: list[dict[str, Any]] = []
    for finding in findings:
        slug = finding["batch_target_slug"]
        eid = finding["entry_id"]
        gid = finding["growth_id"]
        entry = entry_ix.get((slug, eid), {})
        growth = growth_ix.get((slug, gid), {})
        flow = flow_ix.get((slug, eid, gid), {})
        contract = contract_ix.get((slug, gid), {})
        vg = verified_ix.get((slug, gid), {})
        link = link_ix.get((slug, eid, gid), {})
        cert = cert_ix.get((slug, eid, gid), {})
        life = life_ix.get((slug, eid, gid), {})
        reach_row = reach_ix.get((slug, eid), {})
        amp_row = amp_ix.get((slug, eid, gid), {})
        handler = (entry.get("handler") or {})
        registration = (entry.get("registration") or {})
        site = (growth.get("site") or {})
        rp = (growth.get("resource_point") or {})
        attacker_inputs = entry.get("attacker_inputs") or cert.get("attacker_inputs") or []
        truths = finding_to_truth.get(finding["finding_id"]) or growth_to_truth.get((slug, gid)) or entry_to_truth.get((slug, eid)) or []
        recall_status = truths[0]["status"] if truths else None
        recall_ids = [t.get("record_id") for t in truths]
        rec = {
            "finding_id": finding["finding_id"],
            "certificate_id": finding.get("certificate_id"),
            "pipeline_verdict": finding.get("verdict"),
            "reason_codes": finding.get("reason_codes") or [],
            "batch_target_slug": slug,
            "batch_target_name": finding.get("batch_target_name"),
            "batch_repo_path": finding.get("batch_repo_path"),
            "batch_output_dir": finding.get("batch_output_dir"),
            "entry_id": eid,
            "growth_id": gid,
            "framework": entry.get("framework"),
            "protocol": entry.get("protocol"),
            "route": entry.get("route_or_event"),
            "auth_context": entry.get("auth_context") or reach_row.get("auth_context"),
            "handler_callable": handler.get("callable"),
            "entry_file": handler.get("file"),
            "entry_line": handler.get("start_line"),
            "registration_kind": registration.get("kind"),
            "registration_file": registration.get("file"),
            "attacker_inputs": attacker_inputs,
            "has_stream_input": attacker_has_stream(attacker_inputs),
            "growth_kind": growth.get("kind") or contract.get("growth_kind"),
            "growth_operation": growth.get("operation"),
            "growth_file": site.get("file"),
            "growth_line": site.get("start_line"),
            "escape_scope": growth.get("escape_scope"),
            "resource_dimension": (rp.get("dimension") or contract.get("resource_dimension")),
            "resource_id": rp.get("resource_id"),
            "resource_receiver": rp.get("receiver"),
            "resource_field": rp.get("field_path"),
            "flow_id": flow.get("path_id"),
            "flow_kind": flow.get("flow_kind"),
            "flow_coverage": flow.get("coverage_status"),
            "flow_confidence": flow.get("confidence"),
            "flow_call_path": flow.get("call_path"),
            "link_status": link.get("status"),
            "link_reason_codes": link.get("reason_codes") or [],
            "contract_id": contract.get("growth_contract_id"),
            "contract_is_resource_growth": contract.get("is_resource_growth"),
            "contract_confidence": contract.get("confidence"),
            "contract_effect": contract.get("resource_effect"),
            "verified_growth_status": vg.get("status"),
            "verified_growth_reasons": vg.get("reason_codes") or [],
            "bound_decision": (life.get("bound_decision") or (cert.get("bound_decision") or {}).get("status")),
            "release_decision": (life.get("release_decision") or (cert.get("release_decision") or {}).get("status")),
            "guard_decision": (life.get("guard_decision") or (cert.get("guard_decision") or {}).get("status")),
            "reachability_status": reach_row.get("status"),
            "amplification_status": amp_row.get("status"),
            "recall_status": recall_status,
            "recall_record_ids": recall_ids,
        }
        joined.append(rec)

    # Dedup: cluster by target + resource identity, fallback to growth_id.
    clusters: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rec in joined:
        resource_key = rec.get("resource_id") or rec["growth_id"]
        clusters[(rec["batch_target_slug"], resource_key)].append(rec)

    cluster_rows: list[dict[str, Any]] = []
    for (slug, resource_key), members in sorted(clusters.items()):
        ranked = sorted(members, key=evidence_score, reverse=True)
        # Prefer production routes over lookups/internal when scores tie.
        def route_rank(item: dict[str, Any]) -> tuple[int, int]:
            route = item.get("route") or ""
            penalty = 1 if ADMIN_ROUTE_RE.search(route) else 0
            return (-evidence_score(item)[0], penalty)

        ranked = sorted(members, key=lambda m: (evidence_score(m), 0 if not ADMIN_ROUTE_RE.search(m.get("route") or "") else -1), reverse=True)
        best = dict(ranked[0])
        best["cluster_id"] = f"{slug}:{resource_key}"
        best["member_count"] = len(members)
        best["member_finding_ids"] = [m["finding_id"] for m in members]
        best["member_entry_ids"] = sorted({m["entry_id"] for m in members})
        best["member_growth_ids"] = sorted({m["growth_id"] for m in members})
        best["member_routes"] = sorted({m.get("route") or "" for m in members})
        disp, reason, amp_class, prio = classify(best)
        best["independent_disposition"] = disp
        best["audit_reason"] = reason
        best["amplification_class"] = amp_class
        best["dynamic_priority"] = prio
        cluster_rows.append(best)

    def family_key(item: dict[str, Any]) -> tuple[str, ...]:
        slug = item["batch_target_slug"]
        kind = item.get("growth_kind") or "unknown"
        op = item.get("growth_operation") or "unknown"
        handler = item.get("handler_callable") or ""
        handler_class = handler.rsplit(".", 1)[0] if "." in handler else handler
        growth_file = item.get("growth_file") or ""
        if kind == "input_materialization":
            return (slug, "mat", handler_class, op)
        if kind == "container_growth":
            norm_op = re.sub(r"<[^>]*>", "", op)
            return (slug, "ret", growth_file, norm_op)
        if kind == "async_work_growth":
            return (slug, "async", item.get("resource_receiver") or op)
        return (slug, "other", item.get("resource_id") or item["growth_id"])

    rejected = [c for c in cluster_rows if c["independent_disposition"] == "reject"]
    eligible = [
        c
        for c in cluster_rows
        if c["independent_disposition"] == "independent_static_positive"
        and c["dynamic_priority"] in {"P0", "P1", "P2"}
    ] + [
        c
        for c in cluster_rows
        if c["independent_disposition"] == "independent_static_unknown"
        and c["dynamic_priority"] in {"P0", "P1"}
    ]
    families: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in eligible:
        families[family_key(item)].append(item)
    merged: list[dict[str, Any]] = []
    for key, members in families.items():
        ranked = sorted(members, key=evidence_score, reverse=True)
        best = dict(ranked[0])
        best["family_key"] = "|".join(key)
        best["family_member_count"] = len(members)
        best["family_cluster_ids"] = [m["cluster_id"] for m in members]
        best["family_finding_ids"] = [fid for m in members for fid in m.get("member_finding_ids", [m["finding_id"]])]
        best["family_routes"] = sorted({route for m in members for route in (m.get("member_routes") or [m.get("route") or ""])})
        best["member_count"] = sum(m.get("member_count", 1) for m in members)
        merged.append(best)
    positives = [c for c in merged if c["independent_disposition"] == "independent_static_positive"]
    unknowns = [c for c in merged if c["independent_disposition"] == "independent_static_unknown"]

    # Queue = all independent positives + selected high-severity unknowns.
    queue = sorted(
        positives + unknowns,
        key=lambda c: (
            {"P0": 0, "P1": 1, "P2": 2}.get(c["dynamic_priority"], 9),
            0 if c["independent_disposition"] == "independent_static_positive" else 1,
            c["batch_target_slug"],
            c["cluster_id"],
        ),
    )
    for idx, rec in enumerate(queue, 1):
        rec["queue_index"] = idx
        rec["case_id"] = f"{rec['batch_target_slug']}-{rec['finding_id'].replace(':', '_')}"
        rec["probe_plan"] = probe_plan(rec)
        rec["static_conclusion"] = (
            "static_vulnerable"
            if rec["independent_disposition"] == "independent_static_positive"
            else "static_unknown"
        )

    # Dynamic-validator input records.
    dyn_rows: list[dict[str, Any]] = []
    for rec in queue:
        plan = rec["probe_plan"]
        dyn_rows.append(
            {
                "target": rec["batch_target_name"],
                "slug": rec["batch_target_slug"],
                "repo_path": rec["batch_repo_path"],
                "static_output_dir": rec["batch_output_dir"],
                "finding_id": rec["finding_id"],
                "probe_id": plan["probe_id"],
                "title": f"{rec['batch_target_name']} {rec.get('route') or rec.get('handler_callable')} -> {rec.get('resource_receiver')}",
                "verdict": rec["static_conclusion"],
                "resource_dimension": rec.get("resource_dimension"),
                "source": rec.get("handler_callable"),
                "sink": rec.get("growth_operation") or rec.get("resource_receiver"),
                "driver": "stream/body" if rec.get("has_stream_input") else rec.get("escape_scope"),
                "request_shape": plan["request_shape"],
                "parameters": plan["parameters"],
                "loop_variable": plan["loop_variable"],
                "resource_metric": plan["resource_metric"],
                "expected_growth": plan["expected_growth"],
                "safety_limit": plan["safety_limit"],
                "success_condition": plan["success_condition"],
                "stop_condition": plan["stop_condition"],
                "cleanup": plan["cleanup"],
                "evidence": {
                    "cluster_id": rec["cluster_id"],
                    "member_count": rec["member_count"],
                    "flow_kind": rec.get("flow_kind"),
                    "growth_kind": rec.get("growth_kind"),
                    "escape_scope": rec.get("escape_scope"),
                    "recall_record_ids": rec.get("recall_record_ids"),
                },
                "missing_evidence": rec.get("reason_codes"),
                "independent_disposition": rec["independent_disposition"],
                "audit_reason": rec["audit_reason"],
                "dynamic_priority": rec["dynamic_priority"],
                "amplification_class": rec["amplification_class"],
                "entry_id": rec["entry_id"],
                "growth_id": rec["growth_id"],
                "route": rec.get("route"),
                "framework": rec.get("framework"),
            }
        )

    dump_jsonl(OUT / "all_findings_joined.jsonl", joined)
    dump_jsonl(OUT / "dedup_clusters.jsonl", cluster_rows)
    dump_jsonl(OUT / "rejected.jsonl", rejected)
    dump_jsonl(OUT / "independent_audit.jsonl", cluster_rows)
    dump_jsonl(OUT / "static_positive_queue.jsonl", queue)
    dump_jsonl(OUT / "dynamic_validation_queue.jsonl", dyn_rows)

    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "batch_root": str(BATCH),
        "recall_root": str(RECALL),
        "raw_findings": len(findings),
        "unique_entry_growth": len({(f["entry_id"], f["growth_id"]) for f in findings}),
        "unique_growth": len({(f["batch_target_slug"], f["growth_id"]) for f in findings}),
        "unique_resource_clusters": len(cluster_rows),
        "pipeline_verdict_counts": dict(Counter(f.get("verdict") for f in findings)),
        "cluster_disposition_counts": dict(Counter(c["independent_disposition"] for c in cluster_rows)),
        "reject_reason_counts": dict(Counter(c["audit_reason"] for c in rejected)),
        "queue_size": len(queue),
        "queue_disposition_counts": dict(Counter(c["independent_disposition"] for c in queue)),
        "queue_priority_counts": dict(Counter(c["dynamic_priority"] for c in queue)),
        "queue_by_target": dict(Counter(c["batch_target_slug"] for c in queue)),
        "queue_amplification_counts": dict(Counter(c["amplification_class"] for c in queue)),
        "recall_clusters_in_queue": sum(1 for c in queue if c.get("recall_record_ids")),
        "known_poc_truths": len(poc_manifest),
        "note": "independent_static_positive is an audit label for dynamic-validation queueing; it does not rewrite pipeline static_unknown artifacts.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with (OUT / "static_positive_queue.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "queue_index",
                "dynamic_priority",
                "independent_disposition",
                "audit_reason",
                "amplification_class",
                "batch_target_slug",
                "finding_id",
                "route",
                "growth_kind",
                "escape_scope",
                "resource_dimension",
                "resource_receiver",
                "member_count",
                "recall_record_ids",
            ],
        )
        writer.writeheader()
        for rec in queue:
            writer.writerow(
                {
                    "queue_index": rec["queue_index"],
                    "dynamic_priority": rec["dynamic_priority"],
                    "independent_disposition": rec["independent_disposition"],
                    "audit_reason": rec["audit_reason"],
                    "amplification_class": rec["amplification_class"],
                    "batch_target_slug": rec["batch_target_slug"],
                    "finding_id": rec["finding_id"],
                    "route": rec.get("route"),
                    "growth_kind": rec.get("growth_kind"),
                    "escape_scope": rec.get("escape_scope"),
                    "resource_dimension": rec.get("resource_dimension"),
                    "resource_receiver": rec.get("resource_receiver"),
                    "member_count": rec["member_count"],
                    "recall_record_ids": ";".join(rec.get("recall_record_ids") or []),
                }
            )

    lines = [
        "# PoC-33 independent static-positive audit",
        "",
        f"- Batch: `{BATCH}`",
        f"- Recall: `{RECALL}`",
        f"- Raw findings: **{len(findings)}** (all pipeline `static_unknown`)",
        f"- Unique resource clusters after dedup: **{len(cluster_rows)}**",
        f"- Independent static-positive queue: **{len(queue)}**",
        "",
        "## Disposition counts",
        "",
    ]
    for key, value in summary["cluster_disposition_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Reject reasons", ""]
    for key, value in sorted(summary["reject_reason_counts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Queue by target", ""]
    for key, value in sorted(summary["queue_by_target"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Queue table", "", "| # | P | disposition | target | route | growth | dim | members | recall |", "|---|---|---|---|---|---|---|---|---|"]
    for rec in queue:
        route = (rec.get("route") or rec.get("handler_callable") or "").replace("|", "/")
        lines.append(
            f"| {rec['queue_index']} | {rec['dynamic_priority']} | {rec['independent_disposition']} | {rec['batch_target_slug']} | `{route}` | {rec.get('growth_kind')} | {rec.get('resource_dimension')} | {rec['member_count']} | {', '.join(rec.get('recall_record_ids') or [])} |"
        )
    lines += [
        "",
        "## Method",
        "",
        "1. Join each finding to entry, growth candidate, flow, contract, verified growth, link, lifecycle, reachability, amplification, and PoC-33 recall truth.",
        "2. Deduplicate by `(target_slug, resource_id)` (fallback `growth_id`), keeping the strongest evidence member.",
        "3. Independently classify using hunter model `Reach ∧ AttackerControls ∧ Growth ∧ ¬EffectiveB`.",
        "4. Queue `independent_static_positive` plus selected P0/P1 `independent_static_unknown` with a concrete probe plan.",
        "5. Do not rewrite pipeline artifacts; this queue is an independent audit overlay.",
        "",
        "Pipeline produced 0 `static_vulnerable` because growth/lifecycle facts stayed unresolved. The independent queue is the set of clusters whose static evidence is strong enough to justify isolated dynamic validation.",
        "",
    ]
    (OUT / "AUDIT_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
