from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, fields
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import TypeVar

from dosweb.artifacts.identifiers import canonical_json
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle.models import (
    AbstractInstance,
    AnalysisBudget,
    AnalysisResult,
    CountInterval,
    Effect,
    Event,
    Holder,
    Program,
    ResourceFamily,
    ResourceState,
    SourceLocation,
    Trace,
    Transition,
)


_MAX_JSON_BYTES = 16 * 1024 * 1024
T = TypeVar("T")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(value)


def _exact(cls: type[T], value: object, label: str, **updates: object) -> T:
    record = dict(_mapping(value, label))
    expected = {item.name for item in fields(cls)}
    if set(record) != expected:
        raise ValueError(f"{label} fields are invalid")
    record.update(updates)
    return cls(**record)  # type: ignore[arg-type]


def location_from_dict(value: object) -> SourceLocation:
    return _exact(SourceLocation, value, "source location")


def effect_from_dict(value: object) -> Effect:
    record = dict(_mapping(value, "effect"))
    location = location_from_dict(record.get("location"))
    evidence_ids = tuple(str(item) for item in _sequence(record.get("evidence_ids"), "effect evidence_ids"))
    record["location"] = location
    record["evidence_ids"] = evidence_ids
    return _exact(Effect, record, "effect")


def transition_from_dict(value: object) -> Transition:
    record = dict(_mapping(value, "transition"))
    effects_value = _sequence(record.get("effects"), "transition effects")
    assumptions_value = _sequence(record.get("assumptions"), "transition assumptions")
    record["effects"] = tuple(effect_from_dict(item) for item in effects_value)
    record["assumptions"] = tuple(str(item) for item in assumptions_value)
    return _exact(Transition, record, "transition")


def program_to_dict(program: Program) -> dict[str, object]:
    return asdict(program)


def program_from_dict(value: object) -> Program:
    record = dict(_mapping(value, "program"))
    expected = {item.name for item in fields(Program)}
    if set(record) == expected - {"coverage_gaps"}:
        record["coverage_gaps"] = []
    elif set(record) != expected:
        raise ValueError("program fields are invalid")
    record["families"] = tuple(
        ResourceFamily(
            family_id=str(item_record.get("family_id")),
            allocation=location_from_dict(item_record.get("allocation")),
            context=tuple(str(part) for part in _sequence(item_record.get("context"), "resource context")),
            resource_type=str(item_record.get("resource_type")),
            requires_close=item_record.get("requires_close"),
            item_size_upper=item_record.get("item_size_upper"),
        )
        for item in _sequence(record["families"], "program families")
        for item_record in (_mapping(item, "resource family"),)
        if set(item_record) == {item.name for item in fields(ResourceFamily)}
    )
    if len(record["families"]) != len(_sequence(value["families"], "program families")):  # type: ignore[index]
        raise ValueError("resource family fields are invalid")
    record["instances"] = tuple(_exact(AbstractInstance, item, "abstract instance") for item in _sequence(record["instances"], "program instances"))
    record["holders"] = tuple(_exact(Holder, item, "holder") for item in _sequence(record["holders"], "program holders"))
    record["events"] = tuple(_exact(Event, item, "event") for item in _sequence(record["events"], "program events"))
    record["transitions"] = tuple(transition_from_dict(item) for item in _sequence(record["transitions"], "program transitions"))
    record["entry_event_ids"] = tuple(str(item) for item in _sequence(record["entry_event_ids"], "entry_event_ids"))
    record["exit_event_ids"] = tuple(str(item) for item in _sequence(record["exit_event_ids"], "exit_event_ids"))
    coverage_gaps = _sequence(record["coverage_gaps"], "coverage_gaps")
    if any(
        not isinstance(item, list)
        or len(item) != 5
        or not all(isinstance(part, str) for part in item)
        for item in coverage_gaps
    ):
        raise ValueError("coverage_gaps entries are invalid")
    record["coverage_gaps"] = tuple(
        (item[0], item[1], item[2], item[3], item[4]) for item in coverage_gaps  # type: ignore[index]
    )
    return Program(**record)  # type: ignore[arg-type]


def budget_from_dict(value: object) -> AnalysisBudget:
    return _exact(AnalysisBudget, value, "analysis budget")


