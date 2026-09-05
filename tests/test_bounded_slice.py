from __future__ import annotations

import hashlib
import unittest

from dosweb.errors import AnalyzerError
from dosweb.growth.models import BoundedSlice, BoundedSlicePayload, CfgSummary, RegistrationFact, SourceExcerpt, StaticFact


class BoundedSliceTests(unittest.TestCase):
    def _payload(self, **overrides: object) -> BoundedSlicePayload:
        content = "map.put(key, value);\n"
        values = {
            "entry_id": "entry:fixture", "growth_id": "growth:fixture",
            "source_excerpts": (SourceExcerpt("excerpt:1", "src/Fixture.java", 1, 1, content, "a" * 64, hashlib.sha256(content.encode()).hexdigest()),),
            "static_facts": (StaticFact("fact:put", "container_write", "excerpt:1", "sink"),),
            "cfg_summary": CfgSummary(("path:1",), ("in_handler",), ("fact:put",)),
            "registration_facts": (RegistrationFact("spring_mvc", "excerpt:1"),), "config_facts": (),
        }
        values.update(overrides)
        return BoundedSlicePayload(**values)

    def test_payload_accepts_only_explicit_bounded_fields(self) -> None:
        slice_ = BoundedSlice("slice:fixture", self._payload())
        self.assertEqual(slice_.entry_id, "entry:fixture")

    def test_payload_rejects_absolute_parent_and_oversized_excerpts(self) -> None:
        for path in ("/etc/passwd", "src/../private.txt"):
            with self.subTest(path=path):
                with self.assertRaises(AnalyzerError):
                    SourceExcerpt("excerpt:1", path, 1, 1, "x", "a" * 64, hashlib.sha256(b"x").hexdigest())
        oversized = "x" * 16385
        with self.assertRaises(AnalyzerError):
            SourceExcerpt("excerpt:1", "src/Fixture.java", 1, 1, oversized, "a" * 64, hashlib.sha256(oversized.encode()).hexdigest())

    def test_excerpt_rejects_empty_or_reversed_line_ranges(self) -> None:
        digest = hashlib.sha256(b"x").hexdigest()
        for start, end in ((0, 1), (2, 1)):
            with self.subTest(start=start, end=end):
                with self.assertRaises(AnalyzerError):
                    SourceExcerpt("excerpt:1", "src/Fixture.java", start, end, "x", "a" * 64, digest)
        with self.assertRaises(AnalyzerError):
            SourceExcerpt("excerpt:1", "src/Fixture.java", 1, 1, "", "a" * 64, hashlib.sha256(b"").hexdigest())

    def test_payload_rejects_untyped_facts_and_dangling_locations(self) -> None:
        with self.assertRaises(AnalyzerError):
            self._payload(static_facts=({"environment": "private"},))
        with self.assertRaises(AnalyzerError):
            self._payload(static_facts=(StaticFact("fact:put", "container_write", "excerpt:missing", "sink"),))

    def test_payload_rejects_each_collection_and_aggregate_serialization_limits(self) -> None:
        excerpt = self._payload().source_excerpts[0]
        fact = StaticFact("fact:put", "container_write", "excerpt:1", "sink")
        registration = RegistrationFact("spring_mvc", "excerpt:1")
        config = __import__("dosweb.growth.models", fromlist=["ConfigFact"]).ConfigFact("request_limit", "finite", "excerpt:1")
        cases = (
            {"source_excerpts": (excerpt,) * 65},
            {"static_facts": (fact,) * 257},
            {"registration_facts": (registration,) * 65},
            {"config_facts": (config,) * 65},
            {"source_excerpts": (excerpt,) * 64, "static_facts": (fact,) * 256, "registration_facts": (registration,) * 64, "config_facts": (config,) * 64},
        )
        for changes in cases:
            with self.subTest(changes=changes.keys()):
                with self.assertRaises(AnalyzerError) as raised:
                    self._payload(**changes)
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")

    def test_byte_limits_reject_hostile_strings_before_full_encoding(self) -> None:
        class ObservedString(str):
            encode_calls: list[int] = []
            def encode(self, *args: object, **kwargs: object) -> bytes:
                self.encode_calls.append(len(self))
                return super().encode(*args, **kwargs)

        content = "x"
        digest = hashlib.sha256(content.encode()).hexdigest()
        hostile_path = ObservedString("a" * 1000000)
        with self.assertRaises(AnalyzerError) as raised:
            SourceExcerpt("excerpt:1", hostile_path, 1, 1, content, "a" * 64, digest)
        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")
        self.assertEqual(hostile_path.encode_calls, [])

    def test_multibyte_utf8_limits_remain_byte_exact(self) -> None:
        content = "é" * 8192
        SourceExcerpt("excerpt:1", "src/Fixture.java", 1, 1, content, "a" * 64, hashlib.sha256(content.encode()).hexdigest())
        oversized = content + "é"
        with self.assertRaises(AnalyzerError) as raised:
            SourceExcerpt("excerpt:1", "src/Fixture.java", 1, 1, oversized, "a" * 64, hashlib.sha256(oversized.encode()).hexdigest())
        self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")

    def test_line_numbers_have_explicit_integer_bounds(self) -> None:
        content = "x"
        digest = hashlib.sha256(content.encode()).hexdigest()
        for start, end in ((10**20, 10**20), (1, 10**20)):
            with self.subTest(start=start, end=end):
                with self.assertRaises(AnalyzerError) as raised:
                    SourceExcerpt("excerpt:1", "src/Fixture.java", start, end, content, "a" * 64, digest)
                self.assertEqual(raised.exception.code, "LLM_BOUNDED_SLICE_INVALID")

    def test_payload_rejects_oversized_ids_and_paths(self) -> None:
        content = "x"
        digest = hashlib.sha256(content.encode()).hexdigest()
        with self.assertRaises(AnalyzerError):
            SourceExcerpt("excerpt:" + "x" * 249, "src/Fixture.java", 1, 1, content, "a" * 64, digest)
        with self.assertRaises(AnalyzerError):
            SourceExcerpt("excerpt:1", "a" * 513, 1, 1, content, "a" * 64, digest)


if __name__ == "__main__":
    unittest.main()
