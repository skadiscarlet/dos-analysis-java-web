from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import csv
from dataclasses import dataclass, replace
import hashlib
import io
import json
from pathlib import Path
import time
import tracemalloc
from typing import Final, Literal

from dosweb.artifacts.identifiers import file_sha256
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle.commands import TOOL_VERSION
from dosweb.resource_lifecycle.contracts import ExecutorContract
from dosweb.resource_lifecycle.invariants import InvariantCandidate, check_invariants
from dosweb.resource_lifecycle.io import atomic_write_json, atomic_write_text, ensure_output_directory, load_json_regular
from dosweb.resource_lifecycle.models import (
    AbstractInstance,
    AnalysisBudget,
    Effect,
    Event,
    Holder,
    Program,
    ResourceFamily,
    SourceLocation,
    Transition,
)
from dosweb.resource_lifecycle.solver import solve


EVALUATION_MODES: Final = (
    "full",
    "without_identity",
    "without_cross_event",
    "without_scope",
    "without_exit_coverage",
    "without_invariants",
)
_DIMENSIONS = {"held_instances", "item_size_bytes", "close_obligation"}
_STATUSES = {"bounded", "obligation_gap", "unknown", "not_applicable"}
_EXIT_KINDS = {"normal", "exceptional", "rejected", "cancelled", "internal"}


@dataclass(frozen=True)
class ExpectedOutcome:
    dimension: str
    lifecycle_status: str
    upper_bound: int | str | None
    reason_contains: str | None


@dataclass(frozen=True)
class EffectSpec:
    kind: str
    holder: str | None
    target_event: str | None
    contract_id: str | None


@dataclass(frozen=True)
class TransitionSpec:
    transition_id: str
    source: str
    target: str
    exit_kind: str
    cross_event: bool
    effects: tuple[EffectSpec, ...]


@dataclass(frozen=True)
class InvariantSpec:
    dimension: str
    scope: str
    upper_bound: int | str
    initial_holds: bool
    transitions_preserve: bool
    covers_writers: bool
    atomic: bool
    source_kind: str
    executor_contract_id: str | None
    writer_holder_id: str | None
    writer_target_event_id: str | None


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    group: int
    pair: str
    property: str
    requires_close: bool
    item_size_upper: int | None
    abstraction: str
    identity_confidence: str
    coverage_complete: bool
    transitions: tuple[TransitionSpec, ...]
    exit_events: tuple[str, ...]
    invariants: tuple[InvariantSpec, ...]
    expected: ExpectedOutcome


@dataclass(frozen=True)
class RegressionSuite:
    suite_id: str
    source_kind: str
    budget: AnalysisBudget
    cases: tuple[RegressionCase, ...]
    suite_sha256: str


