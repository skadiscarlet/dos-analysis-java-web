"""Bounded content-addressed JSON storage; integrity checking is not semantic replay."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Iterator

from dosweb.artifacts.identifiers import canonical_json
from dosweb.resource_lifecycle.io import atomic_write_json, ensure_output_directory, load_regular_bytes_with_sha256


class ShardError(ValueError):
    pass


@dataclass(frozen=True)
class ShardBudget:
    max_shard_bytes: int = 16 * 1024 * 1024
    max_index_bytes: int = 256 * 1024
    max_total_bytes: int = 512 * 1024 * 1024
    max_decoded_bytes: int = 256 * 1024 * 1024
    max_depth: int = 128
    page_items: int = 512

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise ShardError("budgets must be positive integers")
        if self.max_shard_bytes > 16 * 1024 * 1024:
            raise ShardError("single shard limit cannot exceed 16 MiB")


def _size(value):
    return len(canonical_json(value)) + 1


def _digest(value):
    return hashlib.sha256(canonical_json(value) + b"\n").hexdigest()


class ShardWriter:
    """Add independent JSON objects, then atomically publish the complete index.

    Failed adds do not enter the index. Their unreferenced immutable chunks may
    remain and count against the physical total budget. Use a fresh directory.
    """
    def __init__(self, directory: Path, budget: ShardBudget = ShardBudget()):
        self.directory = ensure_output_directory(directory)
        if any(self.directory.iterdir()):
            raise ShardError("shard output must be an empty directory")
        self.budget = budget
        self.total_bytes = 0
        self.max_shard_bytes = 0
        self._seen = set()
        self._names = set()
        self._head = None
        self._closed = False

    def _put(self, node, *, index=False):
        size = _size(node)
        if size > min(self.budget.max_shard_bytes, self.budget.max_index_bytes if index else self.budget.max_shard_bytes):
            raise ShardError("shard/index byte budget exceeded")
        digest = _digest(node)
        if digest not in self._seen:
            if self.total_bytes + size > self.budget.max_total_bytes:
                raise ShardError("total evidence byte budget exceeded")
            atomic_write_json(self.directory / "shared" / f"{digest}.json", node)
            self._seen.add(digest)
            self.total_bytes += size
            self.max_shard_bytes = max(self.max_shard_bytes, size)
        return digest

    def add(self, name: str, value: object) -> str:
        if self._closed or not isinstance(name, str) or not name or name in self._names:
            raise ShardError("closed writer or invalid/duplicate object name")
        decoded = 0

        def encode(value, depth):
            nonlocal decoded
            if depth > self.budget.max_depth:
                raise ShardError("decoded depth budget exceeded")
            decoded += 256
            if isinstance(value, str):
                decoded += 4 * len(value)
            if decoded > self.budget.max_decoded_bytes:
                raise ShardError("decoded object budget exceeded")
            if isinstance(value, (list, tuple, dict)):
                kind = "dict" if isinstance(value, dict) else "list"
                if kind == "dict" and any(not isinstance(k, str) for k in value):
                    raise ShardError("JSON keys must be strings")
                entries = []
                head = None
                iterator = sorted(value.items()) if kind == "dict" else value
                for item in iterator:
                    if kind == "dict":
                        key, child = item
                        decoded += 256 + 4 * len(key)
                        entry = [key, encode(child, depth + 1)]
                    else:
                        entry = encode(item, depth + 1)
                    entries.append(entry)
                    if len(entries) == self.budget.page_items:
                        head = self._put({"kind": kind, "items": entries, "previous": head})
                        entries = []
                return self._put({"kind": kind, "items": entries, "previous": head})
            if value is not None and type(value) not in (str, int, float, bool):
                raise ShardError("value is not JSON")
            if isinstance(value, float) and not math.isfinite(value):
                raise ShardError("nonfinite JSON value")
            return self._put({"kind": "scalar", "value": value})

        root = encode(value, 0)
        head = self._put({"kind": "index", "name": name, "root": root, "previous": self._head}, index=True)
        self._head = head
        self._names.add(name)
        return root

    def finalize(self, identity: dict) -> Path:
        if self._closed:
            raise ShardError("writer already finalized")
        if not isinstance(identity, dict):
            raise ShardError("identity must be an object")
        index = {"format": "lifecycle-shards-1", "complete": True,
                 "identity": identity, "head": self._head, "object_count": len(self._names)}
        size = _size(index)
        if size > min(self.budget.max_index_bytes, self.budget.max_shard_bytes) or self.total_bytes + size > self.budget.max_total_bytes:
            raise ShardError("final index budget exceeded")
        path = self.directory / "run-index.json"
        atomic_write_json(path, index)
        self.total_bytes += size
        self.max_shard_bytes = max(self.max_shard_bytes, size)
        self._closed = True
        return path


class ShardReader:
    """Stream independent objects with a per-object expansion memory budget.

    No decoded-object cache or run-wide reconstruction is kept. Total read bytes
    include repeated reads, intentionally bounding decompression amplification.
    """
    def __init__(self, directory: Path, budget: ShardBudget = ShardBudget()):
        self.directory = Path(directory)
        self.budget = budget
        self.total_bytes = 0
        self.index = self._read(self.directory / "run-index.json", index=True)
        if not isinstance(self.index, dict) or set(self.index) != {"format", "complete", "identity", "head", "object_count"} or self.index["format"] != "lifecycle-shards-1" or self.index["complete"] is not True:
            raise ShardError("unsupported or incomplete shard index")
        if not isinstance(self.index["identity"], dict):
            raise ShardError("identity must be an object")
        if type(self.index["object_count"]) is not int or self.index["object_count"] < 0:
            raise ShardError("invalid object count")

    def _read(self, path, *, digest=None, index=False):
        raw, actual = load_regular_bytes_with_sha256(path, max_bytes=min(self.budget.max_shard_bytes, self.budget.max_index_bytes if index else self.budget.max_shard_bytes))
        self.total_bytes += len(raw)
        if self.total_bytes > self.budget.max_total_bytes:
            raise ShardError("total read byte budget exceeded")
        if digest is not None and actual != digest:
            raise ShardError("shard hash mismatch")
        if len(raw) * 32 > self.budget.max_decoded_bytes:
            raise ShardError("decoded shard budget exceeded")
        try:
            value = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ShardError("invalid shard JSON") from exc
        return value

    def _node(self, digest, *, index=False):
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ShardError("invalid shard reference")
        return self._read(self.directory / "shared" / f"{digest}.json", digest=digest, index=index)

    def iter_objects(self) -> Iterator[tuple[str, object]]:
        head = self.index["head"]
        names = set()
        names_bytes = 0
        while head is not None:
            node = self._node(head, index=True)
            if not isinstance(node, dict) or set(node) != {"kind", "name", "root", "previous"} or node["kind"] != "index" or not isinstance(node["name"], str) or node["name"] in names:
                raise ShardError("invalid or repeated index entry")
            names.add(node["name"])
            names_bytes += 256 + 4 * len(node["name"])
            if len(names) > self.index["object_count"] or names_bytes > self.budget.max_decoded_bytes:
                raise ShardError("index count/memory budget exceeded")
            used = 0

            def charge(amount):
                nonlocal used
                used += amount
                if used > self.budget.max_decoded_bytes:
                    raise ShardError("decoded object budget exceeded")

            def decode(ref, depth):
                if depth > self.budget.max_depth:
                    raise ShardError("decoded depth budget exceeded")
                charge(256)
                item = self._node(ref)
                if not isinstance(item, dict):
                    raise ShardError("invalid node")
                kind = item.get("kind")
                if kind == "scalar" and set(item) == {"kind", "value"}:
                    value = item["value"]
                    if value is not None and type(value) not in (str, int, float, bool):
                        raise ShardError("invalid scalar")
                    if isinstance(value, float) and not math.isfinite(value):
                        raise ShardError("nonfinite JSON value")
                    charge(4 * len(value) if isinstance(value, str) else 0)
                    return value
                if kind not in ("list", "dict"):
                    raise ShardError("invalid node kind")
                pages = []
                while True:
                    if set(item) != {"kind", "items", "previous"} or item["kind"] != kind or not isinstance(item["items"], list):
                        raise ShardError("invalid container page")
                    charge(256 + _size(item) * 8)
                    pages.append(item["items"])
                    if item["previous"] is None:
                        break
                    item = self._node(item["previous"])
                result = {} if kind == "dict" else []
                for page in reversed(pages):
                    for entry in page:
                        if kind == "list":
                            result.append(decode(entry, depth + 1))
                        else:
                            if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str) or entry[0] in result:
                                raise ShardError("invalid dictionary entry")
                            charge(256 + 4 * len(entry[0]))
                            result[entry[0]] = decode(entry[1], depth + 1)
                return result

            yield node["name"], decode(node["root"], 0)
            head = node["previous"]
        if len(names) != self.index["object_count"]:
            raise ShardError("missing index entries")
