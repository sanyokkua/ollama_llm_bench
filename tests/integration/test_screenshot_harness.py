"""Offscreen screenshot harness for the 08-R §2 screen index (STORY-087).

Renders every screen the screen index enumerates, in both the Light and the Dark
theme, to PNGs in an artifacts directory, and validates the structure of the
mockup-conformance findings report that reviews those captures.

This is a review tool, not a pass/fail pixel gate (ADR-0011): nothing here
asserts that a capture matches its ``mockup.html``. The judgement lives in
``docs/development/mockup_conformance_review.md``, written by a human reading the
captures beside the mockups; these tests only prove the captures were produced
and that the report records a verdict for every checklist item.

Run it for review with ``just screenshots``, which points the artifacts directory
at ``artifacts/screenshots/`` instead of the per-test temporary directory.
"""

import os
from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QLabel, QWidget
import pytest
from pytestqt.qtbot import QtBot

_ARTIFACTS_ENV_VAR: Final[str] = "SCREENSHOT_ARTIFACTS_DIR"


def _artifacts_root(tmp_path: Path) -> Path:
    """Return the directory captures are written to.

    Honours the ``SCREENSHOT_ARTIFACTS_DIR`` environment variable so ``just
    screenshots`` can collect reviewable output, and falls back to the test's own
    temporary directory so the pull-request gate stays hermetic.
    """
    override = os.environ.get(_ARTIFACTS_ENV_VAR)
    if override:
        return Path(override)
    return tmp_path / "screenshots"


def _capture(widget: QWidget, *, path: Path) -> None:
    """Render ``widget`` to a PNG at ``path``.

    Uses ``QImage`` rather than ``QPixmap`` -- pure raster, no platform pixmap
    backend, which is the project's recorded choice for offscreen rendering
    (``ui/results/_internal/charts_tab/painting.py``).
    """
    size = widget.size()
    image = QImage(size.width(), size.height(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path), format=b"PNG"):
        message = f"failed to write capture to {path}"
        raise AssertionError(message)


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_capture_writes_a_decodable_png_of_the_widget_size(qtbot: QtBot, tmp_path: Path) -> None:
    # Arrange
    widget = QLabel("capture me")
    qtbot.addWidget(widget)
    widget.resize(320, 200)
    widget.show()
    qtbot.wait(0)
    destination = _artifacts_root(tmp_path) / "probe.png"

    # Act
    _capture(widget, path=destination)

    # Assert
    assert QImage(str(destination)).size() == widget.size()
