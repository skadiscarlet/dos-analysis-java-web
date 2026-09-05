"""Post-hoc benchmark and open-discovery evaluation."""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any, Mapping

from dosweb.benchmark.truth import normalize_repo

_MATCHED = {"hit", "matched_static_unknown", "matched_bounded"}
_INELIGIBLE = {"target_not_run", "artifact_missing", "truth_invalid"}
_NON_LINKING_SEED_STATUSES = {
    "no_candidate",
    "target_not_run",
    "artifact_missing",
    "truth_invalid",
    "entry_hit",
    "entry_ambiguous",
    "no_entry_match",
    "stage_failed",
    "entry_only",
    "asset_missing",
    "unsupported_scope",
}
_SEED_STATUSES = _MATCHED | _NON_LINKING_SEED_STATUSES | {
    "ambiguous",
    "full_chain_finding",
    "entry_and_growth_linked",
    "growth_only",
    "association_missing",
    "flow_partial",
    "lifecycle_unknown",
    "ambiguous_truth_match",
}
_DISCOVERY_DISPOSITION_STATUSES = {
    "formal_eligible",
    "gap_eligible",
    "rejected",
    "inventory_unresolved",
}
_STATIC_VERDICTS = {
    "static_vulnerable",
    "bounded_under_modeled_assumptions",
    "static_unknown",
}
_ORDINARY_MATCHED_VERDICTS = {
    "hit": "static_vulnerable",
    "matched_static_unknown": "static_unknown",
    "matched_bounded": "bounded_under_modeled_assumptions",
}
_NEGATIVE_PROOF_KINDS = {
    "server_controlled_source",
    "non_retained_owner",
    "finite_keyspace",
    "generated_or_test_only",
    "guaranteed_synchronous_cleanup",
    "effective_local_bound",
    "false_entry_growth_flow",
    "not_entry_reachable",
}
_REPOSITORY_SCOPE_ALIASES = ("batch_target_name", "repository")
OPEN_DISCOVERY_CLASSES = (
    "seed_linked_static_vulnerable",
    "novel_static_vulnerable",
    "novel_bounded",
    "source_proven_negative",
    "unresolved_discovery",
)


def evaluate_matches(
    matches: list[Mapping[str, Any]],
    *,
    truth_valid: bool = True,
    oracle_total: int = 29,
    repository_total: int = 18,
) -> dict[str, Any]:
    status_counts = Counter(str(row.get("status")) for row in matches)
    eligible = sum(1 for row in matches if row.get("status") not in _INELIGIBLE)
    hits = status_counts["hit"]
    matched_any = sum(status_counts[status] for status in _MATCHED)
    targets_completed = len(
        {
            str(row.get("repository"))
            for row in matches
            if row.get("status") not in {"target_not_run", "artifact_missing"}
        }
    )
    metrics = {
        "positive_recall": hits / eligible if eligible else 0.0,
        "global_recall": hits / oracle_total if oracle_total else 0.0,
        "matched_any_rate": matched_any / eligible if eligible else 0.0,
    }
    return {
        "schema_version": 1,
        "truth_valid": truth_valid,
        "oracle_total": oracle_total,
        "repository_total": repository_total,
        "eligible": eligible,
        "hits": hits,
        "targets_completed": targets_completed,
        "status_counts": dict(sorted(status_counts.items())),
        "metrics": metrics,
    }


def _claim_analysis_id(
    owners: dict[str, dict[str, str]], key: str, value: Any, scope: str
) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"open discovery {key} is missing or invalid")
    owner = owners.setdefault(key, {}).get(value)
    if owner is not None and owner != scope:
        raise ValueError(f"open discovery {key} has cross-repository ID reuse")
    owners[key][value] = scope
    return value


