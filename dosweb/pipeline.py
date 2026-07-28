"""Provider-neutral resumable pipeline for injected local stage executors."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, TypeAlias

from dosweb.artifacts.identifiers import canonical_json, file_sha256
from dosweb.errors import AnalyzerError

STAGES: Final[tuple[str, ...]] = ("entries", "growth", "flows", "lifecycle", "conclude", "report")
SCHEMA_VERSION: Final = "2.0"
TOOL_VERSION: Final = "0.1.0"
_MAX_RECORDS: Final = 4096
_MAX_RECORD_BYTES: Final = 262144
_MAX_TOTAL_BYTES: Final = 16 * 1024 * 1024
Payload: TypeAlias = bytes | bytearray | memoryview | str | Sequence[Mapping[str, object]]


@dataclass(frozen=True)
class StageFingerprint:
    schema_version: str = SCHEMA_VERSION
    tool_version: str = TOOL_VERSION
    implementation_version: str = "v1"
    database_fingerprint: str = ""
    query_pack_hash: str = ""
    config_hash: str = ""
    upstream_hashes: Mapping[str, str] = field(default_factory=dict)
    stage: str = ""
    model_fingerprint: str = ""
    report_fingerprint: str = ""
    config_fingerprint: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"stage": self.stage, "schema_version": self.schema_version, "tool_version": self.tool_version, "implementation_version": self.implementation_version, "database_fingerprint": self.database_fingerprint, "query_pack_hash": self.query_pack_hash, "config_hash": self.config_hash or self.config_fingerprint, "config_fingerprint": self.config_fingerprint or self.config_hash, "model_fingerprint": self.model_fingerprint, "report_fingerprint": self.report_fingerprint, "upstream_hashes": dict(sorted((str(k), str(v)) for k, v in self.upstream_hashes.items()))}

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict())).hexdigest()

    @classmethod
    def for_stage(cls, stage: str, **kwargs: Any) -> "StageFingerprint":
        if stage not in STAGES:
            raise ValueError(f"unknown stage: {stage}")
        return cls(stage=stage, **kwargs)


@dataclass(frozen=True)
class StageContext:
    stage: str
    output_root: Path
    fingerprint: StageFingerprint
    upstream: Mapping[str, Mapping[str, object]]
    run: Mapping[str, object]


@dataclass(frozen=True)
class StageOutput:
    artifacts: Mapping[str, Payload]
    metadata: Mapping[str, object] = field(default_factory=dict)


Executor: TypeAlias = Callable[[StageContext], StageOutput | Mapping[str, Payload]]


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(canonical_json(dict(value)) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _safe_relative(raw: str) -> Path:
    if not raw or "\x00" in raw:
        raise AnalyzerError("ARTIFACT_INVALID_PATH", "Stage artifact path is invalid.", {"path": raw})
    path = Path(raw)
    if path.is_absolute() or path == Path(".") or ".." in path.parts:
        raise AnalyzerError("ARTIFACT_INVALID_PATH", "Stage artifact path must stay within the output root.", {"path": raw})
    normalized = Path(os.path.normpath(raw))
    if normalized == Path("run.json") or normalized.parts[:1] in ((".stage-manifests",), (".pipeline.lock",)):
        raise AnalyzerError("ARTIFACT_INVALID_PATH", "Stage cannot overwrite pipeline metadata.", {"path": raw})
    return normalized


def _assert_no_symlink_path(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.parts[0])
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise AnalyzerError("ARTIFACT_UNSAFE_OUTPUT_PATH", "Could not validate output path.", {"path": str(path)}) from exc
        if stat.S_ISLNK(info.st_mode):
            raise AnalyzerError("ARTIFACT_UNSAFE_OUTPUT_PATH", "Output path must not contain symlinks.", {"path": str(path)})


def _actual_record_count(path: Path) -> int:
    count, last = 0, b""
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            count += chunk.count(b"\n")
            last = chunk[-1:]
    return count + (1 if last and last != b"\n" else 0)


def _encode_payload(payload: Payload) -> tuple[bytes, int]:
    if isinstance(payload, str):
        data = payload.encode("utf-8")
        count = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    elif isinstance(payload, (bytes, bytearray, memoryview)):
        data = bytes(payload)
        count = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    elif isinstance(payload, Sequence):
        if len(payload) > _MAX_RECORDS:
            raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Stage contains too many records.")
        encoded: list[bytes] = []
        for index, record in enumerate(payload, 1):
            if not isinstance(record, Mapping):
                raise AnalyzerError("ARTIFACT_INVALID_RECORD", "Stage records must be mappings.", {"line": index})
            try:
                line = canonical_json(dict(record))
            except (TypeError, ValueError, OverflowError, RecursionError) as exc:
                raise AnalyzerError("ARTIFACT_INVALID_RECORD", "Stage record is not strict canonical JSON.", {"line": index}) from exc
            if len(line) > _MAX_RECORD_BYTES:
                raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Stage record exceeds its byte limit.", {"line": index})
            encoded.append(line + b"\n")
        data, count = b"".join(encoded), len(encoded)
    else:
        raise AnalyzerError("ARTIFACT_INVALID_RECORD", "Stage returned an unsupported payload.")
    if len(data) > _MAX_TOTAL_BYTES or count > _MAX_RECORDS:
        raise AnalyzerError("ARTIFACT_LIMIT_EXCEEDED", "Stage artifact exceeds configured limits.")
    return data, count


class Pipeline:
    def __init__(self, output_root: Path | str | None = None, executors: Mapping[str, Executor] | None = None, *, output_dir: Path | str | None = None, database_fingerprint: str = "", model_fingerprint: str = "", report_fingerprint: str = "", config_fingerprint: str = "", query_pack_hash: str = "", config_hash: str = "", schema_version: str = SCHEMA_VERSION, tool_version: str = TOOL_VERSION, implementation_versions: Mapping[str, str] | None = None, fingerprints: Mapping[str, str] | None = None, resume: bool = False, preflight: Callable[[], None] | None = None) -> None:
        root = output_root if output_root is not None else output_dir
        if root is None:
            raise TypeError("output_root is required")
        supplied = dict(fingerprints or {})
        self.output_root = Path(root)
        self.executors = dict(executors or {})
        self.database_fingerprint = database_fingerprint or supplied.get("database", "")
        self.model_fingerprint = model_fingerprint or supplied.get("model", "")
        self.report_fingerprint = report_fingerprint or supplied.get("report", "")
        self.config_fingerprint = config_fingerprint or config_hash or supplied.get("config", "")
        self.query_pack_hash = query_pack_hash or supplied.get("query_pack", "")
        self.config_hash = config_hash
        self.schema_version = schema_version
        self.tool_version = tool_version
        self.implementation_versions = dict(implementation_versions or {})
        self.resume = resume
        self.preflight = preflight
        self._run: dict[str, object] = {}
        self._prior_stage_metadata: dict[str, Mapping[str, object]] = {}

    @property
    def run_path(self) -> Path:
        return self.output_root / "run.json"

    @contextmanager
    def _locked_output(self):
        _assert_no_symlink_path(self.output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        _assert_no_symlink_path(self.output_root)
        lock_path = self.output_root / ".pipeline.lock"
        if lock_path.exists() and lock_path.is_symlink():
            raise AnalyzerError("ARTIFACT_UNSAFE_OUTPUT_PATH", "Pipeline lock must not be a symlink.")
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def run(self, target: str = "analyze") -> Mapping[str, object]:
        if target != "analyze" and target not in STAGES:
            raise AnalyzerError("CONFIG_INVALID_COMMAND", f"Unknown pipeline target: {target}.")
        last_stage = STAGES[-1] if target == "analyze" else target
        with self._locked_output():
            if self.preflight is not None:
                self.preflight()
            self._prior_stage_metadata = self._load_prior_stage_manifests()
            self._run = self._load_run() if self.resume else self._new_run()
            self._run.update(status="running", error=None)
            self._write_run()
            upstream_hashes: dict[str, str] = {}
            upstream: dict[str, Mapping[str, object]] = {}
            for stage in STAGES:
                expected = self._fingerprint(stage, upstream_hashes)
                if not self._reusable(stage, expected):
                    self._invalidate_from(stage)
                    try:
                        self._publish(stage, expected, self._execute(stage, expected, upstream))
                        self._write_run()
                    except AnalyzerError as exc:
                        self._mark_failure(stage, exc)
                        self._write_run()
                        raise
                    except Exception as exc:
                        error = AnalyzerError("ANALYSIS_STAGE_FAILED", "Injected stage executor failed.", {"stage": stage, "error_type": type(exc).__name__})
                        self._mark_failure(stage, error)
                        self._write_run()
                        raise error from exc
                metadata = self._stage_meta(stage)
                upstream[stage] = metadata
                upstream_hashes[stage] = str(metadata.get("output_hash", ""))
                if stage == last_stage:
                    break
            self._run.update(status="completed", error=None)
            self._write_run()
            return self._run

    def _new_run(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "tool_version": self.tool_version, "status": "pending", "error": None, "stages": {stage: {"status": "pending"} for stage in STAGES}}

    def _load_run(self) -> dict[str, object]:
        if not self.run_path.exists():
            return self._new_run()
        try:
            value = json.loads(self.run_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AnalyzerError("ARTIFACT_RUN_METADATA_INVALID", "Resume run metadata is malformed.") from exc
        if not isinstance(value, dict) or not isinstance(value.get("stages"), dict):
            raise AnalyzerError("ARTIFACT_RUN_METADATA_INVALID", "Resume run metadata is malformed.")
        return value

    def _write_run(self) -> None:
        _atomic_json(self.run_path, self._run)

    def _load_prior_stage_manifests(self) -> dict[str, Mapping[str, object]]:
        """Snapshot only prior manifests whose artifact ownership is provable."""
        prior: dict[str, Mapping[str, object]] = {}
        manifest_root = self.output_root / ".stage-manifests"
        for stage in STAGES:
            path = manifest_root / f"{stage}.json"
            try:
                _assert_no_symlink_path(path)
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError, AnalyzerError):
                continue
            if not isinstance(value, Mapping) or value.get("stage") != stage:
                continue
            artifacts = value.get("artifacts")
            if not isinstance(artifacts, list):
                continue
            valid = True
            for artifact in artifacts:
                if not isinstance(artifact, Mapping) or not isinstance(artifact.get("path"), str):
                    valid = False
                    break
                try:
                    _safe_relative(artifact["path"])
                except AnalyzerError:
                    valid = False
                    break
            if valid:
                prior[stage] = dict(value)
        return prior

    def _fingerprint(self, stage: str, upstream: Mapping[str, str]) -> StageFingerprint:
        return StageFingerprint(schema_version=self.schema_version, tool_version=self.tool_version, implementation_version=self.implementation_versions.get(stage, "v1"), database_fingerprint=self.database_fingerprint, query_pack_hash=self.query_pack_hash, config_hash=self.config_hash, upstream_hashes=dict(upstream), stage=stage, model_fingerprint=self.model_fingerprint if stage != "entries" else "", report_fingerprint=self.report_fingerprint if stage == "report" else "", config_fingerprint=self.config_fingerprint)

    def _stage_meta(self, stage: str) -> Mapping[str, object]:
        stages = self._run.get("stages")
        value = stages.get(stage) if isinstance(stages, Mapping) else None
        return value if isinstance(value, Mapping) else {}

    def _reusable(self, stage: str, expected: StageFingerprint) -> bool:
        metadata = self._stage_meta(stage)
        if metadata.get("status") != "completed" or metadata.get("fingerprint") != expected.to_dict():
            return False
        artifacts = metadata.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts or metadata.get("output_hash") != hashlib.sha256(canonical_json(artifacts)).hexdigest():
            return False
        manifest_path = self.output_root / ".stage-manifests" / f"{stage}.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        if manifest != metadata:
            return False
        for item in artifacts:
            if not isinstance(item, Mapping) or item.get("schema_version") != self.schema_version:
                return False
            raw, digest, count = item.get("path"), item.get("sha256"), item.get("record_count")
            if not isinstance(raw, str) or not isinstance(digest, str) or not isinstance(count, int) or isinstance(count, bool) or count < 0:
                return False
            try:
                path = self.output_root / _safe_relative(raw)
                _assert_no_symlink_path(path)
                if not path.is_file() or file_sha256(path) != digest or _actual_record_count(path) != count:
                    return False
            except (OSError, AnalyzerError):
                return False
        return True

    def _invalidate_from(self, first: str) -> None:
        stages = self._run.get("stages")
        if not isinstance(stages, dict):
            stages = {}
            self._run["stages"] = stages
        active = False
        for stage in STAGES:
            active |= stage == first
            if active:
                stages[stage] = {"status": "invalid"}

    def _execute(self, stage: str, fingerprint: StageFingerprint, upstream: Mapping[str, Mapping[str, object]]) -> StageOutput:
        executor = self.executors.get(stage)
        if executor is None:
            raise AnalyzerError("INTERNAL_STAGE_EXECUTORS_UNAVAILABLE", "Production stage executors are unavailable.", {"stage": stage})
        value = executor(StageContext(stage, self.output_root, fingerprint, upstream, self._run))
        if isinstance(value, StageOutput):
            return value
        if isinstance(value, Mapping):
            return StageOutput(value)
        raise AnalyzerError("ARTIFACT_INVALID_RECORD", "Stage executor returned an invalid output.", {"stage": stage})

    def _publish(self, stage: str, fingerprint: StageFingerprint, result: StageOutput) -> None:
        if not result.artifacts:
            raise AnalyzerError("ARTIFACT_EMPTY_STAGE", "A completed stage must publish an artifact.", {"stage": stage})
        normalized: dict[str, tuple[Path, Payload]] = {}
        for raw, payload in result.artifacts.items():
            relative = _safe_relative(str(raw))
            key = relative.as_posix()
            if key in normalized:
                raise AnalyzerError("ARTIFACT_DUPLICATE_PATH", "Stage artifact paths normalize to the same destination.", {"path": key})
            destination = self.output_root / relative
            _assert_no_symlink_path(destination)
            normalized[key] = (destination, payload)
        temporary_root = Path(tempfile.mkdtemp(prefix=f".stage-{stage}-", dir=self.output_root))
        written: list[tuple[str, Path, dict[str, object]]] = []
        try:
            for relative, (destination, payload) in sorted(normalized.items()):
                data, count = _encode_payload(payload)
                staged = temporary_root / relative
                staged.parent.mkdir(parents=True, exist_ok=True)
                with staged.open("wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                digest = file_sha256(staged)
                if digest != hashlib.sha256(data).hexdigest() or _actual_record_count(staged) != count:
                    raise AnalyzerError("ARTIFACT_VALIDATION_FAILED", "Staged artifact validation failed.", {"path": relative})
                written.append((relative, destination, {"path": relative, "sha256": digest, "record_count": count, "byte_count": len(data), "schema_version": self.schema_version}))
            artifacts = [item[2] for item in written]
            manifest = {"stage": stage, "status": "completed", "fingerprint": fingerprint.to_dict(), "artifacts": artifacts, "output_hash": hashlib.sha256(canonical_json(artifacts)).hexdigest(), "metadata": dict(result.metadata)}
            staged_manifest = temporary_root / "manifest.json"
            with staged_manifest.open("wb") as stream:
                stream.write(canonical_json(manifest) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            old = self._prior_stage_metadata.get(stage, {})
            old_paths = {item.get("path") for item in old.get("artifacts", []) if isinstance(item, Mapping) and isinstance(item.get("path"), str)} if isinstance(old.get("artifacts"), list) else set()
            new_paths = {item[0] for item in written}
            backups: list[tuple[Path, Path]] = []
            published: list[Path] = []
            manifest_destination = self.output_root / ".stage-manifests" / f"{stage}.json"
            manifest_backup: Path | None = None
            manifest_touched = False
            try:
                for relative in sorted(old_paths - new_paths):
                    destination = self.output_root / _safe_relative(relative)
                    if destination.exists():
                        backup = temporary_root / "backups" / relative
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(destination, backup)
                        backups.append((destination, backup))
                for relative, destination, _metadata in written:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists():
                        backup = temporary_root / "backups" / relative
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(destination, backup)
                        backups.append((destination, backup))
                    os.replace(temporary_root / relative, destination)
                    published.append(destination)
                manifest_destination.parent.mkdir(parents=True, exist_ok=True)
                if manifest_destination.exists():
                    manifest_backup = temporary_root / "old-manifest.json"
                    os.replace(manifest_destination, manifest_backup)
                    manifest_touched = True
                manifest_touched = True
                os.replace(staged_manifest, manifest_destination)
                _fsync_directory(self.output_root)
            except Exception:
                for destination in published:
                    destination.unlink(missing_ok=True)
                for destination, backup in reversed(backups):
                    if backup.exists():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(backup, destination)
                if manifest_backup is not None and manifest_backup.exists():
                    manifest_destination.unlink(missing_ok=True)
                    os.replace(manifest_backup, manifest_destination)
                elif manifest_touched:
                    manifest_destination.unlink(missing_ok=True)
                raise
            stages = self._run["stages"]
            assert isinstance(stages, dict)
            stages[stage] = manifest
            self._prior_stage_metadata[stage] = manifest
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)

    def _mark_failure(self, stage: str, error: AnalyzerError) -> None:
        stages = self._run.get("stages")
        if isinstance(stages, dict):
            seen = False
            for name in STAGES:
                if name == stage:
                    stages[name] = {"status": "failed", "error": error.code}
                    seen = True
                elif seen:
                    stages[name] = {"status": "pending"}
        self._run.update(status="failed", error={"code": error.code, "message": error.message})


__all__ = ["Executor", "Pipeline", "Payload", "SCHEMA_VERSION", "StageContext", "StageFingerprint", "StageOutput", "STAGES"]
