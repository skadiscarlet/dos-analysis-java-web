from __future__ import annotations

from collections.abc import Iterable

from dosweb.configuration.models import ModeledConfigurationFact
from dosweb.errors import AnalyzerError
from dosweb.reachability.extract import resolve_deployment_status
from dosweb.reachability.models import AuthContract, EntrySecurityFact, ReachabilityDecision


def verify_auth_contract(entry_id: str, contract: AuthContract, facts: Iterable[EntrySecurityFact], *, slice_fact_ids: frozenset[str], configuration_facts: Iterable[ModeledConfigurationFact] = ()) -> ReachabilityDecision:
    """Fail closed: a model can classify only facts supplied in the security slice."""
    indexed = {fact.fact_id: fact for fact in facts}
    if any(fact_id not in slice_fact_ids or fact_id not in indexed or indexed[fact_id].entry_id != entry_id for fact_id in contract.evidence_ids):
        raise AnalyzerError("LLM_RESPONSE_SCHEMA_INVALID", "Auth Contract cites a fact outside its bounded security slice.")
    # A cited complete fact must semantically support the claimed context.  Absence never proves public access.
    cited = tuple(indexed[item] for item in contract.evidence_ids)
    if contract.auth_context in {"unauthenticated", "low_privilege"}:
        expected = contract.auth_context
        supported = any(
            fact.coverage == "complete" and (
                (expected == "unauthenticated" and fact.value in {"unauthenticated_annotation", "unauthenticated_filter", "unauthenticated_constraint", "unauthenticated_configuration"}) or
                (expected == "low_privilege" and fact.value in {"low_privilege_annotation", "low_privilege_filter", "low_privilege_configuration"})
            )
            for fact in cited
        )
        context = expected if supported else "unknown"
    elif contract.auth_context == "privileged":
        context = "privileged" if any(fact.coverage == "complete" and fact.value in {"privileged_annotation", "privileged_filter", "privileged_constraint", "privileged_configuration"} for fact in cited) else "unknown"
    else:
        context = "unknown"
    deployment_facts = tuple(
        fact
        for fact in indexed.values()
        if fact.kind == "deployment_gate" and fact.fact_id in slice_fact_ids
    )
    deployment = resolve_deployment_status(deployment_facts, configuration_facts)
    reasons: set[str] = set()
    if context == "privileged":
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
    contract_id = "auth_contract:" + __import__("hashlib").sha256((entry_id + repr(contract.to_dict())).encode()).hexdigest()
    evidence_ids = tuple(sorted(set(contract.evidence_ids) | {fact.fact_id for fact in deployment_facts if fact.coverage == "complete"}))
    return ReachabilityDecision(entry_id, contract_id, context, deployment, status, evidence_ids, tuple(sorted(reasons)))
