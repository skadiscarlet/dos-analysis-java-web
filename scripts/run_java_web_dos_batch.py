#!/usr/bin/env python3
"""Plan or execute the canonical Java Web DoS batch without implicit network use."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
import inspect
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dosweb.batch.corpus import load_canonical_corpus
from dosweb.batch.plan import build_batch_plan, ensure_batch_plan_archive, load_batch_plan, publish_batch_plan
from dosweb.batch.runner import run_batch
from dosweb.codeql.database import validate_database
from dosweb.config import _DEFAULT_SECRETS_PATH, resolve_api_key
from dosweb.errors import AnalyzerError


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AnalyzerError("BATCH_ARGUMENT_INVALID", "Batch command-line arguments are invalid.", {"diagnostic": message[-512:]})


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="run_java_web_dos_batch.py")
    parser.add_argument("mode", choices=("plan", "entries", "full"))
    parser.add_argument("--plan", type=Path, help="execute an existing batch_plan.json")
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "intel/applications/java_web_205_targets.json")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--refresh-completed",
        action="store_true",
        help="re-enter completed targets so pipeline resume can invalidate stale stages",
    )
    parser.add_argument("--allow-remote-llm", action="store_true", help="authorize remote provider use during full execution")
    parser.add_argument("--plan-only", action="store_true", help="publish a plan but do not execute it (including full mode)")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--max-retries", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--codeql-binary")
    return parser


def _provider_settings(arguments: argparse.Namespace) -> dict[str, object]:
    """Return plan-safe provider settings; credentials never enter a plan."""
    settings: dict[str, object] = {"allow_remote_llm": bool(arguments.allow_remote_llm)}
    for name in ("model", "base_url", "timeout_seconds", "max_retries", "temperature", "codeql_binary"):
        value = getattr(arguments, name)
        if value is not None:
            settings[name] = value
    for name in ("cache_dir", "config"):
        value = getattr(arguments, name)
        if value is not None:
            settings[name] = value.as_posix()
    return settings


def _bind_provider_settings(plan: object, settings: Mapping[str, object]) -> object:
    """Bind the complete non-secret CLI provider configuration to the plan digest."""
    # The plan helper intentionally has a conservative historical allow-list.
    # This CLI binds its additional path settings here without changing runner
    # or aggregation behavior, and recomputes the identity-bearing digest.
    from dosweb.artifacts.identifiers import sha256_canonical_json

    provider = dict(getattr(plan, "provider", {}))
    provider.update(settings)
    if getattr(plan, "mode", None) == "entries":
        provider["allow_remote_llm"] = False
    unsigned = dict(plan.unsigned_dict())
    unsigned["provider"] = provider
    digest = sha256_canonical_json(unsigned)
    return replace(plan, provider=provider, plan_id=f"plan:{digest[:24]}", plan_digest=digest)


def _bound_pipeline_factory(factory: Callable[..., object], provider: Mapping[str, object]) -> Callable[..., object]:
    """Inject plan-bound settings into runner values without changing the runner."""
    def bound(values: Mapping[str, object], *, environ: Mapping[str, str] | None = None) -> object:
        effective = dict(values)
        for key, value in provider.items():
            if key == "allow_remote_llm":
                # Entry extraction is permanently provider-independent; a
                # plan/provider overlay must not re-enable remote calls.
                effective[key] = False if effective.get("command") == "entries" else value
            elif value is not None:
                effective[key] = Path(value) if key in {"cache_dir", "config"} and isinstance(value, str) else value
        try:
            signature = inspect.signature(factory)
        except (TypeError, ValueError):
            return factory(effective)
        candidates = (
            ((effective,), {"environ": environ}),
            ((effective,), {}),
            ((), {"values": effective, "environ": environ}),
            ((), {"values": effective}),
        )
        for args, kwargs in candidates:
            try:
                signature.bind(*args, **kwargs)
            except TypeError:
                continue
            return factory(*args, **kwargs)
        raise TypeError("pipeline factory has an unsupported signature")
    return bound


def main(
    argv: Sequence[str] | None = None,
    *,
    pipeline_factory: Callable[..., object] | None = None,
    environ: Mapping[str, str] | None = None,
    corpus_loader: Callable[..., object] = load_canonical_corpus,
    database_validator: Callable[..., object] = validate_database,
) -> int:
    try:
        arguments = _parser().parse_args(argv)
        environment = dict(os.environ if environ is None else environ)
        if arguments.mode == "full" and not arguments.plan_only:
            if not arguments.allow_remote_llm:
                raise AnalyzerError("BATCH_REMOTE_LLM_NOT_AUTHORIZED", "Full batch mode requires --allow-remote-llm.")
            if not resolve_api_key(environment, _DEFAULT_SECRETS_PATH):
                raise AnalyzerError("BATCH_REMOTE_LLM_NOT_AUTHORIZED", "Full batch mode requires provider credentials.")
        if arguments.plan is not None:
            plan = load_batch_plan(arguments.plan)
            if plan.mode != arguments.mode:
                raise AnalyzerError("BATCH_MODE_INVALID", "Requested mode does not match the published plan.")
        else:
            if not arguments.run_id:
                raise AnalyzerError("BATCH_ARGUMENT_INVALID", "--run-id is required when creating a plan.")
            corpus = corpus_loader(arguments.manifest, repo_root=arguments.repo_root)
            try:
                output_root = arguments.output.resolve().relative_to(arguments.repo_root.resolve()).as_posix()
            except ValueError:
                # Plan paths are repository-relative by contract; the CLI may
                # still publish the plan into an external temporary directory.
                output_root = arguments.output.name
            plan = _bind_provider_settings(
                build_batch_plan(
                    corpus,
                    run_id=arguments.run_id,
                    mode=arguments.mode,
                    output_root=output_root,
                    provider_settings=_provider_settings(arguments),
                ),
                _provider_settings(arguments),
            )
            publish_batch_plan(plan, arguments.output)
        # Planning is always non-executing, including a full plan.  A full run
        # requires two independent operator gates at execution time.
        if arguments.mode == "plan" or arguments.plan_only:
            return 0
        if arguments.mode == "full":
            if not arguments.allow_remote_llm:
                raise AnalyzerError("BATCH_REMOTE_LLM_NOT_AUTHORIZED", "Full batch execution requires --allow-remote-llm.")
            if plan.provider.get("allow_remote_llm") is not True:
                raise AnalyzerError(
                    "BATCH_REMOTE_LLM_NOT_AUTHORIZED",
                    "Published full plan does not authorize remote execution; create a new plan with --allow-remote-llm.",
                )
            if not resolve_api_key(environment, _DEFAULT_SECRETS_PATH):
                raise AnalyzerError("BATCH_REMOTE_LLM_NOT_AUTHORIZED", "Full batch mode requires provider credentials.")
        # Execution output is the canonical P0 archive even when the immutable
        # plan was loaded from elsewhere. Never replace conflicting metadata.
        ensure_batch_plan_archive(plan, arguments.output)
        if pipeline_factory is None:
            from dosweb.production import build_production_pipeline

            pipeline_factory = build_production_pipeline
        provider = dict(plan.provider)
        if arguments.mode == "full" and arguments.allow_remote_llm:
            # CLI consent is the execution-time gate; do not rewrite an
            # already-published plan merely to execute it.
            provider["allow_remote_llm"] = True
        state = run_batch(
            plan,
            arguments.output,
            pipeline_factory=_bound_pipeline_factory(pipeline_factory, provider),
            max_workers=arguments.max_workers,
            resume=not arguments.no_resume,
            retry_failed=arguments.retry_failed,
            refresh_completed=arguments.refresh_completed,
            max_attempts=arguments.max_attempts,
            repo_root=arguments.repo_root,
            environ=environment,
            database_validator=database_validator,
        )
        return 0 if state.get("status") == "completed" else 1
    except AnalyzerError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return exc.exit_status


if __name__ == "__main__":
    raise SystemExit(main())
