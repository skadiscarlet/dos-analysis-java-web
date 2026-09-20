"""Bounded, resumable execution of a published Java Web batch plan."""
from __future__ import annotations

from collections import Counter, deque
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import nullcontext
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path, PurePosixPath
import signal
import threading
from typing import Any

from dosweb.artifacts.identifiers import canonical_json
from dosweb.batch.models import BatchPlan, BatchTargetPlan
from dosweb.batch.plan import write_target_binding
from dosweb.batch.state import BatchState, atomic_write_json, batch_lock
from dosweb.codeql.database import DatabaseInfo, validate_database
from dosweb.config import _DEFAULT_SECRETS_PATH, resolve_api_key
from dosweb.errors import AnalyzerError

PipelineFactory = Callable[..., object]
DatabaseValidator = Callable[..., DatabaseInfo]
Clock = Callable[[], datetime | str]

# Retry decisions are made from the persisted error code, never from a message
# or exception type.  The generic injected-pipeline code remains for backwards
# compatibility with the original runner contract.
_RETRYABLE_ERROR_CODES = frozenset({
    "LLM_RETRYABLE_HTTP",
    "LLM_NETWORK_RETRYABLE",
    "LLM_RETRIES_EXHAUSTED",
    # These failures are terminal for one provider call, but not deterministic
    # across a fresh target attempt.  Permit only the runner's already-bounded
    # retry so a malformed/sensitive model response or a one-off permanent
    # network classification cannot strand an otherwise reusable formal run.
    "LLM_AUTHENTICATION_FAILED",
    "LLM_NETWORK_FAILED",
    "LLM_RESPONSE_INVALID",
    "LLM_RESPONSE_SCHEMA_INVALID",
    "LLM_RESPONSE_SENSITIVE_CONTENT",
    # A target may observe canonical-database drift after its private snapshot
    # has finished.  The next attempt still revalidates the plan-bound database
    # fingerprint before constructing a fresh private snapshot, so bounded
    # target retry is safe while a real persistent drift remains fail-closed.
    "CODEQL_EXECUTION_SNAPSHOT_FAILED",
    "BATCH_TARGET_FAILED",
})


def _timestamp(clock: Clock) -> str:
    value = clock()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat(timespec="seconds")
    if isinstance(value, str) and value:
        return value
    raise TypeError("clock must return datetime or non-empty string")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, AnalyzerError):
        return exc.code, exc.message[:512]
    return "BATCH_TARGET_FAILED", f"Target pipeline failed ({type(exc).__name__})."


