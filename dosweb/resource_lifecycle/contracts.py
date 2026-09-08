from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from dosweb.resource_lifecycle.models import SOURCE_KINDS


EXECUTOR_CONTRACT_VERSION: Final = "executor-contract-v1"


@dataclass(frozen=True)
class ExecutorContract:
    contract_id: str
    scheduling: Literal["inline", "queued"]
    queue_capacity: int | str | None
    capacity_atomic: bool
    completion_drops_capture: bool
    rejection_drops_capture: bool
    cancellation: Literal["drops_capture", "retains_capture", "unknown"]
    source_kind: Literal["static_verified", "trusted_contract", "llm_proposed", "manual_fixture"]
    version: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(item, str)
            or not item
            or len(item.encode("utf-8")) > 512
            for item in (self.contract_id, self.version)
        ):
            raise ValueError("executor contract identity is required")
        if self.version != EXECUTOR_CONTRACT_VERSION:
            raise ValueError("executor contract version is unsupported")
        if any(
            not isinstance(item, bool)
            for item in (self.capacity_atomic, self.completion_drops_capture, self.rejection_drops_capture)
        ):
            raise ValueError("executor contract semantic flags must be boolean")
        if self.scheduling not in {"inline", "queued"}:
            raise ValueError("executor scheduling is invalid")
        if isinstance(self.queue_capacity, int) and (isinstance(self.queue_capacity, bool) or self.queue_capacity <= 0):
            raise ValueError("executor capacity must be positive")
        if isinstance(self.queue_capacity, str) and not self.queue_capacity:
            raise ValueError("symbolic executor capacity must be non-empty")
        if self.queue_capacity is not None and not isinstance(self.queue_capacity, (int, str)):
            raise ValueError("executor capacity is invalid")
        if self.cancellation not in {"drops_capture", "retains_capture", "unknown"}:
            raise ValueError("executor cancellation semantics are invalid")
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError("executor contract source_kind is invalid")
