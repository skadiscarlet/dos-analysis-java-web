from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from dosweb.resource_lifecycle.models import SOURCE_KINDS


EXECUTOR_CONTRACT_VERSION: Final = "executor-contract-v1"


def _validate_positive_limit(value: int | str | None, label: str) -> None:
    if value is None:
        return
    if type(value) is int:
        if value <= 0:
            raise ValueError(f"executor {label} must be positive")
        return
    if not isinstance(value, str):
        raise ValueError(f"executor {label} is invalid")
    if not value:
        raise ValueError(f"symbolic executor {label} must be non-empty")
    try:
        numeric = int(value)
    except ValueError:
        return
    if numeric <= 0:
        raise ValueError(f"executor {label} must be positive")


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
    max_workers: int | str | None = None
    rejection_policy: Literal[
        "abort", "caller_runs", "discard", "discard_oldest", "unknown"
    ] = "unknown"
    termination: Literal["drops_capture", "retains_capture", "unknown"] = "unknown"
    core_workers: int | str | None = None

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
        _validate_positive_limit(self.queue_capacity, "capacity")
        if not (type(self.core_workers) is int and self.core_workers == 0
                or type(self.core_workers) is str and self.core_workers == "0"):
            _validate_positive_limit(self.core_workers, "core worker limit")
        _validate_positive_limit(self.max_workers, "worker limit")
        def numeric_limit(value: int | str | None) -> int | None:
            if type(value) is int:
                return value
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    pass
            return None
        core_limit = numeric_limit(self.core_workers)
        maximum_limit = numeric_limit(self.max_workers)
        if core_limit is not None and maximum_limit is not None and core_limit > maximum_limit:
            raise ValueError(
                "executor core worker limit cannot exceed maximum worker limit"
            )
        if self.rejection_policy not in {
            "abort",
            "caller_runs",
            "discard",
            "discard_oldest",
            "unknown",
        }:
            raise ValueError("executor rejection policy is invalid")
        if self.cancellation not in {"drops_capture", "retains_capture", "unknown"}:
            raise ValueError("executor cancellation semantics are invalid")
        if self.termination not in {"drops_capture", "retains_capture", "unknown"}:
            raise ValueError("executor termination semantics are invalid")
        if self.completion_drops_capture != (self.termination == "drops_capture"):
            raise ValueError("executor termination enum and legacy flag are inconsistent")
        if self.rejection_policy in {"abort", "discard"}:
            if not self.rejection_drops_capture:
                raise ValueError(
                    "executor rejection policy and legacy flag are inconsistent"
                )
        elif (
            self.rejection_policy in {"caller_runs", "discard_oldest"}
            and self.rejection_drops_capture
        ):
            raise ValueError(
                "executor rejection policy and legacy flag are inconsistent"
            )
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError("executor contract source_kind is invalid")
