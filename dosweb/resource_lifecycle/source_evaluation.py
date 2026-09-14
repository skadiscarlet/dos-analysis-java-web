from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import csv
from dataclasses import asdict, dataclass, replace
import io
import json
from pathlib import Path
from typing import Final

from dosweb.codeql.database import validate_database
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle.adapters import AnalysisUnit, ExtractedFacts, extracted_to_dict
from dosweb.resource_lifecycle.commands import (
    TOOL_VERSION,
    _analyze_payload,
    _codeql_facts,
    _implementation_sha256,
)
from dosweb.resource_lifecycle.io import (
    atomic_write_json,
    atomic_write_text,
    ensure_output_directory,
    load_json_regular_with_sha256,
)
from dosweb.resource_lifecycle.models import AnalysisBudget, SCHEMA_VERSION, Transition


SOURCE_EVALUATION_MODES: Final = (
    "full",
    "disable_cross_event_propagation",
)
_DIMENSIONS: Final = frozenset(
    {
        "held_instances",
        "item_size_bytes",
        "close_obligation",
        "accepted_task_population",
    }
)
_SCOPES: Final = frozenset(
    {"all_exits", "per_instance", "task", "resource_family", "executor"}
)
_CUTS: Final = frozenset(
    {
        "all_modeled_exits",
        "after_task_termination:normal",
        "after_task_termination:exceptional",
        "all_tasks_terminated_after_request",
        "arbitrary_finite_repetitions",
    }
)
_STATUSES: Final = frozenset(
    {"bounded", "unknown", "obligation_gap", "not_applicable"}
)
_MAX_MANIFEST_BYTES: Final = 2 * 1024 * 1024


@dataclass(frozen=True)
class SourceExpectedOutcome:
    mode: str
    dimension: str
    scope: str
    cut: str
    lifecycle_status: str
    upper_bound: int | str | None
    reason_contains: str | None


@dataclass(frozen=True)
class SourceCase:
    case_id: str
    group: str
    pair: str
    property: str
    entry_callable: str
    expectations: tuple[SourceExpectedOutcome, ...]


@dataclass(frozen=True)
class SourceSuite:
    suite_id: str
    source_root: Path
    budget: AnalysisBudget
    cases: tuple[SourceCase, ...]
    suite_sha256: str


