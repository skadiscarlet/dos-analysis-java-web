from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

import dosweb.entries.webxml as webxml
from pathlib import Path

from dosweb.entries import normalize_entry_rows, normalize_framework_coverage, normalize_gap_entry_rows
from dosweb.entries.webxml import resolve_webxml_servlet_candidates, validate_descriptor_coverage


class WebXmlServletEntryTests(unittest.TestCase):
    def _candidate(self, **overrides: object) -> dict[str, object]:
        row: dict[str, object] = {
            "framework": "servlet", "protocol": "http", "handler_fqn": "example.DeployedServlet.service",
            "handler_file": "src/example/DeployedServlet.java", "handler_start_line": 10,
            "registration_kind": "dynamic_unresolved", "registration_fqn": "example.DeployedServlet.service",
            "registration_file": "src/example/DeployedServlet.java", "registration_start_line": 10,
            "route_or_event": "web_xml_servlet_mapping", "auth_context": "unknown", "attacker_input_name": "request",
            "attacker_input_type": "HttpServletRequest", "attacker_input_kind": "stream", "materialization_phase": "unknown",
            "coverage_status": "partial", "coverage_note": "web_xml_servlet_mapping_requires_descriptor_binding",
            "query_name": "entries", "query_sha256": "a" * 64,
            "handler_location": {"file": "src/example/DeployedServlet.java", "start_line": 10},
            "registration_location": {"file": "src/example/DeployedServlet.java", "start_line": 10},
        }
        row.update(overrides)
        return row

    def _webxml(self, root: Path, content: bytes) -> Path:
        path = root / "app" / "WEB-INF" / "web.xml"; path.parent.mkdir(parents=True)
        path.write_bytes(content)
        return path

    def test_exact_class_mapping_promotes_each_pattern_without_candidate_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._webxml(root, b"""<web-app><servlet><servlet-name>x</servlet-name><servlet-class>example.DeployedServlet</servlet-class></servlet><servlet-mapping><servlet-name>x</servlet-name><url-pattern>/*</url-pattern></servlet-mapping><servlet-mapping><servlet-name>x</servlet-name><url-pattern>/api/*</url-pattern></servlet-mapping></web-app>""")
            rows, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
            entries = normalize_entry_rows(rows)
            self.assertEqual({item["route_or_event"] for item in entries}, {"/*", "/api/*"})
            self.assertTrue(all(item["registration"]["kind"] == "static_registration" for item in entries))
            self.assertTrue(all(item["registration"]["callable"] == "web.xml:x" for item in entries))
            self.assertEqual(coverage["diagnostics"], [])
            self.assertEqual((coverage["candidate_count"], coverage["complete_candidate_count"], coverage["partial_candidate_count"]), (1, 1, 0))
            self.assertFalse(any(row["coverage_note"] == "web_xml_servlet_mapping_requires_descriptor_binding" for row in rows))

    def test_namespace_and_unmatched_candidate_stay_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._webxml(root, b"""<web-app xmlns=\"https://jakarta.ee/xml/ns/jakartaee\"><servlet><servlet-name>x</servlet-name><servlet-class>example.OtherServlet</servlet-class></servlet><servlet-mapping><servlet-name>x</servlet-name><url-pattern>/x/*</url-pattern></servlet-mapping></web-app>""")
            rows, _ = resolve_webxml_servlet_candidates([self._candidate()], root)
            self.assertEqual(normalize_entry_rows(rows), [])
            self.assertEqual(normalize_gap_entry_rows(rows), [])
            self.assertEqual(normalize_framework_coverage(rows)[4]["status"], "partial")

    def test_malformed_dtd_invalid_utf8_and_symlink_are_partial(self) -> None:
        for payload in (b"<web-app>", b"<!DOCTYPE x [<!ENTITY e 'x'>]><web-app/>", b"\xff"):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self._webxml(root, payload)
                rows, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
                self.assertEqual(normalize_entry_rows(rows), [])
                self.assertTrue(coverage["diagnostics"])
        if hasattr(os, "symlink"):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); outside = root / "outside.xml"; outside.write_text("<web-app/>")
                target = root / "app" / "WEB-INF"; target.mkdir(parents=True)
                os.symlink(outside, target / "web.xml")
                rows, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
                self.assertEqual(normalize_entry_rows(rows), [])
                self.assertTrue(coverage["diagnostics"])

    def test_conflicting_or_undefined_mapping_never_promotes(self) -> None:
        cases = (
            b"<web-app><servlet><servlet-name>x</servlet-name><servlet-class>example.DeployedServlet</servlet-class></servlet><servlet><servlet-name>x</servlet-name><servlet-class>example.OtherServlet</servlet-class></servlet><servlet-mapping><servlet-name>x</servlet-name><url-pattern>/x</url-pattern></servlet-mapping></web-app>",
            b"<web-app><servlet-mapping><servlet-name>missing</servlet-name><url-pattern>/x</url-pattern></servlet-mapping></web-app>",
        )
        for payload in cases:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self._webxml(root, payload)
                rows, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
                self.assertEqual(normalize_entry_rows(rows), [])
                self.assertTrue(coverage["diagnostics"])

    def test_duplicate_same_class_and_cross_descriptor_selection_are_partial(self) -> None:
        duplicate = b"<web-app><servlet><servlet-name>x</servlet-name><servlet-class>example.DeployedServlet</servlet-class></servlet><servlet><servlet-name>x</servlet-name><servlet-class>example.DeployedServlet</servlet-class></servlet><servlet-mapping><servlet-name>x</servlet-name><url-pattern>/x</url-pattern></servlet-mapping></web-app>"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._webxml(root, duplicate)
            rows, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
            self.assertEqual(normalize_entry_rows(rows), [])
            self.assertTrue(coverage["diagnostics"])
        document = b"<web-app><servlet><servlet-name>x</servlet-name><servlet-class>example.DeployedServlet</servlet-class></servlet><servlet-mapping><servlet-name>x</servlet-name><url-pattern>/x</url-pattern></servlet-mapping></web-app>"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._webxml(root, document)
            second = root / "other" / "WEB-INF" / "web.xml"; second.parent.mkdir(parents=True)
            second.write_bytes(b"<web-app><servlet><servlet-name>x</servlet-name><servlet-class>example.DeployedServlet</servlet-class></servlet></web-app>")
            rows, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
            self.assertEqual(normalize_entry_rows(rows), [])
            self.assertEqual(coverage["partial_candidate_count"], 1)
            self.assertTrue(any(row["coverage_note"] == "web_xml_descriptor_selection_ambiguous" for row in rows))

    def test_file_and_byte_limits_and_parent_symlink_are_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for number in range(65):
                path = root / f"app{number}" / "WEB-INF" / "web.xml"; path.parent.mkdir(parents=True); path.write_text("<web-app/>")
            _, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
            self.assertTrue(any(item["reason"] == "web_xml_file_limit" for item in coverage["diagnostics"]))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._webxml(root, b"x" * (256 * 1024 + 1))
            _, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
            self.assertTrue(coverage["diagnostics"])
        if hasattr(os, "symlink"):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); outside = root / "outside"; (outside / "WEB-INF").mkdir(parents=True); (outside / "WEB-INF" / "web.xml").write_text("<web-app/>")
                os.symlink(outside, root / "linked")
                _, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
                self.assertTrue(any(item["reason"] == "web_xml_parent_symlink" for item in coverage["diagnostics"]))

    def test_incremental_single_directory_tree_limit_stops_scandir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for number in range(8): (root / f"file{number}").write_text("x")
            calls = 0
            original = os.scandir
            def counted(path: object):
                nonlocal calls
                iterator = original(path)
                class Wrapped:
                    def __enter__(self): return self
                    def __exit__(self, *args: object): iterator.close()
                    def __iter__(self): return self
                    def __next__(self):
                        nonlocal calls
                        calls += 1
                        return next(iterator)
                return Wrapped()
            with mock.patch.object(webxml, "_MAX_VISITED", 3), mock.patch.object(webxml.os, "scandir", side_effect=counted):
                _, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
            self.assertEqual(calls, 4)
            self.assertTrue(any(item["reason"] == "web_xml_tree_limit" for item in coverage["diagnostics"]))

    def test_real_solr_source_descriptor_integration(self) -> None:
        root = Path(__file__).parents[1] / "frameworks" / "applications" / "apache__solr"
        if not root.is_dir(): self.skipTest("Solr source checkout unavailable")
        candidate = self._candidate(handler_fqn="org.apache.solr.servlet.SolrServlet.service", handler_file="solr/core/src/java/org/apache/solr/servlet/SolrServlet.java", handler_start_line=80, registration_fqn="org.apache.solr.servlet.SolrServlet.service", registration_file="solr/core/src/java/org/apache/solr/servlet/SolrServlet.java", registration_start_line=80)
        rows, coverage = resolve_webxml_servlet_candidates([candidate], root)
        hit = next(item for item in normalize_entry_rows(rows) if item["handler"]["callable"] == candidate["handler_fqn"])
        self.assertEqual(hit["route_or_event"], "/*")
        self.assertEqual(hit["registration"]["kind"], "static_registration")
        self.assertEqual(hit["auth_context"], "unknown")
        self.assertEqual((coverage["candidate_count"], coverage["complete_candidate_count"], coverage["partial_candidate_count"]), (1, 1, 0))

    def test_coverage_schema_is_stable_and_diagnostics_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self._webxml(root, b"<web-app/>")
            _, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
            self.assertEqual(set(coverage), {"schema_version", "discovered_count", "parsed_count", "mapped_descriptor_count", "candidate_count", "complete_candidate_count", "partial_candidate_count", "diagnostics"})
            validate_descriptor_coverage(coverage)
            with self.assertRaises(Exception):
                validate_descriptor_coverage({**coverage, "candidate_count": -1})
            with self.assertRaises(Exception):
                validate_descriptor_coverage({**coverage, "diagnostics": [{"reason": "uncontrolled", "file": "", "line": 1}]})

    def test_element_and_depth_limits_are_partial(self) -> None:
        payloads = (
            b"<web-app>" + b"<x/>" * 513 + b"</web-app>",
            b"<web-app>" + b"<x>" * 33 + b"</x>" * 33 + b"</web-app>",
        )
        for payload in payloads:
            with self.subTest(payload=payload[:32]), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self._webxml(root, payload)
                rows, coverage = resolve_webxml_servlet_candidates([self._candidate()], root)
                self.assertEqual(normalize_entry_rows(rows), [])
                self.assertTrue(coverage["diagnostics"])


if __name__ == "__main__":
    unittest.main()
