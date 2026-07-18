"""Root fixtures: filesystem isolation, Hypothesis profiles, the Qt parity rig.

See docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md Sections 5, 10, 12.
"""

from collections.abc import Iterator
import os
from pathlib import Path

from hypothesis import HealthCheck, settings
from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication
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


@pytest.fixture(autouse=True, scope="session")
def _warm_up_qt_font_alias_population(qapp: QApplication) -> None:
    """Force Qt's one-time, lazy font-family-alias population before any per-test window.

    Qt's font backend lazily builds its family-alias cache the first time anything in the
    process asks it to resolve a font family it has not yet resolved, and logs a one-time
    "Populating font family aliases..." diagnostic naming whichever family triggered it — the
    cost, and the log line, never recur for the rest of the process regardless of which family
    is requested afterwards (confirmed empirically: only the very first family ever requested
    is named in the message). ``ui/theme``'s declared platform font chains (08-D §7.2)
    intentionally name families that may not exist on the host running the tests — e.g. the
    Linux chain's "Cantarell", a GNOME default rarely present outside a full GNOME desktop —
    and 08-D §7.5 forbids probing ``QFontDatabase`` to sidestep this, by design. Left
    untriggered, the one-time diagnostic instead fires lazily on whichever real-widget test
    happens to be first, in whatever order ``pytest-randomly`` chose, to need real
    font-metric/layout work — and ``_qt_parity_rig`` then (correctly, but unhelpfully) fails
    that unrelated test. This fixture depends on ``qapp`` (also session-scoped), so it runs
    once, as part of the first test's fixture setup that needs a ``QApplication`` at all —
    strictly before that same test's own function-scoped ``_qt_parity_rig`` handler is
    installed (session-scoped dependencies always finish setup before the function-scoped
    fixtures of the test that triggered them).
    """
    QFontMetrics(QFont("Cantarell")).height()


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


@pytest.fixture(autouse=True)
def _isolate_qapp_appearance() -> Iterator[None]:
    """Restore the shared ``QApplication``'s styleSheet/palette after each test.

    Several tests apply a real theme (``make_theme_manager``) straight to the process-wide,
    session-scoped ``qapp`` to exercise genuine Qt styling (e.g. a hard-coded
    ``PlatformKind.LINUX`` font chain) and never restore it. Left unrestored, that appearance
    state leaks into every later test in the session: the leaked stylesheet's declared font
    family is only resolved by Qt lazily, on the first widget afterwards that actually performs
    font-metric/layout work — which then trips Qt's one-time "Populating font family aliases"
    diagnostic and gets misattributed by ``_qt_parity_rig`` to whatever unrelated test happens
    to run next (07_TESTING_STANDARD.md §12). Snapshotting and restoring here removes the leak
    at its source instead of suppressing the symptom on the innocent downstream test.

    Uses ``QApplication.instance()`` rather than the ``qapp`` fixture so a Qt-free test never
    forces a ``QApplication`` into existence.
    """
    app = QApplication.instance()
    stylesheet_before = app.styleSheet() if isinstance(app, QApplication) else None
    palette_before = app.palette() if isinstance(app, QApplication) else None
    yield
    app = QApplication.instance()
    if (
        isinstance(app, QApplication)
        and stylesheet_before is not None
        and palette_before is not None
    ):
        app.setStyleSheet(stylesheet_before)
        app.setPalette(palette_before)
