"""Deterministic batch-plan construction and publication helpers."""
from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from dosweb.artifacts.identifiers import canonical_json, sha256_canonical_json
from dosweb.batch.models import BatchPlan, BatchTargetPlan, CanonicalCorpus, TargetCapability, TargetIdentity
from dosweb.errors import AnalyzerError

TOOL_VERSION = "dosweb-v2"
BATCH_SCHEMA_VERSION = "java-web-dos-batch-v2"


def _invalid(reason: str, **details: object) -> AnalyzerError:
    return AnalyzerError("BATCH_PLAN_INVALID", "Batch plan validation failed.", {"reason": reason, **{k: str(v)[:256] for k, v in details.items()}})


def _safe_output(value: str | Path) -> str:
    raw = str(value).replace("\\", "/")
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise _invalid("UNSAFE_OUTPUT_PATH")
    return path.as_posix()


_PROVIDER_KEYS = frozenset({
    "model", "base_url", "temperature", "timeout_seconds", "max_retries",
    "allow_remote_llm", "pilot_skipped", "cache_dir", "config", "codeql_binary",
})
_FINGERPRINT_TYPES = frozenset({"git-commit", "tree-sha256"})
_ATTESTATIONS = frozenset({"git-commit", "tree-sha256", "unavailable"})
_TARGET_STATES = frozenset({"queued", "paused"})


def _provider_settings(settings: Mapping[str, object] | None) -> dict[str, object]:
    """Keep only explicitly non-secret provider settings, with strict types."""
    if not settings:
        return {}
    output: dict[str, object] = {}
    for key, value in settings.items():
        if key not in _PROVIDER_KEYS:
            raise _invalid("PROVIDER_KEY_INVALID", key=key)
        if key in {"allow_remote_llm", "pilot_skipped"}:
            if not isinstance(value, bool):
                raise _invalid("PROVIDER_TYPE_INVALID", key=key)
        elif key in {"timeout_seconds", "max_retries"}:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise _invalid("PROVIDER_TYPE_INVALID", key=key)
        elif key == "temperature":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise _invalid("PROVIDER_TYPE_INVALID", key=key)
        elif value is not None and not isinstance(value, str):
            raise _invalid("PROVIDER_TYPE_INVALID", key=key)
        output[key] = value
    return output


