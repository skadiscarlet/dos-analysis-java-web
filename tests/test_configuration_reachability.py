from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from dosweb.configuration import extract_modeled_configuration, extract_modeled_configuration_with_coverage
from dosweb.errors import AnalyzerError
from dosweb.reachability.models import AuthContract, EntrySecurityFact, LlmAuditRecord
from dosweb.reachability.extract import (
    bind_entry_security_rows,
    extract_entry_deployment_defaults,
    resolve_deployment_status,
)
from dosweb.reachability.audit import publish_private_audit
from dosweb.reachability.verify import verify_auth_contract
from dosweb.production import _extract_entry_security_facts


class ConfigurationExtractionTests(unittest.TestCase):
    def test_default_profile_and_feature_gate_values_are_modeled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "application.properties").write_text(
                "spring.profiles.active=prod,api\n"
                "feature.upload.enabled=false\n"
                "optional.module.enabled=true\n",
                encoding="utf-8",
            )

            by_key = {item["key"]: item for item in extract_modeled_configuration(root)}

        self.assertEqual("prod,api", by_key["spring.profiles.active"]["value"])
        self.assertFalse(by_key["feature.upload.enabled"]["value"])
        self.assertTrue(by_key["optional.module.enabled"]["value"])

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
    def test_complete_registration_is_positive_default_evidence_but_explicit_gate_wins(self) -> None:
        entries = [{
            "entry_id": "entry:public",
            "registration": {
                "kind": "annotation_mapping",
                "callable": "fixture.Controller",
                "file": "src/Controller.java",
                "start_line": 10,
            },
        }]

        defaults = extract_entry_deployment_defaults(entries)
        replaced = extract_entry_deployment_defaults(
            entries,
            excluded_entry_ids=frozenset({"entry:public"}),
        )

        self.assertEqual(1, len(defaults))
        self.assertEqual("deployment_gate", defaults[0].kind)
        self.assertEqual("default_enabled", defaults[0].value)
        self.assertEqual("complete", defaults[0].coverage)
        self.assertEqual("src/Controller.java", defaults[0].location)
        self.assertEqual((), replaced)

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
            self.assertTrue(all(item["coverage"] == "partial" for item in facts.values()))

    def test_codeql_security_rows_bind_only_to_a_unique_normalized_entry(self) -> None:
        entries = [
            {
                "entry_id": "entry:public",
                "handler": {"callable": "fixture.Controller.publicHandler", "file": "src/Controller.java", "start_line": 20},
                "route_or_event": "GET /public",
            },
            {
                "entry_id": "entry:admin",
                "handler": {"callable": "fixture.Controller.adminHandler", "file": "src/Controller.java", "start_line": 30},
                "route_or_event": "GET /admin",
            },
        ]
        rows = [
            {
                "handler_fqn": "fixture.Controller.publicHandler",
                "handler_file": "src/Controller.java",
                "handler_start_line": 20,
                "route_or_event": "GET /public",
                "fact_file": "src/Controller.java",
                "fact_start_line": 19,
                "kind": "annotation",
                "value": "unauthenticated_annotation",
                "coverage_status": "complete",
                "coverage_note": "permit_all",
            },
            {
                "handler_fqn": "fixture.Security.securityFilterChain",
                "handler_file": "src/Security.java",
                "handler_start_line": 10,
                "route_or_event": "/admin",
                "fact_file": "src/Security.java",
                "fact_start_line": 12,
                "kind": "security_filter_chain",
                "value": "privileged_filter",
                "coverage_status": "complete",
                "coverage_note": "static_request_matcher_has_role",
            },
            {
                "handler_fqn": "fixture.Security.securityFilterChain",
                "handler_file": "src/Security.java",
                "handler_start_line": 10,
                "route_or_event": "dynamic_matcher",
                "fact_file": "src/Security.java",
                "fact_start_line": 13,
                "kind": "security_filter_chain",
                "value": "security_matcher_unknown",
                "coverage_status": "partial",
                "coverage_note": "dynamic_matcher",
            },
        ]

        facts = bind_entry_security_rows(rows, entries)

        self.assertEqual(
            {("entry:public", "unauthenticated_annotation"), ("entry:admin", "privileged_filter")},
            {(fact.entry_id, fact.value) for fact in facts},
        )

    def test_deployment_resolution_handles_profile_optional_and_unknown(self) -> None:
        enabled = EntrySecurityFact("entry:test", "deployment_gate", "A.java", 1, "default_enabled", "complete")
        disabled = EntrySecurityFact("entry:test", "deployment_gate", "A.java", 2, "default_disabled", "complete")
        optional = EntrySecurityFact("entry:test", "deployment_gate", "A.java", 3, "optional", "complete")
        dynamic = EntrySecurityFact("entry:test", "deployment_gate", "A.java", 4, "dynamic_matcher", "partial")
        self.assertEqual("default_enabled", resolve_deployment_status([enabled], ()))
        self.assertEqual("default_disabled", resolve_deployment_status([disabled], ()))
        self.assertEqual("optional", resolve_deployment_status([optional], ()))
        self.assertEqual("unknown", resolve_deployment_status([dynamic], ()))
        self.assertEqual("unknown", resolve_deployment_status([], ()))


