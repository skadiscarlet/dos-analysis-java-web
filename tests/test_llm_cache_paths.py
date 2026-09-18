from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import threading
from unittest import mock

import pytest

from dosweb.errors import AnalyzerError
from dosweb.filesystem import CloseRangePreActionError
from dosweb.growth.contracts import validate_growth_contract
from dosweb.llm import cache as cache_module
from dosweb.llm.cache import ContractCache


def _forge_fstat_for_directory(
    directory: Path,
    *,
    uid: int,
    mode: int | None = None,
) -> mock._patch:
    """Forge one opened directory's metadata without weakening other fstat checks."""
    original_fstat = os.fstat
    expected = directory.stat()

    def forged(descriptor: int) -> os.stat_result:
        result = original_fstat(descriptor)
        if (result.st_dev, result.st_ino) != (expected.st_dev, expected.st_ino):
            return result
        values = list(result)
        values[4] = uid
        if mode is not None:
            values[0] = stat.S_IFMT(result.st_mode) | mode
        return os.stat_result(values)

    return mock.patch("dosweb.llm.cache.os.fstat", side_effect=forged)


def _growth_cache_fixture(
    cache: ContractCache,
) -> tuple[dict[str, object], object, dict[str, object]]:
    identity: dict[str, object] = {
        "request_method": "POST",
        "request_url": "https://example.test/responses",
        "provider": "api2cn_responses",
        "protocol": "responses-v1",
        "model": "grok-4.6",
        "slice_content_hash": "a" * 64,
        "allow_remote_llm": True,
        "public_source_url": "",
        "source_commit_sha": "",
        "verified_public": False,
        "verified_clean_checkout": False,
    }
    contract = validate_growth_contract(
        {
            "is_resource_growth": "yes",
            "growth_kind": "container_growth",
            "resource_dimension": "entries",
            "attacker_influence": [
                {"target": "key", "evidence_id": "fact:key"}
            ],
            "resource_effect": "adds_entries",
            "attacker_variable": "request key",
            "attacker_value_space": "unlimited",
            "growth_unit": "one retained map entry",
            "growth_function": "distinct keys add retained entries",
            "amplification_class": "high_cardinality_retention",
            "requests_to_pressure": "many",
            "concurrency_model": "repeatable requests",
            "retention_window": "process",
            "failure_mechanism": "heap_exhaustion",
            "failure_signal": "retained entries exhaust heap",
            "required_static_evidence": ["fact:key", "fact:put"],
            "contract_status": "dos_relevant",
            "rejection_reason": "none",
            "confidence": "high",
        }
    )
    audit: dict[str, object] = {
        "method": identity["request_method"],
        "url": identity["request_url"],
        "provider": identity["provider"],
        "protocol": identity["protocol"],
        "requested_model": identity["model"],
        "actual_model": identity["model"],
        "provider_request_id_digest": cache.provider_request_id_digest("fixture"),
        "slice_content_hash": identity["slice_content_hash"],
        "allow_remote_llm": identity["allow_remote_llm"],
        "public_source_url": identity["public_source_url"],
        "source_commit_sha": identity["source_commit_sha"],
        "verified_public": identity["verified_public"],
        "verified_clean_checkout": identity["verified_clean_checkout"],
    }
    return identity, contract, audit


def test_private_cache_under_sticky_sandbox_tmp_keeps_owner_only_target() -> None:
    """A sticky shared ancestor must not make a private output cache unusable."""
    with tempfile.TemporaryDirectory() as temporary:
        nested = Path(temporary) / "production-output" / "cache" / "llm"
        nested.parent.parent.mkdir(mode=0o755)
        ancestor = Path(tempfile.gettempdir())
        assert ancestor.stat().st_mode & stat.S_ISVTX

        cache = ContractCache(nested, "test-api-key")
        contract = {
            "auth_context": "unknown",
            "evidence_ids": [],
            "assumptions": [],
            "confidence": "low",
        }
        assert cache.put_auth_record("e" * 64, {"kind": "auth"}, contract, "{}")
        assert nested.stat().st_uid == os.getuid()
        assert stat.S_IMODE(nested.stat().st_mode) == 0o700


def test_single_flight_traverses_foreign_readonly_ancestor_after_private_anchor() -> None:
    """A foreign read-only prefix is traversal-only, not authority to create."""
    with tempfile.TemporaryDirectory() as temporary:
        foreign = Path(temporary) / "foreign-readonly"
        foreign.mkdir(mode=0o755)
        direct_target = foreign / "direct-cache"

        with _forge_fstat_for_directory(foreign, uid=os.getuid() + 1):
            with pytest.raises(AnalyzerError) as raised:
                with ContractCache(direct_target, "test-api-key").single_flight("0" * 64):
                    pass

        assert raised.value.code == "LLM_CACHE_UNSAFE"
        assert not direct_target.exists()

        anchor = foreign / "safe-owned-anchor"
        anchor.mkdir(mode=0o755)
        assert stat.S_IMODE(anchor.stat().st_mode) == 0o755
        target = anchor / "cache" / "llm"

        with _forge_fstat_for_directory(foreign, uid=os.getuid() + 1):
            with ContractCache(target, "test-api-key").single_flight("a" * 64):
                pass

        assert target.stat().st_uid == os.getuid()
        assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_single_flight_rejects_foreign_writable_nonsticky_ancestor() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        foreign = Path(temporary) / "foreign-writable"
        foreign.mkdir(mode=0o755)
        anchor = foreign / "private-anchor"
        anchor.mkdir(mode=0o700)
        target = anchor / "cache"

        with _forge_fstat_for_directory(foreign, uid=os.getuid() + 1, mode=0o777):
            with pytest.raises(AnalyzerError, match="LLM cache locking is unavailable") as raised:
                with ContractCache(target, "test-api-key").single_flight("b" * 64):
                    pass

        assert raised.value.code == "LLM_CACHE_UNSAFE"
        assert not target.exists()


def test_single_flight_rejects_foreign_symlink_ancestor() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        real = base / "real"
        real.mkdir(mode=0o700)
        link = base / "foreign-link"
        link.symlink_to(real, target_is_directory=True)

        with pytest.raises(AnalyzerError) as raised:
            with ContractCache(link / "cache", "test-api-key").single_flight("c" * 64):
                pass

        assert raised.value.code == "LLM_CACHE_UNSAFE"
        assert not (real / "cache").exists()


