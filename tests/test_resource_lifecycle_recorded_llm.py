from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from dosweb.cli import main
from dosweb.resource_lifecycle.adapters import extracted_from_dict
from dosweb.resource_lifecycle import commands as lifecycle_commands


def _analyze_worker(arguments: list[str], completed: object, results: object) -> None:
    status = main(arguments)
    completed.set()  # type: ignore[attr-defined]
    results.put(status)  # type: ignore[attr-defined]


def _paused_after_prepare_analyze_worker(
    arguments: list[str],
    prepared: object,
    competitor_completed: object,
    results: object,
) -> None:
    original = lifecycle_commands._prepare_analyze_output

    def paused(output: Path, llm_mode: str) -> None:
        original(output, llm_mode)
        prepared.set()  # type: ignore[attr-defined]
        competitor_completed.wait(1.0)  # type: ignore[attr-defined]

    lifecycle_commands._prepare_analyze_output = paused
    results.put(main(arguments))  # type: ignore[attr-defined]


def _paused_before_replay_publish_worker(
    run: str,
    publish_ready: object,
    analyze_completed: object,
    results: object,
) -> None:
    original = lifecycle_commands.atomic_write_json

    def paused(path: Path, value: object) -> None:
        if path.name == "replay.json":
            publish_ready.set()  # type: ignore[attr-defined]
            analyze_completed.wait(1.0)  # type: ignore[attr-defined]
        original(path, value)

    lifecycle_commands.atomic_write_json = paused
    results.put(main(["resource-replay", "--run", run]))  # type: ignore[attr-defined]


