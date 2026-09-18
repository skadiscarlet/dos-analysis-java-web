import pytest

from dosweb.artifacts.identifiers import stable_identifier
from dosweb.artifacts.schemas import validate_records
from dosweb.conclude import CandidateCoverage
from dosweb.entries import (
    EntryFact,
    FrameworkCoverage,
    normalize_entry_rows,
    registration_coverage_pattern_id,
)
from dosweb.errors import AnalyzerError


def _row(*, coverage_note: str = "spring_annotation_mapping") -> dict[str, object]:
    return {
        "framework": "spring_mvc",
        "protocol": "http",
        "handler_fqn": "fixture.Handler.handle",
        "handler_file": "src/Handler.java",
        "handler_start_line": 20,
        "registration_kind": "annotation_mapping",
        "registration_fqn": "fixture.Handler.handle",
        "registration_file": "src/Handler.java",
        "registration_start_line": 18,
        "route_or_event": "POST /items",
        "auth_context": "unauthenticated",
        "attacker_input_name": "body",
        "attacker_input_type": "byte[]",
        "attacker_input_kind": "request_body",
        "materialization_phase": "in_handler",
        "coverage_status": "complete",
        "coverage_note": coverage_note,
    }


def test_registration_coverage_uses_explicit_pattern_identity() -> None:
    assert registration_coverage_pattern_id(
        "servlet", "static_registration", "web_xml_servlet_mapping"
    ) == "entry-registration-coverage:servlet:static_registration:web_xml_servlet_mapping"
    assert registration_coverage_pattern_id(
        "servlet", "static_registration", "filter_registration_bean"
    ) == "entry-registration-coverage:servlet:static_registration:filter_registration_bean"


def test_substring_or_wrong_registration_kind_cannot_claim_coverage() -> None:
    assert registration_coverage_pattern_id(
        "servlet", "static_registration", "invented_static_registration"
    ) is None
    assert registration_coverage_pattern_id(
        "servlet", "annotation_mapping", "filter_registration_bean"
    ) is None


def test_complete_entry_persists_exact_pattern_in_identity_roundtrip_and_schema() -> None:
    fact = EntryFact.from_raw(_row())
    pattern_id = (
        "entry-registration-coverage:"
        "spring_mvc:annotation_mapping:spring_annotation_mapping"
    )
    assert fact.registration_pattern_id == pattern_id
    assert fact.semantic_identity()["registration_pattern_id"] == pattern_id
    assert fact.entry_id == stable_identifier("entry", fact.semantic_identity())
    assert fact.to_dict()["registration_pattern_id"] == pattern_id
    assert EntryFact.from_dict(fact.to_dict()) == fact
    validate_records("entry_facts", [fact.to_dict()])


def test_complete_entry_rejects_unmodeled_pattern_instead_of_inheriting_kind() -> None:
    with pytest.raises(AnalyzerError) as raised:
        EntryFact.from_raw(_row(coverage_note="invented_annotation_mapping"))
    assert raised.value.code == "COVERAGE_ENTRY_INVALID"


def test_exact_pattern_is_not_dropped_or_merged_during_normalization() -> None:
    rows = normalize_entry_rows(
        [
            _row(coverage_note="spring_annotation_mapping"),
            _row(coverage_note="spring_spel_source_default_modeled_entry"),
        ]
    )
    assert len(rows) == 2
    assert len({row["entry_id"] for row in rows}) == 2
    assert {
        row["registration_pattern_id"] for row in rows
    } == {
        "entry-registration-coverage:spring_mvc:annotation_mapping:spring_annotation_mapping",
        "entry-registration-coverage:spring_mvc:annotation_mapping:spring_spel_source_default_modeled_entry",
    }


def test_deserialization_rejects_pattern_identity_drift() -> None:
    fact = EntryFact.from_raw(_row())
    record = fact.to_dict()
    record["registration_pattern_id"] = (
        "entry-registration-coverage:"
        "spring_mvc:annotation_mapping:spring_spel_source_default_modeled_entry"
    )
    with pytest.raises(AnalyzerError) as raised:
        EntryFact.from_dict(record)
    assert raised.value.code == "ANALYSIS_ENTRY_INVALID"