def test_single_flight_rejects_unsafe_existing_target() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "cache"
        target.mkdir(mode=0o755)

        with pytest.raises(AnalyzerError) as raised:
            with ContractCache(target, "test-api-key").single_flight("d" * 64):
                pass

        assert raised.value.code == "LLM_CACHE_UNSAFE"


def test_foreign_sticky_ancestor_requires_existing_private_anchor() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        shared = Path(temporary) / "foreign-sticky"
        shared.mkdir(mode=0o700)
        direct_target = shared / "direct-cache"

        with _forge_fstat_for_directory(
            shared,
            uid=os.getuid() + 1,
            mode=stat.S_ISVTX | 0o777,
        ):
            with pytest.raises(AnalyzerError) as raised:
                with ContractCache(direct_target, "test-api-key").single_flight("e" * 64):
                    pass

        assert raised.value.code == "LLM_CACHE_UNSAFE"
        assert not direct_target.exists()

        anchor = shared / "private-anchor"
        anchor.mkdir(mode=0o700)
        anchored_target = anchor / "cache"
        with _forge_fstat_for_directory(
            shared,
            uid=os.getuid() + 1,
            mode=stat.S_ISVTX | 0o777,
        ):
            with ContractCache(anchored_target, "test-api-key").single_flight("f" * 64):
                pass

        assert stat.S_IMODE(anchored_target.stat().st_mode) == 0o700


def test_create_keeps_pinned_target_when_foreign_ancestor_swaps_anchor() -> None:
    """Creation must consume the verified fd, never reopen the absolute path."""
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        foreign = base / "foreign-readonly"
        foreign.mkdir(mode=0o755)
        anchor = foreign / "owned-anchor"
        anchor.mkdir(mode=0o755)
        target = anchor / "cache"
        detached_anchor = foreign / "detached-anchor"
        redirect_anchor = base / "redirect-anchor"
        redirect_target = redirect_anchor / "cache"
        redirect_target.mkdir(parents=True, mode=0o700)
        baseline_fds = len(os.listdir("/proc/self/fd"))
        real_create = cache_module._create_private_hierarchy
        swapped = False

        def create_then_swap(path: Path, *, create: bool = True) -> object:
            nonlocal swapped
            result = real_create(path, create=create)
            assert result is not None
            anchor.rename(detached_anchor)
            anchor.symlink_to(redirect_anchor, target_is_directory=True)
            swapped = True
            return result

        with (
            _forge_fstat_for_directory(foreign, uid=os.getuid() + 1),
            mock.patch.object(
                cache_module,
                "_create_private_hierarchy",
                side_effect=create_then_swap,
            ),
        ):
            with ContractCache(target, "test-api-key").single_flight("1" * 64):
                pass

        assert swapped
        assert list(redirect_target.glob(".stripe-*.lock")) == []
        assert len(list((detached_anchor / "cache").glob(".stripe-*.lock"))) == 1
        assert len(os.listdir("/proc/self/fd")) == baseline_fds


def test_read_keeps_pinned_target_when_foreign_ancestor_swaps_anchor() -> None:
    """Read-only cache checks must stay on the descriptor-relative target."""
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        foreign = base / "foreign-readonly"
        foreign.mkdir(mode=0o755)
        anchor = foreign / "owned-anchor"
        anchor.mkdir(mode=0o755)
        target = anchor / "cache"
        target.mkdir(mode=0o700)
        detached_anchor = foreign / "detached-anchor"
        redirect_anchor = base / "redirect-anchor"
        redirect_target = redirect_anchor / "cache"
        redirect_target.mkdir(parents=True, mode=0o700)
        key = "2" * 64
        stripe_name = f".stripe-{int(key[:8], 16) % 64:02d}.lock"
        outside_lock = base / "outside-lock"
        outside_lock.write_bytes(b"")
        (target / stripe_name).symlink_to(outside_lock)
        original_target_identity = (target.stat().st_dev, target.stat().st_ino)
        redirect_target_identity = (
            redirect_target.stat().st_dev,
            redirect_target.stat().st_ino,
        )
        anchor_identity = (anchor.stat().st_dev, anchor.stat().st_ino)
        baseline_fds = len(os.listdir("/proc/self/fd"))
        original_open = os.open
        original_fstat = os.fstat
        original_lstat = os.lstat
        observed_entry_directories: list[tuple[int, int]] = []
        swapped = False

        def swap_before_target_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal swapped
            absolute_target_open = dir_fd is None and Path(path) == target
            relative_target_open = False
            if dir_fd is not None and path == target.name:
                info = original_fstat(dir_fd)
                relative_target_open = (info.st_dev, info.st_ino) == anchor_identity
            if not swapped and (absolute_target_open or relative_target_open):
                anchor.rename(detached_anchor)
                anchor.symlink_to(redirect_anchor, target_is_directory=True)
                swapped = True
            return original_open(path, flags, mode, dir_fd=dir_fd)

        def record_entry_directory(
            path: object,
            *,
            dir_fd: int | None = None,
        ) -> os.stat_result:
            if dir_fd is not None and path in {stripe_name, ".capacity.lock"}:
                info = original_fstat(dir_fd)
                observed_entry_directories.append((info.st_dev, info.st_ino))
            return original_lstat(path, dir_fd=dir_fd)

        with (
            _forge_fstat_for_directory(foreign, uid=os.getuid() + 1),
            mock.patch.object(cache_module.os, "open", side_effect=swap_before_target_open),
            mock.patch.object(cache_module.os, "lstat", side_effect=record_entry_directory),
        ):
            assert not ContractCache(target, "test-api-key").is_usable(key)

        assert swapped
        assert original_target_identity in observed_entry_directories
        assert redirect_target_identity not in observed_entry_directories
        assert len(os.listdir("/proc/self/fd")) == baseline_fds


def test_hierarchy_open_exception_releases_parent_and_child_descriptors() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "cache"
        target.mkdir(mode=0o700)
        target_identity = (target.stat().st_dev, target.stat().st_ino)
        baseline_fds = len(os.listdir("/proc/self/fd"))
        original_fstat = os.fstat

        def fail_target_validation(descriptor: int) -> os.stat_result:
            info = original_fstat(descriptor)
            if (info.st_dev, info.st_ino) == target_identity:
                raise OSError("injected target validation failure")
            return info

        with mock.patch.object(
            cache_module.os,
            "fstat",
            side_effect=fail_target_validation,
        ):
            assert cache_module._create_private_hierarchy(target, create=False) is None

        assert len(os.listdir("/proc/self/fd")) == baseline_fds


