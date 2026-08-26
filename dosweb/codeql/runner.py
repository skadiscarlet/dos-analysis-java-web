from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dosweb.artifacts.identifiers import file_sha256
from dosweb.codeql.database import DatabaseInfo, validate_database
from dosweb.codeql.decoder import DecodeSource, decode_bqrs_json
from dosweb.errors import AnalyzerError

_MAX_DIAGNOSTIC_BYTES: Final = 2048
_MAX_PROCESS_OUTPUT_BYTES: Final = 1024 * 1024
_MAX_QUERY_BYTES: Final = 16 * 1024 * 1024
_MAX_BQRS_BYTES: Final = 256 * 1024 * 1024
_MAX_DECODED_BYTES: Final = 64 * 1024 * 1024
_ALLOWED_ENVIRONMENT: Final = frozenset(
    {"PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "JAVA_HOME", "CODEQL_HOME"}
)
_SAFE_QUERY_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_QUERY_FAMILY_PATTERNS: Final = (
    (re.compile(r"entrytogrowth|flow", re.IGNORECASE), "flow"),
    (re.compile(r"entryinterpositions?", re.IGNORECASE), "entry_interposition"),
    (re.compile(r"entrysecurity", re.IGNORECASE), "entry_security"),
    (re.compile(r"entries?$", re.IGNORECASE), "entries"),
    (re.compile(r"growth|materialization|allocation", re.IGNORECASE), "growth"),
    (re.compile(r"lifecyclesummary", re.IGNORECASE), "lifecycle_summary"),
    (re.compile(r"lifecyclecoverage", re.IGNORECASE), "lifecycle_coverage"),
    (re.compile(r"guard", re.IGNORECASE), "guard"),
    (re.compile(r"bound", re.IGNORECASE), "bound"),
    (re.compile(r"release", re.IGNORECASE), "release"),
)


@dataclass(frozen=True)
class QueryResult:
    query_name: str
    query_path: Path
    bqrs_path: Path
    decoded_path: Path
    query_sha256: str
    bqrs_sha256: str


def _query_family(stem: str) -> str:
    for pattern, family in _QUERY_FAMILY_PATTERNS:
        if pattern.search(stem):
            return family
    raise AnalyzerError(
        "CODEQL_QUERY_FAILED",
        "CodeQL query execution failed.",
        {"stage": "validation", "diagnostic": "query family is unknown"},
    )


def _safe_diagnostic(value: object, secrets: tuple[str, ...]) -> str:
    if isinstance(value, bytes):
        text = value[-_MAX_DIAGNOSTIC_BYTES:].decode("utf-8", errors="replace")
    elif isinstance(value, str):
        text = value[-_MAX_DIAGNOSTIC_BYTES:]
    else:
        text = ""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[-_MAX_DIAGNOSTIC_BYTES:]


def _decode_contract_diagnostic(reason: object, details: Mapping[str, object]) -> str:
    """Serialize only safe decoder contract fields; never paths or source content."""
    fields: dict[str, object] = {}
    if isinstance(reason, str) and reason:
        fields["reason"] = reason[:128]
    for key in ("query_name", "column"):
        value = details.get(key)
        if isinstance(value, str) and value:
            fields[key] = value[:256]
    row = details.get("row")
    if isinstance(row, int) and not isinstance(row, bool):
        fields["row"] = row
    if not fields:
        fields["reason"] = "decoded result violates its query contract"
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))


def _query_failed(
    stage: str,
    *,
    returncode: int | None = None,
    diagnostic: object = "",
    secrets: tuple[str, ...] = (),
) -> AnalyzerError:
    details: dict[str, object] = {"stage": stage, "diagnostic": _safe_diagnostic(diagnostic, secrets)}
    if returncode is not None:
        details["returncode"] = returncode
    return AnalyzerError("CODEQL_QUERY_FAILED", "CodeQL query execution failed.", details)


def _minimal_environment(environment: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in environment.items() if key in _ALLOWED_ENVIRONMENT and isinstance(value, str)}