def _object(value: object, expected: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{label} fields are invalid")
    return value


def _string(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 1024
    ):
        raise ValueError(f"{label} must be a bounded non-empty string")
    return value


def _safe_source_root(manifest_path: Path, value: object) -> Path:
    relative_text = _string(value, "source_root")
    if "\\" in relative_text:
        raise ValueError("source_root must be a safe relative path")
    relative = Path(relative_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("source_root must be a safe relative path")
    parent = manifest_path.parent.resolve(strict=True)
    resolved = (parent / relative).resolve(strict=True)
    if (resolved != parent and parent not in resolved.parents) or not resolved.is_dir():
        raise ValueError("source_root is outside the source suite")
    if (parent / relative).is_symlink():
        raise ValueError("source_root must not be a symlink")
    return resolved


def _expected(value: object) -> SourceExpectedOutcome:
    record = _object(
        value,
        {
            "mode",
            "dimension",
            "scope",
            "cut",
            "lifecycle_status",
            "upper_bound",
            "reason_contains",
        },
        "source expectation",
    )
    mode = _string(record["mode"], "expectation mode")
    dimension = _string(record["dimension"], "expectation dimension")
    scope = _string(record["scope"], "expectation scope")
    cut = _string(record["cut"], "expectation cut")
    lifecycle_status = _string(
        record["lifecycle_status"], "expectation lifecycle_status"
    )
    upper_bound = record["upper_bound"]
    reason_contains = record["reason_contains"]
    if mode not in SOURCE_EVALUATION_MODES:
        raise ValueError("source expectation mode is invalid")
    if dimension not in _DIMENSIONS or scope not in _SCOPES or cut not in _CUTS:
        raise ValueError("source expectation dimension/scope/cut is invalid")
    if lifecycle_status not in _STATUSES:
        raise ValueError("source expectation lifecycle_status is invalid")
    if upper_bound is not None and (
        isinstance(upper_bound, bool)
        or not isinstance(upper_bound, (int, str))
        or isinstance(upper_bound, int)
        and upper_bound < 0
        or upper_bound == ""
    ):
        raise ValueError("source expectation upper_bound is invalid")
    if reason_contains is not None:
        reason_contains = _string(reason_contains, "expectation reason_contains")
    valid_shape = (
        dimension == "accepted_task_population"
        and scope == "executor"
        and cut == "arbitrary_finite_repetitions"
        or dimension in {"held_instances", "close_obligation"}
        and scope == "resource_family"
        and cut
        in {
            "all_tasks_terminated_after_request",
            "after_task_termination:normal",
            "after_task_termination:exceptional",
        }
        or scope in {"all_exits", "per_instance"}
        and cut == "all_modeled_exits"
        or scope == "task"
        and cut.startswith("after_task_termination:")
    )
    if not valid_shape:
        raise ValueError("source expectation observation shape is unsupported")
    return SourceExpectedOutcome(
        mode,
        dimension,
        scope,
        cut,
        lifecycle_status,
        upper_bound,
        reason_contains,
    )


def _case(value: object) -> SourceCase:
    record = _object(
        value,
        {
            "case_id",
            "group",
            "pair",
            "property",
            "entry_callable",
            "expectations",
        },
        "source case",
    )
    expectations_value = record["expectations"]
    if not isinstance(expectations_value, list) or len(expectations_value) != 2:
        raise ValueError("source case must declare exactly two mode expectations")
    expectations = tuple(_expected(item) for item in expectations_value)
    if {item.mode for item in expectations} != set(SOURCE_EVALUATION_MODES):
        raise ValueError("source case expectations must cover both evaluation modes")
    group = _string(record["group"], "source case group")
    if group not in {f"S{index}" for index in range(1, 7)}:
        raise ValueError("source case group is invalid")
    entry_callable = _string(record["entry_callable"], "source entry callable")
    if not entry_callable.startswith("java-callable-v1:"):
        raise ValueError("source entry callable is not canonical")
    return SourceCase(
        _string(record["case_id"], "source case id"),
        group,
        _string(record["pair"], "source case pair"),
        _string(record["property"], "source case property"),
        entry_callable,
        expectations,
    )


def load_source_suite(path: Path, *, source_root: Path | None = None) -> SourceSuite:
    try:
        payload, suite_sha256 = load_json_regular_with_sha256(
            path,
            max_bytes=_MAX_MANIFEST_BYTES,
        )
        record = _object(
            payload,
            {"schema_version", "suite_id", "source_root", "budget", "cases"},
            "source suite",
        )
        if record["schema_version"] != SCHEMA_VERSION:
            raise ValueError("source suite schema is unsupported")
        declared_source_root = _safe_source_root(path, record["source_root"])
        if source_root is not None:
            supplied_source_root = source_root.resolve(strict=True)
            if (
                not supplied_source_root.is_dir()
                or source_root.is_symlink()
                or supplied_source_root != declared_source_root
            ):
                raise ValueError("supplied source root does not match the source suite")
        budget_record = _object(
            record["budget"],
            {"max_steps", "max_updates_per_event", "timeout_ms"},
            "source suite budget",
        )
        if any(
            type(budget_record[name]) is not int or budget_record[name] <= 0
            for name in ("max_steps", "max_updates_per_event", "timeout_ms")
        ):
            raise ValueError("source suite budget values must be positive integers")
        budget = AnalysisBudget(**budget_record)  # type: ignore[arg-type]
        cases_value = record["cases"]
        if not isinstance(cases_value, list) or len(cases_value) != 12:
            raise ValueError("source suite must contain exactly twelve cases")
        cases = tuple(_case(item) for item in cases_value)
        if len({item.case_id for item in cases}) != len(cases):
            raise ValueError("source case identifiers must be unique")
        if len({item.entry_callable for item in cases}) != len(cases):
            raise ValueError("source entry callables must be unique")
        groups = Counter(item.group for item in cases)
        if groups != Counter({f"S{index}": 2 for index in range(1, 7)}):
            raise ValueError("source suite must contain six two-case groups")
        return SourceSuite(
            _string(record["suite_id"], "source suite id"),
            declared_source_root,
            budget,
            cases,
            suite_sha256,
        )
    except AnalyzerError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise AnalyzerError(
            "ARTIFACT_INPUT_INVALID",
            "Resource lifecycle source suite is invalid.",
            {"path": str(path)},
        ) from exc


def _disable_cross_event_propagation(
    unit: AnalysisUnit,
) -> tuple[AnalysisUnit, dict[str, object]]:
    """Delete relation-derived execution edges while preserving all raw input facts."""
    program = unit.program
    events = {event.event_id: event for event in program.events}
    instances = {item.instance_id: item.family_id for item in program.instances}
    task_event_ids = {
        event_id
        for binding in program.task_bindings
        for event_id in (
            binding.submit_event_id,
            binding.queued_event_id,
            binding.run_event_id,
            binding.normal_exit_event_id,
            binding.exceptional_exit_event_id,
            binding.rejected_event_id,
            binding.cancelled_event_id,
        )
    }
    cross_callable_event_ids = {
        event_id
        for event_id, event in events.items()
        if event.callable != unit.unit_id
        and not event.callable.startswith(unit.unit_id + "#")
    }

    def is_cross_event_transition(transition: Transition) -> bool:
        return bool(
            transition.source_event_id in task_event_ids
            or transition.target_event_id in task_event_ids
            or transition.source_event_id in cross_callable_event_ids
            or transition.target_event_id in cross_callable_event_ids
            or transition.guard in {"exact call binding", "verified CFG return"}
            or any(
                item.startswith("task_binding:")
                for item in transition.assumptions
            )
            or transition.population_effects
        )

    removed_transitions = tuple(
        transition
        for transition in program.transitions
        if is_cross_event_transition(transition)
    )
    kept_transitions = tuple(
        transition
        for transition in program.transitions
        if not is_cross_event_transition(transition)
    )
    affected_family_ids = {
        instances[binding.instance_id] for binding in program.call_bindings
    } | {
        instances[binding.instance_id] for binding in program.task_bindings
    } | {
        effect.family_id
        for transition in removed_transitions
        for effect in transition.effects
        if effect.family_id is not None
    }
    added_gaps = {
        (
            dimension,
            family_id,
            "*",
            "cross_event_propagation_disabled",
            f"ablation:disable-cross-event:{unit.unit_id}:{family_id}:{dimension}",
        )
        for family_id in affected_family_ids
        for dimension in (
            "held_instances",
            "item_size_bytes",
            "close_obligation",
        )
        if dimension != "close_obligation"
        or next(item for item in program.families if item.family_id == family_id).requires_close
    }
    ablated_program = replace(
        program,
        transitions=kept_transitions,
        coverage_complete=program.coverage_complete and not added_gaps,
        coverage_gaps=tuple(sorted(set(program.coverage_gaps).union(added_gaps))),
        call_bindings=(),
        task_bindings=(),
        task_exits=(),
    )
    metadata = {
        "unit_id": unit.unit_id,
        "removed_call_bindings": len(program.call_bindings),
        "removed_call_binding_ids": sorted(
            item.binding_id for item in program.call_bindings
        ),
        "removed_task_bindings": len(program.task_bindings),
        "removed_task_binding_ids": sorted(
            item.binding_id for item in program.task_bindings
        ),
        "removed_task_ids": sorted(item.task_id for item in program.task_bindings),
        "removed_task_exits": len(program.task_exits),
        "removed_task_exit_ids": sorted(item.exit_id for item in program.task_exits),
        "removed_transitions": len(removed_transitions),
        "removed_transition_ids": sorted(
            item.transition_id for item in removed_transitions
        ),
        "removed_population_effects": sum(
            len(transition.population_effects) for transition in removed_transitions
        ),
        "added_coverage_gaps": len(added_gaps),
        "affected_resource_family_ids": sorted(affected_family_ids),
    }
    return replace(unit, program=ablated_program), metadata


def _fallback_reasons(
    unit: AnalysisUnit,
    result: Mapping[str, object],
    family_id: str,
) -> tuple[str, ...]:
    reasons = {
        gap[3]
        for gap in unit.program.coverage_gaps
        if gap[1] == family_id
    }
    unknown_reasons = result.get("unknown_reasons")
    if isinstance(unknown_reasons, (list, tuple)):
        reasons.update(item for item in unknown_reasons if isinstance(item, str))
    reasons.add("expected_property_unavailable")
    return tuple(sorted(reasons))


def _dimension_observation(
    expected: SourceExpectedOutcome,
    result: Mapping[str, object],
    unit: AnalysisUnit,
    family_id: str,
) -> dict[str, object]:
    dimensions = result.get("dimensions")
    if not isinstance(dimensions, list):
        dimensions = []
    candidates = [
        item
        for item in dimensions
        if isinstance(item, Mapping)
        and item.get("dimension") == expected.dimension
        and item.get("resource_family_id") == family_id
        and (
            expected.scope in {"all_exits", "per_instance"}
            and item.get("scope") == expected.scope
            or expected.scope == "task"
            and isinstance(item.get("scope"), str)
            and str(item["scope"]).startswith("after_task_termination:")
            and str(item["scope"]).endswith(":" + expected.cut.rsplit(":", 1)[1])
        )
    ]
    if len(candidates) != 1:
        reasons = set(_fallback_reasons(unit, result, family_id))
        reasons.add(
            "expected_property_ambiguous" if candidates else "expected_property_unavailable"
        )
        return {
            "observed_scope": None,
            "lifecycle_status": "unknown",
            "upper_bound": None,
            "reason_codes": sorted(reasons),
        }
    selected = candidates[0]
    reason_codes = selected.get("reason_codes")
    return {
        "observed_scope": selected.get("scope"),
        "lifecycle_status": selected.get("lifecycle_status"),
        "upper_bound": selected.get("upper_bound"),
        "reason_codes": (
            list(reason_codes)
            if isinstance(reason_codes, (list, tuple))
            else []
        ),
    }


def _population_observation(
    expected: SourceExpectedOutcome,
    result: Mapping[str, object],
    unit: AnalysisUnit,
    family_id: str,
) -> dict[str, object]:
    properties = result.get("population_properties")
    if not isinstance(properties, list):
        properties = []
    candidates = [
        item
        for item in properties
        if isinstance(item, Mapping)
        and item.get("dimension") == "accepted_task_population"
        and isinstance(item.get("scope"), str)
        and str(item["scope"]).startswith("executor:")
        and item.get("repeat_assumption")
        == {
            "arbitrary_finite_repetitions":
                "arbitrary_finite_repetitions_of_external_accept"
        }.get(expected.cut)
    ]
    if len(candidates) != 1:
        reasons = set(_fallback_reasons(unit, result, family_id))
        if len(candidates) > 1:
            reasons.add("expected_property_ambiguous")
        return {
            "observed_scope": None,
            "lifecycle_status": "unknown",
            "upper_bound": None,
            "reason_codes": sorted(reasons),
        }
    selected = candidates[0]
    lifecycle_status = selected.get("lifecycle_status")
    reasons = selected.get("unknown_reasons")
    return {
        "observed_scope": selected.get("scope"),
        "lifecycle_status": lifecycle_status,
        "upper_bound": (
            selected.get("total_upper_bound")
            if lifecycle_status == "bounded"
            else None
        ),
        "reason_codes": (
            list(reasons) if isinstance(reasons, (list, tuple)) else []
        ),
    }


def _state_observation(
    expected: SourceExpectedOutcome,
    result: Mapping[str, object],
    unit: AnalysisUnit,
    family_id: str,
) -> dict[str, object]:
    ignored_cut_reasons = (
        {"async_consumer_contract_unmodeled"}
        if expected.cut.startswith("after_task_termination:")
        else set()
    )
    incomplete_reasons = (
        {
            item
            for item in result.get("unknown_reasons", ())
            if isinstance(item, str)
        }
        if result.get("terminated") is not True
        else set()
    )
    if result.get("terminated") is not True:
        incomplete_reasons.add("source_case_analysis_incomplete")
    coverage_reasons = {
        gap[3]
        for gap in unit.program.coverage_gaps
        if gap[0] == expected.dimension
        and gap[1] == family_id
        and gap[3] not in ignored_cut_reasons
    }
    blocking_reasons = sorted(incomplete_reasons | coverage_reasons)
    if blocking_reasons:
        return {
            "observed_scope": expected.cut,
            "lifecycle_status": "unknown",
            "upper_bound": None,
            "reason_codes": blocking_reasons,
        }
    properties = result.get("property_states")
    property_name = expected.cut.split(":", 1)[0]
    states = properties.get(property_name) if isinstance(properties, Mapping) else None
    if (
        isinstance(states, Mapping)
        and expected.cut.startswith("after_task_termination:")
    ):
        kind = expected.cut.rsplit(":", 1)[1]
        selected_event_ids = {
            task_exit.event_id
            for task_exit in unit.program.task_exits
            if task_exit.kind == kind
        }
        states = {
            event_id: state
            for event_id, state in states.items()
            if event_id in selected_event_ids
        }
    if not isinstance(states, Mapping) or not states:
        return {
            "observed_scope": None,
            "lifecycle_status": "unknown",
            "upper_bound": None,
            "reason_codes": list(_fallback_reasons(unit, result, family_id)),
        }
    upper_bounds: list[int] = []
    state_reasons: set[str] = set()
    for state in states.values():
        if not isinstance(state, Mapping):
            return {
                "observed_scope": expected.cut,
                "lifecycle_status": "unknown",
                "upper_bound": None,
                "reason_codes": ["property_state_invalid"],
            }
        unknown_reasons = state.get("unknown_reasons")
        if not isinstance(unknown_reasons, list) or any(
            not isinstance(item, str) for item in unknown_reasons
        ):
            return {
                "observed_scope": expected.cut,
                "lifecycle_status": "unknown",
                "upper_bound": None,
                "reason_codes": ["property_state_unknown_reasons_invalid"],
            }
        state_reasons.update(unknown_reasons)
        count_field = (
            "held_counts"
            if expected.dimension == "held_instances"
            else "obligation_counts"
        )
        held_counts = state.get(count_field)
        if not isinstance(held_counts, list):
            held_counts = []
        intervals = [
            item[1]
            for item in held_counts
            if isinstance(item, list)
            and len(item) == 2
            and item[0] == family_id
            and isinstance(item[1], Mapping)
        ]
        upper = 0 if not intervals else intervals[0].get("upper")
        if len(intervals) > 1 or isinstance(upper, bool) or not isinstance(upper, int):
            return {
                "observed_scope": expected.cut,
                "lifecycle_status": "unknown",
                "upper_bound": None,
                "reason_codes": ["property_state_count_unknown"],
            }
        upper_bounds.append(upper)
    if state_reasons:
        return {
            "observed_scope": expected.cut,
            "lifecycle_status": "unknown",
            "upper_bound": None,
            "reason_codes": sorted(state_reasons),
        }
    return {
        "observed_scope": expected.cut,
        "lifecycle_status": "bounded",
        "upper_bound": max(upper_bounds, default=0),
        "reason_codes": [],
        "property_event_ids": sorted(states),
    }


def _observation(
    expected: SourceExpectedOutcome,
    result: Mapping[str, object],
    unit: AnalysisUnit,
) -> dict[str, object]:
    if len(unit.program.families) != 1:
        return {
            "observed_scope": None,
            "lifecycle_status": "unknown",
            "upper_bound": None,
            "reason_codes": ["source_case_resource_family_ambiguous"],
        }
    family_id = unit.program.families[0].family_id
    if expected.scope == "executor":
        observed = _population_observation(expected, result, unit, family_id)
    elif expected.scope == "resource_family":
        observed = _state_observation(expected, result, unit, family_id)
    else:
        observed = _dimension_observation(expected, result, unit, family_id)
    return {"resource_family_id": family_id, **observed}


def _matches(expected: SourceExpectedOutcome, observed: Mapping[str, object]) -> bool:
    if (
        observed.get("lifecycle_status") != expected.lifecycle_status
        or observed.get("upper_bound") != expected.upper_bound
    ):
        return False
    reasons = observed.get("reason_codes")
    return expected.reason_contains is None or (
        isinstance(reasons, list)
        and any(
            expected.reason_contains in item
            for item in reasons
            if isinstance(item, str)
        )
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = (
        "case_id",
        "group",
        "pair",
        "property",
        "entry_callable",
        "mode",
        "dimension",
        "scope",
        "cut",
        "observed_scope",
        "lifecycle_status",
        "upper_bound",
        "reason_codes",
        "expected_status",
        "expected_upper_bound",
        "reason_contains",
        "matches_expected",
        "change_from_full",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        value = dict(row)
        value["reason_codes"] = json.dumps(
            value["reason_codes"], ensure_ascii=False, separators=(",", ":")
        )
        writer.writerow({field: value.get(field) for field in fields})
    atomic_write_text(path, stream.getvalue())


def _summary(
    suite: SourceSuite,
    metrics: Mapping[str, object],
    source_snapshot_sha256: object,
) -> str:
    modes = metrics["modes"]
    assert isinstance(modes, Mapping)
    lines = [
        "# Resource Lifecycle v1.1 真实源码成对评价",
        "",
        f"- 源码案例：{len(suite.cases)} 个变体，6 组成对输入。",
        "- 执行链：Java source → CodeQL 两查询 → adapter → 主 solver → report。",
        "- 对照模式仅删除跨事件 relation 和由其驱动的 transition，再从同一 raw facts 重算；不硬改标签。",
        f"- source snapshot：`{source_snapshot_sha256}`。",
        "- LLM：`off`；未执行网络、服务、PoC 或动态 DoS。",
        "",
        "| 模式 | 例数 | 期望匹配 | unknown |",
        "| --- | ---: | ---: | ---: |",
    ]
    for mode in SOURCE_EVALUATION_MODES:
        item = modes[mode]
        assert isinstance(item, Mapping)
        lines.append(
            f"| `{mode}` | {item['cases']} | {item['expected_matches']} | {item['unknown']} |"
        )
    lines.extend(
        [
            "",
            f"固定输入确定性增益：{metrics['determinacy_gains']} 例。",
            "这里的 `bounded`/`unknown` 是受声明 cut 与 modeled assumptions 限定的静态 lifecycle 性质，不是动态 confirmed 结论。",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_source_suite(
    suite_path: Path,
    source_root: Path,
    database_path: Path,
    output: Path,
    *,
    codeql_binary: str = "codeql",
) -> dict[str, object]:
    suite = load_source_suite(suite_path, source_root=source_root)
    output = ensure_output_directory(output)
    try:
        database = validate_database(database_path)
        if database.source_root.resolve(strict=True) != suite.source_root:
            raise ValueError("CodeQL database source root does not match source suite")
        entries = tuple(item.entry_callable for item in suite.cases)
        extracted = _codeql_facts(
            {
                "schema_version": SCHEMA_VERSION,
                "mode": "codeql_database",
                "database": str(database.path),
                "entry_methods": list(entries),
                "budget": asdict(suite.budget),
            },
            {"codeql_binary": codeql_binary},
            output,
        )
        if extracted.coverage.get("end_to_end_mode") != "real_source_codeql":
            raise ValueError("source evaluation did not use real CodeQL facts")
        if (
            extracted.coverage.get("database_fingerprint")
            != database.fingerprint
        ):
            raise ValueError(
                "source evaluation database provenance changed before extraction"
            )
        if extracted.coverage.get("matched_entry_methods") != sorted(entries):
            raise ValueError("not every source case entry was extracted")
    except AnalyzerError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise AnalyzerError(
            "ARTIFACT_INPUT_INVALID",
            "Resource lifecycle source evaluation input could not be adapted.",
        ) from exc

    try:
        full_results = _analyze_payload(extracted)
        ablated_pairs = tuple(
            _disable_cross_event_propagation(unit) for unit in extracted.units
        )
        ablated = replace(
            extracted,
            units=tuple(item[0] for item in ablated_pairs),
        )
        ablated_results = _analyze_payload(ablated)
    except AnalyzerError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise AnalyzerError(
            "INTERNAL_RESOURCE_EVALUATION_FAILED",
            "Resource lifecycle source evaluation could not be solved.",
        ) from exc
    results_by_mode = {
        "full": full_results,
        "disable_cross_event_propagation": ablated_results,
    }
    units_by_mode = {
        "full": {unit.unit_id: unit for unit in extracted.units},
        "disable_cross_event_propagation": {
            unit.unit_id: unit for unit in ablated.units
        },
    }
    unit_results_by_mode: dict[str, dict[str, Mapping[str, object]]] = {}
    for mode, result in results_by_mode.items():
        result_units = result.get("units")
        if not isinstance(result_units, list):
            raise AnalyzerError(
                "INTERNAL_RESOURCE_EVALUATION_FAILED",
                "Resource lifecycle source result units are invalid.",
            )
        unit_results_by_mode[mode] = {
            str(item["unit_id"]): item
            for item in result_units
            if isinstance(item, Mapping) and isinstance(item.get("unit_id"), str)
        }

    rows: list[dict[str, object]] = []
    full_by_case: dict[str, tuple[object, object]] = {}
    for current in suite.cases:
        for expected in sorted(
            current.expectations,
            key=lambda item: SOURCE_EVALUATION_MODES.index(item.mode),
        ):
            unit = units_by_mode[expected.mode].get(current.entry_callable)
            result = unit_results_by_mode[expected.mode].get(current.entry_callable)
            if unit is None or result is None:
                raise AnalyzerError(
                    "ARTIFACT_INPUT_INVALID",
                    "A source case entry is missing from the adapted analysis units.",
                    {"case_id": current.case_id},
                )
            observed = _observation(expected, result, unit)
            identity = (
                observed["lifecycle_status"],
                observed["upper_bound"],
            )
            if expected.mode == "full":
                full_by_case[current.case_id] = identity
            row = {
                "case_id": current.case_id,
                "group": current.group,
                "pair": current.pair,
                "property": current.property,
                "entry_callable": current.entry_callable,
                "mode": expected.mode,
                "dimension": expected.dimension,
                "scope": expected.scope,
                "cut": expected.cut,
                **observed,
                "expected_status": expected.lifecycle_status,
                "expected_upper_bound": expected.upper_bound,
                "reason_contains": expected.reason_contains,
                "matches_expected": _matches(expected, observed),
                "change_from_full": (
                    False
                    if expected.mode == "full"
                    else identity != full_by_case[current.case_id]
                ),
            }
            rows.append(row)

    mode_metrics = {
        mode: {
            "cases": len(selected),
            "expected_matches": sum(
                bool(item["matches_expected"]) for item in selected
            ),
            "unknown": sum(
                item["lifecycle_status"] == "unknown" for item in selected
            ),
        }
        for mode in SOURCE_EVALUATION_MODES
        for selected in ([item for item in rows if item["mode"] == mode],)
    }
    rows_by_case = {
        case.case_id: {
            str(row["mode"]): row
            for row in rows
            if row["case_id"] == case.case_id
        }
        for case in suite.cases
    }
    determinacy_gain_cases = sorted(
        case_id
        for case_id, values in rows_by_case.items()
        if values["full"]["lifecycle_status"] != "unknown"
        and values["disable_cross_event_propagation"]["lifecycle_status"]
        == "unknown"
    )
    metrics = {
        "schema_version": SCHEMA_VERSION,
        "source_cases": len(suite.cases),
        "source_pairs": 6,
        "modes": mode_metrics,
        "determinacy_gains": len(determinacy_gain_cases),
        "determinacy_gain_cases": determinacy_gain_cases,
        "raw_fact_count": len(extracted.facts),
        "raw_fact_snapshot_sha256": extracted.snapshot_sha256,
        "llm": {"mode": "off", "calls": 0, "cost": None},
    }
    ablation = {
        "mode": "disable_cross_event_propagation",
        "input_fact_snapshot_sha256": extracted.snapshot_sha256,
        "output_fact_snapshot_sha256": extracted.snapshot_sha256,
        "facts_added": 0,
        "facts_removed": 0,
        "units": [item[1] for item in ablated_pairs],
    }
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": suite.suite_id,
        "suite_sha256": suite.suite_sha256,
        "modes": list(SOURCE_EVALUATION_MODES),
        "cases": rows,
        "metrics": metrics,
        "ablation": ablation,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "implementation_sha256": _implementation_sha256(),
        "suite_id": suite.suite_id,
        "suite_sha256": suite.suite_sha256,
        "source_root": str(suite.source_root),
        "source_snapshot_sha256": extracted.coverage.get(
            "source_snapshot_sha256"
        ),
        "database": str(database.path),
        "database_fingerprint": database.fingerprint,
        "query_provenance": extracted.coverage.get("query_provenance"),
        "query_suite_sha256": extracted.coverage.get("query_suite_sha256"),
        "provenance_sha256": extracted.coverage.get("provenance_sha256"),
        "raw_fact_snapshot_sha256": extracted.snapshot_sha256,
        "entry_methods": list(entries),
        "budget": asdict(suite.budget),
        "modes": list(SOURCE_EVALUATION_MODES),
        "result_sha256": {
            mode: result.get("result_sha256")
            for mode, result in results_by_mode.items()
        },
        "same_entries_candidates_and_raw_facts": True,
        "llm": {"mode": "off", "provider": None, "model": None, "calls": 0},
    }
    atomic_write_json(output / "facts.json", extracted_to_dict(extracted))
    atomic_write_json(output / "coverage.json", dict(extracted.coverage))
    atomic_write_json(output / "full-results.json", full_results)
    atomic_write_json(
        output / "disable-cross-event-results.json", ablated_results
    )
    atomic_write_json(output / "source-evaluation.json", artifact)
    atomic_write_json(output / "metrics.json", metrics)
    atomic_write_json(output / "run-manifest.json", manifest)
    _write_csv(output / "source-cases.csv", rows)
    atomic_write_text(
        output / "summary.md",
        _summary(
            suite,
            metrics,
            extracted.coverage.get("source_snapshot_sha256"),
        ),
    )
    return artifact


def evaluate_source_command(values: Mapping[str, object]) -> dict[str, object]:
    suite = values.get("suite")
    source_root = values.get("source_root")
    database = values.get("database")
    output = values.get("out")
    if not all(isinstance(item, Path) for item in (suite, source_root, database, output)):
        raise AnalyzerError(
            "CONFIG_INVALID_VALUE",
            "--suite, --source-root, --database, and --out are required for resource-source-evaluate.",
        )
    unsupported_overrides = (
        "allow_remote_llm",
        "public_source_url",
        "source_commit_sha",
        "source_checkout",
        "analysis_source_root",
        "model",
        "base_url",
        "timeout_seconds",
        "max_retries",
        "temperature",
        "cache_dir",
        "resume",
        "allow_partial_codeql",
        "modeled_default",
        "llm",
        "config",
        "facts",
        "run",
        "manifest",
        "output",
    )
    if any(values.get(name) is not None for name in unsupported_overrides):
        raise AnalyzerError(
            "CONFIG_INVALID_VALUE",
            "Source evaluation accepts only a local source suite and CodeQL database; provider, LLM, and imported-facts overrides are unsupported.",
        )
    codeql_binary = values.get("codeql_binary") or "codeql"
    if not isinstance(codeql_binary, str) or not codeql_binary:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "--codeql-binary is invalid.")
    return evaluate_source_suite(
        suite,  # type: ignore[arg-type]
        source_root,  # type: ignore[arg-type]
        database,  # type: ignore[arg-type]
        output,  # type: ignore[arg-type]
        codeql_binary=codeql_binary,
    )


__all__ = [
    "SOURCE_EVALUATION_MODES",
    "SourceCase",
    "SourceExpectedOutcome",
    "SourceSuite",
    "evaluate_source_command",
    "evaluate_source_suite",
    "load_source_suite",
]
