"""Shared fixtures for ``backend/log_file_writer/`` colocated tests."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

FAKE_NOW_UNIX_TS: Final[int] = 1_700_100_000
"""~28 hours after the ``base_ts`` the count-rule tests seed, so nothing in
those fixtures is age-expired and the count rule is measured in isolation."""


class FakePlatformDetector:
    """A minimal fake satisfying the ``PlatformDetector`` Protocol structurally."""

    def __init__(self, app_data_root: Path) -> None:
        self._app_data_root = app_data_root

    @property
    def app_data_root(self) -> Path:
        return self._app_data_root


class FakeClock:
    """A ``Clock`` pinned to ``FAKE_NOW_UNIX_TS`` so age assertions are exact."""

    def now_utc(self) -> str:
        return datetime.fromtimestamp(FAKE_NOW_UNIX_TS, UTC).isoformat()

    def monotonic_ms(self) -> int:
        return 0


@pytest.fixture
def fake_platform_detector(tmp_path: Path) -> FakePlatformDetector:
    """A fake ``PlatformDetector`` rooted at a fresh ``tmp_path`` per test."""
    return FakePlatformDetector(tmp_path)


@pytest.fixture
def fake_clock() -> FakeClock:
    """A ``Clock`` fake pinned just after the run-log timestamps these tests seed."""
    return FakeClock()
