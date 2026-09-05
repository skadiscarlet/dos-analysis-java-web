from __future__ import annotations

from collections.abc import Iterable

from dosweb.configuration.models import ModeledConfigurationFact
from dosweb.errors import AnalyzerError
from dosweb.reachability.extract import resolve_deployment_status
from dosweb.reachability.models import AuthContract, EntrySecurityFact, ReachabilityDecision


_AUTH_CONTEXT_BY_FACT = {
    ("annotation", "unauthenticated_annotation"): "unauthenticated",
    ("annotation", "low_privilege_annotation"): "low_privilege",
    ("annotation", "privileged_annotation"): "privileged",
    ("servlet_constraint", "unauthenticated_constraint"): "unauthenticated",
    ("servlet_constraint", "privileged_constraint"): "privileged",
    ("security_filter_chain", "unauthenticated_filter"): "unauthenticated",
    ("security_filter_chain", "low_privilege_filter"): "low_privilege",
    ("security_filter_chain", "privileged_filter"): "privileged",
    ("filter", "unauthenticated_filter"): "unauthenticated",
    ("filter", "low_privilege_filter"): "low_privilege",
    ("filter", "privileged_filter"): "privileged",
    ("configuration", "unauthenticated_configuration"): "unauthenticated",
    ("configuration", "low_privilege_configuration"): "low_privilege",
    ("configuration", "privileged_configuration"): "privileged",
}
_AUTH_CONTEXT_ORDER = ("unauthenticated", "low_privilege", "privileged")
_DEPLOYMENT_STATUS_ORDER = (
    "default_enabled",
    "default_disabled",
    "optional",
    "unknown",
)
_MAX_DECISION_EVIDENCE_IDS = 32


def _auth_context_for_fact(fact: EntrySecurityFact) -> str | None:
    return _AUTH_CONTEXT_BY_FACT.get((fact.kind, fact.value))


def derive_auth_contract_from_facts(
    entry_id: str,
    facts: Iterable[EntrySecurityFact],
) -> AuthContract | None:
    """Resolve a unique complete Auth Contract locally; conflicts stay unresolved."""
    supporting: dict[str, set[str]] = {}
    for fact in facts:
        if fact.entry_id != entry_id:
            continue
        if fact.kind != "deployment_gate" and fact.coverage in {
            "partial",
            "unsupported",
        }:
            return None
        if fact.coverage != "complete":
            continue
        context = _auth_context_for_fact(fact)
        if context is not None:
            supporting.setdefault(context, set()).add(fact.fact_id)
    if len(supporting) != 1:
        return None
    context, evidence_ids = next(iter(supporting.items()))
    return AuthContract(context, (min(evidence_ids),), (), "high")


