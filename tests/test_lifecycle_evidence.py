from __future__ import annotations

import unittest

from pathlib import Path

from dosweb.lifecycle import LifecycleCoverage, LifecycleEvidence
from dosweb.production import _same_java_callable


class LifecycleEvidenceTests(unittest.TestCase):
    def test_path_bound_evidence_and_coverage_are_canonical(self) -> None:
        evidence = LifecycleEvidence(
            "entry:a", "growth:b", "flow:c", "bound", "bound:d",
            "src/A.java", 10, "src/A.java", 12, "field:pkg.A.queue",
            "field:pkg.A.queue", "key", "same_cfg", "complete",
        )
        self.assertEqual(LifecycleEvidence.from_dict(evidence.to_dict()), evidence)
        coverage = LifecycleCoverage("entry:a", "growth:b", "flow:c", "bound", "complete", "BOUND_QUERY_COMPLETE")
        self.assertEqual(LifecycleCoverage.from_dict(coverage.to_dict()), coverage)

    def test_cross_path_or_partial_binding_is_not_promoted(self) -> None:
        evidence = LifecycleEvidence(
            "entry:a", "growth:b", "flow:one", "release", "release:d",
            "src/A.java", 10, "src/B.java", 12, "receiver:text", "unknown", "none", "partial", "partial",
        )
        self.assertEqual(evidence.cfg_relation, "partial")
        self.assertEqual(evidence.coverage_status, "partial")

    def test_same_callable_binding_rejects_cross_handler_receiver_reuse(self) -> None:
        root = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "netty" / "src" / "main" / "java"
        relative = "fixture/netty/NettyFixture.java"
        # channelRead body lines must bind internally, while an initializer and
        # handler must never share a lifecycle witness merely because they are
        # in the same source file.
        self.assertTrue(_same_java_callable(root, relative, 50, 54))
        self.assertFalse(_same_java_callable(root, relative, 22, 50))


if __name__ == "__main__":
    unittest.main()
