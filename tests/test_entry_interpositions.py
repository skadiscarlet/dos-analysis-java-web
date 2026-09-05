from __future__ import annotations

import unittest

from dosweb.artifacts.schemas import validate_references
from dosweb.production import _normalize_interposition_rows


class EntryInterpositionTests(unittest.TestCase):
    def _row(self, **changes: object) -> dict[str, object]:
        value: dict[str, object] = {
            "entry_file": "fixture/interposition/InterpositionFixture.java",
            "entry_start_line": 6,
            "interposer_fqn": "fixture.interposition.RegisteredFilter.doFilter",
            "interposer_file": "fixture/interposition/InterpositionFixture.java",
            "interposer_start_line": 5,
            "registration_kind": "filter_registration_bean",
            "registration_fqn": "org.springframework.boot.web.servlet.FilterRegistrationBean.setFilter",
            "registration_file": "fixture/interposition/InterpositionFixture.java",
            "registration_start_line": 8,
            "url_predicate_kind": "exact", "url_predicate_value": "/api/push",
            "order_status": "known", "order_value": "1",
            "action_fqn": "fixture.interposition.Service.accept",
            "action_file": "fixture/interposition/InterpositionFixture.java", "action_start_line": 5,
            "chain_file": "fixture/interposition/InterpositionFixture.java", "chain_start_line": 5,
            "phase": "unknown", "action_before_chain": False,
            "coverage_status": "partial", "coverage_note": "cfg_action_before_chain_unproven",
        }
        value.update(changes)
        return value

    def _entries(self) -> list[dict[str, object]]:
        return [{
            "entry_id": "entry:a",
            "handler": {"file": "fixture/interposition/InterpositionFixture.java", "start_line": 6},
            "registration": {"kind": "annotation_mapping", "callable": "fixture.Controller.push", "file": "fixture/interposition/InterpositionFixture.java", "start_line": 6},
            "route_or_event": "POST /api/push/**",
        }]

    def test_partial_first_row_is_bound_to_one_complete_entry(self) -> None:
        records = _normalize_interposition_rows([self._row()], self._entries())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["entry_id"], "entry:a")
        self.assertEqual(records[0]["coverage_status"], "partial")
        validate_references("entry_interposition_facts", records, {"entry_id": {"entry:a"}})

    def test_route_normalization_variants_choose_one_registration_identity(self) -> None:
        duplicate = {
            **self._entries()[0],
            "entry_id": "entry:b",
            "route_or_event": "/api/push/**",
        }
        records = _normalize_interposition_rows([self._row()], [*self._entries(), duplicate])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["entry_id"], "entry:a")

    def test_ambiguous_handler_or_unsafe_complete_claim_is_not_complete(self) -> None:
        distinct = {
            **self._entries()[0],
            "entry_id": "entry:b",
            "registration": {"kind": "static_registration", "callable": "fixture.Other.register", "file": "fixture/Other.java", "start_line": 9},
        }
        self.assertEqual(_normalize_interposition_rows([self._row()], [*self._entries(), distinct]), [])
        record = _normalize_interposition_rows(
            [self._row(coverage_status="complete", phase="unknown", action_before_chain=False)],
            self._entries(),
        )[0]
        self.assertEqual(record["coverage_status"], "partial")
        self.assertEqual(record["coverage_note"], "interposition_complete_claim_rejected")

    def test_negative_shapes_are_not_promoted(self) -> None:
        # Dynamic URL/order and action-after-chain must reach the normalizer as partial rows.
        for row in (
            self._row(url_predicate_kind="unknown", coverage_note="dynamic_url_pattern"),
            self._row(order_status="unknown", order_value="unknown", coverage_note="dynamic_order"),
            self._row(phase="after_handler", action_before_chain=False, coverage_note="action_after_chain"),
        ):
            with self.subTest(note=row["coverage_note"]):
                record = _normalize_interposition_rows([row], self._entries())[0]
                self.assertEqual(record["coverage_status"], "partial")


if __name__ == "__main__":
    unittest.main()
