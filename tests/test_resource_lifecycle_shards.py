from dataclasses import replace
import json

import pytest

from dosweb.resource_lifecycle.shards import ShardBudget, ShardError, ShardReader, ShardWriter


def test_nested_structure_and_content_reuse(tmp_path):
    common = {"state": {"held": ["resource-a"], "count": 3}, "trace": ["allocate", "retain"]}
    value = {"task-a": [common, common], "task-b": {"derivation": common}, "literal": {"$ref": "ordinary string"}, "empty": []}
    writer = ShardWriter(tmp_path)
    root = writer.add("first", value)
    before = len(list((tmp_path / "shared").iterdir()))
    assert writer.add("second", value) == root
    assert len(list((tmp_path / "shared").iterdir())) == before + 1
    writer.finalize({"source_tree": "abc", "tool": "1.2", "contracts": "def"})
    assert dict(ShardReader(tmp_path).iter_objects()) == {"first": value, "second": value}


def test_failed_unit_does_not_publish_or_hide_other_units(tmp_path):
    budget = ShardBudget(max_decoded_bytes=2000)
    writer = ShardWriter(tmp_path, budget)
    with pytest.raises(ShardError, match="decoded"):
        writer.add("too-big", ["x" * 2000])
    assert not (tmp_path / "run-index.json").exists()
    writer.add("independent", 42)
    writer.finalize({})
    assert dict(ShardReader(tmp_path).iter_objects()) == {"independent": 42}


def test_hash_and_missing_shard_rejected(tmp_path):
    writer = ShardWriter(tmp_path)
    root = writer.add("a", {"x": 1})
    writer.finalize({})
    path = tmp_path / "shared" / f"{root}.json"
    raw = path.read_bytes()
    path.write_text('{}\n')
    with pytest.raises(ShardError, match="hash"):
        list(ShardReader(tmp_path).iter_objects())
    path.write_bytes(raw)
    path.unlink()
    with pytest.raises(Exception):
        list(ShardReader(tmp_path).iter_objects())


def test_paged_containers_and_index_budget(tmp_path):
    budget = ShardBudget(max_shard_bytes=1024, max_index_bytes=512, page_items=2)
    writer = ShardWriter(tmp_path, budget)
    expected = {str(i): {"values": list(range(30))} for i in range(8)}
    for name, value in expected.items():
        writer.add(name, value)
    writer.finalize({})
    assert writer.max_shard_bytes <= 1024
    assert dict(ShardReader(tmp_path, budget).iter_objects()) == expected
    with pytest.raises(ShardError, match="read byte"):
        list(ShardReader(tmp_path, replace(budget, max_total_bytes=600)).iter_objects())
    with pytest.raises(ShardError, match="decoded"):
        list(ShardReader(tmp_path, replace(budget, max_decoded_bytes=1000)).iter_objects())


def test_nonempty_derivation_scale_exceeds_old_raw_limit(tmp_path):
    # Full repeated records (including state, evidence, and source location), not
    # empty reference placeholders. This is storage validation, not solver replay.
    derivation = {"state": {"held_edges": [["holder", "resource"]], "obligations": [1, 2]},
                  "trace": {"events": ["allocate", "retain"], "evidence": "e" * 4096},
                  "source": {"path": "src/Example.java", "line": 42}}
    value = {"derivations": [derivation] * 1100}
    writer = ShardWriter(tmp_path)
    for i in range(4):
        writer.add(f"unit-{i}", value)
    writer.finalize({"source_tree": "synthetic-storage-test"})
    assert len(json.dumps(value).encode()) * 4 > 16 * 1024 * 1024
    count = 0
    for name, restored in ShardReader(tmp_path).iter_objects():
        assert name.startswith("unit-") and restored == value
        count += 1
    assert count == 4
    assert writer.max_shard_bytes <= 16 * 1024 * 1024
    assert writer.total_bytes < len(json.dumps(value).encode())


def test_final_index_and_scalar_limits(tmp_path):
    writer = ShardWriter(tmp_path, ShardBudget(max_index_bytes=200))
    with pytest.raises(ShardError, match="index"):
        writer.add("x" * 300, 1)
    assert not (tmp_path / "run-index.json").exists()
    with pytest.raises(ShardError):
        ShardBudget(max_shard_bytes=17 * 1024 * 1024)


def test_physical_evidence_exceeds_single_file_cap(tmp_path):
    writer = ShardWriter(tmp_path)
    common = {"state": {"held": ["resource"]}, "trace": ["allocate", "retain"]}
    for i in range(20):
        writer.add(f"unit-{i}", {"derivations": [common, common],
                                 "source_evidence": str(i) + "e" * (1024 * 1024)})
    writer.finalize({"kind": "synthetic-storage-only"})
    physical = sum(p.stat().st_size for p in tmp_path.rglob("*.json"))
    assert physical == writer.total_bytes > 16 * 1024 * 1024
    assert max(p.stat().st_size for p in tmp_path.rglob("*.json")) <= 16 * 1024 * 1024
    restored = 0
    for name, value in ShardReader(tmp_path).iter_objects():
        assert value == {"derivations": [common, common],
                         "source_evidence": name.removeprefix("unit-") + "e" * (1024 * 1024)}
        restored += 1
    assert restored == 20