@pytest.mark.parametrize("release_site", ["previous", "child", "outer_finally"])
def test_hierarchy_unregistered_descriptor_pre_close_fault_is_retired_once(
    tmp_path: Path,
    release_site: str,
) -> None:
    target = tmp_path / release_site / "cache"
    target.mkdir(parents=True, mode=0o700)
    if release_site == "child":
        target.chmod(0o755)
    baseline_fds = len(os.listdir("/proc/self/fd"))
    real_open = os.open
    real_close = os.close
    real_closerange = os.closerange
    target_identity = (target.stat().st_dev, target.stat().st_ino)
    open_calls = 0
    injected_descriptors: list[int] = []
    fallback_ranges: list[tuple[int, int]] = []
    returned_descriptor: int | None = None

    def fault_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal open_calls
        open_calls += 1
        if release_site == "outer_finally" and open_calls == 2:
            raise OSError(5, "injected hierarchy open failure")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def fault_close(descriptor: int) -> None:
        should_inject = False
        if not injected_descriptors:
            if release_site == "previous":
                should_inject = True
            elif release_site == "child":
                info = os.fstat(descriptor)
                should_inject = (info.st_dev, info.st_ino) == target_identity
            else:
                should_inject = True
        if should_inject:
            injected_descriptors.append(descriptor)
            raise CloseRangePreActionError(5, "injected pre-action close")
        real_close(descriptor)

    def record_closerange(first: int, last: int) -> None:
        fallback_ranges.append((first, last))
        real_closerange(first, last)

    try:
        with (
            mock.patch.object(cache_module.os, "open", side_effect=fault_open),
            mock.patch.object(cache_module.os, "close", side_effect=fault_close),
            mock.patch.object(
                cache_module.os,
                "closerange",
                side_effect=record_closerange,
            ),
        ):
            try:
                returned_descriptor = cache_module._create_private_hierarchy(
                    target,
                    create=False,
                )
            except CloseRangePreActionError:
                returned_descriptor = None

        returned_target = returned_descriptor is not None
        if returned_descriptor is not None:
            cache_module._close_unregistered_descriptor(returned_descriptor)
            returned_descriptor = None

        if release_site == "child":
            target.chmod(0o700)
        followup = cache_module._create_private_hierarchy(target, create=False)
        assert followup is not None
        cache_module._close_unregistered_descriptor(followup)

        assert len(os.listdir("/proc/self/fd")) - baseline_fds == 0
        assert returned_target is (release_site == "previous")
        assert len(injected_descriptors) == 1
        assert fallback_ranges == [
            (injected_descriptors[0], injected_descriptors[0] + 1)
        ]
        assert not cache_module._ACTIVE_TRANSIENT_FDS
        assert not cache_module._ACTIVE_FLOCK_FDS
        assert not cache_module._ACTIVE_CACHE_DIRECTORIES
        assert not getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {})
    finally:
        if returned_descriptor is not None:
            try:
                real_close(returned_descriptor)
            except OSError:
                pass
        for descriptor in injected_descriptors:
            try:
                real_close(descriptor)
            except OSError:
                pass


@pytest.mark.parametrize("close_phase", ["pre", "post"])
def test_unsafe_regular_file_unregistered_close_fault_is_retired_once(
    tmp_path: Path,
    close_phase: str,
) -> None:
    directory = tmp_path / "regular-file"
    directory.mkdir(mode=0o700)
    directory_descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    name = "unsafe"
    (directory / name).write_bytes(b"payload")
    (directory / name).chmod(0o600)
    baseline_fds = len(os.listdir("/proc/self/fd"))
    real_fstat = os.fstat
    real_close = os.close
    real_closerange = os.closerange
    opened_descriptor: int | None = None
    injected_descriptors: list[int] = []
    fallback_ranges: list[tuple[int, int]] = []
    replacements: list[int] = []

    def unsafe_metadata(descriptor: int) -> os.stat_result:
        nonlocal opened_descriptor
        info = real_fstat(descriptor)
        if descriptor != directory_descriptor:
            opened_descriptor = descriptor
            values = list(info)
            values[0] = stat.S_IFMT(info.st_mode) | 0o644
            return os.stat_result(values)
        return info

    def fault_close(descriptor: int) -> None:
        if descriptor == opened_descriptor and not injected_descriptors:
            injected_descriptors.append(descriptor)
            if close_phase == "pre":
                raise CloseRangePreActionError(5, "injected pre-action close")
            real_close(descriptor)
            replacement = os.open(
                tmp_path / "post-close-replacement",
                os.O_RDWR | os.O_CREAT,
                0o600,
            )
            assert replacement == descriptor
            replacements.append(replacement)
            raise KeyboardInterrupt("injected post-action close")
        real_close(descriptor)

    def record_closerange(first: int, last: int) -> None:
        fallback_ranges.append((first, last))
        real_closerange(first, last)

    try:
        with (
            mock.patch.object(cache_module.os, "fstat", side_effect=unsafe_metadata),
            mock.patch.object(cache_module.os, "close", side_effect=fault_close),
            mock.patch.object(
                cache_module.os,
                "closerange",
                side_effect=record_closerange,
            ),
        ):
            assert (
                cache_module._open_private_regular_file(
                    directory_descriptor,
                    name,
                    create=False,
                )
                is None
            )

        followup = cache_module._open_private_regular_file(
            directory_descriptor,
            name,
            create=False,
        )
        assert followup is not None
        cache_module._close_unregistered_descriptor(followup)

        assert len(injected_descriptors) == 1
        if close_phase == "pre":
            assert not replacements
            assert fallback_ranges == [
                (injected_descriptors[0], injected_descriptors[0] + 1)
            ]
        else:
            assert len(replacements) == 1
            os.fstat(replacements[0])
            assert not fallback_ranges
        assert not cache_module._ACTIVE_TRANSIENT_FDS
        assert not cache_module._ACTIVE_FLOCK_FDS
        assert not cache_module._ACTIVE_CACHE_DIRECTORIES
        assert not getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {})
        for replacement in replacements:
            real_close(replacement)
        replacements.clear()
        assert len(os.listdir("/proc/self/fd")) - baseline_fds == 0
    finally:
        for replacement in replacements:
            try:
                real_close(replacement)
            except OSError:
                pass
        for descriptor in injected_descriptors:
            try:
                real_close(descriptor)
            except OSError:
                pass
        real_close(directory_descriptor)


