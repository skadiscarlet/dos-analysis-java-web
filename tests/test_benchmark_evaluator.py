import unittest

from dosweb.benchmark.evaluator import evaluate_matches, evaluate_open_discovery


def _finding(
    *,
    repository: str = "owner/repo",
    finding_id: str = "finding:fixture",
    growth_id: str = "growth:fixture",
    verdict: str = "static_vulnerable",
):
    return {
        "batch_target_name": repository,
        "finding_id": finding_id,
        "growth_id": growth_id,
        "verdict": verdict,
    }


def _disposition(
    *,
    repository: str = "owner/repo",
    disposition_id: str = "disposition:fixture",
    growth_id: str = "growth:fixture",
    status: str = "formal_eligible",
    negative_proof_ids: list[str] | None = None,
):
    return {
        "batch_target_name": repository,
        "disposition_id": disposition_id,
        "growth_id": growth_id,
        "status": status,
        "negative_proof_ids": [] if negative_proof_ids is None else negative_proof_ids,
    }


def _negative_proof(
    *,
    repository: str = "owner/repo",
    negative_proof_id: str = "negative_proof:fixture",
    growth_id: str = "growth:fixture",
    kind: str = "finite_keyspace",
):
    return {
        "batch_target_name": repository,
        "negative_proof_id": negative_proof_id,
        "growth_id": growth_id,
        "kind": kind,
    }


