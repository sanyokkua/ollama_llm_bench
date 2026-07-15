"""Colocated tests for owner-only filesystem permissions — STORY-037-AC-4."""

from pathlib import Path

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogEventKind
from ollama_llm_bench.backend.log_file_writer import make_app_log_writer, make_run_log_writer
from ollama_llm_bench.backend.log_file_writer.tests.conftest import FakePlatformDetector

_OWNER_ONLY_MODE_SUFFIX = "600"


def test_app_log_file_created_via_factory_is_owner_only(
    tmp_path: Path, fake_platform_detector: FakePlatformDetector
) -> None:
    """Proves: STORY-037-AC-4

    The application-log file created through ``make_app_log_writer`` carries mode
    0600 (owner read/write only).
    """
    writer = make_app_log_writer(platform_detector=fake_platform_detector)

    writer.write_line("application started")

    log_path = fake_platform_detector.app_data_root / "logs" / "app" / "app.log"
    assert oct(log_path.stat().st_mode)[-3:] == _OWNER_ONLY_MODE_SUFFIX


def test_run_log_file_created_via_factory_is_owner_only(
    tmp_path: Path, fake_platform_detector: FakePlatformDetector
) -> None:
    """Proves: STORY-037-AC-4

    The per-run log file created through ``make_run_log_writer`` carries mode 0600
    (owner read/write only).
    """
    writer = make_run_log_writer(platform_detector=fake_platform_detector, run_id="7", unix_ts=100)

    writer.write_event(RunLogEvent(kind=RunLogEventKind.STAGE, timestamp="2026-05-22T00:00:00Z"))

    log_path = fake_platform_detector.app_data_root / "logs" / "run" / "run_7_100.log"
    assert oct(log_path.stat().st_mode)[-3:] == _OWNER_ONLY_MODE_SUFFIX
