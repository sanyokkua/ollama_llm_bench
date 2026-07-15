"""Colocated tests for the startup run-log count-based cleanup — STORY-037-AC-2."""

from pathlib import Path

from ollama_llm_bench.backend.log_file_writer import cleanup_run_logs
from ollama_llm_bench.backend.log_file_writer._internal.run_log_cleanup import (
    cleanup_run_logs_by_count,
)
from ollama_llm_bench.backend.log_file_writer.tests.conftest import FakePlatformDetector

_KEEP_COUNT = 200
_SEED_COUNT = 205
_EXPECTED_DELETED_COUNT = _SEED_COUNT - _KEEP_COUNT


def test_startup_cleanup_prunes_oldest_to_200(
    tmp_path: Path, fake_platform_detector: FakePlatformDetector
) -> None:
    """Proves: STORY-037-AC-2

    Given more than 200 run-log files, cleanup deletes the oldest (by embedded
    timestamp) until exactly 200 remain, and leaves an unrelated file untouched.
    Covers EC-FL-10.
    """
    run_log_dir = fake_platform_detector.app_data_root / "logs" / "run"
    run_log_dir.mkdir(parents=True)
    base_ts = 1_700_000_000
    for offset in range(_SEED_COUNT):
        (run_log_dir / f"run_{offset}_{base_ts + offset}.log").write_text("x", encoding="utf-8")
    unrelated_file = run_log_dir / "notes.txt"
    unrelated_file.write_text("keep me", encoding="utf-8")

    deleted_count = cleanup_run_logs(platform_detector=fake_platform_detector)

    remaining_run_logs = sorted(run_log_dir.glob("run_*.log"))
    assert deleted_count == _EXPECTED_DELETED_COUNT
    assert len(remaining_run_logs) == _KEEP_COUNT
    assert unrelated_file.exists()
    remaining_offsets = {int(p.stem.split("_")[1]) for p in remaining_run_logs}
    assert remaining_offsets == set(range(_EXPECTED_DELETED_COUNT, _SEED_COUNT))


def test_cleanup_on_missing_directory_returns_zero(tmp_path: Path) -> None:
    """Proves: STORY-037-AC-2

    A ``logs/run/`` directory that does not yet exist is not an error — cleanup
    reports zero deletions.
    """
    missing_dir = tmp_path / "does" / "not" / "exist"

    deleted_count = cleanup_run_logs_by_count(run_log_dir=missing_dir, keep_count=_KEEP_COUNT)

    assert deleted_count == 0


def test_cleanup_skips_non_file_entries(tmp_path: Path) -> None:
    """Proves: STORY-037-AC-2

    A subdirectory whose name happens to match the run-log filename template is
    skipped — only regular files are considered for deletion.
    """
    run_log_dir = tmp_path / "run"
    run_log_dir.mkdir()
    (run_log_dir / "run_1_100.log").mkdir()

    deleted_count = cleanup_run_logs_by_count(run_log_dir=run_log_dir, keep_count=0)

    assert deleted_count == 0
    assert (run_log_dir / "run_1_100.log").is_dir()