class BenchmarkEvaluatorTests(unittest.TestCase):
    def test_only_recall_metrics_are_emitted_with_eligibility(self):
        result = evaluate_matches(
            [
                {"status": "hit", "repository": "a/a"},
                {"status": "matched_static_unknown", "repository": "b/b"},
                {"status": "no_candidate", "repository": "c/c"},
                {"status": "target_not_run", "repository": "d/d"},
                {"status": "artifact_missing", "repository": "e/e"},
            ]
        )
        self.assertEqual(
            set(result["metrics"]),
            {"positive_recall", "global_recall", "matched_any_rate"},
        )
        self.assertEqual(result["eligible"], 3)
        self.assertEqual(result["hits"], 1)
        self.assertEqual(result["targets_completed"], 3)
        self.assertEqual(result["metrics"]["positive_recall"], 1 / 3)
        self.assertEqual(result["metrics"]["global_recall"], 1 / 29)
        self.assertEqual(result["metrics"]["matched_any_rate"], 2 / 3)

    def test_empty_is_safe(self):
        result = evaluate_matches([])
        self.assertEqual(result["metrics"]["global_recall"], 0.0)
        self.assertEqual(result["eligible"], 0)

    def test_open_discovery_classifies_seed_novel_bounded_negative_and_unresolved(self):
        findings = [
            {"batch_target_name": "owner/repo", "finding_id": "finding:seed", "growth_id": "growth:seed", "verdict": "static_vulnerable"},
            {"batch_target_name": "owner/repo", "finding_id": "finding:novel", "growth_id": "growth:novel", "verdict": "static_vulnerable"},
            {"batch_target_name": "owner/repo", "finding_id": "finding:bounded", "growth_id": "growth:bounded", "verdict": "bounded_under_modeled_assumptions"},
            {"batch_target_name": "owner/repo", "finding_id": "finding:unknown", "growth_id": "growth:unknown", "verdict": "static_unknown"},
        ]
        dispositions = [
            {
                "batch_target_name": "owner/repo",
                "disposition_id": "disposition:seed",
                "growth_id": "growth:seed",
                "status": "formal_eligible",
                "negative_proof_ids": [],
            },
            {
                "batch_target_name": "owner/repo",
                "disposition_id": "disposition:novel",
                "growth_id": "growth:novel",
                "status": "formal_eligible",
                "negative_proof_ids": [],
            },
            {
                "batch_target_name": "owner/repo",
                "disposition_id": "disposition:bounded",
                "growth_id": "growth:bounded",
                "status": "formal_eligible",
                "negative_proof_ids": [],
            },
            {
                "batch_target_name": "owner/repo",
                "disposition_id": "disposition:unknown",
                "growth_id": "growth:unknown",
                "status": "gap_eligible",
                "negative_proof_ids": [],
            },
            {
                "batch_target_name": "owner/repo",
                "disposition_id": "disposition:negative",
                "growth_id": "growth:negative",
                "status": "rejected",
                "negative_proof_ids": ["negative_proof:finite"],
            },
            {
                "batch_target_name": "owner/repo",
                "disposition_id": "disposition:inventory",
                "growth_id": "growth:inventory",
                "status": "inventory_unresolved",
                "negative_proof_ids": [],
            },
        ]
        negative_proofs = [
            {
                "batch_target_name": "owner/repo",
                "negative_proof_id": "negative_proof:finite",
                "growth_id": "growth:negative",
                "kind": "finite_keyspace",
            }
        ]
        seed_matches = [
            {
                "case_id": "seed:1",
                "repository": "owner/repo",
                "status": "hit",
                "chain": {
                    "finding_id": "finding:seed",
                    "growth_id": "growth:seed",
                },
            },
            {"case_id": "seed:miss", "repository": "owner/repo", "status": "no_candidate", "candidate_ids": []},
        ]

        result = evaluate_open_discovery(
            findings=findings,
            dispositions=dispositions,
            negative_proofs=negative_proofs,
            seed_matches=seed_matches,
        )

        by_growth = {row["growth_id"]: row for row in result["discoveries"]}
        self.assertEqual("seed_linked_static_vulnerable", by_growth["growth:seed"]["classification"])
        self.assertEqual("novel_static_vulnerable", by_growth["growth:novel"]["classification"])
        self.assertEqual("novel_bounded", by_growth["growth:bounded"]["classification"])
        self.assertEqual("unresolved_discovery", by_growth["growth:unknown"]["classification"])
        self.assertEqual("source_proven_negative", by_growth["growth:negative"]["classification"])
        self.assertEqual("unresolved_discovery", by_growth["growth:inventory"]["classification"])
        self.assertEqual(["seed:1"], by_growth["growth:seed"]["seed_ids"])
        self.assertFalse(by_growth["growth:seed"]["recall_miss"])
        seed_miss = next(
            row
            for row in result["discoveries"]
            if row["discovery_id"].endswith("seed::seed:miss")
        )
        self.assertEqual("unresolved_discovery", seed_miss["classification"])
        self.assertEqual(["seed:miss"], seed_miss["seed_ids"])
        self.assertTrue(seed_miss["recall_miss"])
        self.assertEqual("no_candidate", seed_miss["seed_status"])
        for field in ("finding_id", "growth_id", "disposition_id", "static_verdict"):
            self.assertIsNone(seed_miss[field])
        self.assertNotIn("false_positive", result["category_counts"])

    def test_open_discovery_fails_closed_on_missing_negative_proof(self):
        with self.assertRaisesRegex(ValueError, "negative proof"):
            evaluate_open_discovery(
                findings=[],
                dispositions=[{
                    "batch_target_name": "owner/repo",
                    "disposition_id": "disposition:rejected",
                    "growth_id": "growth:rejected",
                    "status": "rejected",
                    "negative_proof_ids": ["negative_proof:missing"],
                }],
                negative_proofs=[],
                seed_matches=[],
            )

    def test_open_discovery_rejects_cross_repository_analysis_id_reuse(self):
        findings = [
            {
                "batch_target_name": "owner/seeded",
                "finding_id": "finding:same",
                "growth_id": "growth:same",
                "verdict": "static_vulnerable",
            },
            {
                "batch_target_name": "owner/novel",
                "finding_id": "finding:novel-scope",
                "growth_id": "growth:novel-scope",
                "verdict": "static_vulnerable",
            },
        ]
        dispositions = [
            {
                "batch_target_name": repository,
                "disposition_id": "disposition:same",
                "growth_id": "growth:same",
                "status": "formal_eligible",
                "negative_proof_ids": [],
            }
            for repository in ("owner/seeded", "owner/novel")
        ]

        with self.assertRaisesRegex(ValueError, "cross-repository"):
            evaluate_open_discovery(
                findings=findings,
                dispositions=dispositions,
                negative_proofs=[],
                seed_matches=[],
            )

    def test_open_discovery_links_poc33_dispositions_by_concrete_scoped_ids(self):
        findings = [
            {
                "batch_target_name": "owner/seeded",
                "finding_id": "finding:same",
                "growth_id": "growth:same",
                "verdict": "static_vulnerable",
            },
            {
                "batch_target_name": "owner/novel",
                "finding_id": "finding:novel-scope",
                "growth_id": "growth:novel-scope",
                "verdict": "static_vulnerable",
            },
        ]
        findings.extend([
            {
                "batch_target_name": "owner/seeded",
                "finding_id": "finding:growth-only",
                "growth_id": "growth:growth-only",
                "verdict": "static_vulnerable",
            },
            {
                "batch_target_name": "owner/seeded",
                "finding_id": "finding:entry-only",
                "growth_id": "growth:entry-only",
                "verdict": "static_vulnerable",
            },
            {
                "batch_target_name": "owner/seeded",
                "finding_id": "finding:entry-and-growth",
                "growth_id": "growth:entry-and-growth",
                "verdict": "static_vulnerable",
            },
        ])
        dispositions = [
            {
                "batch_target_name": finding["batch_target_name"],
                "disposition_id": f"disposition:{index}",
                "growth_id": finding["growth_id"],
                "status": "formal_eligible",
                "negative_proof_ids": [],
            }
            for index, finding in enumerate(findings)
        ]
        seed_matches = [
            {
                "record_id": "record:full-chain",
                "case_id": "case:must-not-win",
                "truth_id": "truth:must-not-win",
                "repository": "owner/seeded",
                "status": "full_chain_finding",
                "matched_finding_ids": ["finding:same"],
                "matched_growth_ids": ["growth:same"],
            },
            {
                "record_id": "record:growth-only",
                "repository": "owner/seeded",
                "status": "growth_only",
                "matched_entry_ids": ["entry:shared"],
                "matched_growth_ids": ["growth:growth-only"],
            },
            {
                "record_id": "record:entry-only",
                "repository": "owner/seeded",
                "status": "entry_only",
                "matched_entry_ids": ["entry:shared"],
            },
            {
                "record_id": "record:entry-and-growth",
                "repository": "owner/seeded",
                "status": "entry_and_growth_linked",
                "matched_entry_ids": ["entry:linked"],
                "matched_growth_ids": ["growth:entry-and-growth"],
            },
            {
                "record_id": "record:ambiguous-entry",
                "repository": "owner/seeded",
                "status": "ambiguous_truth_match",
                "matched_entry_ids": ["entry:shared", "entry:other"],
            },
            {
                "record_id": "record:failed",
                "repository": "owner/seeded",
                "status": "stage_failed",
            },
        ]

        result = evaluate_open_discovery(
            findings=findings,
            dispositions=dispositions,
            negative_proofs=[],
            seed_matches=seed_matches,
        )

        by_target_and_growth = {
            (row["target"], row["growth_id"]): row
            for row in result["discoveries"]
        }
        self.assertEqual(
            ["record:full-chain"],
            by_target_and_growth[("owner/seeded", "growth:same")]["seed_ids"],
        )
        self.assertEqual(
            "novel_static_vulnerable",
            by_target_and_growth[("owner/novel", "growth:novel-scope")]["classification"],
        )
        self.assertEqual(
            ["record:growth-only"],
            by_target_and_growth[("owner/seeded", "growth:growth-only")]["seed_ids"],
        )
        self.assertEqual(
            [],
            by_target_and_growth[("owner/seeded", "growth:entry-only")]["seed_ids"],
        )
        self.assertEqual(
            ["record:entry-and-growth"],
            by_target_and_growth[
                ("owner/seeded", "growth:entry-and-growth")
            ]["seed_ids"],
        )

    def test_open_discovery_ambiguous_truth_links_only_concrete_ids(self):
        findings = [
            {
                "batch_target_name": "owner/repo",
                "finding_id": "finding:ambiguous-growth",
                "growth_id": "growth:ambiguous-growth",
                "verdict": "static_vulnerable",
            },
            {
                "batch_target_name": "owner/repo",
                "finding_id": "finding:ambiguous-finding",
                "growth_id": "growth:ambiguous-finding",
                "verdict": "static_vulnerable",
            },
            {
                "batch_target_name": "owner/repo",
                "finding_id": "finding:entry-only",
                "growth_id": "growth:entry-only",
                "verdict": "static_vulnerable",
            },
        ]
        dispositions = [
            {
                "batch_target_name": "owner/repo",
                "disposition_id": f"disposition:{index}",
                "growth_id": finding["growth_id"],
                "status": "formal_eligible",
                "negative_proof_ids": [],
            }
            for index, finding in enumerate(findings)
        ]
        seed_matches = [
            {
                "record_id": "record:ambiguous-growth",
                "repository": "owner/repo",
                "status": "ambiguous_truth_match",
                "matched_entry_ids": ["entry:a", "entry:b"],
                "matched_growth_ids": ["growth:ambiguous-growth"],
            },
            {
                "record_id": "record:ambiguous-finding",
                "repository": "owner/repo",
                "status": "ambiguous_truth_match",
                "matched_entry_ids": ["entry:a", "entry:b"],
                "matched_finding_ids": ["finding:ambiguous-finding"],
            },
            {
                "record_id": "record:ambiguous-entry-only",
                "repository": "owner/repo",
                "status": "ambiguous_truth_match",
                "matched_entry_ids": ["entry:a", "entry:b"],
            },
        ]

        result = evaluate_open_discovery(
            findings=findings,
            dispositions=dispositions,
            negative_proofs=[],
            seed_matches=seed_matches,
        )

        by_growth = {row["growth_id"]: row for row in result["discoveries"]}
        self.assertEqual(
            ["record:ambiguous-growth"],
            by_growth["growth:ambiguous-growth"]["seed_ids"],
        )
        self.assertEqual(
            ["record:ambiguous-finding"],
            by_growth["growth:ambiguous-finding"]["seed_ids"],
        )
        self.assertEqual([], by_growth["growth:entry-only"]["seed_ids"])

    def test_open_discovery_requires_scope_on_analysis_records(self):
        finding = {
            "batch_target_name": "owner/repo",
            "finding_id": "finding:scoped",
            "growth_id": "growth:scoped",
            "verdict": "static_vulnerable",
        }
        disposition = {
            "batch_target_name": "owner/repo",
            "disposition_id": "disposition:scoped",
            "growth_id": "growth:scoped",
            "status": "formal_eligible",
            "negative_proof_ids": [],
        }
        proof = {
            "batch_target_name": "owner/repo",
            "negative_proof_id": "negative-proof:scoped",
            "growth_id": "growth:scoped",
        }
        unscoped_finding = dict(finding)
        unscoped_finding.pop("batch_target_name")
        unscoped_disposition = dict(disposition)
        unscoped_disposition.pop("batch_target_name")
        unscoped_proof = dict(proof)
        unscoped_proof.pop("batch_target_name")
        cases = {
            "finding": ([unscoped_finding], [disposition], []),
            "disposition": ([finding], [unscoped_disposition], []),
            "negative-proof": ([finding], [disposition], [unscoped_proof]),
        }

        for label, (findings, dispositions, negative_proofs) in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "scope"):
                    evaluate_open_discovery(
                        findings=findings,
                        dispositions=dispositions,
                        negative_proofs=negative_proofs,
                        seed_matches=[],
                    )

    def test_open_discovery_rejects_concrete_seed_ids_without_scope(self):
        with self.assertRaisesRegex(ValueError, "scope"):
            evaluate_open_discovery(
                findings=[{
                    "batch_target_name": "owner/repo",
                    "finding_id": "finding:scoped",
                    "growth_id": "growth:scoped",
                    "verdict": "static_vulnerable",
                }],
                dispositions=[{
                    "batch_target_name": "owner/repo",
                    "disposition_id": "disposition:scoped",
                    "growth_id": "growth:scoped",
                    "status": "formal_eligible",
                    "negative_proof_ids": [],
                }],
                negative_proofs=[],
                seed_matches=[{
                    "record_id": "record:unscoped",
                    "status": "growth_only",
                    "matched_growth_ids": ["growth:scoped"],
                }],
            )

    def test_open_discovery_seed_identity_prefers_case_then_truth(self):
        findings = [
            {
                "batch_target_name": "owner/repo",
                "finding_id": "finding:case",
                "growth_id": "growth:case",
                "verdict": "static_vulnerable",
            },
            {
                "batch_target_name": "owner/repo",
                "finding_id": "finding:truth",
                "growth_id": "growth:truth",
                "verdict": "static_vulnerable",
            },
        ]
        dispositions = [
            {
                "batch_target_name": "owner/repo",
                "disposition_id": f"disposition:{index}",
                "growth_id": finding["growth_id"],
                "status": "formal_eligible",
                "negative_proof_ids": [],
            }
            for index, finding in enumerate(findings)
        ]

        result = evaluate_open_discovery(
            findings=findings,
            dispositions=dispositions,
            negative_proofs=[],
            seed_matches=[
                {
                    "case_id": "case:chosen",
                    "truth_id": "truth:must-not-win",
                    "repository": "owner/repo",
                    "status": "full_chain_finding",
                    "matched_finding_ids": ["finding:case"],
                },
                {
                    "truth_id": "truth:only",
                    "repository": "owner/repo",
                    "status": "growth_only",
                    "matched_growth_ids": ["growth:truth"],
                },
            ],
        )

        by_growth = {row["growth_id"]: row for row in result["discoveries"]}
        self.assertEqual(["case:chosen"], by_growth["growth:case"]["seed_ids"])
        self.assertEqual(["truth:only"], by_growth["growth:truth"]["seed_ids"])

    def test_open_discovery_rejects_concrete_seed_ids_without_identity(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            evaluate_open_discovery(
                findings=[{
                    "batch_target_name": "owner/repo",
                    "finding_id": "finding:scoped",
                    "growth_id": "growth:scoped",
                    "verdict": "static_vulnerable",
                }],
                dispositions=[{
                    "batch_target_name": "owner/repo",
                    "disposition_id": "disposition:scoped",
                    "growth_id": "growth:scoped",
                    "status": "formal_eligible",
                    "negative_proof_ids": [],
                }],
                negative_proofs=[],
                seed_matches=[{
                    "repository": "owner/repo",
                    "status": "growth_only",
                    "matched_growth_ids": ["growth:scoped"],
                }],
            )

    def test_open_discovery_identity_priority_does_not_skip_invalid_record_id(self):
        with self.assertRaisesRegex(ValueError, "record_id"):
            evaluate_open_discovery(
                findings=[],
                dispositions=[],
                negative_proofs=[],
                seed_matches=[{
                    "record_id": "",
                    "case_id": "case:must-not-win",
                    "truth_id": "truth:must-not-win",
                    "repository": "owner/repo",
                    "status": "no_candidate",
                }],
            )

    def test_open_discovery_uses_strict_repository_alias_normalization(self):
        finding = {
            "batch_target_name": "Owner/Repo",
            "repository": "owner/repo",
            "finding_id": "finding:strict-scope",
            "growth_id": "growth:strict-scope",
            "verdict": "static_vulnerable",
        }
        disposition = {
            "batch_target_name": "OWNER/REPO",
            "repository": "owner/repo",
            "disposition_id": "disposition:strict-scope",
            "growth_id": "growth:strict-scope",
            "status": "formal_eligible",
            "negative_proof_ids": [],
        }
        result = evaluate_open_discovery(
            findings=[finding],
            dispositions=[disposition],
            negative_proofs=[],
            seed_matches=[{
                "case_id": "case:strict-scope",
                "repository": "OWNER/REPO",
                "status": "hit",
                "chain": {
                    "finding_id": "finding:strict-scope",
                    "growth_id": "growth:strict-scope",
                },
            }],
        )
        self.assertEqual(
            ["case:strict-scope"],
            result["discoveries"][0]["seed_ids"],
        )

        invalid_findings = {
            "target-id-only": {
                **finding,
                "batch_target_name": "",
                "repository": "",
                "target_id": "target:hash",
            },
            "unicode-casefold": {
                **finding,
                "batch_target_name": "straße/repo",
                "repository": "straße/repo",
            },
            "conflicting-aliases": {
                **finding,
                "batch_target_name": "owner/repo",
                "repository": "other/repo",
            },
        }
        for label, invalid_finding in invalid_findings.items():
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    evaluate_open_discovery(
                        findings=[invalid_finding],
                        dispositions=[disposition],
                        negative_proofs=[],
                        seed_matches=[],
                    )

    def test_open_discovery_requires_known_disposition_for_every_finding(self):
        finding = {
            "batch_target_name": "owner/repo",
            "finding_id": "finding:orphan",
            "growth_id": "growth:orphan",
            "verdict": "static_vulnerable",
        }
        with self.assertRaisesRegex(ValueError, "disposition"):
            evaluate_open_discovery(
                findings=[finding],
                dispositions=[],
                negative_proofs=[],
                seed_matches=[],
            )

        with self.assertRaisesRegex(ValueError, "status"):
            evaluate_open_discovery(
                findings=[finding],
                dispositions=[{
                    "batch_target_name": "owner/repo",
                    "disposition_id": "disposition:unknown",
                    "growth_id": "growth:orphan",
                    "status": "unexpected",
                    "negative_proof_ids": [],
                }],
                negative_proofs=[],
                seed_matches=[],
            )

    def test_open_discovery_rejects_malformed_matched_id_lists(self):
        invalid_values = (
            "growth:not-a-list",
            ("growth:tuple",),
            [""],
            [1],
            ["growth:duplicate", "growth:duplicate"],
        )
        for field in ("matched_finding_ids", "matched_growth_ids"):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        evaluate_open_discovery(
                            findings=[],
                            dispositions=[],
                            negative_proofs=[],
                            seed_matches=[{
                                "record_id": "record:invalid-list",
                                "repository": "owner/repo",
                                "status": "stage_failed",
                                field: value,
                            }],
                        )

    def test_open_discovery_rejects_duplicate_scoped_seed_identity(self):
        with self.assertRaisesRegex(ValueError, "duplicated"):
            evaluate_open_discovery(
                findings=[],
                dispositions=[],
                negative_proofs=[],
                seed_matches=[
                    {
                        "case_id": "case:duplicate",
                        "repository": "owner/repo",
                        "status": "no_candidate",
                    },
                    {
                        "case_id": "case:duplicate",
                        "repository": "OWNER/REPO",
                        "status": "no_candidate",
                    },
                ],
            )

    def test_open_discovery_rejects_invalid_negative_proof_id_lists(self):
        invalid_values = (
            "negative-proof:not-a-list",
            ("negative-proof:tuple",),
            [""],
            [1],
            ["negative-proof:duplicate", "negative-proof:duplicate"],
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "negative_proof_ids"):
                    evaluate_open_discovery(
                        findings=[],
                        dispositions=[{
                            "batch_target_name": "owner/repo",
                            "disposition_id": "disposition:invalid-proof-list",
                            "growth_id": "growth:invalid-proof-list",
                            "status": "rejected",
                            "negative_proof_ids": value,
                        }],
                        negative_proofs=[],
                        seed_matches=[],
                    )

    def test_open_discovery_preserves_valid_negative_proof_ids(self):
        result = evaluate_open_discovery(
            findings=[],
            dispositions=[{
                "batch_target_name": "owner/repo",
                "disposition_id": "disposition:proof",
                "growth_id": "growth:proof",
                "status": "rejected",
                "negative_proof_ids": ["negative-proof:one"],
            }],
            negative_proofs=[{
                "batch_target_name": "owner/repo",
                "negative_proof_id": "negative-proof:one",
                "growth_id": "growth:proof",
                "kind": "finite_keyspace",
            }],
            seed_matches=[],
        )
        self.assertEqual(
            ["negative-proof:one"],
            result["discoveries"][0]["negative_proof_ids"],
        )

    def test_open_discovery_enforces_finding_disposition_and_verdict_contract(self):
        invalid_cases = {
            "invalid-verdict": (
                _finding(verdict="dynamic_confirmed"),
                _disposition(),
            ),
            "gap-vulnerable": (
                _finding(verdict="static_vulnerable"),
                _disposition(status="gap_eligible"),
            ),
            "gap-bounded": (
                _finding(verdict="bounded_under_modeled_assumptions"),
                _disposition(status="gap_eligible"),
            ),
            "rejected-finding": (
                _finding(),
                _disposition(
                    status="rejected",
                    negative_proof_ids=["negative_proof:fixture"],
                ),
            ),
            "inventory-finding": (
                _finding(verdict="static_unknown"),
                _disposition(status="inventory_unresolved"),
            ),
        }
        for label, (finding, disposition) in invalid_cases.items():
            proofs = (
                [_negative_proof()]
                if disposition["status"] == "rejected"
                else []
            )
            with self.subTest(label=label), self.assertRaises(ValueError):
                evaluate_open_discovery(
                    findings=[finding],
                    dispositions=[disposition],
                    negative_proofs=proofs,
                    seed_matches=[],
                )

    def test_open_discovery_malformed_scalar_contracts_raise_value_error(self):
        cases = {
            "finding-verdict": (
                [{**_finding(), "verdict": []}],
                [_disposition()],
                [],
                [],
            ),
            "disposition-status": (
                [_finding()],
                [{**_disposition(), "status": []}],
                [],
                [],
            ),
            "proof-kind": (
                [],
                [_disposition(
                    status="rejected",
                    negative_proof_ids=["negative_proof:fixture"],
                )],
                [{**_negative_proof(), "kind": []}],
                [],
            ),
            "seed-status": (
                [],
                [],
                [],
                [{
                    "record_id": "seed:malformed-status",
                    "repository": "owner/repo",
                    "status": [],
                }],
            ),
        }
        for label, arguments in cases.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                evaluate_open_discovery(
                    findings=arguments[0],
                    dispositions=arguments[1],
                    negative_proofs=arguments[2],
                    seed_matches=arguments[3],
                )

    def test_open_discovery_enforces_exact_typed_negative_proof_ownership(self):
        cases = {
            "rejected-empty": (
                [_disposition(status="rejected")],
                [],
            ),
            "formal-proof": (
                [_disposition(negative_proof_ids=["negative_proof:fixture"])],
                [_negative_proof()],
            ),
            "wrong-growth": (
                [_disposition(
                    status="rejected",
                    negative_proof_ids=["negative_proof:fixture"],
                )],
                [_negative_proof(growth_id="growth:other")],
            ),
            "invalid-kind": (
                [_disposition(
                    status="rejected",
                    negative_proof_ids=["negative_proof:fixture"],
                )],
                [_negative_proof(kind="free_text")],
            ),
            "orphan-proof": (
                [_disposition(status="inventory_unresolved")],
                [_negative_proof()],
            ),
        }
        for label, (dispositions, proofs) in cases.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                evaluate_open_discovery(
                    findings=[],
                    dispositions=dispositions,
                    negative_proofs=proofs,
                    seed_matches=[],
                )

    def test_open_discovery_rejects_stale_links_on_non_linking_seed_statuses(self):
        for status in (
            "no_candidate",
            "target_not_run",
            "artifact_missing",
            "truth_invalid",
            "stage_failed",
            "entry_only",
            "asset_missing",
            "unsupported_scope",
        ):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "non-linking"):
                evaluate_open_discovery(
                    findings=[_finding()],
                    dispositions=[_disposition()],
                    negative_proofs=[],
                    seed_matches=[{
                        "record_id": f"seed:{status}",
                        "repository": "owner/repo",
                        "status": status,
                        "matched_finding_ids": ["finding:fixture"],
                    }],
                )

    def test_open_discovery_rejects_ordinary_matched_status_verdict_mismatch(self):
        expected = {
            "hit": "static_vulnerable",
            "matched_static_unknown": "static_unknown",
            "matched_bounded": "bounded_under_modeled_assumptions",
        }
        for status, matching_verdict in expected.items():
            wrong_verdict = next(
                verdict
                for verdict in (
                    "static_vulnerable",
                    "static_unknown",
                    "bounded_under_modeled_assumptions",
                )
                if verdict != matching_verdict
            )
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "status"):
                evaluate_open_discovery(
                    findings=[_finding(verdict=wrong_verdict)],
                    dispositions=[_disposition()],
                    negative_proofs=[],
                    seed_matches=[{
                        "case_id": f"seed:{status}",
                        "repository": "owner/repo",
                        "status": status,
                        "chain": {
                            "finding_id": "finding:fixture",
                            "growth_id": "growth:fixture",
                        },
                    }],
                )

    def test_open_discovery_rejects_seed_finding_growth_chain_mismatch(self):
        findings = [
            _finding(),
            _finding(
                finding_id="finding:other",
                growth_id="growth:other",
            ),
        ]
        dispositions = [
            _disposition(),
            _disposition(
                disposition_id="disposition:other",
                growth_id="growth:other",
            ),
        ]
        with self.assertRaisesRegex(ValueError, "chain"):
            evaluate_open_discovery(
                findings=findings,
                dispositions=dispositions,
                negative_proofs=[],
                seed_matches=[{
                    "record_id": "seed:mismatch",
                    "repository": "owner/repo",
                    "status": "full_chain_finding",
                    "matched_finding_ids": ["finding:fixture"],
                    "matched_growth_ids": ["growth:other"],
                }],
            )

    def test_open_discovery_allows_finding_growth_subset_of_declared_growths(self):
        findings = [
            _finding(
                finding_id="finding:powerjob",
                growth_id="growth:powerjob:g2",
            )
        ]
        dispositions = [
            _disposition(
                disposition_id="disposition:powerjob:g1",
                growth_id="growth:powerjob:g1",
            ),
            _disposition(
                disposition_id="disposition:powerjob:g2",
                growth_id="growth:powerjob:g2",
            ),
        ]
        result = evaluate_open_discovery(
            findings=findings,
            dispositions=dispositions,
            negative_proofs=[],
            seed_matches=[{
                "record_id": "POWERJOB-APP-STATIC-0002",
                "repository": "owner/repo",
                "status": "full_chain_finding",
                "matched_finding_ids": ["finding:powerjob"],
                "matched_growth_ids": [
                    "growth:powerjob:g1",
                    "growth:powerjob:g2",
                ],
            }],
        )

        by_growth = {row["growth_id"]: row for row in result["discoveries"]}
        self.assertEqual(
            ["POWERJOB-APP-STATIC-0002"],
            by_growth["growth:powerjob:g1"]["seed_ids"],
        )
        self.assertEqual(
            "seed_linked_static_vulnerable",
            by_growth["growth:powerjob:g2"]["classification"],
        )

    def test_open_discovery_validates_equivalent_seed_carriers_before_union(self):
        with self.assertRaisesRegex(ValueError, "carrier"):
            evaluate_open_discovery(
                findings=[],
                dispositions=[],
                negative_proofs=[],
                seed_matches=[{
                    "record_id": "seed:conflicting-carriers",
                    "repository": "owner/repo",
                    "status": "ambiguous_truth_match",
                    "matched_finding_ids": ["finding:matched"],
                    "matched_growth_ids": ["growth:matched"],
                    "chain": {
                        "finding_id": "finding:chain",
                        "growth_id": "growth:chain",
                    },
                    "candidate": {
                        "finding": {"finding_id": "finding:candidate"},
                        "growth": {"growth_id": "growth:candidate"},
                    },
                }],
            )

        with self.assertRaisesRegex(ValueError, "carrier"):
            evaluate_open_discovery(
                findings=[],
                dispositions=[],
                negative_proofs=[],
                seed_matches=[{
                    "record_id": "seed:disconnected-carriers",
                    "repository": "owner/repo",
                    "status": "ambiguous_truth_match",
                    "chain": {"growth_id": "growth:novel"},
                    "candidate": {
                        "finding": {"finding_id": "finding:novel"},
                    },
                }],
            )

        result = evaluate_open_discovery(
            findings=[_finding(
                finding_id="finding:carrier",
                growth_id="growth:carrier:g2",
            )],
            dispositions=[
                _disposition(
                    disposition_id="disposition:carrier:g1",
                    growth_id="growth:carrier:g1",
                ),
                _disposition(
                    disposition_id="disposition:carrier:g2",
                    growth_id="growth:carrier:g2",
                ),
            ],
            negative_proofs=[],
            seed_matches=[{
                "record_id": "seed:compatible-carriers",
                "repository": "owner/repo",
                "status": "full_chain_finding",
                "matched_finding_ids": ["finding:carrier"],
                "matched_growth_ids": [
                    "growth:carrier:g1",
                    "growth:carrier:g2",
                ],
                "chain": {
                    "finding_id": "finding:carrier",
                    "growth_id": "growth:carrier:g2",
                },
                "candidate": {
                    "finding": {"finding_id": "finding:carrier"},
                    "growth": {"growth_id": "growth:carrier:g2"},
                },
            }],
        )
        self.assertEqual(2, len(result["discoveries"]))
        self.assertFalse(any(row["recall_miss"] for row in result["discoveries"]))

        connected_novel = evaluate_open_discovery(
            findings=[],
            dispositions=[],
            negative_proofs=[],
            seed_matches=[{
                "record_id": "seed:connected-carriers",
                "repository": "owner/repo",
                "status": "ambiguous_truth_match",
                "matched_finding_ids": ["finding:novel"],
                "chain": {
                    "finding_id": "finding:novel",
                    "growth_id": "growth:novel",
                },
                "candidate": {
                    "growth": {"growth_id": "growth:novel"},
                },
            }],
        )
        self.assertEqual(1, len(connected_novel["discoveries"]))
        self.assertTrue(connected_novel["discoveries"][0]["recall_miss"])

    def test_open_discovery_rejects_seed_analysis_id_owned_by_another_repository(self):
        with self.assertRaisesRegex(ValueError, "cross-repository"):
            evaluate_open_discovery(
                findings=[_finding(repository="owner/first")],
                dispositions=[_disposition(repository="owner/first")],
                negative_proofs=[],
                seed_matches=[{
                    "record_id": "seed:wrong-scope",
                    "repository": "owner/second",
                    "status": "growth_only",
                    "matched_growth_ids": ["growth:fixture"],
                }],
            )

    def test_open_discovery_claims_missing_seed_ids_globally_by_repository(self):
        for field, concrete_id in (
            ("matched_finding_ids", "finding:missing"),
            ("matched_growth_ids", "growth:missing"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "cross-repository"
            ):
                evaluate_open_discovery(
                    findings=[],
                    dispositions=[],
                    negative_proofs=[],
                    seed_matches=[
                        {
                            "record_id": f"seed:first:{field}",
                            "repository": "owner/first",
                            "status": "ambiguous_truth_match",
                            field: [concrete_id],
                        },
                        {
                            "record_id": f"seed:second:{field}",
                            "repository": "owner/second",
                            "status": "ambiguous_truth_match",
                            field: [concrete_id],
                        },
                    ],
                )

        same_scope = evaluate_open_discovery(
            findings=[],
            dispositions=[],
            negative_proofs=[],
            seed_matches=[
                {
                    "record_id": "seed:first:same-scope",
                    "repository": "owner/repo",
                    "status": "growth_only",
                    "matched_growth_ids": ["growth:missing"],
                },
                {
                    "record_id": "seed:second:same-scope",
                    "repository": "OWNER/REPO",
                    "status": "growth_only",
                    "matched_growth_ids": ["growth:missing"],
                },
            ],
        )
        self.assertEqual(2, len(same_scope["discoveries"]))
        self.assertTrue(
            all(row["recall_miss"] for row in same_scope["discoveries"])
        )

    def test_open_discovery_emits_deterministic_seed_only_rows_for_all_recall_misses(self):
        result = evaluate_open_discovery(
            findings=[_finding()],
            dispositions=[_disposition()],
            negative_proofs=[],
            seed_matches=[
                {
                    "record_id": "seed:no-ids",
                    "repository": "owner/repo",
                    "status": "entry_only",
                },
                {
                    "case_id": "seed:missing-id",
                    "truth_id": "seed:must-not-win",
                    "repository": "owner/repo",
                    "status": "growth_only",
                    "matched_growth_ids": ["growth:absent"],
                },
            ],
        )

        misses = [row for row in result["discoveries"] if row["recall_miss"]]
        self.assertEqual(
            ["seed:missing-id", "seed:no-ids"],
            sorted(row["seed_ids"][0] for row in misses),
        )
        self.assertEqual(
            ["entry_only", "growth_only"],
            sorted(row["seed_status"] for row in misses),
        )
        self.assertTrue(
            all(row["classification"] == "unresolved_discovery" for row in misses)
        )
        for field in ("finding_id", "growth_id", "disposition_id", "static_verdict"):
            self.assertTrue(all(row[field] is None for row in misses))
