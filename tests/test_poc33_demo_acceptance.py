from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dosweb.artifacts.identifiers import sha256_canonical_json
from dosweb.batch.models import (
    CanonicalCorpus,
    CorpusTarget,
    TargetCapability,
    TargetIdentity,
)
from dosweb.batch.plan import (
    build_batch_plan,
    load_batch_plan,
    publish_batch_plan,
    write_target_binding,
)

from scripts.run_poc33_demo_acceptance import (
    PAUSED_EXIT_STATUS,
    build_poc33_selection,
    main,
    validate_entries_archive,
    validate_p0_aggregate,
)

ROOT = Path(__file__).resolve().parents[1]


class Poc33DemoAcceptanceTests(unittest.TestCase):
    def test_acceptance_script_is_directly_executable_from_repository_root(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/run_poc33_demo_acceptance.py"), "--help"],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("poc33-real-provider-full", completed.stdout)

    def _complete_full_archive(self, root: Path) -> None:
        plan = load_batch_plan(root / "batch_plan.json")
        state_targets = {}
        for target in plan.targets:
            target_root = root / "targets" / Path(target.output_path).name
            target_root.mkdir(parents=True)
            write_target_binding(plan, target, target_root)
            audit = target_root / "llm_audit.private.jsonl"
            audit.write_text("", encoding="utf-8")
            audit.chmod(0o600)
            (target_root / "run.json").write_text(json.dumps({
                "schema_version": "2.6",
                "tool_version": "0.5.0",
                "status": "completed",
                "identity": {
                    "analysis_mode": "formal",
                    "query_failure_policy": "fail_closed",
                },
                "stages": {
                    stage: {
                        "status": "completed",
                        **({
                            "metadata": {
                                "query_count": 8,
                                "query_diagnostics": [],
                                "skipped_query_count": 0,
                            },
                        } if stage == "entries" else {}),
                    }
                    for stage in (
                        "entries",
                        "growth",
                        "flows",
                        "lifecycle",
                        "conclude",
                        "report",
                    )
                },
            }), encoding="utf-8")
            state_targets[target.target_id] = {
                "target_id": target.target_id,
                "state": "completed",
                "status": "completed",
                "attempt": 1,
                "output_path": target.output_path,
            }
        (root / "batch_state.json").write_text(json.dumps({
            "schema_version": 1,
            "batch_id": plan.plan_id,
            "mode": "full",
            "status": "completed",
            "created_at": "2026-08-27T12:00:00+00:00",
            "updated_at": "2026-08-27T12:01:00+00:00",
            "targets": state_targets,
        }), encoding="utf-8")

    def _tracked_canonical_corpus(self) -> CanonicalCorpus:
        manifest = ROOT / "intel" / "applications" / "java_web_205_targets.json"
        rows = json.loads(manifest.read_text(encoding="utf-8"))["projects"]
        targets = []
        for row in rows:
            identity = TargetIdentity(
                index=row["index"],
                name=row["name"],
                fingerprint_type=row["fingerprint_type"],
                fingerprint=row["checkout_fingerprint"],
                source_path=row["source_path"],
                database_path=row["codeql_path"],
            )
            targets.append(CorpusTarget(
                identity=identity,
                source=Path(identity.source_path),
                database=Path(identity.database_path),
                capability=TargetCapability(
                    provider_eligible=True,
                    public_source_url=(
                        f"https://github.com/{identity.name}"
                        if identity.fingerprint_type == "git-commit"
                        else None
                    ),
                    attestation=identity.fingerprint_type,
                ),
                database_fingerprint=row["database_fingerprint"],
            ))
        return CanonicalCorpus(
            schema_version=1,
            status="canonical",
            corpus="java-web-205",
            total=205,
            inventory_digest="e" * 64,
            targets=tuple(targets),
            manifest_path=manifest,
        )

    def _complete_entries_archive(self, root: Path, *, query_count: int = 8) -> None:
        plan = load_batch_plan(root / "batch_plan.json")
        state_targets = {}
        for target in plan.targets:
            target_root = root / "targets" / Path(target.output_path).name
            target_root.mkdir(parents=True)
            write_target_binding(plan, target, target_root)
            (target_root / "run.json").write_text(json.dumps({
                "schema_version": "2.6",
                "tool_version": "0.5.0",
                "status": "completed",
                "identity": {
                    "analysis_mode": "exploratory_entries",
                    "query_failure_policy": "coverage_gap",
                },
                "stages": {
                    "entries": {
                        "status": "completed",
                        "metadata": {
                            "query_count": query_count,
                            "query_diagnostics": [],
                            "skipped_query_count": 0,
                        },
                    },
                },
            }), encoding="utf-8")
            state_targets[target.target_id] = {
                "target_id": target.target_id,
                "state": "completed",
                "status": "completed",
                "attempt": 1,
                "output_path": target.output_path,
            }
        (root / "batch_state.json").write_text(json.dumps({
            "schema_version": 1,
            "batch_id": plan.plan_id,
            "mode": "entries",
            "status": "completed",
            "created_at": "2026-08-27T12:00:00+00:00",
            "updated_at": "2026-08-27T12:01:00+00:00",
            "targets": state_targets,
        }), encoding="utf-8")

    def _write_entries_archive(self, root: Path, *, query_count: int = 8) -> None:
        run_id = "poc33-p02-20260827_120000"
        targets = []
        for index in range(1, 22):
            identity = TargetIdentity(
                index=index,
                name=f"selected{index}/repo{index}",
                fingerprint_type="git-commit",
                fingerprint=f"{index:040x}",
                source_path=f"frameworks/applications/selected{index}__repo{index}",
                database_path=f"databases/applications/selected{index}__repo{index}-db",
            )
            targets.append(CorpusTarget(
                identity=identity,
                source=Path(identity.source_path),
                database=Path(identity.database_path),
                capability=TargetCapability(
                    provider_eligible=True,
                    public_source_url=f"https://github.com/{identity.name}",
                    attestation="git-commit",
                ),
                database_fingerprint=f"{index:064x}",
            ))
        corpus = CanonicalCorpus(
            schema_version=1,
            status="canonical",
            corpus="poc33-21",
            total=21,
            inventory_digest="a" * 64,
            targets=tuple(targets),
            manifest_path=Path("selection.json"),
        )
        plan = build_batch_plan(
            corpus,
            run_id=run_id,
            mode="entries",
            output_root=f"results/java_web_dos_batch/{run_id}-entries",
        )
        publish_batch_plan(plan, root)
        selection_unsigned = {
            "format": "dosweb-poc33-selection-v1",
            "run_id": run_id,
            "canonical_manifest_sha256": "b" * 64,
            "canonical_inventory_digest": "c" * 64,
            "truth_manifest_sha256": "d" * 64,
            "truth_record_count": 33,
            "target_count": 21,
            "targets": [
                {
                    "index": target.identity.index,
                    "name": target.identity.name,
                    "source_path": target.identity.source_path,
                    "codeql_path": target.identity.database_path,
                    "fingerprint_type": target.identity.fingerprint_type,
                    "checkout_fingerprint": target.identity.fingerprint,
                    "codeql_built": True,
                }
                for target in targets
            ],
        }
        (root / "selection.json").write_text(
            json.dumps({
                **selection_unsigned,
                "selection_digest": sha256_canonical_json(selection_unsigned),
            }),
            encoding="utf-8",
        )
        self._complete_entries_archive(root, query_count=query_count)

    def test_selection_joins_poc_apps_to_canonical_205_without_reindexing(self) -> None:
        selected_names = [f"selected{i}/repo{i}" for i in range(1, 22)]
        projects = [
            {
                "index": index,
                "name": name,
                "source_path": f"frameworks/applications/{name.replace('/', '__')}",
                "codeql_path": f"databases/applications/{name.replace('/', '__')}-db",
                "fingerprint_type": "git-commit",
                "checkout_fingerprint": f"{index:040x}",
                "codeql_built": True,
            }
            for index, name in enumerate(selected_names, 1)
        ]
        projects.extend(
            {
                "index": index,
                "name": f"other{index}/repo{index}",
                "source_path": f"frameworks/applications/other{index}__repo{index}",
                "codeql_path": f"databases/applications/other{index}__repo{index}-db",
                "fingerprint_type": "git-commit",
                "checkout_fingerprint": f"{index:040x}",
                "codeql_built": True,
            }
            for index in range(22, 206)
        )
        canonical = {
            "schema_version": 1,
            "status": "canonical",
            "corpus": "java-web-205",
            "total": 205,
            "valid_codeql_databases": 205,
            "batch_ready": True,
            "projects": projects,
        }
        truth = [
            {
                "record_id": f"truth-{index:02d}",
                "app": (
                    selected_names[index - 1]
                    if index <= 10
                    else selected_names[index - 1].replace("/", "__")
                ),
            }
            for index in range(1, 22)
        ]
        truth.extend(
            {"record_id": f"truth-extra-{index:02d}", "app": selected_names[index % 21]}
            for index in range(12)
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical_path = root / "java_web_205_targets.json"
            truth_path = root / "manifest.json"
            canonical_path.write_text(json.dumps(canonical), encoding="utf-8")
            truth_path.write_text(json.dumps(truth), encoding="utf-8")

            selection = build_poc33_selection(
                canonical_path,
                truth_path,
                run_id="poc33-p02-20260827_120000",
            )

        self.assertEqual(selection["format"], "dosweb-poc33-selection-v1")
        self.assertEqual(selection["run_id"], "poc33-p02-20260827_120000")
        self.assertEqual(selection["truth_record_count"], 33)
        self.assertEqual(selection["target_count"], 21)
        self.assertEqual(
            [target["name"] for target in selection["targets"]],
            selected_names,
        )
        self.assertEqual(
            [target["index"] for target in selection["targets"]],
            list(range(1, 22)),
        )

    def test_entries_archive_requires_21_completed_targets_and_eight_clean_queries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_entries_archive(root)

            summary = validate_entries_archive(
                root,
                run_id="poc33-p02-20260827_120000",
            )

        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["completed_targets"], 21)
        self.assertEqual(summary["selected_queries"], 21 * 8)
        self.assertEqual(summary["query_diagnostics"], 0)
        self.assertEqual(summary["skipped_queries"], 0)

    def test_entries_archive_rejects_a_seven_query_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_entries_archive(root, query_count=7)

            with self.assertRaisesRegex(ValueError, "exactly 8 selected queries"):
                validate_entries_archive(
                    root,
                    run_id="poc33-p02-20260827_120000",
                )

    def test_real_provider_without_authorization_and_key_pauses_before_selection(self) -> None:
        calls: list[object] = []

        def forbidden_runner(*args: object, **kwargs: object) -> object:
            calls.append((args, kwargs))
            raise AssertionError("paused provider gate must not execute a command")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results_root = root / "results"
            status = main(
                [
                    "poc33-real-provider-full",
                    "--run-id",
                    "poc33-p02-20260827_120000",
                    "--repo-root",
                    str(root),
                    "--results-root",
                    str(results_root),
                ],
                environ={},
                command_runner=forbidden_runner,
            )
            prerequisite = json.loads(
                (
                    results_root
                    / "poc33-p02-20260827_120000-provider-prerequisite.json"
                ).read_text(encoding="utf-8")
            )

            self.assertFalse(
                (results_root / "poc33-p02-20260827_120000-full").exists()
            )

        self.assertEqual(status, PAUSED_EXIT_STATUS)
        self.assertEqual(calls, [])
        self.assertEqual(
            prerequisite["status"], "paused_by_provider_prerequisite"
        )
        self.assertEqual(
            prerequisite["reason_codes"],
            ["REMOTE_LLM_AUTHORIZATION_MISSING", "REMOTE_LLM_API_KEY_MISSING"],
        )

    def test_fast_layer_runs_compileall_and_network_free_pytest(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((command, kwargs))
            stdout = "" if "compileall" in command else "321 passed, 7 skipped in 1.25s\n"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status = main(
                ["fast", "--repo-root", str(root)],
                environ={"DEEPSEEK_API_KEY": "must-not-propagate", "PATH": "/bin"},
                command_runner=runner,
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            [command for command, _ in calls],
            [
                [sys.executable, "-m", "compileall", "-q", "dosweb", "scripts", "tests"],
                [sys.executable, "-m", "pytest", "-q"],
            ],
        )
        self.assertTrue(all(kwargs["cwd"] == root for _, kwargs in calls))
        self.assertTrue(
            all("DEEPSEEK_API_KEY" not in kwargs["env"] for _, kwargs in calls)
        )

    def test_codeql_fixture_layer_sets_only_the_fixture_switch(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="44 passed, 100 subtests passed in 3.0s\n",
                stderr="",
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status = main(
                ["codeql-fixtures", "--repo-root", str(root)],
                environ={"DEEPSEEK_API_KEY": "must-not-propagate", "PATH": "/bin"},
                command_runner=runner,
            )

        self.assertEqual(status, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0][0],
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_codeql_entry_queries.py",
                "tests/test_codeql_growth_queries.py",
                "tests/test_codeql_lifecycle_queries.py",
                "tests/test_production_e2e.py",
            ],
        )
        environment = calls[0][1]["env"]
        self.assertIsInstance(environment, dict)
        self.assertEqual(environment["DOSWEB_RUN_CODEQL_FIXTURES"], "1")
        self.assertNotIn("DEEPSEEK_API_KEY", environment)

    def test_entries_layer_builds_a_fresh_plan_runs_batch_and_audits_21_by_8(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []
        corpus = self._tracked_canonical_corpus()

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((command, kwargs))
            output = Path(command[command.index("--output") + 1])
            self._complete_entries_archive(output)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temporary:
            repo_root = Path(temporary) / "repo"
            repo_root.mkdir()
            results_root = Path(temporary) / "results"
            run_id = "poc33-p02-20260827_120000"
            status = main(
                [
                    "poc33-entries",
                    "--run-id",
                    run_id,
                    "--repo-root",
                    str(repo_root),
                    "--results-root",
                    str(results_root),
                    "--canonical-manifest",
                    str(ROOT / "intel/applications/java_web_205_targets.json"),
                    "--truth-manifest",
                    str(ROOT / "poc/manifest.json"),
                ],
                environ={"DEEPSEEK_API_KEY": "must-not-propagate", "PATH": "/bin"},
                command_runner=runner,
                corpus_loader=lambda *args, **kwargs: corpus,
            )
            output = results_root / f"{run_id}-entries"
            acceptance = json.loads(
                (output / "acceptance_manifest.json").read_text(encoding="utf-8")
            )
            selection = json.loads(
                (output / "selection.json").read_text(encoding="utf-8")
            )
            plan = load_batch_plan(output / "batch_plan.json")

        self.assertEqual(status, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][0:3], [
            sys.executable,
            str(ROOT / "scripts/run_java_web_dos_batch.py"),
            "entries",
        ])
        self.assertIn("--no-resume", calls[0][0])
        self.assertEqual(calls[0][0][calls[0][0].index("--max-workers") + 1], "3")
        self.assertNotIn("DEEPSEEK_API_KEY", calls[0][1]["env"])
        self.assertEqual(selection["run_id"], run_id)
        self.assertEqual(selection["target_count"], 21)
        self.assertEqual(plan.run_id, run_id)
        self.assertEqual(plan.mode, "entries")
        self.assertEqual(acceptance["status"], "completed")
        self.assertEqual(acceptance["completed_targets"], 21)
        self.assertEqual(acceptance["selected_queries"], 168)

    def test_authorized_full_layer_runs_formal_batch_then_p0_aggregate(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []
        corpus = self._tracked_canonical_corpus()

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append((command, kwargs))
            if command[1].endswith("run_java_web_dos_batch.py"):
                output = Path(command[command.index("--output") + 1])
                self._complete_full_archive(output)
            elif command[1].endswith("aggregate_java_web_dos_batch.py"):
                output = Path(command[command.index("--batch-root") + 1])
                plan = load_batch_plan(output / "batch_plan.json")
                (output / "aggregate_status.jsonl").write_text(
                    "".join(
                        json.dumps({
                            "batch_target_index": target.identity.index,
                            "batch_target_name": target.identity.name,
                            "batch_target_slug": target.identity.slug,
                            "batch_plan_id": plan.plan_id,
                            "batch_plan_digest": plan.plan_digest,
                            "batch_mode": "full",
                            "status": "completed",
                            "authoritative_status": "completed",
                        }) + "\n"
                        for target in plan.targets
                    ),
                    encoding="utf-8",
                )
                (output / "aggregate_finding_families.jsonl").write_text(
                    "", encoding="utf-8"
                )
            else:
                raise AssertionError(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temporary:
            repo_root = Path(temporary) / "repo"
            repo_root.mkdir()
            results_root = Path(temporary) / "results"
            run_id = "poc33-p02-20260827_120000"
            status = main(
                [
                    "poc33-real-provider-full",
                    "--run-id",
                    run_id,
                    "--repo-root",
                    str(repo_root),
                    "--results-root",
                    str(results_root),
                    "--canonical-manifest",
                    str(ROOT / "intel/applications/java_web_205_targets.json"),
                    "--truth-manifest",
                    str(ROOT / "poc/manifest.json"),
                    "--allow-remote-llm",
                    "--max-workers",
                    "1",
                ],
                environ={"DEEPSEEK_API_KEY": "fixture-key", "PATH": "/bin"},
                command_runner=runner,
                corpus_loader=lambda *args, **kwargs: corpus,
            )
            output = results_root / f"{run_id}-full"
            acceptance = json.loads(
                (output / "acceptance_manifest.json").read_text(encoding="utf-8")
            )
            plan = load_batch_plan(output / "batch_plan.json")
            with self.assertRaisesRegex(ValueError, "run identity"):
                validate_p0_aggregate(output, run_id=f"{run_id}-different")

        self.assertEqual(status, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(plan.run_id, run_id)
        self.assertEqual(plan.mode, "full")
        self.assertIs(plan.provider["allow_remote_llm"], True)
        self.assertIn("--allow-remote-llm", calls[0][0])
        self.assertIn("--no-resume", calls[0][0])
        self.assertEqual(calls[0][0][calls[0][0].index("--max-workers") + 1], "1")
        self.assertEqual(calls[0][1]["env"]["DEEPSEEK_API_KEY"], "fixture-key")
        self.assertEqual(
            calls[1][0][0:2],
            [sys.executable, str(ROOT / "scripts/aggregate_java_web_dos_batch.py")],
        )
        self.assertEqual(acceptance["status"], "completed")
        self.assertEqual(acceptance["completed_targets"], 21)
        self.assertEqual(acceptance["private_audit_mode"], "0600")
        self.assertEqual(acceptance["aggregate_completed_targets"], 21)

    def test_offline_eval_keeps_one_run_id_and_enforces_rollout_gates(self) -> None:
        corpus = self._tracked_canonical_corpus()

        def full_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if command[1].endswith("run_java_web_dos_batch.py"):
                output = Path(command[command.index("--output") + 1])
                self._complete_full_archive(output)
            elif command[1].endswith("aggregate_java_web_dos_batch.py"):
                output = Path(command[command.index("--batch-root") + 1])
                plan = load_batch_plan(output / "batch_plan.json")
                (output / "aggregate_status.jsonl").write_text(
                    "".join(
                        json.dumps({
                            "batch_target_index": target.identity.index,
                            "batch_target_name": target.identity.name,
                            "batch_target_slug": target.identity.slug,
                            "batch_plan_id": plan.plan_id,
                            "batch_plan_digest": plan.plan_digest,
                            "batch_mode": "full",
                            "status": "completed",
                            "authoritative_status": "completed",
                        }) + "\n"
                        for target in plan.targets
                    ),
                    encoding="utf-8",
                )
                (output / "aggregate_finding_families.jsonl").write_text(
                    json.dumps({
                        "family_id": "family:1",
                        "member_finding_ids": ["finding:1"],
                        "verdict": "static_unknown",
                    }) + "\n",
                    encoding="utf-8",
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        offline_calls: list[list[str]] = []

        def offline_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            offline_calls.append(command)
            output = Path(command[command.index("--output") + 1])
            output.mkdir(parents=True)
            if command[1].endswith("generate_poc33_recall.py"):
                dispositions = [
                    {"record_id": f"supported:{index}", "status": "full_chain_finding"}
                    for index in range(29)
                ]
                dispositions.extend(
                    {
                        "record_id": f"deferred:{index}",
                        "status": "growth_only",
                        "reason_codes": [
                            "ENTRY_DYNAMIC_REGISTRATION_UNPROVEN",
                            "GROWTH_SINK_MATCHED",
                        ],
                    }
                    for index in range(4)
                )
                (output / "truth_dispositions.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in dispositions),
                    encoding="utf-8",
                )
                (output / "summary.json").write_text(
                    json.dumps({"total": 33, "full_chain_finding_count": 29}),
                    encoding="utf-8",
                )
            elif command[1].endswith("evaluate_poc33_demo.py"):
                (output / "metrics.json").write_text(json.dumps({
                    "format": "dosweb-poc33-demo-evaluation-v1",
                    "targets": 21,
                    "completed_targets": 21,
                    "formal_completed": True,
                    "selected_queries": 168,
                    "query_diagnostics": 0,
                    "skipped_queries": 0,
                    "truth": 33,
                    "explicit_deferred": 4,
                    "supported_chain_recall": {
                        "numerator": 29,
                        "denominator": 29,
                        "ratio": 1.0,
                    },
                    "eligible_positive": 6,
                    "hard_negative": 15,
                    "ordinary_positive_recall": {
                        "numerator": 5,
                        "denominator": 6,
                        "ratio": 0.833333,
                    },
                    "hard_negative_safety": {
                        "numerator": 15,
                        "denominator": 15,
                        "ratio": 1.0,
                    },
                    "hard_negative_static_vulnerable": 0,
                    "precision": 0.5,
                }), encoding="utf-8")
                (output / "case_matrix.jsonl").write_text("", encoding="utf-8")
                (output / "REPORT.md").write_text("# report\n", encoding="utf-8")
            else:
                raise AssertionError(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temporary:
            repo_root = Path(temporary) / "repo"
            repo_root.mkdir()
            results_root = Path(temporary) / "results"
            dynamic = Path(temporary) / "dynamic"
            dynamic.mkdir()
            run_id = "poc33-p02-20260827_120000"
            common = [
                "--run-id", run_id,
                "--repo-root", str(repo_root),
                "--results-root", str(results_root),
                "--canonical-manifest",
                str(ROOT / "intel/applications/java_web_205_targets.json"),
                "--truth-manifest", str(ROOT / "poc/manifest.json"),
            ]
            self.assertEqual(0, main(
                ["poc33-real-provider-full", *common, "--allow-remote-llm"],
                environ={"DEEPSEEK_API_KEY": "fixture-key", "PATH": "/bin"},
                command_runner=full_runner,
                corpus_loader=lambda *args, **kwargs: corpus,
            ))

            status = main(
                ["poc33-offline-eval", *common, "--dynamic", str(dynamic)],
                environ={"DEEPSEEK_API_KEY": "must-not-propagate", "PATH": "/bin"},
                command_runner=offline_runner,
                corpus_loader=lambda *args, **kwargs: corpus,
            )
            recall = results_root / f"{run_id}-recall"
            evaluation = results_root / f"{run_id}-eval"
            recall_manifest = json.loads(
                (recall / "run_manifest.json").read_text(encoding="utf-8")
            )
            evaluation_manifest = json.loads(
                (evaluation / "run_manifest.json").read_text(encoding="utf-8")
            )
            gate = json.loads((evaluation / "gate.json").read_text(encoding="utf-8"))
            blockers = json.loads(
                (evaluation / "blocker_matrix.json").read_text(encoding="utf-8")
            )

        self.assertEqual(status, 0)
        self.assertEqual(len(offline_calls), 2)
        self.assertNotIn("--static-audit", offline_calls[1])
        self.assertEqual(recall_manifest["run_id"], run_id)
        self.assertEqual(evaluation_manifest["run_id"], run_id)
        self.assertEqual(gate["status"], "passed")
        self.assertIs(gate["rollout_178_target_full"], True)
        self.assertEqual(blockers["total_blockers"], 0)


if __name__ == "__main__":
    unittest.main()