class ReachabilityContractTests(unittest.TestCase):
    def _fact(self, coverage: str = "complete", value: str = "privileged_annotation", kind: str = "annotation") -> EntrySecurityFact:
        return EntrySecurityFact("entry:test", kind, "A.java", 1, value, coverage)  # type: ignore[arg-type]

    def _decision(self, context: str, value: str, deployment: str = "default_enabled"):
        auth = self._fact(value=value)
        gate = self._fact(value=deployment, kind="deployment_gate")
        return verify_auth_contract(
            "entry:test",
            AuthContract(context, (auth.fact_id,), (), "high"),  # type: ignore[arg-type]
            [auth, gate],
            slice_fact_ids=frozenset({auth.fact_id, gate.fact_id}),
        )

    def test_complete_public_and_low_privilege_default_entries_are_reachable(self) -> None:
        public = self._decision("unauthenticated", "unauthenticated_annotation")
        user = self._decision("low_privilege", "low_privilege_filter")
        self.assertEqual("ordinary_attacker_reachable", public.status)
        self.assertEqual("default_enabled", public.deployment_status)
        self.assertEqual("ordinary_attacker_reachable", user.status)
        self.assertIn("REACH_ORDINARY_ATTACKER", public.reason_codes)

    def test_admin_disabled_and_optional_entries_are_not_reachable(self) -> None:
        admin = self._decision("privileged", "privileged_constraint")
        disabled = self._decision("unauthenticated", "unauthenticated_filter", "default_disabled")
        optional = self._decision("unauthenticated", "unauthenticated_filter", "optional")
        self.assertEqual("not_entry_reachable", admin.status)
        self.assertIn("REACH_PRIVILEGED", admin.reason_codes)
        self.assertEqual("not_entry_reachable", disabled.status)
        self.assertIn("REACH_DEFAULT_DISABLED", disabled.reason_codes)
        self.assertEqual("not_entry_reachable", optional.status)
        self.assertIn("REACH_OPTIONAL_COMPONENT", optional.reason_codes)

    def test_dynamic_matcher_and_missing_deployment_stay_unknown(self) -> None:
        auth = self._fact("partial", "security_matcher_unknown", "security_filter_chain")
        gate = self._fact(value="default_enabled", kind="deployment_gate")
        dynamic = verify_auth_contract(
            "entry:test",
            AuthContract("unauthenticated", (auth.fact_id,), (), "high"),
            [auth, gate],
            slice_fact_ids=frozenset({auth.fact_id, gate.fact_id}),
        )
        public = self._fact(value="unauthenticated_annotation")
        missing_gate = verify_auth_contract(
            "entry:test",
            AuthContract("unauthenticated", (public.fact_id,), (), "high"),
            [public],
            slice_fact_ids=frozenset({public.fact_id}),
        )
        self.assertEqual("unknown", dynamic.status)
        self.assertEqual("unknown", missing_gate.deployment_status)
        self.assertEqual("unknown", missing_gate.status)

    def test_text_cannot_create_unauthenticated_without_complete_fact(self) -> None:
        fact = self._fact("partial")
        gate = self._fact(value="default_enabled", kind="deployment_gate")
        decision = verify_auth_contract("entry:test", AuthContract("unauthenticated", (fact.fact_id,), (), "high"), [fact, gate], slice_fact_ids=frozenset({fact.fact_id, gate.fact_id}))
        self.assertEqual("unknown", decision.auth_context)

    def test_privileged_and_outside_slice(self) -> None:
        fact = self._fact()
        gate = self._fact(value="default_enabled", kind="deployment_gate")
        decision = verify_auth_contract("entry:test", AuthContract("privileged", (fact.fact_id,), (), "high"), [fact, gate], slice_fact_ids=frozenset({fact.fact_id, gate.fact_id}))
        self.assertEqual("not_entry_reachable", decision.status)
        self.assertEqual("unknown", verify_auth_contract("entry:test", AuthContract("unauthenticated", (fact.fact_id,), (), "high"), [fact, gate], slice_fact_ids=frozenset({fact.fact_id, gate.fact_id})).auth_context)
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
