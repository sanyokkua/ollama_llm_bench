"""Acquire the process-lifetime single-instance advisory lock.

Source of truth: ``docs/v3_specification/12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md``
§5 (SPEC-035: the lock file records the owning PID and a start timestamp; an
apparently-held lock whose recorded PID is not a live process is stale and is
re-acquired) and §6 (a later instance on the same data directory refuses to run
without opening the database or mutating the directory).

The operating-system calls sit behind the ``LockPrimitives`` seam so the
stale-reclaim branch — which depends on the kernel's lock visibility lagging a
dead owner's reaping — is deterministically testable.
"""

import contextlib
import errno
import os
from pathlib import Path
from typing import Final, Protocol

import msgspec

from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.infra.models import (
    InstanceLockOutcome,
    InstanceLockRecord,
    InstanceLockResult,
)
from ollama_llm_bench.backend.infra.protocols import Clock

LOCK_FILENAME: Final[str] = ".instance.lock"
_LOCK_FILE_MODE: Final[int] = 0o600
_LOCK_BUSY_ERRNOS: Final[frozenset[int]] = frozenset({errno.EACCES, errno.EAGAIN})
_MAX_RECORD_BYTES: Final[int] = 4096


class LockPrimitives(Protocol):
    """The operating-system operations the acquire algorithm depends on."""

    def try_lock_exclusive(self, fd: int) -> bool:
        """Take a non-blocking exclusive advisory lock; return whether it succeeded."""
        ...

    def unlock(self, fd: int) -> None:
        """Drop the advisory lock held on ``fd``."""
        ...

    def is_pid_alive(self, pid: int) -> bool:
        """Report whether a live process currently owns ``pid``."""
        ...

    def current_pid(self) -> int:
        """Return this process's identifier."""
        ...


class PosixLockPrimitives:
    """``LockPrimitives`` backed by ``fcntl.flock`` and ``os.kill(pid, 0)``.

    ``fcntl.flock`` is deliberately chosen over ``fcntl.lockf``: flock locks are
    scoped to the open file description, so a second descriptor on the same file
    is refused even within one process, which is exactly the multi-instance
    semantics §6 describes.
    """

    def try_lock_exclusive(self, fd: int) -> bool:
        """Take a non-blocking exclusive ``flock`` on ``fd``.

        Args:
            fd: The open file descriptor to lock.

        Returns:
            ``True`` if the lock was taken; ``False`` if it is already held
            elsewhere.
        """
        import fcntl  # noqa: PLC0415  # fcntl is POSIX-only; a module-level import breaks import on Windows

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in _LOCK_BUSY_ERRNOS:
                return False
            raise
        return True

    def unlock(self, fd: int) -> None:
        """Drop the ``flock`` held on ``fd``.

        Args:
            fd: The open file descriptor whose lock is dropped.
        """
        import fcntl  # noqa: PLC0415  # fcntl is POSIX-only; a module-level import breaks import on Windows

        fcntl.flock(fd, fcntl.LOCK_UN)

    def is_pid_alive(self, pid: int) -> bool:
        """Report whether ``pid`` currently names a live process via ``os.kill(pid, 0)``.

        Args:
            pid: The process identifier to probe.

        Returns:
            ``True`` when the process exists (including when it is owned by
            another user and only a permission error is observable);
            ``False`` when it does not.
        """
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def current_pid(self) -> int:
        """Return this process's PID via ``os.getpid()``.

        Returns:
            This process's operating-system process identifier.
        """
        return os.getpid()


class _HeldInstanceLock:
    """A taken advisory lock, released at shutdown by the composition root."""

    def __init__(self, *, lock_file: Path, fd: int, primitives: LockPrimitives) -> None:
        self._lock_file = lock_file
        self._fd: int | None = fd
        self._primitives = primitives

    @property
    def lock_file(self) -> Path:
        """The lock file this handle holds."""
        return self._lock_file

    def release(self) -> None:
        """Release the advisory lock and close its descriptor; idempotent."""
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        # The close always runs, even if unlock raises: closing the descriptor
        # drops the flock regardless of whether the explicit unlock call above
        # succeeded, because a flock lives on the open file description, not on
        # any handle to it. Either call failing must not break release()'s
        # "never raises" promise.
        try:
            with contextlib.suppress(OSError):
                self._primitives.unlock(fd)
        finally:
            with contextlib.suppress(OSError):
                os.close(fd)


def default_primitives() -> LockPrimitives:
    """Return the primitives for this host.

    Returns:
        The POSIX ``fcntl.flock`` implementation.

    Raises:
        ConfigurationError: This host has no POSIX advisory-lock support, so the
            single-instance guarantee cannot be enforced and launch must abort
            rather than silently permit two writers.
    """
    if os.name != "posix":
        raise ConfigurationError(
            message=(
                f"The single-instance lock requires POSIX advisory locking, which "
                f"this platform ('{os.name}') does not provide."
            ),
        )
    return PosixLockPrimitives()


