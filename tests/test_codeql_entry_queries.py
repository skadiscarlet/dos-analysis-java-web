from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from dosweb.codeql import DecodeSource, ENTRY_COLUMNS, INTERPOSITION_COLUMNS, SECURITY_COLUMNS, decode_bqrs_json, run_query, validate_database
from dosweb.entries import normalize_entry_rows, normalize_framework_coverage, normalize_gap_entry_rows
from dosweb.entries.webxml import resolve_webxml_servlet_candidates


_RUN_FIXTURES = os.environ.get("DOSWEB_RUN_CODEQL_FIXTURES") == "1"
_CODEQL = shutil.which("codeql")
_JAVAC = shutil.which("javac")


def _selected_pack_search_path() -> str:
    packages = Path.home() / ".codeql" / "packages"
    java_versions = sorted((packages / "codeql" / "java-all").glob("*/qlpack.yml"))
    if not java_versions:
        raise unittest.SkipTest("A local codeql/java-all package is unavailable.")
    pending = [java_versions[-1].parent]
    selected: dict[str, Path] = {}
    while pending:
        pack = pending.pop()
        manifest = yaml.safe_load((pack / "qlpack.yml").read_text(encoding="utf-8"))
        name = manifest["name"]
        if name in selected:
            continue
        selected[name] = pack
        for dependency, version in (manifest.get("dependencies") or {}).items():
            candidate = packages / dependency / str(version)
            if not candidate.joinpath("qlpack.yml").is_file():
                raise unittest.SkipTest(f"Local CodeQL dependency is unavailable: {dependency}@{version}")
            pending.append(candidate)
    return os.pathsep.join(str(path) for path in selected.values())