def _target_directory(batch_root: Path, target: BatchTargetPlan) -> Path:
    # The plan path is identity-bearing, but the caller chooses where the
    # published plan directory lives.  Keep only the deterministic target leaf.
    path = PurePosixPath(target.output_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise AnalyzerError("BATCH_TARGET_OUTPUT_INVALID", "Batch target output path is invalid.")
    try:
        targets_index = path.parts.index("targets")
        suffix = path.parts[targets_index + 1 :]
    except ValueError:
        suffix = path.parts[-1:]
    if len(suffix) != 1:
        raise AnalyzerError("BATCH_TARGET_OUTPUT_INVALID", "Batch target output path is invalid.")
    output = batch_root / "targets" / suffix[0]
    try:
        output.resolve(strict=False).relative_to(batch_root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise AnalyzerError("BATCH_TARGET_OUTPUT_INVALID", "Batch target output path is invalid.") from exc
    return output


def _factory_call(factory: PipelineFactory, values: Mapping[str, object], environ: Mapping[str, str]) -> object:
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return factory(values)
    candidates = (
        ((values,), {"environ": environ}),
        ((values,), {}),
        ((), {"values": values, "environ": environ}),
        ((), {"values": values}),
    )
    for arguments, keywords in candidates:
        try:
            signature.bind(*arguments, **keywords)
        except TypeError:
            continue
        return factory(*arguments, **keywords)
    raise TypeError("pipeline factory has an unsupported signature")


def _resolve_input(repo_root: Path, raw: str) -> Path:
    relative = PurePosixPath(raw.replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise AnalyzerError("BATCH_TARGET_INPUT_INVALID", "Batch target input path is invalid.")
    path = (repo_root / Path(*relative.parts)).resolve(strict=False)
    try:
        path.relative_to(repo_root)
    except ValueError as exc:
        raise AnalyzerError("BATCH_TARGET_INPUT_INVALID", "Batch target input path is invalid.") from exc
    return path


def _atomic_jsonl(path: Path, rows: list[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join(canonical_json(dict(row)) + b"\n" for row in rows)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


class BatchRunner:
    """Execute independent target pipelines with bounded thread concurrency."""

    def __init__(
        self,
        plan: BatchPlan,
        output_directory: Path | str,
        *,
        pipeline_factory: PipelineFactory,
        max_workers: int = 3,
        resume: bool = True,
        retry_failed: bool = False,
        max_attempts: int = 2,
        repo_root: Path | str | None = None,
        environ: Mapping[str, str] | None = None,
        clock: Clock = _utcnow,
        database_validator: DatabaseValidator = validate_database,
    ) -> None:
        if not plan.verify_digest() or plan.plan_id != f"plan:{plan.plan_digest[:24]}":
            raise AnalyzerError("BATCH_PLAN_INVALID", "Batch plan digest or canonical identity does not match its contents.")
        target_ids = [target.target_id for target in plan.targets]
        indexes = [target.identity.index for target in plan.targets]
        output_dirs = [PurePosixPath(target.output_path).parts[-1] for target in plan.targets]
        if len(set(target_ids)) != len(target_ids) or len(set(indexes)) != len(indexes) or len(set(output_dirs)) != len(output_dirs):
            raise AnalyzerError("BATCH_PLAN_INVALID", "Batch plan contains duplicate target identities or output directories.")
        if plan.mode not in {"entries", "full"}:
            raise AnalyzerError("BATCH_MODE_INVALID", "Only entries and full plans can be executed.")
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or not 1 <= max_workers <= 5:
            raise AnalyzerError("BATCH_CONCURRENCY_INVALID", "Batch concurrency must be between 1 and 5.")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 16:
            raise AnalyzerError("BATCH_RETRY_INVALID", "Batch max attempts must be between 1 and 16.")
        self.plan = plan
        self.output_directory = Path(output_directory)
        self.pipeline_factory = pipeline_factory
        self.max_workers = max_workers
        self.resume = resume
        self.retry_failed = retry_failed
        self.max_attempts = max_attempts
        self.repo_root = Path(repo_root or Path.cwd()).resolve()
        self.environ = dict(os.environ if environ is None else environ)
        self.clock = clock
        self.database_validator = database_validator
        self.state_path = self.output_directory / "batch_state.json"
        self.lock_path = self.output_directory / ".batch.lock"
        self._state_lock = threading.Lock()
        self._state: BatchState | None = None
        self._interrupt = threading.Event()
        self._interrupted_target_ids: set[str] = set()
        self._signal_handlers: dict[int, Any] = {}

    def _request_interrupt(self) -> None:
        # Signal handlers must not take locks or perform I/O: a signal can
        # arrive while the main thread already owns the state lock.
        self._interrupt.set()
        state = self._state
        if state is not None:
            self._interrupted_target_ids.update(
                target_id
                for target_id, record in state.targets.items()
                if record.get("state") in {"queued", "running", "retrying"}
            )

    def _mark_interrupted(self) -> None:
        if self._state is None:
            return
        with self._state_lock:
            changed = False
            for target_id, record in self._state.targets.items():
                if record.get("state") in {"queued", "running", "retrying"}:
                    self._interrupted_target_ids.add(target_id)
                if target_id in self._interrupted_target_ids and record.get("state") != "interrupted":
                    self._state.update_target(
                        target_id,
                        state="interrupted",
                        status="interrupted",
                        error_code="BATCH_INTERRUPTED",
                        error_message="Batch execution was interrupted.",
                        finished_at=_timestamp(self.clock),
                    )
                    changed = True
            if changed:
                self._publish(self._state)

    def _install_signal_handlers(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._signal_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, lambda _signum, _frame: self._request_interrupt())

    def _restore_signal_handlers(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for signum, handler in self._signal_handlers.items():
            signal.signal(signum, handler)
        self._signal_handlers.clear()

    def _initial_records(self) -> dict[str, dict[str, object]]:
        records: dict[str, dict[str, object]] = {}
        for target in self.plan.targets:
            records[target.target_id] = {
                "target_id": target.target_id,
                "target": target.identity.name,
                "slug": target.identity.slug,
                "fingerprint_type": target.identity.fingerprint_type,
                "fingerprint": target.identity.fingerprint,
                "output_path": str(_target_directory(self.output_directory, target).relative_to(self.output_directory)),
                "state": target.initial_state,
                "status": target.initial_state,
                "attempt": 0,
                "error_code": None,
                "error_message": None,
                "started_at": None,
                "finished_at": None,
            }
        return records

    def _load_or_create_state(self) -> BatchState:
        if self.resume and self.state_path.exists():
            try:
                state = BatchState.load(self.state_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise AnalyzerError("BATCH_STATE_INVALID", "Batch state could not be resumed.") from exc
            by_id = {target.target_id: target for target in self.plan.targets}
            if state.batch_id != self.plan.plan_id or state.mode != self.plan.mode or set(state.targets) != set(by_id):
                raise AnalyzerError("BATCH_STATE_IDENTITY_MISMATCH", "Batch state does not match the execution plan.")
            for target_id, target in by_id.items():
                record = state.targets[target_id]
                expected_output = str(_target_directory(self.output_directory, target).relative_to(self.output_directory))
                if (
                    record.get("target_id") != target_id
                    or record.get("target") != target.identity.name
                    or record.get("slug") != target.identity.slug
                    or record.get("fingerprint_type") != target.identity.fingerprint_type
                    or record.get("fingerprint") != target.identity.fingerprint
                    or record.get("output_path") != expected_output
                ):
                    raise AnalyzerError("BATCH_STATE_IDENTITY_MISMATCH", "Batch state target identity does not match the execution plan.")
            return state
        state = BatchState(
            batch_id=self.plan.plan_id,
            mode=self.plan.mode,
            targets=self._initial_records(),
            created_at=_timestamp(self.clock),
            updated_at=_timestamp(self.clock),
        )
        self._publish(state)
        return state

    def _compatibility_rows(self, state: BatchState) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        by_id = {target.target_id: target for target in self.plan.targets}
        for target_id in sorted(state.targets, key=lambda key: by_id[key].identity.index):
            target = by_id[target_id]
            record = state.targets[target_id]
            rows.append({
                "target_id": target_id,
                "target": target.identity.name,
                "slug": target.identity.slug,
                "status": record.get("state", "queued"),
                "failure_reason": record.get("error_code"),
                "hunter_output_dir": record.get("output_path"),
                "attempt": record.get("attempt", 0),
                "updated_at": record.get("updated_at"),
            })
        return rows

    def _publish(self, state: BatchState) -> None:
        state.updated_at = _timestamp(self.clock)
        try:
            atomic_write_json(self.state_path, state.to_dict())
            rows = self._compatibility_rows(state)
            _atomic_jsonl(self.output_directory / "batch_status.jsonl", rows)
            _atomic_jsonl(self.output_directory / "status.jsonl", rows)
        except (OSError, ValueError) as exc:
            raise AnalyzerError("BATCH_STATE_PUBLISH_FAILED", "Batch state could not be published.") from exc

    def _update(self, target_id: str, **fields: object) -> None:
        assert self._state is not None
        with self._state_lock:
            current = self._state.targets[target_id].get("state")
            # A worker may finish after the signal handler has published the
            # interruption.  Never let that late completion overwrite it.
            if target_id in self._interrupted_target_ids or (self._interrupt.is_set() and current == "interrupted"):
                fields = {
                    "state": "interrupted",
                    "status": "interrupted",
                    "error_code": "BATCH_INTERRUPTED",
                    "error_message": "Batch execution was interrupted.",
                    "finished_at": fields.get("finished_at") or _timestamp(self.clock),
                }
            fields["updated_at"] = _timestamp(self.clock)
            self._state.update_target(target_id, **fields)
            self._publish(self._state)

    def _completed_artifacts_reusable(self, target: BatchTargetPlan) -> bool:
        output = _target_directory(self.output_directory, target)
        binding_path = output / "batch_target.json"
        run_path = output / "run.json"
        try:
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            run = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        expected = {"plan_id": self.plan.plan_id, "plan_digest": self.plan.plan_digest, "run_id": self.plan.run_id, "mode": self.plan.mode, "analysis_mode": self.plan.analysis_mode, "query_failure_policy": self.plan.query_failure_policy, "target": target.to_dict()}
        return binding == expected and isinstance(run, Mapping) and run.get("status") == "completed"

    def _normalize_completed_gaps(self) -> None:
        """Convert exhausted completed records with missing artifacts to gaps."""
        assert self._state is not None
        changed = False
        for target in self.plan.targets:
            record = self._state.targets[target.target_id]
            attempt = record.get("attempt", 0)
            if (
                record.get("state") == "completed"
                and isinstance(attempt, int)
                and not isinstance(attempt, bool)
                and attempt >= self.max_attempts
                and not self._completed_artifacts_reusable(target)
            ):
                self._state.update_target(
                    target.target_id,
                    state="completed_with_gaps",
                    status="completed_with_gaps",
                    error_code="BATCH_TARGET_ARTIFACTS_MISSING",
                    error_message="Completed target artifacts are missing or mismatched after exhausting attempts.",
                    finished_at=record.get("finished_at") or _timestamp(self.clock),
                )
                changed = True
        if changed:
            self._publish(self._state)

    def _validate_database_binding(
        self,
        target: BatchTargetPlan,
        database: Path,
        source_checkout: Path,
    ) -> None:
        if not target.database_fingerprint:
            return
        try:
            info = self.database_validator(database)
        except AnalyzerError:
            raise
        except Exception as exc:
            raise AnalyzerError(
                "BATCH_DATABASE_VALIDATION_FAILED",
                "Target CodeQL database could not be validated.",
            ) from exc
        if not isinstance(info, DatabaseInfo):
            raise AnalyzerError(
                "BATCH_DATABASE_VALIDATION_FAILED",
                "Target CodeQL database validator returned an invalid result.",
            )
        if info.fingerprint != target.database_fingerprint:
            raise AnalyzerError(
                "BATCH_DATABASE_FINGERPRINT_MISMATCH",
                "Target CodeQL database no longer matches the execution plan.",
            )
        try:
            source_matches = (
                info.source_root.resolve(strict=False)
                == source_checkout.resolve(strict=False)
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise AnalyzerError(
                "BATCH_DATABASE_SOURCE_ROOT_INVALID",
                "Target CodeQL database source root could not be resolved.",
            ) from exc
        if not source_matches:
            raise AnalyzerError(
                "BATCH_DATABASE_SOURCE_ROOT_MISMATCH",
                "Target CodeQL database does not belong to the planned source checkout.",
            )

    def _eligible(self, target: BatchTargetPlan, record: Mapping[str, object]) -> bool:
        state = record.get("state", target.initial_state)
        attempt = record.get("attempt", 0)
        if isinstance(attempt, bool) or not isinstance(attempt, int):
            return False
        if state == "completed":
            # A state record alone is not enough to skip a target on resume.
            # Missing/mismatched artifacts are repaired by a bounded rerun.
            return not self._completed_artifacts_reusable(target) and attempt < self.max_attempts
        if state in {"completed_with_gaps", "paused"}:
            return False
        if state == "failed":
            if not self.retry_failed:
                return False
            if record.get("error_code") not in _RETRYABLE_ERROR_CODES:
                return False
        return attempt < self.max_attempts

    def _run_target(self, target: BatchTargetPlan) -> None:
        assert self._state is not None
        record = self._state.targets[target.target_id]
        attempt = int(record.get("attempt", 0)) + 1
        try:
            # Persist the attempt before any target-directory setup so mkdir,
            # path, and binding failures remain isolated to this target.
            self._update(
                target.target_id,
                state="retrying" if attempt > 1 else "running",
                status="retrying" if attempt > 1 else "running",
                attempt=attempt,
                started_at=_timestamp(self.clock),
                finished_at=None,
                error_code=None,
                error_message=None,
            )
            database = _resolve_input(self.repo_root, target.identity.database_path)
            analysis_source = _resolve_input(self.repo_root, target.identity.source_path)
            self._validate_database_binding(target, database, analysis_source)
            source_checkout = _resolve_input(
                self.repo_root,
                target.capability.provider_source_path or target.identity.source_path,
            )
            output = _target_directory(self.output_directory, target)
            output.mkdir(parents=True, exist_ok=True)
            binding_path = output / "batch_target.json"
            if binding_path.exists():
                try:
                    binding = json.loads(binding_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise AnalyzerError("BATCH_TARGET_BINDING_INVALID", "Existing target binding is malformed.") from exc
                expected = {"plan_id": self.plan.plan_id, "plan_digest": self.plan.plan_digest, "run_id": self.plan.run_id, "mode": self.plan.mode, "analysis_mode": self.plan.analysis_mode, "query_failure_policy": self.plan.query_failure_policy, "target": target.to_dict()}
                if binding != expected:
                    raise AnalyzerError("BATCH_TARGET_IDENTITY_MISMATCH", "Existing target output belongs to another identity.")
            else:
                write_target_binding(self.plan, target, output)
            environment = dict(self.environ)
            public_source_url = target.capability.public_source_url
            provider_commit = target.capability.provider_source_commit or (
                target.identity.fingerprint if target.identity.fingerprint_type == "git-commit"
                else None
            )
            if self.plan.mode == "entries":
                provider_checkout = nullcontext(source_checkout)
            elif self.plan.mode == "full":
                if self.plan.analysis_mode not in {"", "formal"} or self.plan.query_failure_policy not in {"", "fail_closed"}:
                    raise AnalyzerError("BATCH_PLAN_INVALID", "Formal plan has an invalid query failure policy.")
                if not resolve_api_key(environment, _DEFAULT_SECRETS_PATH):
                    raise AnalyzerError("BATCH_REMOTE_LLM_NOT_AUTHORIZED", "Full batch mode requires explicit provider authorization.")
                # Git commit provenance is not required: use the local source tree directly.
                provider_checkout = nullcontext(source_checkout)
            else:
                provider_checkout = nullcontext(source_checkout)
            with provider_checkout as prepared_checkout:
                values: dict[str, object] = {
                    "command": "entries" if self.plan.mode == "entries" else "analyze",
                    "database": database,
                    "output": output,
                    "analysis_source_root": analysis_source,
                    "source_checkout": prepared_checkout,
                    "source_commit_sha": provider_commit,
                    "public_source_url": public_source_url,
                    "resume": self.resume,
                    "allow_remote_llm": self.plan.mode == "full",
                    "allow_partial_codeql": self.plan.analysis_mode == "exploratory_entries" and self.plan.query_failure_policy == "coverage_gap",
                }
                if self.plan.mode == "entries":
                    if self.plan.analysis_mode not in {"", "exploratory_entries"} or self.plan.query_failure_policy not in {"", "coverage_gap"}:
                        raise AnalyzerError("BATCH_PLAN_INVALID", "Entries plan has an invalid query failure policy.")
                    # Entry extraction must be provider-independent even if the
                    # parent process happens to carry credentials.
                    environment.pop("DEEPSEEK_API_KEY", None)
                    values["allow_remote_llm"] = False
                    values["public_source_url"] = None
                pipeline = _factory_call(self.pipeline_factory, values, environment)
                run = getattr(pipeline, "run", None)
                if not callable(run):
                    raise AnalyzerError("BATCH_PIPELINE_INVALID", "Injected pipeline has no callable run method.")
                result = run(values["command"])
            if not isinstance(result, Mapping) or result.get("status") != "completed":
                raise AnalyzerError(
                    "BATCH_PIPELINE_INCOMPLETE",
                    "Target pipeline did not report completed status.",
                )
            self._update(target.target_id, state="completed", status="completed", finished_at=_timestamp(self.clock))
        except (KeyboardInterrupt, SystemExit):
            # Worker control-flow escapes must become durable target state; do
            # not let BaseException escape through Future.result().
            self._interrupted_target_ids.add(target.target_id)
            self._update(
                target.target_id,
                state="interrupted",
                status="interrupted",
                error_code="BATCH_INTERRUPTED",
                error_message="Batch execution was interrupted.",
                finished_at=_timestamp(self.clock),
            )
            self._interrupt.set()
        except Exception as exc:
            code, message = _safe_error(exc)
            self._update(
                target.target_id,
                state="failed",
                status="failed",
                error_code=code,
                error_message=message,
                finished_at=_timestamp(self.clock),
            )

    def run(self) -> Mapping[str, object]:
        if self.plan.mode == "full":
            if self.plan.provider.get("allow_remote_llm") is not True:
                raise AnalyzerError("BATCH_REMOTE_LLM_NOT_AUTHORIZED", "Full batch plan requires explicit remote provider authorization.")
            if not resolve_api_key(self.environ, _DEFAULT_SECRETS_PATH):
                raise AnalyzerError("BATCH_REMOTE_LLM_NOT_AUTHORIZED", "Full batch mode requires provider credentials.")
        try:
            with batch_lock(self.lock_path, blocking=False):
                self.output_directory.mkdir(parents=True, exist_ok=True)
                self._state = self._load_or_create_state()
                self._normalize_completed_gaps()
                self._state.set_status("running", updated_at=_timestamp(self.clock))
                self._publish(self._state)
                self._install_signal_handlers()
                targets = [
                    target for target in self.plan.targets
                    if self._eligible(target, self._state.targets[target.target_id])
                ]
                pending = deque(targets)
                active: dict[object, BatchTargetPlan] = {}
                with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="dosweb-batch") as pool:
                    def submit_available() -> None:
                        while not self._interrupt.is_set() and len(active) < self.max_workers:
                            if not pending:
                                return
                            target = pending.popleft()
                            active[pool.submit(self._run_target, target)] = target

                    submit_available()
                    while active:
                        try:
                            done, _ = wait(tuple(active), timeout=0.1, return_when=FIRST_COMPLETED)
                        except KeyboardInterrupt:
                            self._request_interrupt()
                            self._mark_interrupted()
                            continue
                        if self._interrupt.is_set():
                            self._mark_interrupted()
                        for future in done:
                            target = active.pop(future, None)
                            try:
                                future.result()
                            except (KeyboardInterrupt, SystemExit):
                                if target is not None:
                                    self._interrupted_target_ids.add(target.target_id)
                                self._request_interrupt()
                                self._mark_interrupted()
                            if (
                                target is not None
                                and not self._interrupt.is_set()
                                and self._eligible(
                                    target,
                                    self._state.targets[target.target_id],
                                )
                            ):
                                pending.append(target)
                        submit_available()
                if self._interrupt.is_set():
                    self._mark_interrupted()
                self._normalize_completed_gaps()
                states = Counter(record.get("state", "queued") for record in self._state.targets.values())
                if self._interrupt.is_set() or states.get("interrupted"):
                    final = "interrupted"
                elif states.get("failed"):
                    final = "completed_with_failures"
                elif any(
                    states.get(name)
                    for name in ("paused", "queued", "running", "retrying", "completed_with_gaps", "interrupted")
                ):
                    final = "completed_with_gaps"
                else:
                    final = "completed"
                self._state.set_status(final, updated_at=_timestamp(self.clock))
                self._publish(self._state)
                result = self._state.to_dict()
                if final == "interrupted":
                    raise AnalyzerError("BATCH_INTERRUPTED", "Batch execution was interrupted.", {"state": result})
                return result
        except BlockingIOError as exc:
            raise AnalyzerError("BATCH_LOCKED", "Another process is already running this batch.") from exc
        except AnalyzerError:
            raise
        except (OSError, ValueError) as exc:
            raise AnalyzerError("BATCH_RUNNER_FAILED", "Batch runner setup failed.") from exc
        finally:
            self._restore_signal_handlers()


def run_batch(
    plan: BatchPlan,
    output_directory: Path | str,
    *,
    pipeline_factory: PipelineFactory,
    max_workers: int = 3,
    resume: bool = True,
    retry_failed: bool = False,
    max_attempts: int = 2,
    repo_root: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    clock: Clock = _utcnow,
    database_validator: DatabaseValidator = validate_database,
) -> Mapping[str, object]:
    return BatchRunner(
        plan,
        output_directory,
        pipeline_factory=pipeline_factory,
        max_workers=max_workers,
        resume=resume,
        retry_failed=retry_failed,
        max_attempts=max_attempts,
        repo_root=repo_root,
        environ=environ,
        clock=clock,
        database_validator=database_validator,
    ).run()


__all__ = ["BatchRunner", "Clock", "DatabaseValidator", "PipelineFactory", "run_batch"]
