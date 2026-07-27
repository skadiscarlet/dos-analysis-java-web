from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import os
from pathlib import Path
import sys
from typing import Any

from dosweb.errors import AnalyzerError

_COMMANDS = ("analyze", "entries", "growth", "flows", "lifecycle", "conclude", "report")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AnalyzerError(
            "CONFIG_INVALID_VALUE",
            "Command-line arguments are invalid.",
            {"diagnostic": message[-512:]},
        )


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="dos-web-analyzer")
    parser.add_argument("command", nargs="?", choices=_COMMANDS)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path)
    remote = parser.add_mutually_exclusive_group()
    remote.add_argument("--allow-remote-llm", dest="allow_remote_llm", action="store_true")
    remote.add_argument("--no-remote-llm", dest="allow_remote_llm", action="store_false")
    parser.set_defaults(allow_remote_llm=None)
    parser.add_argument("--public-source-url")
    parser.add_argument("--source-commit-sha")
    parser.add_argument("--source-checkout", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--max-retries", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--codeql-binary")
    parser.add_argument("--resume", action="store_true", default=None)
    return parser


def parse_cli_values(argv: Sequence[str] | None = None) -> dict[str, object]:
    """Parse only; this function never constructs a provider or performs I/O."""
    return vars(_parser().parse_args(argv))


def _make_pipeline(factory: Callable[..., object], values: Mapping[str, object]) -> object:
    try:
        signature = __import__("inspect").signature(factory)
    except (TypeError, ValueError):
        return factory(values)
    environment = dict(os.environ)
    candidates = (
        ((values,), {"environ": environment}),
        ((values,), {}),
        ((), {"values": values, "environ": environment}),
        ((), {"values": values}),
        ((), {}),
    )
    for arguments, keywords in candidates:
        try:
            signature.bind(*arguments, **keywords)
        except TypeError:
            continue
        return factory(*arguments, **keywords)
    raise TypeError("pipeline factory has an unsupported signature")


def dispatch(
    values: Mapping[str, object],
    *,
    pipeline_factory: Callable[..., object] | None = None,
) -> object:
    """Dispatch one command through the injected or production pipeline."""
    command = values.get("command")
    if not isinstance(command, str) or command not in _COMMANDS:
        raise AnalyzerError("CONFIG_INVALID_COMMAND", "A valid pipeline subcommand is required.")
    if pipeline_factory is None:
        from dosweb.production import build_production_pipeline

        pipeline_factory = build_production_pipeline
    try:
        pipeline = _make_pipeline(pipeline_factory, values)
    except AnalyzerError:
        raise
    except Exception as exc:
        raise AnalyzerError(
            "INTERNAL_PIPELINE_FACTORY_FAILED",
            "Injected local pipeline factory failed.",
            {"error_type": type(exc).__name__},
        ) from exc
    run = getattr(pipeline, "run", None)
    if not callable(run):
        raise AnalyzerError("INTERNAL_PIPELINE_INVALID", "Injected pipeline has no callable run method.")
    try:
        return run(command)
    except AnalyzerError:
        raise
    except Exception as exc:
        raise AnalyzerError(
            "INTERNAL_PIPELINE_FAILED",
            "Injected pipeline dispatch failed.",
            {"error_type": type(exc).__name__},
        ) from exc


def main(
    argv: Sequence[str] | None = None,
    *,
    pipeline_factory: Callable[..., object] | None = None,
) -> int:
    try:
        values = parse_cli_values(argv)
        dispatch(values, pipeline_factory=pipeline_factory)
        return 0
    except AnalyzerError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return exc.exit_status


__all__ = ["dispatch", "main", "parse_cli_values"]
