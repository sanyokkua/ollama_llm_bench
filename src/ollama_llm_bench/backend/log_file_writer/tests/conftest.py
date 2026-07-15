"""Shared fixtures for ``backend/log_file_writer/`` colocated tests."""

from pathlib import Path

import pytest


class FakePlatformDetector:
    """A minimal fake satisfying the ``PlatformDetector`` Protocol structurally."""

    def __init__(self, app_data_root: Path) -> None:
        self._app_data_root = app_data_root

    @property
    def app_data_root(self) -> Path:
        return self._app_data_root


@pytest.fixture
def fake_platform_detector(tmp_path: Path) -> FakePlatformDetector:
    """A fake ``PlatformDetector`` rooted at a fresh ``tmp_path`` per test."""
    return FakePlatformDetector(tmp_path)