def test_nested_duplicate_metadata_drift_closes_each_owned_descriptor_once() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        cache_dir = Path(temporary) / "cache"
        transaction = cache_module._begin_cache_directory_transaction(
            cache_dir,
            create=True,
        )
        assert transaction is not None
        state, owns_transaction = transaction
        assert owns_transaction
        pinned_descriptor = state.descriptor
        original_dup = os.dup
        original_fstat = os.fstat
        original_close = os.close
        duplicated_descriptor: int | None = None
        close_calls: dict[int, int] = {}

        def capture_duplicate(descriptor: int) -> int:
            nonlocal duplicated_descriptor
            duplicated_descriptor = original_dup(descriptor)
            return duplicated_descriptor

        def drift_duplicate_metadata(descriptor: int) -> os.stat_result:
            info = original_fstat(descriptor)
            if descriptor != duplicated_descriptor:
                return info
            values = list(info)
            values[0] = stat.S_IFMT(info.st_mode) | 0o755
            return os.stat_result(values)

        def count_close(descriptor: int) -> None:
            close_calls[descriptor] = close_calls.get(descriptor, 0) + 1
            original_close(descriptor)

        with (
            mock.patch.object(cache_module.os, "dup", side_effect=capture_duplicate),
            mock.patch.object(cache_module.os, "fstat", side_effect=drift_duplicate_metadata),
            mock.patch.object(cache_module.os, "close", side_effect=count_close),
        ):
            try:
                assert ContractCache(cache_dir, "test-api-key")._open_cache_dir(
                    create=False
                ) is None
            finally:
                cache_module._end_cache_directory_transaction(
                    state,
                    owns_transaction,
                )

        assert duplicated_descriptor is not None
        assert close_calls[duplicated_descriptor] == 1
        assert close_calls[pinned_descriptor] == 1
        assert state.descriptor == -1


def test_cross_cache_nested_capacity_fails_before_global_lock_reentry() -> None:
    class DetectingNonReentrantLock:
        def __init__(self) -> None:
            self.owner: int | None = None
            self.acquire_calls = 0
            self.release_calls = 0
            self.reentrant_attempts = 0

        def __enter__(self) -> DetectingNonReentrantLock:
            owner = threading.get_ident()
            if self.owner == owner:
                self.reentrant_attempts += 1
                raise RuntimeError("WOULD_SELF_DEADLOCK")
            assert self.owner is None
            self.owner = owner
            self.acquire_calls += 1
            return self

        def __exit__(self, *_args: object) -> None:
            assert self.owner == threading.get_ident()
            self.owner = None
            self.release_calls += 1

    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        cache_a = ContractCache(base / "cache-a", "test-api-key")
        cache_b = ContractCache(base / "cache-b", "test-api-key")
        detecting_lock = DetectingNonReentrantLock()
        baseline_fds = len(os.listdir("/proc/self/fd"))

        with mock.patch.object(cache_module, "_CAPACITY_LOCK", detecting_lock):
            with cache_a.capacity_reservation("a" * 64):
                with pytest.raises(AnalyzerError) as raised:
                    with cache_b.capacity_reservation("b" * 64):
                        pass

        assert raised.value.code == "LLM_CACHE_LOCK_FAILED"
        assert detecting_lock.reentrant_attempts == 0
        assert detecting_lock.acquire_calls == 1
        assert detecting_lock.release_calls == 1
        assert detecting_lock.owner is None
        assert getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {}) == {}
        assert len(os.listdir("/proc/self/fd")) == baseline_fds


def _assert_fork_child_unwind_preserves_reused_flock_fd(
    cache: ContractCache,
    context: object,
    reuse_path: Path,
) -> None:
    """The child must not retire a descriptor already closed by at-fork reset."""
    parent_baseline_fds = len(os.listdir("/proc/self/fd"))
    child = False
    child_baseline_fds = -1
    inherited_flock_descriptor = -1
    opened: list[int] = []
    state: cache_module._ActiveCacheDirectory | None = None
    child_state_was_reset = False
    child_registry_was_reset = False
    pid: int | None = None

    try:
        with context:  # type: ignore[attr-defined]
            state = next(
                iter(cache_module._ACTIVE_RESERVATIONS.directories.values())
            )
            inherited_flock_descriptor = next(iter(cache_module._ACTIVE_FLOCK_FDS))
            pid = os.fork()
            if pid == 0:
                child = True
                child_baseline_fds = len(os.listdir("/proc/self/fd"))
                child_state_was_reset = state.descriptor == -1
                child_registry_was_reset = (
                    not cache_module._ACTIVE_FLOCK_FDS
                    and not getattr(
                        cache_module._ACTIVE_RESERVATIONS,
                        "directories",
                        {},
                    )
                )
                for _ in range(16):
                    descriptor = os.open(
                        reuse_path,
                        os.O_RDWR | os.O_CREAT,
                        0o600,
                    )
                    opened.append(descriptor)
                    if descriptor == inherited_flock_descriptor:
                        break
    except BaseException:
        if child:
            for descriptor in opened:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            os._exit(2)
        raise

    if child:
        reused_descriptor_still_open = False
        try:
            os.fstat(inherited_flock_descriptor)
            reused_descriptor_still_open = True
        except OSError:
            pass
        state_is_retired = (
            state is not None
            and state.descriptor == -1
            and not state.reservations
            and not cache_module._ACTIVE_FLOCK_FDS
            and not getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {})
        )
        for descriptor in opened:
            try:
                os.close(descriptor)
            except OSError:
                pass
        no_child_leak = len(os.listdir("/proc/self/fd")) == child_baseline_fds
        os._exit(
            0
            if (
                inherited_flock_descriptor in opened
                and reused_descriptor_still_open
                and child_state_was_reset
                and child_registry_was_reset
                and state_is_retired
                and no_child_leak
            )
            else 1
        )

    assert pid is not None
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert state is not None and state.descriptor == -1
    assert getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {}) == {}
    assert not cache_module._ACTIVE_FLOCK_FDS
    assert len(os.listdir("/proc/self/fd")) == parent_baseline_fds


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
def test_capacity_child_unwind_does_not_close_reused_flock_fd(tmp_path: Path) -> None:
    cache = ContractCache(tmp_path / "capacity-cache", "test-api-key")
    _assert_fork_child_unwind_preserves_reused_flock_fd(
        cache,
        cache.capacity_reservation("1" * 64),
        tmp_path / "capacity-reused-fd",
    )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