def _validate_string(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid(reason)
    return value


def _validate_loaded_target(item: Mapping[str, object]) -> BatchTargetPlan:
    legacy_fields = {"target_id", "identity", "output_path", "capability", "initial_state"}
    fields = set(item)
    if fields != legacy_fields and fields != legacy_fields | {"database_fingerprint"}:
        raise ValueError("target fields")
    identity = item["identity"]
    capability = item["capability"]
    if not isinstance(identity, Mapping) or not isinstance(capability, Mapping):
        raise ValueError("target shape")
    expected_identity = {"target_id", "index", "name", "fingerprint_type", "fingerprint", "source_path", "database_path", "slug"}
    if set(identity) != expected_identity or item["target_id"] != identity.get("target_id"):
        raise ValueError("target identity fields")
    index = identity["index"]
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise ValueError("target index")
    name = identity["name"]
    if not isinstance(name, str) or not name or name.count("/") != 1:
        raise ValueError("target name")
    for key in ("fingerprint", "source_path", "database_path"):
        if not isinstance(identity[key], str) or not identity[key]:
            raise ValueError("target identity value")
    if identity["fingerprint_type"] not in _FINGERPRINT_TYPES:
        raise ValueError("fingerprint type")
    fingerprint = identity["fingerprint"]
    if not re.fullmatch(r"[0-9a-f]{40}" if identity["fingerprint_type"] == "git-commit" else r"[0-9a-f]{64}", fingerprint):
        raise ValueError("fingerprint format")
    for key in ("source_path", "database_path"):
        path = PurePosixPath(identity[key].replace("\\", "/"))
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or path.as_posix() != identity[key]:
            raise ValueError("identity path")
    target_identity = TargetIdentity(index, name, identity["fingerprint_type"], fingerprint, identity["source_path"], identity["database_path"])
    if identity["slug"] != target_identity.slug or identity["target_id"] != target_identity.identity_id:
        raise ValueError("target id or slug")
    legacy_capability = {"provider_eligible", "public_source_url", "attestation", "reason"}
    capability_fields = set(capability)
    provider_capability = legacy_capability | {"provider_source_path", "provider_source_commit"}
    if capability_fields != legacy_capability and capability_fields != provider_capability:
        raise ValueError("capability fields")
    if not isinstance(capability["provider_eligible"], bool) or capability["attestation"] not in _ATTESTATIONS:
        raise ValueError("capability type")
    for key in ("public_source_url", "reason"):
        if capability[key] is not None and not isinstance(capability[key], str):
            raise ValueError("capability value")
    provider_source_path = capability.get("provider_source_path")
    provider_source_commit = capability.get("provider_source_commit")
    if provider_source_path is not None:
        if not isinstance(provider_source_path, str):
            raise ValueError("provider source path")
        path = PurePosixPath(provider_source_path.replace("\\", "/"))
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or path.as_posix() != provider_source_path:
            raise ValueError("provider source path")
    if provider_source_commit is not None and (
        not isinstance(provider_source_commit, str)
        or not re.fullmatch(r"[0-9a-f]{40}", provider_source_commit)
    ):
        raise ValueError("provider source commit")
    if (provider_source_path is None) != (provider_source_commit is None):
        raise ValueError("provider source binding")
    output_path = item["output_path"]
    if not isinstance(output_path, str):
        raise ValueError("output path")
    initial_state = item["initial_state"]
    if initial_state not in _TARGET_STATES:
        raise ValueError("initial state")
    database_fingerprint = item.get("database_fingerprint", "")
    if (
        not isinstance(database_fingerprint, str)
        or (database_fingerprint and not re.fullmatch(r"[0-9a-f]{64}", database_fingerprint))
    ):
        raise ValueError("database fingerprint")
    return BatchTargetPlan(
        target_identity,
        _safe_output(output_path),
        TargetCapability(**dict(capability)),
        initial_state,
        item["target_id"],
        database_fingerprint,
    )


def _effective_output_key(value: str) -> str:
    path = PurePosixPath(value)
    try:
        index = path.parts.index("targets")
        suffix = path.parts[index + 1:]
    except ValueError:
        suffix = path.parts[-1:]
    if len(suffix) != 1:
        raise _invalid("OUTPUT_PATH_INVALID")
    return suffix[0]


def build_batch_plan(
    corpus: CanonicalCorpus,
    *,
    run_id: str,
    mode: str = "plan",
    output_root: str | Path = "results/java_web_dos_batch",
    tool_version: str = TOOL_VERSION,
    provider_settings: Mapping[str, object] | None = None,
) -> BatchPlan:
    """Create a digest-bound plan without running CodeQL, a provider, or the network."""
    if mode not in {"plan", "entries", "full"}:
        raise _invalid("MODE_INVALID")
    if not isinstance(run_id, str) or not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
        raise _invalid("RUN_ID_INVALID")
    output = _safe_output(output_root)
    targets: list[BatchTargetPlan] = []
    for target in corpus.targets:
        if not re.fullmatch(r"[0-9a-f]{64}", target.database_fingerprint):
            raise _invalid("DATABASE_FINGERPRINT_INVALID", target_id=target.identity.identity_id)
        target_output = f"{output}/targets/{target.index:03d}-{target.slug}"
        targets.append(BatchTargetPlan(
            identity=target.identity,
            output_path=target_output,
            capability=target.capability,
            initial_state="queued",
            target_id=target.identity.identity_id,
            database_fingerprint=target.database_fingerprint,
        ))
    indexes: set[int] = set()
    target_ids: set[str] = set()
    output_dirs: set[str] = set()
    for target in targets:
        if target.identity.index in indexes or target.target_id in target_ids:
            raise _invalid("DUPLICATE_TARGET_ID_OR_INDEX", target_id=target.target_id)
        indexes.add(target.identity.index)
        target_ids.add(target.target_id)
        effective = _effective_output_key(target.output_path)
        if effective in output_dirs:
            raise _invalid("DUPLICATE_EFFECTIVE_OUTPUT_DIR", output_path=effective)
        output_dirs.add(effective)
    provider = _provider_settings(provider_settings)
    if mode == "entries":
        provider["allow_remote_llm"] = False
    analysis_mode = "exploratory_entries" if mode == "entries" else "formal"
    query_failure_policy = "coverage_gap" if mode == "entries" else "fail_closed"
    unsigned = {
        "schema_version": 1,
        "tool_version": tool_version,
        "batch_schema_version": BATCH_SCHEMA_VERSION,
        "run_id": run_id,
        "mode": mode,
        "output_root": output,
        "inventory_digest": corpus.inventory_digest,
        "provider": provider,
        "analysis_mode": analysis_mode,
        "query_failure_policy": query_failure_policy,
        "targets": [target.to_dict() for target in targets],
    }
    digest = sha256_canonical_json(unsigned)
    plan_id = f"plan:{digest[:24]}"
    return BatchPlan(
        schema_version=1, tool_version=tool_version, batch_schema_version=BATCH_SCHEMA_VERSION,
        run_id=run_id, mode=mode, output_root=output, inventory_digest=corpus.inventory_digest,
        targets=tuple(targets), plan_id=plan_id, plan_digest=digest, provider=unsigned["provider"],
        analysis_mode=analysis_mode, query_failure_policy=query_failure_policy,
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise AnalyzerError("BATCH_PLAN_PUBLISH_FAILED", "Could not publish batch plan.") from exc


def _published_plan_payloads(plan: BatchPlan) -> tuple[bytes, bytes]:
    payload = canonical_json(plan.to_dict()) + b"\n"
    lines = [canonical_json(target.to_dict()) for target in plan.targets]
    manifest = b"\n".join(lines) + (b"\n" if lines else b"")
    return payload, manifest


def publish_batch_plan(plan: BatchPlan, output_directory: Path | str) -> tuple[Path, Path]:
    """Atomically publish canonical JSON and compatibility JSONL plan files."""
    if not plan.verify_digest():
        raise _invalid("PLAN_DIGEST_MISMATCH")
    root = Path(output_directory)
    payload, manifest = _published_plan_payloads(plan)
    json_path = root / "batch_plan.json"
    _atomic_write(json_path, payload)
    jsonl_path = root / "manifest.normalized.jsonl"
    _atomic_write(jsonl_path, manifest)
    return json_path, jsonl_path


def _create_or_verify_metadata(path: Path, expected: bytes) -> None:
    """Create immutable archive metadata or verify an identical existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise AnalyzerError("BATCH_PLAN_CONFLICT", "Existing batch archive metadata conflicts with the execution plan.")
    try:
        existing = path.read_bytes()
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise AnalyzerError("BATCH_PLAN_CONFLICT", "Existing batch archive metadata could not be verified.") from exc
    if existing is not None:
        if existing != expected:
            raise AnalyzerError("BATCH_PLAN_CONFLICT", "Existing batch archive metadata conflicts with the execution plan.")
        return

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(expected)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != expected:
                raise AnalyzerError("BATCH_PLAN_CONFLICT", "Existing batch archive metadata conflicts with the execution plan.")
        descriptor = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except AnalyzerError:
        raise
    except OSError as exc:
        raise AnalyzerError("BATCH_PLAN_PUBLISH_FAILED", "Could not publish batch archive metadata.") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_batch_plan_archive(plan: BatchPlan, output_directory: Path | str) -> tuple[Path, Path]:
    """Make an execution output self-contained without replacing metadata."""
    if not plan.verify_digest() or plan.plan_id != f"plan:{plan.plan_digest[:24]}":
        raise _invalid("PLAN_DIGEST_MISMATCH")
    root = Path(output_directory)
    payload, manifest = _published_plan_payloads(plan)
    paths = (
        (root / "batch_plan.json", payload),
        (root / "manifest.normalized.jsonl", manifest),
    )
    # Check all existing files before creating either, so known conflicts do not
    # leave a newly-created partial metadata pair behind.
    for path, expected in paths:
        if path.exists() or path.is_symlink():
            _create_or_verify_metadata(path, expected)
    for path, expected in paths:
        _create_or_verify_metadata(path, expected)
    return paths[0][0], paths[1][0]


def load_batch_plan(path: Path | str) -> BatchPlan:
    """Read a published plan and reject any identity or digest tampering."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid("PLAN_READ_FAILED") from exc
    if not isinstance(raw, Mapping):
        raise _invalid("PLAN_NOT_OBJECT")
    legacy_required = {"schema_version", "tool_version", "batch_schema_version", "run_id", "mode", "output_root", "inventory_digest", "provider", "targets", "plan_id", "plan_digest"}
    required = legacy_required | {"analysis_mode", "query_failure_policy"}
    if (set(raw) != legacy_required and set(raw) != required) or not isinstance(raw["targets"], list):
        raise _invalid("PLAN_FIELDS_INVALID")
    try:
        unsigned_fields = (required if set(raw) == required else legacy_required) - {"plan_id", "plan_digest"}
        unsigned = {key: raw[key] for key in unsigned_fields}
        digest = sha256_canonical_json(unsigned)
    except (TypeError, ValueError, MemoryError, RecursionError) as exc:
        raise _invalid("PLAN_DIGEST_INVALID") from exc
    if raw["plan_digest"] != digest or raw["plan_id"] != f"plan:{digest[:24]}":
        raise _invalid("PLAN_DIGEST_MISMATCH")
    try:
        if raw["schema_version"] != 1 or not isinstance(raw["tool_version"], str) or not raw["tool_version"]:
            raise ValueError("schema")
        if not isinstance(raw["plan_digest"], str) or not re.fullmatch(r"[0-9a-f]{64}", raw["plan_digest"]):
            raise ValueError("plan digest")
        if not isinstance(raw["plan_id"], str) or not re.fullmatch(r"plan:[0-9a-f]{24}", raw["plan_id"]):
            raise ValueError("plan id")
        if raw["batch_schema_version"] not in {"java-web-dos-batch-v1", BATCH_SCHEMA_VERSION} or raw["mode"] not in {"plan", "entries", "full"}:
            raise ValueError("enum")
        if set(raw) == required and (raw["analysis_mode"] not in {"formal", "exploratory_entries"} or raw["query_failure_policy"] not in {"fail_closed", "coverage_gap"}):
            raise ValueError("analysis mode")
        if (
            not isinstance(raw["run_id"], str) or not raw["run_id"]
            or "/" in raw["run_id"] or "\\" in raw["run_id"] or ".." in raw["run_id"]
            or not isinstance(raw["output_root"], str)
        ):
            raise ValueError("plan identity")
        output_root = _safe_output(raw["output_root"])
        if (
            output_root != raw["output_root"]
            or not isinstance(raw["inventory_digest"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", raw["inventory_digest"])
        ):
            raise ValueError("plan values")
        provider = raw["provider"]
        if not isinstance(provider, Mapping) or dict(provider) != _provider_settings(provider):
            raise ValueError("provider")
        targets = [_validate_loaded_target(item) for item in raw["targets"]]
        indexes = [target.identity.index for target in targets]
        ids = [target.target_id for target in targets]
        outputs = [_effective_output_key(target.output_path) for target in targets]
        for target in targets:
            expected_output = f"{output_root}/targets/{target.identity.index:03d}-{target.identity.slug}"
            if target.output_path != expected_output:
                raise ValueError("noncanonical output path")
        if len(set(indexes)) != len(indexes) or len(set(ids)) != len(ids) or len(set(outputs)) != len(outputs):
            raise ValueError("duplicate target")
    except (TypeError, ValueError, KeyError, AttributeError, AnalyzerError) as exc:
        raise _invalid("TARGET_INVALID") from exc
    return BatchPlan(raw["schema_version"], raw["tool_version"], raw["batch_schema_version"], raw["run_id"], raw["mode"], output_root, raw["inventory_digest"], tuple(targets), raw["plan_id"], raw["plan_digest"], dict(provider), str(raw.get("analysis_mode", "")), str(raw.get("query_failure_policy", "")))


def write_target_binding(plan: BatchPlan, target: BatchTargetPlan, output_directory: Path | str) -> Path:
    """Publish target binding before execution so resume cannot cross identities."""
    if target not in plan.targets:
        raise _invalid("TARGET_NOT_IN_PLAN")
    path = Path(output_directory) / "batch_target.json"
    binding = {"plan_id": plan.plan_id, "plan_digest": plan.plan_digest, "run_id": plan.run_id, "mode": plan.mode, "analysis_mode": plan.analysis_mode, "query_failure_policy": plan.query_failure_policy, "target": target.to_dict()}
    _atomic_write(path, canonical_json(binding) + b"\n")
    return path

__all__ = ["build_batch_plan", "ensure_batch_plan_archive", "load_batch_plan", "publish_batch_plan", "write_target_binding"]
