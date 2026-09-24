"""Offline regressions for typed security-fact binding, not target scanning."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dosweb.codeql import DatabaseInfo, QueryResult
from dosweb.codeql.decoder import ENTRY_COLUMNS, INTERPOSITION_COLUMNS, SECURITY_COLUMNS
from dosweb.production import build_production_pipeline
from dosweb.reachability import EntrySecurityFact
from dosweb.reachability.extract import bind_entry_security_rows
from dosweb.reachability.verify import derive_auth_contract_from_facts, verify_auth_contract


def _entry(identifier: str, route: str, line: int = 20) -> dict[str, object]:
    return {
        "entry_id": identifier,
        "handler": {"callable": "fixture.Api.handle", "file": "src/Api.java", "start_line": line},
        "route_or_event": route,
    }


def _row(**changes: object) -> dict[str, object]:
    return {
        "handler_fqn": "fixture.Api.handle", "handler_file": "src/Api.java",
        "handler_start_line": 20, "route_or_event": "",
        "fact_file": "src/Api.java", "fact_start_line": 19,
        "kind": "annotation", "value": "unauthenticated_annotation",
        "coverage_status": "complete", "coverage_note": "permit_all", **changes,
    }


@pytest.mark.parametrize("kind,value,coverage", [
    ("annotation", "unauthenticated_annotation", "complete"),
    ("servlet_constraint", "privileged_constraint", "complete"),
    ("deployment_gate", "optional", "partial"),
])
def test_exact_handler_fact_survives_multiple_registered_routes(kind, value, coverage):
    entries = [_entry("entry:a", "GET /one"), _entry("entry:b", "POST /two"),
               _entry("entry:other", "GET /one", line=40)]
    row = _row(kind=kind, value=value, coverage_status=coverage)
    facts = bind_entry_security_rows([row], entries)
    assert {fact.entry_id for fact in facts} == {"entry:a", "entry:b"}
    assert all(fact.coverage == coverage for fact in facts)
    assert facts == bind_entry_security_rows([row], list(reversed(entries)))


@pytest.mark.parametrize("matcher,expected", [
    ("GET /items", {"entry:get"}),
    ("POST /items", {"entry:post"}),
    ("GET /items/**", {"entry:get", "entry:child"}),
    ("/items", {"entry:get", "entry:post", "entry:unspecified"}),
])
def test_route_rules_preserve_explicit_http_method(matcher, expected):
    entries = [_entry("entry:get", "GET /items"), _entry("entry:post", "POST /items"),
               _entry("entry:unspecified", "/items"), _entry("entry:child", "GET /items/one")]
    facts = bind_entry_security_rows([
        _row(kind="security_filter_chain", value="low_privilege_filter", route_or_event=matcher)
    ], entries)
    assert {fact.entry_id for fact in facts} == expected


def test_dynamic_or_untyped_rules_do_not_gain_handler_wide_authority():
    entries = [_entry("entry:a", "GET /one"), _entry("entry:b", "POST /two")]
    assert not bind_entry_security_rows([
        _row(kind="security_filter_chain", value="security_matcher_unknown",
             route_or_event="dynamic_matcher", coverage_status="partial")
    ], entries)
    assert not bind_entry_security_rows([
        _row(kind="filter", value="unauthenticated_filter")
    ], entries)


@pytest.mark.parametrize("partial_gate", [False, True])
def test_production_entries_preserve_handler_auth_and_explicit_gate_for_route_aliases(tmp_path: Path, partial_gate: bool):
    database = tmp_path / "database"
    source = tmp_path / "source"
    database.mkdir(); source.mkdir()
    (source / "pom.xml").write_text("<project><dependencies><dependency>org.springframework</dependency></dependencies></project>")
    info = DatabaseInfo(database, source, "d" * 64)
    entries = [[
        "spring_mvc", "http", "fixture.Api.handle", "src/Api.java", 20,
        "annotation_mapping", "fixture.Api", "src/Api.java", 18,
        route, "unknown", "body", "String", "request_body", "in_handler", "complete", "spring_annotation_mapping"
    ] for route in ("GET /one", "POST /two")]
    security_rows = [_row()]
    if partial_gate:
        security_rows.append(_row(kind="deployment_gate", value="optional", coverage_status="partial", fact_start_line=17))

    def fake_run(query, _database, output_dir, **_kwargs):
        if query.name == "SpringMvcEntries.ql":
            columns, rows = ENTRY_COLUMNS, entries
        elif query.name == "EntrySecurity.ql":
            columns, rows = SECURITY_COLUMNS, [[r[c] for c in SECURITY_COLUMNS] for r in security_rows]
        elif query.name == "EntryInterpositions.ql":
            columns, rows = INTERPOSITION_COLUMNS, []
        else:
            columns, rows = ENTRY_COLUMNS, []
        decoded = output_dir / (query.stem + ".json")
        decoded.write_text(json.dumps({"#select": {"columns": list(columns), "tuples": rows}}))
        return QueryResult(query.name, query, query, decoded, "a" * 64, "b" * 64)

    output = tmp_path / "output"
    pipeline = build_production_pipeline({
        "command": "entries", "database": database, "output": output,
        "source_checkout": source, "analysis_source_root": source,
    }, environ={}, validate_database_fn=lambda *_a, **_kw: info, run_query_fn=fake_run)
    assert pipeline.run("entries")["status"] == "completed"
    normalized = [json.loads(line) for line in (output / "entry_facts.jsonl").read_text().splitlines()]
    facts = tuple(EntrySecurityFact.from_dict(json.loads(line)) for line in (output / "entry_security_facts.jsonl").read_text().splitlines())
    assert len(normalized) == 2
    for entry in normalized:
        local = tuple(fact for fact in facts if fact.entry_id == entry["entry_id"])
        auth = derive_auth_contract_from_facts(entry["entry_id"], local)
        assert auth is not None
        decision = verify_auth_contract(entry["entry_id"], auth, local, slice_fact_ids=frozenset(fact.fact_id for fact in local))
        assert decision.deployment_status == ("unknown" if partial_gate else "default_enabled")
        assert decision.status == ("unknown" if partial_gate else "ordinary_attacker_reachable")
        if partial_gate:
            assert not any(fact.value == "default_enabled" for fact in local)
