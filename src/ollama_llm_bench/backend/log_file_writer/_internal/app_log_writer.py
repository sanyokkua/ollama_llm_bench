"""The rotating application-log writer implementation (STORY-037-AC-4, §8.1).

Source of truth: ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md`` §8.1 —
``app.log`` rotates when it would reach the size trigger: it is renamed to
``app.log.1``, each existing ``app.log.N`` is renamed to ``app.log.N+1``, a fresh empty
``app.log`` is opened, and ``app.log.<backup_count>`` is discarded when it would be
pushed one step further.
"""

from pathlib import Path
from typing import Final

from ollama_llm_bench.backend.log_file_writer._internal.safe_append import append_line_safely
from ollama_llm_bench.backend.log_file_writer.models import WriteFailureReason, WriteOutcome

DEFAULT_ROTATION_MAX_BYTES: Final[int] = 10 * 1024 * 1024
DEFAULT_ROTATION_BACKUP_COUNT: Final[int] = 5


class AppLogWriterImpl:
    """Appends lines to a size-rotated application-log file."""

    def __init__(self, *, log_file: Path, max_bytes: int, backup_count: int) -> None:
        self._log_file = log_file
        self._max_bytes = max_bytes
        self._backup_count = backup_count

    def write_line(self, text: str) -> WriteOutcome:
        """Rotate first if needed, then append ``text`` as one line (§8.1).

        Args:
            text: The already-formatted application-log record.

        Returns:
            The typed outcome; a rotation failure is reported as
            ``WriteFailureReason.ROTATION_FAILED``.
        """
        projected_line_size = len(text.rstrip("\n").encode("utf-8")) + 1
        if self._log_file.exists():
            current_size = self._log_file.stat().st_size
            if current_size > 0 and current_size + projected_line_size > self._max_bytes:
                rotation_outcome = self._rotate()
                if not rotation_outcome.succeeded:
                    return rotation_outcome
        return append_line_safely(path=self._log_file, line=text)

    def close(self) -> None:
        """No-op: each write is self-contained via its own file descriptor."""

    def _rotate(self) -> WriteOutcome:
        """Shift ``app.log.N`` -> ``app.log.N+1`` and move ``app.log`` -> ``app.log.1``."""
        try:
            oldest_backup = self._backup_path(self._backup_count)
            if oldest_backup.exists():
                oldest_backup.unlink()
            for generation in range(self._backup_count - 1, 0, -1):
                source = self._backup_path(generation)
                if source.exists():
                    source.rename(self._backup_path(generation + 1))
            self._log_file.rename(self._backup_path(1))
        except OSError as exc:
            return WriteOutcome(
                succeeded=False,
                failure_reason=WriteFailureReason.ROTATION_FAILED,
                detail=str(exc),
            )
        return WriteOutcome(succeeded=True)

    def _backup_path(self, generation: int) -> Path:
        return self._log_file.with_name(f"{self._log_file.name}.{generation}")
