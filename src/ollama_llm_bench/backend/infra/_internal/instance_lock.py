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
        import fcntl  # noqa: PLC0415  # fcntl is POSIX-only; a module-level import breaks import on Windows

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in _LOCK_BUSY_ERRNOS:
                return False
            raise
        return True

    def unlock(self, fd: int) -> None:
        import fcntl  # noqa: PLC0415  # fcntl is POSIX-only; a module-level import breaks import on Windows

        fcntl.flock(fd, fcntl.LOCK_UN)

    def is_pid_alive(self, pid: int) -> bool:
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
        self._primitives.unlock(fd)
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
    """Take, refuse, or reclaim the single-instance lock in ``app_data_root``."""
    lock_file = app_data_root / LOCK_FILENAME
    fd = _open_lock_file(lock_file)
    if primitives.try_lock_exclusive(fd):
        return _claim(lock_file=lock_file, fd=fd, clock=clock, primitives=primitives)
    os.close(fd)
    return InstanceLockResult(outcome=InstanceLockOutcome.ALREADY_RUNNING, lock_file=lock_file)


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
            message=f"Cannot open the instance lock file at '{lock_file}': {exc.strerror}.",
        ) from exc


def _claim(
    *, lock_file: Path, fd: int, clock: Clock, primitives: LockPrimitives
) -> InstanceLockResult:
    """Write this process's ownership record into an already-locked descriptor."""
    record = InstanceLockRecord(pid=primitives.current_pid(), started_at=clock.now_utc())
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, msgspec.json.encode(record))
    os.fsync(fd)
    return InstanceLockResult(
        outcome=InstanceLockOutcome.ACQUIRED,
        lock_file=lock_file,
        lock=_HeldInstanceLock(lock_file=lock_file, fd=fd, primitives=primitives),
    )