def test_stripe_child_unwind_does_not_close_reused_flock_fd(tmp_path: Path) -> None:
    cache = ContractCache(tmp_path / "stripe-cache", "test-api-key")
    _assert_fork_child_unwind_preserves_reused_flock_fd(
        cache,
        cache.single_flight("2" * 64),
        tmp_path / "stripe-reused-fd",
    )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
@pytest.mark.parametrize("transaction_kind", ["capacity", "stripe"])
def test_fork_from_another_thread_closes_all_inherited_cache_descriptors(
    tmp_path: Path,
    transaction_kind: str,
) -> None:
    cache = ContractCache(tmp_path / f"{transaction_kind}-cache", "test-api-key")
    key = "5" * 64
    entered = threading.Event()
    release = threading.Event()
    state_holder: list[cache_module._ActiveCacheDirectory] = []
    failures: list[BaseException] = []
    baseline_fds = len(os.listdir("/proc/self/fd"))

    def hold_transaction() -> None:
        context = (
            cache.capacity_reservation(key)
            if transaction_kind == "capacity"
            else cache.single_flight(key)
        )
        try:
            with context:
                state_holder.append(
                    next(
                        iter(
                            cache_module._ACTIVE_RESERVATIONS.directories.values()
                        )
                    )
                )
                entered.set()
                release.wait(5)
        except BaseException as exc:
            failures.append(exc)
            entered.set()

    worker = threading.Thread(target=hold_transaction)
    worker.start()
    assert entered.wait(5)
    assert not failures
    assert len(state_holder) == 1
    state = state_holder[0]
    assert state.descriptor >= 0

    pid = os.fork()
    if pid == 0:
        descriptor_is_closed = False
        try:
            os.fstat(state.descriptor)
        except OSError:
            descriptor_is_closed = True
        os._exit(
            0
            if (
                descriptor_is_closed
                and state.descriptor == -1
                and not cache_module._ACTIVE_FLOCK_FDS
                and not getattr(
                    cache_module,
                    "_ACTIVE_CACHE_DIRECTORIES",
                    {},
                )
                and not getattr(
                    cache_module._ACTIVE_RESERVATIONS,
                    "directories",
                    {},
                )
            )
            else 1
        )

    _, status = os.waitpid(pid, 0)
    release.set()
    worker.join(5)
    assert not worker.is_alive()
    assert not failures
    assert os.waitstatus_to_exitcode(status) == 0
    assert state.descriptor == -1
    assert not cache_module._ACTIVE_FLOCK_FDS
    assert len(os.listdir("/proc/self/fd")) == baseline_fds


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
@pytest.mark.parametrize("transaction_kind", ["capacity", "stripe"])
@pytest.mark.parametrize("lifecycle_phase", ["acquire", "retire"])
def test_fork_waits_for_active_directory_lifecycle_transfer(
    tmp_path: Path,
    transaction_kind: str,
    lifecycle_phase: str,
) -> None:
    cache = ContractCache(tmp_path / f"{lifecycle_phase}-{transaction_kind}", "test-api-key")
    key = "6" * 64
    entered = threading.Event()
    leave_transaction = threading.Event()
    window_open = threading.Event()
    close_window = threading.Event()
    state_holder: list[cache_module._ActiveCacheDirectory] = []
    descriptor_holder: list[int] = []
    failures: list[BaseException] = []
    baseline_fds = len(os.listdir("/proc/self/fd"))
    real_create = cache_module._create_private_hierarchy
    real_close = os.close

    def pause_after_directory_open(path: Path, *, create: bool = True) -> int | None:
        descriptor = real_create(path, create=create)
        if descriptor is not None and lifecycle_phase == "acquire":
            descriptor_holder.append(descriptor)
            window_open.set()
            close_window.wait(5)
        return descriptor

    def pause_before_directory_close(descriptor: int) -> None:
        if (
            lifecycle_phase == "retire"
            and descriptor_holder
            and descriptor == descriptor_holder[0]
            and not window_open.is_set()
        ):
            window_open.set()
            close_window.wait(5)
        real_close(descriptor)

    def run_transaction() -> None:
        context = (
            cache.capacity_reservation(key)
            if transaction_kind == "capacity"
            else cache.single_flight(key)
        )
        try:
            with (
                mock.patch.object(
                    cache_module,
                    "_create_private_hierarchy",
                    side_effect=pause_after_directory_open,
                ),
                mock.patch.object(
                    cache_module.os,
                    "close",
                    side_effect=pause_before_directory_close,
                ),
                context,
            ):
                state = next(
                    iter(cache_module._ACTIVE_RESERVATIONS.directories.values())
                )
                state_holder.append(state)
                if lifecycle_phase == "retire":
                    descriptor_holder.append(state.descriptor)
                entered.set()
                leave_transaction.wait(5)
        except BaseException as exc:
            failures.append(exc)
            entered.set()
            window_open.set()

    worker = threading.Thread(target=run_transaction)
    worker.start()
    if lifecycle_phase == "acquire":
        assert window_open.wait(5)
    else:
        assert entered.wait(5)
        assert not failures
        leave_transaction.set()
        assert window_open.wait(5)
    assert len(descriptor_holder) == 1
    inherited_descriptor = descriptor_holder[0]

    delayed_release = threading.Timer(0.25, close_window.set)
    delayed_release.start()
    pid = os.fork()
    if pid == 0:
        descriptor_is_closed = False
        try:
            os.fstat(inherited_descriptor)
        except OSError:
            descriptor_is_closed = True
        os._exit(0 if descriptor_is_closed else 1)

    _, status = os.waitpid(pid, 0)
    leave_transaction.set()
    close_window.set()
    delayed_release.join(5)
    worker.join(5)
    assert not worker.is_alive()
    assert not failures
    assert os.waitstatus_to_exitcode(status) == 0
    assert state_holder and state_holder[0].descriptor == -1
    assert not cache_module._ACTIVE_FLOCK_FDS
    assert not cache_module._ACTIVE_CACHE_DIRECTORIES
    assert len(os.listdir("/proc/self/fd")) == baseline_fds


