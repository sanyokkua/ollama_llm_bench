"""DTOs owned by ``backend/infra/``: the single-instance lock record and outcome.

Source of truth: ``docs/v3_specification/12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md``
§5 (the lock file records the owning PID and a start timestamp) and §6 (a later
instance on the same data directory refuses to run).
"""

from enum import StrEnum
from pathlib import Path

import msgspec

from ollama_llm_bench.backend.domain.models import Iso8601Utc
from ollama_llm_bench.backend.infra.protocols import InstanceLockHandle

__all__: list[str] = [
    "InstanceLockHandle",
    "InstanceLockOutcome",
    "InstanceLockRecord",
    "InstanceLockResult",
]


class InstanceLockOutcome(StrEnum):
    """The two outcomes of attempting to take the single-instance lock."""

    ACQUIRED = "acquired"
    ALREADY_RUNNING = "already_running"


class InstanceLockRecord(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """What ``<app-data>/.instance.lock`` stores about its owning process."""

    pid: int
    started_at: Iso8601Utc


class InstanceLockResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The outcome of one attempt to take the single-instance lock.

    Attributes:
        outcome: Whether the lock was taken or a live owner already holds it.
        lock_file: The lock file the attempt targeted, whatever the outcome.
        lock: The release handle when ``outcome`` is ``ACQUIRED``; ``None`` when
            the attempt was refused.
        holder: The record read off a refused lock, naming the live owner;
            ``None`` when the lock was acquired or the record was unreadable.
    """

    outcome: InstanceLockOutcome
    lock_file: Path
    lock: InstanceLockHandle | None = None
    holder: InstanceLockRecord | None = None
