"""Startup run-log retention — both §5 rules applied together (STORY-088-AC-2).

Source of truth: ``docs/v3_specification/12_Quality_and_NFRs/07_RESOURCE_LIMITS.md``
§5 ("At most 200 files; none older than 90 days ... The age rule and the count
rule are both applied; whichever removes more files governs") and §7 (enforced by
"Startup cleanup; integration test").
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ollama_llm_bench.backend.log_file_writer import cleanup_run_logs

_KEEP_COUNT = 200
_MAX_AGE_DAYS = 90
_DAY_SECONDS = 86_400
_HOUR_SECONDS = 3_600
_NOW_UNIX_TS = 1_800_000_000
_AGE_CUTOFF_TS = _NOW_UNIX_TS - _MAX_AGE_DAYS * _DAY_SECONDS


class _FakePlatformDetector:
    """A minimal fake satisfying the ``PlatformDetector`` Protocol structurally."""

    def __init__(self, app_data_root: Path) -> None:
        self._app_data_root = app_data_root

    @property
    def app_data_root(self) -> Path:
        return self._app_data_root


class _FakeClock:
    """A ``Clock`` pinned to ``_NOW_UNIX_TS`` so the 90-day cutoff is exact."""

    def now_utc(self) -> str:
        return datetime.fromtimestamp(_NOW_UNIX_TS, UTC).isoformat()

    def monotonic_ms(self) -> int:
        return 0


@pytest.fixture
def run_log_dir(tmp_path: Path) -> Path:
    """A fresh, empty ``<app-data>/logs/run/`` directory."""
    directory = tmp_path / "logs" / "run"
    directory.mkdir(parents=True)
    return directory


def _seed(run_log_dir: Path, *, count: int, first_run_id: int, first_ts: int, step: int) -> None:
    """Create ``count`` run-log files with timestamps ``first_ts + i * step``."""
    for offset in range(count):
        path = run_log_dir / f"run_{first_run_id + offset}_{first_ts + offset * step}.log"
        path.write_text("x", encoding="utf-8")


def _surviving_timestamps(run_log_dir: Path) -> set[int]:
    """Return the encoded timestamp of every run log still on disk."""
    return {int(path.stem.rsplit("_", 1)[1]) for path in run_log_dir.glob("run_*.log")}


def test_startup_prune_caps_run_logs_to_200_files_and_90_days(
    tmp_path: Path, run_log_dir: Path
) -> None:
    """Proves: STORY-088-AC-2

    Given a directory holding more than 200 run logs of which 20 predate the
    90-day cutoff, the prune leaves at most 200 files, all at most 90 days old,
    having deleted oldest-timestamp-first every file that violated either rule
    and retained every file that violated neither — the age rule governing here
    because it removes more (20) than the count rule would (10).
    """
    # Arrange
    _seed(
        run_log_dir,
        count=20,
        first_run_id=1,
        first_ts=_AGE_CUTOFF_TS - 20 * _DAY_SECONDS,
        step=_DAY_SECONDS,
    )
    _seed(
        run_log_dir,
        count=190,
        first_run_id=101,
        first_ts=_AGE_CUTOFF_TS + _HOUR_SECONDS,
        step=_HOUR_SECONDS,
    )
    expected_survivors = {_AGE_CUTOFF_TS + offset * _HOUR_SECONDS for offset in range(1, 191)}

    # Act
    deleted_count = cleanup_run_logs(
        platform_detector=_FakePlatformDetector(tmp_path),
        clock=_FakeClock(),
        keep_count=_KEEP_COUNT,
        max_age_days=_MAX_AGE_DAYS,
    )

    # Assert
    assert (deleted_count, _surviving_timestamps(run_log_dir)) == (20, expected_survivors)


def test_startup_prune_lets_the_count_rule_govern_when_it_removes_more(
    tmp_path: Path, run_log_dir: Path
) -> None:
    """Proves: STORY-088-AC-2

    The converse direction of §5's "whichever removes more files governs": with
    210 files of which only 3 predate the cutoff, the count rule's 10 deletions
    govern, and those 10 include the 3 expired files.
    """
    # Arrange
    _seed(
        run_log_dir,
        count=3,
        first_run_id=1,
        first_ts=_AGE_CUTOFF_TS - 3 * _DAY_SECONDS,
        step=_DAY_SECONDS,
    )
    _seed(
        run_log_dir,
        count=207,
        first_run_id=101,
        first_ts=_AGE_CUTOFF_TS + _HOUR_SECONDS,
        step=_HOUR_SECONDS,
    )
    expected_survivors = {_AGE_CUTOFF_TS + offset * _HOUR_SECONDS for offset in range(8, 208)}

    # Act
    deleted_count = cleanup_run_logs(
        platform_detector=_FakePlatformDetector(tmp_path),
        clock=_FakeClock(),
        keep_count=_KEEP_COUNT,
        max_age_days=_MAX_AGE_DAYS,
    )

    # Assert
    assert (deleted_count, _surviving_timestamps(run_log_dir)) == (10, expected_survivors)
