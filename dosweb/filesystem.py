"""Small Linux filesystem primitives used by fail-closed publication paths."""
from __future__ import annotations

import ctypes
from collections.abc import Callable
from dataclasses import dataclass
import errno
from enum import Enum
import os
import platform
import signal
import sys
import tempfile
from typing import TypeVar

_RENAME_NOREPLACE = 1
_RENAME_EXCHANGE = 2
_CLOSE_RANGE_SYSCALLS = {
    "aarch64": 436,
    "amd64": 436,
    "x86_64": 436,
}
_MAX_FD = (1 << 32) - 1
_T = TypeVar("_T")


def run_with_deferred_interrupts(action: Callable[[], _T]) -> _T:
    """Run one ownership action with post-action-safe state restoration.

    Every mutating setup call is already inside the matching restoration
    ``finally`` before it executes. The signal mask is queried separately
    before blocking, so an exception after ``SIG_BLOCK`` still restores the
    exact prior mask.
    """

    previous_profile = sys.getprofile()
    previous_trace = sys.gettrace()
    previous_mask: set[signal.Signals] | None = None
    if hasattr(signal, "pthread_sigmask"):
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    try:
        sys.setprofile(None)
        try:
            sys.settrace(None)
            if previous_mask is None:
                return action()
            try:
                signal.pthread_sigmask(
                    signal.SIG_BLOCK,
                    {signal.SIGINT},
                )
                return action()
            finally:
                signal.pthread_sigmask(
                    signal.SIG_SETMASK,
                    previous_mask,
                )
        finally:
            sys.settrace(previous_trace)
    finally:
        sys.setprofile(previous_profile)


def open_owned_descriptor(
    owner: list[int],
    path: str | os.PathLike[str],
    flags: int,
    mode: int = 0o777,
    *,
    dir_fd: int | None = None,
) -> int:
    """Open one fd only after reserving its structural owner slot.

    The slot exists before ``os.open`` and is populated while instrumentation
    and ``SIGINT`` are deferred.  A restoration exception therefore cannot
    occur between the C return and structural ownership. ``mode`` is forwarded
    for the owned ``O_CREAT`` cases rather than reopening a created path.
    """

    owner.append(-1)
    slot = len(owner) - 1

    def acquire() -> int:
        try:
            descriptor = os.open(path, flags, mode, dir_fd=dir_fd)
        except BaseException:
            owner.pop()
            raise
        owner[slot] = descriptor
        return descriptor

    return run_with_deferred_interrupts(acquire)


def duplicate_owned_descriptor(
    owner: list[int],
    source_descriptor: int,
) -> int:
    """Duplicate one fd into a pre-reserved owner slot."""

    owner.append(-1)
    slot = len(owner) - 1

    def acquire() -> int:
        try:
            descriptor = os.dup(source_descriptor)
        except BaseException:
            owner.pop()
            raise
        owner[slot] = descriptor
        return descriptor

    return run_with_deferred_interrupts(acquire)


def create_owned_tempfile(
    owner: list[OwnedTemporaryFile],
    *,
    directory: str | os.PathLike[str],
    prefix: str,
    suffix: str,
) -> OwnedTemporaryFile:
    """Create one tempfile with fd and path owned before factory return."""

    owner.append(OwnedTemporaryFile(-1, ""))
    slot = len(owner) - 1

    def acquire() -> OwnedTemporaryFile:
        descriptor = -1
        path = ""
        try:
            descriptor, path = tempfile.mkstemp(
                dir=directory,
                prefix=prefix,
                suffix=suffix,
            )
            owned = OwnedTemporaryFile(descriptor, path)
            owner[slot] = owned
            return owned
        except BaseException:
            owner.pop()
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException:
                    pass
            if path:
                try:
                    os.unlink(path)
                except BaseException:
                    pass
            raise

    return run_with_deferred_interrupts(acquire)


def _close_range_syscall_number() -> int:
    if sys.platform != "linux" or platform.system() != "Linux":
        raise OSError(errno.ENOSYS, "close_range requires Linux")
    syscall_number = _CLOSE_RANGE_SYSCALLS.get(platform.machine().lower())
    if syscall_number is None:
        raise OSError(errno.ENOSYS, "close_range unavailable")
    return syscall_number


@dataclass(frozen=True)
class CloseRangeCapability:
    """A probed Linux close_range(flags=0) syscall binding."""

    syscall_number: int