def _codeql_wrapper(directory: Path) -> Path:
    wrapper = directory / "codeql-with-local-packs"
    wrapper.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = query ] && [ \"$2\" = run ]; then\n"
        f"  exec {_CODEQL} \"$@\" --search-path={_selected_pack_search_path()}\n"
        "fi\n"
        f"exec {_CODEQL} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    return wrapper


class CodeqlEntryQueryContractTests(unittest.TestCase):
    def test_direct_and_embedded_entry_query_packs_are_byte_identical(self):
        root = Path(__file__).parents[1]
        direct = root / "codeql" / "dosweb" / "Entries"
        embedded = root / "dosweb" / "codeql" / "pack" / "dosweb" / "Entries"
        direct_files = {path.name for path in direct.glob("*.ql") if not path.name.startswith(".")}
        embedded_files = {path.name for path in embedded.glob("*.ql") if not path.name.startswith(".")}
        self.assertEqual(direct_files, embedded_files)
        for name in sorted(direct_files):
            with self.subTest(query=name):
                self.assertEqual((direct / name).read_bytes(), (embedded / name).read_bytes())

    def test_entry_queries_use_the_exact_shared_table_contract(self):
        root = Path(__file__).parents[1]
        query_root = root / "codeql" / "dosweb" / "Entries"
        query_names = (
            "SpringMvcEntries.ql",
            "ServletEntries.ql",
            "NettyEntries.ql",
            "MqttEntries.ql",
            "JaxRsEntries.ql",
            "GrpcEntries.ql",
        )
        self.assertEqual(len(ENTRY_COLUMNS), 17)
        for query_name in query_names:
            with self.subTest(query=query_name):
                source = (query_root / query_name).read_text(encoding="utf-8")
                self.assertIn("@kind table", source)
                self.assertIn("import java", source)
                for column in ENTRY_COLUMNS:
                    self.assertIn(f'"{column}"', source)
        interposition = (query_root / "EntryInterpositions.ql").read_text(encoding="utf-8")
        self.assertIn("@kind table", interposition)
        self.assertIn("import java", interposition)
        for column in INTERPOSITION_COLUMNS:
            self.assertIn(f'"{column}"', interposition)
        self.assertIn("cfg_action_before_chain_unproven", interposition)
        security = (query_root / "EntrySecurity.ql").read_text(encoding="utf-8")
        self.assertIn("@kind table", security)
        self.assertIn("import java", security)
        for column in SECURITY_COLUMNS:
            self.assertIn(f'"{column}"', security)
        for marker in (
            "PermitAll",
            "isAuthenticated()",
            "ServletSecurity",
            "requestMatchers",
            "permitAll",
            "hasRole",
            "profile:",
            "conditional_property:",
            'value = "optional"',
            "dynamic_security_matcher_partial",
        ):
            self.assertIn(marker, security)
        self.assertNotIn("not hasConditionalDeployment", security)

    def test_security_decoder_has_an_independent_strict_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Controller.java").write_text("class Controller {}\n", encoding="utf-8")
            payload = {
                "#select": {
                    "columns": list(SECURITY_COLUMNS),
                    "tuples": [[
                        "fixture.Controller.publicHandler", "Controller.java", 1,
                        "GET /public", "Controller.java", 1, "annotation",
                        "unauthenticated_annotation", "complete", "permit_all",
                    ]],
                }
            }

            rows = decode_bqrs_json(
                "entry_security",
                payload,
                DecodeSource(root, "a" * 64),
            )

        self.assertEqual("entry_security", rows[0]["query_name"])
        self.assertEqual("Controller.java", rows[0]["fact_file"])

    def test_servlet_query_models_one_helper_jetty_holder_binding(self):
        root = Path(__file__).parents[1]
        content = (root / "codeql/dosweb/Entries/ServletEntries.ql").read_text(encoding="utf-8")
        self.assertIn("org.eclipse.jetty.ee8.servlet", content)
        self.assertIn("helperHolderBinds", content)



@unittest.skipUnless(
    _RUN_FIXTURES and _CODEQL and _JAVAC,
    "Set DOSWEB_RUN_CODEQL_FIXTURES=1 with codeql and javac available.",
)
class CodeqlEntryQueryFixtureTests(unittest.TestCase):
    def test_entry_security_query_extracts_typed_auth_without_inventing_deployment(self):
        root = Path(__file__).parents[1]
        source_root = root / "tests" / "fixtures" / "spring" / "src" / "main" / "java"
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database_path = temporary / "spring-security-database"
            classes = temporary / "spring-security-classes"
            classes.mkdir()
            java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
            completed = subprocess.run(
                [
                    _CODEQL,
                    "database",
                    "create",
                    str(database_path),
                    "--language=java",
                    f"--source-root={source_root}",
                    f"--command={_JAVAC} -d {classes} "
                    + " ".join(str(path) for path in java_files),
                    "--overwrite",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            database = validate_database(database_path)
            query = root / "codeql" / "dosweb" / "Entries" / "EntrySecurity.ql"
            result = run_query(
                query,
                database,
                temporary / "security-results",
                codeql_binary=str(_codeql_wrapper(temporary)),
            )
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
            rows = decode_bqrs_json(
                "entry_security",
                payload,
                DecodeSource(database.source_root, result.query_sha256),
            )

        self.assertTrue(
            any(
                row["handler_fqn"].endswith("SpringFixture.handle")
                and row["kind"] == "annotation"
                and row["value"] == "unauthenticated_annotation"
                and row["coverage_status"] == "complete"
                for row in rows
            ),
            rows,
        )
        self.assertFalse(
            any(
                row["handler_fqn"].endswith("SpringFixture.handle")
                and row["kind"] == "deployment_gate"
                for row in rows
            ),
            rows,
        )

    def test_spel_source_defaults_publish_modeled_entries_and_keep_runtime_gaps(self):
        root = Path(__file__).parents[1]
        source_root = root / "tests" / "fixtures" / "spring" / "src" / "main" / "java"
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            database_path = temporary / "spring-spel-database"
            classes = temporary / "spring-spel-classes"
            classes.mkdir()
            java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
            completed = subprocess.run(
                [
                    _CODEQL,
                    "database",
                    "create",
                    str(database_path),
                    "--language=java",
                    f"--source-root={source_root}",
                    f"--command={_JAVAC} -d {classes} "
                    + " ".join(str(path) for path in java_files),
                    "--overwrite",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            database = validate_database(database_path)
            query = root / "codeql" / "dosweb" / "Entries" / "SpringMvcEntries.ql"
            result = run_query(
                query,
                database,
                temporary / "spring-spel-results",
                codeql_binary=str(_codeql_wrapper(temporary)),
            )
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
            rows = decode_bqrs_json(
                "entries",
                payload,
                DecodeSource(database.source_root, result.query_sha256),
            )

        entries = normalize_entry_rows(rows)
        gaps = normalize_gap_entry_rows(rows)
        self.assertTrue(
            any(
                entry["handler"]["callable"].endswith("SpelController.authenticate")
                and entry["route_or_event"] == "POST /rest/authenticate"
                and entry["registration"]["kind"] == "annotation_mapping"
                for entry in entries
            ),
            entries,
        )
        self.assertTrue(
            any(
                entry["handler"]["callable"].endswith("SpelClassController.image")
                and entry["route_or_event"] == "GET /rest/verify/{type}"
                and entry["registration"]["kind"] == "annotation_mapping"
                for entry in entries
            ),
            entries,
        )
        self.assertTrue(
            any(
                gap["route_or_event"] == "POST /rest/authenticate"
                and gap["coverage_note"]
                == "spring_spel_route_default_requires_runtime_binding"
                for gap in gaps
            ),
            gaps,
        )
        self.assertTrue(
            any(
                gap["route_or_event"] == "GET /rest/verify/{type}"
                and gap["coverage_note"]
                == "spring_spel_class_route_default_requires_runtime_binding"
                for gap in gaps
            ),
            gaps,
        )

    def test_component_filter_with_dependency_framework_types_is_a_default_entry(self):
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            dependency_sources = temporary / "dependency-sources"
            application_sources = temporary / "application-sources"
            dependency_classes = temporary / "dependency-classes"
            application_classes = temporary / "application-classes"
            for directory in (
                dependency_sources,
                application_sources,
                dependency_classes,
                application_classes,
            ):
                directory.mkdir()

            dependencies = {
                "javax/servlet/ServletRequest.java": (
                    "package javax.servlet; public interface ServletRequest {}\n"
                ),
                "javax/servlet/ServletResponse.java": (
                    "package javax.servlet; public interface ServletResponse {}\n"
                ),
                "javax/servlet/FilterChain.java": (
                    "package javax.servlet; public interface FilterChain { "
                    "void doFilter(ServletRequest request, ServletResponse response); }\n"
                ),
                "javax/servlet/Filter.java": (
                    "package javax.servlet; public interface Filter { "
                    "void doFilter(ServletRequest request, ServletResponse response, FilterChain chain); }\n"
                ),
                "org/springframework/stereotype/Component.java": (
                    "package org.springframework.stereotype; "
                    "import java.lang.annotation.*; "
                    "@Retention(RetentionPolicy.RUNTIME) @Target(ElementType.TYPE) "
                    "public @interface Component {}\n"
                ),
            }
            dependency_files = []
            for relative, content in dependencies.items():
                path = dependency_sources / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                dependency_files.append(path)
            completed = subprocess.run(
                [_JAVAC, "-d", str(dependency_classes), *(str(path) for path in dependency_files)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            component_filter = application_sources / "app" / "ComponentFilter.java"
            component_filter.parent.mkdir(parents=True)
            component_filter.write_text(
                "package app;\n"
                "import javax.servlet.*;\n"
                "import org.springframework.stereotype.Component;\n"
                "@Component public class ComponentFilter implements Filter {\n"
                "  public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain) {\n"
                "    chain.doFilter(request, response);\n"
                "  }\n"
                "}\n",
                encoding="utf-8",
            )
            database_path = temporary / "database"
            completed = subprocess.run(
                [
                    _CODEQL,
                    "database",
                    "create",
                    str(database_path),
                    "--language=java",
                    f"--source-root={application_sources}",
                    "--command="
                    f"{_JAVAC} -cp {dependency_classes} -d {application_classes} "
                    "app/ComponentFilter.java",
                    "--overwrite",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            database = validate_database(database_path)
            query = root / "codeql" / "dosweb" / "Entries" / "ServletEntries.ql"
            result = run_query(
                query,
                database,
                temporary / "results",
                codeql_binary=str(_codeql_wrapper(temporary)),
            )
            payload = json.loads(result.decoded_path.read_text(encoding="utf-8"))
            rows = decode_bqrs_json(
                "entries",
                payload,
                DecodeSource(database.source_root, result.query_sha256),
            )
            entries = normalize_entry_rows(rows)
            self.assertTrue(
                any(
                    entry["handler"]["callable"].endswith("ComponentFilter.doFilter")
                    and entry["route_or_event"] == "/*"
                    and entry["registration"]["kind"] == "annotation_mapping"
                    for entry in entries
                ),
                entries,
            )

    def test_registered_entries_and_dynamic_gaps_against_temporary_databases(self):
        root = Path(__file__).parents[1]
        fixtures = {
            "spring": ("SpringMvcEntries.ql", "spring_mvc", "SpringFixture.handle"),
            "servlet": ("ServletEntries.ql", "servlet", "ServletFixture.doPost"),
            "netty": ("NettyEntries.ql", "netty", "RegisteredHandler.channelRead"),
            "mqtt": ("MqttEntries.ql", "mqtt", "NettyMqttHandler.channelRead"),
            "armeria": ("SpringMvcEntries.ql", "spring_mvc", "RegisteredCollector.uploadSpans"),
            "jax_rs": ("JaxRsEntries.ql", "jax_rs", "RegisteredResource.get"),
            "grpc": ("GrpcEntries.ql", "grpc", "RegisteredService.unary"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            codeql_binary = _codeql_wrapper(temporary)
            for fixture, (query_name, framework, handler_suffix) in fixtures.items():
                with self.subTest(framework=framework):
                    source_root = root / "tests" / "fixtures" / fixture / "src" / "main" / "java"
                    database_path = temporary / f"{fixture}-database"
                    classes = temporary / f"{fixture}-classes"
                    classes.mkdir()
                    java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
                    completed = subprocess.run(
                        [
                            _CODEQL,
                            "database",
                            "create",
                            str(database_path),
                            "--language=java",
                            f"--source-root={source_root}",
                            f"--command={_JAVAC} -d {classes} " + " ".join(str(path) for path in java_files),
                            "--overwrite",
                        ],
                        check=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
                    database = validate_database(database_path)
                    query = root / "codeql" / "dosweb" / "Entries" / query_name
                    output = temporary / f"{fixture}-results"
                    try:
                        result = run_query(
                            query,
                            database,
                            output,
                            codeql_binary=str(codeql_binary),
                        )
                        decoded_path = result.decoded_path
                        query_sha256 = result.query_sha256
                    except Exception as exc:
                        if not (
                            getattr(exc, "code", None) == "CODEQL_QUERY_FAILED"
                            and getattr(exc, "details", {}).get("diagnostic")
                            == "database changed during query execution"
                        ):
                            raise
                        bqrs_path = temporary / f"{fixture}.bqrs"
                        decoded_path = temporary / f"{fixture}.json"
                        completed = subprocess.run(
                            [
                                str(codeql_binary),
                                "query",
                                "run",
                                str(query),
                                "--database",
                                str(database.path),
                                "--output",
                                str(bqrs_path),
                            ],
                            check=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )
                        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
                        completed = subprocess.run(
                            [
                                str(codeql_binary),
                                "bqrs",
                                "decode",
                                str(bqrs_path),
                                "--format=json",
                                "--output",
                                str(decoded_path),
                            ],
                            check=False,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )
                        self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
                        from dosweb.artifacts.identifiers import file_sha256

                        query_sha256 = file_sha256(query)
                    payload = json.loads(decoded_path.read_text(encoding="utf-8"))
                    decoded_columns = tuple(
                        column["name"] if isinstance(column, dict) else column
                        for column in payload["#select"]["columns"]
                    )
                    self.assertEqual(decoded_columns, ENTRY_COLUMNS)
                    rows = decode_bqrs_json(
                        "entries",
                        payload,
                        DecodeSource(database.source_root, query_sha256),
                    )
                    if fixture == "servlet":
                        rows, _ = resolve_webxml_servlet_candidates(rows, database.source_root)
                    entries = normalize_entry_rows(rows)
                    coverage = normalize_framework_coverage(rows)
                    self.assertTrue(
                        any(
                            entry["framework"] == framework
                            and entry["handler"]["callable"].endswith(handler_suffix)
                            for entry in entries
                        ),
                        entries,
                    )
                    if fixture == "spring":
                        gaps = normalize_gap_entry_rows(rows)
                        self.assertFalse(any("#{" in entry["route_or_event"] for entry in entries), entries)
                        self.assertTrue(
                            any(
                                gap["route_or_event"] == "POST /rest/authenticate"
                                and gap["coverage_note"] == "spring_spel_route_default_requires_runtime_binding"
                                for gap in gaps
                            ),
                            gaps,
                        )
                        self.assertTrue(
                            any(
                                gap["route_or_event"] == "GET /rest/verify/{type}"
                                and gap["coverage_note"] == "spring_spel_class_route_default_requires_runtime_binding"
                                for gap in gaps
                            ),
                            gaps,
                        )
                    if fixture == "mqtt":
                        broker_handlers = {
                            entry["handler"]["callable"]
                            for entry in entries
                            if entry["registration"]["kind"] == "broker_registration"
                            and entry["route_or_event"] == "mqtt_protocol"
                        }
                        self.assertTrue(
                            any(name.endswith("NettyMqttHandler.channelRead") for name in broker_handlers),
                            entries,
                        )
                        self.assertTrue(
                            any(name.endswith("ConvertedNettyMqttHandler.channelRead") for name in broker_handlers),
                            entries,
                        )
                    if fixture == "netty":
                        full_request_routes = {
                            entry["route_or_event"]
                            for entry in entries
                            if entry["handler"]["callable"].endswith(
                                "FullRequestHandler.channelRead0"
                            )
                        }
                        self.assertEqual(
                            full_request_routes,
                            {"channelRead", "/trigger", "/beat"},
                            entries,
                        )
                        self.assertFalse(
                            any(
                                "LookalikeRequestHandler" in entry["handler"]["callable"]
                                for entry in entries
                            ),
                            entries,
                        )
                    if fixture == "servlet":
                        self.assertTrue(
                            any(
                                entry["handler"]["callable"].endswith("RegisteredStreamFilter.doFilter")
                                and entry["route_or_event"] == "/api/push/*"
                                for entry in entries
                            ),
                            entries,
                        )
                        self.assertTrue(
                            any(
                                entry["handler"]["callable"].endswith("ComponentCachingFilter.doFilter")
                                and entry["route_or_event"] == "/*"
                                and entry["registration"]["kind"] == "annotation_mapping"
                                for entry in entries
                            ),
                            entries,
                        )
                        self.assertTrue(
                            any(
                                entry["handler"]["callable"].endswith("ForwardingServlet.service")
                                and entry["route_or_event"] == "/druid/v2/*"
                                and entry["registration"]["kind"] == "static_registration"
                                for entry in entries
                            ),
                            entries,
                        )
                        self.assertTrue(
                            any(
                                entry["handler"]["callable"].endswith("DescriptorServlet.service")
                                and entry["route_or_event"] == "/descriptor/*"
                                and entry["registration"]["kind"] == "static_registration"
                                for entry in entries
                            ),
                            entries,
                        )
                    if fixture == "armeria":
                        self.assertTrue(
                            any(
                                entry["route_or_event"] == "/api/v2/spans"
                                and entry["registration"]["kind"] == "static_registration"
                                for entry in entries
                            ),
                            entries,
                        )
                    if fixture == "jax_rs":
                        routes = {
                            entry["route_or_event"]
                            for entry in entries
                            if entry["framework"] == framework
                        }
                        self.assertIn("GET /api/items/{id}", routes)
                        self.assertIn("POST /api/items", routes)
                    if fixture == "grpc":
                        self.assertTrue(
                            any(
                                entry["handler"]["callable"].endswith("RegisteredService.unary")
                                and entry["route_or_event"] == "/example.Sample/unary"
                                and entry["materialization_phase"] == "in_handler"
                                for entry in entries
                            ),
                            entries,
                        )
                        self.assertTrue(
                            any(
                                entry["handler"]["callable"].endswith("RequestCollector.onNext")
                                and entry["route_or_event"] == "/example.Sample/collect"
                                and entry["attacker_inputs"] == [{"name": "request", "type": "Request", "kind": "stream"}]
                                and entry["materialization_phase"] == "streaming"
                                and entry["registration"]["kind"] == "static_registration"
                                for entry in entries
                            ),
                            entries,
                        )
                        self.assertFalse(
                            any("RegisteredHelper" in entry["handler"]["callable"] or "responseObserver" in str(entry["attacker_inputs"])
                                for entry in entries),
                            entries,
                        )
                        self.assertTrue(
                            any(
                                entry["handler_fqn"].endswith("UnregisteredClientStreamingService.collect")
                                and entry["registration_kind"] == "dynamic_unresolved"
                                and entry["coverage_status"] == "partial"
                                and entry["coverage_note"] == "grpc_generated_streaming_registration_identity_or_observer_unproven"
                                for entry in rows
                            ),
                            rows,
                        )
                        self.assertFalse(
                            any("UnregisteredClientStreamingService" in entry["handler"]["callable"] for entry in entries),
                            entries,
                        )
                        ternary_handlers = {
                            entry["handler"]["callable"]
                            for entry in entries
                            if entry["route_or_event"] == "/example.Sample/collect"
                            and entry["materialization_phase"] == "streaming"
                        }
                        self.assertTrue(any(name.endswith("TernaryFirstCollector.onNext") for name in ternary_handlers), entries)
                        self.assertTrue(any(name.endswith("TernarySecondCollector.onNext") for name in ternary_handlers), entries)
                        self.assertTrue(
                            any(
                                entry["handler"]["callable"].endswith("ModernCollector.onNext")
                                and entry["route_or_event"] == "/example.Modern/collect"
                                and entry["attacker_inputs"] == [{"name": "request", "type": "Request", "kind": "stream"}]
                                and entry["registration"]["kind"] == "static_registration"
                                for entry in entries
                            ),
                            entries,
                        )
                        self.assertTrue(
                            any(
                                entry["handler"]["callable"].endswith("ForwardingModernCollector.onNext")
                                and entry["route_or_event"] == "/example.ForwardingModern/collect"
                                and entry["attacker_inputs"] == [{"name": "request", "type": "Request", "kind": "stream"}]
                                and entry["registration"]["kind"] == "static_registration"
                                for entry in entries
                            ),
                            entries,
                        )
                        complete_services = ("RegisteredClientStreamingService", "TernaryStreamingService", "ModernAsyncService", "ForwardingModernAsyncService")
                        for service_name in complete_services:
                            self.assertFalse(
                                any(row["handler_fqn"].endswith("." + service_name + ".collect")
                                    and row["coverage_status"] == "partial" for row in rows),
                                (service_name, rows),
                            )
                        self.assertTrue(
                            any(entry["handler"]["callable"].endswith("RequestCollector.onNext")
                                and entry["route_or_event"] == "/example.Sample/collect" for entry in entries),
                            entries,
                        )
                        self.assertTrue(
                            any(
                                entry["handler_fqn"].endswith("UnsupportedLeafService.collect")
                                and entry["coverage_status"] == "partial"
                                for entry in rows
                            ), rows,
                        )
                        self.assertFalse(
                            any(entry["handler"]["callable"].endswith("UnsupportedGoodCollector.onNext")
                                for entry in entries),
                            entries,
                        )
                        self.assertTrue(
                            any(
                                entry["handler_fqn"].endswith("NoIdentityService.collect")
                                and entry["coverage_status"] == "partial"
                                and entry["route_or_event"].endswith("NoIdentityService.collect")
                                for entry in rows
                            ), rows,
                        )
                        self.assertTrue(
                            any(
                                entry["handler_fqn"].endswith("LookalikeService.collect")
                                and entry["coverage_status"] == "partial"
                                and entry["route_or_event"] == "/example.Sample/collect"
                                for entry in rows
                            ), rows,
                        )
                        for service_name in (
                            "NoForwardService", "ReflectionService", "MixedForwardService",
                            "MultiImplementationService", "DuplicateRegistrationService",
                        ):
                            partial_handlers = {
                                row["handler_fqn"] for row in rows
                                if row["handler_fqn"].endswith(service_name + ".collect")
                                and row["coverage_status"] == "partial"
                                and row["route_or_event"] == "/example.Partial/collect"
                            }
                            self.assertTrue(partial_handlers, (service_name, rows))
                            self.assertFalse(
                                any(entry["route_or_event"] == "/example.Partial/collect" for entry in entries),
                                (service_name, entries),
                            )
                        self.assertTrue(
                            any(
                                row["handler_fqn"].endswith("AmbiguousModernAsyncService.collect")
                                and row["route_or_event"] == "/example.AmbiguousModern/collect"
                                and row["coverage_status"] == "partial"
                                for row in rows
                            ),
                            rows,
                        )
                        self.assertFalse(
                            any(entry["route_or_event"] == "/example.AmbiguousModern/collect" for entry in entries),
                            entries,
                        )
                        self.assertFalse(any("FooAsyncService" in row["handler_fqn"] for row in rows), rows)
                        self.assertFalse(any("FooCollector" in entry["handler"]["callable"] for entry in entries), entries)
                        self.assertTrue(
                            any(
                                row["handler_fqn"].endswith("FakeBuilderService.unary")
                                and row["route_or_event"] == "/example.FakeBuilder/unary"
                                and row["coverage_status"] == "partial"
                                for row in rows
                            ),
                            rows,
                        )
                        self.assertFalse(
                            any("FakeBuilderService" in entry["handler"]["callable"] for entry in entries),
                            entries,
                        )
                        self.assertFalse(any("UnsupportedLeafService" in entry["handler"]["callable"] for entry in entries), entries)
                        self.assertFalse(any("NoIdentityService" in entry["handler"]["callable"] for entry in entries), entries)
                        self.assertFalse(any("LookalikeService.helper" in entry["handler_fqn"] for entry in rows), rows)
                    rejected_markers = (
                        ("Unregistered", "Fake", "Dynamic")
                        if fixture == "spring"
                        else ("Unregistered", "Lookalike", "Fake", "Dynamic")
                    )
                    self.assertFalse(
                        any(
                            any(marker in entry["handler"]["callable"] for marker in rejected_markers)
                            or (
                                fixture == "spring"
                                and entry["handler"]["callable"].endswith(
                                    "SpringFixture.unregisteredLookalike"
                                )
                            )
                            or (
                                fixture == "spring"
                                and ".SpringLookalike." in entry["handler"]["callable"]
                            )
                            for entry in entries
                        ),
                        entries,
                    )
                    if fixture not in {"armeria"}:
                        self.assertTrue(
                            any(
                                record["framework"] == framework
                                and record["status"] == "partial"
                                and record["effect_on_verdict"] == "forces_unknown"
                                for record in coverage
                            ),
                            coverage,
                        )
                    if fixture in {"jax_rs", "grpc"}:
                        unresolved_handlers = {
                            row["handler_fqn"]
                            for row in rows
                            if row["framework"] == framework
                            and row["registration_kind"] == "dynamic_unresolved"
                        }
                        self.assertFalse(
                            any(name.endswith(handler_suffix) for name in unresolved_handlers),
                            unresolved_handlers,
                        )
                        self.assertTrue(
                            any("Unregistered" in name for name in unresolved_handlers),
                            unresolved_handlers,
                        )

    def test_filter_registration_interposition_is_partial_until_cfg_proven(self):
        root = Path(__file__).parents[1]
        source_root = root / "tests" / "fixtures" / "interposition" / "src" / "main" / "java"
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            classes = temporary / "classes"; classes.mkdir()
            java_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*.java"))
            database_path = temporary / "database"
            completed = subprocess.run(
                [_CODEQL, "database", "create", str(database_path), "--language=java", f"--source-root={source_root}",
                 f"--command={_JAVAC} -d {classes} " + " ".join(str(path) for path in java_files), "--overwrite"],
                cwd=source_root, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            database = validate_database(database_path)
            result = run_query(root / "codeql" / "dosweb" / "Entries" / "EntryInterpositions.ql", database, temporary / "results", codeql_binary=str(_codeql_wrapper(temporary)))
            rows = decode_bqrs_json("entry_interposition", json.loads(result.decoded_path.read_text(encoding="utf-8")), DecodeSource(database.source_root, result.query_sha256))
            self.assertEqual(len(rows), 3)
            row = next(item for item in rows if item["url_predicate_value"] == "/api/push")
            ambiguous_interposition = next(item for item in rows if item["url_predicate_value"] == "/api/ambiguous")
            unknown_order = next(item for item in rows if item["url_predicate_value"] == "/api/no-order")
            self.assertEqual(ambiguous_interposition["coverage_status"], "partial")
            self.assertEqual(unknown_order["order_status"], "unknown")
            self.assertEqual(unknown_order["coverage_note"], "static_filter_order_unproven")
            self.assertEqual(row["url_predicate_value"], "/api/push")
            self.assertEqual(row["coverage_status"], "partial")
            self.assertFalse(row["action_before_chain"])
            self.assertEqual(row["coverage_note"], "cfg_action_before_chain_unproven")

            association = run_query(
                root / "codeql" / "dosweb" / "Flows" / "EntryToGrowthAssociations.ql",
                database,
                temporary / "association-results",
                codeql_binary=str(_codeql_wrapper(temporary)),
            )
            association_rows = decode_bqrs_json(
                "flow",
                json.loads(association.decoded_path.read_text(encoding="utf-8")),
                DecodeSource(database.source_root, association.query_sha256),
            )
            matching = [
                item for item in association_rows
                if item["source_start_line"] == 14 and item["sink_start_line"] == 10
            ]
            self.assertEqual(len(matching), 1, association_rows)
            self.assertFalse(any(item["source_start_line"] == 30 for item in association_rows), association_rows)
            self.assertEqual(matching[0]["attacker_target"], "key")
            self.assertEqual(matching[0]["coverage_status"], "partial")
            self.assertEqual(
                matching[0]["coverage_note"],
                "transitive_callgraph_association_requires_flow_witness",
            )

            flow = run_query(
                root / "codeql" / "dosweb" / "Flows" / "EntryToGrowth.ql",
                database,
                temporary / "flow-results",
                codeql_binary=str(_codeql_wrapper(temporary)),
            )
            flow_rows = decode_bqrs_json(
                "flow",
                json.loads(flow.decoded_path.read_text(encoding="utf-8")),
                DecodeSource(database.source_root, flow.query_sha256),
            )
            matching_flow = [
                item for item in flow_rows
                if item["source_start_line"] == 14 and item["sink_start_line"] == 10
            ]
            self.assertEqual(len(matching_flow), 1, flow_rows)
            self.assertFalse(any(item["source_start_line"] == 30 for item in flow_rows), flow_rows)
            self.assertEqual(matching_flow[0]["confidence"], "partial")
            self.assertEqual(
                matching_flow[0]["coverage_note"],
                "transitive_callgraph_witness_requires_path_coverage",
            )


if __name__ == "__main__":
    unittest.main()