def state_to_dict(state: ResourceState) -> dict[str, object]:
    return {
        "instance_families": [list(item) for item in state.instance_families],
        "instance_abstractions": [list(item) for item in state.instance_abstractions],
        "instance_confidences": [list(item) for item in state.instance_confidences],
        "family_requires_close": [list(item) for item in state.family_requires_close],
        "family_size_upper": [list(item) for item in state.family_size_upper],
        "holder_kinds": [list(item) for item in state.holder_kinds],
        "holder_scopes": [list(item) for item in state.holder_scopes],
        "holder_precisions": [list(item) for item in state.holder_precisions],
        "held_edges": [list(item) for item in sorted(state.held_edges)],
        "created_instances": sorted(state.created_instances),
        "open_obligations": sorted(state.open_obligations),
        "must_released": sorted(state.must_released),
        "obligation_counts": [
            [family_id, {"lower": interval.lower, "upper": interval.upper}]
            for family_id, interval in state.obligation_counts
        ],
        "allocation_counts": [
            [family_id, {"lower": interval.lower, "upper": interval.upper}]
            for family_id, interval in state.allocation_counts
        ],
        "held_counts": [
            [family_id, {"lower": interval.lower, "upper": interval.upper}]
            for family_id, interval in state.held_counts
        ],
        "peak_held_counts": [list(item) for item in state.peak_held_counts],
        "repeated_instances": sorted(state.repeated_instances),
        "unknown_reasons": list(state.unknown_reasons),
    }


def analysis_result_to_dict(result: AnalysisResult) -> dict[str, object]:
    return {
        "exit_states": {key: state_to_dict(value) for key, value in sorted(result.exit_states.items())},
        "event_states": {key: state_to_dict(value) for key, value in sorted(result.event_states.items())},
        "traces": {key: asdict(value) for key, value in sorted(result.traces.items())},
        "terminated": result.terminated,
        "unknown_reasons": list(result.unknown_reasons),
        "lifecycle_statuses": list(result.lifecycle_statuses),
        "steps": result.steps,
    }


def load_regular_bytes_with_sha256(
    path: Path,
    *,
    max_bytes: int = _MAX_JSON_BYTES,
    required_mode: int | None = None,
) -> tuple[bytes, str]:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | os.O_NONBLOCK
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size > max_bytes
            or (
                required_mode is not None
                and (
                    stat.S_IMODE(info.st_mode) != required_mode
                    or info.st_uid != os.geteuid()
                    or info.st_nlink != 1
                )
            )
        ):
            raise OSError("input is not a bounded regular file")
        raw = bytearray()
        while len(raw) <= max_bytes:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > max_bytes:
            raise OSError("input exceeds byte limit")
        payload = bytes(raw)
        return payload, hashlib.sha256(payload).hexdigest()
    except OSError as exc:
        raise AnalyzerError(
            "ARTIFACT_INPUT_INVALID",
            "Resource lifecycle input is invalid.",
            {"path": str(path)},
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def load_json_regular_with_sha256(
    path: Path,
    *,
    max_bytes: int = _MAX_JSON_BYTES,
    required_mode: int | None = None,
) -> tuple[object, str]:
    raw, digest = load_regular_bytes_with_sha256(
        path,
        max_bytes=max_bytes,
        required_mode=required_mode,
    )
    try:
        def finite_float(value: str) -> float:
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError("non-finite JSON number")
            return parsed

        parsed = json.loads(
            raw.decode("utf-8"),
            parse_float=finite_float,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        return parsed, digest
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle input is invalid.", {"path": str(path)}) from exc


def load_json_regular(path: Path, *, max_bytes: int = _MAX_JSON_BYTES) -> object:
    return load_json_regular_with_sha256(path, max_bytes=max_bytes)[0]


def load_text_regular(path: Path, *, max_bytes: int = _MAX_JSON_BYTES) -> str:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise OSError("input is not a bounded regular file")
        raw = bytearray()
        while len(raw) <= max_bytes:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, max_bytes + 1 - len(raw)),
            )
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > max_bytes:
            raise OSError("input exceeds byte limit")
        return raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise AnalyzerError(
            "ARTIFACT_INPUT_INVALID",
            "Resource lifecycle text input is invalid.",
            {"path": str(path)},
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def ensure_output_directory(path: Path) -> Path:
    try:
        if path.exists() and path.is_symlink():
            raise OSError("output is a symlink")
        path.mkdir(parents=True, exist_ok=True)
        resolved = path.resolve(strict=True)
        if not resolved.is_dir():
            raise OSError("output is not a directory")
        return resolved
    except OSError as exc:
        raise AnalyzerError("ARTIFACT_UNSAFE_OUTPUT_PATH", "Resource lifecycle output path is invalid.") from exc


def atomic_write_json(path: Path, value: object) -> None:
    output = ensure_output_directory(path.parent)
    raw = canonical_json(value) + b"\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=output, prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output / path.name)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, value: str) -> None:
    output = ensure_output_directory(path.parent)
    raw = value.encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=output, prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output / path.name)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