class CloseRangePreActionError(OSError):
    """A raw close_range error that Linux reports before fd-table action."""


class CloseFdOnceStatus(str, Enum):
    RELEASED = "released"
    PRE_ACTION_FAILURE = "pre_action_failure"
    POST_ACTION_EXCEPTION = "post_action_exception"


@dataclass(frozen=True)
class CloseFdOnceOutcome:
    """Observable outcome of the final, single-shot descriptor release."""

    status: CloseFdOnceStatus
    error: BaseException | None = None


@dataclass
class DeferredCloseFdOnceOutcome:
    """Preallocated state for one deferred owned-descriptor release."""

    status: CloseFdOnceStatus | None = None
    primary_error: BaseException | None = None
    transaction_error: BaseException | None = None
    callback_error: BaseException | None = None
    fallback_error: BaseException | None = None
    fallback_attempted: bool = False

    @property
    def explicitly_consumed(self) -> bool:
        return (
            self.status == CloseFdOnceStatus.RELEASED
            or self.status == CloseFdOnceStatus.POST_ACTION_EXCEPTION
        )

    @property
    def succeeded(self) -> bool:
        return (
            self.status == CloseFdOnceStatus.RELEASED
            and self.primary_error is None
            and self.transaction_error is None
            and self.callback_error is None
            and self.fallback_error is None
        )

    @property
    def failures(self) -> tuple[BaseException, ...]:
        return tuple(
            failure
            for failure in (
                self.primary_error,
                self.transaction_error,
                self.callback_error,
                self.fallback_error,
            )
            if failure is not None
        )


@dataclass(frozen=True)
class OwnedTemporaryFile:
    """One newly created tempfile structurally owned with its exact path."""

    descriptor: int
    path: str


def _close_range(
    capability: CloseRangeCapability,
    first_fd: int,
    last_fd: int,
) -> None:
    """Invoke one Linux close_range syscall with its fail-before-action flags."""

    libc = ctypes.CDLL(None, use_errno=True)
    ctypes.set_errno(0)
    result = libc.syscall(
        capability.syscall_number,
        ctypes.c_uint(first_fd),
        ctypes.c_uint(last_fd),
        ctypes.c_uint(0),
    )
    if result < 0:
        error_number = ctypes.get_errno()
        raise CloseRangePreActionError(
            error_number,
            os.strerror(error_number),
        )


def require_close_fd_once() -> CloseRangeCapability:
    """Probe and bind the Linux primitive before allocating an owned fd."""

    syscall_number = _close_range_syscall_number()
    capability = CloseRangeCapability(syscall_number=syscall_number)
    _close_range(capability, _MAX_FD, _MAX_FD)
    return capability


def close_fd_once(
    descriptor: int,
    capability: CloseRangeCapability | None = None,
) -> None:
    """Release exactly one fd with one close_range(fd, fd, 0) syscall.

    Linux validates the flags and range before walking the descriptor table;
    flags=0 has no per-descriptor writeback error.  A reported syscall failure
    therefore leaves the requested descriptor untouched and must not be
    retried by fd number.
    """

    if (
        isinstance(descriptor, bool)
        or not isinstance(descriptor, int)
        or descriptor < 0
        or descriptor > _MAX_FD
    ):
        raise OSError(errno.EINVAL, "invalid file descriptor")
    if capability is None:
        syscall_number = _close_range_syscall_number()
        capability = CloseRangeCapability(
            syscall_number=syscall_number,
        )
    if not isinstance(capability, CloseRangeCapability):
        raise TypeError("invalid close_range capability")
    _close_range(
        capability,
        descriptor,
        descriptor,
    )


def close_fd_once_outcome(
    descriptor: int,
    capability: CloseRangeCapability,
) -> CloseFdOnceOutcome:
    """Classify a final release without retrying its fd number.

    A raw negative syscall result is a proven pre-action failure.  Any other
    exception observed around the call is treated as post-action/ambiguous:
    the fd number must never be touched again.
    """

    try:
        close_fd_once(descriptor, capability)
    except CloseRangePreActionError as exc:
        return CloseFdOnceOutcome(
            status=CloseFdOnceStatus.PRE_ACTION_FAILURE,
            error=exc,
        )
    except BaseException as exc:
        return CloseFdOnceOutcome(
            status=CloseFdOnceStatus.POST_ACTION_EXCEPTION,
            error=exc,
        )
    return CloseFdOnceOutcome(status=CloseFdOnceStatus.RELEASED)


