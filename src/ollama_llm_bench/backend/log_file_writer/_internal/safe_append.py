"""Append-one-line-safely primitive shared by every writer in this module.

Source of truth: ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md`` §9
(owner-only permission set at creation, never a follow-up ``chmod``) and EC-FL-9 (a
disk-full mid-write must leave no partial line on disk).
"""

import os
from pathlib import Path

from ollama_llm_bench.backend.log_file_writer.models import WriteFailureReason, WriteOutcome

_OWNER_ONLY_MODE = 0o600


def _write_and_fsync(file_descriptor: int, data: bytes) -> None:
    """Write the full buffer and force it to stable storage.

    A single, separately named step so a test can simulate a mid-write failure (a
    disk-full condition, EC-FL-9) without touching real disk I/O.
    """
    os.write(file_descriptor, data)
    os.fsync(file_descriptor)


def append_line_safely(*, path: Path, line: str) -> WriteOutcome:
    """Append one normalized, newline-terminated line to ``path``.

    Creates the parent directory tree and the file if either is missing. The file's
    mode is applied atomically at creation via ``os.open``'s ``mode`` argument — never
    as a follow-up ``chmod`` — so there is no window in which the file is readable by
    others (§9). A write/fsync failure truncates the file back to its pre-write size
    before closing it, so no partial line is ever left on disk (EC-FL-9).

    Args:
        path: The destination log file.
        line: The line to append; normalized to end with exactly one ``\\n``.

    Returns:
        ``WriteOutcome(succeeded=True)`` on success. On any failure, ``path`` is left
        exactly as it was before the call and the typed failure reason is reported.
    """
    normalized_line = line.rstrip("\n") + "\n"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return WriteOutcome(
            succeeded=False,
            failure_reason=WriteFailureReason.DIRECTORY_NOT_WRITABLE,
            detail=str(exc),
        )

    try:
        file_descriptor = os.open(
            str(path), os.O_CREAT | os.O_APPEND | os.O_WRONLY, _OWNER_ONLY_MODE
        )
    except OSError as exc:
        return WriteOutcome(
            succeeded=False,
            failure_reason=WriteFailureReason.DIRECTORY_NOT_WRITABLE,
            detail=str(exc),
        )

    try:
        pre_write_size = os.fstat(file_descriptor).st_size
        try:
            _write_and_fsync(file_descriptor, normalized_line.encode("utf-8"))
        except OSError as exc:
            os.ftruncate(file_descriptor, pre_write_size)
            return WriteOutcome(
                succeeded=False,
                failure_reason=WriteFailureReason.WRITE_FAILED,
                detail=str(exc),
            )
    finally:
        os.close(file_descriptor)

    return WriteOutcome(succeeded=True)