def _bounded_decision_evidence(
    auth_coverage_gap_ids: set[str],
    auth_evidence: dict[str, set[str]],
    deployment_evidence: dict[str, set[str]],
    cited_evidence_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Keep semantic representatives first, then fill the fixed proof budget."""
    prioritized = (
        [min(auth_coverage_gap_ids)] if auth_coverage_gap_ids else []
    )
    prioritized.extend(
        min(auth_evidence[context])
        for context in _AUTH_CONTEXT_ORDER
        if context in auth_evidence
    )
    prioritized.extend(
        min(deployment_evidence[status])
        for status in _DEPLOYMENT_STATUS_ORDER
        if status in deployment_evidence
    )
    prioritized.extend(sorted(cited_evidence_ids))

    selected: list[str] = []
    seen: set[str] = set()
    for fact_id in prioritized:
        if fact_id in seen:
            continue
        selected.append(fact_id)
        seen.add(fact_id)
        if len(selected) == _MAX_DECISION_EVIDENCE_IDS:
            break
    return tuple(sorted(selected))


def verify_auth_contract(entry_id: str, contract: AuthContract, facts: Iterable[EntrySecurityFact], *, slice_fact_ids: frozenset[str], configuration_facts: Iterable[ModeledConfigurationFact] = ()) -> ReachabilityDecision:
    """Fail closed: a model can classify only facts supplied in the security slice."""
    indexed = {fact.fact_id: fact for fact in facts}
    if any(fact_id not in slice_fact_ids or fact_id not in indexed or indexed[fact_id].entry_id != entry_id for fact_id in contract.evidence_ids):
        raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Auth Contract cites a fact outside its bounded security slice.")
    # A cited complete fact must semantically support the claimed context.  The
    # provider cannot hide a conflicting complete fact by selectively citing a
    # compatible one from the same Entry slice.
    cited = tuple(indexed[item] for item in contract.evidence_ids)
    complete_auth_evidence: dict[str, set[str]] = {}
    auth_coverage_gap_ids: set[str] = set()
    for fact in indexed.values():
        if (
            fact.entry_id != entry_id
            or fact.fact_id not in slice_fact_ids
        ):
            continue
        if fact.kind != "deployment_gate" and fact.coverage in {
            "partial",
            "unsupported",
        }:
            auth_coverage_gap_ids.add(fact.fact_id)
        if fact.coverage != "complete":
            continue
        fact_context = _auth_context_for_fact(fact)
        if fact_context is not None:
            complete_auth_evidence.setdefault(fact_context, set()).add(fact.fact_id)
    auth_conflict = len(complete_auth_evidence) > 1
    if contract.auth_context in {"unauthenticated", "low_privilege"}:
        expected = contract.auth_context
        supported = any(
            fact.coverage == "complete"
            and _auth_context_for_fact(fact) == expected
            for fact in cited
        )
        context = expected if supported else "unknown"
    elif contract.auth_context == "privileged":
        context = "privileged" if any(fact.coverage == "complete" and _auth_context_for_fact(fact) == "privileged" for fact in cited) else "unknown"
    else:
        context = "unknown"
    if auth_conflict:
        context = "unknown"
    if auth_coverage_gap_ids:
        context = "unknown"
    deployment_facts = tuple(
        fact
        for fact in indexed.values()
        if fact.entry_id == entry_id
        and fact.kind == "deployment_gate"
        and fact.fact_id in slice_fact_ids
    )
    configuration_facts = tuple(configuration_facts)
    deployment = resolve_deployment_status(deployment_facts, configuration_facts)
    complete_deployment_evidence: dict[str, set[str]] = {}
    for fact in deployment_facts:
        if fact.coverage != "complete":
            continue
        fact_status = resolve_deployment_status((fact,), configuration_facts)
        complete_deployment_evidence.setdefault(fact_status, set()).add(fact.fact_id)
    reasons: set[str] = set()
    if auth_coverage_gap_ids:
        status = "unknown"
        reasons.add("REACH_AUTH_COVERAGE_PARTIAL")
        reasons.add("REACH_AUTH_UNKNOWN")
    elif context == "privileged":
        status = "not_entry_reachable"; reasons.add("REACH_PRIVILEGED")
    elif deployment == "default_disabled":
        status = "not_entry_reachable"; reasons.add("REACH_DEFAULT_DISABLED")
    elif deployment == "optional":
        status = "not_entry_reachable"; reasons.add("REACH_OPTIONAL_COMPONENT")
    elif context in {"unauthenticated", "low_privilege"} and deployment == "default_enabled":
        status = "ordinary_attacker_reachable"; reasons.add("REACH_ORDINARY_ATTACKER")
    else:
        status = "unknown"
        if context == "unknown": reasons.add("REACH_AUTH_UNKNOWN")
        if deployment == "unknown": reasons.add("REACH_DEPLOYMENT_UNKNOWN")
    if auth_conflict:
        reasons.add("REACH_AUTH_CONFLICT")
    contract_id = "auth_contract:" + __import__("hashlib").sha256((entry_id + repr(contract.to_dict())).encode()).hexdigest()
    evidence_ids = _bounded_decision_evidence(
        auth_coverage_gap_ids,
        complete_auth_evidence,
        complete_deployment_evidence,
        contract.evidence_ids,
    )
    return ReachabilityDecision(entry_id, contract_id, context, deployment, status, evidence_ids, tuple(sorted(reasons)))