def release_owned_descriptor_once(
    descriptor: int,
    capability: CloseRangeCapability,
    *,
    transaction: DeferredCloseFdOnceOutcome,
    close_fn: Callable[[int, CloseRangeCapability], None] | None = None,
    before_fallback: Callable[[], None] | None = None,
) -> DeferredCloseFdOnceOutcome:
    """Release one structurally owned fd without an outcome call/commit gap.

    The caller-side release wrapper allocates ``transaction`` before the raw
    action while its outer batch still owns the local descriptor value.  The
    raw close and its allocation-free status commit execute with trace/profile
    callbacks and ``SIGINT`` deferred.  Only RELEASED or POST_ACTION consumes
    the close-range action.  A setup escape before the action or a proved
    PRE_ACTION result retains ownership long enough to run ``before_fallback``
    and exactly one ``closerange`` fallback.  Callers releasing an owned set
    must handle transaction-allocation failure with the still-owned local
    fallback, then put their complete owner-retirement/result-commit loop in one outer
    :func:`run_with_deferred_interrupts` transaction so this helper's return
    event cannot split the set.  No primary/callback/fallback failure escapes.
    """

    if close_fn is None:
        close_fn = close_fd_once

    def release_action() -> None:
        try:
            close_fn(descriptor, capability)
        except CloseRangePreActionError as exc:
            transaction.status = CloseFdOnceStatus.PRE_ACTION_FAILURE
            transaction.primary_error = exc
        except BaseException as exc:
            transaction.status = CloseFdOnceStatus.POST_ACTION_EXCEPTION
            transaction.primary_error = exc
        else:
            transaction.status = CloseFdOnceStatus.RELEASED

        transaction.fallback_attempted = (
            transaction.status is None
            or transaction.status == CloseFdOnceStatus.PRE_ACTION_FAILURE
        )
        if not transaction.fallback_attempted:
            return
        if before_fallback is not None:
            try:
                before_fallback()
            except BaseException as exc:
                transaction.callback_error = exc
        try:
            os.closerange(descriptor, descriptor + 1)
        except BaseException as exc:
            transaction.fallback_error = exc

    try:
        run_with_deferred_interrupts(release_action)
    except BaseException as exc:
        transaction.transaction_error = exc

    if (
        transaction.status is None
        or transaction.status == CloseFdOnceStatus.PRE_ACTION_FAILURE
    ) and not transaction.fallback_attempted:
        transaction.fallback_attempted = True
        if before_fallback is not None:
            try:
                before_fallback()
            except BaseException as exc:
                transaction.callback_error = exc

        def fallback_after_setup_failure() -> None:
            os.closerange(descriptor, descriptor + 1)

        try:
            run_with_deferred_interrupts(fallback_after_setup_failure)
        except BaseException as exc:
            transaction.fallback_error = exc

    return transaction


def renameat2_no_replace(
    source_directory_fd: int,
    source_name: str,
    destination_directory_fd: int,
    destination_name: str,
) -> None:
    """Atomically rename one dirfd-relative leaf without replacing a target."""

    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise OSError(
            errno.ENOSYS, "renameat2(RENAME_NOREPLACE) unavailable"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        source_directory_fd,
        os.fsencode(source_name),
        destination_directory_fd,
        os.fsencode(destination_name),
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            destination_name,
        )


def renameat2_exchange(
    source_directory_fd: int,
    source_name: str,
    destination_directory_fd: int,
    destination_name: str,
) -> None:
    """Atomically exchange two existing dirfd-relative leaves."""

    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise OSError(
            errno.ENOSYS, "renameat2(RENAME_EXCHANGE) unavailable"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        source_directory_fd,
        os.fsencode(source_name),
        destination_directory_fd,
        os.fsencode(destination_name),
        _RENAME_EXCHANGE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            destination_name,
        )


__all__ = [
    "CloseRangeCapability",
    "CloseRangePreActionError",
    "CloseFdOnceOutcome",
    "CloseFdOnceStatus",
    "DeferredCloseFdOnceOutcome",
    "close_fd_once",
    "close_fd_once_outcome",
    "release_owned_descriptor_once",
    "renameat2_exchange",
    "renameat2_no_replace",
    "require_close_fd_once",
    "run_with_deferred_interrupts",
]
