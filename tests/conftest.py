"""Root fixtures: filesystem isolation, Hypothesis profiles, the Qt parity rig.

See docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md Sections 5, 10, 12.
"""

from collections.abc import Iterator
import os
from pathlib import Path

from hypothesis import HealthCheck, settings
from PySide6.QtCore import QtMsgType, qInstallMessageHandler
import pytest

settings.register_profile("dev", max_examples=20, deadline=None)
settings.register_profile(
    "release", max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile(
    "ci",
    max_examples=200,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

_QT_WARNING_MESSAGE_TYPES = frozenset({QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg})
"""Message types the parity rig treats as a Qt/PySide warning (07_TESTING_STANDARD.md §12)."""


@pytest.fixture(autouse=True)
def _isolate_filesystem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))


@pytest.fixture(autouse=True)
def _qt_parity_rig(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail a test that emits a Qt/PySide warning, unless explicitly exempted.

    Installs a Qt message handler for the duration of the test that records every
    ``QtWarningMsg``/``QtCriticalMsg`` record instead of letting it print to stderr.
    At teardown, the previous handler is restored and the test fails if any warning
    was captured — unless it carries ``@pytest.mark.allow_qt_warnings``
    (07_TESTING_STANDARD.md §12: "installs a Qt message handler and fails any test
    emitting a Qt or PySide warning, unless the test is explicitly marked").
    """
    captured_messages: list[str] = []

    def _handler(msg_type: QtMsgType, _context: object, message: str) -> None:
        if msg_type in _QT_WARNING_MESSAGE_TYPES:
            captured_messages.append(message)

    previous_handler = qInstallMessageHandler(_handler)
    try:
        yield
    finally:
        qInstallMessageHandler(previous_handler)

    if request.node.get_closest_marker("allow_qt_warnings") is not None:
        return
    assert captured_messages == [], (
        f"Qt/PySide warning(s) captured during test (mark @pytest.mark.allow_qt_warnings "
        f"if intentional): {captured_messages}"
    )
