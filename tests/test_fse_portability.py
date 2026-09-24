"""Small fixture checks; missing optional assets never conceal corrupt inputs."""
import json
import unittest
import pytest
from dosweb.benchmark.truth import normalize_truth
from tests.support.offline_assets import (
    JAVA_WEB_205_MANIFEST, require_java_web_205_assets,
    skip_unless_present, write_synthetic_poc29_truth,
)


def test_optional_asset_absence_is_explicit_skip(tmp_path):
    with pytest.raises(unittest.SkipTest, match="optional asset absent"):
        skip_unless_present(tmp_path / "absent", "optional asset absent")


def test_present_symbolic_link_is_an_error_not_a_missing_asset(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(AssertionError, match="symbolic-link"):
        skip_unless_present(alias, "must not be classified as missing")


@pytest.mark.parametrize("payload", [{"projects": []}, {"projects": None}, {"projects": [{}]}])
def test_corrupt_tracked_manifest_cannot_be_skipped(tmp_path, payload):
    manifest = tmp_path / JAVA_WEB_205_MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(payload))
    with pytest.raises(AssertionError, match="205 projects"):
        require_java_web_205_assets(tmp_path)


def test_missing_required_manifest_fails(tmp_path):
    with pytest.raises(AssertionError, match="required tracked manifest"):
        require_java_web_205_assets(tmp_path)


def test_late_bad_path_is_not_hidden_by_missing_first_checkout(tmp_path):
    projects = [{"source_path": "missing/source", "codeql_path": "missing/db"} for _ in range(205)]
    projects[-1]["source_path"] = "../escape"
    manifest = tmp_path / JAVA_WEB_205_MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"projects": projects}))
    with pytest.raises(AssertionError, match="unsafe source_path"):
        require_java_web_205_assets(tmp_path)


def test_synthetic_truth_has_explicit_fixed_denominators(tmp_path):
    truth = write_synthetic_poc29_truth(tmp_path)
    rows, validation, manifest = normalize_truth(truth, repo_root=tmp_path)
    assert len(rows) == 29
    assert validation["valid"] and validation["batch_ready"]
    assert validation["repository_count"] == 18
    assert len(manifest["projects"]) == 18
    assert all(project["name"].startswith("fixture") for project in manifest["projects"])
