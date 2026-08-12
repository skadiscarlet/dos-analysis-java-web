"""Fail-closed deterministic matching between truth cases and static candidates."""
from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlsplit

STATUSES = (
    "hit",
    "matched_static_unknown",
    "matched_bounded",
    "no_candidate",
    "ambiguous",
    "target_not_run",
    "artifact_missing",
    "truth_invalid",
    "entry_hit",
    "entry_ambiguous",
    "no_entry_match",
)
_VALID_VERDICTS = {
    "static_vulnerable": "hit",
    "static_unknown": "matched_static_unknown",
    "bounded_under_modeled_assumptions": "matched_bounded",
}
_METHOD = re.compile(r"^\s*(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|TRACE|CONNECT)\b", re.IGNORECASE)
_ROUTE = re.compile(r"(/[^\s,;]*)")
_PLACEHOLDER = re.compile(r"\{[^/{}]+\}")


def _text(value: object) -> str:
    return "" if value is None else str(value).strip().casefold()


def normalize_route(value: object) -> str:
    text = "" if value is None else str(value).strip()
    match = _ROUTE.search(text)
    if not match:
        return ""
    route = match.group(1).rstrip(".,)")
    route = urlsplit(route).path
    route = re.sub(r"/+", "/", route)
    route = _PLACEHOLDER.sub("{}", route)
    return route.rstrip("/") or "/"


def _method(value: object) -> str:
    match = _METHOD.search("" if value is None else str(value))
    return match.group(1).upper() if match else ""


def _protocol(value: object) -> str:
    text = _text(value)
    if "grpc" in text:
        return "grpc"
    if "mqtt" in text:
        return "mqtt"
    if "tcp" in text:
        return "tcp"
    if "http" in text or normalize_route(value):
        return "http"
    return ""


def _candidate_route(candidate: Mapping[str, Any]) -> object:
    route = candidate.get("route_or_event")
    if route is not None:
        return route
    entry = candidate.get("entry")
    return entry.get("route_or_event") if isinstance(entry, Mapping) else None


def _candidate_method(candidate: Mapping[str, Any]) -> str:
    return _method(_candidate_route(candidate))


def _score(truth: Mapping[str, Any], candidate: Mapping[str, Any]) -> tuple[int, list[str]]:
    finding_id = _text(truth.get("finding_id"))
    finding = candidate.get("finding")
    if not isinstance(finding, Mapping):
        return 0, []
    reasons: list[str] = []
    score = 0
    if finding_id and _text(finding.get("finding_id")) == finding_id:
        score += 100
        reasons.append("finding_id")

    truth_route = normalize_route(truth.get("entry"))
    candidate_route = normalize_route(_candidate_route(candidate))
    if truth_route and candidate_route:
        if truth_route != candidate_route:
            return 0, []
        score += 40
        reasons.append("route")
    truth_method = _method(truth.get("entry"))
    candidate_method = _candidate_method(candidate)
    if truth_method:
        if candidate_method and truth_method != candidate_method:
            return 0, []
        if candidate_method:
            score += 10
            reasons.append("method")
    truth_protocol = _protocol(truth.get("entry"))
    candidate_protocol = _text(candidate.get("protocol")) or _protocol(
        _candidate_route(candidate)
    )
    if truth_protocol:
        if candidate_protocol != truth_protocol:
            return 0, []
        score += 5
        reasons.append("protocol")

    return score, reasons


def match_case(
    truth: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
    *,
    error: str | None = None,
) -> dict[str, Any]:
    base = {
        "case_id": truth.get("case_id"),
        "repository": truth.get("repository"),
        "truth_id": truth.get("truth_id"),
    }
    if error:
        status = error if error in {"target_not_run", "artifact_missing"} else "truth_invalid"
        return {**base, "status": status, "candidate_ids": [], "reason": error}
    if not isinstance(truth.get("case_id"), str) or not isinstance(truth.get("repository"), str):
        return {**base, "status": "truth_invalid", "candidate_ids": [], "reason": "truth_shape"}
    same_repo = [
        candidate
        for candidate in candidates
        if _text(candidate.get("repository")) == _text(truth.get("repository"))
    ]
    if any(candidate.get("verdict") not in _VALID_VERDICTS for candidate in same_repo):
        return {
            **base,
            "status": "truth_invalid",
            "candidate_ids": [],
            "reason": "invalid_candidate_verdict",
        }
    scored = []
    for candidate in same_repo:
        score, reasons = _score(truth, candidate)
        if score > 0 and ("finding_id" in reasons or "route" in reasons):
            scored.append((score, candidate, reasons))
    scored.sort(key=lambda row: (-row[0], str(row[1].get("candidate_id"))))
    if not scored:
        return {**base, "status": "no_candidate", "candidate_ids": []}
    best = scored[0][0]
    winners = [row for row in scored if row[0] == best]
    if len(winners) != 1:
        return {
            **base,
            "status": "ambiguous",
            "candidate_ids": [row[1].get("candidate_id") for row in winners],
        }
    _, winner, reasons = winners[0]
    return {
        **base,
        "status": _VALID_VERDICTS[winner["verdict"]],
        "candidate_ids": [winner.get("candidate_id")],
        "match_evidence": reasons,
        "candidate": winner,
    }