def test_artifact_schema_rejects_cross_kind_registration_pattern_identity() -> None:
    record = EntryFact.from_raw(_row()).to_dict()
    record["registration_pattern_id"] = (
        "entry-registration-coverage:"
        "spring_mvc:static_registration:armeria_annotated_service_registration"
    )
    with pytest.raises(AnalyzerError) as raised:
        validate_records("entry_facts", [record])
    assert raised.value.code == "ARTIFACT_INVALID_RECORD"


def test_entry_scoped_candidate_coverage_cannot_cite_a_sibling_pattern() -> None:
    entry_pattern_id = (
        "entry-registration-coverage:"
        "spring_mvc:annotation_mapping:spring_spel_source_default_modeled_entry"
    )
    sibling_pattern_id = (
        "entry-registration-coverage:"
        "spring_mvc:annotation_mapping:spring_annotation_mapping"
    )
    with pytest.raises(AnalyzerError) as raised:
        CandidateCoverage(
            framework="spring_mvc",
            status="partial",
            supported_patterns=(sibling_pattern_id,),
            unsupported_patterns=("entry_exact_pattern_uncovered",),
            effect_on_verdict="forces_unknown",
            registration_pattern_id=entry_pattern_id,
            entry_id="entry:fixture",
        )
    assert raised.value.code == "COVERAGE_ENTRY_INVALID"


@pytest.mark.parametrize(
    "unsupported_supported_pattern",
    (
        "invented_registration_pattern",
        "annotation_mapping",
        "entry-registration-coverage:servlet:annotation_mapping:servlet_annotation_mapping",
    ),
)
def test_generic_candidate_coverage_rejects_non_framework_exact_supported_patterns(
    unsupported_supported_pattern: str,
) -> None:
    with pytest.raises(AnalyzerError) as raised:
        CandidateCoverage(
            framework="spring_mvc",
            status="complete",
            supported_patterns=(unsupported_supported_pattern,),
            unsupported_patterns=(),
            effect_on_verdict="none",
        )
    assert raised.value.code == "COVERAGE_ENTRY_INVALID"


def test_framework_coverage_is_narrowed_to_the_current_entry_exact_pattern() -> None:
    annotation_id = (
        "entry-registration-coverage:"
        "spring_mvc:annotation_mapping:spring_annotation_mapping"
    )
    spel_id = (
        "entry-registration-coverage:"
        "spring_mvc:annotation_mapping:spring_spel_source_default_modeled_entry"
    )
    framework = FrameworkCoverage(
        "spring_mvc",
        "partial",
        tuple(sorted((annotation_id, spel_id))),
        ("reflection_controller_registration",),
        "forces_unknown",
    )
    narrowed = CandidateCoverage.from_framework(
        framework,
        registration_pattern_id=spel_id,
        entry_id="entry:fixture",
    )
    assert narrowed.status == "complete"
    assert narrowed.supported_patterns == (spel_id,)
    assert narrowed.unsupported_patterns == ()


def test_framework_coverage_missing_current_exact_pattern_becomes_candidate_gap() -> None:
    annotation_id = (
        "entry-registration-coverage:"
        "spring_mvc:annotation_mapping:spring_annotation_mapping"
    )
    spel_id = (
        "entry-registration-coverage:"
        "spring_mvc:annotation_mapping:spring_spel_source_default_modeled_entry"
    )
    framework = FrameworkCoverage(
        "spring_mvc", "complete", (annotation_id,), (), "none"
    )
    narrowed = CandidateCoverage.from_framework(
        framework,
        registration_pattern_id=spel_id,
        entry_id="entry:fixture",
    )
    assert narrowed.status == "partial"
    assert narrowed.supported_patterns == ()
    assert narrowed.unsupported_patterns == (
        f"entry_registration_pattern_uncovered:{spel_id}",
    )