def _require_regular_output(path: Path, limit: int, stage: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise _query_failed(stage, diagnostic="expected output was not created") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise _query_failed(stage, diagnostic="expected output is not a bounded regular file")
    os.chmod(path, 0o600)


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("not a regular file")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        pass


def _bounded_process(
    argv: list[str], environment: Mapping[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        argv,
        env=dict(environment),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    streams = (process.stdout, process.stderr)
    output = [bytearray(), bytearray()]
    total = 0
    lock = threading.Lock()
    overflow = threading.Event()

    def read_stream(index: int) -> None:
        nonlocal total
        stream = streams[index]
        assert stream is not None
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                with lock:
                    total += len(chunk)
                    if total > _MAX_PROCESS_OUTPUT_BYTES:
                        overflow.set()
                    output[index].extend(chunk)
                    if len(output[index]) > _MAX_DIAGNOSTIC_BYTES:
                        del output[index][:-_MAX_DIAGNOSTIC_BYTES]
                if overflow.is_set():
                    break
        except (OSError, ValueError):
            return

    readers = [threading.Thread(target=read_stream, args=(index,), daemon=True) for index in range(2)]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    failure: BaseException | None = None
    try:
        while True:
            if overflow.is_set():
                failure = OSError("process output exceeded limit")
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = subprocess.TimeoutExpired(argv, timeout)
                break
            if process.poll() is None:
                try:
                    process.wait(timeout=min(remaining, 0.05))
                except subprocess.TimeoutExpired:
                    continue
            else:
                for reader in readers:
                    reader.join(timeout=min(remaining, 0.05))
                if not any(reader.is_alive() for reader in readers):
                    break
        if failure is not None:
            _terminate_group(process)
    finally:
        for reader in readers:
            reader.join(timeout=0.5)
        for stream in streams:
            if stream is not None:
                stream.close()
        for reader in readers:
            reader.join(timeout=0.1)
    if failure is not None:
        raise failure
    if overflow.is_set():
        raise OSError("process output exceeded limit")
    return subprocess.CompletedProcess(
        argv,
        process.returncode,
        output[0].decode("utf-8", errors="replace"),
        output[1].decode("utf-8", errors="replace"),
    )


def _invoke(
    argv: list[str],
    *,
    stage: str,
    timeout_seconds: float,
    environment: Mapping[str, str],
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]],
    secrets: tuple[str, ...],
) -> None:
    if timeout_seconds <= 0:
        raise _query_failed(stage, diagnostic="command deadline exceeded")
    try:
        if subprocess_run is subprocess.run:
            result = _bounded_process(argv, environment, timeout_seconds)
        else:
            result = subprocess_run(
                argv,
                env=dict(environment),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise _query_failed(stage, diagnostic="command deadline exceeded", secrets=secrets) from exc
    except (OSError, ValueError) as exc:
        raise _query_failed(stage, diagnostic="command could not be completed", secrets=secrets) from exc
    if not isinstance(result, subprocess.CompletedProcess):
        raise _query_failed(stage, diagnostic="subprocess runner returned an invalid result")
    if result.returncode != 0:
        diagnostic = result.stderr if isinstance(result.stderr, str) else result.stdout
        raise _query_failed(stage, returncode=result.returncode, diagnostic=diagnostic, secrets=secrets)


def _require_deadline(deadline: float, monotonic: Callable[[], float], stage: str) -> None:
    if deadline - monotonic() <= 0:
        raise _query_failed(stage, diagnostic="query deadline exceeded")


def _read_decoded_json(
    path: Path,
    query_name: str,
    database: DatabaseInfo,
    query_sha256: str,
    deadline: float,
    monotonic: Callable[[], float],
) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_DECODED_BYTES:
            raise ValueError("decoded output is not bounded")
        raw = bytearray()
        while len(raw) <= _MAX_DECODED_BYTES:
            _require_deadline(deadline, monotonic, "bqrs_decode")
            chunk = os.read(descriptor, min(1024 * 1024, _MAX_DECODED_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > _MAX_DECODED_BYTES:
            raise ValueError("decoded output exceeds limit")
        payload = json.loads(raw.decode("utf-8"))
        decode_bqrs_json(
            query_name,
            payload,
            DecodeSource(source_root=database.source_root, query_sha256=query_sha256),
        )
    except AnalyzerError as exc:
        details = exc.details if isinstance(exc.details, Mapping) else {}
        diagnostic = _decode_contract_diagnostic(details.get("reason"), details)
        raise _query_failed("bqrs_decode", diagnostic=diagnostic) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, MemoryError, RecursionError) as exc:
        raise _query_failed("bqrs_decode", diagnostic="decoded result violates its query contract") from exc
    finally:
        os.close(descriptor)


def _deadline_file_sha256(
    path: Path,
    deadline: float,
    monotonic: Callable[[], float],
    stage: str,
) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        while True:
            _require_deadline(deadline, monotonic, stage)
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)
    finally:
        os.close(descriptor)


def _read_query_source(
    supplied: Path,
    deadline: float,
    monotonic: Callable[[], float],
) -> tuple[Path, bytes, str]:
    descriptor = os.open(
        supplied,
        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_QUERY_BYTES:
            raise ValueError("query is not a bounded regular file")
        resolved = supplied.resolve(strict=True)
        current = resolved.lstat()
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_dev != before.st_dev
            or current.st_ino != before.st_ino
        ):
            raise ValueError("query changed during validation")
        raw = bytearray()
        while len(raw) <= _MAX_QUERY_BYTES:
            _require_deadline(deadline, monotonic, "validation")
            chunk = os.read(
                descriptor,
                min(1024 * 1024, _MAX_QUERY_BYTES + 1 - len(raw)),
            )
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
        if (
            len(raw) > _MAX_QUERY_BYTES
            or len(raw) != before.st_size
            or after.st_size != before.st_size
            or after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
        ):
            raise ValueError("query changed while reading")
        payload = bytes(raw)
        return resolved, payload, hashlib.sha256(payload).hexdigest()
    finally:
        os.close(descriptor)


def _write_query_snapshot(
    payload: bytes,
    destination: Path,
    deadline: float,
    monotonic: Callable[[], float],
) -> None:
    with destination.open("xb") as target:
        os.chmod(destination, 0o600)
        for offset in range(0, len(payload), 1024 * 1024):
            _require_deadline(deadline, monotonic, "query_run")
            target.write(payload[offset : offset + 1024 * 1024])
        target.flush()
        os.fsync(target.fileno())


def _create_execution_snapshot(
    snapshot: Path,
    query_path: Path,
    deadline: float,
    monotonic: Callable[[], float],
) -> Path:
    descriptor, name = tempfile.mkstemp(
        dir=query_path.parent,
        prefix=f".{query_path.stem}.dosweb.",
        suffix=query_path.suffix,
    )
    execution_path = Path(name)
    source = -1
    try:
        os.fchmod(descriptor, 0o400)
        source = os.open(snapshot, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        while True:
            _require_deadline(deadline, monotonic, "query_run")
            chunk = os.read(source, 1024 * 1024)
            if not chunk:
                break
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
        os.fsync(descriptor)
        return execution_path
    except Exception:
        execution_path.unlink(missing_ok=True)
        raise
    finally:
        if source >= 0:
            os.close(source)
        os.close(descriptor)


def run_query(
    query: Path | str,
    database: DatabaseInfo,
    output_dir: Path | str,
    *,
    codeql_binary: str = "codeql",
    timeout_seconds: int = 300,
    environment: Mapping[str, str] | None = None,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    monotonic: Callable[[], float] = time.monotonic,
) -> QueryResult:
    supplied_query = Path(query)
    if not isinstance(database, DatabaseInfo):
        raise _query_failed("validation", diagnostic="database has not been validated")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 3600:
        raise _query_failed("validation", diagnostic="timeout is outside the supported range")
    deadline = monotonic() + timeout_seconds
    try:
        query_path, query_payload, initial_query_sha256 = _read_query_source(
            supplied_query, deadline, monotonic
        )
    except (OSError, ValueError) as exc:
        raise _query_failed("validation", diagnostic="query file is invalid") from exc
    stem = query_path.stem
    if not _SAFE_QUERY_NAME.fullmatch(stem):
        raise _query_failed("validation", diagnostic="query name is unsafe")
    query_name = _query_family(stem)

    output = Path(output_dir)
    try:
        if output.exists() and output.is_symlink():
            raise ValueError("output symlink is not supported")
        output.mkdir(parents=True, exist_ok=True)
        output = output.resolve(strict=True)
        if not output.is_dir():
            raise ValueError("output is not a directory")
        generations = output / ".generations"
        try:
            generations.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = generations.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("generation directory is unsafe")
        os.chmod(generations, 0o700)
    except (OSError, ValueError) as exc:
        raise _query_failed("validation", diagnostic="output directory is invalid") from exc

    try:
        current_database = validate_database(
            database.path, deadline=deadline, monotonic=monotonic
        )
    except TimeoutError as exc:
        raise _query_failed("validation", diagnostic="query deadline exceeded") from exc
    if current_database.fingerprint != database.fingerprint or current_database.source_root != database.source_root:
        raise _query_failed("validation", diagnostic="database changed after validation")

    source_environment = dict(os.environ if environment is None else environment)
    minimal_environment = _minimal_environment(source_environment)
    secrets = tuple(
        value for key, value in source_environment.items()
        if isinstance(value, str) and value and any(marker in key.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH"))
    )
    _require_deadline(deadline, monotonic, "validation")
    pending = Path(tempfile.mkdtemp(dir=generations, prefix=f".{stem}.pending."))
    os.chmod(pending, 0o700)
    snapshot_query = pending / query_path.name
    temporary_bqrs = pending / f"{stem}.bqrs"
    temporary_json = pending / f"{stem}.json"
    query_sha256 = ""
    bqrs_sha256 = ""
    published: Path | None = None
    execution_query: Path | None = None
    committed = False
    try:
        query_sha256 = initial_query_sha256
        _write_query_snapshot(query_payload, snapshot_query, deadline, monotonic)
        execution_query = _create_execution_snapshot(
            snapshot_query, query_path, deadline, monotonic
        )
        if deadline - monotonic() <= 0:
            raise _query_failed("query_run", diagnostic="query deadline exceeded")
        _invoke(
            [codeql_binary, "query", "run", str(execution_query), "--database", str(database.path), "--output", str(temporary_bqrs)],
            stage="query_run",
            timeout_seconds=deadline - monotonic(),
            environment=minimal_environment,
            subprocess_run=subprocess_run,
            secrets=secrets,
        )
        try:
            current_query_sha256 = _deadline_file_sha256(
                query_path, deadline, monotonic, "query_run"
            )
        except AnalyzerError:
            raise
        except OSError as exc:
            raise _query_failed("query_run", diagnostic="query could not be revalidated") from exc
        if current_query_sha256 != query_sha256:
            raise _query_failed("query_run", diagnostic="query changed during execution")
        _require_regular_output(temporary_bqrs, _MAX_BQRS_BYTES, "query_run")
        _invoke(
            [codeql_binary, "bqrs", "decode", str(temporary_bqrs), "--format=json", "--output", str(temporary_json)],
            stage="bqrs_decode",
            timeout_seconds=deadline - monotonic(),
            environment=minimal_environment,
            subprocess_run=subprocess_run,
            secrets=secrets,
        )
        _require_regular_output(temporary_json, _MAX_DECODED_BYTES, "bqrs_decode")
        _read_decoded_json(
            temporary_json, query_name, database, query_sha256, deadline, monotonic
        )
        if deadline - monotonic() <= 0:
            raise _query_failed("validation", diagnostic="query deadline exceeded")
        after_database = validate_database(
            database.path, deadline=deadline, monotonic=monotonic
        )
        if after_database.fingerprint != database.fingerprint or after_database.source_root != database.source_root:
            raise _query_failed("validation", diagnostic="database changed during query execution")
        bqrs_sha256 = _deadline_file_sha256(
            temporary_bqrs, deadline, monotonic, "publication"
        )
        if deadline - monotonic() <= 0:
            raise _query_failed("publication", diagnostic="query deadline exceeded")
        for path in (snapshot_query, temporary_bqrs, temporary_json):
            _require_deadline(deadline, monotonic, "publication")
            _fsync_file(path)
        _require_deadline(deadline, monotonic, "publication")
        _fsync_directory(pending)
        generation_name = f"{stem}-{uuid.uuid4().hex}"
        published = generations / generation_name
        _require_deadline(deadline, monotonic, "publication")
        os.replace(pending, published)
        try:
            _fsync_directory(generations)
        except Exception:
            shutil.rmtree(published, ignore_errors=True)
            published = None
            raise
        committed = True
    except AnalyzerError:
        raise
    except Exception as exc:
        raise _query_failed("publication", diagnostic="query outputs could not be published") from exc
    finally:
        if execution_query is not None:
            execution_query.unlink(missing_ok=True)
        if not committed:
            shutil.rmtree(pending, ignore_errors=True)

    assert published is not None
    final_query = published / snapshot_query.name
    final_bqrs = published / temporary_bqrs.name
    final_json = published / temporary_json.name
    return QueryResult(
        query_name=query_name,
        query_path=final_query,
        bqrs_path=final_bqrs,
        decoded_path=final_json,
        query_sha256=query_sha256,
        bqrs_sha256=bqrs_sha256,
    )
