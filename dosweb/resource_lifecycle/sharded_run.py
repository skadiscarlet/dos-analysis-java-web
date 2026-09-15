"""Per-unit bounded delivery and actual local solver replay (LLM off)."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
from pathlib import Path
import time
import re

from dosweb.artifacts.identifiers import canonical_json
from dosweb.errors import AnalyzerError
from dosweb.resource_lifecycle.adapters import ExtractedFacts, extracted_from_dict, extracted_to_dict, validate_extracted
from dosweb.resource_lifecycle.shards import ShardBudget, ShardError, ShardReader, ShardWriter


_RUN_FORMAT = "lifecycle-run-2"
_CATALOG_NAME = "__lifecycle_required_inputs_v2__"
_INPUT_BINDING = "chosen_unit_facts_catalog; original_snapshot_is_provenance"


def _required_digest(identity, catalog_sha):
    return _sha({"input_snapshot_sha256": identity["input_snapshot_sha256"],
                 "scope": identity["scope"], "catalog_sha256": catalog_sha,
                 "input_binding": _INPUT_BINDING})


def _catalog_bound(catalog, budget):
    if len(catalog) > 4096 or len(canonical_json(catalog)) * 32 > budget.max_decoded_bytes:
        raise ValueError("required input catalog budget exceeded")


def _commands():
    # CLI imports this module too; keep the dependency acyclic at import time.
    from dosweb.resource_lifecycle import commands
    return commands


def _sha(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _single(extracted, unit):
    facts = tuple(f for f in extracted.facts if f.unit_id == unit.unit_id)
    coverage = dict(extracted.coverage)
    snapshot = extracted.snapshot_sha256
    if extracted.source_kind == "static_verified":
        requested = coverage["requested_entry_methods"]
        coverage.update(units=1, facts=len(facts),
                        partial_or_unsupported=sum(f.coverage_status != "complete" for f in facts),
                        dimension_gaps=len(unit.program.coverage_gaps),
                        matched_entry_methods=[unit.unit_id] if unit.unit_id in requested else [],
                        external_entry_units=int(unit.unit_id in requested),
                        local_method_units=int(unit.unit_id not in requested))
        snapshot = _sha([asdict(f) for f in facts])
    return validate_extracted(replace(extracted, units=(unit,), facts=facts,
                                      snapshot_sha256=snapshot, coverage=coverage))


def _verify_source(identity, source_root):
    if identity["source_kind"] != "static_verified":
        return
    if source_root is None:
        raise ValueError("semantic replay requires --source-root for static source identity verification")
    if _commands()._java_source_snapshot(Path(source_root))[1] != identity["source_snapshot_sha256"]:
        raise ValueError("source tree snapshot mismatch")


def analyze_sharded(extracted: ExtractedFacts, output: Path, *,
                    budget: ShardBudget = ShardBudget(), source_root: Path | None = None,
                    unit_ids: tuple[str, ...] | None = None, on_unit=None, deadline: float | None = None) -> dict:
    """Analyze each input unit independently and publish a compact run receipt.

    Storage complete means all declared records were published. analysis_status
    remains partial for empty runs or a failed unit; no failure is omitted.
    """
    try:
        extracted = validate_extracted(extracted)
        if len(extracted.units) > 4096 or len({u.unit_id for u in extracted.units}) != len(extracted.units):
            raise ValueError("invalid/duplicate or excessive unit ledger")
        requested_ids = set(unit_ids) if unit_ids is not None else {u.unit_id for u in extracted.units}
        if not requested_ids <= {u.unit_id for u in extracted.units}:
            raise ValueError("selected unit does not exist")
        selected_units = tuple(u for u in extracted.units if u.unit_id in requested_ids)
        if _CATALOG_NAME in requested_ids:
            raise ValueError("reserved unit identifier")
        catalog = []
        for unit in sorted(selected_units, key=lambda item: item.unit_id):
            catalog.append({"unit_id": unit.unit_id,
                            "facts_sha256": _sha(extracted_to_dict(_single(extracted, unit)))})
            _catalog_bound(catalog, budget)
        commands = _commands()
        identity = {"tool_version": commands.TOOL_VERSION,
                    "implementation_sha256": commands._implementation_sha256(),
                    "contracts_versions": sorted({u.program.contracts_version for u in selected_units}),
                    "source_kind": extracted.source_kind,
                    "source_snapshot_sha256": extracted.coverage.get("source_snapshot_sha256"),
                    "input_snapshot_sha256": extracted.snapshot_sha256,
                    "extractor_version": extracted.extractor_version,
                    "analysis_budget": asdict(extracted.budget),
                    "llm": "off", "unit_count": len(selected_units),
                    "scope": "selected" if unit_ids is not None else "full_run"}
        identity.update(run_format=_RUN_FORMAT, input_binding=_INPUT_BINDING,
                        required_catalog_sha256=_sha(catalog),
                        required_inputs_sha256=_required_digest(identity, _sha(catalog)))
        if source_root is not None:
            _verify_source(identity, source_root)
        writer = ShardWriter(Path(output), budget)
        ledger = []
        for unit in selected_units:
            single = _single(extracted, unit)
            if deadline is not None and time.monotonic() >= deadline:
                payload = {"unit_id": unit.unit_id, "status": "batch_budget_exit", "reason": "batch_timeout",
                           "facts_sha256": _sha(extracted_to_dict(single))}
                root = writer.add(unit.unit_id, payload)
                record = {"unit_id": unit.unit_id, "status": "batch_budget_exit", "root_sha256": root}
                ledger.append(record)
                if on_unit is not None:
                    on_unit(record, None)
                continue
            unit_result = None
            try:
                results = commands._analyze_payload(single)
                evidence = commands._evidence_payload(single, results)
                payload = {"unit_id": unit.unit_id, "status": "analyzed",
                           "facts": extracted_to_dict(single), "results": results, "evidence": evidence,
                           "analysis_outcome": "analyzed" if results["units"][0]["terminated"] else "analysis_budget_exit"}
                root = writer.add(unit.unit_id, payload)
                record = {"unit_id": unit.unit_id, "status": payload["analysis_outcome"], "root_sha256": root}
                unit_result = results["units"][0]
            except ShardError as exc:
                root = writer.add(unit.unit_id, {"unit_id": unit.unit_id, "status": "storage_budget_exit",
                                          "reason": str(exc), "facts_sha256": _sha(extracted_to_dict(single))})
                record = {"unit_id": unit.unit_id, "status": "storage_budget_exit", "root_sha256": root}
            except (AnalyzerError, ValueError, TypeError, KeyError, OSError) as exc:
                root = writer.add(unit.unit_id, {"unit_id": unit.unit_id, "status": "unit_failed",
                    "failure_kind": type(exc).__name__, "facts_sha256": _sha(extracted_to_dict(single))})
                record = {"unit_id": unit.unit_id, "status": "unit_failed", "root_sha256": root}
            ledger.append(record)
            # Delivery callbacks are outside analysis/storage exception handling.
            # A failure aborts publication; never retry an already-added unit.
            if on_unit is not None:
                on_unit(record, unit_result)
        writer.add(_CATALOG_NAME, catalog)
        identity["analysis_status"] = "complete" if ledger and all(x["status"] == "analyzed" for x in ledger) else "partial"
        writer.finalize(identity)
        return {"format": "lifecycle-shards-1", "run_format": _RUN_FORMAT, "input_binding": _INPUT_BINDING, "analysis_status": identity["analysis_status"],
                "units": ledger, "total_serialized_bytes": writer.total_bytes,
                "max_shard_bytes": writer.max_shard_bytes, "index": str(Path(output) / "run-index.json")}
    except AnalyzerError:
        raise
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Sharded lifecycle analysis failed.", {"reason": str(exc)}) from exc


def replay_sharded(run_dir: Path, source_root: Path | None = None, integrity_only: bool = False,
                   *, budget: ShardBudget = ShardBudget()) -> dict:
    """Re-solve every saved unit and compare full result/evidence, or check bytes.

    No full-run object reconstruction; only one unit is decoded at a time.
    Manual IR runs are explicitly labeled and do not count as source extraction.
    """
    try:
        reader = ShardReader(Path(run_dir), budget)
        identity = reader.index["identity"]
        if identity.get("llm") != "off" or type(identity.get("unit_count")) is not int:
            raise ValueError("unsupported sharded run identity")
        if identity.get("run_format") != _RUN_FORMAT or identity.get("input_binding") != _INPUT_BINDING:
            raise ValueError("unsupported sharded run version: required input catalog missing; re-analyze")
        if identity.get("scope") not in {"full_run", "selected"}:
            raise ValueError("invalid run selection scope")
        objects = reader.iter_objects()
        first = next(objects, None)
        if first is None or first[0] != _CATALOG_NAME or not isinstance(first[1], list):
            raise ValueError("required input catalog missing or misplaced")
        catalog = first[1]
        _catalog_bound(catalog, budget)
        required = {}
        for row in catalog:
            if (not isinstance(row, dict) or set(row) != {"unit_id", "facts_sha256"}
                or not isinstance(row["unit_id"], str) or not row["unit_id"]
                or row["unit_id"] in required or row["unit_id"] == _CATALOG_NAME
                or not isinstance(row["facts_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", row["facts_sha256"]) is None):
                raise ValueError("invalid required input catalog entry")
            required[row["unit_id"]] = row["facts_sha256"]
        if (catalog != sorted(catalog, key=lambda row: row["unit_id"])
            or len(required) != identity["unit_count"]
            or _sha(catalog) != identity.get("required_catalog_sha256")
            or _required_digest(identity, _sha(catalog)) != identity.get("required_inputs_sha256")):
            raise ValueError("required input identity mismatch")
        commands = _commands()
        if not integrity_only:
            if identity["tool_version"] != commands.TOOL_VERSION or identity["implementation_sha256"] != commands._implementation_sha256():
                raise ValueError("tool implementation identity mismatch")
            _verify_source(identity, source_root)
        count = 0
        failures = []
        contracts = set()
        for name, payload in objects:
            count += 1
            if not isinstance(payload, dict) or payload.get("unit_id") != name:
                raise ValueError("unit record identity mismatch")
            if name not in required:
                raise ValueError("unexpected or repeated required input")
            observed_input = _sha(payload["facts"]) if payload.get("status") == "analyzed" else payload.get("facts_sha256")
            if observed_input != required.pop(name):
                raise ValueError("required unit facts identity mismatch")
            if payload.get("status") != "analyzed":
                failures.append(name)
                if not integrity_only:
                    raise ValueError("failed unit prevents full semantic replay")
                continue
            if payload.get("analysis_outcome") != "analyzed":
                failures.append(name)
            if integrity_only:
                continue
            single = validate_extracted(extracted_from_dict(payload["facts"]))
            if len(single.units) != 1 or single.units[0].unit_id != name:
                raise ValueError("facts unit identity mismatch")
            if (single.source_kind != identity["source_kind"] or
                single.extractor_version != identity["extractor_version"] or
                single.coverage.get("source_snapshot_sha256") != identity["source_snapshot_sha256"] or
                asdict(single.budget) != identity["analysis_budget"]):
                raise ValueError("facts provenance identity mismatch")
            contracts.add(single.units[0].program.contracts_version)
            results = commands._analyze_payload(single)
            evidence = commands._evidence_payload(single, results)
            if _sha(results) != _sha(payload["results"]) or _sha(evidence) != _sha(payload["evidence"]):
                raise ValueError("recomputed result/evidence mismatch")
        if required or count != identity["unit_count"]:
            raise ValueError("run unit count mismatch")
        if not integrity_only:
            if not count or identity.get("analysis_status") != "complete":
                raise ValueError("partial or empty run cannot complete semantic replay")
            if sorted(contracts) != identity["contracts_versions"]:
                raise ValueError("contract identity mismatch")
        return {"consistent": True, "mode": "integrity_only" if integrity_only else "semantic_replay",
                "scope": identity.get("scope", "full_run"), "source_kind": identity["source_kind"],
                "unit_count": count, "failed_units": failures,
                "analysis_status": identity.get("analysis_status"), "run_format": _RUN_FORMAT,
                "input_binding": _INPUT_BINDING, "original_input_snapshot_recomputed": False}
    except AnalyzerError:
        raise
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Sharded lifecycle replay failed.", {"reason": str(exc)}) from exc


def iter_run_units(reader: ShardReader):
    """Iterate unit records, excluding the v2 catalog; not semantic verification.

    Consumers that report successful replay must call replay_sharded separately.
    The underlying generic store's iter_objects includes the catalog object.
    """
    if reader.index["identity"].get("run_format") != _RUN_FORMAT:
        raise AnalyzerError("ARTIFACT_INPUT_INVALID", "Unsupported sharded run version; re-analyze with lifecycle-run-2.")
    for name, payload in reader.iter_objects():
        if name != _CATALOG_NAME:
            yield name, payload
