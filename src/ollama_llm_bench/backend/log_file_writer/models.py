"""DTOs for ``backend/log_file_writer/``: the typed write outcome.

Source of truth: ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md`` §8.1,
§8.2, §9. This module never redefines ``RunLogEvent``/``RunLogEventKind`` — those are
owned by ``backend/domain`` and imported, not duplicated.
"""

from enum import StrEnum

import msgspec

__all__: list[str] = [
    "WriteFailureReason",
    "WriteOutcome",
]


class WriteFailureReason(StrEnum):
    """Why a log write failed (§8, §9)."""

    DIRECTORY_NOT_WRITABLE = "directory_not_writable"
    WRITE_FAILED = "write_failed"
    ROTATION_FAILED = "rotation_failed"


class WriteOutcome(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The typed outcome of a log write; a writer never raises for an I/O failure.

    Attributes:
        succeeded: Whether the write (and any rotation it triggered) completed.
        failure_reason: The typed reason on failure; ``None`` on success.
        detail: A human-readable, OS-provided failure detail, or ``""`` on success.
    """

    succeeded: bool
    failure_reason: WriteFailureReason | None = None
    detail: str = ""
