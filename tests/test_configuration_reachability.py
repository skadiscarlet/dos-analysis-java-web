from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from dosweb.configuration import extract_modeled_configuration, extract_modeled_configuration_with_coverage
from dosweb.errors import AnalyzerError
from dosweb.reachability.models import AuthContract, EntrySecurityFact, LlmAuditRecord
from dosweb.reachability.audit import publish_private_audit
from dosweb.reachability.verify import verify_auth_contract
from dosweb.production import _extract_entry_security_facts


class ConfigurationExtractionTests(unittest.TestCase):
    def test_properties_duplicate_placeholder_and_cli_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "application.properties").write_text("cap=10\nrequest.name=${NAME}\ncap=11\n")
            items = {x["key"]: x for x in extract_modeled_configuration(root, {"cap": 42})}
            self.assertEqual(42, items["cap"]["value"])
            self.assertEqual("cli_override", items["cap"]["provenance"])
            self.assertEqual("unknown", items["request.name"]["status"])

    def test_sensitive_and_irrelevant_application_values_are_never_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "application.properties").write_text(
                "spring.datasource.password=super-secret\n"
                "service.api-key=token-value\n"
                "business.name=customer-private-name\n"
                "request.max-bytes=1024\n"
                "auth.mode=opaque-business-secret\n",
                encoding="utf-8",
            )
            records = extract_modeled_configuration(root)
            rendered = repr(records)
            self.assertNotIn("super-secret", rendered)
            self.assertNotIn("token-value", rendered)
            self.assertNotIn("customer-private-name", rendered)
            self.assertNotIn("opaque-business-secret", rendered)
            by_key = {item["key"]: item for item in records}
            self.assertEqual(1024, by_key["request.max-bytes"]["value"])
            self.assertEqual("unknown", by_key["auth.mode"]["status"])

    def test_yaml_alias_is_rejected_without_recursive_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "application.yml").write_text("tree: &tree\n  child: *tree\n", encoding="utf-8")
            records = extract_modeled_configuration(root)
            self.assertEqual("unknown", {item["key"]: item for item in records}["yaml_parse"]["status"])

    def test_yaml_and_symlink_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "application.yaml").write_text("server:\n  limit: 12\n")
            self.assertEqual(12, {x["key"]: x for x in extract_modeled_configuration(root)}["server.limit"]["value"])
            target = root / "target.properties"; target.write_text("x=1")
            (root / "application.properties").symlink_to(target)
            with self.assertRaises(AnalyzerError): extract_modeled_configuration(root)

    def test_prunes_excluded_directories_and_reports_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src/main/resources").mkdir(parents=True)
            (root / "node_modules/pkg").mkdir(parents=True)
            (root / "build").mkdir(parents=True)
            (root / "src/main/resources/application.properties").write_text("request.max-bytes=2048\n")
            (root / "node_modules/pkg/application.properties").write_text("spring.datasource.password=leak\n")
            (root / "build/application.properties").write_text("server.limit=999999\n")
            records, coverage = extract_modeled_configuration_with_coverage(root)
            by_key = {item["key"]: item for item in records}
            self.assertIn("request.max-bytes", by_key)
            self.assertNotIn("server.limit", by_key)
            rendered = repr(records)
            self.assertNotIn("leak", rendered)
            self.assertGreaterEqual(coverage["pruned_directory_entries"], 2)
            self.assertEqual(1, coverage["config_files_read"])
            self.assertFalse(coverage["truncated"])
            pruned_paths = {item["path"] for item in coverage["pruned_directories"]}
            self.assertIn("node_modules", pruned_paths)
            self.assertIn("build", pruned_paths)

    def test_out_of_scope_config_files_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir(parents=True)
            (root / "docs/application.properties").write_text("request.max-bytes=4096\n")
            records, coverage = extract_modeled_configuration_with_coverage(root)
            self.assertEqual([], records)
            self.assertEqual(1, coverage["config_files_skipped_out_of_scope"])
            self.assertEqual(0, coverage["config_files_read"])

    def test_deep_excluded_tree_does_not_exhaust_visited_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "application.properties").write_text("request.max-bytes=1\n")
            deep = root / "node_modules"
            for i in range(300):
                deep = deep / f"d{i}"
            deep.mkdir(parents=True)
            (deep / "application.properties").write_text("server.limit=1\n")
            records, coverage = extract_modeled_configuration_with_coverage(root)
            self.assertIn("request.max-bytes", {item["key"] for item in records})
            self.assertGreaterEqual(coverage["pruned_directory_entries"], 1)