def _record_index(
    records: Sequence[Mapping[str, Any]],
    key: str,
    owners: dict[str, dict[str, str]],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("open discovery record must be a JSON object")
        scope = _record_scope(record)
        value = _claim_analysis_id(owners, key, record.get(key), scope)
        identity = (scope, value)
        if identity in result:
            raise ValueError(f"open discovery {key} is duplicated")
        result[identity] = record
    return result


def _record_target(record: Mapping[str, Any]) -> str:
    return _record_scope(record)


def _record_scope(record: Mapping[str, Any]) -> str:
    aliases = [
        (key, record[key]) for key in _REPOSITORY_SCOPE_ALIASES if key in record
    ]
    if not aliases:
        raise ValueError("open discovery repository scope is missing")
    normalized: list[str] = []
    for key, value in aliases:
        try:
            normalized.append(normalize_repo(value))
        except ValueError as exc:
            raise ValueError(
                f"open discovery repository scope alias {key} is invalid"
            ) from exc
    if len(set(normalized)) != 1:
        raise ValueError("open discovery repository scope aliases conflict")
    return normalized[0]


def _strict_id_list(
    record: Mapping[str, Any], key: str, *, required: bool = False
) -> list[str]:
    if key not in record:
        if required:
            raise ValueError(f"open discovery {key} must be a JSON list")
        return []
    values = record.get(key)
    if (
        not isinstance(values, list)
        or any(not isinstance(value, str) or not value for value in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError(
            f"open discovery {key} must be a JSON list of unique non-empty strings"
        )
    return list(values)


def _optional_nested_id(
    record: Mapping[str, Any], container_key: str, key: str
) -> set[str]:
    if container_key not in record or record.get(container_key) is None:
        return set()
    container = record.get(container_key)
    if not isinstance(container, Mapping):
        raise ValueError(f"open discovery seed {container_key} is malformed")
    value = container.get(key)
    if value is None:
        return set()
    if not isinstance(value, str) or not value:
        raise ValueError(f"open discovery seed {container_key}.{key} is malformed")
    return {value}


def _candidate_nested_id(
    record: Mapping[str, Any], container_key: str, key: str
) -> set[str]:
    if "candidate" not in record or record.get("candidate") is None:
        return set()
    candidate = record.get("candidate")
    if not isinstance(candidate, Mapping):
        raise ValueError("open discovery seed candidate is malformed")
    return _optional_nested_id(candidate, container_key, key)


def _seed_identity(match: Mapping[str, Any]) -> str:
    for key in ("record_id", "case_id", "truth_id"):
        if key in match:
            value = match.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"open discovery seed {key} identity is invalid")
            return value
    raise ValueError("open discovery seed identity is invalid")


def _seed_id_carriers(match: Mapping[str, Any]) -> list[dict[str, Any]]:
    carriers = [
        {
            "name": "matched_ids",
            "finding_ids": set(_strict_id_list(match, "matched_finding_ids")),
            "growth_ids": set(_strict_id_list(match, "matched_growth_ids")),
        },
        {
            "name": "chain",
            "finding_ids": _optional_nested_id(match, "chain", "finding_id"),
            "growth_ids": _optional_nested_id(match, "chain", "growth_id"),
        },
        {
            "name": "candidate",
            "finding_ids": _candidate_nested_id(match, "finding", "finding_id"),
            "growth_ids": _candidate_nested_id(match, "growth", "growth_id"),
        },
    ]
    return [
        carrier
        for carrier in carriers
        if carrier["finding_ids"] or carrier["growth_ids"]
    ]


def _validate_seed_carriers(
    carriers: Sequence[Mapping[str, Any]],
    *,
    scope: str,
    finding_by_id: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    for carrier in carriers:
        finding_ids = carrier["finding_ids"]
        growth_ids = carrier["growth_ids"]
        if finding_ids and growth_ids:
            mapped_growth_ids = {
                str(finding_by_id[(scope, finding_id)]["growth_id"])
                for finding_id in finding_ids
                if (scope, finding_id) in finding_by_id
            }
            if not mapped_growth_ids.issubset(growth_ids):
                raise ValueError(
                    f"open discovery seed {carrier['name']} carrier has a conflicting finding/Growth chain"
                )
    adjacency: list[set[int]] = [set() for _ in carriers]
    for index, left in enumerate(carriers):
        for right_index, right in enumerate(carriers[index + 1 :], index + 1):
            shares_compatible_dimension = False
            for key in ("finding_ids", "growth_ids"):
                left_ids = left[key]
                right_ids = right[key]
                if left_ids and right_ids:
                    if not (
                        left_ids.issubset(right_ids)
                        or right_ids.issubset(left_ids)
                    ):
                        raise ValueError(
                            f"open discovery seed {left['name']}/{right['name']} carriers conflict"
                        )
                    shares_compatible_dimension = True
            if shares_compatible_dimension:
                adjacency[index].add(right_index)
                adjacency[right_index].add(index)
    if len(carriers) > 1:
        reachable = {0}
        pending = [0]
        while pending:
            current = pending.pop()
            for neighbor in adjacency[current] - reachable:
                reachable.add(neighbor)
                pending.append(neighbor)
        if len(reachable) != len(carriers):
            raise ValueError(
                "open discovery seed equivalent carriers are disconnected"
            )


def _seed_links(
    seed_matches: Sequence[Mapping[str, Any]],
    *,
    finding_by_id: Mapping[tuple[str, str], Mapping[str, Any]],
    disposition_by_growth: Mapping[tuple[str, str], Mapping[str, Any]],
    analysis_id_owners: dict[str, dict[str, str]],
) -> tuple[
    dict[tuple[str, str], set[str]],
    dict[tuple[str, str], set[str]],
    list[dict[str, Any]],
]:
    by_finding: dict[tuple[str, str], set[str]] = {}
    by_growth: dict[tuple[str, str], set[str]] = {}
    validated: list[dict[str, Any]] = []
    seen_identities: set[tuple[str, str]] = set()
    for match in seed_matches:
        if not isinstance(match, Mapping):
            raise ValueError("open discovery seed record must be a JSON object")
        scope = _record_scope(match)
        seed_id = _seed_identity(match)
        identity = (scope, seed_id)
        if identity in seen_identities:
            raise ValueError("open discovery scoped seed identity is duplicated")
        seen_identities.add(identity)
        status = match.get("status")
        if not isinstance(status, str) or status not in _SEED_STATUSES:
            raise ValueError("open discovery seed status is invalid")
        carriers = _seed_id_carriers(match)
        _validate_seed_carriers(
            carriers,
            scope=scope,
            finding_by_id=finding_by_id,
        )
        finding_ids = {
            finding_id
            for carrier in carriers
            for finding_id in carrier["finding_ids"]
        }
        growth_ids = {
            growth_id
            for carrier in carriers
            for growth_id in carrier["growth_ids"]
        }
        if status in _NON_LINKING_SEED_STATUSES and (finding_ids or growth_ids):
            raise ValueError(
                "open discovery non-linking seed status carries stale concrete IDs"
            )
        for key, values in (
            ("finding_id", finding_ids),
            ("growth_id", growth_ids),
        ):
            for value in values:
                _claim_analysis_id(analysis_id_owners, key, value, scope)
        known_findings = {
            finding_id: finding_by_id[(scope, finding_id)]
            for finding_id in finding_ids
            if (scope, finding_id) in finding_by_id
        }
        expected_verdict = _ORDINARY_MATCHED_VERDICTS.get(str(status))
        if expected_verdict is not None and any(
            finding.get("verdict") != expected_verdict
            for finding in known_findings.values()
        ):
            raise ValueError(
                "open discovery ordinary matched seed status conflicts with its finding verdict"
            )
        if finding_ids and growth_ids and known_findings:
            expected_growth_ids = {
                str(finding["growth_id"]) for finding in known_findings.values()
            }
            if not expected_growth_ids.issubset(growth_ids):
                raise ValueError(
                    "open discovery seed finding and Growth IDs must bind the same analysis chain"
                )
        validated.append({
            "scope": scope,
            "seed_id": seed_id,
            "status": status,
            "finding_ids": finding_ids,
            "growth_ids": growth_ids,
        })
    for seed in validated:
        scope = str(seed["scope"])
        seed_id = str(seed["seed_id"])
        finding_ids = seed["finding_ids"]
        growth_ids = seed["growth_ids"]
        status = seed["status"]
        if status in _NON_LINKING_SEED_STATUSES:
            continue
        for finding_id in finding_ids:
            if (scope, finding_id) in finding_by_id:
                by_finding.setdefault((scope, finding_id), set()).add(seed_id)
        for growth_id in growth_ids:
            if (scope, growth_id) in disposition_by_growth:
                by_growth.setdefault((scope, growth_id), set()).add(seed_id)
    return by_finding, by_growth, validated


def evaluate_open_discovery(
    *,
    findings: Sequence[Mapping[str, Any]],
    dispositions: Sequence[Mapping[str, Any]],
    negative_proofs: Sequence[Mapping[str, Any]],
    seed_matches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Classify all post-scan findings/inventory after subtracting PoC seeds.

    Production artifacts never receive a ``novel`` label.  Seed linkage is
    computed here, after the scan.  An unmatched static positive is therefore
    a novel validation candidate, never an automatic false positive.
    """

    analysis_id_owners: dict[str, dict[str, str]] = {}
    finding_by_id = _record_index(findings, "finding_id", analysis_id_owners)
    disposition_by_id = _record_index(
        dispositions, "disposition_id", analysis_id_owners
    )
    proof_by_id = _record_index(
        negative_proofs, "negative_proof_id", analysis_id_owners
    )
    for proof in proof_by_id.values():
        scope = _record_scope(proof)
        _claim_analysis_id(
            analysis_id_owners, "growth_id", proof.get("growth_id"), scope
        )
        kind = proof.get("kind")
        if not isinstance(kind, str) or kind not in _NEGATIVE_PROOF_KINDS:
            raise ValueError("open discovery negative proof kind is invalid")
    dispositions_by_growth: dict[tuple[str, str], Mapping[str, Any]] = {}
    proof_reference_counts: Counter[tuple[str, str]] = Counter()
    for disposition in disposition_by_id.values():
        status = disposition.get("status")
        if (
            not isinstance(status, str)
            or status not in _DISCOVERY_DISPOSITION_STATUSES
        ):
            raise ValueError("open discovery disposition status is invalid")
        proof_ids = _strict_id_list(
            disposition, "negative_proof_ids", required=True
        )
        scope = _record_scope(disposition)
        growth_id = _claim_analysis_id(
            analysis_id_owners, "growth_id", disposition.get("growth_id"), scope
        )
        growth_key = (scope, growth_id)
        if growth_key in dispositions_by_growth:
            raise ValueError("open discovery growth disposition is missing or duplicated")
        if status == "rejected":
            if not proof_ids:
                raise ValueError(
                    "open discovery rejected disposition requires a negative proof"
                )
            for proof_id in proof_ids:
                proof_key = (scope, proof_id)
                proof = proof_by_id.get(proof_key)
                if proof is None:
                    raise ValueError(
                        "open discovery rejected disposition references a missing negative proof"
                    )
                if proof.get("growth_id") != growth_id:
                    raise ValueError(
                        "open discovery negative proof Growth ownership is inconsistent"
                    )
                proof_reference_counts[proof_key] += 1
        elif proof_ids:
            raise ValueError(
                "open discovery non-rejected disposition carries a negative proof"
            )
        dispositions_by_growth[growth_key] = disposition
    for proof_key in proof_by_id:
        if proof_reference_counts[proof_key] != 1:
            raise ValueError(
                "open discovery negative proof must be referenced exactly once by its same-Growth rejected disposition"
            )

    for finding in finding_by_id.values():
        scope = _record_scope(finding)
        growth_id = _claim_analysis_id(
            analysis_id_owners, "growth_id", finding.get("growth_id"), scope
        )
        verdict = finding.get("verdict")
        if not isinstance(verdict, str) or verdict not in _STATIC_VERDICTS:
            raise ValueError("open discovery finding static verdict is invalid")
        disposition = dispositions_by_growth.get((scope, growth_id))
        if disposition is None:
            raise ValueError("open discovery finding growth disposition is missing")
        status = disposition.get("status")
        if status not in {"formal_eligible", "gap_eligible"}:
            raise ValueError(
                "open discovery finding may bind only a formal or gap disposition"
            )
        if status == "gap_eligible" and verdict != "static_unknown":
            raise ValueError(
                "open discovery gap disposition may emit only static_unknown"
            )

    seed_by_finding, seed_by_growth, seeds = _seed_links(
        seed_matches,
        finding_by_id=finding_by_id,
        disposition_by_growth=dispositions_by_growth,
        analysis_id_owners=analysis_id_owners,
    )

    def make_row(
        *,
        discovery_id: str,
        target: str,
        scope: str,
        growth_id: str,
        finding: Mapping[str, Any] | None,
        disposition: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        finding_id = finding.get("finding_id") if finding is not None else None
        verdict = finding.get("verdict") if finding is not None else None
        seed_ids = sorted(
            seed_by_finding.get((scope, str(finding_id)), set())
            | seed_by_growth.get((scope, growth_id), set())
        )
        disposition_status = disposition.get("status") if disposition is not None else None
        proof_ids = (
            disposition["negative_proof_ids"]
            if disposition is not None
            else []
        )
        if disposition_status == "rejected":
            classification = "source_proven_negative"
        elif disposition_status == "inventory_unresolved":
            classification = "unresolved_discovery"
        elif verdict == "static_vulnerable":
            classification = (
                "seed_linked_static_vulnerable"
                if seed_ids
                else "novel_static_vulnerable"
            )
        elif verdict == "bounded_under_modeled_assumptions" and not seed_ids:
            classification = "novel_bounded"
        else:
            classification = "unresolved_discovery"
        return {
            "discovery_id": discovery_id,
            "target": target or None,
            "finding_id": finding_id,
            "growth_id": growth_id,
            "disposition_id": (
                disposition.get("disposition_id") if disposition is not None else None
            ),
            "static_verdict": verdict,
            "disposition_status": disposition_status,
            "negative_proof_ids": list(proof_ids),
            "seed_ids": seed_ids,
            "classification": classification,
            "recall_miss": False,
            "seed_status": None,
        }

    rows: list[dict[str, Any]] = []
    finding_growth_ids: set[tuple[str, str]] = set()
    for (scope, finding_id), finding in finding_by_id.items():
        growth_id = str(finding["growth_id"])
        growth_key = (scope, growth_id)
        disposition = dispositions_by_growth.get(growth_key)
        assert disposition is not None
        finding_growth_ids.add(growth_key)
        target = _record_target(finding)
        rows.append(
            make_row(
                discovery_id=f"{scope}::{finding_id}" if scope else finding_id,
                target=target,
                scope=scope,
                growth_id=growth_id,
                finding=finding,
                disposition=disposition,
            )
        )
    for (scope, growth_id), disposition in dispositions_by_growth.items():
        if (scope, growth_id) not in finding_growth_ids:
            target = _record_target(disposition)
            local_id = str(disposition["disposition_id"])
            rows.append(
                make_row(
                    discovery_id=f"{scope}::{local_id}" if scope else local_id,
                    target=target,
                    scope=scope,
                    growth_id=growth_id,
                    finding=None,
                    disposition=disposition,
                )
            )
    linked_seed_ids = {
        (str(row["target"]), seed_id)
        for row in rows
        for seed_id in row["seed_ids"]
    }
    for seed in seeds:
        scope = str(seed["scope"])
        seed_id = str(seed["seed_id"])
        if (scope, seed_id) in linked_seed_ids:
            continue
        rows.append({
            "discovery_id": f"{scope}::seed::{seed_id}",
            "target": scope,
            "finding_id": None,
            "growth_id": None,
            "disposition_id": None,
            "static_verdict": None,
            "disposition_status": None,
            "negative_proof_ids": [],
            "seed_ids": [seed_id],
            "classification": "unresolved_discovery",
            "recall_miss": True,
            "seed_status": seed["status"],
        })
    rows.sort(key=lambda row: (str(row["target"]), str(row["discovery_id"])))
    counts = Counter(str(row["classification"]) for row in rows)
    return {
        "schema_version": 1,
        "discoveries": rows,
        "category_counts": {
            category: counts[category] for category in OPEN_DISCOVERY_CLASSES
        },
    }
