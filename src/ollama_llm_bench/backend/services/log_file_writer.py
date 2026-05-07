"""LogFileWriter — writes structured benchmark log entries to per-run files on disk.

Each run ID gets its own file under ``{app_root}/logs/``.  The directory is
created lazily on the first ``write_entry`` call so that constructing a
``LogFileWriter`` has no filesystem side effects.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import IO, Final

from ollama_llm_bench.backend.core.models import LogEntryType

logger = logging.getLogger(__name__)

_LOG_DIR_NAME: Final[str] = "logs"
_TIMESTAMP_FMT: Final[str] = "%H:%M:%S"


class LogFileWriter:
    """Write structured log entries to per-run files under ``{app_root}/logs/``.

    Files are opened lazily on the first ``write_entry`` call for a given run
    ID, so constructing this class never touches the filesystem.  Each run ID
    maps to an independent file handle, allowing multiple concurrent runs to be
    tracked without interference.

    All I/O errors are caught internally and logged as warnings so that the
    benchmark pipeline's no-throw contract is preserved.
    """

    def __init__(self, *, app_root: Path) -> None:
        self._log_dir: Path = app_root / _LOG_DIR_NAME
        self._handles: dict[int, IO[str]] = {}
        self._log_paths: dict[int, Path] = {}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _open_handle(self, run_id: int) -> None:
        """Create the log directory and open a new file handle for *run_id*.

        Args:
            run_id: Identifier of the benchmark run whose file is being opened.
        """
        self._log_dir.mkdir(parents=True, exist_ok=True)
        filename: str = f"benchmark_{run_id}_{int(time.time())}.log"
        log_path: Path = self._log_dir / filename
        self._log_paths[run_id] = log_path
        self._handles[run_id] = log_path.open("w", encoding="utf-8", buffering=1)

    # ------------------------------------------------------------------
    # Public API (implements LogFileWriterApi Protocol)
    # ------------------------------------------------------------------

    def write_entry(self, run_id: int, entry_type: LogEntryType, content: str) -> None:
        """Append one structured log line for the given run.

        Opens a new file for *run_id* on the first call.  Subsequent calls for
        the same *run_id* append to the same file.  Any ``OSError`` is caught,
        logged as a warning, and not propagated.

        Args:
            run_id: Identifier of the benchmark run.
            entry_type: Semantic category of the entry (used as a field label).
            content: Human-readable content for this log line.
        """
        try:
            if run_id not in self._handles:
                self._open_handle(run_id)
            timestamp: str = datetime.now().strftime(_TIMESTAMP_FMT)
            line: str = f"[{timestamp}] [{entry_type}] {content}\n"
            self._handles[run_id].write(line)
        except OSError:
            logger.warning(
                "log_write_failed",
                extra={"run_id": run_id, "entry_type": entry_type},
            )

    def get_log_path(self, run_id: int) -> Path:
        """Return the filesystem path of the log file for *run_id*.

        Args:
            run_id: Identifier of the benchmark run.

        Returns:
            Absolute path to the log file.

        Raises:
            KeyError: If no log file has been opened for *run_id* yet.
                      Call ``write_entry`` at least once before calling this method.
        """
        if run_id not in self._log_paths:
            raise KeyError(f"No log path for run_id={run_id}. Call write_entry first.")
        return self._log_paths[run_id]

    def close(self, run_id: int) -> None:
        """Flush and close the log file for *run_id*.

        Silently does nothing if *run_id* has no open handle (idempotent).

        Args:
            run_id: Identifier of the benchmark run whose file should be closed.
        """
        if run_id not in self._handles:
            return
        handle: IO[str] = self._handles[run_id]
        handle.flush()
        handle.close()
        del self._handles[run_id]