@pytest.mark.parametrize("transaction_kind", ["capacity", "stripe"])
@pytest.mark.parametrize("fault_phase", ["unlock", "close_pre", "close_post"])
def test_lock_cleanup_retires_every_owner_after_async_release_fault(
    tmp_path: Path,
    transaction_kind: str,
    fault_phase: str,
) -> None:
    cache = ContractCache(tmp_path / f"{fault_phase}-{transaction_kind}", "test-api-key")
    key = "7" * 64
    baseline_fds = len(os.listdir("/proc/self/fd"))
    real_flock = cache_module.fcntl.flock
    real_close = os.close
    injected = False
    lock_descriptors: list[int] = []
    directory_states: list[cache_module._ActiveCacheDirectory] = []
    replacements: list[int] = []

    def fault_flock(descriptor: int, operation: int) -> object:
        nonlocal injected
        if fault_phase == "unlock" and operation == cache_module.fcntl.LOCK_UN:
            injected = True
            raise KeyboardInterrupt("injected unlock interruption")
        return real_flock(descriptor, operation)

    def fault_close(descriptor: int) -> None:
        nonlocal injected
        if (
            fault_phase.startswith("close_")
            and not injected
            and descriptor in cache_module._ACTIVE_FLOCK_FDS
        ):
            injected = True
            if fault_phase == "close_pre":
                raise CloseRangePreActionError(5, "injected pre-action close")
            real_close(descriptor)
            replacement = os.open(tmp_path / "replacement", os.O_RDWR | os.O_CREAT, 0o600)
            assert replacement == descriptor
            replacements.append(replacement)
            raise KeyboardInterrupt("injected post-action close interruption")
        real_close(descriptor)

    context = (
        cache.capacity_reservation(key)
        if transaction_kind == "capacity"
        else cache.single_flight(key)
    )
    try:
        with (
            mock.patch.object(cache_module.fcntl, "flock", side_effect=fault_flock),
            mock.patch.object(cache_module.os, "close", side_effect=fault_close),
        ):
            try:
                with context:
                    lock_descriptors.extend(cache_module._ACTIVE_FLOCK_FDS)
                    directory_states.extend(cache_module._ACTIVE_CACHE_DIRECTORIES.values())
            except BaseException:
                pass

        for replacement in replacements:
            os.fstat(replacement)
        cleanup_is_complete = (
            injected
            and not cache_module._ACTIVE_FLOCK_FDS
            and not cache_module._ACTIVE_CACHE_DIRECTORIES
            and not getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {})
            and all(state.descriptor == -1 for state in directory_states)
            and len(os.listdir("/proc/self/fd")) == baseline_fds + len(replacements)
        )
        followup_completed = False
        if cleanup_is_complete:
            followup_key = "8" * 64
            followup = (
                cache.capacity_reservation(followup_key)
                if transaction_kind == "capacity"
                else cache.single_flight(followup_key)
            )
            with followup:
                followup_completed = True

        assert cleanup_is_complete
        assert followup_completed
    finally:
        for replacement in replacements:
            try:
                real_close(replacement)
            except OSError:
                pass
        for descriptor in lock_descriptors:
            try:
                real_close(descriptor)
            except OSError:
                pass
        for state in directory_states:
            if state.descriptor >= 0:
                try:
                    real_close(state.descriptor)
                except OSError:
                    pass
                state.descriptor = -1
        cache_module._ACTIVE_FLOCK_FDS.clear()
        cache_module._ACTIVE_CACHE_DIRECTORIES.clear()
        cache_module._ACTIVE_RESERVATIONS = threading.local()


@pytest.mark.parametrize("fault_timing", ["before", "after"])
def test_capacity_active_check_async_fault_still_retires_lock_and_directory(
    tmp_path: Path,
    fault_timing: str,
) -> None:
    cache = ContractCache(tmp_path / f"active-check-{fault_timing}", "test-api-key")
    key = "d" * 64
    followup_key = "e" * 64
    baseline_fds = len(os.listdir("/proc/self/fd"))
    real_active_check = cache_module._active_flock_is_owned
    real_close = os.close
    injected = False
    lock_descriptors: list[int] = []
    directory_states: list[cache_module._ActiveCacheDirectory] = []

    def fault_active_check(
        ownership: cache_module._ActiveFlockOwnership | None,
    ) -> bool:
        nonlocal injected
        if not injected:
            injected = True
            if fault_timing == "after":
                assert real_active_check(ownership)
            raise KeyboardInterrupt(f"injected {fault_timing}-check interruption")
        return real_active_check(ownership)

    try:
        with mock.patch.object(
            cache_module,
            "_active_flock_is_owned",
            side_effect=fault_active_check,
        ):
            with pytest.raises(KeyboardInterrupt):
                with cache.capacity_reservation(key):
                    lock_descriptors.extend(cache_module._ACTIVE_FLOCK_FDS)
                    directory_states.extend(
                        cache_module._ACTIVE_CACHE_DIRECTORIES.values()
                    )

        assert injected
        assert not cache_module._ACTIVE_FLOCK_FDS
        assert not cache_module._ACTIVE_CACHE_DIRECTORIES
        assert not getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {})
        assert directory_states
        assert all(state.descriptor == -1 for state in directory_states)
        assert len(os.listdir("/proc/self/fd")) == baseline_fds

        with cache.capacity_reservation(followup_key):
            pass
    finally:
        for descriptor in lock_descriptors:
            try:
                real_close(descriptor)
            except OSError:
                pass
        for state in directory_states:
            if state.descriptor >= 0:
                try:
                    real_close(state.descriptor)
                except OSError:
                    pass
                state.descriptor = -1
        cache_module._ACTIVE_FLOCK_FDS.clear()
        cache_module._ACTIVE_CACHE_DIRECTORIES.clear()
        cache_module._ACTIVE_RESERVATIONS = threading.local()


