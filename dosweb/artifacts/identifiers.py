from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_canonical_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def stable_identifier(prefix: str, semantic_identity: Mapping[str, object]) -> str:
    return f"{prefix}:{sha256_canonical_json(semantic_identity)[:24]}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
