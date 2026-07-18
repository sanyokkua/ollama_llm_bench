"""Shared ``ui/`` test-tree fixture: restores QApplication-level appearance state.

See docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md Section 12. This
conftest.py sits above every colocated ``ui/**/tests/`` directory so the fixture below applies
regardless of which feature module's test suite runs — it is not visible to
``tests/integration/`` (that tree gets the equivalent fixture from the root ``tests/conftest.py``
directly, since a conftest.py only applies to descendants of its own directory).
"""

from collections.abc import Iterator

from PySide6.QtWidgets import QApplication
import pytest


@pytest.fixture(autouse=True)
def _isolate_qapp_appearance() -> Iterator[None]:
    """Restore the shared ``QApplication``'s styleSheet/palette after each test.

    Several colocated ``ui/**/tests/`` suites apply a real theme (``make_theme_manager``)
    straight to the process-wide, session-scoped ``qapp`` to exercise genuine Qt styling (e.g.
    a hard-coded ``PlatformKind.LINUX`` font chain) and never restore it. Left unrestored, that
    appearance state leaks into every later test in the session: the leaked stylesheet's
    declared font family is only resolved by Qt lazily, on the first widget afterwards that
    actually performs font-metric/layout work — which then trips Qt's one-time "Populating font
    family aliases" diagnostic and gets misattributed by ``_qt_parity_rig``
    (``tests/conftest.py``) to whatever unrelated, later test happens to run next
    (07_TESTING_STANDARD.md §12). Snapshotting and restoring here removes the leak at its
    source instead of suppressing the symptom on the innocent downstream test.

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
