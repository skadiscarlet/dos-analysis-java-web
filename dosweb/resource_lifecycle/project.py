"""Explicit local-project intake; selection never supplies solver conclusions."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, replace
import hashlib
from pathlib import Path
import re
import time

from dosweb.artifacts.identifiers import canonical_json, stable_identifier
from dosweb.artifacts.jsonl import read_jsonl_bytes_strict
from dosweb.entries.models import EntryFact
from dosweb.errors import AnalyzerError
from dosweb.growth.slices import GrowthCandidate
from dosweb.resource_lifecycle.adapters import AnalysisUnit, ExtractedFacts
from dosweb.resource_lifecycle.commands import (
    _codeql_facts, _java_source_snapshot, _run_directory_lock,
    validate_database,
)
from dosweb.resource_lifecycle.io import atomic_write_json, ensure_output_directory, load_json_regular, load_text_regular
from dosweb.resource_lifecycle.models import AnalysisBudget, SCHEMA_VERSION

from dosweb.resource_lifecycle.sharded_run import analyze_sharded
from dosweb.resource_lifecycle.shards import ShardBudget

VERSION = "resource-project-v1.2"
_HASH = re.compile(r"[0-9a-f]{64}")
_FIELDS = {"version", "project_id", "source_root", "tree_hash", "database", "selection",
           "dependency_scope", "budgets", "output"}
_SELECTION_FIELDS = {"input_id", "kind", "entry_callable", "resource_family_id", "allocation", "source_sha256", "candidate_file", "record_id"}
_GROWTH_FIELDS = {"growth_id", "site", "kind", "operation", "resource_point", "demand_inputs",
                  "escape_scope", "candidate_evidence", "coverage_status", "coverage_notes"}
_ENTRY_FIELDS = {
    "entry_id", "framework", "protocol", "handler", "registration",
    "registration_pattern_id", "route_or_event", "auth_context",
    "attacker_inputs", "materialization_phase",
}
_BUDGET_DEFAULTS = {"batch_timeout_ms": 300_000, "max_unit_result_bytes": 16 * 1024 * 1024,
                    "max_output_bytes": 256 * 1024 * 1024, "max_index_bytes": 256 * 1024,
                    "max_ledger_bytes": 16 * 1024 * 1024, "max_decoded_bytes": 256 * 1024 * 1024}


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > 2048:
        raise ValueError(f"invalid {label}")
    return value


def _validate_manifest(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != _FIELDS or payload["version"] != VERSION:
        raise ValueError("project manifest fields or version are invalid")
    _text(payload["project_id"], "project_id")
    if not isinstance(payload["tree_hash"], str) or not _HASH.fullmatch(payload["tree_hash"]):
        raise ValueError("tree_hash must identify the actual Java source snapshot")
    for key in ("source_root", "database", "output"):
        if payload[key] is not None:
            _text(payload[key], key)
    selection = payload["selection"]
    if not isinstance(selection, list) or not selection or len(selection) > 4096:
        raise ValueError("selection must contain 1..4096 inputs")
    seen: set[str] = set()
    for item in selection:
        if not isinstance(item, dict) or not {"input_id", "kind"} <= set(item) <= _SELECTION_FIELDS:
            raise ValueError("selection fields are invalid; judgment fields are not inputs")
        input_id = _text(item["input_id"], "input_id")
        if input_id in seen:
            raise ValueError("duplicate input_id")
        seen.add(input_id)
        if "candidate_file" in item or "record_id" in item:
            if item["kind"] != "candidate" or not {"candidate_file", "record_id"} <= set(item):
                raise ValueError("candidate import requires candidate_file and record_id")
            _text(item["candidate_file"], "candidate_file")
            _text(item["record_id"], "record_id")
        elif "entry_callable" not in item:
            raise ValueError("selection needs an exact callable")
        if "entry_callable" in item:
            _text(item["entry_callable"], "entry_callable")
        if item["kind"] not in {"method", "candidate"}:
            raise ValueError("selection kind is invalid")
        if "resource_family_id" in item:
            _text(item["resource_family_id"], "resource_family_id")
        if "source_sha256" in item and (not isinstance(item["source_sha256"], str) or not _HASH.fullmatch(item["source_sha256"])):
            raise ValueError("source_sha256 is invalid")
        if "allocation" in item:
            allocation = item["allocation"]
            if not isinstance(allocation, dict) or not allocation or not set(allocation) <= {"program_point", "instance_key", "path", "start_line", "start_column"}:
                raise ValueError("allocation fields are invalid")
            if not {"program_point", "instance_key"}.intersection(allocation):
                raise ValueError("allocation requires an exact program point or instance key")
            for key, value in allocation.items():
                if key in {"start_line", "start_column"}:
                    if type(value) is not int or value < 1:
                        raise ValueError("allocation location is invalid")
                else:
                    _text(value, key)
            if "path" in allocation:
                path = Path(allocation["path"])
                if path.is_absolute() or ".." in path.parts or "\\" in allocation["path"]:
                    raise ValueError("allocation path must be source relative")
        if item["kind"] == "method" and ({"resource_family_id", "allocation"} & set(item)):
            raise ValueError("method selection must retain every resource")
    dependency = payload["dependency_scope"]
    if not isinstance(dependency, dict) or set(dependency) != {"sources", "dependencies", "unknown_dependencies"}:
        raise ValueError("dependency_scope fields are invalid")
    for values in dependency.values():
        if not isinstance(values, list) or len(values) > 4096:
            raise ValueError("dependency_scope collection is invalid")
        for value in values:
            _text(value, "dependency_scope")
    budgets = payload["budgets"]
    if not isinstance(budgets, dict) or not set(budgets) <= {"unit", *_BUDGET_DEFAULTS}:
        raise ValueError("project budget fields are invalid")
    unit = budgets.get("unit", {})
    if not isinstance(unit, dict) or not set(unit) <= set(asdict(AnalysisBudget())):
        raise ValueError("unit budget fields are invalid")
    for value in [*unit.values(), *(value for key, value in budgets.items() if key != "unit")]:
        if type(value) is not int or value <= 0:
            raise ValueError("budgets must be positive integers")
    if budgets.get("max_unit_result_bytes", _BUDGET_DEFAULTS["max_unit_result_bytes"]) > 16 * 1024 * 1024:
        raise ValueError("unit result budget exceeds the existing reader limit")
    if budgets.get("max_ledger_bytes", _BUDGET_DEFAULTS["max_ledger_bytes"]) > 16 * 1024 * 1024:
        raise ValueError("ledger budget exceeds existing reader limit")
    return payload


def import_candidates(selection: list[dict[str, object]], manifest_dir: Path) -> list[dict[str, object]]:
    """Read existing P0 growth_candidates/entry_facts records as observations only.

    Growth's resource_point.resource_id is not a lifecycle family ID, and its
    site has no column/AST identity. Such records need an explicit exact selector
    to map allocations; this reader never manufactures one from the line number.
    """
    output: list[dict[str, object]] = []
    cache: dict[Path, tuple[list[dict[str, object]], str] | None] = {}
    for original in selection:
        item = dict(original)
        if "candidate_file" not in item:
            output.append(item)
            continue
        path = Path(str(item["candidate_file"]))
        path = path if path.is_absolute() else manifest_dir / path
        try:
            if path not in cache:
                # Lifecycle reader rejects symlinks/nonregular files and bounds bytes;
                # existing JSONL reader additionally bounds line size, nodes and depth.
                raw = load_text_regular(path, max_bytes=16 * 1024 * 1024).encode("utf-8")
                cache.clear()  # At most one bounded artifact in memory, regardless of project count.
                cache[path] = (read_jsonl_bytes_strict(raw, "project_candidate_import"), hashlib.sha256(raw).hexdigest())
            records, digest = cache[path]
            matches = [record for record in records if record.get("growth_id") == item["record_id"]
                       or record.get("entry_id") == item["record_id"]]
            if len(matches) != 1:
                item["_import_status"] = "mapping_ambiguous" if matches else "mapping_missing"
                item["_import_reason"] = "candidate_record_not_unique" if matches else "candidate_record_missing"
            else:
                record = matches[0]
                if "growth_id" in record:
                    candidate = GrowthCandidate.from_dict({key: record[key] for key in _GROWTH_FIELDS})
                    observation = candidate.to_dict()
                    # Keep static input references and positions, never the older verdicts.
                    item["_observation"] = {"artifact_kind": "growth_candidates", **observation}
                    if "entry_callable" not in item:
                        item["_import_status"] = "mapping_missing"
                        item["_import_reason"] = "growth_record_has_no_callable"
                elif "entry_id" in record:
                    entry = EntryFact.from_dict({key: record[key] for key in _ENTRY_FIELDS})
                    item["_observation"] = {"artifact_kind": "entry_facts", "entry_id": entry.entry_id,
                        "handler": entry.handler.to_dict(), "registration": entry.registration.to_dict(),
                        "attacker_inputs": [value.to_dict() for value in entry.attacker_inputs]}
                    if "entry_callable" in item and item["entry_callable"] != entry.handler.callable:
                        item["_import_status"] = "mapping_ambiguous"
                        item["_import_reason"] = "candidate_callable_conflict"
                    else:
                        item["entry_callable"] = entry.handler.callable
                else:
                    raise ValueError("unsupported existing candidate record")
                if not {"allocation", "resource_family_id"}.intersection(item) and "_import_status" not in item:
                    item["_import_status"] = "mapping_missing"
                    item["_import_reason"] = "candidate_has_no_exact_allocation_identity"
                if "source_sha256" not in item and "_import_status" not in item:
                    item["_import_status"] = "mapping_missing"
                    item["_import_reason"] = "candidate_source_snapshot_unbound"
                item["_candidate_file_sha256"] = digest
        except (AnalyzerError, ValueError, TypeError, KeyError, OSError):
            cache[path] = None
            item["_import_status"] = "mapping_missing"
            item["_import_reason"] = "candidate_artifact_invalid_or_unavailable"
        output.append(item)
    return output


def _path(payload: Mapping[str, object], values: Mapping[str, object], key: str, base: Path, alias: str | None = None) -> Path:
    override = values.get(alias or key)
    value = override if override is not None else payload[key]
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError(f"{key} needs a manifest path or CLI override")
    path = Path(value)
    if override is not None:
        return path.absolute()
    return path if path.is_absolute() else base / path


def _families(item: Mapping[str, object], unit: AnalysisUnit, extracted: ExtractedFacts) -> tuple[str, list[str]]:
    families = {family.family_id: family for family in unit.program.families}
    if item.get("source_sha256") and item["source_sha256"] not in {family.allocation.source_sha256 for family in families.values()}:
        return "stale_source", []
    if item["kind"] == "method":
        return ("mapped", sorted(families)) if families else ("mapping_missing", [])
    selected = set(families)
    if "resource_family_id" in item:
        selected &= {str(item["resource_family_id"])}
    allocation = item.get("allocation")
    if allocation is not None:
        matched: set[str] = set()
        for fact in extracted.facts:
            if fact.unit_id != unit.unit_id or fact.fact_kind != "create":
                continue
            fields = {"program_point": fact.program_point, "instance_key": fact.instance_key,
                      "path": fact.location.path, "start_line": fact.location.start_line,
                      "start_column": fact.site_start_column}
            if all(fields[key] == value for key, value in allocation.items()):
                # Exactly the family identity used by the source adapter; line alone is insufficient.
                matched.add(stable_identifier("family", {"allocation": asdict(fact.location),
                    "instance_key": fact.instance_key, "context": unit.unit_id, "type": fact.resource_type}))
        selected &= matched
    if item.get("source_sha256"):
        matching_snapshot = {key for key in selected if families[key].allocation.source_sha256 == item["source_sha256"]}
        if selected and not matching_snapshot:
            return "stale_source", []
        selected = matching_snapshot
    observation = item.get("_observation")
    if isinstance(observation, dict) and observation.get("artifact_kind") == "growth_candidates" and observation.get("kind") == "direct_allocation":
        site = observation["site"]
        selected = {key for key in selected if families[key].allocation.path == site["file"]
                    and families[key].allocation.start_line == site["start_line"]}
    if not selected:
        return "mapping_missing", []
    if len(selected) != 1:
        return "mapping_ambiguous", []
    return "mapped", sorted(selected)


def _report(payload: Mapping[str, object], ledger: list[dict[str, object]], units: list[dict[str, object]], tree_hash: str) -> dict[str, object]:
    counts = {stage: dict(sorted(Counter(str(row[stage]) for row in ledger).items()))
              for stage in ("mapping", "method_resolution", "resource_recognition", "extraction", "analysis")}
    incomplete = any(row["mapping"] != "mapped" or row["analysis"] != "analyzed" for row in ledger)
    return {"version": VERSION, "project_id": payload["project_id"], "source_tree_hash": tree_hash,
            "dependency_scope": payload["dependency_scope"], "status": "partial" if incomplete else "complete",
            "requested": len(ledger), "stage_counts": counts,
            "unique_analyzed_units": len({row["entry_callable"] for row in ledger if row["analysis"] == "analyzed"}),
            "unique_computed_units": len(units),
            "ledger": ledger, "units": units}


def resource_project(values: Mapping[str, object]) -> dict[str, object]:
    if values.get("allow_partial_codeql") or values.get("llm") not in {None, "off"}:
        raise AnalyzerError("CONFIG_INVALID_VALUE", "Project intake requires complete offline CodeQL facts and LLM off.")
    try:
        manifest_path = Path(values["manifest"])
        payload = _validate_manifest(load_json_regular(manifest_path))
        base = manifest_path.resolve(strict=True).parent
        source = _path(payload, values, "source_root", base).resolve(strict=True)
        database_path = _path(payload, values, "database", base)
        output = ensure_output_directory(_path(payload, values, "output", base, "out"))
        _files, tree_hash = _java_source_snapshot(source)
        payload = {**payload, "selection": import_candidates(payload["selection"], base)}
    except (ValueError, TypeError, KeyError, OSError) as exc:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Project manifest or local source is invalid.") from exc
    with _run_directory_lock(output):
        return _execute(payload, values, source, database_path, output, tree_hash)


def _execute(payload: Mapping[str, object], values: Mapping[str, object], source: Path,
             database_path: Path, output: Path, tree_hash: str) -> dict[str, object]:
    started = time.monotonic()
    budgets = {**_BUDGET_DEFAULTS, **payload["budgets"]}
    budget = AnalysisBudget(**budgets.get("unit", {}))
    selection = sorted(payload["selection"], key=lambda item: item["input_id"])
    ledger = [{"input_id": item["input_id"], "kind": item["kind"], "entry_callable": item.get("entry_callable"),
               "mapping": "unavailable", "method_resolution": "not_attempted", "resource_recognition": "not_attempted",
               "extraction": "not_attempted", "analysis": "skipped",
               "reason": "not_started", "resource_family_ids": [], "property_ids": []} for item in selection]
    for item, row in zip(selection, ledger):
        if "candidate_file" in item:
            row["imported_record_id"] = item["record_id"]
            row["candidate_file_sha256"] = item.get("_candidate_file_sha256")
            row["imported_observation"] = item.get("_observation")
            row["allocation_selector"] = item.get("allocation")
            row["source_sha256"] = item.get("source_sha256")
        if "_import_status" in item:
            row.update(mapping=item["_import_status"], reason=item["_import_reason"])
    _write_report(output, budgets, {**_report(payload, ledger, [], tree_hash), "status": "running"})
    if tree_hash != payload["tree_hash"]:
        for row in ledger:
            row.update(mapping="stale_source", method_resolution="source_mismatch", reason="source_tree_hash_mismatch")
        result = _report(payload, ledger, [], tree_hash)
        _write_report(output, budgets, result)
        return result
    eligible = [item for item in selection if "_import_status" not in item]
    if not eligible:
        result = _report(payload, ledger, [], tree_hash)
        _write_report(output, budgets, result)
        return result
    extraction_started = time.monotonic()
    try:
        database = validate_database(database_path)
        if database.source_root.resolve(strict=True) != source:
            raise ValueError("database source root differs from explicit project source")
        extracted = _codeql_facts({"schema_version": SCHEMA_VERSION, "mode": "codeql_database",
            "database": str(database_path), "entry_methods": sorted({item["entry_callable"] for item in eligible}),
            "budget": asdict(budget)}, {**values, "_project_intake_diagnostics": True}, output)
        if extracted.coverage.get("source_snapshot_sha256") != tree_hash:
            raise ValueError("extracted source snapshot differs from project identity")
    except (AnalyzerError, ValueError, TypeError, KeyError, OSError) as exc:
        for row in ledger:
            if row["mapping"] == "unavailable":
                row.update(extraction="failed", method_resolution="extraction_failed", reason="shared_extraction_failed")
        result = _report(payload, ledger, [], tree_hash)
        result["failure_kind"] = type(exc).__name__
        if isinstance(exc, AnalyzerError):
            result["failure_code"] = exc.code
            result["failure_details"] = dict(exc.details or {})
        scope_path = output / "source-scope.json"
        if scope_path.exists():
            scope = load_json_regular(scope_path)
            result["source_scope_artifact"] = "source-scope.json"
            if not scope.get("scope_complete", False):
                for row in ledger:
                    if row["reason"] == "shared_extraction_failed":
                        row.update(reason="archived_source_byte_mismatch" if scope.get("archived_mismatch_files") else "unarchived_source_dependency_gap", method_resolution="source_mismatch")
                result.update(_report(payload, ledger, [], tree_hash))
        atomic_write_json(output / "phase-costs.json", {
            "extraction_and_adaptation_seconds": time.monotonic() - extraction_started,
            "solve_and_serialization_seconds": None, "extraction_seconds": None,
            "adaptation_seconds": None, "replay_seconds": None,
            "note": "Extraction failed; solver and replay were not attempted; extraction/adaptation timing is combined."})
        _write_report(output, budgets, result)
        return result
    extraction_seconds = time.monotonic() - extraction_started
    inventory_path = output / "callable-inventory.json"
    inventory_payload = load_json_regular(inventory_path) if inventory_path.exists() else {}
    inventory: dict[str, list[dict[str, object]]] = {}
    for record in inventory_payload.get("callables", []):
        inventory.setdefault(record["unit_id"], []).append(record)
    units_by_id = {unit.unit_id: unit for unit in extracted.units}
    for item, row in zip(selection, ledger):
        if "_import_status" in item:
            continue
        unit = units_by_id.get(item["entry_callable"])
        identities = inventory.get(item["entry_callable"], [])
        if len(identities) > 1:
            row.update(mapping="mapping_ambiguous", method_resolution="ambiguous", extraction="extracted",
                       reason="callable_identity_not_unique", method_evidence=identities)
            continue
        if identities:
            identity = identities[0]
            row.update(method_resolution="method_resolved", method_evidence=identity,
                external_dependency_status="missing_source_body" if identity["external_call_count"] else "no_external_calls_observed")
            if item.get("source_sha256") and item["source_sha256"] != identity["source_sha256"]:
                row.update(mapping="stale_source", method_resolution="source_mismatch", extraction="extracted", reason="callable_source_hash_mismatch")
                continue
        elif unit is not None:
            # Old imported facts can prove identity at a resource site; they do
            # not establish a complete callable inventory for missing methods.
            row.update(method_resolution="method_resolved", method_evidence={"basis": "resource_fact_location",
                "locations": sorted({family.allocation.path for family in unit.program.families})})
        else:
            row.update(mapping="mapping_missing", method_resolution="method_missing" if inventory_payload else "inventory_unavailable",
                extraction="extracted", reason="callable_not_in_extracted_inventory" if inventory_payload else "callable_inventory_unavailable")
            continue
        if unit is None or not unit.program.families:
            unmodeled = bool(identities and (identities[0]["call_count"] or identities[0]["resource_coverage_notes"]))
            recognition = "resource_unmodeled" if unmodeled else "no_modeled_resource"
            row.update(mapping="mapped" if item["kind"] == "method" else "mapping_missing", extraction="extracted", resource_recognition=recognition,
                reason="calls_without_modeled_resource_family" if unmodeled else "no_resource_family_under_current_rules",
                resource_rule_scope=inventory_payload.get("rule_scope"), analysis="not_applicable")
            continue
        row["resource_recognition"] = "modeled_resource"
        mapping, families = _families(item, unit, extracted)
        row.update(mapping=mapping, extraction="extracted", resource_family_ids=families,
                   reason=None if mapping == "mapped" else mapping)
    unit_results: list[dict[str, object]] = []
    def received(record, unit_result):
        unit_id = record["unit_id"]
        rows = [row for row in ledger if row["mapping"] == "mapped" and row["entry_callable"] == unit_id]
        unit_results.append({"analysis_unit_id": unit_id, "root_sha256": record["root_sha256"],
                             "status": record["status"], "replay_directory": "analysis"})
        if unit_result is None:
            for row in rows:
                row.update(analysis="failed" if record["status"] == "unit_failed" else "budget_exit", reason=record["status"])
            return
        properties = unit_result.get("properties", [])
        for row in rows:
            selected = [prop for prop in properties if row["kind"] == "method"
                        or prop.get("resource_family_id") in row["resource_family_ids"]]
            row["property_ids"] = sorted({prop["property_id"] for prop in selected})
            if not unit_result.get("terminated", False):
                row.update(analysis="budget_exit", reason="unit_analysis_budget")
            elif not selected:
                row.update(analysis="unknown", reason="missing_property")
            else:
                row.update(analysis="analyzed", reason="property_unknown" if any(prop["status"] == "unknown" for prop in selected) else None)
        _check_report_budget(_report(payload, ledger, unit_results, tree_hash), budgets)

    receipt = None
    solving_started = time.monotonic()
    try:
        evidence_budget = budgets["max_output_bytes"] - budgets["max_ledger_bytes"]
        if evidence_budget <= 0:
            raise ValueError("output budget cannot reserve the bounded project ledger")
        receipt = analyze_sharded(extracted, output / "analysis", source_root=source,
            unit_ids=tuple(sorted({row["entry_callable"] for row in ledger if row["mapping"] == "mapped" and row["resource_family_ids"]})),
            on_unit=received, deadline=started + budgets["batch_timeout_ms"] / 1000,
            budget=ShardBudget(max_shard_bytes=budgets["max_unit_result_bytes"],
                max_index_bytes=budgets["max_index_bytes"], max_total_bytes=evidence_budget,
                max_decoded_bytes=budgets["max_decoded_bytes"]))
    except (AnalyzerError, ValueError, TypeError, KeyError, OSError) as exc:
        for row in ledger:
            if row["mapping"] == "mapped" and row["analysis"] == "skipped":
                row.update(analysis="failed", reason="sharded_run_failed", failure_kind=type(exc).__name__)
    result = _report(payload, ledger, unit_results, tree_hash)
    if receipt is not None:
        receipt = {**receipt, "index": "analysis/run-index.json"}
    atomic_write_json(output / "phase-costs.json", {
        "extraction_and_adaptation_seconds": extraction_seconds,
        "solve_and_serialization_seconds": time.monotonic() - solving_started,
        "extraction_seconds": None, "adaptation_seconds": None, "replay_seconds": None,
        "note": "Combined extraction includes scope hashing and callable inventory; solve includes shard serialization. Separate internal timing and replay are not measured here."})
    result["callable_inventory_artifact"] = "callable-inventory.json" if inventory_payload else None
    result["source_scope_artifact"] = "source-scope.json" if (output / "source-scope.json").exists() else None
    result["sharded_analysis"] = receipt
    result["replay_directory"] = "analysis" if receipt is not None else None
    result["serialized_evidence_bytes"] = receipt["total_serialized_bytes"] if receipt else None
    result["max_shard_bytes"] = receipt["max_shard_bytes"] if receipt else None
    result["budgets"] = {**budgets, "unit": asdict(budget)}
    result["budget_scope"] = "solver/batch budgets; all sharded facts/results/evidence plus bounded project ledger; CodeQL uses runner limits"
    if receipt is None or receipt["analysis_status"] != "complete":
        result["status"] = "partial"
    _write_report(output, budgets, result)
    return result


def _check_report_budget(result, budgets):
    size = len(canonical_json(result)) + 1
    if size > min(budgets["max_ledger_bytes"], budgets["max_output_bytes"]):
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Project ledger byte budget exceeded.")


def _write_report(output, budgets, result):
    _check_report_budget(result, budgets)
    atomic_write_json(output / "project-results.json", result)