@pytest.mark.parametrize("publication_kind", ["growth", "auth"])
@pytest.mark.parametrize("unlink_timing", ["before", "after"])
def test_publication_cleanup_retires_directory_after_async_unlink_fault(
    tmp_path: Path,
    publication_kind: str,
    unlink_timing: str,
) -> None:
    cache_path = tmp_path / f"{publication_kind}-{unlink_timing}"
    cache = ContractCache(cache_path, "test-api-key")
    key = ("f" if publication_kind == "growth" else "0") * 64
    baseline_fds = len(os.listdir("/proc/self/fd"))
    real_close = os.close
    real_unlink = os.unlink
    publication_directory: list[int] = []
    replacements: list[int] = []
    link_injected = False
    unlink_injected = False
    close_injected = False

    def fault_link(*args: object, **kwargs: object) -> None:
        nonlocal link_injected
        link_injected = True
        assert len(cache_module._ACTIVE_TRANSIENT_FDS) == 1
        publication_directory.extend(cache_module._ACTIVE_TRANSIENT_FDS)
        raise OSError(5, "injected publication link failure")

    def fault_unlink(path: object, *args: object, **kwargs: object) -> None:
        nonlocal unlink_injected
        assert not unlink_injected
        unlink_injected = True
        if unlink_timing == "after":
            real_unlink(path, *args, **kwargs)
        raise KeyboardInterrupt(f"injected {unlink_timing}-unlink interruption")

    def fault_close(descriptor: int) -> None:
        nonlocal close_injected
        if publication_directory and descriptor == publication_directory[0]:
            assert not close_injected
            close_injected = True
            real_close(descriptor)
            replacement = os.open(
                tmp_path / f"replacement-{publication_kind}-{unlink_timing}",
                os.O_RDWR | os.O_CREAT,
                0o600,
            )
            assert replacement == descriptor
            replacements.append(replacement)
            raise KeyboardInterrupt("injected post-close interruption")
        real_close(descriptor)

    try:
        with (
            mock.patch.object(cache_module.os, "link", side_effect=fault_link),
            mock.patch.object(cache_module.os, "unlink", side_effect=fault_unlink),
            mock.patch.object(cache_module.os, "close", side_effect=fault_close),
        ):
            with pytest.raises(KeyboardInterrupt):
                if publication_kind == "growth":
                    identity, contract, audit = _growth_cache_fixture(cache)
                    cache.put(
                        key,
                        identity,
                        contract,  # type: ignore[arg-type]
                        audit,
                        raw_response="{}",
                    )
                else:
                    cache.put_auth_record(
                        key,
                        {"kind": "auth"},
                        {"origin": "fault-test"},
                        "{}",
                    )

        assert link_injected
        assert unlink_injected
        assert close_injected
        assert len(publication_directory) == 1
        assert len(replacements) == 1
        os.fstat(replacements[0])
        assert not cache_module._ACTIVE_TRANSIENT_FDS
        assert not cache_module._ACTIVE_FLOCK_FDS
        assert not cache_module._ACTIVE_CACHE_DIRECTORIES
        assert not getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {})
        assert len(os.listdir("/proc/self/fd")) == baseline_fds + 1

        temporary_names = [
            name for name in os.listdir(cache_path) if cache_module._TEMPORARY_NAME.fullmatch(name)
        ]
        assert len(temporary_names) == (1 if unlink_timing == "before" else 0)

        with cache.capacity_reservation("1" * 64):
            pass
        os.fstat(replacements[0])
    finally:
        for name in cache_path.iterdir() if cache_path.exists() else ():
            if cache_module._TEMPORARY_NAME.fullmatch(name.name):
                try:
                    real_unlink(name)
                except OSError:
                    pass
        for replacement in replacements:
            try:
                real_close(replacement)
            except OSError:
                pass
        for descriptor in publication_directory:
            if descriptor not in replacements:
                try:
                    real_close(descriptor)
                except OSError:
                    pass
        cache_module._ACTIVE_TRANSIENT_FDS.clear()
        cache_module._ACTIVE_FLOCK_FDS.clear()
        cache_module._ACTIVE_CACHE_DIRECTORIES.clear()
        cache_module._ACTIVE_RESERVATIONS = threading.local()


