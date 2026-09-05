from __future__ import annotations

from dosweb.reachability import EntrySecurityFact
from dosweb.reachability.verify import derive_auth_contract_from_facts
from tests.support.mock_deepseek import auth_unauthenticated_from_facts


def _fact(entry_id: str, kind: str, value: str, coverage: str = "complete") -> EntrySecurityFact:
    return EntrySecurityFact(entry_id, kind, "src/Handler.java", 10, value, coverage)


def test_complete_unique_auth_fact_is_derived_without_provider() -> None:
    entry_id = "entry:fixture"
    deployment = _fact(entry_id, "deployment_gate", "default_enabled")
    auth = _fact(entry_id, "annotation", "unauthenticated_annotation")

    contract = derive_auth_contract_from_facts(entry_id, (deployment, auth))

    assert contract is not None
    assert contract.auth_context == "unauthenticated"
    assert contract.evidence_ids == (auth.fact_id,)
    assert contract.confidence == "high"


def test_partial_missing_or_conflicting_auth_facts_require_provider() -> None:
    entry_id = "entry:fixture"
    assert derive_auth_contract_from_facts(
        entry_id,
        (_fact(entry_id, "annotation", "unauthenticated_annotation", "partial"),),
    ) is None
    assert derive_auth_contract_from_facts(
        entry_id,
        (
            _fact(entry_id, "annotation", "unauthenticated_annotation"),
            _fact(entry_id, "filter", "privileged_filter"),
        ),
    ) is None


def test_scripted_auth_fixture_finds_unique_complete_fact_after_deployment_fact() -> None:
    request = {
        "input": [{
            "content": [{
                "text": __import__("json").dumps({
                    "security_facts": [
                        {"fact_id": "security:1", "coverage": "complete", "value": "default_enabled"},
                        {"fact_id": "security:2", "coverage": "complete", "value": "unauthenticated_annotation"},
                    ]
                })
            }]
        }]
    }

    assert auth_unauthenticated_from_facts(request) == {
        "auth_context": "unauthenticated",
        "evidence_ids": ["security:2"],
        "assumptions": [],
        "confidence": "high",
    }