def _protocol_event(value: object) -> str:
    text = _text(value)
    return "mqtt_protocol" if "mqtt" in text and any(
        marker in text for marker in ("protocol", "broker", "service")
    ) else ""


def _entry_identity(value: Mapping[str, Any]) -> tuple[str, str, str, str]:
    entry = value.get("entry") if isinstance(value.get("entry"), Mapping) else value
    route_or_event = entry.get("route_or_event") if isinstance(entry, Mapping) else None
    protocol = entry.get("protocol") if isinstance(entry, Mapping) else value.get("protocol")
    route = normalize_route(route_or_event)
    method = _method(route_or_event)
    protocol_name = _protocol(protocol or route_or_event)
    if not route and not method and protocol_name == "mqtt":
        route = _protocol_event(route_or_event) or _protocol_event(value.get("entry"))
    return (_text(value.get("repository")), route, method, protocol_name)


def _registration_identity(value: Mapping[str, Any]) -> tuple[str, str, str, int] | None:
    entry = value.get("entry")
    registration = entry.get("registration") if isinstance(entry, Mapping) else None
    if not isinstance(registration, Mapping):
        return None
    kind = _text(registration.get("kind"))
    callable_name = _text(registration.get("callable"))
    file_name = _text(registration.get("file"))
    start_line = registration.get("start_line")
    if not kind or not callable_name or not file_name or not isinstance(start_line, int):
        return None
    return (kind, callable_name, file_name, start_line)


def match_entry_case(
    truth: Mapping[str, Any],
    entries: list[Mapping[str, Any]],
    *,
    error: str | None = None,
) -> dict[str, Any]:
    base = {"case_id": truth.get("case_id"), "repository": truth.get("repository"), "truth_id": truth.get("truth_id")}
    if error:
        return {**base, "status": error if error in {"target_not_run", "artifact_missing"} else "artifact_missing", "entry_ids": [], "reason": error}
    if not isinstance(truth.get("case_id"), str) or not isinstance(truth.get("repository"), str):
        return {**base, "status": "no_entry_match", "entry_ids": [], "reason": "truth_shape"}
    truth_key = _entry_identity({"repository": truth.get("repository"), "entry": {"route_or_event": truth.get("entry"), "protocol": _protocol(truth.get("entry"))}})
    is_http_identity = bool(truth_key[1] and truth_key[3] == "http")
    is_grpc_identity = bool(truth_key[1] and truth_key[3] == "grpc")
    is_protocol_identity = bool(truth_key[1] == "mqtt_protocol" and not truth_key[2] and truth_key[3] == "mqtt")
    if not (is_http_identity or is_grpc_identity or is_protocol_identity):
        return {**base, "status": "no_entry_match", "entry_ids": [], "reason": "truth_entry_identity_incomplete"}
    matches = []
    for entry in entries:
        candidate_key = _entry_identity(entry)
        if candidate_key[0] != truth_key[0] or candidate_key[1] != truth_key[1] or candidate_key[3] != truth_key[3]:
            continue
        if truth_key[2] and candidate_key[2] and truth_key[2] != candidate_key[2]:
            continue
        matches.append(entry)
    matches.sort(key=lambda row: str((row.get("entry") or {}).get("entry_id", "")))
    ids = [((row.get("entry") or {}).get("entry_id")) for row in matches]
    if len(matches) == 1:
        return {**base, "status": "entry_hit", "entry_ids": ids, "entry": matches[0].get("entry")}
    if matches:
        registrations = {_registration_identity(row) for row in matches}
        if None not in registrations and len(registrations) == 1:
            return {
                **base,
                "status": "entry_hit",
                "entry_ids": ids,
                "entry": matches[0].get("entry"),
                "merged_entry_ids": ids[1:],
            }
        return {**base, "status": "entry_ambiguous", "entry_ids": ids}
    return {**base, "status": "no_entry_match", "entry_ids": []}


def match_entry_cases(
    truth_rows: list[Mapping[str, Any]],
    entries_by_repo: Mapping[str, tuple[list[Mapping[str, Any]], str | None]],
) -> list[dict[str, Any]]:
    result = []
    for truth in truth_rows:
        key = _text(truth.get("repository"))
        entries, error = entries_by_repo.get(key, ([], "target_not_run"))
        result.append(match_entry_case(truth, entries, error=error))
    return result


def match_cases(
    truth_rows: list[Mapping[str, Any]],
    candidates_by_repo: Mapping[str, tuple[list[Mapping[str, Any]], str | None]],
) -> list[dict[str, Any]]:
    result = []
    for truth in truth_rows:
        key = _text(truth.get("repository"))
        candidates, error = candidates_by_repo.get(key, ([], "target_not_run"))
        result.append(match_case(truth, candidates, error=error))
    return result
