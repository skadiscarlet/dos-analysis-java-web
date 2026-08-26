"""Chain-level truth dispositions for the PoC-33 recall harness.

A truth disposition records the furthest reached stage of the P0 analysis chain
(entry -> growth -> association -> flow -> lifecycle -> finding) plus an explicit
reason, instead of the route-marker recall used by earlier baselines.  Dynamic
status is only an oracle label and never changes a static verdict.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from dosweb.artifacts.schemas import validate_records, validate_references
from dosweb.benchmark.matching import _entry_identity, _method, _protocol, normalize_route
from dosweb.errors import AnalyzerError

DISPOSITION_STATUSES = (
    "full_chain_finding",
    "entry_and_growth_linked",
    "entry_only",
    "growth_only",
    "association_missing",
    "flow_partial",
    "lifecycle_unknown",
    "stage_failed",
    "asset_missing",
    "unsupported_scope",
    "ambiguous_truth_match",
)

_SUPPORTED_FRAMEWORKS = frozenset({"spring_mvc", "servlet", "netty", "mqtt", "jax_rs", "grpc"})
_GENERIC_TCP_SERVICE_ENTRY = re.compile(
    r"^protocol service on port [0-9]+$", re.IGNORECASE
)

_ENTRY_ARTIFACT = "entry_facts.jsonl"
_GAP_ARTIFACT = "entry_gap_facts.jsonl"
_INTERPOSITION_ARTIFACT = "entry_interposition_facts.jsonl"
_GROWTH_ARTIFACT = "growth_candidates.jsonl"
_LINKS_ARTIFACT = "candidate_entry_links.jsonl"
_DISPOSITIONS_ARTIFACT = "candidate_dispositions.jsonl"
_VERIFIED_ARTIFACT = "verified_growth.jsonl"
_FLOW_ARTIFACT = "flow_proofs.jsonl"
_FINDINGS_ARTIFACT = "static_findings.jsonl"
_CERTIFICATES_ARTIFACT = "lifecycle_certificates.jsonl"
_RUN_ARTIFACT = "run.json"


class TargetArtifacts:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.entries: list[dict[str, Any]] = []
        self.entry_gaps: list[dict[str, Any]] = []
        self.entry_interpositions: list[dict[str, Any]] = []
        self.growth_candidates: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.candidate_dispositions: list[dict[str, Any]] = []
        self.verified_growth: list[dict[str, Any]] = []
        self.flow_proofs: list[dict[str, Any]] = []
        self.findings: list[dict[str, Any]] = []
        self.certificates: list[dict[str, Any]] = []
        self.run_status = "pending"
        self.run_error: dict[str, Any] | None = None

    @classmethod
    def load(cls, directory: Path) -> "TargetArtifacts":
        artifacts = cls(directory)
        if not directory.is_dir():
            return artifacts
        for name, field in (
            (_ENTRY_ARTIFACT, "entries"),
            (_GAP_ARTIFACT, "entry_gaps"),
            (_INTERPOSITION_ARTIFACT, "entry_interpositions"),
            (_GROWTH_ARTIFACT, "growth_candidates"),
            (_LINKS_ARTIFACT, "links"),
            (_DISPOSITIONS_ARTIFACT, "candidate_dispositions"),
            (_VERIFIED_ARTIFACT, "verified_growth"),
            (_FLOW_ARTIFACT, "flow_proofs"),
            (_FINDINGS_ARTIFACT, "findings"),
            (_CERTIFICATES_ARTIFACT, "certificates"),
        ):
            path = directory / name
            if name in {_GAP_ARTIFACT, _INTERPOSITION_ARTIFACT}:
                records = _read_jsonl_strict(path)
                if name == _GAP_ARTIFACT:
                    validate_records("entry_gap_facts", records)
                else:
                    validate_references(
                        "entry_interposition_facts",
                        records,
                        {"entry_id": {str(entry.get("entry_id")) for entry in artifacts.entries}},
                    )
                setattr(artifacts, field, records)
            else:
                setattr(artifacts, field, _read_jsonl(path))
        run = _read_json(directory / _RUN_ARTIFACT)
        if isinstance(run, Mapping):
            artifacts.run_status = str(run.get("status", "pending"))
            error = run.get("error")
            artifacts.run_error = dict(error) if isinstance(error, Mapping) else None
        return artifacts


def _read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise AnalyzerError(
            "ARTIFACT_INVALID_RECORD",
            "Benchmark chain artifact must be a regular file.",
            {"artifact": path.name},
        )
    rows: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise AnalyzerError(
                    "ARTIFACT_RECORD_NOT_OBJECT",
                    "Benchmark chain artifact record must be an object.",
                    {"artifact": path.name, "line": line_number},
                )
            rows.append(value)
    except AnalyzerError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalyzerError(
            "ARTIFACT_INVALID_RECORD",
            "Benchmark chain artifact is unreadable or invalid JSONL.",
            {"artifact": path.name},
        ) from exc
    return rows


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return rows


def _read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _entry_route(entry: Mapping[str, Any]) -> str:
    return normalize_route(entry.get("route_or_event"))


def _entry_protocol(entry: Mapping[str, Any]) -> str:
    return _protocol(entry.get("protocol") or entry.get("route_or_event"))


def _route_pattern(value: str) -> str:
    # Servlet path mappings ending in ``/*`` cover descendant segments, like
    # Spring's ``/**``. Other single-star forms are not generalized here.
    if value.endswith("/*") and not value.endswith("/**"):
        return value[:-1] + "**"
    return value


def _routes_match(a: str, b: str) -> bool:
    if a == b:
        return True
    left, right = _route_pattern(a), _route_pattern(b)
    # ``**`` is a multi-segment wildcard; ``{}`` is a single-segment
    # path-variable placeholder (e.g. ``/data/table/{erupt}`` vs ``/data/table/EruptUser``).
    pattern = left if ("**" in left or "{}" in left) else right
    value = right if ("**" in left or "{}" in left) else left
    if "**" not in pattern and "{}" not in pattern:
        left_parts = [part for part in left.split("/") if part]
        right_parts = [part for part in right.split("/") if part]
        shorter, longer = (
            (left_parts, right_parts)
            if len(left_parts) <= len(right_parts)
            else (right_parts, left_parts)
        )
        # Spring's deployment context path is not part of annotation mappings.
        # Permit only a proper suffix with at least two application-route
        # segments; downstream Growth identity/link evidence still has to match.
        return (
            len(shorter) >= 2
            and len(longer) > len(shorter)
            and longer[-len(shorter):] == shorter
        )
    regex = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\{\}", "[^/]+")
    return re.fullmatch(regex, value) is not None


def _match_entries(
    truth: Mapping[str, Any],
    entries: list[dict[str, Any]],
    preferred_entry_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    truth_route = normalize_route(truth.get("entry"))
    truth_method = _method(truth.get("entry"))
    configured_protocol = truth.get("protocol")
    truth_protocol = str(configured_protocol) if configured_protocol in {"http", "tcp", "mqtt", "grpc"} else _protocol(truth.get("entry"))
    generic_tcp_service = bool(
        _GENERIC_TCP_SERVICE_ENTRY.fullmatch(str(truth.get("entry", "")).strip())
    )
    if not truth_route and not truth_protocol and not generic_tcp_service:
        return []
    matches = []
    for entry in entries:
        candidate_route = _entry_route(entry)
        candidate_protocol = _entry_protocol(entry)
        candidate_method = _method(entry.get("route_or_event"))
        if generic_tcp_service:
            accepted_protocols = (
                {"mqtt"} if truth_protocol == "mqtt" else {"tcp"}
            )
            if candidate_protocol not in accepted_protocols:
                continue
        if truth_route and candidate_route and not _routes_match(candidate_route, truth_route):
            continue
        if truth_method and candidate_method and truth_method != candidate_method:
            continue
        netty_http_route_over_tcp = (
            truth_protocol == "http"
            and candidate_protocol == "tcp"
            and entry.get("framework") == "netty"
            and bool(truth_route and candidate_route)
        )
        if (
            truth_protocol
            and candidate_protocol != truth_protocol
            and not netty_http_route_over_tcp
        ):
            continue
        matches.append(entry)
    if truth_route:
        exact_matches = [entry for entry in matches if _entry_route(entry) == truth_route]
        if exact_matches:
            linked_matches = [
                entry for entry in matches
                if str(entry.get("entry_id")) in (preferred_entry_ids or set())
            ]
            matches = linked_matches or exact_matches
    matches.sort(key=lambda row: str(row.get("entry_id")))
    return matches


def _registration_identity(entry: Mapping[str, Any]) -> tuple[object, ...]:
    registration = entry.get("registration")
    if not isinstance(registration, Mapping):
        return (entry.get("entry_id"),)
    return (
        registration.get("kind"), registration.get("callable"),
        registration.get("file"), registration.get("start_line"),
    )


def _route_alias_identity(entry: Mapping[str, Any]) -> tuple[object, ...]:
    handler = entry.get("handler")
    handler_identity = (
        handler.get("callable"), handler.get("file"), handler.get("start_line")
    ) if isinstance(handler, Mapping) else ()
    return (*_registration_identity(entry), *handler_identity)


def _canonical_matched_entries(
    entries: list[dict[str, Any]], truth_method: str,
    preferred_entry_ids: set[str],
) -> list[dict[str, Any]]:
    groups: dict[tuple[object, ...], list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(_route_alias_identity(entry), []).append(entry)
    canonical: list[dict[str, Any]] = []
    for group in groups.values():
        canonical.append(min(
            group,
            key=lambda entry: (
                0 if str(entry.get("entry_id")) in preferred_entry_ids else 1,
                0 if (
                    _method(entry.get("route_or_event")) == truth_method
                    if truth_method
                    else not _method(entry.get("route_or_event"))
                ) else 1,
                str(entry.get("entry_id", "")),
            ),
        ))
    return sorted(canonical, key=lambda entry: str(entry.get("entry_id", "")))


def _interposition_connects(
    entries: list[dict[str, Any]], facts: list[dict[str, Any]],
) -> bool:
    ids = {str(entry.get("entry_id")) for entry in entries}
    if len(ids) <= 1:
        return True
    by_location: dict[tuple[object, object], set[str]] = {}
    for entry in entries:
        handler = entry.get("handler")
        if isinstance(handler, Mapping):
            by_location.setdefault((handler.get("file"), handler.get("start_line")), set()).add(str(entry.get("entry_id")))
    graph = {entry_id: set() for entry_id in ids}
    for fact in facts:
        source = fact.get("entry_id")
        interposer = fact.get("interposer")
        if source not in ids or not isinstance(interposer, Mapping):
            continue
        for target in by_location.get((interposer.get("file"), interposer.get("start_line")), set()):
            graph[str(source)].add(target)
            graph[target].add(str(source))
    reached: set[str] = set()
    pending = [next(iter(ids))]
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(graph[current] - reached)
    return reached == ids


def _match_gap_entries(truth: Mapping[str, Any], gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adapted = [
        {"entry_id": gap.get("gap_id"), "route_or_event": gap.get("route_or_event"), "protocol": gap.get("protocol"), "framework": gap.get("framework")}
        for gap in gaps
    ]
    return _match_entries(truth, adapted)


def _match_growth(truth: Mapping[str, Any], growth: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers = truth.get("markers")
    if not isinstance(markers, list) or not markers:
        return []
    lowered_markers = [str(item).lower() for item in markers if isinstance(item, str)]
    call_identities = [
        (receiver.casefold(), operation.casefold())
        for marker in lowered_markers
        for receiver, operation in re.findall(
            r"([A-Za-z_$][A-Za-z0-9_$]*)\.([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", marker
        )
    ]
    sink_locations = truth.get("sink_locations")
    locations = sink_locations if isinstance(sink_locations, list) else []
    matches = []
    for candidate in growth:
        blob = json.dumps(candidate, sort_keys=True, default=str).lower()
        site = candidate.get("site")
        location_match = False
        receiver_owner_match = False
        resource_point = candidate.get("resource_point")
        receiver = resource_point.get("receiver") if isinstance(resource_point, Mapping) else None
        receiver_parts = set(re.split(r"[.$]", receiver.casefold())) if isinstance(receiver, str) else set()
        receiver_type = (
            receiver.rsplit(".", 1)[-1].split("<", 1)[0].casefold()
            if isinstance(receiver, str)
            else ""
        )
        receiver_type_named = (
            len(receiver_type) >= 6
            and any(receiver_type in marker for marker in lowered_markers)
        )
        receiver_type_match = False
        operation = candidate.get("operation")
        semantic_marker_match = (
            operation == "netty_full_http_request_string_materialization"
            and any(
                "fullhttprequest" in re.sub(r"[^a-z0-9]", "", marker)
                and "string" in marker
                for marker in lowered_markers
            )
        )
        if isinstance(site, Mapping):
            site_file, site_line = site.get("file"), site.get("start_line")
            if isinstance(site_file, str) and isinstance(site_line, int):
                receiver_type_match = receiver_type_named and any(
                    isinstance(location, Mapping)
                    and isinstance(location.get("file"), str)
                    and Path(site_file).name == Path(str(location["file"])).name
                    for location in locations
                )
                for location in locations:
                    if not isinstance(location, Mapping):
                        continue
                    expected_file = location.get("file")
                    start, end = location.get("start_line"), location.get("end_line")
                    if (
                        isinstance(expected_file, str) and isinstance(start, int) and isinstance(end, int)
                        and (site_file.endswith(expected_file) or Path(site_file).name == Path(expected_file).name)
                        and start <= site_line <= end
                    ):
                        location_match = True
                        break
        if receiver_parts:
            receiver_owner_match = any(
                isinstance(location, Mapping)
                and isinstance(location.get("file"), str)
                and Path(str(location["file"])).stem.casefold() in receiver_parts
                for location in locations
            )
        if (
            location_match
            or receiver_owner_match
            or receiver_type_match
            or semantic_marker_match
            or any(marker in blob for marker in lowered_markers)
            or any(receiver in blob and operation in blob for receiver, operation in call_identities)
        ):
            matches.append(candidate)
    return matches


def compute_disposition(
    truth: Mapping[str, Any],
    artifacts: TargetArtifacts,
    *,
    error: str | None = None,
) -> dict[str, Any]:
    base = {
        "truth_id": truth.get("truth_id"),
        "record_id": truth.get("record_id"),
        "repository": truth.get("repository") or truth.get("app"),
        "dynamic_status": truth.get("status") or truth.get("dynamic_status"),
    }
    reason_codes: list[str] = []

    if error == "asset_missing":
        return {**base, "status": "asset_missing", "reason_codes": ["ASSET_SOURCE_OR_DATABASE_MISSING"]}

    if artifacts.run_status != "completed":
        error = artifacts.run_error or {}
        reason_codes.append("STAGE_FAILED" if not artifacts.entries else "STAGE_INCOMPLETE")
        if error.get("code"):
            reason_codes.append(str(error["code"]))
        return {**base, "status": "stage_failed", "reason_codes": reason_codes}

    entries = artifacts.entries
    if not entries and not artifacts.entry_gaps:
        return {**base, "status": "entry_only", "reason_codes": ["NO_ENTRY_FACTS"]}

    growth_matches = _match_growth(truth, artifacts.growth_candidates)
    growth_marker_ids = {
        str(item.get("growth_id")) for item in growth_matches if isinstance(item.get("growth_id"), str)
    }
    preferred_entry_ids = {
        str(link.get("entry_id"))
        for link in artifacts.links
        if link.get("growth_id") in growth_marker_ids and isinstance(link.get("entry_id"), str)
    }
    matched_entries = _canonical_matched_entries(
        _match_entries(truth, entries, preferred_entry_ids),
        _method(truth.get("entry")),
        preferred_entry_ids,
    )
    if (
        len(matched_entries) > 1
        and len({_entry_route(entry) for entry in matched_entries}) > 1
        and not _interposition_connects(matched_entries, artifacts.entry_interpositions)
    ):
        growth_linked_matches = [
            entry for entry in matched_entries
            if str(entry.get("entry_id")) in preferred_entry_ids
        ]
        if len(growth_linked_matches) == 1:
            matched_entries = growth_linked_matches
    entry_ids = [str(entry.get("entry_id")) for entry in matched_entries]
    if not matched_entries:
        gap_matches = _match_gap_entries(truth, artifacts.entry_gaps)
        if gap_matches:
            result = {
                **base,
                "status": "growth_only" if growth_matches else "entry_only",
                "reason_codes": ["ENTRY_DYNAMIC_REGISTRATION_UNPROVEN"],
                "matched_gap_ids": [str(gap.get("entry_id")) for gap in gap_matches],
            }
            if growth_matches:
                result["reason_codes"].append("GROWTH_SINK_MATCHED")
                result["matched_growth_ids"] = [str(item.get("growth_id")) for item in growth_matches]
            return result
        if growth_matches:
            return {
                **base,
                "status": "growth_only",
                "reason_codes": ["ENTRY_IDENTITY_NOT_MATCHED", "GROWTH_SINK_MATCHED"],
                "matched_growth_ids": [str(item.get("growth_id")) for item in growth_matches],
            }
        return {**base, "status": "entry_only", "reason_codes": ["ENTRY_IDENTITY_NOT_MATCHED"]}

    frameworks = {entry.get("framework") for entry in matched_entries}
    if frameworks - _SUPPORTED_FRAMEWORKS:
        return {
            **base,
            "status": "unsupported_scope",
            "reason_codes": ["UNSUPPORTED_ENTRY_FRAMEWORK", *sorted(str(f) for f in frameworks if f not in _SUPPORTED_FRAMEWORKS)],
            "matched_entry_ids": entry_ids,
        }
    if (
        len(matched_entries) > 1
        and len({_entry_route(entry) for entry in matched_entries}) > 1
        and not _interposition_connects(matched_entries, artifacts.entry_interpositions)
    ):
        return {
            **base,
            "status": "ambiguous_truth_match",
            "reason_codes": ["AMBIGUOUS_ENTRY_IDENTITY"],
            "matched_entry_ids": entry_ids,
        }

    matched_alias_ids = {_route_alias_identity(entry) for entry in matched_entries}
    # Production compresses method-level alias mappings to one candidate link.
    # Treat sibling routes declared by that exact registration as the same
    # E->G chain identity while retaining the truth-matched route IDs above.
    entry_id_set = {
        str(entry.get("entry_id"))
        for entry in entries
        if _route_alias_identity(entry) in matched_alias_ids
        and isinstance(entry.get("entry_id"), str)
    }
    if not growth_marker_ids:
        return {
            **base,
            "status": "entry_only",
            "reason_codes": ["GROWTH_IDENTITY_NOT_MATCHED"],
            "matched_entry_ids": entry_ids,
        }
    links = [
        link for link in artifacts.links
        if link.get("entry_id") in entry_id_set and link.get("growth_id") in growth_marker_ids
    ]
    linked_growth_ids = sorted({str(link.get("growth_id")) for link in links if isinstance(link.get("growth_id"), str)})
    if not linked_growth_ids:
        return {
            **base,
            "status": "association_missing",
            "reason_codes": ["GROWTH_SINK_MATCHED", "NO_ENTRY_ASSOCIATION"],
            "matched_entry_ids": entry_ids,
            "matched_growth_ids": sorted(growth_marker_ids),
        }

    growth_id_set = set(linked_growth_ids)
    flows = [flow for flow in artifacts.flow_proofs if flow.get("entry_id") in entry_id_set and flow.get("growth_id") in growth_id_set]
    findings = [finding for finding in artifacts.findings if finding.get("entry_id") in entry_id_set and finding.get("growth_id") in growth_id_set]

    if findings:
        verdicts = sorted({str(finding.get("verdict")) for finding in findings})
        return {
            **base,
            "status": "full_chain_finding",
            "reason_codes": ["FINDING_CERTIFICATE_BACKED"],
            "matched_entry_ids": entry_ids,
            "matched_growth_ids": linked_growth_ids,
            "matched_flow_ids": [str(flow.get("path_id")) for flow in flows],
            "matched_finding_ids": [str(finding.get("finding_id")) for finding in findings],
            "verdicts": verdicts,
        }

    if flows:
        proven = [flow for flow in flows if flow.get("confidence") == "proven"]
        if proven:
            return {
                **base,
                "status": "lifecycle_unknown",
                "reason_codes": ["FLOW_PROVEN", "NO_FINDING"],
                "matched_entry_ids": entry_ids,
                "matched_growth_ids": linked_growth_ids,
                "matched_flow_ids": [str(flow.get("path_id")) for flow in flows],
            }
        return {
            **base,
            "status": "flow_partial",
            "reason_codes": ["FLOW_PARTIAL_ONLY", "NO_FINDING"],
            "matched_entry_ids": entry_ids,
            "matched_growth_ids": linked_growth_ids,
            "matched_flow_ids": [str(flow.get("path_id")) for flow in flows],
        }

    # Links exist but no flow proof and no finding.
    verified = [item for item in artifacts.verified_growth if item.get("growth_id") in growth_id_set]
    if verified:
        return {
            **base,
            "status": "flow_partial",
            "reason_codes": ["GROWTH_VERIFIED", "NO_FLOW_PROOF"],
            "matched_entry_ids": entry_ids,
            "matched_growth_ids": linked_growth_ids,
        }
    return {
        **base,
        "status": "entry_and_growth_linked",
        "reason_codes": ["ASSOCIATION_LINKED", "GROWTH_NOT_VERIFIED"],
        "matched_entry_ids": entry_ids,
        "matched_growth_ids": linked_growth_ids,
    }


__all__ = ["DISPOSITION_STATUSES", "TargetArtifacts", "compute_disposition"]
