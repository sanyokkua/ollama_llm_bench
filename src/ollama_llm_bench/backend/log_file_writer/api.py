"""Public factories for ``backend/log_file_writer/`` (`01_MODULE_INVENTORY.md` §4.5)."""

from typing import TYPE_CHECKING

import icontract

if TYPE_CHECKING:
    from pathlib import Path

from ollama_llm_bench.backend.infra import app_log_path, run_log_dir, run_log_path
from ollama_llm_bench.backend.infra.protocols import PlatformDetector
from ollama_llm_bench.backend.log_file_writer._internal.app_log_writer import (
    DEFAULT_ROTATION_BACKUP_COUNT,
    DEFAULT_ROTATION_MAX_BYTES,
    AppLogWriterImpl,
)
from ollama_llm_bench.backend.log_file_writer._internal.run_log_cleanup import (
    DEFAULT_RUN_LOG_KEEP_COUNT,
    cleanup_run_logs_by_count,
)
from ollama_llm_bench.backend.log_file_writer._internal.run_log_writer import RunLogWriterImpl
from ollama_llm_bench.backend.log_file_writer.protocols import AppLogWriter, RunLogWriter

__all__: list[str] = [
    "cleanup_run_logs",
    "make_app_log_writer",
    "make_run_log_writer",
]


@icontract.require(lambda max_bytes: max_bytes > 0, "max_bytes must be positive")
@icontract.require(lambda backup_count: backup_count >= 1, "backup_count must be at least 1")
@icontract.ensure(lambda result: result is not None)
def make_app_log_writer(
    *,
    platform_detector: PlatformDetector,
    max_bytes: int = DEFAULT_ROTATION_MAX_BYTES,
    backup_count: int = DEFAULT_ROTATION_BACKUP_COUNT,
) -> AppLogWriter:
    """Construct the rotating application-log writer (§4.1, §8.1).

    Args:
        platform_detector: Supplies the resolved application-data root.
        max_bytes: The rotation trigger size in bytes (10 MB default).
        backup_count: The number of rotated backups to retain (5 default).

    Returns:
        An ``AppLogWriter`` targeting ``<app-data>/logs/app/app.log``.
    """
    log_file: Path = app_log_path(platform_detector)
    return AppLogWriterImpl(log_file=log_file, max_bytes=max_bytes, backup_count=backup_count)


@icontract.require(lambda run_id: len(run_id) > 0, "run_id must be non-empty")
@icontract.require(lambda unix_ts: unix_ts >= 0, "unix_ts must be non-negative")
@icontract.ensure(lambda result: result is not None)
def make_run_log_writer(
    *, platform_detector: PlatformDetector, run_id: str, unix_ts: int
) -> RunLogWriter:
    """Construct a single run's dedicated event-log writer (§4.2).

    Args:
        platform_detector: Supplies the resolved application-data root.
        run_id: The run identifier the log file is named after.
        unix_ts: The run's start time as a Unix timestamp in seconds.

    Returns:
        A ``RunLogWriter`` targeting
        ``<app-data>/logs/run/run_<run_id>_<unix_ts>.log``.
    """
    log_file: Path = run_log_path(platform_detector, run_id=run_id, unix_ts=unix_ts)
    return RunLogWriterImpl(log_file=log_file)


@icontract.require(lambda keep_count: keep_count >= 0, "keep_count must be non-negative")
@icontract.ensure(lambda result: result >= 0)
def cleanup_run_logs(
    *, platform_detector: PlatformDetector, keep_count: int = DEFAULT_RUN_LOG_KEEP_COUNT
) -> int:
    """Prune ``<app-data>/logs/run/`` down to ``keep_count`` files, oldest first (§8.2).

    Only the count rule is applied — the age and orphan rules are out of scope.

    Args:
        platform_detector: Supplies the resolved application-data root.
        keep_count: How many run-log files to retain (200 default).

    Returns:
        The number of files deleted.
    """
    log_dir: Path = run_log_dir(platform_detector)
    return cleanup_run_logs_by_count(run_log_dir=log_dir, keep_count=keep_count)
