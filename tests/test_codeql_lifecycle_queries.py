from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from dosweb.artifacts.identifiers import file_sha256
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query, validate_database
from dosweb.codeql.decoder import BOUND_COLUMNS, FLOW_COLUMNS, GUARD_COLUMNS, LIFECYCLE_COVERAGE_COLUMNS, LIFECYCLE_SUMMARY_COLUMNS, RELEASE_COLUMNS
from tests.test_codeql_entry_queries import _codeql_wrapper

_ROOT = Path(__file__).resolve().parents[1]
_RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql")
_JAVAC = shutil.which("javac")


class CodeqlLifecycleQueryContractTests(unittest.TestCase):
    def test_embedded_and_direct_pack_match_for_lifecycle_and_loop_growth(self) -> None:
        embedded = _ROOT / "dosweb" / "codeql" / "pack" / "dosweb"
        direct = _ROOT / "codeql" / "dosweb"
        relatives = (
            "Entries/EntrySecurity.ql",
            "Entries/EntryInterpositions.ql",
            "Flows/EntryGrowthDomain.qll", "Flows/EntryToGrowth.ql",
            "Flows/EntryToGrowthAssociations.ql",
            "Lifecycle/GuardCandidates.ql", "Lifecycle/BoundCandidates.ql",
            "Lifecycle/FrameworkLimitDomain.qll",
            "Lifecycle/SynchronousReleaseCandidates.ql", "Lifecycle/LifecycleCoverage.ql",
            "Lifecycle/LifecycleSummary.ql", "Growth/LoopAmplification.qll",
            "Growth/ContainerGrowth.ql", "Growth/AsyncWorkGrowth.ql",
        )
        for relative in relatives:
            with self.subTest(query=relative):
                self.assertEqual((embedded / relative).read_bytes(), (direct / relative).read_bytes())

    def test_queries_use_exact_candidate_only_contracts(self) -> None:
        queries = (
            ("codeql/dosweb/Flows/EntryToGrowth.ql", FLOW_COLUMNS),
            ("codeql/dosweb/Flows/EntryToGrowthAssociations.ql", FLOW_COLUMNS),
            ("codeql/dosweb/Lifecycle/GuardCandidates.ql", GUARD_COLUMNS),
            ("codeql/dosweb/Lifecycle/BoundCandidates.ql", BOUND_COLUMNS),
            ("codeql/dosweb/Lifecycle/SynchronousReleaseCandidates.ql", RELEASE_COLUMNS),
            ("codeql/dosweb/Lifecycle/LifecycleCoverage.ql", LIFECYCLE_COVERAGE_COLUMNS),
            ("codeql/dosweb/Lifecycle/LifecycleSummary.ql", LIFECYCLE_SUMMARY_COLUMNS),
        )
        forbidden = ("static_vulnerable", "bounded_under_modeled_assumptions", "static_unknown", "assertion", "verdict", "lifecycle_result")
        for relative, columns in queries:
            with self.subTest(query=relative):
                content = (_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("@kind table", content)
                self.assertIn("import java", content)
                positions = [
                    content.index(f"as {column}")
                    if f"as {column}" in content
                    else content.rindex("confidence,")
                    if column == "confidence"
                    else -1
                    for column in columns
                ]
                self.assertNotIn(-1, positions)
                self.assertEqual(positions, sorted(positions))
                for term in forbidden:
                    self.assertNotIn(term, content.lower())

    def test_flow_and_lifecycle_queries_share_growth_and_handler_domains(self) -> None:
        shared_domain = (
            _ROOT / "codeql/dosweb/Flows/EntryGrowthDomain.qll"
        ).read_text(encoding="utf-8")

        def effective_content(relative: str) -> str:
            content = (_ROOT / "codeql" / "dosweb" / relative).read_text(
                encoding="utf-8"
            )
            return content + ("\n" + shared_domain if relative.startswith("Flows/") else "")

        for relative in (
            "Flows/EntryToGrowth.ql",
            "Flows/EntryToGrowthAssociations.ql",
            "Lifecycle/LifecycleCoverage.ql",
        ):
            with self.subTest(query=relative, domain="armeria"):
                content = effective_content(relative)
                self.assertIn('"aggregateWithPooledObjects"', content)
                self.assertIn("isArmeriaRequestType", content)
        for relative in (
            "Flows/EntryToGrowth.ql",
            "Flows/EntryToGrowthAssociations.ql",
            "Lifecycle/LifecycleCoverage.ql",
        ):
            with self.subTest(query=relative, domain="constructor"):
                content = effective_content(relative)
                self.assertIn("constructorCall", content)
                self.assertIn("lexicalLambdaCall", content)
        flow = effective_content("Flows/EntryToGrowth.ql")
        self.assertIn("servletRequestAccessor", flow)
        for relative in (
            "Flows/EntryToGrowth.ql",
            "Flows/EntryToGrowthAssociations.ql",
            "Lifecycle/LifecycleCoverage.ql",
        ):
            with self.subTest(query=relative, domain="byte_array_output_stream"):
                content = effective_content(relative)
                self.assertIn('"java.io", "ByteArrayOutputStream", "toByteArray"', content)
            with self.subTest(query=relative, domain="source_input_stream_handler"):
                content = effective_content(relative)
                self.assertIn("sourceInputStreamHandler", content)
            with self.subTest(query=relative, domain="netty_full_http_request_string"):
                content = effective_content(relative)
                self.assertIn("nettyFullRequestStringMaterialization", content)
            with self.subTest(query=relative, domain="http_session_attribute_write"):
                content = effective_content(relative)
                self.assertIn("httpSessionAttributeWrite", content)

    def test_association_and_formal_flow_share_proof_carrying_domain(self) -> None:
        shared = _ROOT / "codeql" / "dosweb" / "Flows" / "EntryGrowthDomain.qll"
        self.assertTrue(shared.is_file())
        domain = shared.read_text(encoding="utf-8")
        self.assertIn("module EntryGrowthPathDomain", domain)
        self.assertIn("predicate entryGrowthPath", domain)
        self.assertIn("EntryToGrowthFlow::flow", domain)
        self.assertIn("boundedCallPath", domain)
        self.assertIn("callEdgeId", domain)
        self.assertIn("getStartLine().toString()", domain)
        self.assertIn("import dosweb.Growth.LoopAmplification", domain)
        self.assertIn("getADimension", domain)
        self.assertNotIn("getDimension(0)", domain)
        self.assertIn("provenAttackerLoopMultiplicity", domain)
        self.assertIn('target = "iteration_count"', domain)
        self.assertIn('target = "submission_count"', domain)
        self.assertIn("exactRequestLocalContainerIterationDemand", domain)
        self.assertIn("exactAsyncSubmissionIterationDemand", domain)
        self.assertIn(
            "provenAttackerLoopMultiplicityForDirectAllocation", domain
        )

        loop_domain = (
            _ROOT / "codeql" / "dosweb" / "Growth" / "LoopAmplification.qll"
        ).read_text(encoding="utf-8")
        for marker in (
            "canonicalAttackerBoundForLoop",
            "variableUpdatedInLoopBody",
            "soleTopLevelStatement",
            "unconditionalTopLevelGrowthInLoop",
            "unconditionalTopLevelDirectAllocationInLoop",
            "provenAttackerLoopMultiplicity",
            "provenAttackerLoopMultiplicityForDirectAllocation",
            "growth.getEnclosingCallable() = loop.getEnclosingCallable()",
            "statement.getExpr() = growth",
            "AssignExpr assignment",
            "assignment.getSource() = growth",
            "SingletonBlock",
        ):
            with self.subTest(loop_marker=marker):
                self.assertIn(marker, loop_domain)

        for query_name in ("EntryToGrowth.ql", "EntryToGrowthAssociations.ql"):
            with self.subTest(query=query_name):
                content = (
                    _ROOT / "codeql" / "dosweb" / "Flows" / query_name
                ).read_text(encoding="utf-8")
                self.assertIn("import EntryGrowthDomain", content)
                self.assertIn("EntryGrowthPathDomain::entryGrowthPath", content)

    def test_shared_flow_domain_unrolls_bounded_call_path(self) -> None:
        domain = (
            _ROOT / "codeql" / "dosweb" / "Flows" / "EntryGrowthDomain.qll"
        ).read_text(encoding="utf-8")
        self.assertNotIn("predicate boundedCallEdges", domain)
        for depth in range(4):
            with self.subTest(depth=depth):
                self.assertIn(f"depth = {depth}", domain)

    def test_framework_limit_domains_are_explicit_and_coverage_is_fail_closed(self) -> None:
        bound = (
            _ROOT / "codeql" / "dosweb" / "Lifecycle" / "BoundCandidates.ql"
        ).read_text(encoding="utf-8")
        coverage = (
            _ROOT / "codeql" / "dosweb" / "Lifecycle" / "LifecycleCoverage.ql"
        ).read_text(encoding="utf-8")
        for token in (
            "StreamReadConstraints",
            "HttpObjectAggregator",
            "MultipartConfig",
            "formdataUploadLimitInKB",
        ):
            with self.subTest(token=token):
                self.assertIn(token, bound)
                self.assertIn(token, coverage)
        self.assertIn("familyModeledDomain", coverage)
        self.assertIn("numericClampBound", bound)
        framework_domain = (
            _ROOT
            / "codeql"
            / "dosweb"
            / "Lifecycle"
            / "FrameworkLimitDomain.qll"
        ).read_text(encoding="utf-8")
        self.assertIn("exists(IntegerLiteral configured", framework_domain)
        self.assertIn("configured.getIntValue() > 0", framework_domain)
        self.assertIn("value = configured.getIntValue().toString()", framework_domain)
        self.assertIn("annotation = input.getAnAnnotation()", framework_domain)
        self.assertIn(
            '["RequestBody", "RequestParam", "PathVariable", "RequestHeader"]',
            framework_domain,
        )
        self.assertIn("demand = access", framework_domain)
        self.assertNotIn("not demand instanceof CompileTimeConstantExpr", framework_domain)
        self.assertIn("directByteAllocationModeledDomain", coverage)
        self.assertIn("lifecycle_family_api_domain_unmodeled", coverage)
        self.assertNotIn(
            'not reflectiveLifecycleDispatch(growth) and not unmodeledLifecycleDispatch(growth, familyValue) and\n      not (familyValue = "bound" and unresolvedFiniteQueueOffer(growth)) and\n      statusValue = "complete"',
            coverage,
        )


@unittest.skipUnless(
    _RUN_FIXTURES and _CODEQL and _JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class CodeqlLifecycleFixtureTests(unittest.TestCase):
    def _database(self, source_root: Path, temporary: Path, name: str):
        database_path = temporary / f"{name}-database"
        classes = temporary / f"{name}-classes"
        classes.mkdir()
        java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
        completed = subprocess.run(
            [
                _CODEQL, "database", "create", str(database_path), "--language=java",
                f"--source-root={source_root}",
                f"--command={_JAVAC} -d {classes} " + " ".join(str(path) for path in java_files),
                "--overwrite",
            ], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
        return validate_database(database_path)

    def _rows(self, query_name: str, database, temporary: Path) -> list[dict[str, object]]:
        query = _ROOT / "codeql" / "dosweb" / query_name
        try:
            result = run_query(query, database, temporary / query_name.replace("/", "-"), codeql_binary=str(_codeql_wrapper(temporary)))
            decoded_path, query_sha256 = result.decoded_path, result.query_sha256
        except Exception as exc:
            if not (getattr(exc, "code", None) == "CODEQL_QUERY_FAILED" and getattr(exc, "details", {}).get("diagnostic") == "database changed during query execution"):
                raise
            bqrs = temporary / f"{query.stem}.bqrs"
            decoded_path = temporary / f"{query.stem}.json"
            completed = subprocess.run([str(_codeql_wrapper(temporary)), "query", "run", str(query), "--database", str(database.path), "--output", str(bqrs)], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            completed = subprocess.run([str(_codeql_wrapper(temporary)), "bqrs", "decode", str(bqrs), "--format=json", "--output", str(decoded_path)], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            query_sha256 = file_sha256(query)
        payload = json.loads(decoded_path.read_text(encoding="utf-8"))
        return decode_bqrs_json(
            {"EntryToGrowth": "flow", "EntryToGrowthAssociations": "flow", "GuardCandidates": "guard", "BoundCandidates": "bound", "SynchronousReleaseCandidates": "release", "LifecycleCoverage": "lifecycle_coverage", "LifecycleSummary": "lifecycle_summary"}[query.stem],
            payload,
            DecodeSource(database.source_root, query_sha256),
        )

    def test_route_alias_and_unrelated_handler_share_one_proof_carrying_path(self) -> None:
        source_root = _ROOT / "tests" / "fixtures" / "spring" / "src" / "main" / "java"
        fixture = source_root / "fixture" / "spring" / "FlowAliasController.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        canonical_line = next(
            number for number, line in enumerate(lines, 1)
            if "void canonical(HttpServletRequest request)" in line
        )
        unrelated_line = next(
            number for number, line in enumerate(lines, 1)
            if "void unrelated(HttpServletRequest request)" in line
        )
        growth_line = next(
            number for number, line in enumerate(lines, 1)
            if "request.getInputStream().readAllBytes()" in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "proof-carrying-alias")
            associations = self._rows(
                "Flows/EntryToGrowthAssociations.ql", database, temporary
            )
            flows = self._rows("Flows/EntryToGrowth.ql", database, temporary)

        def matching(rows: list[dict[str, object]], source_line: int) -> list[dict[str, object]]:
            return [
                row for row in rows
                if row.get("source_file", "").endswith("FlowAliasController.java")
                and row.get("source_start_line") == source_line
                and row.get("sink_start_line") == growth_line
            ]

        canonical_associations = matching(associations, canonical_line)
        canonical_flows = matching(flows, canonical_line)
        self.assertEqual(len(canonical_associations), 1, canonical_associations)
        self.assertEqual(len(canonical_flows), 1, canonical_flows)
        self.assertEqual(canonical_associations[0]["confidence"], "proven")
        self.assertEqual(canonical_associations[0]["coverage_status"], "complete")
        self.assertEqual(canonical_flows[0]["confidence"], "proven")
        self.assertEqual(canonical_flows[0]["coverage_status"], "complete")
        self.assertEqual(canonical_associations[0]["call_path"], canonical_flows[0]["call_path"])
        self.assertEqual(matching(associations, unrelated_line), [])
        self.assertEqual(matching(flows, unrelated_line), [])

    def test_source_input_stream_handler_and_byte_array_output_copy(self) -> None:
        source_root = _ROOT / "tests" / "fixtures" / "spring" / "src" / "main" / "java"
        source_stream_fixture = source_root / "fixture" / "spring" / "SourceStreamResource.java"
        source_stream_lines = source_stream_fixture.read_text(encoding="utf-8").splitlines()
        method_line = next(
            line_number
            for line_number, line in enumerate(source_stream_lines, start=1)
            if "public byte[] process(InputStream input)" in line
        )
        read_line = next(
            line_number
            for line_number, line in enumerate(source_stream_lines, start=1)
            if "input.readAllBytes()" in line
        )
        copy_line = next(
            line_number
            for line_number, line in enumerate(source_stream_lines, start=1)
            if "output.toByteArray()" in line
        )
        beyond_bound_line = next(
            line_number
            for line_number, line in enumerate(source_stream_lines, start=1)
            if "public byte[] processBeyondBound(InputStream input)" in line
        )
        deep_copy_line = next(
            line_number
            for line_number, line in enumerate(source_stream_lines, start=1)
            if "deepOutput.toByteArray()" in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "source-stream")
            association_rows = self._rows(
                "Flows/EntryToGrowthAssociations.ql", database, temporary
            )
            flow_rows = self._rows("Flows/EntryToGrowth.ql", database, temporary)
            coverage_rows = self._rows(
                "Lifecycle/LifecycleCoverage.ql", database, temporary
            )

        source_associations = [
            row for row in association_rows
            if row.get("source_file", "").endswith("SourceStreamResource.java")
            and row.get("source_start_line") == method_line
            and row.get("sink_file", "").endswith("SourceStreamResource.java")
        ]
        self.assertTrue(source_associations, association_rows)
        self.assertTrue(
            any(row.get("sink_start_line") == read_line for row in source_associations),
            source_associations,
        )

        self.assertTrue(
            any(row.get("sink_start_line") == copy_line for row in source_associations),
            source_associations,
        )
        bounded_helper_rows = [
            row
            for row in association_rows
            if row.get("source_file", "").endswith("SourceStreamResource.java")
            and row.get("source_start_line") == beyond_bound_line
            and row.get("sink_start_line") == deep_copy_line
        ]
        self.assertEqual(len(bounded_helper_rows), 1, bounded_helper_rows)
        self.assertEqual(bounded_helper_rows[0]["confidence"], "proven")
        self.assertEqual(bounded_helper_rows[0]["coverage_status"], "complete")
        self.assertEqual(
            bounded_helper_rows[0]["coverage_note"],
            "unique_bounded_call_path_global_dataflow",
        )
        self.assertTrue(
            any(
                row.get("source_file", "").endswith("SourceStreamResource.java")
                and row.get("source_start_line") == method_line
                and row.get("sink_start_line") == read_line
                and row.get("attacker_source") == "input"
                for row in flow_rows
            ),
            flow_rows,
        )
        self.assertTrue(
            any(
                row.get("anchor_file", "").endswith("SourceStreamResource.java")
                and row.get("anchor_start_line") == copy_line
                for row in coverage_rows
            ),
            coverage_rows,
        )

    def test_source_stream_to_bounded_parser_output_copy_is_exact_partial(self) -> None:
        source_root = _ROOT / "tests" / "fixtures" / "spring" / "src" / "main" / "java"
        fixture = source_root / "fixture" / "spring" / "SourceStreamResource.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        method_line = next(
            number for number, line in enumerate(lines, 1)
            if "public byte[] processParserOutput(InputStream input)" in line
        )
        copy_line = next(
            number for number, line in enumerate(lines, 1)
            if "return parserOutput.toByteArray()" in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "source-parser-output")
            associations = self._rows(
                "Flows/EntryToGrowthAssociations.ql", database, temporary
            )
            flows = self._rows("Flows/EntryToGrowth.ql", database, temporary)

        matching_associations = [
            row for row in associations
            if row.get("source_file", "").endswith("SourceStreamResource.java")
            and row.get("source_start_line") == method_line
            and row.get("sink_start_line") == copy_line
        ]
        matching_flows = [
            row for row in flows
            if row.get("source_file", "").endswith("SourceStreamResource.java")
            and row.get("source_start_line") == method_line
            and row.get("sink_start_line") == copy_line
        ]
        self.assertEqual(len(matching_associations), 1, matching_associations)
        self.assertEqual(len(matching_flows), 1, matching_flows)
        self.assertEqual(
            matching_associations[0]["call_path"], matching_flows[0]["call_path"]
        )
        for row in matching_associations + matching_flows:
            self.assertEqual(row["attacker_target"], "size")
            self.assertEqual(row["confidence"], "partial")
            self.assertEqual(row["coverage_status"], "partial")
            self.assertEqual(
                row["coverage_note"],
                "source_input_stream_to_output_copy_requires_dataflow_witness",
            )
        self.assertEqual(matching_flows[0]["attacker_source"], "input")

    def test_jmqtt_qos2_dispatch_emits_only_partial_association(self) -> None:
        source_root = _ROOT / "tests" / "fixtures" / "mqtt" / "src" / "main" / "java"
        fixture = source_root / "fixture" / "mqtt" / "MqttFixture.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        handler_line = next(
            number for number, line in enumerate(lines, 1)
            if "public void channelRead(BrokerContext context, Object message)" in line
        )
        growth_line = next(
            number for number, line in enumerate(lines, 1)
            if "qos2Receiving.put(originPacketId, message)" in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "jmqtt-qos2-dispatch")
            associations = self._rows(
                "Flows/EntryToGrowthAssociations.ql", database, temporary
            )

        matching = [
            row for row in associations
            if row.get("source_file", "").endswith("MqttFixture.java")
            and row.get("source_start_line") == handler_line
            and row.get("sink_start_line") == growth_line
        ]
        self.assertEqual(len(matching), 1, matching)
        self.assertEqual(matching[0]["attacker_target"], "key")
        self.assertEqual(matching[0]["confidence"], "partial")
        self.assertEqual(matching[0]["coverage_status"], "partial")
        self.assertEqual(
            matching[0]["coverage_note"],
            "jmqtt_async_processor_qos2_dispatch_requires_path_coverage",
        )

    def test_citrus_default_routes_emit_only_partial_prehandler_and_session_associations(
        self,
    ) -> None:
        source_root = _ROOT / "tests" / "fixtures" / "spring" / "src" / "main" / "java"
        fixture = source_root / "fixture" / "spring" / "CitrusFixture.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        authenticate_line = next(
            number
            for number, line in enumerate(lines, 1)
            if "void authenticate(HttpServletRequest request)" in line
        )
        read_line = next(
            number
            for number, line in enumerate(lines, 1)
            if "body = IoUtil.readBytes(request.getInputStream())" in line
        )
        image_line = next(
            number
            for number, line in enumerate(lines, 1)
            if "void image(HttpServletRequest request" in line
        )
        session_line = next(
            number
            for number, line in enumerate(lines, 1)
            if 'session.setAttribute("SESSION_VERIFY_ID", verification)' in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "citrus-default-routes")
            associations = self._rows(
                "Flows/EntryToGrowthAssociations.ql", database, temporary
            )

        auth_matches = [
            row
            for row in associations
            if row.get("source_file", "").endswith("CitrusFixture.java")
            and row.get("source_start_line") == authenticate_line
            and row.get("sink_start_line") == read_line
        ]
        self.assertEqual(len(auth_matches), 1, auth_matches)
        self.assertEqual(auth_matches[0]["attacker_target"], "size")
        self.assertEqual(auth_matches[0]["confidence"], "partial")
        self.assertEqual(auth_matches[0]["coverage_status"], "partial")
        self.assertEqual(
            auth_matches[0]["coverage_note"],
            "citrus_component_request_wrapper_prehandler_requires_path_coverage",
        )

        captcha_matches = [
            row
            for row in associations
            if row.get("source_file", "").endswith("CitrusFixture.java")
            and row.get("source_start_line") == image_line
            and row.get("sink_start_line") == session_line
        ]
        self.assertTrue(captcha_matches, associations)
        self.assertTrue(
            all(
                row["attacker_target"] == "value"
                and row["confidence"] == "partial"
                and row["coverage_status"] == "partial"
                for row in captcha_matches
            ),
            captcha_matches,
        )
        self.assertEqual(
            len(
                [
                    row
                    for row in captcha_matches
                    if row["coverage_note"]
                    == "citrus_verification_session_dispatch_requires_path_coverage"
                ]
            ),
            1,
            captcha_matches,
        )

    def test_solr_form_parser_prehandler_emits_only_partial_association(self) -> None:
        source_root = _ROOT / "tests" / "fixtures" / "servlet" / "src" / "main" / "java"
        fixture = source_root / "org" / "apache" / "solr" / "servlet" / "SolrServlet.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        service_line = next(
            number for number, line in enumerate(lines, 1)
            if "protected void service(HttpServletRequest request" in line
        )
        form_copy_line = next(
            number for number, line in enumerate(lines, 1)
            if "byte[] keyBytes = keyStream.toByteArray()" in line
        )
        unrelated_copy_line = next(
            number for number, line in enumerate(lines, 1)
            if "return unrelated.toByteArray()" in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "solr-form")
            rows = self._rows(
                "Flows/EntryToGrowthAssociations.ql", database, temporary
            )

        matching = [
            row for row in rows
            if row.get("source_file", "").endswith("org/apache/solr/servlet/SolrServlet.java")
            and row.get("source_start_line") == service_line
            and row.get("sink_start_line") == form_copy_line
        ]
        self.assertEqual(len(matching), 1, rows)
        self.assertEqual(matching[0]["confidence"], "partial")
        self.assertEqual(matching[0]["coverage_status"], "partial")
        self.assertEqual(
            matching[0]["coverage_note"],
            "solr_form_prehandler_dispatch_requires_path_coverage",
        )
        self.assertFalse(
            any(
                row.get("source_start_line") == service_line
                and row.get("sink_start_line") == unrelated_copy_line
                for row in rows
            ),
            rows,
        )

    def test_spring_request_body_string_is_shared_by_flow_and_lifecycle_domains(self) -> None:
        source_root = _ROOT / "tests" / "fixtures" / "spring" / "src" / "main" / "java"
        fixture = source_root / "fixture" / "spring" / "RequestBodyStringController.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        string_body_line = next(
            number for number, line in enumerate(lines, 1)
            if "void stringBody(" in line
        )
        unannotated_line = next(
            number for number, line in enumerate(lines, 1)
            if "void unannotatedString(" in line
        )
        lookalike_line = next(
            number for number, line in enumerate(lines, 1)
            if "void stringLookalike(" in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "request-body-string")
            associations = self._rows(
                "Flows/EntryToGrowthAssociations.ql", database, temporary
            )
            flows = self._rows("Flows/EntryToGrowth.ql", database, temporary)
            coverage = self._rows(
                "Lifecycle/LifecycleCoverage.ql", database, temporary
            )

        fixture_associations = [
            row for row in associations
            if row.get("sink_file", "").endswith("RequestBodyStringController.java")
        ]
        self.assertEqual(
            [row["sink_start_line"] for row in fixture_associations],
            [string_body_line],
            fixture_associations,
        )
        self.assertEqual(fixture_associations[0]["attacker_target"], "size")
        self.assertEqual(fixture_associations[0]["coverage_status"], "complete")

        fixture_flows = [
            row for row in flows
            if row.get("sink_file", "").endswith("RequestBodyStringController.java")
        ]
        self.assertEqual(
            [row["sink_start_line"] for row in fixture_flows],
            [string_body_line],
            fixture_flows,
        )
        self.assertEqual(fixture_flows[0]["attacker_source"], "body")
        self.assertEqual(fixture_flows[0]["attacker_target"], "size")
        self.assertEqual(fixture_flows[0]["coverage_status"], "complete")

        fixture_coverage = [
            row for row in coverage
            if row.get("anchor_file", "").endswith("RequestBodyStringController.java")
        ]
        self.assertEqual(
            {row["anchor_start_line"] for row in fixture_coverage},
            {string_body_line},
            fixture_coverage,
        )
        self.assertEqual(
            {row["family"] for row in fixture_coverage},
            {"guard", "bound", "release"},
            fixture_coverage,
        )
        self.assertTrue(
            all(row["coverage_status"] == "partial" for row in fixture_coverage),
            fixture_coverage,
        )
        self.assertEqual(
            {row["coverage_note"] for row in fixture_coverage},
            {"lifecycle_family_api_domain_unmodeled"},
        )
        for negative_line in (unannotated_line, lookalike_line):
            self.assertNotIn(
                negative_line,
                {row["sink_start_line"] for row in fixture_associations + fixture_flows},
            )
            self.assertNotIn(
                negative_line,
                {row["anchor_start_line"] for row in fixture_coverage},
            )

    def test_netty_full_request_string_is_shared_by_flow_and_lifecycle_domains(self) -> None:
        source_root = _ROOT / "tests" / "fixtures" / "netty" / "src" / "main" / "java"
        fixture = source_root / "fixture" / "netty" / "NettyFixture.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        materialization_lines = [
            number for number, line in enumerate(lines, 1)
            if "request.content().toString(CharsetUtil.UTF_8)" in line
        ]
        self.assertEqual(len(materialization_lines), 2)
        positive_line, lookalike_line = materialization_lines
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "netty-full-request-string")
            associations = self._rows(
                "Flows/EntryToGrowthAssociations.ql", database, temporary
            )
            flows = self._rows("Flows/EntryToGrowth.ql", database, temporary)
            coverage = self._rows(
                "Lifecycle/LifecycleCoverage.ql", database, temporary
            )

        fixture_associations = [
            row for row in associations
            if row.get("sink_file", "").endswith("NettyFixture.java")
            and row.get("sink_start_line") in materialization_lines
        ]
        self.assertEqual(
            [row["sink_start_line"] for row in fixture_associations],
            [positive_line],
            fixture_associations,
        )
        self.assertEqual(fixture_associations[0]["attacker_target"], "size")
        self.assertEqual(fixture_associations[0]["coverage_status"], "complete")

        fixture_flows = [
            row for row in flows
            if row.get("sink_file", "").endswith("NettyFixture.java")
            and row.get("sink_start_line") in materialization_lines
        ]
        self.assertEqual(
            [row["sink_start_line"] for row in fixture_flows],
            [positive_line],
            fixture_flows,
        )
        self.assertEqual(fixture_flows[0]["attacker_source"], "request")
        self.assertEqual(fixture_flows[0]["attacker_target"], "size")
        self.assertEqual(fixture_flows[0]["coverage_status"], "complete")

        fixture_coverage = [
            row for row in coverage
            if row.get("anchor_file", "").endswith("NettyFixture.java")
            and row.get("anchor_start_line") in materialization_lines
        ]
        self.assertEqual(
            {row["anchor_start_line"] for row in fixture_coverage},
            {positive_line},
            fixture_coverage,
        )
        self.assertEqual(
            {row["family"] for row in fixture_coverage},
            {"guard", "bound", "release"},
            fixture_coverage,
        )
        self.assertTrue(
            all(row["coverage_status"] == "partial" for row in fixture_coverage),
            fixture_coverage,
        )
        self.assertEqual(
            {row["coverage_note"] for row in fixture_coverage},
            {"lifecycle_family_api_domain_unmodeled"},
        )
        self.assertNotIn(
            lookalike_line,
            {row["sink_start_line"] for row in fixture_associations + fixture_flows},
        )
        self.assertNotIn(
            lookalike_line,
            {row["anchor_start_line"] for row in fixture_coverage},
        )

    def test_netty_json_switch_dispatch_remains_partial_through_service_growth(self) -> None:
        source_root = _ROOT / "tests" / "fixtures" / "netty" / "src" / "main" / "java"
        fixture = source_root / "fixture" / "netty" / "NettyFixture.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        handler_line = next(
            number for number, line in enumerate(lines, 1)
            if "protected void channelRead0(" in line
        )
        growth_line = next(
            number for number, line in enumerate(lines, 1)
            if "requests.add(request)" in line
        )
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "netty-json-switch-dispatch")
            associations = self._rows(
                "Flows/EntryToGrowthAssociations.ql", database, temporary
            )
            flows = self._rows("Flows/EntryToGrowth.ql", database, temporary)
            coverage = self._rows(
                "Lifecycle/LifecycleCoverage.ql", database, temporary
            )

        matching_associations = [
            row for row in associations
            if row.get("source_file", "").endswith("NettyFixture.java")
            and row.get("source_start_line") == handler_line
            and row.get("sink_start_line") == growth_line
        ]
        self.assertEqual(len(matching_associations), 1, matching_associations)
        self.assertEqual(matching_associations[0]["confidence"], "partial")
        self.assertEqual(matching_associations[0]["coverage_status"], "partial")
        self.assertEqual(
            matching_associations[0]["coverage_note"],
            "netty_json_switch_async_dispatch_requires_path_coverage",
        )

        matching_flows = [
            row for row in flows
            if row.get("source_file", "").endswith("NettyFixture.java")
            and row.get("source_start_line") == handler_line
            and row.get("sink_start_line") == growth_line
        ]
        self.assertEqual(len(matching_flows), 1, matching_flows)
        self.assertEqual(matching_flows[0]["attacker_source"], "request")
        self.assertEqual(matching_flows[0]["attacker_target"], "value")
        self.assertEqual(matching_flows[0]["confidence"], "partial")
        self.assertEqual(matching_flows[0]["coverage_status"], "partial")

        matching_coverage = [
            row for row in coverage
            if row.get("anchor_file", "").endswith("NettyFixture.java")
            and row.get("anchor_start_line") == growth_line
        ]
        self.assertEqual(
            {row["family"] for row in matching_coverage},
            {"guard", "bound", "release"},
            matching_coverage,
        )
        self.assertTrue(
            all(row["coverage_status"] == "partial" for row in matching_coverage),
            matching_coverage,
        )
        self.assertEqual(
            {row["coverage_note"] for row in matching_coverage},
            {"netty_async_json_dispatch_lifecycle_unresolved"},
        )

    def test_framework_limits_emit_complete_growth_anchored_bound_rows(self) -> None:
        source_root = (
            _ROOT / "tests" / "fixtures" / "framework_limits" / "src" / "main" / "java"
        )
        fixture = source_root / "fixture" / "limits" / "FrameworkLimitFixture.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        anchors = {
            marker: next(
                number for number, line in enumerate(lines, 1) if marker in line
            )
            for marker in (
                "ByteBuffer.allocate(jacksonSize)",
                "ByteBuffer.allocate(Math.min(requestedSize, 1024))",
                "ByteBuffer.allocate(Math.min(requestedSize, 0x400))",
                "ByteBuffer.allocate(Math.min(requestedSize, 0b10000000000))",
                "ByteBuffer.allocate(message.content().readableBytes())",
                "ByteBuffer.allocate(request.size())",
                "keyStream.toByteArray()",
            )
        }
        unrelated_anchors = {
            marker: next(
                number for number, line in enumerate(lines, 1) if marker in line
            )
            for marker in (
                "ByteBuffer.allocate(unboundJacksonSize)",
                "ByteBuffer.allocate((Integer) looseMessage)",
                "ByteBuffer.allocate(1024); // unrelated multipart allocation",
            )
        }
        invalid_clamp_anchors = {
            marker: next(
                number for number, line in enumerate(lines, 1) if marker in line
            )
            for marker in (
                "ByteBuffer.allocate(Math.min(requestedSize, 512 + 512))",
                "ByteBuffer.allocate(Math.min(requestedSize, LIMIT))",
                "ByteBuffer.allocate(Math.min(serverDerivedValue(), 1024))",
                "ByteBuffer.allocate(Math.min(requestedSize, 0))",
                "ByteBuffer.allocate(Math.min(requestedSize, -1))",
                "ByteBuffer.allocate(Math.min(-1, 1024))",
            )
        }
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "framework-limits")
            bounds = self._rows("Lifecycle/BoundCandidates.ql", database, temporary)
            coverage = self._rows("Lifecycle/LifecycleCoverage.ql", database, temporary)

        fixture_bounds = [
            row for row in bounds
            if row.get("anchor_file", "").endswith("FrameworkLimitFixture.java")
        ]
        self.assertEqual(
            {row["evidence"] for row in fixture_bounds},
            {
                "jackson_stream_read_constraints_literal",
                "netty_http_object_aggregator_literal",
                "numeric_min_literal",
                "servlet_multipart_config_literal",
                "solr_formdata_upload_limit_literal",
            },
            fixture_bounds,
        )
        self.assertEqual(
            {row["anchor_start_line"] for row in fixture_bounds},
            set(anchors.values()),
            fixture_bounds,
        )
        self.assertEqual(len(fixture_bounds), 7, fixture_bounds)
        expected_bound_rows = {
            anchors["ByteBuffer.allocate(jacksonSize)"]: (
                "jackson_stream_read_constraints_literal",
                "1024",
                "json",
            ),
            anchors["ByteBuffer.allocate(Math.min(requestedSize, 1024))"]: (
                "numeric_min_literal",
                "1024",
                "any",
            ),
            anchors["ByteBuffer.allocate(Math.min(requestedSize, 0x400))"]: (
                "numeric_min_literal",
                "1024",
                "any",
            ),
            anchors["ByteBuffer.allocate(Math.min(requestedSize, 0b10000000000))"]: (
                "numeric_min_literal",
                "1024",
                "any",
            ),
            anchors["ByteBuffer.allocate(message.content().readableBytes())"]: (
                "netty_http_object_aggregator_literal",
                "1024",
                "aggregated_http",
            ),
            anchors["ByteBuffer.allocate(request.size())"]: (
                "servlet_multipart_config_literal",
                "1024",
                "multipart",
            ),
            anchors["keyStream.toByteArray()"]: (
                "solr_formdata_upload_limit_literal",
                "1024",
                "form_urlencoded",
            ),
        }
        self.assertEqual(
            {
                row["anchor_start_line"]: (
                    row["evidence"],
                    row["configuration_value"],
                    row["request_encoding"],
                )
                for row in fixture_bounds
            },
            expected_bound_rows,
            fixture_bounds,
        )
        self.assertTrue(
            set(unrelated_anchors.values()).isdisjoint(
                {row["anchor_start_line"] for row in fixture_bounds}
            ),
            fixture_bounds,
        )
        self.assertTrue(
            set(invalid_clamp_anchors.values()).isdisjoint(
                {row["anchor_start_line"] for row in fixture_bounds}
            ),
            fixture_bounds,
        )
        framework_bounds = [
            row for row in fixture_bounds
            if row["evidence"] != "numeric_min_literal"
        ]
        self.assertEqual(len(framework_bounds), 4, framework_bounds)
        self.assertTrue(
            all(
                row["coverage_status"] == "complete"
                and row["behavior"] == "reject"
                and row["coverage_note"] == "framework_limit_exact_path_literal"
                and row["phase"] == "before_growth"
                and row["covers_flow"] is True
                and row["product_bound"] is True
                for row in framework_bounds
            ),
            framework_bounds,
        )
        clamp_bounds = [
            row for row in fixture_bounds
            if row["evidence"] == "numeric_min_literal"
        ]
        self.assertEqual(len(clamp_bounds), 3, clamp_bounds)
        self.assertEqual(
            {
                anchors["ByteBuffer.allocate(Math.min(requestedSize, 1024))"],
                anchors["ByteBuffer.allocate(Math.min(requestedSize, 0x400))"],
                anchors[
                    "ByteBuffer.allocate(Math.min(requestedSize, 0b10000000000))"
                ],
            },
            {row["anchor_start_line"] for row in clamp_bounds},
        )
        self.assertTrue(
            all(
                row["behavior"] == "clamp"
                and row["coverage_note"] == "same_expression_numeric_clamp"
                and row["phase"] == "inside_growth"
                and row["configuration_value"] == "1024"
                and row["coverage_status"] == "complete"
                and row["covers_flow"] is True
                and row["product_bound"] is True
                for row in clamp_bounds
            ),
            clamp_bounds,
        )
        bound_coverage = [
            row for row in coverage
            if row.get("anchor_file", "").endswith("FrameworkLimitFixture.java")
            and row.get("anchor_start_line") in anchors.values()
            and row.get("family") == "bound"
        ]
        self.assertEqual(len(bound_coverage), 7, bound_coverage)
        self.assertEqual(
            {row["anchor_start_line"] for row in bound_coverage},
            set(anchors.values()),
            bound_coverage,
        )
        self.assertTrue(
            all(
                row["coverage_status"] == "complete"
                and row["coverage_note"] == "same_callable_modeled_domain_scanned"
                for row in bound_coverage
            ),
            bound_coverage,
        )

    def test_direct_byte_allocation_bound_domain_covers_absence_and_numeric_clamp(self) -> None:
        source_root = (
            _ROOT / "tests" / "fixtures" / "framework_limits" / "src" / "main" / "java"
        )
        fixture = source_root / "fixture" / "limits" / "FrameworkLimitFixture.java"
        lines = fixture.read_text(encoding="utf-8").splitlines()
        plain_line = next(
            number for number, line in enumerate(lines, 1)
            if "ByteBuffer.allocate(requestedSize)" in line
        )
        clamped_lines = {
            marker: next(
                number for number, line in enumerate(lines, 1) if marker in line
            )
            for marker in (
                "ByteBuffer.allocate(Math.min(requestedSize, 1024))",
                "ByteBuffer.allocate(Math.min(requestedSize, 0x400))",
                "ByteBuffer.allocate(Math.min(requestedSize, 0b10000000000))",
            )
        }
        invalid_clamped_lines = {
            next(
                number for number, line in enumerate(lines, 1) if marker in line
            )
            for marker in (
                "ByteBuffer.allocate(Math.min(requestedSize, 512 + 512))",
                "ByteBuffer.allocate(Math.min(requestedSize, LIMIT))",
                "ByteBuffer.allocate(Math.min(serverDerivedValue(), 1024))",
                "ByteBuffer.allocate(Math.min(requestedSize, 0))",
                "ByteBuffer.allocate(Math.min(requestedSize, -1))",
                "ByteBuffer.allocate(Math.min(-1, 1024))",
            )
        }
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database = self._database(source_root, temporary, "direct-allocation-bound-domain")
            bounds = self._rows("Lifecycle/BoundCandidates.ql", database, temporary)
            coverage = self._rows("Lifecycle/LifecycleCoverage.ql", database, temporary)

        fixture_bounds = [
            row for row in bounds
            if row.get("anchor_file", "").endswith("FrameworkLimitFixture.java")
        ]
        self.assertFalse(
            any(row["anchor_start_line"] == plain_line for row in fixture_bounds),
            fixture_bounds,
        )
        clamped = [
            row for row in fixture_bounds
            if row["anchor_start_line"] in clamped_lines.values()
        ]
        self.assertEqual(3, len(clamped), clamped)
        self.assertTrue(
            all(
                row["behavior"] == "clamp"
                and row["evidence"] == "numeric_min_literal"
                and row["configuration_value"] == "1024"
                and row["product_bound"] is True
                for row in clamped
            ),
            clamped,
        )
        self.assertTrue(
            invalid_clamped_lines.isdisjoint(
                {row["anchor_start_line"] for row in fixture_bounds}
            ),
            fixture_bounds,
        )
        bound_coverage = {
            row["anchor_start_line"]: row
            for row in coverage
            if row.get("anchor_file", "").endswith("FrameworkLimitFixture.java")
            and row.get("family") == "bound"
            and row.get("anchor_start_line") in {plain_line, *clamped_lines.values()}
        }
        self.assertEqual({plain_line, *clamped_lines.values()}, set(bound_coverage))
        self.assertTrue(
            all(row["coverage_status"] == "complete" for row in bound_coverage.values()),
            bound_coverage,
        )

    def test_fixture_semantics(self) -> None:
        cases = {
            "spring": {"association": True, "flow": True, "guard": True, "bound": False, "release": False, "coverage": True, "summary": False},
            "servlet": {"association": True, "flow": True, "guard": True, "bound": False, "release": True, "coverage": True, "summary": False},
            "netty": {"association": True, "flow": True, "guard": False, "bound": True, "release": True, "coverage": True, "summary": False},
            "mqtt": {"association": True, "flow": True, "guard": True, "bound": False, "release": False, "coverage": True, "summary": False},
            "armeria": {"association": True, "flow": True, "guard": False, "bound": False, "release": False, "coverage": True, "summary": False},
        }
        query_names = {
            "association": "Flows/EntryToGrowthAssociations.ql",
            "flow": "Flows/EntryToGrowth.ql",
            "guard": "Lifecycle/GuardCandidates.ql",
            "bound": "Lifecycle/BoundCandidates.ql",
            "release": "Lifecycle/SynchronousReleaseCandidates.ql",
            "coverage": "Lifecycle/LifecycleCoverage.ql",
            "summary": "Lifecycle/LifecycleSummary.ql",
        }
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            wrapper = _codeql_wrapper(temporary)
            self.assertTrue(wrapper.exists())
            for fixture, expectations in cases.items():
                source_root = _ROOT / "tests" / "fixtures" / fixture / "src" / "main" / "java"
                database = self._database(source_root, temporary, fixture)
                servlet_append_line = None
                servlet_lambda_line = None
                if fixture == "servlet":
                    servlet_fixture = source_root / "fixture" / "servlet" / "ServletFixture.java"
                    servlet_append_line = next(
                        line_number
                        for line_number, line in enumerate(
                            servlet_fixture.read_text(encoding="utf-8").splitlines(),
                            start=1,
                        )
                        if "builder.append(buffer, 0, count)" in line
                    )
                    servlet_lambda_line = next(
                        line_number
                        for line_number, line in enumerate(
                            servlet_fixture.read_text(encoding="utf-8").splitlines(),
                            start=1,
                        )
                        if "request.getInputStream().readAllBytes()" in line
                    )
                for family, query_name in query_names.items():
                    with self.subTest(fixture=fixture, query=family):
                        rows = self._rows(query_name, database, temporary)
                        if expectations[family]:
                            self.assertTrue(rows, f"expected {family} candidates for {fixture}")
                        if fixture == "spring" and family in {"association", "flow"}:
                            gateway_rows = [
                                row for row in rows
                                if row.get("sink_file", "").endswith("GatewayController.java")
                            ]
                            self.assertTrue(gateway_rows, rows)
                            if family == "flow":
                                self.assertTrue(
                                    any(row["attacker_source"] == "request" for row in gateway_rows),
                                    gateway_rows,
                                )
                            else:
                                self.assertTrue(
                                    any(
                                        str(row["attacker_source"]).endswith("GatewayController.gateway")
                                        for row in gateway_rows
                                    ),
                                    gateway_rows,
                                )
                            read_all_rows = [
                                row for row in rows
                                if row.get("sink_file", "").endswith("ReadAllController.java")
                            ]
                            self.assertTrue(read_all_rows, rows)
                            self.assertTrue(
                                {
                                    "hutool",
                                    "commonsIo",
                                    "springBytes",
                                    "springString",
                                    "jdkReadAllBytes",
                                }.issubset(
                                    {
                                        str(row["call_path"]).split(">", 1)[0].rsplit(".", 1)[-1]
                                        for row in read_all_rows
                                    }
                                ),
                                read_all_rows,
                            )
                            self.assertTrue(
                                any(
                                    "constructorString" in str(row["call_path"])
                                    and "RequestWrapper" in str(row["call_path"])
                                    for row in read_all_rows
                                ),
                                read_all_rows,
                            )
                        if fixture == "armeria" and family in {"association", "flow"}:
                            aggregate_rows = [
                                row for row in rows
                                if row.get("sink_file", "").endswith("ArmeriaFixture.java")
                                and "RegisteredCollector" in str(row.get("call_path", ""))
                            ]
                            self.assertTrue(aggregate_rows, rows)
                            self.assertTrue(
                                any(row["attacker_target"] == "size" for row in aggregate_rows),
                                aggregate_rows,
                            )
                            if family == "flow":
                                self.assertTrue(
                                    any(row["attacker_source"] == "request" for row in aggregate_rows),
                                    aggregate_rows,
                                )
                        if fixture == "servlet" and family in {"association", "flow"}:
                            wrapper_rows = [
                                row for row in rows
                                if row.get("sink_file", "").endswith("ServletFixture.java")
                                and row.get("sink_start_line") == servlet_append_line
                                and "BodyCachingWrapper" in str(row.get("call_path", ""))
                            ]
                            self.assertTrue(wrapper_rows, rows)
                            if family == "flow":
                                self.assertTrue(
                                    any(row["attacker_source"] == "request" for row in wrapper_rows),
                                    wrapper_rows,
                                )
                                self.assertTrue(
                                    any(row["attacker_sink"] == "buffer" for row in wrapper_rows),
                                    wrapper_rows,
                                )
                            lambda_rows = [
                                row for row in rows
                                if row.get("sink_file", "").endswith("ServletFixture.java")
                                and row.get("sink_start_line") == servlet_lambda_line
                                and "LambdaMaterializationServlet.service" in str(row.get("call_path", ""))
                            ]
                            self.assertTrue(lambda_rows, rows)
                            if family == "flow":
                                self.assertTrue(
                                    any(row["attacker_source"] == "request" for row in lambda_rows),
                                    lambda_rows,
                                )
                        if fixture == "spring" and family == "coverage":
                            self.assertTrue(
                                any(
                                    row.get("anchor_file", "").endswith("GatewayController.java")
                                    for row in rows
                                ),
                                rows,
                            )
                        if fixture == "armeria" and family == "coverage":
                            self.assertTrue(
                                any(
                                    row.get("anchor_file", "").endswith("ArmeriaFixture.java")
                                    for row in rows
                                ),
                                rows,
                            )
                        if fixture == "servlet" and family == "coverage":
                            self.assertTrue(
                                any(
                                    row.get("anchor_file", "").endswith("ServletFixture.java")
                                    and row.get("anchor_start_line") == servlet_append_line
                                    for row in rows
                                ),
                                rows,
                            )
                            self.assertTrue(
                                any(
                                    row.get("anchor_file", "").endswith("ServletFixture.java")
                                    and row.get("anchor_start_line") == servlet_lambda_line
                                    for row in rows
                                ),
                                rows,
                            )
                        for row in rows:
                            self.assertIn("coverage_status", row)
                            self.assertNotIn("verdict", row)
                            self.assertNotIn("assertion", row)
                        if family == "coverage":
                            self.assertTrue(all(row["family"] in {"guard", "bound", "release"} for row in rows))
                        if family == "guard":
                            for row in (item for item in rows if item["coverage_status"] == "complete"):
                                if row["coverage_note"] == "same_cfg_shared_source_guard_witness":
                                    self.assertTrue(row["dominates_growth"])
                                    self.assertFalse(row["reject_path_reaches_growth"])
                                    self.assertTrue(row["covers_materialization"])
                                    self.assertEqual("before_growth", row["phase"])
                                else:
                                    self.assertEqual("same_cfg_guard_ineffective_after_growth", row["coverage_note"])
                                    self.assertFalse(row["dominates_growth"])
                                    self.assertTrue(row["reject_path_reaches_growth"])
                                    self.assertFalse(row["covers_materialization"])
                                    self.assertEqual("after_growth", row["phase"])
                        if family == "release":
                            for row in (item for item in rows if item["coverage_status"] == "complete"):
                                self.assertTrue(row["after_growth"])
                                self.assertTrue(row["normal_path"])
                                self.assertTrue(row["actual_reduction"])
                                if row["exceptional_path"]:
                                    self.assertEqual("same_cfg_finally_release_witness", row["coverage_note"])
                                else:
                                    self.assertEqual("success_only_exception_path_missing", row["coverage_note"])
                        if fixture == "netty" and family == "bound":
                            self.assertTrue(any(row["coverage_status"] == "complete" for row in rows))


if __name__ == "__main__":
    unittest.main()
