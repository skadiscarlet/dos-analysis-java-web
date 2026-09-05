from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from dosweb.growth.excerpts import extract_source_excerpt
from dosweb.growth.redaction import REDACTED_TOKEN, redact_source_content
from dosweb.llm.deepseek import _sensitive_java_assignment, _sensitive_method_call


class RedactionTests(unittest.TestCase):
    def test_assignment_value_is_redacted_without_losing_line_structure(self):
        content = "String password = \"s3cr3t\";\nint token = 42;\n"
        out, events = redact_source_content(content, 20)
        self.assertNotIn("s3cr3t", out)
        self.assertIn("password = [REDACTED]", out)
        self.assertIn("token = [REDACTED]", out)
        self.assertEqual(out.count("\n"), content.count("\n"))
        self.assertEqual({e["pattern_id"] for e in events}, {"credential_assignment"})
        self.assertEqual([e["line"] for e in events], [20, 21])

    def test_mutator_and_header_arguments_are_redacted(self):
        content = (
            "config.setPassword(\"pw123\");\n"
            'req.header("Authorization", "Bearer abc");\n'
        )
        out, events = redact_source_content(content, 5)
        self.assertNotIn("pw123", out)
        self.assertNotIn("Bearer abc", out)
        self.assertIn("setPassword([REDACTED])", out)
        self.assertIn('header("Authorization",[REDACTED])', out)
        self.assertEqual({e["pattern_id"] for e in events}, {"credential_mutator", "credential_header"})

    def test_string_literal_mentioning_token_is_not_corrupted(self):
        content = 'logger.info("token = foo");\n'
        out, events = redact_source_content(content, 1)
        self.assertEqual(out, content)
        self.assertEqual(events, ())

    def test_nonsecret_code_is_untouched(self):
        content = "int nonsecret = 5;\nString url = \"https://user:pass@host\";\n"
        out, events = redact_source_content(content, 1)
        self.assertEqual(out, content)
        self.assertEqual(events, ())

    def test_excerpt_redacts_and_records_original_and_transmitted_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Example.java"
            source.write_text(
                "class Example {\n  String password = \"s3cr3t\";\n  int limit = 8;\n}\n",
                encoding="utf-8",
            )
            excerpt = extract_source_excerpt(root, None, "Example.java", 2, context_lines=1)
            self.assertNotIn("s3cr3t", excerpt.content)
            self.assertIn(REDACTED_TOKEN, excerpt.content)
            self.assertTrue(excerpt.redaction_events)
            self.assertEqual(excerpt.redaction_events[0]["line"], 2)
            self.assertNotEqual(excerpt.original_excerpt_sha256, excerpt.excerpt_sha256)
            expected_original = hashlib.sha256(
                "class Example {\n  String password = \"s3cr3t\";\n  int limit = 8;\n".encode()
            ).hexdigest()
            self.assertEqual(excerpt.original_excerpt_sha256, expected_original)

    def test_excerpt_without_secrets_has_equal_hashes_and_no_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Example.java"
            source.write_text("class Example {\n  int limit = 8;\n}\n", encoding="utf-8")
            excerpt = extract_source_excerpt(root, None, "Example.java", 2, context_lines=1)
            self.assertEqual(excerpt.redaction_events, ())
            self.assertEqual(excerpt.original_excerpt_sha256, excerpt.excerpt_sha256)
            self.assertNotIn(REDACTED_TOKEN, excerpt.content)


class CredentialScannerRedactionAwarenessTests(unittest.TestCase):
    def test_redacted_assignment_is_not_flagged_but_real_secret_is(self):
        self.assertFalse(_sensitive_java_assignment("String password = [REDACTED];"))
        self.assertTrue(_sensitive_java_assignment('String password = "s3cr3t";'))

    def test_redacted_method_call_is_not_flagged_but_real_value_is(self):
        self.assertFalse(_sensitive_method_call("config.setPassword([REDACTED]);"))
        self.assertTrue(_sensitive_method_call('config.setPassword("pw123");'))

    def test_redacted_header_is_not_flagged_but_real_bearer_is(self):
        self.assertFalse(_sensitive_method_call('req.header("Authorization",[REDACTED]);'))
        self.assertTrue(_sensitive_method_call('req.header("Authorization", "Bearer abc");'))


if __name__ == "__main__":
    unittest.main()
