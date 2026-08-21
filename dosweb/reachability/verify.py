from __future__ import annotations

from collections.abc import Iterable

from dosweb.errors import AnalyzerError
from dosweb.reachability.models import AuthContract, EntrySecurityFact, ReachabilityDecision


def verify_auth_contract(entry_id: str, contract: AuthContract, facts: Iterable[EntrySecurityFact], *, slice_fact_ids: frozenset[str]) -> ReachabilityDecision:
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
                (expected == "unauthenticated" and fact.value in {"unauthenticated_annotation", "unauthenticated_filter", "unauthenticated_configuration"}) or
                (expected == "low_privilege" and fact.value in {"low_privilege_annotation", "low_privilege_filter", "low_privilege_configuration"})
            )
            for fact in cited
        )
        context = expected if supported else "unknown"
    elif contract.auth_context == "privileged":
        context = "privileged" if any(fact.coverage == "complete" and fact.value in {"privileged_annotation", "privileged_filter", "privileged_constraint", "privileged_configuration"} for fact in cited) else "unknown"
    else:
        context = "unknown"
    contract_id = "auth_contract:" + __import__("hashlib").sha256((entry_id + repr(contract.to_dict())).encode()).hexdigest()
    status = "ordinary_attacker_reachable" if context in {"unauthenticated", "low_privilege"} else "not_entry_reachable" if context == "privileged" else "unknown"
    return ReachabilityDecision(entry_id, contract_id, context, status, contract.evidence_ids)
