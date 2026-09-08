from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dosweb.resource_lifecycle.commands import resource_replay


@dataclass(frozen=True)
class ReplayResult:
    consistent: bool
    recomputed: bool
    stored_result_sha256: str
    recomputed_result_sha256: str


def replay(run_dir: Path) -> ReplayResult:
    value = resource_replay({"run": run_dir})
    return ReplayResult(
        bool(value["consistent"]),
        bool(value["recomputed"]),
        str(value["stored_result_sha256"]),
        str(value["recomputed_result_sha256"]),
    )
