"""The no-network fixture provider must obey the current production contract."""
import json
import pytest
from dosweb.growth.contracts import bind_provider_growth_contract, validate_contract_static_semantics, validate_provider_growth_contract
from dosweb.llm.prompts import build_provider_payload
from tests.support.mock_deepseek import growth_yes_from_slice
from tests.test_growth_contract_v5 import _large_single_request_slice

@pytest.mark.parametrize('kind', ['input_materialization','allocation'])
def test_scripted_complete_request_fact_set_preserves_mandatory_citations(kind):
    slice_ = _large_single_request_slice(sink_kind=kind)
    payload = build_provider_payload(slice_)
    request = {'input':[{'content':[{'text':payload.messages[1]['content']}]}]}
    answer = growth_yes_from_slice(request)
    contract = bind_provider_growth_contract(validate_provider_growth_contract(answer),slice_,payload.fact_alias_to_original)
    assert validate_contract_static_semantics(contract,slice_) is contract
    cited = set(contract.required_static_evidence)
    assert any(f.kind=='known_limit_location' and f.fact_id in cited for f in slice_.payload.static_facts)
