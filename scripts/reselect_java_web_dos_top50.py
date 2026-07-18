#!/usr/bin/env python3
"""Create, select, render, and audit a reproducible Java Web DoS Top-50."""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dosweb.errors import AnalyzerError
from dosweb.top50.contracts import (
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
    write_text_atomically,
)


MARKDOWN_SLUG_RE = re.compile(r"`([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)`")


def _load_slugs(path: Path) -> list[str]:
    if path.suffix.casefold() == ".json":
        snapshot = read_json_object(path, "initial snapshot")
        projects = snapshot.get("projects")
        if not isinstance(projects, list):
            raise AnalyzerError("TOP50_INVALID_FIELD", f"initial snapshot {path} requires projects list")
        slugs: list[str] = []
        for index, project in enumerate(projects):
            if not isinstance(project, dict) or not isinstance(project.get("slug_normalized"), str):
                raise AnalyzerError("TOP50_INVALID_FIELD", f"initial snapshot {path} projects[{index}] requires slug_normalized")
            slugs.append(project["slug_normalized"])
        return slugs
    spec = importlib.util.spec_from_file_location("top50_builder_manifest", REPO_ROOT / "scripts" / "build_top50_codeql_dbs.py")
    if spec is None or spec.loader is None:
        raise AnalyzerError("TOP50_INVALID_FIELD", "unable to load old Top-50 manifest parser")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.load_slugs(path)
    except (FileNotFoundError, ValueError) as exc:
        raise AnalyzerError("TOP50_INVALID_FIELD", str(exc)) from exc


def _write_new_json(path: Path, document: dict[str, object]) -> None:
    if path.exists():
        raise AnalyzerError("TOP50_OUTPUT_EXISTS", f"refusing to overwrite immutable output: {path}")
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
            _write_new_json(args.output, capture_snapshot(args.source_root, args.db_root))
            return 0
        reviewed = validate_reviewed_candidates(read_jsonl_strict(args.reviewed, "reviewed_candidates")) if args.command in {"validate-review", "select"} else None
        if args.command == "validate-review":
            reserves = read_jsonl_strict(args.reserves, "reserve_candidates")
            validate_reserve_candidates(reserves, reviewed or {}, set())
            return 0
        if args.command == "select":
            reserves = read_jsonl_strict(args.reserves, "reserve_candidates")
            document = select_targets(reviewed or {}, reserves, set(_load_slugs(args.old_manifest)), set(_load_slugs(args.initial_manifest)))
            write_json_atomically(args.output, document)
            return 0
        document, old_slugs, initial_slugs = _selected_and_sets(args)
        if args.command == "render":
            _assert_distinct_render_paths(args)
            validate_selected_targets(document, old_slugs, initial_slugs)
            write_text_atomically(args.markdown_output, render_markdown(document))
            write_json_atomically(args.intel_output, render_intel_json(document))
            write_json_atomically(args.overlap_output, overlap_report(document, old_slugs, initial_slugs))
            return 0
        markdown_slugs = MARKDOWN_SLUG_RE.findall(args.markdown.read_text(encoding="utf-8"))
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
        write_json_atomically(args.output, report)
        return 0
    except AnalyzerError as exc:
        print(f"error [{exc.code}]: {exc.message}", file=sys.stderr)
        return exc.exit_status


if __name__ == "__main__":
    raise SystemExit(main())
