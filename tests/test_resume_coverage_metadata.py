"""Production metadata must count partial coverage, not all coverage records."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import dosweb.production as production
from tests.test_fse_offline_e2e import run_synthetic_case


@pytest.mark.parametrize("partial_families", [(), ("guard",), ("guard", "bound", "release")])
def test_coverage_metadata_matches_published_records(tmp_path: Path, monkeypatch, partial_families) -> None:
    original = production._run_codeql_family

    def add_partial_rows(*args, **kwargs):
        rows = original(*args, **kwargs)
        if args[2] == "lifecycle":
            rows = [
                {**row, "coverage_status": "partial", "coverage_note": "fixture_scope_unresolved"}
                if row.get("query_name") == "lifecycle_coverage" and row.get("family") in partial_families
                else row
                for row in rows
            ]
        return rows

    monkeypatch.setattr(production, "_run_codeql_family", add_partial_rows)
    result, output, *_ = run_synthetic_case(tmp_path, "off")
    assert result["status"] == "completed"
    records = [json.loads(line) for line in (output / "lifecycle_coverage.jsonl").read_text().splitlines()]
    run = json.loads((output / "run.json").read_text())
    metadata = run["stages"]["lifecycle"]["metadata"]
    expected_partial = sum(row["status"] == "partial" for row in records)
    assert expected_partial == len(partial_families)
    assert metadata["coverage_partial_count"] == expected_partial
    assert metadata["coverage_total_count"] == len(records)
    assert metadata["coverage_complete_count"] == sum(row["status"] == "complete" for row in records)
    if partial_families:
        finding = json.loads((output / "static_findings.jsonl").read_text())
        assert finding["verdict"] == "static_unknown", "Counting metadata must not relax incomplete evidence."