class ResourceLifecycleRecordedLlmTests(unittest.TestCase):
    def _facts(
        self,
        root: Path,
        *,
        second_resource: bool = False,
        auxiliary_source: str | None = None,
        precise_columns: bool = False,
        unknown_at_create: bool = False,
    ) -> Path:
        source = root / "source"
        source.mkdir()
        (source / "Fixture.java").write_text(
            "final class Fixture {\n  Object field;\n  void handle() {}\n}\n",
            encoding="utf-8",
        )
        if auxiliary_source is not None:
            (source / "Wrapper.java").write_text(auxiliary_source, encoding="utf-8")
        common = {
            "unit_id": "java-callable-v1:fixture.Fixture.handle()V",
            "site_file": "Fixture.java",
            "site_start_column": 1,
            "instance_key": "Fixture.java:1:1:fixture.Resource",
            "resource_type": "fixture.Resource",
            "requires_close": True,
            "holder_kind": "none",
            "holder_scope": "none",
            "holder_key": "none",
            "target_event": "none",
            "capacity": "unknown",
            "normal_path": True,
            "exceptional_path": True,
            "source_evidence": "recorded_static_fact",
            "coverage_status": "complete",
            "coverage_note": "exact",
        }
        rows = [
            {**common, "site_start_line": 1, "fact_kind": "create"},
            {
                **common,
                "site_start_line": 3,
                "fact_kind": "retain",
                "holder_kind": "field",
                "holder_scope": "instance",
                "holder_key": "fixture.Fixture.field",
                "exceptional_path": False,
            },
            {**common, "site_start_line": 3, "fact_kind": "release"},
            {
                **common,
                "site_start_line": 3,
                "fact_kind": "unknown_call",
                "source_evidence": "codeql_unmodeled_argument_escape",
                "coverage_status": "partial",
                "coverage_note": "callee_resource_effects_unmodeled",
                "target_event": "java-callable-v1:fixture.Wrapper.retain(Lfixture/Resource;)V",
            },
            {
                **common,
                "site_start_line": 4,
                "fact_kind": "unknown_call",
                "source_evidence": "codeql_unmodeled_argument_escape",
                "coverage_status": "partial",
                "coverage_note": "callee_resource_effects_unmodeled",
                "target_event": "java-callable-v1:fixture.Wrapper.release(Lfixture/Resource;)V",
            },
        ]
        if precise_columns:
            for row, column in zip(rows, (1, 3, 8, 30, 3), strict=True):
                row["site_start_column"] = column
        if unknown_at_create:
            rows[3]["site_start_line"] = rows[0]["site_start_line"]
            rows[3]["site_start_column"] = rows[0]["site_start_column"]
        if second_resource:
            rows.extend(
                [
                    {
                        **common,
                        "site_start_line": 1,
                        "fact_kind": "create",
                        "instance_key": "Fixture.java:1:2:fixture.OtherResource",
                        "resource_type": "fixture.OtherResource",
                    },
                    {
                        **common,
                        "site_start_line": 2,
                        "fact_kind": "retain",
                        "instance_key": "Fixture.java:1:2:fixture.OtherResource",
                        "resource_type": "fixture.OtherResource",
                        "holder_kind": "field",
                        "holder_scope": "instance",
                        "holder_key": "fixture.Fixture.otherField",
                    },
                ]
            )
        (root / "rows.json").write_text(json.dumps(rows), encoding="utf-8")
        manifest = {
            "schema_version": "1.0",
            "mode": "static_verified_json",
            "rows": "rows.json",
            "source_root": "source",
            "query_sha256": "a" * 64,
            "entry_methods": [common["unit_id"]],
            "budget": {"max_steps": 64, "max_updates_per_event": 8, "timeout_ms": 1000},
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        output = root / "facts"
        self.assertEqual(
            0,
            main(
                [
                    "resource-extract",
                    "--manifest",
                    str(root / "manifest.json"),
                    "--out",
                    str(output),
                ]
            ),
        )
        return output / "facts.json"

    def _recording(
        self,
        root: Path,
        facts_path: Path,
        *,
        target_known_effect: bool = False,
        use_local_retain: bool = False,
    ) -> Path:
        extracted = extracted_from_dict(json.loads(facts_path.read_text(encoding="utf-8")))
        unit = extracted.units[0]
        effects = [effect for transition in unit.program.transitions for effect in transition.effects]
        unknown = next(effect for effect in effects if effect.kind == "unknown_call")
        holders = {holder.holder_id: holder for holder in unit.program.holders}
        retain = next(
            effect
            for effect in effects
            if effect.kind == "retain"
            and effect.holder_id is not None
            and effect.instance_id == unknown.instance_id
            and holders[effect.holder_id].kind
            in ({"local", "request_stack"} if use_local_retain else {"field"})
        )
        release = next(effect for effect in effects if effect.kind == "release")
        llm_location = replace(unknown.location, extractor_version="recorded-summary-v1", source_kind="llm_proposed")
        proposed_retain = replace(
            retain,
            effect_id="effect:llm-proposed-retain",
            location=llm_location,
        )
        proposed_release = replace(
            release,
            effect_id="effect:llm-proposed-release",
            location=llm_location,
        )
        source_fact = next(
            fact for fact in extracted.facts if fact.fact_id in unknown.evidence_ids
        )
        snippet = (root / "source" / source_fact.location.path).read_text(encoding="utf-8").splitlines(keepends=True)[
            source_fact.location.start_line - 1
        ]
        model = "recorded-model"
        contract_version = "summary-contract-v1"
        request = {
            "unknown_effect_id": unknown.effect_id,
            "method": source_fact.target_event,
            "source_path": unknown.location.path,
            "start_line": unknown.location.start_line,
            "end_line": unknown.location.end_line,
            "start_column": source_fact.site_start_column,
            "source_sha256": unknown.location.source_sha256,
            "source_snapshot_sha256": extracted.coverage["source_snapshot_sha256"],
            "snippet_sha256": hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
            "signature": source_fact.target_event,
            "model": model,
            "contract_version": contract_version,
        }
        proposal = {
            "summary_id": "summary:recorded-wrapper",
            "method": source_fact.target_event,
            "preconditions": [f"resource identity is {unknown.instance_id}"],
            "normal_effects": [asdict(proposed_retain), asdict(proposed_release)],
            "exceptional_effects": [],
            "captures": [],
            "field_saves": [str(retain.holder_id)],
            "location": asdict(llm_location),
            "evidence_ids": sorted(set(proposed_retain.evidence_ids + proposed_release.evidence_ids)),
            "source_kind": "llm_proposed",
        }
        recording = {
            "schema_version": "resource-lifecycle-summary-recording-v1",
            "provider": "recorded-fixture",
            "model": model,
            "contract_version": contract_version,
            "budget": {
                "max_calls": 1,
                "max_tokens": 128,
                "timeout_ms": 500,
                "max_retries": 0,
            },
            "responses": [
                {
                    "unknown_effect_id": retain.effect_id if target_known_effect else unknown.effect_id,
                    "snippet": snippet,
                    "request": request,
                    "proposal": proposal,
                    "usage": {"input_tokens": 20, "output_tokens": 30},
                }
            ],
        }
        path = root / "recording.json"
        path.write_text(json.dumps(recording, sort_keys=True), encoding="utf-8")
        return path

    def test_recorded_replay_validates_but_does_not_duplicate_static_positive_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"

            status = main(
                [
                    "resource-analyze",
                    "--facts",
                    str(facts),
                    "--out",
                    str(run),
                    "--llm",
                    "replay",
                    "--config",
                    str(recording),
                ]
            )

            self.assertEqual(0, status)
            manifest = json.loads((run / "run-manifest.json").read_text(encoding="utf-8"))
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))
            recording_snapshot = json.loads(
                (run / "llm-recording.private.json").read_text(encoding="utf-8")
            )
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))
            evidence = json.loads((run / "evidence.json").read_text(encoding="utf-8"))
            facts_payload = json.loads(facts.read_text(encoding="utf-8"))
            unknown_fact_ids = {
                item["fact_id"] for item in facts_payload["facts"] if item["fact_kind"] == "unknown_call"
            }
            self.assertEqual("1.1", recording_snapshot["schema_version"])
            self.assertEqual("1.1", summaries["schema_version"])
            self.assertEqual(
                {
                    "mode": "replay",
                    "provider": "recorded-fixture",
                    "model": "recorded-model",
                    "calls": 1,
                    "cost": None,
                    "live_call_verified": False,
                    "contract_version": "summary-contract-v1",
                    "budget": {
                        "max_calls": 1,
                        "max_tokens": 128,
                        "timeout_ms": 500,
                        "max_retries": 0,
                    },
                    "recording_snapshot": "llm-recording.private.json",
                    "recording_sha256": manifest["llm"]["recording_sha256"],
                    "summaries_sha256": manifest["llm"]["summaries_sha256"],
                },
                manifest["llm"],
            )
            self.assertRegex(manifest["llm"]["recording_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(manifest["llm"]["summaries_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(0o600, stat.S_IMODE((run / "llm-recording.private.json").stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE((run / "llm-summaries.json").stat().st_mode))
            record = summaries["records"][0]
            self.assertEqual("verified", record["validation"]["status"])
            self.assertEqual(record["unknown_effect_id"], record["request"]["unknown_effect_id"])
            self.assertEqual("Fixture.java", record["request"]["source_path"])
            self.assertEqual((3, 3), (record["request"]["start_line"], record["request"]["end_line"]))
            self.assertEqual([], record["usable_effect_ids"])
            self.assertEqual(1, len(record["trigger_evidence_ids"]))
            self.assertTrue(set(record["trigger_evidence_ids"]) <= unknown_fact_ids)
            self.assertIn(
                "llm_proposed_release_cannot_prove_must_release",
                record["validation"]["reason_codes"],
            )
            self.assertIn(
                "llm_proposed_effect_already_static",
                record["validation"]["reason_codes"],
            )
            self.assertEqual([], results["summary_effect_ids"])
            self.assertEqual("unknown", next(
                item["lifecycle_status"]
                for item in results["units"][0]["dimensions"]
                if item["dimension"] == "close_obligation"
            ))
            self.assertEqual(1, len(evidence["summary_derivations"]))
            self.assertEqual(
                [],
                evidence["summary_derivations"][0]["usable_effect_ids"],
            )
            self.assertEqual(
                record["trigger_evidence_ids"],
                evidence["summary_derivations"][0]["trigger_evidence_ids"],
            )
            self.assertTrue(
                set(record["trigger_evidence_ids"])
                <= set(evidence["summary_derivations"][0]["evidence_ids"])
            )
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))
            self.assertTrue(replay["consistent"])
            self.assertTrue(replay["summary_consistent"])

    def test_reusing_replay_run_for_off_removes_only_stale_managed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"
            sentinel = run / "operator-note.txt"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            sentinel.write_text("preserve me\n", encoding="utf-8")

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "off",
                    ]
                ),
            )
            stale = {
                name
                for name in (
                    "llm-recording.private.json",
                    "llm-summaries.json",
                    "replay.json",
                )
                if (run / name).exists() or (run / name).is_symlink()
            }
            manifest = json.loads(
                (run / "run-manifest.json").read_text(encoding="utf-8")
            )

            self.assertEqual(set(), stale)
            self.assertEqual("off", manifest["llm"]["mode"])
            self.assertEqual("preserve me\n", sentinel.read_text(encoding="utf-8"))

    def test_reusing_off_run_for_replay_removes_stale_replay_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"
            sentinel = run / "operator-note.txt"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "off",
                    ]
                ),
            )
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            sentinel.write_text("preserve me\n", encoding="utf-8")

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            manifest = json.loads(
                (run / "run-manifest.json").read_text(encoding="utf-8")
            )

            self.assertFalse((run / "replay.json").exists())
            self.assertTrue((run / "llm-recording.private.json").is_file())
            self.assertTrue((run / "llm-summaries.json").is_file())
            self.assertEqual("replay", manifest["llm"]["mode"])
            self.assertEqual("preserve me\n", sentinel.read_text(encoding="utf-8"))

    def test_reusing_run_fails_closed_on_unsafe_managed_artifact(self) -> None:
        for unsafe_kind in ("symlink", "directory"):
            with self.subTest(unsafe_kind=unsafe_kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                facts = self._facts(root)
                run = root / "run"
                self.assertEqual(
                    0,
                    main(
                        [
                            "resource-analyze",
                            "--facts",
                            str(facts),
                            "--out",
                            str(run),
                            "--llm",
                            "off",
                        ]
                    ),
                )
                self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
                stale = run / "replay.json"
                stale.unlink()
                protected = root / "protected.txt"
                protected.write_text("do not touch\n", encoding="utf-8")
                if unsafe_kind == "symlink":
                    stale.symlink_to(protected)
                else:
                    stale.mkdir()
                manifest_before = (run / "run-manifest.json").read_bytes()

                self.assertEqual(
                    5,
                    main(
                        [
                            "resource-analyze",
                            "--facts",
                            str(facts),
                            "--out",
                            str(run),
                            "--llm",
                            "off",
                        ]
                    ),
                )
                self.assertEqual(
                    manifest_before,
                    (run / "run-manifest.json").read_bytes(),
                )
                self.assertEqual(
                    "do not touch\n", protected.read_text(encoding="utf-8")
                )

    def test_concurrent_off_and_replay_analyze_publish_one_coherent_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"
            context = multiprocessing.get_context("spawn")
            prepared = context.Event()
            replay_completed = context.Event()
            results = context.Queue()
            off_arguments = [
                "resource-analyze",
                "--facts",
                str(facts),
                "--out",
                str(run),
                "--llm",
                "off",
            ]
            replay_arguments = [
                "resource-analyze",
                "--facts",
                str(facts),
                "--out",
                str(run),
                "--llm",
                "replay",
                "--config",
                str(recording),
            ]
            off_worker = context.Process(
                target=_paused_after_prepare_analyze_worker,
                args=(off_arguments, prepared, replay_completed, results),
            )
            replay_worker = context.Process(
                target=_analyze_worker,
                args=(replay_arguments, replay_completed, results),
            )
            off_worker.start()
            self.assertTrue(prepared.wait(5))
            replay_worker.start()
            for worker in (off_worker, replay_worker):
                worker.join(10)
                self.assertFalse(worker.is_alive())
                self.assertEqual(0, worker.exitcode)
            self.assertEqual([0, 0], sorted(results.get(timeout=2) for _ in range(2)))
            manifest = json.loads(
                (run / "run-manifest.json").read_text(encoding="utf-8")
            )
            llm_paths = tuple(run / name for name in (
                "llm-recording.private.json",
                "llm-summaries.json",
            ))

            self.assertFalse((run / "replay.json").exists())
            if manifest["llm"]["mode"] == "replay":
                self.assertTrue(all(path.is_file() for path in llm_paths))
            else:
                self.assertEqual("off", manifest["llm"]["mode"])
                self.assertFalse(any(path.exists() for path in llm_paths))
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))
            self.assertTrue(replay["consistent"])

    def test_concurrent_replay_and_analyze_cannot_publish_stale_replay_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "off",
                    ]
                ),
            )
            context = multiprocessing.get_context("spawn")
            publish_ready = context.Event()
            analyze_completed = context.Event()
            results = context.Queue()
            replay_worker = context.Process(
                target=_paused_before_replay_publish_worker,
                args=(str(run), publish_ready, analyze_completed, results),
            )
            replay_worker.start()
            self.assertTrue(publish_ready.wait(5))

            analyze_status = main(
                [
                    "resource-analyze",
                    "--facts",
                    str(facts),
                    "--out",
                    str(run),
                    "--llm",
                    "replay",
                    "--config",
                    str(recording),
                ]
            )
            analyze_completed.set()
            replay_worker.join(10)

            self.assertEqual(0, analyze_status)
            self.assertFalse(replay_worker.is_alive())
            self.assertEqual(0, replay_worker.exitcode)
            self.assertEqual(0, results.get(timeout=2))
            self.assertFalse((run / "replay.json").exists())
            manifest = json.loads(
                (run / "run-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("replay", manifest["llm"]["mode"])
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))
            self.assertTrue(replay["consistent"])

    def test_analyze_lock_path_must_be_owner_only_regular_file(self) -> None:
        for unsafe_kind in ("symlink", "directory", "wrong_mode"):
            with self.subTest(unsafe_kind=unsafe_kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                facts = self._facts(root)
                run = root / "run"
                run.mkdir()
                lock = run / ".resource-lifecycle.lock"
                protected = root / "protected.txt"
                protected.write_text("do not touch\n", encoding="utf-8")
                if unsafe_kind == "symlink":
                    lock.symlink_to(protected)
                elif unsafe_kind == "directory":
                    lock.mkdir()
                else:
                    lock.write_text("unsafe mode\n", encoding="utf-8")
                    lock.chmod(0o644)

                self.assertEqual(
                    5,
                    main(
                        [
                            "resource-analyze",
                            "--facts",
                            str(facts),
                            "--out",
                            str(run),
                            "--llm",
                            "off",
                        ]
                    ),
                )
                self.assertEqual(
                    "do not touch\n", protected.read_text(encoding="utf-8")
                )
                self.assertFalse((run / "run-manifest.json").exists())

    def test_replay_rejects_unsafe_or_oversized_facts_without_legacy_hashing(self) -> None:
        for unsafe_kind in ("symlink", "directory", "oversized"):
            with self.subTest(unsafe_kind=unsafe_kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                facts = self._facts(root)
                run = root / "run"
                self.assertEqual(
                    0,
                    main(
                        [
                            "resource-analyze",
                            "--facts",
                            str(facts),
                            "--out",
                            str(run),
                            "--llm",
                            "off",
                        ]
                    ),
                )
                snapshot = run / "facts.snapshot.json"
                snapshot.unlink()
                if unsafe_kind == "symlink":
                    protected = root / "protected-facts.json"
                    protected.write_bytes(facts.read_bytes())
                    snapshot.symlink_to(protected)
                elif unsafe_kind == "directory":
                    snapshot.mkdir()
                else:
                    snapshot.write_bytes(b" " * (16 * 1024 * 1024 + 1))

                with patch.object(
                    lifecycle_commands,
                    "file_sha256",
                    wraps=lifecycle_commands.file_sha256,
                ) as legacy_hash:
                    self.assertEqual(
                        5, main(["resource-replay", "--run", str(run)])
                    )

                legacy_hash.assert_not_called()

    def test_replay_hashes_facts_and_private_artifacts_from_their_parse_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )

            with patch.object(
                lifecycle_commands,
                "file_sha256",
                wraps=lifecycle_commands.file_sha256,
            ) as legacy_hash:
                self.assertEqual(0, main(["resource-replay", "--run", str(run)]))

            legacy_hash.assert_not_called()
            replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))
            self.assertTrue(replay["consistent"])

    def test_replay_rejects_unsafe_private_snapshot_without_legacy_hashing(self) -> None:
        for name in ("llm-recording.private.json", "llm-summaries.json"):
            for unsafe_kind in ("symlink", "directory"):
                with (
                    self.subTest(name=name, unsafe_kind=unsafe_kind),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    root = Path(tmp)
                    facts = self._facts(root)
                    recording = self._recording(root, facts)
                    run = root / "run"
                    self.assertEqual(
                        0,
                        main(
                            [
                                "resource-analyze",
                                "--facts",
                                str(facts),
                                "--out",
                                str(run),
                                "--llm",
                                "replay",
                                "--config",
                                str(recording),
                            ]
                        ),
                    )
                    private = run / name
                    private.unlink()
                    if unsafe_kind == "symlink":
                        protected = root / f"protected-{name}"
                        protected.write_bytes(recording.read_bytes())
                        private.symlink_to(protected)
                    else:
                        private.mkdir()

                    with patch.object(
                        lifecycle_commands,
                        "file_sha256",
                        wraps=lifecycle_commands.file_sha256,
                    ) as legacy_hash:
                        self.assertEqual(
                            5, main(["resource-replay", "--run", str(run)])
                        )

                    legacy_hash.assert_not_called()

    def test_recording_is_bound_to_the_entire_java_source_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            first_facts = self._facts(
                first,
                auxiliary_source="final class Wrapper { static void retain(Object value) {} }\n",
            )
            second_facts = self._facts(
                second,
                auxiliary_source=(
                    "final class Wrapper { static void retain(Object value) "
                    "{ System.out.println(value); } }\n"
                ),
            )
            recording = self._recording(first, first_facts)

            status = main(
                [
                    "resource-analyze",
                    "--facts",
                    str(second_facts),
                    "--out",
                    str(root / "run"),
                    "--llm",
                    "replay",
                    "--config",
                    str(recording),
                ]
            )

        self.assertEqual(5, status)

    def test_recording_cannot_borrow_static_evidence_from_another_statement_on_the_same_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root, precise_columns=True)
            recording = self._recording(root, facts)
            extracted = extracted_from_dict(json.loads(facts.read_text(encoding="utf-8")))
            unknown = next(
                fact
                for fact in extracted.facts
                if fact.fact_kind == "unknown_call" and fact.location.start_line == 3
            )
            retained = next(
                fact
                for fact in extracted.facts
                if fact.fact_kind == "retain" and fact.location.start_line == 3
            )
            self.assertNotEqual(unknown.site_start_column, retained.site_start_column)

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(root / "run"),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads(
                (root / "run" / "llm-summaries.json").read_text(encoding="utf-8")
            )

        self.assertEqual("unresolved", summaries["records"][0]["validation"]["status"])
        self.assertEqual([], summaries["records"][0]["usable_effect_ids"])

    def test_summary_derivation_keeps_each_usable_effects_static_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            payload = json.loads(recording.read_text(encoding="utf-8"))
            response = payload["responses"][0]
            extracted = extracted_from_dict(json.loads(facts.read_text(encoding="utf-8")))
            unknown = next(
                effect
                for transition in extracted.units[0].program.transitions
                for effect in transition.effects
                if effect.effect_id == response["unknown_effect_id"]
            )
            response["proposal"]["evidence_ids"] = list(unknown.evidence_ids)
            recording.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))
            evidence = json.loads((run / "evidence.json").read_text(encoding="utf-8"))

        record = summaries["records"][0]
        self.assertEqual("verified", record["validation"]["status"])
        supporting = {
            evidence_id
            for effect in record["proposal"]["normal_effects"]
            + record["proposal"]["exceptional_effects"]
            for evidence_id in effect["evidence_ids"]
        }
        derivation = evidence["summary_derivations"][0]
        self.assertTrue(supporting)
        self.assertTrue(supporting <= set(derivation["evidence_ids"]))
        self.assertTrue(
            supporting
            <= {
                item["evidence_id"]
                for item in evidence["proof_dependencies"]
                if item["proof_id"] == derivation["derivation_id"]
            }
        )

    def test_recording_cannot_describe_a_local_holder_as_a_field_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root, unknown_at_create=True)
            recording = self._recording(root, facts, use_local_retain=True)
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))

        validation = summaries["records"][0]["validation"]
        self.assertEqual("unresolved", validation["status"])
        self.assertIn("field_save_holder_kind_unresolved", validation["reason_codes"])
        self.assertEqual([], summaries["records"][0]["usable_effect_ids"])

    def test_recorded_summary_does_not_reexecute_an_existing_static_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))

        record = summaries["records"][0]
        self.assertEqual("verified", record["validation"]["status"])
        self.assertIn(
            "llm_proposed_effect_already_static",
            record["validation"]["reason_codes"],
        )
        self.assertEqual([], record["usable_effect_ids"])
        self.assertEqual([], results["summary_effect_ids"])

    def test_recording_response_must_target_an_unknown_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts, target_known_effect=True)

            status = main(
                [
                    "resource-analyze",
                    "--facts",
                    str(facts),
                    "--out",
                    str(root / "run"),
                    "--llm",
                    "replay",
                    "--config",
                    str(recording),
                ]
            )

        self.assertEqual(5, status)

    def test_recording_rejects_effect_identity_reused_across_unknown_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            extracted = extracted_from_dict(json.loads(facts.read_text(encoding="utf-8")))
            unknown_ids = sorted(
                {
                    effect.effect_id
                    for transition in extracted.units[0].program.transitions
                    for effect in transition.effects
                    if effect.kind == "unknown_call"
                }
            )
            payload = json.loads(recording.read_text(encoding="utf-8"))
            second = json.loads(json.dumps(payload["responses"][0]))
            second["unknown_effect_id"] = next(
                effect_id for effect_id in unknown_ids if effect_id != payload["responses"][0]["unknown_effect_id"]
            )
            payload["responses"].append(second)
            payload["budget"]["max_calls"] = 2
            payload["budget"]["max_tokens"] = 256
            recording.write_text(json.dumps(payload), encoding="utf-8")

            status = main(
                [
                    "resource-analyze",
                    "--facts",
                    str(facts),
                    "--out",
                    str(root / "run"),
                    "--llm",
                    "replay",
                    "--config",
                    str(recording),
                ]
            )

        self.assertEqual(5, status)

    def test_recording_request_and_location_are_bound_to_the_target_unknown_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            extracted = extracted_from_dict(json.loads(facts.read_text(encoding="utf-8")))
            payload = json.loads(recording.read_text(encoding="utf-8"))
            original = payload["responses"][0]["unknown_effect_id"]
            payload["responses"][0]["unknown_effect_id"] = next(
                effect.effect_id
                for transition in extracted.units[0].program.transitions
                for effect in transition.effects
                if effect.kind == "unknown_call" and effect.effect_id != original
            )
            recording.write_text(json.dumps(payload), encoding="utf-8")

            status = main(
                [
                    "resource-analyze",
                    "--facts",
                    str(facts),
                    "--out",
                    str(root / "run"),
                    "--llm",
                    "replay",
                    "--config",
                    str(recording),
                ]
            )

        self.assertEqual(5, status)

    def test_recording_snippet_must_be_the_exact_target_source_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            payload = json.loads(recording.read_text(encoding="utf-8"))
            snippet = "fabricated_call(resource);\n"
            payload["responses"][0]["snippet"] = snippet
            payload["responses"][0]["request"]["snippet_sha256"] = hashlib.sha256(
                snippet.encode("utf-8")
            ).hexdigest()
            recording.write_text(json.dumps(payload), encoding="utf-8")

            status = main(
                [
                    "resource-analyze",
                    "--facts",
                    str(facts),
                    "--out",
                    str(root / "run"),
                    "--llm",
                    "replay",
                    "--config",
                    str(recording),
                ]
            )

        self.assertEqual(5, status)

    def test_proposal_location_cannot_move_to_another_line_in_the_same_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            payload = json.loads(recording.read_text(encoding="utf-8"))
            proposal = payload["responses"][0]["proposal"]
            proposal["location"]["start_line"] = 4
            proposal["location"]["end_line"] = 4
            for path_name in ("normal_effects", "exceptional_effects"):
                for effect in proposal[path_name]:
                    effect["location"]["start_line"] = 4
                    effect["location"]["end_line"] = 4
            recording.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))

        self.assertEqual("rejected", summaries["records"][0]["validation"]["status"])
        self.assertEqual([], summaries["records"][0]["usable_effect_ids"])

    def test_proposal_location_range_must_equal_the_target_call_site(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            payload = json.loads(recording.read_text(encoding="utf-8"))
            proposal = payload["responses"][0]["proposal"]
            proposal["location"]["end_line"] += 1
            for path_name in ("normal_effects", "exceptional_effects"):
                for effect in proposal[path_name]:
                    effect["location"]["end_line"] += 1
            recording.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))

        self.assertEqual("rejected", summaries["records"][0]["validation"]["status"])
        self.assertEqual([], summaries["records"][0]["usable_effect_ids"])

    def test_recording_cannot_borrow_operations_or_identities_from_another_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root, second_resource=True)
            recording = self._recording(root, facts)
            extracted = extracted_from_dict(json.loads(facts.read_text(encoding="utf-8")))
            payload = json.loads(recording.read_text(encoding="utf-8"))
            unknown_id = payload["responses"][0]["unknown_effect_id"]
            target_unknown = next(
                effect
                for transition in extracted.units[0].program.transitions
                for effect in transition.effects
                if effect.effect_id == unknown_id
            )
            borrowed = next(
                effect
                for transition in extracted.units[0].program.transitions
                for effect in transition.effects
                if effect.kind == "retain"
                and effect.holder_id is not None
                and effect.instance_id != target_unknown.instance_id
            )
            proposal = payload["responses"][0]["proposal"]
            for path_name in ("normal_effects", "exceptional_effects"):
                for proposed in proposal[path_name]:
                    for field in (
                        "instance_id",
                        "family_id",
                        "holder_id",
                        "target_event_id",
                        "contract_id",
                        "condition",
                        "size_lower",
                        "size_upper",
                        "evidence_ids",
                    ):
                        proposed[field] = asdict(borrowed)[field]
            proposal["preconditions"].append("caller has administrator privileges")
            proposal["captures"] = [str(borrowed.instance_id)]
            proposal["field_saves"] = [str(borrowed.holder_id), "holder:fabricated"]
            recording.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))

        self.assertEqual("unresolved", summaries["records"][0]["validation"]["status"])
        self.assertEqual([], summaries["records"][0]["usable_effect_ids"])
        self.assertEqual([], results["summary_effect_ids"])

    def test_recording_cannot_borrow_a_prefix_operation_from_the_same_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            extracted = extracted_from_dict(json.loads(facts.read_text(encoding="utf-8")))
            payload = json.loads(recording.read_text(encoding="utf-8"))
            unit = extracted.units[0]
            holders = {holder.holder_id: holder for holder in unit.program.holders}
            prefix_retain = next(
                effect
                for transition in unit.program.transitions
                for effect in transition.effects
                if effect.kind == "retain"
                and effect.holder_id is not None
                and holders[effect.holder_id].kind in {"local", "request_stack"}
            )
            proposed = payload["responses"][0]["proposal"]["normal_effects"][0]
            for field in (
                "instance_id",
                "family_id",
                "holder_id",
                "target_event_id",
                "contract_id",
                "condition",
                "size_lower",
                "size_upper",
                "evidence_ids",
            ):
                proposed[field] = asdict(prefix_retain)[field]
            payload["responses"][0]["proposal"]["field_saves"] = [str(prefix_retain.holder_id)]
            recording.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))

        self.assertEqual("unresolved", summaries["records"][0]["validation"]["status"])
        self.assertEqual([], summaries["records"][0]["usable_effect_ids"])

    def test_recorded_existing_static_effect_is_not_inserted_on_any_caller_exit(self) -> None:
        from dosweb.resource_lifecycle.summaries import (
            apply_recorded_summaries,
            recording_from_dict,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording_path = self._recording(root, facts)
            extracted = extracted_from_dict(json.loads(facts.read_text(encoding="utf-8")))
            recording = recording_from_dict(json.loads(recording_path.read_text(encoding="utf-8")))

            applied = apply_recorded_summaries(extracted, recording)

        transitions_with_unknown = [
            transition
            for transition in applied.extracted.units[0].program.transitions
            if any(effect.kind == "unknown_call" for effect in transition.effects)
        ]
        self.assertEqual({"normal", "exceptional"}, {item.exit_kind for item in transitions_with_unknown})
        self.assertTrue(
            all(
                "effect:llm-proposed-retain" not in {effect.effect_id for effect in transition.effects}
                for transition in transitions_with_unknown
            )
        )
        self.assertEqual((), applied.summary_effect_ids)

    def test_recorded_exceptional_effect_is_unresolved_without_callee_cfg_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            payload = json.loads(recording.read_text(encoding="utf-8"))
            payload["responses"][0]["proposal"]["exceptional_effects"] = json.loads(
                json.dumps(payload["responses"][0]["proposal"]["normal_effects"])
            )
            recording.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))

        self.assertEqual("unresolved", summaries["records"][0]["validation"]["status"])
        self.assertEqual([], summaries["records"][0]["usable_effect_ids"])

    def test_unverified_recorded_effect_remains_display_only_and_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            payload = json.loads(recording.read_text(encoding="utf-8"))
            for path in ("normal_effects", "exceptional_effects"):
                for effect in payload["responses"][0]["proposal"][path]:
                    effect["family_id"] = "family:fabricated"
            recording.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))

        self.assertEqual("unresolved", summaries["records"][0]["validation"]["status"])
        self.assertEqual([], summaries["records"][0]["usable_effect_ids"])
        self.assertEqual([], results["summary_effect_ids"])
        self.assertEqual(
            "unknown",
            next(
                item["lifecycle_status"]
                for item in results["units"][0]["dimensions"]
                if item["dimension"] == "held_instances"
            ),
        )

    def test_proposal_locations_are_bound_to_the_static_source_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            payload = json.loads(recording.read_text(encoding="utf-8"))
            proposal = payload["responses"][0]["proposal"]
            proposal["location"]["source_sha256"] = "0" * 64
            for path in ("normal_effects", "exceptional_effects"):
                for current in proposal[path]:
                    current["location"]["source_sha256"] = "0" * 64
            recording.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))

        self.assertEqual("rejected", summaries["records"][0]["validation"]["status"])
        self.assertIn(
            "location_not_in_static_slice",
            summaries["records"][0]["validation"]["reason_codes"],
        )
        self.assertEqual([], results["summary_effect_ids"])

    def test_parameter_mapping_requires_an_exact_static_identity_precondition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            payload = json.loads(recording.read_text(encoding="utf-8"))
            original = payload["responses"][0]["proposal"]["preconditions"][0]
            payload["responses"][0]["proposal"]["preconditions"] = [f"not ({original})"]
            recording.write_text(json.dumps(payload), encoding="utf-8")
            run = root / "run"

            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            summaries = json.loads((run / "llm-summaries.json").read_text(encoding="utf-8"))
            results = json.loads((run / "lifecycle-results.json").read_text(encoding="utf-8"))

        self.assertEqual("unresolved", summaries["records"][0]["validation"]["status"])
        self.assertIn(
            "parameter_mapping_unresolved",
            summaries["records"][0]["validation"]["reason_codes"],
        )
        self.assertEqual([], results["summary_effect_ids"])

    def test_replay_detects_tampered_summary_validation_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            path = run / "llm-summaries.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["records"][0]["validation"]["status"] = "rejected"
            path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))

        self.assertFalse(replay["consistent"])
        self.assertFalse(replay["summary_consistent"])

    def test_replay_detects_tampered_human_readable_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            (run / "summary.md").write_text("# tampered\n", encoding="utf-8")

            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))

        self.assertFalse(replay["consistent"])
        self.assertFalse(replay["summary_markdown_consistent"])

    def test_replay_rejects_non_private_recording_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            for name in ("llm-recording.private.json", "llm-summaries.json"):
                with self.subTest(name=name):
                    run = root / f"run-{name}"
                    self.assertEqual(
                        0,
                        main(
                            [
                                "resource-analyze",
                                "--facts",
                                str(facts),
                                "--out",
                                str(run),
                                "--llm",
                                "replay",
                                "--config",
                                str(recording),
                            ]
                        ),
                    )
                    os.chmod(run / name, 0o644)

                    self.assertEqual(5, main(["resource-replay", "--run", str(run)]))

    def test_replay_uses_saved_recording_snapshot_not_mutable_original_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            run = root / "run"
            self.assertEqual(
                0,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(run),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )
            recording.write_text("{}\n", encoding="utf-8")

            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))

        self.assertTrue(replay["consistent"])
        self.assertTrue(replay["summary_consistent"])

    def test_recording_budget_and_request_identity_are_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            payload = json.loads(recording.read_text(encoding="utf-8"))
            payload["responses"][0]["usage"]["output_tokens"] = 200
            recording.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(
                5,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(root / "budget-run"),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )

            payload["responses"][0]["usage"] = {"input_tokens": 20, "output_tokens": 30}
            payload["responses"][0]["request"]["model"] = "different-model"
            recording.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(
                5,
                main(
                    [
                        "resource-analyze",
                        "--facts",
                        str(facts),
                        "--out",
                        str(root / "identity-run"),
                        "--llm",
                        "replay",
                        "--config",
                        str(recording),
                    ]
                ),
            )

    def test_recorded_replay_rejects_live_provider_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)

            status = main(
                [
                    "resource-analyze",
                    "--facts",
                    str(facts),
                    "--out",
                    str(root / "run"),
                    "--llm",
                    "replay",
                    "--config",
                    str(recording),
                    "--model",
                    "override-model",
                ]
            )

        self.assertEqual(2, status)

    def test_recording_schema_rejects_wrong_scalar_and_array_types_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            mutations = (
                lambda payload: payload.__setitem__("provider", 7),
                lambda payload: payload["responses"][0]["proposal"].__setitem__("preconditions", [7]),
            )
            for index, mutate in enumerate(mutations):
                with self.subTest(index=index):
                    recording = self._recording(root, facts)
                    payload = json.loads(recording.read_text(encoding="utf-8"))
                    mutate(payload)
                    recording.write_text(json.dumps(payload), encoding="utf-8")

                    status = main(
                        [
                            "resource-analyze",
                            "--facts",
                            str(facts),
                            "--out",
                            str(root / f"invalid-schema-{index}"),
                            "--llm",
                            "replay",
                            "--config",
                            str(recording),
                        ]
                    )

                    self.assertEqual(5, status)

    def test_recording_rejects_non_finite_exponent_numbers_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = self._facts(root)
            recording = self._recording(root, facts)
            raw = recording.read_text(encoding="utf-8")
            self.assertIn('"max_calls": 1', raw)
            recording.write_text(raw.replace('"max_calls": 1', '"max_calls": 1e309', 1), encoding="utf-8")

            status = main(
                [
                    "resource-analyze",
                    "--facts",
                    str(facts),
                    "--out",
                    str(root / "run"),
                    "--llm",
                    "replay",
                    "--config",
                    str(recording),
                ]
            )

        self.assertEqual(5, status)

if __name__ == "__main__":
    unittest.main()