def acquire_instance_lock_impl(
    *, app_data_root: Path, clock: Clock, primitives: LockPrimitives
) -> InstanceLockResult:
    """Take, refuse, or reclaim the single-instance lock in ``app_data_root``.

    A lock that appears held is only honoured while its recorded owner is a live
    process. When the recorded PID names no live process — or the record is
    unreadable — the lock is stale (SPEC-035) and is retaken, so a crash never
    leaves the data directory permanently locked.

    Args:
        app_data_root: The already-created application data directory the lock
            file lives in.
        clock: The time source stamping the lock record's start timestamp.
        primitives: The operating-system operations backing the acquire
            algorithm.

    Returns:
        The acquire/refuse outcome; on success it carries the release handle,
        and the lock file now names this process. On refusal it carries the
        live holder's record, if readable.

    Raises:
        ConfigurationError: The lock file could not be opened, or taking,
            claiming, or reading the lock's ownership record failed with an
            OS error that leaves nothing reclaimable (e.g. no advisory-lock
            slots left, or the data volume is full while writing the
            ownership record). The descriptor is always closed first, so the
            failure never wedges this process against its own future
            retries.
    """
    lock_file = app_data_root / LOCK_FILENAME
    fd = _open_lock_file(lock_file)
    holder: InstanceLockRecord | None = None
    handed_off = False
    try:
        if primitives.try_lock_exclusive(fd):
            claimed = _claim(lock_file=lock_file, fd=fd, clock=clock, primitives=primitives)
            handed_off = True
            return claimed
        holder = _read_record(fd)
        if _is_stale(holder=holder, primitives=primitives) and primitives.try_lock_exclusive(fd):
            reclaimed = _claim(lock_file=lock_file, fd=fd, clock=clock, primitives=primitives)
            handed_off = True
            return reclaimed
    except OSError as exc:
        raise ConfigurationError(
            message=f"Cannot take the instance lock at '{lock_file}': {exc.strerror or exc}.",
        ) from exc
    finally:
        if not handed_off:
            with contextlib.suppress(OSError):
                os.close(fd)
    return InstanceLockResult(
        outcome=InstanceLockOutcome.ALREADY_RUNNING, lock_file=lock_file, holder=holder
    )


def _is_stale(*, holder: InstanceLockRecord | None, primitives: LockPrimitives) -> bool:
    """Report whether an apparently-held lock's recorded owner is already gone.

    An unreadable record counts as stale: a first instance that died between
    creating the lock file and writing its record leaves an empty body, and that
    must be reclaimable rather than permanently blocking (SPEC-035).

    Args:
        holder: The ownership record read off the lock file, or ``None`` when
            the record was unreadable.
        primitives: Supplies the liveness check for the recorded PID.

    Returns:
        ``True`` when the lock has no live owner and should be reclaimed.
    """
    return holder is None or not primitives.is_pid_alive(holder.pid)


def _open_lock_file(lock_file: Path) -> int:
    """Open (creating if absent, never truncating) the lock file.

    Raises:
        ConfigurationError: The lock file could not be opened — the data
            directory is missing or the process lacks permission to write it.
    """
    try:
        return os.open(lock_file, os.O_RDWR | os.O_CREAT, _LOCK_FILE_MODE)
    except OSError as exc:
        raise ConfigurationError(
            message=f"Cannot open the instance lock file at '{lock_file}': {exc.strerror or exc}.",
        ) from exc


def _read_record(fd: int) -> InstanceLockRecord | None:
    """Read the ownership record off a lock file without modifying it.

    The file's content is external data -- it may be empty (a first instance
    crashed between creating and writing it) or hand-edited -- so an unreadable
    body is reported as "no known owner", never raised.

    Args:
        fd: The open lock-file descriptor to read from.

    Returns:
        The decoded ownership record, or ``None`` when the body is empty,
        truncated, or otherwise not a valid ``InstanceLockRecord``.
    """
    os.lseek(fd, 0, os.SEEK_SET)
    raw = os.read(fd, _MAX_RECORD_BYTES)
    try:
        return msgspec.json.decode(raw, type=InstanceLockRecord)
    except (msgspec.DecodeError, msgspec.ValidationError):
        return None


def _claim(
    *, lock_file: Path, fd: int, clock: Clock, primitives: LockPrimitives
) -> InstanceLockResult:
    """Write this process's ownership record into an already-locked descriptor.

    Args:
        lock_file: The lock file path, carried through onto the result.
        fd: The already-locked file descriptor to write the record into.
        clock: The time source stamping the record's start timestamp.
        primitives: Supplies this process's PID for the record.

    Returns:
        An ``ACQUIRED`` result holding the release handle for ``fd``.
    """
    record = InstanceLockRecord(pid=primitives.current_pid(), started_at=clock.now_utc())
    payload = msgspec.json.encode(record)
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    _write_all(fd, payload)
    os.fsync(fd)
    return InstanceLockResult(
        outcome=InstanceLockOutcome.ACQUIRED,
        lock_file=lock_file,
        lock=_HeldInstanceLock(lock_file=lock_file, fd=fd, primitives=primitives),
    )


def _write_all(fd: int, payload: bytes) -> None:
    """Write every byte of ``payload`` to ``fd``, looping over any partial write.

    ``os.write`` may write fewer bytes than requested even for a regular
    file; a single unguarded call would silently truncate the ownership
    record on that rare partial write.

    Args:
        fd: The open, writable file descriptor to write to.
        payload: The encoded bytes to write in full.
    """
    written = 0
    while written < len(payload):
        written += os.write(fd, payload[written:])
