"""Run membership is not a failed analysis, nor permission to drop truth rows."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from dosweb.batch.plan import build_batch_plan, publish_batch_plan, write_target_binding
from dosweb.errors import AnalyzerError
from scripts.generate_poc33_recall import main
from tests import test_batch_plan


def _inputs(root: Path, *, plan: bool = True, target: bool = True):
    run = root / "run"
    run.mkdir()
    manifest = root / "truth.json"
    records = [{"record_id": f"case-{i}", "app": f"owner{i}/repo{i}", "entry": "POST /body", "status": "static_seed"} for i in (1, 2)]
    manifest.write_text(json.dumps(records))
    for i in (1, 2):
        (root / f"frameworks/applications/owner{i}__repo{i}").mkdir(parents=True)
        (root / f"databases/applications/owner{i}__repo{i}-db").mkdir(parents=True)
    batch = None
    directory = None
    if plan:
        batch = build_batch_plan(test_batch_plan.BatchPlanTests()._corpus(1), run_id="scope-test", mode="full")
        publish_batch_plan(batch, run)
        if target:
            directory = run / "targets/001-owner1__repo1"
            directory.mkdir(parents=True)
            write_target_binding(batch, batch.targets[0], directory)
            (directory / "run.json").write_text(json.dumps({"status": "completed"}))
    return run, manifest, batch, directory


def _evaluate(root: Path, run: Path, manifest: Path):
    out = root / "report"
    assert main(["--repo-root", str(root), "--manifest", str(manifest), "--results-root", str(run), "--output", str(out)]) == 0
    rows = [json.loads(line) for line in (out / "truth_dispositions.jsonl").read_text().splitlines()]
    return rows, json.loads((out / "summary.json").read_text())


def test_subset_preserves_full_manifest_and_marks_excluded_not_failed(tmp_path):
    run, manifest, _, _ = _inputs(tmp_path)
    rows, summary = _evaluate(tmp_path, run, manifest)
    assert len(rows) == summary["total"] == 2
    assert rows[0]["execution_scope"] == "in_run"
    assert rows[1]["status"] == "not_in_run"
    assert rows[1]["execution_scope"] == "not_in_run"
    assert rows[1]["verdicts"] == []
    assert summary["status_counts"]["not_in_run"] == 1
    assert summary["scope_counts"] == {"in_run": 1, "not_in_run": 1, "unverified_scope": 0}
    assert summary["static_vulnerable_count"] == 0


def test_selected_project_with_no_artifacts_remains_failed(tmp_path):
    run, manifest, _, _ = _inputs(tmp_path, target=False)
    rows, summary = _evaluate(tmp_path, run, manifest)
    assert rows[0]["execution_scope"] == "in_run"
    assert rows[0]["status"] == "stage_failed"
    assert rows[1]["status"] == "not_in_run"
    assert summary["status_counts"]["stage_failed"] == 1


def test_no_plan_does_not_infer_exclusion_from_missing_directory(tmp_path):
    run, manifest, _, _ = _inputs(tmp_path, plan=False)
    rows, summary = _evaluate(tmp_path, run, manifest)
    assert all(row["execution_scope"] == "unverified_scope" for row in rows)
    assert all(row["status"] == "stage_failed" for row in rows)
    assert summary["status_counts"]["not_in_run"] == 0


@pytest.mark.parametrize("damage", ["plan_digest", "invalid_json", "plan_symlink", "binding_run_id", "binding_target", "missing_binding"])
def test_unverified_plan_or_cross_run_binding_cannot_change_scope(tmp_path, damage):
    run, manifest, _, directory = _inputs(tmp_path)
    assert directory is not None
    path = run / "batch_plan.json"
    if damage == "plan_digest":
        value = json.loads(path.read_text()); value["targets"] = []; path.write_text(json.dumps(value))
    elif damage == "invalid_json":
        path.write_text("{")
    elif damage == "plan_symlink":
        archived = run / "archived.json"; path.rename(archived); path.symlink_to(archived)
    elif damage == "missing_binding":
        (directory / "batch_target.json").unlink()
    else:
        binding = directory / "batch_target.json"
        value = json.loads(binding.read_text())
        if damage == "binding_run_id":
            value["run_id"] = "different-run"
        else:
            value["target"]["identity"]["fingerprint"] = "f" * 40
        binding.write_text(json.dumps(value))
    with pytest.raises(AnalyzerError):
        _evaluate(tmp_path, run, manifest)
    assert not (tmp_path / "report/summary.json").exists()


def test_excluded_project_with_stray_artifacts_is_scope_conflict(tmp_path):
    run, manifest, _, _ = _inputs(tmp_path)
    stray = run / "owner2__repo2"
    stray.mkdir()
    (stray / "run.json").write_text(json.dumps({"status": "completed"}))
    with pytest.raises(AnalyzerError):
        _evaluate(tmp_path, run, manifest)
