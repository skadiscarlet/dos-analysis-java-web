#!/usr/bin/env python3
"""Aggregate Java Web DoS batch outputs.

The implementation lives in :mod:`dosweb.batch.aggregate`; this script is a
small compatibility CLI for historical archives and explicit P0 archives.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dosweb.batch.aggregate import (
    STATIC_VERDICTS,
    add_meta,
    aggregate,
    latest_status_by_slug,
    read_findings,
    read_jsonl,
    record_static_verdict,
    target_meta,
    validate_manifest,
    write_jsonl,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-root", required=True, type=Path)
    parser.add_argument(
        "--format",
        choices=("historical", "p0"),
        default=None,
        help="artifact contract to aggregate (required unless legacy-safe detection is used)",
    )
    parser.add_argument(
        "--p0",
        action="store_true",
        help="short form for --format p0",
    )
    args = parser.parse_args(argv)
    if args.p0 and args.format is not None:
        parser.error("use either --format or --p0, not both")
    # Historical auto-detection is deliberately narrow: every manifest row
    # must explicitly carry the legacy hunter_output_dir and no row may carry
    # normative plan identity.  P0 is never inferred from missing fields.
    selected = args.format
    if args.p0:
        selected = "p0"
    if selected is None:
        manifest_path = args.batch_root / "manifest.normalized.jsonl"
        try:
            rows = read_jsonl(manifest_path)
        except (FileNotFoundError, ValueError) as exc:
            parser.error(str(exc))
        legacy = bool(rows) and all(
            isinstance(row.get("hunter_output_dir"), str) and row["hunter_output_dir"].strip()
            and not any(key in row for key in ("target_id", "identity", "output_path"))
            for row in rows
        )
        if not legacy:
            parser.error("--format is required; manifest is not unambiguously historical (use --format p0 or --format historical)")
        selected = "historical"
    try:
        aggregate(args.batch_root.resolve(), selected)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
