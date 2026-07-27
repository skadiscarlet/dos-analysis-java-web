"""Opt-in DeepSeek integration using one fixed artificial public fixture slice.

The only accepted checkout is the public https://github.com/octocat/Hello-World fixture.
`DOSWEB_PUBLIC_FIXTURE_SHA` must be a full commit from that repository whose README is
exactly the fixed artificial text ``Hello World!\n``. The test validates that constraint
before constructing the slice, so no caller-selected target source content is sent.

DOSWEB_RUN_DEEPSEEK_INTEGRATION=1 DEEPSEEK_API_KEY=... \
DOSWEB_PUBLIC_FIXTURE_SHA=<full-40-hex-fixture-commit> \
DOSWEB_PUBLIC_FIXTURE_CHECKOUT=/clean/octocat-hello-world-checkout \
python -m unittest tests.integration.test_deepseek_online -v
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from dosweb.config import DEFAULT_BASE_URL, LlmConfig
from dosweb.growth.models import BoundedSlice, BoundedSlicePayload, CfgSummary, GrowthContract, RegistrationFact, SourceExcerpt, StaticFact
from dosweb.llm.deepseek import DeepSeekClient

_FIXTURE_REPOSITORY = "https://github.com/octocat/Hello-World"
_FIXTURE_PATH = "README"
_FIXTURE_CONTENT = "Hello World!\n"
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class DeepSeekOnlineTests(unittest.TestCase):
    def test_public_fixture_returns_growth_contract(self) -> None:
        required = {name: os.environ.get(name) for name in (
            "DEEPSEEK_API_KEY", "DOSWEB_PUBLIC_FIXTURE_SHA", "DOSWEB_PUBLIC_FIXTURE_CHECKOUT",
        )}
        if os.environ.get("DOSWEB_RUN_DEEPSEEK_INTEGRATION") != "1" or not all(required.values()):
            self.skipTest("Set the explicit integration guard, API key, and pinned fixed-fixture checkout guards.")
        sha, checkout = required["DOSWEB_PUBLIC_FIXTURE_SHA"], Path(required["DOSWEB_PUBLIC_FIXTURE_CHECKOUT"])
        if not _FULL_SHA.fullmatch(sha):
            self.fail("DOSWEB_PUBLIC_FIXTURE_SHA must be a full lower-case 40-hex fixture commit.")
        object_id = f"{sha}:{_FIXTURE_PATH}"
        metadata = subprocess.run(
            ["git", "-C", str(checkout), "cat-file", "--batch-check=%(objecttype) %(objectsize)"],
            input=f"{object_id}\n".encode("ascii"), check=True, stdout=subprocess.PIPE,
        ).stdout.rstrip(b"\n").split()
        expected = _FIXTURE_CONTENT.encode("utf-8")
        self.assertEqual(metadata, [b"blob", str(len(expected)).encode("ascii")], "fixture blob metadata must match the fixed bounded payload")
        blob = subprocess.run(["git", "-C", str(checkout), "show", object_id], check=True, stdout=subprocess.PIPE).stdout
        self.assertEqual(blob, expected, "fixture commit must contain only the documented artificial README text")
        excerpt = SourceExcerpt("excerpt:fixture", _FIXTURE_PATH, 1, 1, _FIXTURE_CONTENT, hashlib.sha256(blob).hexdigest(), hashlib.sha256(blob).hexdigest())
        payload = BoundedSlicePayload(
            "entry:fixture", "growth:fixture", (excerpt,),
            (StaticFact("fact:source", "flow", "excerpt:fixture", "source"),),
            CfgSummary(("path:fixture",), ("in_handler",), ("fact:source",)),
            (RegistrationFact("spring_mvc", "excerpt:fixture"),), (),
        )
        with tempfile.TemporaryDirectory() as directory:
            config = LlmConfig("deepseek-v4-pro", DEFAULT_BASE_URL, required["DEEPSEEK_API_KEY"], 60, 3, 0, Path(directory) / "cache", True, _FIXTURE_REPOSITORY, sha, checkout)
            result = DeepSeekClient(config).classify_growth(BoundedSlice("slice:fixture", payload))
        self.assertIsInstance(result, GrowthContract)


if __name__ == "__main__":
    unittest.main()
