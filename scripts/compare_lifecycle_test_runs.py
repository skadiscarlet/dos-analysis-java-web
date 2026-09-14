#!/usr/bin/env python3
"""Compare JUnit test identities without publishing raw failure logs."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def read_run(path):
    data = path.read_bytes()
    root = ET.fromstring(data)
    outcomes = {key: {} for key in ("failed", "errors", "skipped")}
    passed = []
    for case in root.iter("testcase"):
        identity = case.get("classname", "") + "::" + case.get("name", "")
        for tag, key in (("failure", "failed"), ("error", "errors"), ("skipped", "skipped")):
            node = case.find(tag)
            if node is not None:
                # Failure bodies can contain local source and paths. Publish
                # only identities; skip reasons are needed for coverage audit.
                outcomes[key][identity] = node.get("message", "") if key == "skipped" else tag
                break
        else:
            passed.append(identity)
    return {
        "xml_sha256": hashlib.sha256(data).hexdigest(),
        "counts": {**{key: len(value) for key, value in outcomes.items()}, "passed_xml_records": len(passed)},
        **outcomes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("final", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    baseline, final = read_run(args.baseline), read_run(args.final)
    differences = {}
    for category in ("failed", "errors", "skipped"):
        before, after = set(baseline[category]), set(final[category])
        differences[category] = {"added": sorted(after - before), "resolved": sorted(before - after), "persistent": sorted(before & after)}
    result = {
        "baseline": baseline, "final": final, "differences": differences,
        "scope": "Same host and pytest command with --continue-on-collection-errors; ignored assets absent in both worktrees. JUnit records may include subtests.",
        "limitations": ["Collection error prevents coverage of the legacy global-skill test module.", "Missing ignored assets remain failed; no complete-suite green claim."],
        "new_failure_ids": differences["failed"]["added"],
        "new_error_ids": differences["errors"]["added"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
