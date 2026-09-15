import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from dosweb.cli import main
import tests.test_resource_lifecycle_cli as fixtures


class ShardedCliTests(unittest.TestCase):
    def test_missing_required_shard_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = fixtures.ResourceLifecycleCliTests()._manifest(root)
            facts, run = root / "facts", root / "run"
            self.assertEqual(0, main(["resource-extract", "--manifest", str(manifest), "--out", str(facts)]))
            self.assertEqual(0, main(["resource-analyze", "--facts", str(facts / "facts.json"),
                                      "--out", str(run), "--sharded", "--llm", "off"]))
            self.assertEqual(0, main(["resource-replay", "--run", str(run)]))
            for shard in (run / "shared").glob("*.json"):
                shard.unlink()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(0, main(["resource-replay", "--run", str(run)]))
                self.assertNotEqual(0, main(["resource-replay", "--run", str(run), "--integrity-only"]))
