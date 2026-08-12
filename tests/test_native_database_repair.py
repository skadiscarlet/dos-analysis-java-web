from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.repair_java_web_205_databases import _latest_attestations, _valid_attestation

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.codeql.native_builder import (
    NativeBuildSpec,
    build_native_database,
    default_java_homes,
    discover_native_build,
    promote_database,
    validate_native_command,
    validate_run_id,
)


class NativeDatabaseRepairTests(unittest.TestCase):
    def test_only_native_build_commands_are_accepted(self):
        cases = (
            ("mvn -B -DskipTests compile", "maven"),
            ("sh ./mvnw -B -DskipTests package", "maven"),
            ("sh ./gradlew --no-daemon assemble -x test", "gradle"),
            ("ant -Dskip.tests=true jar", "ant"),
        )
        for command, expected in cases:
            with self.subTest(command=command):
                kind, normalized = validate_native_command(command)
                self.assertEqual(expected, kind)
                self.assertEqual(command, normalized)

    def test_source_only_bounded_and_runtime_commands_are_rejected(self):
        commands = (
            "codeql database create db --build-mode=none",
            "sh scripts/codeql_bounded_javac.sh src/main/java",
            "mvn -Dallow_compilation_failure=true compile",
            "sh ./gradlew bootRun",
            "mvn test",
            "mvn deploy",
            "mvn compile && curl https://example.invalid",
        )
        for command in commands:
            with self.subTest(command=command):
                with self.assertRaises(ValueError):
                    validate_native_command(command)

    def test_default_java_homes_accepts_installed_legacy_and_current_toolchains(self):
        homes = default_java_homes()
        for version in (25, 11, 8):
            installed = Path(f"/usr/lib/jvm/java-{version}-openjdk")
            if (installed / "bin/java").is_file():
                self.assertIn(installed, homes)

    def test_discovery_supports_a_safe_nested_build_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            nested = source / "backend"
            nested.mkdir()
            (nested / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
            java_home = source / "jdk"
            (java_home / "bin").mkdir(parents=True)
            (java_home / "bin/java").write_text("", encoding="utf-8")
            spec = discover_native_build(
                source,
                "owner/repo",
                {
                    "working_directory": "backend",
                    "java_homes": [str(java_home)],
                },
            )
        self.assertEqual("gradle", spec.kind)
        self.assertEqual("backend", spec.working_directory)

    def test_discovery_rejects_an_unsafe_nested_build_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            with self.assertRaises(ValueError):
                discover_native_build(
                    source,
                    "owner/repo",
                    {"working_directory": "../escape", "java_homes": []},
                )

    def test_discovery_prefers_wrappers_and_requires_available_jdk(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")
            java_home = source / "jdk"
            (java_home / "bin").mkdir(parents=True)
            (java_home / "bin/java").write_text("", encoding="utf-8")
            spec = discover_native_build(
                source,
                "owner/repo",
                {"java_homes": [str(java_home)]},
            )
        self.assertIsInstance(spec, NativeBuildSpec)
        self.assertEqual("maven", spec.kind)
        self.assertIn("./mvnw", spec.command)

    def test_discovery_validates_native_setup_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "pom.xml").write_text("<project/>", encoding="utf-8")
            java_home = source / "jdk"
            (java_home / "bin").mkdir(parents=True)
            (java_home / "bin/java").write_text("", encoding="utf-8")
            spec = discover_native_build(
                source,
                "owner/repo",
                {
                    "command": "mvn -B compile",
                    "setup_commands": ["mvn -B -N install"],
                    "java_homes": [str(java_home)],
                },
            )
            self.assertEqual(("mvn -B -N install",), spec.setup_commands)
            with self.assertRaises(ValueError):
                discover_native_build(
                    source,
                    "owner/repo",
                    {
                        "command": "mvn -B compile",
                        "setup_commands": ["mvn test"],
                        "java_homes": [str(java_home)],
                    },
                )

    def test_maven_capture_uses_repository_owned_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "frameworks" / "applications" / "owner__repo"
            source.mkdir(parents=True)
            (source / "pom.xml").write_text("<project/>", encoding="utf-8")
            database_root = root / "databases" / "applications"
            database_root.mkdir(parents=True)
            java_home = root / "jdk"
            (java_home / "bin").mkdir(parents=True)
            (java_home / "bin/java").write_text("", encoding="utf-8")
            observed = {}

            def runner(argv, **kwargs):
                observed["argv"] = argv
                observed["env"] = kwargs["env"]
                return mock.Mock(returncode=2)

            with mock.patch(
                "dosweb.codeql.native_builder._fingerprint",
                return_value=("git-commit", "a" * 40),
            ):
                build_native_database(
                    repository="owner/repo",
                    source=source,
                    target=database_root / "owner__repo-db",
                    spec=NativeBuildSpec(
                        "owner/repo",
                        "maven",
                        "mvn -B compile",
                        (java_home,),
                    ),
                    run_id="native-settings-test",
                    database_root=database_root,
                    result_root=root / "results",
                    timeout_seconds=60,
                    process_runner=runner,
                )

        self.assertIn(f"--working-dir={source}", observed["argv"])
        self.assertNotIn("MAVEN_ARGS", observed["env"])
        effective_command = observed["argv"][-1]
        self.assertIn("--settings", effective_command)
        self.assertIn("config/native_maven_settings.xml", effective_command)
        self.assertIn("-Dmaven.repo.local=", effective_command)
        self.assertIn("results/maven-repository", effective_command)

    def test_maven_setup_commands_share_isolated_repository_before_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "frameworks" / "applications" / "owner__repo"
            source.mkdir(parents=True)
            (source / "pom.xml").write_text("<project/>", encoding="utf-8")
            database_root = root / "databases" / "applications"
            database_root.mkdir(parents=True)
            java_home = root / "jdk"
            (java_home / "bin").mkdir(parents=True)
            (java_home / "bin/java").write_text("", encoding="utf-8")
            observed = []

            def runner(argv, **kwargs):
                observed.append(list(argv))
                return mock.Mock(returncode=2 if argv[0] == "codeql" else 0)

            with mock.patch(
                "dosweb.codeql.native_builder._fingerprint",
                return_value=("git-commit", "a" * 40),
            ):
                result = build_native_database(
                    repository="owner/repo",
                    source=source,
                    target=database_root / "owner__repo-db",
                    spec=NativeBuildSpec(
                        "owner/repo",
                        "maven",
                        "mvn -B compile",
                        (java_home,),
                        ".",
                        ("mvn -B -N install",),
                    ),
                    run_id="native-setup-test",
                    database_root=database_root,
                    result_root=root / "results",
                    timeout_seconds=60,
                    process_runner=runner,
                )

        self.assertEqual("failed", result.status)
        self.assertEqual("mvn", observed[0][0])
        self.assertEqual("codeql", observed[1][0])
        setup_command = " ".join(observed[0])
        capture_command = observed[1][-1]
        self.assertIn("--settings", setup_command)
        self.assertIn("results/maven-repository", setup_command)
        self.assertIn("results/maven-repository", capture_command)
        self.assertEqual(1, len(result.record["setup_results"]))

    def test_attestation_digest_is_required_and_corrupt_lines_are_ignored(self):
        row = {
            "schema_version": 1,
            "repository": "owner/repo",
            "status": "success",
            "source_fingerprint_type": "git-commit",
            "source_fingerprint_before": "a" * 40,
            "source_fingerprint_after": "a" * 40,
            "database_path": "/tmp/owner__repo-db",
            "database_fingerprint": "b" * 64,
            "build_kind": "maven",
            "build_command": "mvn -B compile",
            "setup_commands": [],
            "setup_results": [],
            "working_directory": ".",
            "java_home": "/jdk",
        }
        row["attestation_digest"] = sha256_canonical_json(row)
        self.assertTrue(_valid_attestation(row))
        tampered = dict(row)
        tampered["database_fingerprint"] = "c" * 64
        self.assertFalse(_valid_attestation(tampered))
        tampered_setup = dict(row)
        tampered_setup["setup_commands"] = ["mvn -B -N install"]
        self.assertFalse(_valid_attestation(tampered_setup))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "attestations.jsonl"
            path.write_text("{bad json\n" + json.dumps(row) + "\n", encoding="utf-8")
            loaded = _latest_attestations(path)
        self.assertEqual(row, loaded["owner/repo"])

    def test_source_drift_preserves_completed_candidate_for_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "frameworks" / "applications" / "owner__repo"
            source.mkdir(parents=True)
            (source / "pom.xml").write_text("<project/>", encoding="utf-8")
            database_root = root / "databases" / "applications"
            database_root.mkdir(parents=True)
            java_home = root / "jdk"
            (java_home / "bin").mkdir(parents=True)
            (java_home / "bin/java").write_text("", encoding="utf-8")

            def runner(argv, **kwargs):
                Path(argv[3]).mkdir(parents=True)
                return mock.Mock(returncode=0)

            with mock.patch(
                "dosweb.codeql.native_builder._fingerprint",
                side_effect=(("tree-sha256", "a" * 64), ("tree-sha256", "b" * 64)),
            ):
                result = build_native_database(
                    repository="owner/repo",
                    source=source,
                    target=database_root / "owner__repo-db",
                    spec=NativeBuildSpec("owner/repo", "maven", "mvn -B compile", (java_home,)),
                    run_id="source-drift-test",
                    database_root=database_root,
                    result_root=root / "results",
                    timeout_seconds=60,
                    process_runner=runner,
                )

            recovery = Path(str(result.record["recovery_candidate"]))
            self.assertEqual("failed", result.status)
            self.assertEqual("SOURCE_FINGERPRINT_DRIFT", result.record["reason"])
            self.assertTrue(recovery.is_dir())
            self.assertTrue(recovery.name.endswith(".source-drift"))

    def test_nested_build_root_is_passed_to_codeql(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "frameworks" / "applications" / "owner__repo"
            nested = source / "backend"
            nested.mkdir(parents=True)
            (nested / "pom.xml").write_text("<project/>", encoding="utf-8")
            database_root = root / "databases" / "applications"
            database_root.mkdir(parents=True)
            java_home = root / "jdk"
            (java_home / "bin").mkdir(parents=True)
            (java_home / "bin/java").write_text("", encoding="utf-8")
            observed = {}

            def runner(argv, **kwargs):
                observed["argv"] = argv
                return mock.Mock(returncode=2)

            with mock.patch(
                "dosweb.codeql.native_builder._fingerprint",
                return_value=("git-commit", "a" * 40),
            ):
                build_native_database(
                    repository="owner/repo",
                    source=source,
                    target=database_root / "owner__repo-db",
                    spec=NativeBuildSpec(
                        "owner/repo",
                        "maven",
                        "mvn -B compile",
                        (java_home,),
                        "backend",
                    ),
                    run_id="nested-root-test",
                    database_root=database_root,
                    result_root=root / "results",
                    timeout_seconds=60,
                    process_runner=runner,
                )
        self.assertIn(f"--working-dir={nested}", observed["argv"])

    def test_promotion_quarantines_invalid_database_and_rolls_forward(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate"
            target = root / "repo-db"
            quarantine = root / "quarantine" / "repo-db"
            candidate.mkdir()
            target.mkdir()
            (candidate / "new").write_text("new", encoding="utf-8")
            (target / "old").write_text("old", encoding="utf-8")
            status = promote_database(candidate, target, quarantine)
            self.assertEqual("replaced_invalid", status)
            self.assertTrue((target / "new").is_file())
            self.assertTrue((quarantine / "old").is_file())
            self.assertFalse(candidate.exists())

    def test_promotion_refuses_symlinked_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate"
            actual = root / "actual"
            target = root / "repo-db"
            candidate.mkdir()
            actual.mkdir()
            target.symlink_to(actual, target_is_directory=True)
            with self.assertRaises(ValueError):
                promote_database(candidate, target, root / "quarantine" / "repo-db")

    def test_run_id_is_path_safe(self):
        self.assertEqual("java-web-205-native-1", validate_run_id("java-web-205-native-1"))
        for value in ("", "../escape", "with space", "a/b"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_run_id(value)


if __name__ == "__main__":
    unittest.main()