class EntrySecurityExtractionTests(unittest.TestCase):
    def test_explicit_annotations_are_classified_without_inferring_from_absence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Handlers.java"
            source.write_text(
                "@PermitAll\nvoid publicHandler() {}\n"
                "@PreAuthorize(\"permitAll()\")\nvoid explicitPublic() {}\n"
                "@PreAuthorize(\"isAuthenticated()\")\nvoid userHandler() {}\n"
                "@RolesAllowed(\"admin\")\nvoid adminHandler() {}\n"
                "void unknownHandler() {}\n",
                encoding="utf-8",
            )
            entries = [
                {
                    "entry_id": f"entry:{name}",
                    "handler": {"file": source.name, "start_line": line},
                    "auth_context": "unknown",
                }
                for name, line in (
                    ("public", 2), ("permit", 4), ("user", 6),
                    ("admin", 8), ("unknown", 9),
                )
            ]
            facts = {item["entry_id"]: item for item in _extract_entry_security_facts(entries, root)}
            self.assertEqual("unauthenticated_annotation", facts["entry:public"]["value"])
            self.assertEqual("unauthenticated_annotation", facts["entry:permit"]["value"])
            self.assertEqual("low_privilege_annotation", facts["entry:user"]["value"])
            self.assertEqual("privileged_annotation", facts["entry:admin"]["value"])
            self.assertEqual("partial", facts["entry:unknown"]["coverage"])


class ReachabilityContractTests(unittest.TestCase):
    def _fact(self, coverage: str = "complete", value: str = "privileged_annotation") -> EntrySecurityFact:
        return EntrySecurityFact("entry:test", "annotation", "A.java", 1, value, coverage)  # type: ignore[arg-type]

    def test_text_cannot_create_unauthenticated_without_complete_fact(self) -> None:
        fact = self._fact("partial")
        decision = verify_auth_contract("entry:test", AuthContract("unauthenticated", (fact.fact_id,), (), "high"), [fact], slice_fact_ids=frozenset({fact.fact_id}))
        self.assertEqual("unknown", decision.auth_context)

    def test_privileged_and_outside_slice(self) -> None:
        fact = self._fact()
        decision = verify_auth_contract("entry:test", AuthContract("privileged", (fact.fact_id,), (), "high"), [fact], slice_fact_ids=frozenset({fact.fact_id}))
        self.assertEqual("not_entry_reachable", decision.status)
        self.assertEqual("unknown", verify_auth_contract("entry:test", AuthContract("unauthenticated", (fact.fact_id,), (), "high"), [fact], slice_fact_ids=frozenset({fact.fact_id})).auth_context)
        with self.assertRaises(AnalyzerError):
            verify_auth_contract("entry:test", AuthContract("low_privilege", (fact.fact_id,), (), "high"), [fact], slice_fact_ids=frozenset())

    def test_audit_is_deterministic_and_bounded(self) -> None:
        audit = LlmAuditRecord("auth", "", '{"x":1}', {"type":"object"}, '{"auth_context":"unknown"}', {"auth_context":"unknown"}, {"model":"test"}, {"verified_public":True}, False)
        self.assertTrue(audit.audit_id.startswith("llm_audit:"))
        self.assertEqual('{"auth_context":"unknown"}', audit.to_dict()["raw_response"])
        with self.assertRaises(AnalyzerError):
            LlmAuditRecord("auth", "", "x" * 140000, {}, "", {}, {}, {}, False)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "audit.jsonl"
            publish_private_audit(path, [audit])
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
            self.assertNotIn("Authorization", path.read_text())


if __name__ == "__main__": unittest.main()
