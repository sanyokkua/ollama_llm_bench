"""Derive the two log-stream paths from a ``PlatformDetector``'s resolved app-data root.

Source of truth: ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md`` §2
(directory tree) and §8.1 (application-log rotation policy). This module composes over
``PlatformDetector.app_data_root`` — it never re-detects the OS itself (STORY-005 owns
OS classification).
"""

from pathlib import Path

from ollama_llm_bench.backend.infra.protocols import PlatformDetector

_APP_LOG_SUBDIR = "app"
_RUN_LOG_SUBDIR = "run"
_APP_LOG_FILENAME = "app.log"


def app_log_dir(platform_detector: PlatformDetector) -> Path:
    """Return ``<app_data_root>/logs/app/``."""
    return platform_detector.app_data_root / "logs" / _APP_LOG_SUBDIR


def app_log_path(platform_detector: PlatformDetector) -> Path:
    """Return ``<app_data_root>/logs/app/app.log``."""
    return app_log_dir(platform_detector) / _APP_LOG_FILENAME


def run_log_dir(platform_detector: PlatformDetector) -> Path:
    """Return ``<app_data_root>/logs/run/``."""
    return platform_detector.app_data_root / "logs" / _RUN_LOG_SUBDIR


def run_log_path(platform_detector: PlatformDetector, *, run_id: str, unix_ts: int) -> Path:
    """Return ``<app_data_root>/logs/run/run_<run_id>_<unix_ts>.log``."""
    return run_log_dir(platform_detector) / f"run_{run_id}_{unix_ts}.log"
