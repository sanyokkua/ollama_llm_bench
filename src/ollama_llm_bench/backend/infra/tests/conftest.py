"""Shared fixtures for ``backend/infra/`` colocated tests.

Provides a fake ``PlatformDetector`` (structurally satisfying the narrow Protocol declared
in ``backend/infra/protocols.py``) and a logging-state reset fixture so one test's
``configure_logging`` call never leaks handlers into another test.
"""

from collections.abc import Iterator
import logging
from typing import Final

import pytest

from ollama_llm_bench.backend.infra._internal.logging_setup import (
    _INSTALLED_MARKER_ATTR,
    _QUEUE_LISTENER_ATTR,
)
from ollama_llm_bench.backend.infra.protocols import InstanceLockHandle


class FakePlatformDetector:
    """A minimal fake satisfying the ``PlatformDetector`` Protocol structurally."""

    def __init__(self, app_data_root) -> None:  # type: ignore[no-untyped-def]
        self._app_data_root = app_data_root

    @property
    def app_data_root(self):  # type: ignore[no-untyped-def]
        return self._app_data_root


@pytest.fixture
def fake_platform_detector(tmp_path):  # type: ignore[no-untyped-def]
    """A fake ``PlatformDetector`` rooted at a fresh ``tmp_path`` per test."""
    return FakePlatformDetector(tmp_path)


FAKE_NOW_UTC: Final[str] = "2026-07-29T12:00:00Z"


class FakeClock:
    """A ``Clock`` returning a fixed instant, so timestamp assertions are exact."""

    def now_utc(self) -> str:
        return FAKE_NOW_UTC

    def monotonic_ms(self) -> int:
        return 0


@pytest.fixture
def fake_clock() -> FakeClock:
    """A ``Clock`` frozen at ``FAKE_NOW_UTC``."""
    return FakeClock()


@pytest.fixture
def held_locks() -> Iterator[list[InstanceLockHandle]]:
    """Collect acquired lock handles and release them all after the test.

    An acquired advisory lock plus its open file descriptor is process-global
    state; without this teardown one test's lock would refuse the next test's
    acquisition on a shared path and leak a file descriptor.
    """
    handles: list[InstanceLockHandle] = []
    yield handles
    for handle in handles:
        handle.release()


@pytest.fixture(autouse=True)
def _reset_app_logging_state() -> Iterator[None]:
    """Tear down any ``app`` logger handlers/listener installed by a test.

    ``configure_logging`` is idempotent-safe against a second call within the same
    test, but without this fixture, a handler installed by one test (writing to that
    test's own ``tmp_path``) would remain attached to the shared stdlib ``app`` logger
    for the next test, since the stdlib logging module's logger registry is
    process-global, not reset between tests.
    """
    yield
    app_logger = logging.getLogger("app")
    listener = getattr(app_logger, _QUEUE_LISTENER_ATTR, None)
    if listener is not None:
        listener.stop()
    for handler in list(app_logger.handlers):
        app_logger.removeHandler(handler)
        handler.close()
    if hasattr(app_logger, _INSTALLED_MARKER_ATTR):
        delattr(app_logger, _INSTALLED_MARKER_ATTR)