def _object(value: object, expected: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{label} fields are invalid")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 512:
        raise ValueError(f"{label} must be a bounded non-empty string")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _optional_size(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("item_size_upper is invalid")
    return value


def _effect_spec(value: object) -> EffectSpec:
    if not isinstance(value, Mapping):
        raise ValueError("effect fields are invalid")
    kind_value = value.get("kind")
    expected = (
        {"kind", "holder", "target_event", "contract_id"}
        if kind_value == "dispatch"
        else ({"kind", "holder"} if "holder" in value else {"kind"})
    )
    record = _object(value, expected, "effect")
    kind = _string(record["kind"], "effect kind")
    if kind not in {"create", "retain", "drop", "release", "dispatch", "unknown_call"}:
        raise ValueError("suite effect kind is unsupported")
    holder = record.get("holder")
    if holder is not None:
        holder = _string(holder, "effect holder")
    if (kind in {"retain", "drop", "dispatch"}) != (holder is not None):
        raise ValueError("retain/drop/dispatch holder contract is invalid")
    target_event = record.get("target_event")
    contract_id = record.get("contract_id")
    if target_event is not None:
        target_event = _string(target_event, "effect target event")
    if contract_id is not None:
        contract_id = _string(contract_id, "effect contract id")
    if kind == "dispatch" and (target_event is None or contract_id is None):
        raise ValueError("dispatch target/contract is invalid")
    return EffectSpec(kind, holder, target_event, contract_id)


def _transition_spec(value: object) -> TransitionSpec:
    record = _object(value, {"id", "source", "target", "exit_kind", "cross_event", "effects"}, "transition")
    effects = record["effects"]
    if not isinstance(effects, list) or len(effects) > 64:
        raise ValueError("transition effects are invalid")
    exit_kind = _string(record["exit_kind"], "exit kind")
    if exit_kind not in _EXIT_KINDS:
        raise ValueError("transition exit kind is invalid")
    return TransitionSpec(
        _string(record["id"], "transition id"),
        _string(record["source"], "transition source"),
        _string(record["target"], "transition target"),
        exit_kind,
        _boolean(record["cross_event"], "cross_event"),
        tuple(_effect_spec(item) for item in effects),
    )


def _invariant_spec(value: object) -> InvariantSpec:
    record = _object(
        value,
        {
            "dimension", "scope", "upper_bound", "initial_holds", "transitions_preserve",
            "covers_writers", "atomic", "source_kind", "executor_contract_id",
            "writer_holder_id", "writer_target_event_id",
        },
        "invariant",
    )
    dimension = _string(record["dimension"], "invariant dimension")
    if dimension not in _DIMENSIONS:
        raise ValueError("invariant dimension is invalid")
    upper = record["upper_bound"]
    if isinstance(upper, bool) or not isinstance(upper, (int, str)) or (isinstance(upper, int) and upper < 0) or upper == "":
        raise ValueError("invariant upper bound is invalid")
    queue_identity = tuple(
        record[item]
        for item in (
            "executor_contract_id",
            "writer_holder_id",
            "writer_target_event_id",
        )
    )
    if record["scope"] == "task_queue":
        if any(not isinstance(item, str) or not item for item in queue_identity):
            raise ValueError("task queue invariant identity is invalid")
    elif any(item is not None for item in queue_identity):
        raise ValueError("non-queue invariant identity is invalid")
    return InvariantSpec(
        dimension,
        _string(record["scope"], "invariant scope"),
        upper,
        _boolean(record["initial_holds"], "initial_holds"),
        _boolean(record["transitions_preserve"], "transitions_preserve"),
        _boolean(record["covers_writers"], "covers_writers"),
        _boolean(record["atomic"], "atomic"),
        _string(record["source_kind"], "invariant source_kind"),
        queue_identity[0],  # type: ignore[arg-type]
        queue_identity[1],  # type: ignore[arg-type]
        queue_identity[2],  # type: ignore[arg-type]
    )


def _case(value: object) -> RegressionCase:
    record = _object(
        value,
        {"case_id", "group", "pair", "property", "resource", "instance", "coverage_complete", "transitions", "exit_events", "invariants", "expected"},
        "regression case",
    )
    resource = _object(record["resource"], {"requires_close", "item_size_upper"}, "resource")
    instance = _object(record["instance"], {"abstraction", "identity_confidence"}, "instance")
    expected = _object(record["expected"], {"dimension", "lifecycle_status", "upper_bound", "reason_contains"}, "expected result")
    transitions = record["transitions"]
    exits = record["exit_events"]
    invariants = record["invariants"]
    if not isinstance(transitions, list) or not transitions or len(transitions) > 32:
        raise ValueError("case transitions are invalid")
    if not isinstance(exits, list) or not exits or any(not isinstance(item, str) or not item for item in exits):
        raise ValueError("case exit events are invalid")
    if not isinstance(invariants, list) or len(invariants) > 16:
        raise ValueError("case invariants are invalid")
    group = record["group"]
    if isinstance(group, bool) or not isinstance(group, int) or not 1 <= group <= 12:
        raise ValueError("case group is invalid")
    dimension = _string(expected["dimension"], "expected dimension")
    status = _string(expected["lifecycle_status"], "expected lifecycle status")
    if dimension not in _DIMENSIONS or status not in _STATUSES:
        raise ValueError("expected dimension/status is invalid")
    reason = expected["reason_contains"]
    if reason is not None:
        reason = _string(reason, "expected reason")
    upper = expected["upper_bound"]
    if upper is not None and (isinstance(upper, bool) or not isinstance(upper, (int, str))):
        raise ValueError("expected upper bound is invalid")
    abstraction = _string(instance["abstraction"], "instance abstraction")
    confidence = _string(instance["identity_confidence"], "identity confidence")
    if abstraction not in {"recent", "summary"} or confidence not in {"exact", "family", "unknown"}:
        raise ValueError("instance abstraction/confidence is invalid")
    return RegressionCase(
        _string(record["case_id"], "case id"),
        group,
        _string(record["pair"], "pair"),
        _string(record["property"], "property"),
        _boolean(resource["requires_close"], "requires_close"),
        _optional_size(resource["item_size_upper"]),
        abstraction,
        confidence,
        _boolean(record["coverage_complete"], "coverage_complete"),
        tuple(_transition_spec(item) for item in transitions),
        tuple(exits),
        tuple(_invariant_spec(item) for item in invariants),
        ExpectedOutcome(dimension, status, upper, reason),
    )


def load_suite(path: Path) -> RegressionSuite:
    try:
        payload = load_json_regular(path, max_bytes=4 * 1024 * 1024)
        record = _object(payload, {"schema_version", "suite_id", "source_kind", "budget", "cases"}, "regression suite")
        if record["schema_version"] != "1.0" or record["source_kind"] != "manual_fixture":
            raise ValueError("regression suite schema/source is unsupported")
        budget_record = _object(record["budget"], {"max_steps", "max_updates_per_event", "timeout_ms"}, "budget")
        budget = AnalysisBudget(**budget_record)  # type: ignore[arg-type]
        values = record["cases"]
        if not isinstance(values, list) or not 24 <= len(values) <= 256:
            raise ValueError("regression suite must contain 24..256 cases")
        cases = tuple(_case(item) for item in values)
        if len({item.case_id for item in cases}) != len(cases):
            raise ValueError("regression case identifiers must be unique")
        groups = Counter(item.group for item in cases)
        if set(groups) != set(range(1, 13)) or any(count < 2 for count in groups.values()):
            raise ValueError("regression suite must contain twelve semantic pairs")
        return RegressionSuite(_string(record["suite_id"], "suite id"), "manual_fixture", budget, cases, file_sha256(path))
    except AnalyzerError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Resource lifecycle regression suite is invalid.", {"path": str(path)}) from exc


def _event_kind(event_id: str) -> Literal["request", "request_exit", "method", "task_submit", "task_queue", "task_run", "task_exit"]:
    if event_id == "entry":
        return "request"
    if "queue" in event_id:
        return "task_queue"
    if "run" in event_id:
        return "task_run"
    if event_id in {"normal", "error", "rejected"}:
        return "request_exit"
    return "method"


def _build_case(
    current: RegressionCase,
    suite_sha256: str,
    mode: str,
) -> tuple[Program, tuple[InvariantCandidate, ...], tuple[ExecutorContract, ...]]:
    family_id = f"family:{current.case_id}"
    instance_id = f"instance:{current.case_id}"
    source = SourceLocation(
        f"manual/{current.case_id}.json",
        1,
        1,
        suite_sha256,
        "resource-lifecycle-regression-v1",
        "manual_fixture",
    )
    family = ResourceFamily(family_id, source, (current.case_id,), "fixture.Resource", current.requires_close, current.item_size_upper)
    abstraction = current.abstraction
    confidence = current.identity_confidence
    identity_sensitive = any(effect.kind in {"drop", "release"} for transition in current.transitions for effect in transition.effects)
    if mode == "without_identity" and identity_sensitive:
        abstraction, confidence = "summary", "family"
    instance = AbstractInstance(instance_id, family_id, abstraction, confidence)  # type: ignore[arg-type]
    holders = (
        Holder("holder:request", "request_stack", "request", "exact"),
        Holder("holder:field", "field", "instance", "exact"),
        Holder("holder:task", "task", "task", "exact"),
        Holder("holder:container", "container", "global", "exact"),
    )
    scoped = any(effect.holder in {"field", "task", "container"} for transition in current.transitions for effect in transition.effects)
    if mode == "without_scope" and scoped:
        holders = tuple(replace(holder, identity_precision="unknown") for holder in holders)

    selected = list(current.transitions)
    coverage_complete = current.coverage_complete
    if mode == "without_cross_event" and any(item.cross_event for item in selected):
        selected = [item for item in selected if not item.cross_event]
        coverage_complete = False
    if mode == "without_exit_coverage" and any(item.exit_kind == "exceptional" or item.cross_event for item in selected):
        selected = [item for item in selected if item.exit_kind != "exceptional" and not item.cross_event]
        coverage_complete = False
    event_ids = {"entry", *current.exit_events}
    for transition in current.transitions:
        event_ids.update((transition.source, transition.target))
        event_ids.update(effect.target_event for effect in transition.effects if effect.target_event is not None)
    events = tuple(
        Event(f"event:{event_id}", _event_kind(event_id), f"Fixture.{current.case_id}#{event_id}", "true")
        for event_id in sorted(event_ids)
    )
    transitions: list[Transition] = []
    for spec in selected:
        effects = []
        for index, effect_spec in enumerate(spec.effects):
            effects.append(
                Effect(
                    f"effect:{current.case_id}:{spec.transition_id}:{index}",
                    effect_spec.kind,  # type: ignore[arg-type]
                    instance_id,
                    family_id,
                    f"holder:{effect_spec.holder}" if effect_spec.holder else None,
                    f"event:{effect_spec.target_event}" if effect_spec.target_event else None,
                    "true",
                    source,
                    (f"manual:{current.case_id}:{spec.transition_id}:{index}",),
                    contract_id=effect_spec.contract_id,
                )
            )
        transitions.append(
            Transition(
                f"transition:{current.case_id}:{spec.transition_id}",
                f"event:{spec.source}",
                f"event:{spec.target}",
                "true",
                tuple(effects),
                spec.exit_kind,  # type: ignore[arg-type]
                (current.property,),
            )
        )
    program = Program(
        "1.0",
        (family,),
        (instance,),
        holders,
        events,
        tuple(transitions),
        ("event:entry",),
        tuple(f"event:{item}" for item in current.exit_events),
        coverage_complete,
        "resource-lifecycle-contracts-v1",
    )
    candidates = tuple(
        InvariantCandidate(
            f"invariant:{current.case_id}:{index}",
            family_id,
            item.dimension,  # type: ignore[arg-type]
            item.scope,
            item.upper_bound,
            item.initial_holds,
            item.transitions_preserve,
            item.covers_writers,
            item.atomic,
            item.source_kind,  # type: ignore[arg-type]
            (current.property,),
            (f"manual-contract:{current.case_id}:{index}",),
            item.executor_contract_id,
            item.writer_holder_id,
            item.writer_target_event_id,
        )
        for index, item in enumerate(current.invariants)
    )
    if mode == "without_invariants":
        candidates = ()
    executor_contracts = tuple(
        ExecutorContract(
            contract_id=item.executor_contract_id,
            scheduling="queued",
            queue_capacity=item.upper_bound,
            capacity_atomic=item.atomic,
            completion_drops_capture=False,
            rejection_drops_capture=True,
            cancellation="unknown",
            source_kind=item.source_kind,  # type: ignore[arg-type]
            version="executor-contract-v1",
        )
        for item in current.invariants
        if item.scope == "task_queue" and item.executor_contract_id is not None
    )
    return program, candidates, executor_contracts


def _matches(expected: ExpectedOutcome, status: str, upper_bound: int | str | None, reasons: tuple[str, ...]) -> bool:
    if status != expected.lifecycle_status or upper_bound != expected.upper_bound:
        return False
    return expected.reason_contains is None or any(expected.reason_contains in reason for reason in reasons)


def _mode_metrics(rows: list[dict[str, object]], runtime_ms: float) -> dict[str, object]:
    reasons = Counter(
        reason
        for row in rows
        if row["lifecycle_status"] == "unknown"
        for reason in row["reason_codes"]
        if isinstance(reason, str)
    )
    status_counts = Counter(str(row["lifecycle_status"]) for row in rows)
    confusion: dict[str, dict[str, int]] = {}
    for row in rows:
        expected = str(row["expected_status"])
        actual = str(row["lifecycle_status"])
        confusion.setdefault(expected, {})[actual] = confusion.setdefault(expected, {}).get(actual, 0) + 1
    return {
        "input_total": len(rows),
        "extractable": len(rows),
        "build_failures": 0,
        "analyzed": len(rows),
        "unknown": status_counts["unknown"],
        "unknown_rate": status_counts["unknown"] / len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "unknown_reason_distribution": dict(sorted(reasons.items())),
        "expected_matches": sum(bool(row["matches_expected"]) for row in rows),
        "property_status_confusion": confusion,
        "runtime_ms": round(runtime_ms, 3),
    }


def _summary(suite: RegressionSuite, metrics: Mapping[str, Mapping[str, object]], peak_bytes: int) -> str:
    lines = [
        "# Resource Lifecycle v1 固定输入评价",
        "",
        f"- 人工 IR 回归：{len(suite.cases)} 例，12 组成对语义。",
        "- 真实源码端到端：本报告不重复计入；由 CodeQL fixture 验收单独报告。",
        "- 历史资料：29 条仅建 metadata manifest，0 条进入生命周期指标分母。",
        "- legacy / 外部文献基线：`N/A`，本地没有可按同一输入清单运行的等价实现。",
        "- LLM：`off`，调用 0，费用不可适用。",
        f"- 评价过程峰值 Python 分配内存：{peak_bytes} bytes。",
        "",
        "| 模式 | 完成 | unknown | 期望匹配 | 运行时 ms |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for mode in EVALUATION_MODES:
        item = metrics[mode]
        lines.append(f"| `{mode}` | {item['analyzed']} | {item['unknown']} | {item['expected_matches']} | {item['runtime_ms']} |")
    lines.extend(
        [
            "",
            "完整模式的期望来自性质定义，不由当前实现输出反向生成。消融删除信息后只允许保持原状态或保守退化为 `unknown`。",
            "本评价只检查声明的 lifecycle dimension、scope 和 assumptions，不能证明服务可用性、实际资源耗尽或动态漏洞。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, object]], suite_sha256: str) -> None:
    fields = (
        "case_id", "group", "pair", "property", "mode", "source_kind", "dimension", "lifecycle_status",
        "upper_bound", "reason_codes", "expected_status", "expected_upper_bound", "matches_expected", "change_from_full",
        "change_reason", "suite_sha256",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        value = dict(row)
        value["reason_codes"] = json.dumps(value["reason_codes"], ensure_ascii=False, separators=(",", ":"))
        value["suite_sha256"] = suite_sha256
        writer.writerow({key: value.get(key) for key in fields})
    atomic_write_text(path, stream.getvalue())


def evaluate_suite(suite_path: Path, output: Path) -> dict[str, object]:
    suite = load_suite(suite_path)
    output = ensure_output_directory(output)
    rows: list[dict[str, object]] = []
    metrics: dict[str, dict[str, object]] = {}
    full_by_case: dict[str, tuple[str, int | str | None]] = {}
    tracemalloc.start()
    try:
        for mode in EVALUATION_MODES:
            started = time.perf_counter()
            mode_rows: list[dict[str, object]] = []
            for current in suite.cases:
                program, candidates, executor_contracts = _build_case(
                    current, suite.suite_sha256, mode
                )
                analysis = solve(program, budget=suite.budget)
                dimensions = check_invariants(
                    program,
                    analysis,
                    candidates,
                    timeout_ms=suite.budget.timeout_ms,
                    executor_contracts=executor_contracts,
                )
                result = next(item for item in dimensions if item.dimension == current.expected.dimension)
                if mode == "full":
                    full_by_case[current.case_id] = (result.lifecycle_status, result.upper_bound)
                baseline = full_by_case[current.case_id]
                changed = (result.lifecycle_status, result.upper_bound) != baseline
                row: dict[str, object] = {
                    "case_id": current.case_id,
                    "group": current.group,
                    "pair": current.pair,
                    "property": current.property,
                    "mode": mode,
                    "source_kind": suite.source_kind,
                    "dimension": result.dimension,
                    "lifecycle_status": result.lifecycle_status,
                    "upper_bound": result.upper_bound,
                    "reason_codes": list(result.reason_codes),
                    "expected_status": current.expected.lifecycle_status,
                    "expected_upper_bound": current.expected.upper_bound,
                    "matches_expected": _matches(current.expected, result.lifecycle_status, result.upper_bound, result.reason_codes),
                    "change_from_full": changed,
                    "change_reason": ";".join(result.reason_codes) if changed else "unchanged",
                }
                mode_rows.append(row)
                rows.append(row)
            metrics[mode] = _mode_metrics(mode_rows, (time.perf_counter() - started) * 1000)
        _current, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    metrics_artifact = {
        "schema_version": "1.0",
        "suite_sha256": suite.suite_sha256,
        "source_breakdown": {"manual_ir": len(suite.cases), "real_source_codeql": 0, "imported_static_facts": 0},
        "modes": metrics,
        "peak_analyzer_memory_bytes": peak_bytes,
        "cache": {"hits": 0, "misses": 0, "status": "not_used"},
        "llm": {"mode": "off", "calls": 0, "cost": None},
        "historical_label_subset": {"eligible": 0, "confusion_matrix": None, "pending": 29},
    }
    historical_path = Path("evaluation/historical_manifest.json")
    manifest = {
        "schema_version": "1.0",
        "tool_version": TOOL_VERSION,
        "suite_id": suite.suite_id,
        "suite_sha256": suite.suite_sha256,
        "modes": list(EVALUATION_MODES),
        "budget": {"max_steps": suite.budget.max_steps, "max_updates_per_event": suite.budget.max_updates_per_event, "timeout_ms": suite.budget.timeout_ms},
        "input_mode": "manual_ir",
        "legacy_baseline": {"status": "N/A", "reason": "no runnable equivalent implementation for the fixed suite"},
        "historical_manifest_sha256": file_sha256(historical_path) if historical_path.is_file() else None,
        "llm": {"mode": "off", "provider": None, "model": None, "calls": 0, "cost": None},
    }
    atomic_write_json(output / "metrics.json", metrics_artifact)
    atomic_write_json(output / "run-manifest.json", manifest)
    _write_csv(output / "cases.csv", rows, suite.suite_sha256)
    atomic_write_text(output / "summary.md", _summary(suite, metrics, peak_bytes))
    return {"suite_sha256": suite.suite_sha256, "metrics": metrics, "cases": rows, "peak_analyzer_memory_bytes": peak_bytes}


def evaluate_command(values: Mapping[str, object]) -> dict[str, object]:
    suite = values.get("suite")
    output = values.get("out")
    if not isinstance(suite, Path) or not isinstance(output, Path):
        raise AnalyzerError("CONFIG_INVALID_VALUE", "--suite and --out are required for resource-evaluate.")
    return evaluate_suite(suite, output)
