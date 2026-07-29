"""Tests proving STORY-079: the single-instance advisory lock on ``<app-data>/.instance.lock``.

Source of truth: ``docs/v3_specification/12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md``
§5 (file-lock policy, SPEC-035 stale-owner recovery) and §6 (multi-instance handling).
"""

import os
from pathlib import Path
from typing import override

import msgspec
import pytest

from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.infra._internal.instance_lock import (
    LOCK_FILENAME,
    PosixLockPrimitives,
    acquire_instance_lock_impl,
    default_primitives,
)
from ollama_llm_bench.backend.infra.api import acquire_instance_lock
from ollama_llm_bench.backend.infra.models import (
    InstanceLockHandle,
    InstanceLockOutcome,
    InstanceLockRecord,
)
from ollama_llm_bench.backend.infra.tests.conftest import FAKE_NOW_UTC, FakeClock


def test_first_acquisition_succeeds_and_records_pid_and_timestamp(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """Proves: STORY-079-AC-1

    Given a data directory with no live lock owner, acquisition succeeds and
    ``<app-data>/.instance.lock`` records this process's PID and the clock's
    start timestamp.
    """
    # Arrange
    expected_lock_file = tmp_path / LOCK_FILENAME

    # Act
    result = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert result.lock is not None
    held_locks.append(result.lock)
    written = msgspec.json.decode(expected_lock_file.read_bytes(), type=InstanceLockRecord)

    # Assert
    assert result.outcome is InstanceLockOutcome.ACQUIRED
    assert result.lock_file == expected_lock_file
    assert written == InstanceLockRecord(pid=os.getpid(), started_at=FAKE_NOW_UTC)


def test_second_acquisition_against_live_owner_refuses_and_touches_nothing(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """Proves: STORY-079-AC-2

    Given the lock is held by a live process, a second acquisition against the
    same data directory reports "already running", hands back no release handle,
    names the live holder, and leaves every file in the data directory unchanged
    -- no database is opened and nothing is written.
    """
    # Arrange
    first = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert first.lock is not None
    held_locks.append(first.lock)
    before = {path.name: path.read_bytes() for path in sorted(tmp_path.iterdir())}

    # Act
    second = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    after = {path.name: path.read_bytes() for path in sorted(tmp_path.iterdir())}

    # Assert
    assert second.outcome is InstanceLockOutcome.ALREADY_RUNNING
    assert second.lock is None
    assert second.holder == InstanceLockRecord(pid=os.getpid(), started_at=FAKE_NOW_UTC)
    assert after == before


def test_release_leaves_the_lock_file_on_disk(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """Pin the deliberate decision that ``release()`` never deletes the lock file.

    Deleting the file on release would race a concurrent acquirer: it could
    create and lock a brand-new file at a different inode in the instant
    between this process's delete and the next process's open, so this
    process and the new one would each believe they alone hold the
    single-instance lock. Leaving the file in place after release closes that
    race -- every acquirer, past and future, locks the same inode.
    """
    # Arrange
    expected_lock_file = tmp_path / LOCK_FILENAME
    result = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert result.lock is not None
    held_locks.append(result.lock)

    # Act
    result.lock.release()

    # Assert
    assert expected_lock_file.exists()


class _UnlockFailsPrimitives(PosixLockPrimitives):
    """``LockPrimitives`` whose ``unlock`` always raises, driving ``release()``'s error path."""

    @override
    def unlock(self, fd: int) -> None:
        """Simulate ``fcntl.flock(fd, LOCK_UN)`` failing with an OS error."""
        raise OSError("Simulated unlock failure")


def test_release_does_not_raise_when_unlock_fails(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """``release()`` must never raise, even when the underlying unlock call fails.

    ``InstanceLockHandle.release()`` is documented as "never raises" because two
    callers depend on that promise: the application's shutdown sequence, and the
    ``held_locks`` teardown fixture, whose release loop would abort on the first
    failure and leak every remaining lock into the rest of the test session.
    """
    # Arrange
    primitives = _UnlockFailsPrimitives()
    result = acquire_instance_lock_impl(
        app_data_root=tmp_path, clock=fake_clock, primitives=primitives
    )
    assert result.lock is not None

    # Act
    result.lock.release()
    reacquired = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert reacquired.lock is not None
    held_locks.append(reacquired.lock)

    # Assert
    assert reacquired.outcome is InstanceLockOutcome.ACQUIRED


_HIGHEST_PROBED_PID = 2**15 - 1


def _find_dead_pid() -> int:
    """Return a PID no live process owns, probing down from the top of the PID space."""
    primitives = PosixLockPrimitives()
    candidate = _HIGHEST_PROBED_PID
    while primitives.is_pid_alive(candidate):
        candidate -= 1
    return candidate


class LaggingLockPrimitives(PosixLockPrimitives):
    """Report the lock as held once, then behave normally.

    Simulates the kernel's lock visibility lagging a crashed owner's reaping --
    the exact window ``05_CONCURRENCY_GUARANTEES.md`` §5 says the PID-liveness
    check exists to close.
    """

    def __init__(self) -> None:
        """Arm exactly one simulated refusal before real ``flock`` behaviour resumes."""
        self.refusals_remaining = 1

    @override
    def try_lock_exclusive(self, fd: int) -> bool:
        """Report the lock as already held on the first call, then delegate to ``flock``."""
        if self.refusals_remaining > 0:
            self.refusals_remaining -= 1
            return False
        return super().try_lock_exclusive(fd)


def test_stale_lock_from_dead_pid_is_reclaimed(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """Proves: STORY-079-AC-3

    Given a lock file whose recorded PID is not a live process, and a lock that
    still appears held because the operating system has not yet published the
    dead owner's release, acquisition reclaims the stale lock and succeeds,
    rewriting the file to name this process.
    """
    # Arrange
    stale = InstanceLockRecord(pid=_find_dead_pid(), started_at="2026-07-28T09:15:00Z")
    lock_file = tmp_path / LOCK_FILENAME
    lock_file.write_bytes(msgspec.json.encode(stale))

    # Act
    result = acquire_instance_lock_impl(
        app_data_root=tmp_path, clock=fake_clock, primitives=LaggingLockPrimitives()
    )
    assert result.lock is not None
    held_locks.append(result.lock)
    written = msgspec.json.decode(lock_file.read_bytes(), type=InstanceLockRecord)

    # Assert
    assert result.outcome is InstanceLockOutcome.ACQUIRED
    assert written == InstanceLockRecord(pid=os.getpid(), started_at=FAKE_NOW_UTC)


def test_release_is_idempotent(
    tmp_path: Path,
    fake_clock: FakeClock,
) -> None:
    """Release a held lock twice; the second call is a no-op, not a bad file descriptor.

    The shutdown sequence and the crash path can both reach the release step, so
    a double release must not raise.
    """
    # Arrange
    result = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert result.lock is not None

    # Act
    result.lock.release()
    result.lock.release()
    reacquired = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert reacquired.lock is not None
    reacquired.lock.release()

    # Assert
    assert reacquired.outcome is InstanceLockOutcome.ACQUIRED


def test_unreadable_lock_record_is_treated_as_no_owner(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """A hand-edited or half-written lock file is data, not a crash.

    An instance that died between creating ``.instance.lock`` and writing its
    record leaves an empty body; that must be reclaimable, not fatal.
    """
    # Arrange
    lock_file = tmp_path / LOCK_FILENAME
    lock_file.write_bytes(b"not json at all")

    # Act
    result = acquire_instance_lock_impl(
        app_data_root=tmp_path, clock=fake_clock, primitives=LaggingLockPrimitives()
    )
    assert result.lock is not None
    held_locks.append(result.lock)

    # Assert
    assert result.outcome is InstanceLockOutcome.ACQUIRED


class _LockingFailsPrimitives(PosixLockPrimitives):
    """``LockPrimitives`` that takes the real flock, then reports the attempt as failed."""

    @override
    def try_lock_exclusive(self, fd: int) -> bool:
        """Take the real ``flock`` via ``super()``, then raise as if the call itself failed.

        Taking the real lock first is what makes this fake able to detect a
        stranded descriptor: if the caller's cleanup does not close ``fd``, the
        flock taken here is still held when a fresh acquisition retries, and
        that retry is refused.
        """
        super().try_lock_exclusive(fd)
        raise OSError("Simulated try_lock_exclusive failure")


def test_lock_failure_does_not_strand_the_descriptor(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """A failed lock attempt must close its descriptor rather than leak the flock.

    A stranded flock from this failure would make the app refuse to start
    against its own orphaned lock on the very next launch attempt.
    """
    # Arrange
    primitives = _LockingFailsPrimitives()

    # Act
    with pytest.raises(ConfigurationError):
        acquire_instance_lock_impl(app_data_root=tmp_path, clock=fake_clock, primitives=primitives)
    retry = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert retry.lock is not None
    held_locks.append(retry.lock)

    # Assert
    assert retry.outcome is InstanceLockOutcome.ACQUIRED


class _ClaimFailsPrimitives(PosixLockPrimitives):
    """``LockPrimitives`` whose ``current_pid`` raises once the flock is already held."""

    @override
    def current_pid(self) -> int:
        """Simulate an OS-level failure while writing the ownership record."""
        raise OSError("Simulated current_pid failure")


def test_claim_failure_after_locking_does_not_strand_the_lock(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """A failure writing the ownership record after locking must not strand the flock.

    This is the exact self-wedge scenario ``handed_off`` exists to prevent: if the
    descriptor stayed open on this path, the app would refuse to start against
    its own orphaned lock on the very next launch attempt.
    """
    # Arrange
    primitives = _ClaimFailsPrimitives()

    # Act
    with pytest.raises(ConfigurationError):
        acquire_instance_lock_impl(app_data_root=tmp_path, clock=fake_clock, primitives=primitives)
    retry = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert retry.lock is not None
    held_locks.append(retry.lock)

    # Assert
    assert retry.outcome is InstanceLockOutcome.ACQUIRED


class _AlwaysRefusesPrimitives(PosixLockPrimitives):
    """``LockPrimitives`` that reports every liveness check and lock attempt as failed."""

    @override
    def try_lock_exclusive(self, fd: int) -> bool:
        """Report every lock attempt -- initial or retry -- as already held elsewhere."""
        return False

    @override
    def is_pid_alive(self, pid: int) -> bool:
        """Report every recorded owner as dead, so staleness alone never blocks reclaim."""
        return False


def test_stale_lock_whose_retry_still_fails_refuses_rather_than_forcing(
    tmp_path: Path,
    fake_clock: FakeClock,
) -> None:
    """A lock judged stale must still be refused if retaking it fails.

    Without the ``and`` guard on the second lock attempt in
    ``acquire_instance_lock_impl``, a stale-judged lock would be forced open
    even though the retry itself reports failure -- letting two instances run
    at once, which is the one thing this module exists to prevent.
    """
    # Arrange
    lock_file = tmp_path / LOCK_FILENAME
    lock_file.write_bytes(b"")
    primitives = _AlwaysRefusesPrimitives()

    # Act
    result = acquire_instance_lock_impl(
        app_data_root=tmp_path, clock=fake_clock, primitives=primitives
    )

    # Assert
    assert result.outcome is InstanceLockOutcome.ALREADY_RUNNING


class _ClaimFailsWithProgrammerErrorPrimitives(PosixLockPrimitives):
    """``LockPrimitives`` whose ``current_pid`` raises a non-``OSError`` after locking."""

    @override
    def current_pid(self) -> int:
        """Simulate a bug -- a non-OS failure -- while writing the ownership record."""
        raise RuntimeError("Simulated non-OSError failure")


def test_non_os_error_after_locking_propagates_and_still_releases_the_lock(
    tmp_path: Path,
    fake_clock: FakeClock,
    held_locks: list[InstanceLockHandle],
) -> None:
    """A non-``OSError`` escaping after the flock is taken must propagate unwrapped.

    ``acquire_instance_lock_impl`` only translates ``OSError`` into
    ``ConfigurationError``; anything else is not an environment failure the
    caller can retry past, so it must surface as-is rather than being coerced
    into the taxonomy. The ``finally`` block must still drop the real flock
    already taken before the failure, or every later acquisition in this
    process would be refused by its own orphaned lock.
    """
    # Arrange
    primitives = _ClaimFailsWithProgrammerErrorPrimitives()

    # Act
    with pytest.raises(RuntimeError):
        acquire_instance_lock_impl(app_data_root=tmp_path, clock=fake_clock, primitives=primitives)
    retry = acquire_instance_lock(app_data_root=tmp_path, clock=fake_clock)
    assert retry.lock is not None
    held_locks.append(retry.lock)

    # Assert
    assert retry.outcome is InstanceLockOutcome.ACQUIRED


def test_default_primitives_on_non_posix_host_names_the_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-POSIX host cannot enforce the single-instance guarantee at all.

    The failure message must name the actual platform so a user reading the
    launch error understands why, not merely that something is unsupported.
    """
    # Arrange
    monkeypatch.setattr(os, "name", "nt")

    # Act
    with pytest.raises(ConfigurationError) as exc_info:
        default_primitives()

    # Assert
    assert "'nt'" in str(exc_info.value)
