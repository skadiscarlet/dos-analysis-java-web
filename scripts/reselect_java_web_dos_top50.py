#!/usr/bin/env python3
"""Create, select, render, and audit a reproducible Java Web DoS Top-50."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dosweb.errors import AnalyzerError
from dosweb.top50.contracts import (
    normalize_slug,
    read_jsonl_strict,
    validate_reserve_candidates,
    validate_reviewed_candidates,
    validate_selected_targets,
    write_json_atomically,
)
from dosweb.top50.selection import (
    audit_selection,
    capture_snapshot,
    overlap_report,
    read_json_object,
    read_status_events,
    render_intel_json,
    render_markdown,
    select_targets,
    write_render_transaction,
)


MARKDOWN_SLUG_RE = re.compile(r"`([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)`")
DEFAULT_SOURCE_ROOT = REPO_ROOT / "frameworks" / "applications"
DEFAULT_DB_ROOT = REPO_ROOT / "databases" / "applications"


def _load_slugs(path: Path) -> list[str]:
    suffix = path.suffix.casefold()
    if suffix == ".json":
        document = read_json_object(path, "slug snapshot")
        slugs = document.get("slugs")
        if not isinstance(slugs, list) or not all(isinstance(slug, str) for slug in slugs):
            projects = document.get("projects")
            if isinstance(projects, list):
                slugs = [item.get("slug_normalized") for item in projects if isinstance(item, dict)]
            else:
                raise AnalyzerError("TOP50_INVALID_FIELD", f"{path}: JSON snapshot requires a slugs string list")
        normalized: list[str] = []
        for index, slug in enumerate(slugs):
            normalized.append(normalize_slug(slug, f"{path}.slugs[{index}]"))
        if len(set(normalized)) != len(normalized):
            raise AnalyzerError("TOP50_DUPLICATE_SLUG", f"{path}: duplicate normalized slug")
        return normalized
    if suffix == ".jsonl":
        records = read_jsonl_strict(path, "slug records")
        slugs: list[str] = []
        for index, record in enumerate(records):
            slug = record.get("slug_normalized", record.get("slug"))
            if not isinstance(slug, str):
                raise AnalyzerError("TOP50_INVALID_FIELD", f"{path}:{index + 1}: slug or slug_normalized is required")
            slugs.append(normalize_slug(slug, f"{path}:{index + 1}.slug"))
        if len(set(slugs)) != len(slugs):
            raise AnalyzerError("TOP50_DUPLICATE_SLUG", f"{path}: duplicate normalized slug")
        return slugs
    raise AnalyzerError("TOP50_INVALID_JSON", f"{path}: slug artifacts must use .json or .jsonl; Markdown/plain text is not accepted")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _assert_safe_output(path: Path, source_root: Path, db_root: Path, *, immutable: bool = False) -> None:
    resolved = path.resolve(strict=False)
    if _is_within(resolved, source_root) or _is_within(resolved, db_root):
        raise AnalyzerError("TOP50_OUTPUT_EXISTS", f"output must not overwrite source or database assets: {path}")
    if path.is_symlink() or (path.exists() and (path.is_dir() or stat.S_ISFIFO(path.stat().st_mode) or stat.S_ISSOCK(path.stat().st_mode) or stat.S_ISCHR(path.stat().st_mode) or stat.S_ISBLK(path.stat().st_mode))):
        raise AnalyzerError("TOP50_OUTPUT_EXISTS", f"output path is not a regular file: {path}")
    if immutable and path.exists():
        raise AnalyzerError("TOP50_OUTPUT_EXISTS", f"refusing to overwrite immutable output: {path}")


def _assert_not_input(path: Path, inputs: tuple[Path, ...]) -> None:
    resolved = path.resolve(strict=False)
    if any(resolved == candidate.resolve(strict=False) for candidate in inputs):
        raise AnalyzerError("TOP50_OUTPUT_EXISTS", f"output must not overwrite command input: {path}")


def _write_new_json(path: Path, document: dict[str, object], source_root: Path, db_root: Path) -> None:
    _assert_safe_output(path, source_root, db_root, immutable=True)
    write_json_atomically(path, document)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    snapshot = commands.add_parser("snapshot", help="capture the immutable first-level source inventory")
    snapshot.add_argument("--source-root", type=Path, required=True)
    snapshot.add_argument("--db-root", type=Path, required=True)
    snapshot.add_argument("--output", type=Path, required=True)

    validate = commands.add_parser("validate-review", help="validate reviewed candidates and replacement reserves")
    validate.add_argument("--reviewed", type=Path, required=True)
    validate.add_argument("--reserves", type=Path, required=True)

    select = commands.add_parser("select", help="write deterministic selected targets and reserves")
    select.add_argument("--reviewed", type=Path, required=True)
    select.add_argument("--reserves", type=Path, required=True)
    select.add_argument("--old-manifest", type=Path, required=True)
    select.add_argument("--initial-manifest", "--initial-snapshot", dest="initial_manifest", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)

    render = commands.add_parser("render", help="render Markdown and intel JSON from one selected document")
    render.add_argument("--selected", type=Path, required=True)
    render.add_argument("--old-manifest", type=Path, required=True)
    render.add_argument("--initial-manifest", "--initial-snapshot", dest="initial_manifest", type=Path, required=True)
    render.add_argument("--markdown-output", type=Path, required=True)
    render.add_argument("--intel-output", type=Path, required=True)
    render.add_argument("--overlap-output", type=Path, required=True)

    audit = commands.add_parser("audit", help="audit sources, commits, databases, constraints, and rendered outputs")
    audit.add_argument("--selected", type=Path, required=True)
    audit.add_argument("--old-manifest", type=Path, required=True)
    audit.add_argument("--initial-manifest", "--initial-snapshot", dest="initial_manifest", type=Path, required=True)
    audit.add_argument("--source-root", type=Path, required=True)
    audit.add_argument("--db-root", type=Path, required=True)
    audit.add_argument("--status-events", type=Path, required=True)
    audit.add_argument("--markdown", type=Path, required=True)
    audit.add_argument("--intel", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    return result


def _assert_distinct_render_paths(args: argparse.Namespace) -> None:
    inputs = {path.resolve(strict=False) for path in (args.selected, args.old_manifest, args.initial_manifest)}
    outputs = [args.markdown_output.resolve(strict=False), args.intel_output.resolve(strict=False), args.overlap_output.resolve(strict=False)]
    if len(set(outputs)) != len(outputs) or any(path in inputs for path in outputs):
        raise AnalyzerError("TOP50_OUTPUT_EXISTS", "render outputs must be distinct and must not overwrite inputs")
    for output in (args.markdown_output, args.intel_output, args.overlap_output):
        _assert_safe_output(output, DEFAULT_SOURCE_ROOT, DEFAULT_DB_ROOT)


def _selected_and_sets(args: argparse.Namespace) -> tuple[dict[str, object], set[str], set[str]]:
    return (
        read_json_object(args.selected, "selected targets"),
        set(_load_slugs(args.old_manifest)),
        set(_load_slugs(args.initial_manifest)),
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            _write_new_json(args.output, capture_snapshot(args.source_root, args.db_root), args.source_root, args.db_root)
            return 0
        reviewed = validate_reviewed_candidates(read_jsonl_strict(args.reviewed, "reviewed_candidates")) if args.command in {"validate-review", "select"} else None
        if args.command == "validate-review":
            reserves = read_jsonl_strict(args.reserves, "reserve_candidates")
            validate_reserve_candidates(reserves, reviewed or {}, set())
            return 0
        if args.command == "select":
            _assert_not_input(args.output, (args.reviewed, args.reserves, args.old_manifest, args.initial_manifest))
            reserves = read_jsonl_strict(args.reserves, "reserve_candidates")
            document = select_targets(reviewed or {}, reserves, set(_load_slugs(args.old_manifest)), set(_load_slugs(args.initial_manifest)))
            _assert_safe_output(args.output, DEFAULT_SOURCE_ROOT, DEFAULT_DB_ROOT)
            write_json_atomically(args.output, document)
            return 0
        if args.command == "render":
            document, old_slugs, initial_slugs = _selected_and_sets(args)
            _assert_distinct_render_paths(args)
            validate_selected_targets(document, old_slugs, initial_slugs)
            write_render_transaction({
                args.markdown_output: render_markdown(document),
                args.intel_output: json.dumps(render_intel_json(document), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                args.overlap_output: json.dumps(overlap_report(document, old_slugs, initial_slugs), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            })
            return 0
        document, old_slugs, initial_slugs = _selected_and_sets(args)
        _assert_not_input(args.output, (args.selected, args.old_manifest, args.initial_manifest, args.status_events, args.markdown, args.intel))
        _assert_safe_output(args.output, args.source_root, args.db_root)
        try:
            markdown_slugs = MARKDOWN_SLUG_RE.findall(args.markdown.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            raise AnalyzerError("TOP50_INVALID_JSON", f"unable to read Markdown output {args.markdown}: {exc}") from exc
        try:
            report = audit_selection(
                document,
                old_slugs,
                initial_slugs,
                args.source_root,
                args.db_root,
                read_status_events(args.status_events),
                markdown_slugs,
                read_json_object(args.intel, "intel JSON"),
            )
        except AnalyzerError as exc:
            failure = {
                "schema_version": "1.0",
                "status": "failed",
                "failure_summary": exc.message,
                "error_code": exc.code,
            }
            write_json_atomically(args.output, failure)
            raise
        write_json_atomically(args.output, report)
        return 0
    except AnalyzerError as exc:
        print(f"error [{exc.code}]: {exc.message}", file=sys.stderr)
        return exc.exit_status


if __name__ == "__main__":
    raise SystemExit(main())
