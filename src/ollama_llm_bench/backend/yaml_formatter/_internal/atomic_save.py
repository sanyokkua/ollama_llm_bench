"""Write-temp-then-fsync-then-rename atomic save (`12_YAML_FORMATTER.md` §6.6, §8)."""

import os
from pathlib import Path
import tempfile
from typing import TextIO

from ollama_llm_bench.backend.yaml_formatter.models import SaveFailureReason, SaveResult


def _write_and_fsync(handle: TextIO, text: str) -> None:
    """Write the full buffer and force it to stable storage.

    A single, separately named step so a test can simulate a mid-write
    failure (a disk-full condition, YF-16) without touching real disk I/O.
    """
    handle.write(text)
    handle.flush()
    os.fsync(handle.fileno())


def atomic_write(*, text: str, target_path: str) -> SaveResult:
    """Commit ``text`` to ``target_path`` by the write-temp-then-rename pattern (§6.6).

    Args:
        text: The full serialized file content to write.
        target_path: The absolute path of the ``.yaml``/``.yml`` file to write.

    Returns:
        ``SaveResult(succeeded=True)`` on success. On any failure,
        ``target_path`` is left byte-for-byte unchanged, no temporary file
        remains, and the typed failure reason is reported.
    """
    target = Path(target_path)
    try:
        descriptor, tmp_name = tempfile.mkstemp(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
        )
    except OSError as exc:
        return SaveResult(
            succeeded=False,
            failure_reason=SaveFailureReason.DIRECTORY_NOT_WRITABLE,
            detail=str(exc),
        )

    tmp_path = Path(tmp_name)
    try:
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                _write_and_fsync(handle, text)
        except OSError as exc:
            return SaveResult(
                succeeded=False,
                failure_reason=SaveFailureReason.WRITE_FAILED,
                detail=str(exc),
            )

        try:
            os.replace(tmp_path, target)
        except OSError as exc:
            return SaveResult(
                succeeded=False,
                failure_reason=SaveFailureReason.RENAME_FAILED,
                detail=str(exc),
            )
    finally:
        tmp_path.unlink(missing_ok=True)

    return SaveResult(succeeded=True)
