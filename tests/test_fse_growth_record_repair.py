"""Synthetic regression of Growth record parsing; no source/target discovery."""
from __future__ import annotations

import pytest

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.errors import AnalyzerError
from dosweb.growth import VerificationCheck, VerifiedGrowthResult
from tests.test_resource_lifecycle_production_bridge import _growth, _verified


@pytest.mark.parametrize("passed", [0, 1, "false", None])
def test_verification_check_requires_actual_boolean(passed):
    with pytest.raises(AnalyzerError, match="check"):
        VerificationCheck("resource_growth", passed)


@pytest.mark.parametrize("name,reason", [("", None), (None, None), ("resource_growth", ""), ("resource_growth", 1)])
def test_verification_check_requires_nonempty_typed_strings(name, reason):
    with pytest.raises(AnalyzerError, match="check"):
        VerificationCheck(name, True, reason)


@pytest.mark.parametrize("malformed", [None, {}, {"name": "ignored", "passed": False},
    {"name": "ignored", "passed": False, "reason_code": "INCOMPLETE", "extra": True}])
def test_malformed_checks_are_rejected_not_silently_filtered(malformed):
    original = _verified(_growth())
    record = original.to_dict()
    record["checks"].append(malformed)
    with pytest.raises(AnalyzerError, match="check"):
        VerifiedGrowthResult.from_dict(record, original.candidate)


@pytest.mark.parametrize("passed", [1, "false"])
def test_rehashed_truthy_nonboolean_cannot_become_verified(passed):
    original = _verified(_growth())
    record = original.to_dict()
    record["checks"][0]["passed"] = passed
    semantic = {key: value for key, value in record.items() if key != "verified_growth_id"}
    record["verified_growth_id"] = stable_identifier("verified_growth", semantic)
    with pytest.raises(AnalyzerError, match="check"):
        VerifiedGrowthResult.from_dict(record, original.candidate)


def test_valid_complete_and_incomplete_check_objects_remain_supported():
    assert VerificationCheck("valid", True).passed is True
    assert VerificationCheck("incomplete", False, "INCOMPLETE").passed is False
    original = _verified(_growth())
    assert VerifiedGrowthResult.from_dict(original.to_dict(), original.candidate) == original