@pytest.mark.parametrize("publication_kind", ["growth", "auth"])
def test_successful_publication_post_unlink_fault_does_not_retry_mutable_name(
    tmp_path: Path,
    publication_kind: str,
) -> None:
    cache_path = tmp_path / f"successful-post-unlink-{publication_kind}"
    cache = ContractCache(cache_path, "test-api-key")
    key = ("2" if publication_kind == "growth" else "3") * 64
    destination = f"{key}.json" if publication_kind == "growth" else f"auth-{key}.json"
    baseline_fds = len(os.listdir("/proc/self/fd"))
    real_close = os.close
    real_unlink = os.unlink
    unlink_calls: list[str] = []
    temporary_name: str | None = None
    substitute_identity: tuple[int, int] | None = None
    substitute_payload = b"retained-ambiguous-temporary"

    def post_action_unlink(
        path: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        nonlocal temporary_name, substitute_identity
        rendered = os.fspath(path)
        assert isinstance(rendered, str)
        unlink_calls.append(rendered)
        if len(unlink_calls) == 1:
            directory = kwargs.get("dir_fd")
            assert isinstance(directory, int)
            source = os.lstat(rendered, dir_fd=directory)
            published = os.lstat(destination, dir_fd=directory)
            assert (source.st_dev, source.st_ino) == (
                published.st_dev,
                published.st_ino,
            )
            real_unlink(path, *args, **kwargs)
            replacement = os.open(
                rendered,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory,
            )
            try:
                os.write(replacement, substitute_payload)
                info = os.fstat(replacement)
                substitute_identity = (info.st_dev, info.st_ino)
            finally:
                real_close(replacement)
            temporary_name = rendered
            raise KeyboardInterrupt("injected post-action unlink interruption")
        real_unlink(path, *args, **kwargs)

    try:
        with mock.patch.object(
            cache_module.os,
            "unlink",
            side_effect=post_action_unlink,
        ):
            with pytest.raises(
                KeyboardInterrupt,
                match="injected post-action unlink interruption",
            ):
                if publication_kind == "growth":
                    identity, contract, audit = _growth_cache_fixture(cache)
                    cache.put(
                        key,
                        identity,
                        contract,  # type: ignore[arg-type]
                        audit,
                        raw_response="{}",
                    )
                else:
                    identity = {"kind": "auth"}
                    cache.put_auth_record(
                        key,
                        identity,
                        {"origin": "published-before-interrupt"},
                        "{}",
                    )

        assert temporary_name is not None
        assert substitute_identity is not None
        assert unlink_calls == [temporary_name]
        substitute = cache_path / temporary_name
        info = substitute.stat()
        assert (info.st_dev, info.st_ino) == substitute_identity
        assert substitute.read_bytes() == substitute_payload
        assert (cache_path / destination).is_file()

        if publication_kind == "growth":
            assert cache.authenticated_contract(key, identity) is not None
        else:
            record = cache.get_auth_record(key, identity)
            assert record is not None
            assert record["contract"] == {"origin": "published-before-interrupt"}

        assert not cache_module._ACTIVE_TRANSIENT_FDS
        assert not cache_module._ACTIVE_FLOCK_FDS
        assert not cache_module._ACTIVE_CACHE_DIRECTORIES
        assert not getattr(cache_module._ACTIVE_RESERVATIONS, "directories", {})
        assert len(os.listdir("/proc/self/fd")) == baseline_fds
    finally:
        if temporary_name is not None:
            try:
                real_unlink(cache_path / temporary_name)
            except OSError:
                pass


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
@pytest.mark.parametrize("capability_kind", ["duplicate", "entry", "temporary"])
def test_cross_thread_fork_closes_nested_cache_capabilities(
    tmp_path: Path,
    capability_kind: str,
) -> None:
    cache = ContractCache(tmp_path / f"cache-{capability_kind}", "test-api-key")
    growth_identity, growth_contract, growth_audit = _growth_cache_fixture(cache)
    growth_key = "9" * 64
    auth_key = "a" * 64
    auth_identity = {"kind": "auth"}
    if capability_kind == "duplicate":
        assert cache.put(
            growth_key,
            growth_identity,
            growth_contract,  # type: ignore[arg-type]
            growth_audit,
            raw_response="{}",
        )
    elif capability_kind == "entry":
        assert cache.put_auth_record(
            auth_key,
            auth_identity,
            {"origin": "auth-entry"},
            "{}",
        )

    baseline_fds = len(os.listdir("/proc/self/fd"))
    window_open = threading.Event()
    release_window = threading.Event()
    inherited_descriptors: list[int] = []
    results: list[object] = []
    failures: list[BaseException] = []
    real_dup = os.dup
    real_read = os.read
    real_temporary = cache_module._create_private_temporary

    def pause_duplicate(descriptor: int) -> int:
        duplicate = real_dup(descriptor)
        if capability_kind == "duplicate" and not window_open.is_set():
            inherited_descriptors.append(duplicate)
            window_open.set()
            release_window.wait(5)
        return duplicate

    def pause_entry_read(descriptor: int, size: int) -> bytes:
        if capability_kind == "entry" and not window_open.is_set():
            inherited_descriptors.append(descriptor)
            window_open.set()
            release_window.wait(5)
        return real_read(descriptor, size)

    def pause_temporary(directory: int, key: str) -> tuple[str, object]:
        created = real_temporary(directory, key)
        if capability_kind == "temporary" and not window_open.is_set():
            temporary_owner = created[1]
            descriptor = (
                temporary_owner.descriptor
                if hasattr(temporary_owner, "descriptor")
                else temporary_owner.fileno()
            )
            inherited_descriptors.append(descriptor)
            window_open.set()
            release_window.wait(5)
        return created

    def exercise_production_path() -> None:
        try:
            with (
                mock.patch.object(cache_module.os, "dup", side_effect=pause_duplicate),
                mock.patch.object(cache_module.os, "read", side_effect=pause_entry_read),
                mock.patch.object(
                    cache_module,
                    "_create_private_temporary",
                    side_effect=pause_temporary,
                ),
            ):
                if capability_kind == "duplicate":
                    with cache.capacity_reservation("b" * 64):
                        results.append(
                            cache.authenticated_contract(growth_key, growth_identity)
                        )
                elif capability_kind == "entry":
                    with cache.capacity_reservation("c" * 64):
                        results.append(cache.get_auth_record(auth_key, auth_identity))
                else:
                    results.append(
                        cache.put(
                            growth_key,
                            growth_identity,
                            growth_contract,  # type: ignore[arg-type]
                            growth_audit,
                            raw_response="{}",
                        )
                    )
        except BaseException as exc:
            failures.append(exc)
            window_open.set()

    worker = threading.Thread(target=exercise_production_path)
    worker.start()
    assert window_open.wait(5)
    assert not failures
    assert len(inherited_descriptors) == 1
    inherited_descriptor = inherited_descriptors[0]

    delayed_release = threading.Timer(0.25, release_window.set)
    delayed_release.start()
    pid = os.fork()
    if pid == 0:
        descriptor_is_closed = False
        try:
            os.fstat(inherited_descriptor)
        except OSError:
            descriptor_is_closed = True
        os._exit(0 if descriptor_is_closed else 1)

    _, status = os.waitpid(pid, 0)
    release_window.set()
    delayed_release.join(5)
    worker.join(5)
    assert not worker.is_alive()
    assert not failures
    assert os.waitstatus_to_exitcode(status) == 0
    assert results and results[0] is not None
    assert not getattr(cache_module, "_ACTIVE_TRANSIENT_FDS", {})
    assert not cache_module._ACTIVE_FLOCK_FDS
    assert not cache_module._ACTIVE_CACHE_DIRECTORIES
    assert len(os.listdir("/proc/self/fd")) == baseline_fds


@pytest.mark.parametrize("transaction_kind", ["capacity", "stripe"])
def test_relative_cache_path_stays_pinned_after_cwd_switch_and_ancestor_rename(
    tmp_path: Path,
    transaction_kind: str,
) -> None:
    original_cwd = Path.cwd()
    scope_a = tmp_path / "scope-a"
    scope_b = tmp_path / "scope-b"
    detached_a = tmp_path / "detached-a"
    scope_a.mkdir()
    scope_b.mkdir()
    record_key = "3" * 64
    lock_key = "4" * 64
    identity = {"kind": "auth"}
    try:
        os.chdir(scope_a)
        cache = ContractCache(Path("cache"), "test-api-key")
        assert cache.put_auth_record(
            record_key,
            identity,
            {"origin": "A"},
            '"A"',
        )

        os.chdir(scope_b)
        other_cache = ContractCache(Path("cache"), "test-api-key")
        assert other_cache.put_auth_record(
            record_key,
            identity,
            {"origin": "B"},
            '"B"',
        )

        os.chdir(scope_a)
        context = (
            cache.capacity_reservation(lock_key)
            if transaction_kind == "capacity"
            else cache.single_flight(lock_key)
        )
        with context:
            state = next(
                iter(cache_module._ACTIVE_RESERVATIONS.directories.values())
            )
            pinned_identity = (state.device, state.inode)
            scope_a.rename(detached_a)
            os.chdir(scope_b)

            record = cache.get_auth_record(record_key, identity)
            assert record is not None
            assert record["contract"] == {"origin": "A"}
            active = next(
                iter(cache_module._ACTIVE_RESERVATIONS.directories.values())
            )
            assert (active.device, active.inode) == pinned_identity

        # The frozen lexical path now names a missing ancestor.  It must not
        # drift to scope-b/cache merely because the process cwd changed.
        assert cache.get_auth_record(record_key, identity) is None
        assert other_cache.get_auth_record(record_key, identity) is not None
    finally:
        os.chdir(original_cwd)
