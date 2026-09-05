"""Immutable domain models for canonical Java Web batch orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dosweb.artifacts.identifiers import sha256_canonical_json, stable_identifier

FingerprintType = Literal["git-commit", "tree-sha256"]
BatchMode = Literal["plan", "entries", "full"]
TargetState = Literal[
    "queued", "running", "retrying", "paused", "completed",
    "completed_with_gaps", "failed", "interrupted",
]


def _slug(name: str) -> str:
    owner, repository = name.split("/", 1)
    return f"{owner.lower()}__{repository.lower()}"


@dataclass(frozen=True, order=True)
class TargetIdentity:
    """Stable identity of one corpus target, independent of output location."""

    index: int
    name: str
    fingerprint_type: FingerprintType
    fingerprint: str
    source_path: str
    database_path: str

    @property
    def slug(self) -> str:
        return _slug(self.name)

    @property
    def owner(self) -> str:
        return self.name.split("/", 1)[0]

    @property
    def repository(self) -> str:
        return self.name.split("/", 1)[1]

    @property
    def identity_id(self) -> str:
        return stable_identifier("target", self.semantic_identity())

    def semantic_identity(self) -> dict[str, object]:
        return {
            "index": self.index,
            "name": self.name,
            "fingerprint_type": self.fingerprint_type,
            "fingerprint": self.fingerprint,
            "source_path": self.source_path,
            "database_path": self.database_path,
        }

    def to_dict(self) -> dict[str, object]:
        return {"target_id": self.identity_id, **self.semantic_identity(), "slug": self.slug}


@dataclass(frozen=True)
class TargetCapability:
    """Execution capabilities derived from attested corpus facts."""

    provider_eligible: bool = False
    public_source_url: str | None = None
    attestation: Literal["git-commit", "tree-sha256", "unavailable"] = "unavailable"
    reason: str | None = None
    provider_source_path: str | None = None
    provider_source_commit: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider_eligible": self.provider_eligible,
            "public_source_url": self.public_source_url,
            "attestation": self.attestation,
            "reason": self.reason,
        }
        if self.provider_source_path is not None:
            payload["provider_source_path"] = self.provider_source_path
        if self.provider_source_commit is not None:
            payload["provider_source_commit"] = self.provider_source_commit
        return payload


@dataclass(frozen=True)
class CorpusTarget:
    """A validated inventory row with resolved paths retained in memory only."""

    identity: TargetIdentity
    source: Path
    database: Path
    capability: TargetCapability = field(default_factory=TargetCapability)
    database_fingerprint: str = ""

    @property
    def index(self) -> int:
        return self.identity.index

    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def slug(self) -> str:
        return self.identity.slug

    @property
    def source_path(self) -> str:
        return self.identity.source_path

    @property
    def database_path(self) -> str:
        return self.identity.database_path

    @property
    def fingerprint_type(self) -> FingerprintType:
        return self.identity.fingerprint_type

    @property
    def fingerprint(self) -> str:
        return self.identity.fingerprint

    def to_dict(self) -> dict[str, object]:
        return {
            **self.identity.to_dict(),
            "capability": self.capability.to_dict(),
            "database_fingerprint": self.database_fingerprint,
        }


@dataclass(frozen=True)
class CanonicalCorpus:
    """Validated canonical corpus and its inventory digest."""

    schema_version: int
    status: str
    corpus: str
    total: int
    inventory_digest: str
    targets: tuple[CorpusTarget, ...]
    manifest_path: Path
    generated_at: str | None = None

    @property
    def projects(self) -> tuple[CorpusTarget, ...]:
        return self.targets

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "corpus": self.corpus,
            "total": self.total,
            "inventory_digest": self.inventory_digest,
            "manifest_path": self.manifest_path.as_posix(),
            "generated_at": self.generated_at,
            "projects": [target.to_dict() for target in self.targets],
        }


@dataclass(frozen=True)
class BatchTargetPlan:
    identity: TargetIdentity
    output_path: str
    capability: TargetCapability
    initial_state: TargetState
    target_id: str
    database_fingerprint: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "target_id": self.target_id,
            "identity": self.identity.to_dict(),
            "output_path": self.output_path,
            "capability": self.capability.to_dict(),
            "initial_state": self.initial_state,
        }
        if self.database_fingerprint:
            payload["database_fingerprint"] = self.database_fingerprint
        return payload


@dataclass(frozen=True)
class BatchPlan:
    """Immutable, digest-bound execution plan."""

    schema_version: int
    tool_version: str
    batch_schema_version: str
    run_id: str
    mode: BatchMode
    output_root: str
    inventory_digest: str
    targets: tuple[BatchTargetPlan, ...]
    plan_id: str
    plan_digest: str
    provider: dict[str, object] = field(default_factory=dict)
    analysis_mode: str = ""
    query_failure_policy: str = ""

    def unsigned_dict(self) -> dict[str, object]:
        value = {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "batch_schema_version": self.batch_schema_version,
            "run_id": self.run_id,
            "mode": self.mode,
            "output_root": self.output_root,
            "inventory_digest": self.inventory_digest,
            "provider": self.provider,
            "targets": [target.to_dict() for target in self.targets],
        }
        if self.analysis_mode:
            value["analysis_mode"] = self.analysis_mode
            value["query_failure_policy"] = self.query_failure_policy
        return value

    def to_dict(self) -> dict[str, object]:
        return {
            **self.unsigned_dict(),
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
        }

    def verify_digest(self) -> bool:
        return self.plan_digest == sha256_canonical_json(self.unsigned_dict())


@dataclass(frozen=True)
class TargetStatus:
    target_id: str
    state: TargetState
    attempt: int = 0
    stage: str | None = None
    output_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "target_id": self.target_id, "state": self.state, "attempt": self.attempt,
            "stage": self.stage, "output_path": self.output_path,
            "error_code": self.error_code, "error_message": self.error_message,
            "started_at": self.started_at, "finished_at": self.finished_at,
        }


@dataclass(frozen=True)
class AggregateSummary:
    total: int
    completed: int = 0
    completed_with_gaps: int = 0
    failed: int = 0
    paused: int = 0
    verdict_counts: dict[str, int] = field(default_factory=dict)
    gaps: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total, "completed": self.completed,
            "completed_with_gaps": self.completed_with_gaps, "failed": self.failed,
            "paused": self.paused, "gaps": self.gaps,
            "verdict_counts": dict(sorted(self.verdict_counts.items())),
        }


__all__ = [
    "AggregateSummary", "BatchMode", "BatchPlan", "BatchTargetPlan",
    "CanonicalCorpus", "CorpusTarget", "FingerprintType", "TargetCapability",
    "TargetIdentity", "TargetState", "TargetStatus",
]
