import os
from pathlib import Path

import pytest

from dosweb.resource_lifecycle.io import atomic_write_json, load_json_regular

from dosweb.resource_lifecycle.commands import (
    _analyze_payload, _evidence_payload, resource_analyze, resource_replay,
)
from tests.test_resource_lifecycle_task4_locations import located_program
from tests.test_resource_lifecycle_task4_review import artifact


def test_child_dependency_and_rule_references_preserve_exact_solved_path():
    extracted = artifact(located_program())
    result = _analyze_payload(extracted)
    evidence = _evidence_payload(extracted, result)
    assert evidence["path_dependency_encoding"]["result_binding"] == "result_sha256"
    assert evidence["result_sha256"] == result["result_sha256"]
    units = {unit["unit_id"]: unit for unit in result["units"]}
    indexed = {row["proof_id"] for row in evidence["proof_dependencies"]}
    count = 0
    for parent in evidence["dimension_derivations"]:
        for child in parent["path_derivations"]:
            count += 1
            assert child["proof_id"] not in indexed
            assert set(child["evidence_ids"]) <= set(evidence["facts"])
            recorded = units[child["unit_id"]]["property_derivations"][child["scope"].split(":", 1)[0]][child["property_event_id"]][child["property_derivation_index"]]
            assert child["state"] == recorded["state"]
            assert child["trace"] == {key: value for key, value in recorded["trace"].items() if key not in {"rule_ids", "rule_dependencies"}}
            assert set(recorded["trace"]["evidence_ids"]) <= set(child["evidence_ids"])
            assert all({"rule_id": rule, "evidence_id": fact} in evidence["dependencies"] for rule, fact in recorded["trace"]["rule_dependencies"])
    assert count > 0


@pytest.mark.skipif(not os.environ.get("DOSWEB_G8_CACHED_FACTS"), reason="Requires retained real SourcePairs facts via DOSWEB_G8_CACHED_FACTS")
def test_real_source_evidence_fits_reader_and_replays(tmp_path):
    facts = Path(os.environ["DOSWEB_G8_CACHED_FACTS"])
    resource_analyze({"facts": facts, "out": tmp_path, "llm": "off"})
    assert (tmp_path / "evidence.json").stat().st_size <= 16 * 1024 * 1024
    assert resource_replay({"run": tmp_path})["consistent"] is True
    evidence = load_json_regular(tmp_path / "evidence.json")
    child = next(child for parent in evidence["dimension_derivations"] for child in parent["path_derivations"])
    child["property_derivation_index"] += 100000
    atomic_write_json(tmp_path / "evidence.json", evidence)
    assert resource_replay({"run": tmp_path})["consistent"] is False
