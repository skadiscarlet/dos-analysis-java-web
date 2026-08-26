from __future__ import annotations

import hashlib
import unittest

from dosweb.errors import AnalyzerError
from dosweb.growth.models import (
    BoundedSlicePayload,
    CfgSummary,
    RegistrationFact,
    SourceExcerpt,
    StaticFact,
)


class StrictGrowthPayloadTests(unittest.TestCase):
    def _excerpt(self) -> SourceExcerpt:
        content = "map.put(key, value);\n"
        return SourceExcerpt(
            "excerpt:1", "src/Fixture.java", 1, 1, content,
            "a" * 64, hashlib.sha256(content.encode()).hexdigest(),
        )

    def _payload(self, **changes: object) -> BoundedSlicePayload:
        values = {
            "entry_id": "entry:fixture",
            "growth_id": "growth:fixture",
            "source_excerpts": [self._excerpt()],
            "static_facts": [StaticFact("fact:1", "container_write", "excerpt:1", "sink")],
            "cfg_summary": CfgSummary(("path:1",), ("in_handler",), ("fact:1",)),
            "registration_facts": [RegistrationFact("spring_mvc", "excerpt:1")],
            "config_facts": [],
        }
        values.update(changes)
        return BoundedSlicePayload(**values)

    def test_constructor_normalizes_iterables_to_immutable_snapshot(self) -> None:
        facts = [StaticFact("fact:1", "container_write", "excerpt:1", "sink")]
        payload = self._payload(static_facts=facts)
        facts.append(StaticFact("fact:2", "flow", "excerpt:1", "flows_to"))
        self.assertEqual(tuple(item.fact_id for item in payload.static_facts), ("fact:1",))
        self.assertIsInstance(payload.static_facts, tuple)

    def test_payload_rejects_free_detail_text_and_dangling_excerpt_reference(self) -> None:
        with self.assertRaises(TypeError):
            StaticFact("fact:1", "container_write", "excerpt:1", "sink", detail="private")
        with self.assertRaises(AnalyzerError) as raised:
            self._payload(static_facts=[StaticFact("fact:1", "container_write", "excerpt:missing", "sink")])
        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")

    def test_config_fact_rejects_secret_text_value_and_non_enum_value(self) -> None:
        from dosweb.growth.models import ConfigFact

        for value in ("sk-private-value", "database-password", "arbitrary-string"):
            with self.subTest(value=value):
                with self.assertRaises(AnalyzerError):
                    ConfigFact("request_limit", value, "excerpt:1")

    def test_config_fact_accepts_matching_virtual_config_provenance_only(self) -> None:
        from dosweb.growth.models import ConfigFact

        fact = ConfigFact("capacity", 16, "config:explicit", "config:explicit")
        payload = self._payload(config_facts=(fact,))
        self.assertEqual("config:explicit", payload.config_facts[0].source_location_ref)
        with self.assertRaises(AnalyzerError):
            ConfigFact("capacity", 16, "config:other", "config:explicit")

    def test_payload_rejects_dangling_static_fact_value_reference(self) -> None:
        with self.assertRaises(AnalyzerError) as raised:
            self._payload(static_facts=[StaticFact("fact:1", "container_write", "excerpt:1", "sink", "fact:missing")])
        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")

    def test_unknown_enum_and_unexpected_payload_field_are_rejected(self) -> None:
        with self.assertRaises(AnalyzerError):
            StaticFact("fact:1", "arbitrary_kind", "excerpt:1", "sink")
        with self.assertRaises(TypeError):
            BoundedSlicePayload(**{**self._payload().__dict__, "detail": "private"})

    def test_bounded_materialization_stops_at_limit_plus_one(self) -> None:
        consumed = 0

        def facts():
            nonlocal consumed
            while True:
                consumed += 1
                yield StaticFact(f"fact:{consumed}", "flow", "excerpt:1", "source")

        with self.assertRaises(AnalyzerError) as raised:
            self._payload(static_facts=facts())
        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")
        self.assertEqual(consumed, 257)

        consumed = 0

        def paths():
            nonlocal consumed
            while True:
                consumed += 1
                yield f"path:{consumed}"

        with self.assertRaises(AnalyzerError):
            CfgSummary(paths(), (), ())
        self.assertEqual(consumed, 65)

    def test_config_fact_accepts_signed_64_bit_values_and_rejects_out_of_range_cleanly(self) -> None:
        from dosweb.growth.models import ConfigFact

        fact = ConfigFact("capacity", 10_000_000_000, "excerpt:1")
        self.assertEqual(fact.normalized_value, 10_000_000_000)

        for value in (True, False, -(2**63), 2**63):
            with self.subTest(value=value):
                with self.assertRaises(AnalyzerError) as raised:
                    ConfigFact("capacity", value, "excerpt:1")
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")

    def test_growth_contract_iterables_are_bounded_before_materialization(self) -> None:
        from dosweb.growth.models import AttackerInfluence, GrowthContract

        consumed = 0
        def influences():
            nonlocal consumed
            while True:
                consumed += 1
                yield AttackerInfluence("key", f"fact:{consumed}")

        with self.assertRaises(AnalyzerError) as raised:
            GrowthContract("yes", "container_growth", "entries", influences(), "adds_entries", (), "high")
        self.assertEqual(raised.exception.code, "LLM_RESPONSE_SCHEMA_INVALID")
        self.assertEqual(consumed, 17)

    def test_duplicate_semantic_identifiers_are_rejected(self) -> None:
        duplicate = StaticFact("fact:1", "flow", "excerpt:1", "source")
        with self.assertRaises(AnalyzerError) as raised:
            self._payload(static_facts=(duplicate, duplicate))
        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")


if __name__ == "__main__":
    unittest.main()
