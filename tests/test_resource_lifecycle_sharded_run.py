from dataclasses import replace
import shutil

import pytest

from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle import commands
from dosweb.resource_lifecycle.sharded_run import analyze_sharded, replay_sharded, iter_run_units
from dosweb.resource_lifecycle.shards import ShardBudget, ShardReader, ShardWriter
from tests.test_resource_lifecycle_task4_review import artifact
from tests.test_resource_lifecycle_async_solver import task_program


def test_manual_ir_replay_really_solves_after_directory_move(tmp_path, monkeypatch):
    facts = artifact(task_program())
    out = tmp_path / "original"
    receipt = analyze_sharded(facts, out)
    assert receipt["analysis_status"] == "complete"
    assert [name for name, _ in iter_run_units(ShardReader(out))] == ["manual:review"]
    moved = tmp_path / "moved"
    shutil.move(out, moved)
    original = commands.solve
    calls = []
    def counted(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(commands, "solve", counted)
    assert replay_sharded(moved)["mode"] == "semantic_replay"
    assert calls == [True]
    calls.clear()
    assert replay_sharded(moved, integrity_only=True)["mode"] == "integrity_only"
    assert calls == []


def test_valid_hashes_cannot_mask_semantic_tamper(tmp_path):
    out = tmp_path / "original"
    analyze_sharded(artifact(task_program()), out)
    reader = ShardReader(out)
    altered = ShardWriter(tmp_path / "altered")
    for name, payload in reversed(list(reader.iter_objects())):
        if isinstance(payload, list):
            altered.add(name, payload)
            continue
        payload["results"]["units"][0]["steps"] += 1
        altered.add(name, payload)
    altered.finalize(reader.index["identity"])
    assert replay_sharded(tmp_path / "altered", integrity_only=True)["consistent"]
    with pytest.raises(AnalyzerError, match="replay failed"):
        replay_sharded(tmp_path / "altered")


def test_empty_run_is_partial_and_not_semantic_success(tmp_path):
    facts = replace(artifact(task_program()), units=())
    assert analyze_sharded(facts, tmp_path)["analysis_status"] == "partial"
    assert replay_sharded(tmp_path, integrity_only=True)["unit_count"] == 0
    with pytest.raises(AnalyzerError):
        replay_sharded(tmp_path)


def test_storage_budget_exit_is_visible(tmp_path):
    receipt = analyze_sharded(artifact(task_program()), tmp_path,
                              budget=ShardBudget(max_decoded_bytes=5000))
    assert receipt["analysis_status"] == "partial"
    assert receipt["units"][0]["status"] == "storage_budget_exit"
    result = replay_sharded(tmp_path, integrity_only=True)
    assert result["failed_units"] == ["manual:review"]
    with pytest.raises(AnalyzerError):
        replay_sharded(tmp_path)


def test_source_snapshot_binding_rejects_missing_and_changed_root(tmp_path):
    # This exercises source identity verification, not CodeQL extraction.
    from dosweb.resource_lifecycle.sharded_run import _verify_source
    source = tmp_path / "source"
    source.mkdir()
    (source / "A.java").write_text("class A {}")
    identity = {"source_kind": "static_verified", "source_snapshot_sha256": commands._java_source_snapshot(source)[1]}
    _verify_source(identity, source)
    rebound = tmp_path / "rebound"
    shutil.copytree(source, rebound)
    _verify_source(identity, rebound)
    with pytest.raises(ValueError, match="source-root"):
        _verify_source(identity, None)
    (rebound / "A.java").write_text("class B {}")
    with pytest.raises(ValueError, match="mismatch"):
        _verify_source(identity, rebound)


def test_one_unit_failure_does_not_skip_independent_unit(tmp_path, monkeypatch):
    facts = artifact(task_program())
    facts = replace(facts, units=(replace(facts.units[0], unit_id="bad"),
                                  replace(facts.units[0], unit_id="good")))
    original = commands._analyze_payload
    calls = []
    def analyze(single):
        name = single.units[0].unit_id
        calls.append(name)
        if name == "bad":
            raise ValueError("synthetic unit failure")
        return original(single)
    monkeypatch.setattr(commands, "_analyze_payload", analyze)
    seen = []
    result = analyze_sharded(facts, tmp_path, on_unit=lambda record, value: seen.append((record["unit_id"], value is not None)))
    assert calls == ["bad", "good"]
    assert seen == [("bad", False), ("good", True)]
    assert result["analysis_status"] == "partial"
    assert [row["status"] for row in result["units"]] == ["unit_failed", "analyzed"]
    assert replay_sharded(tmp_path, integrity_only=True)["failed_units"] == ["bad"]


def _rewrite_run(original, changed, mutate):
    reader = ShardReader(original)
    objects = list(reader.iter_objects())
    identity = dict(reader.index["identity"])
    mutate(objects, identity)
    writer = ShardWriter(changed)
    for name, payload in reversed(objects):
        writer.add(name, payload)
    writer.finalize(identity)


@pytest.mark.parametrize("scope", ["full_run", "selected"])
def test_required_catalog_rejects_missing_unit_even_with_rewritten_counts(tmp_path, scope):
    facts = artifact(task_program())
    facts = replace(facts, units=(replace(facts.units[0], unit_id="first"),
                                  replace(facts.units[0], unit_id="second")))
    original = tmp_path / "original"
    analyze_sharded(facts, original, unit_ids=("first", "second") if scope == "selected" else None)
    def drop(objects, identity):
        objects[:] = [(name, payload) for name, payload in objects if name != "first"]
        identity["unit_count"] -= 1
    changed = tmp_path / "changed"
    _rewrite_run(original, changed, drop)
    for integrity in (False, True):
        with pytest.raises(AnalyzerError):
            replay_sharded(changed, integrity_only=integrity)


@pytest.mark.parametrize("change", ["input_snapshot", "facts", "legacy"])
def test_input_identity_and_old_version_rejected(tmp_path, change):
    original = tmp_path / "original"
    analyze_sharded(artifact(task_program()), original)
    def mutate(objects, identity):
        if change == "input_snapshot":
            identity["input_snapshot_sha256"] = "b" * 64
        elif change == "legacy":
            identity.pop("run_format")
        else:
            for _, payload in objects:
                if isinstance(payload, dict):
                    payload["facts"]["snapshot_sha256"] = "b" * 64
    changed = tmp_path / "changed"
    _rewrite_run(original, changed, mutate)
    with pytest.raises(AnalyzerError):
        replay_sharded(changed, integrity_only=True)


def test_callback_error_aborts_without_second_add_or_complete(tmp_path, monkeypatch):
    original_add = ShardWriter.add
    calls = []
    def add(writer, name, value):
        calls.append(name)
        return original_add(writer, name, value)
    monkeypatch.setattr(ShardWriter, "add", add)
    def failed_delivery(record, value):
        raise ValueError("callback ledger budget exceeded")
    with pytest.raises(AnalyzerError) as error:
        analyze_sharded(artifact(task_program()), tmp_path, on_unit=failed_delivery)
    assert "duplicate" not in str(error.value)
    assert calls == ["manual:review"]
    assert not (tmp_path / "run-index.json").exists()
