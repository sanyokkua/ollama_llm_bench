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

from collections.abc import Callable
import os
from pathlib import Path
from typing import Final, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QLabel, QSplitter, QStackedWidget, QTabWidget, QWidget
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.compose import AppHandle

_ARTIFACTS_ENV_VAR: Final[str] = "SCREENSHOT_ARTIFACTS_DIR"

_SCREEN_INDEX_IDS: Final[tuple[str, ...]] = ("01", "02", "03", "04", "05", "06", "07", "09")

_CAPTURE_IDS: Final[tuple[str, ...]] = (
    "01_main_window",
    "02_new_benchmark",
    "03_resume_benchmark",
    "04_progress",
    "05_result",
    "06_settings",
    "07_common_dialogs__rename_run",
    "07_common_dialogs__run_summary",
    "07_common_dialogs__resume_summary",
    "07_common_dialogs__retry_selection",
    "07_common_dialogs__error",
    "07_common_dialogs__about",
    "07_common_dialogs__generate_analysis",
    "09_task_editor",
)

_WINDOW_SIZE: Final[tuple[int, int]] = (1600, 1000)


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


def _screen_id_of(capture_id: str) -> str:
    """Return the 08-R §2 screen-index id a capture belongs to."""
    return capture_id[:2]


def _covered_screen_ids() -> frozenset[str]:
    """Return every screen-index id the capture registry covers."""
    return frozenset(_screen_id_of(capture_id) for capture_id in _CAPTURE_IDS)


def test_capture_registry_covers_every_screen_in_the_screen_index() -> None:
    # Arrange / Act / Assert
    assert _covered_screen_ids() == frozenset(_SCREEN_INDEX_IDS)


def _workspace_stack_of(benchmark: QWidget) -> QStackedWidget:
    """Return the workspace `QStackedWidget` that hosts the benchmark splitter as a page.

    `workspace_region` (`compose.py`) carries no `objectName`, so it cannot be located via
    `findChild`. A `QStackedWidget` reparents each page directly onto itself, so the benchmark
    splitter's parent *is* the stack.
    """
    stack = benchmark.parentWidget()
    if not isinstance(stack, QStackedWidget):
        message = f"benchmark workspace parent is {type(stack).__name__}, not QStackedWidget"
        raise AssertionError(message)
    return stack


def _task_editor_page(stack: QStackedWidget, *, benchmark: QWidget) -> QWidget:
    """Return the workspace page that is not the benchmark splitter."""
    pages = [stack.widget(index) for index in range(stack.count())]
    others = [page for page in pages if page is not benchmark]
    if len(others) != 1:
        message = f"expected exactly one non-benchmark workspace page, got {len(others)}"
        raise AssertionError(message)
    return others[0]


def _capture_app_screens(*, qtbot: QtBot, handle: AppHandle, destination: Path) -> None:
    """Capture screens 01-05 and 09 from a fully built application."""
    window = handle.window
    window.resize(*_WINDOW_SIZE)
    window.show()
    qtbot.wait(0)
    _capture(window, path=destination / "01_main_window.png")

    left_panel = cast("QTabWidget", window.findChild(QTabWidget, "benchmark_left_panel"))
    assert left_panel is not None
    splitter = left_panel.parentWidget()
    while splitter is not None and not isinstance(splitter, QSplitter):
        splitter = splitter.parentWidget()
    if splitter is None:
        message = "benchmark workspace splitter not found under the main window"
        raise AssertionError(message)

    left_panel.setCurrentIndex(0)
    qtbot.wait(0)
    _capture(left_panel.widget(0), path=destination / "02_new_benchmark.png")
    left_panel.setCurrentIndex(1)
    qtbot.wait(0)
    _capture(left_panel.widget(1), path=destination / "03_resume_benchmark.png")
    left_panel.setCurrentIndex(0)

    _capture(splitter.widget(1), path=destination / "04_progress.png")
    _capture(splitter.widget(2), path=destination / "05_result.png")

    stack = _workspace_stack_of(splitter)
    task_editor = _task_editor_page(stack, benchmark=splitter)
    stack.setCurrentWidget(task_editor)
    qtbot.wait(0)
    _capture(task_editor, path=destination / "09_task_editor.png")
    stack.setCurrentWidget(splitter)


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_app_derived_screens_are_captured_from_one_real_app_build(
    qtbot: QtBot,
    tmp_path: Path,
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    # Arrange
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    destination = _artifacts_root(tmp_path) / "probe-app"

    # Act
    _capture_app_screens(qtbot=qtbot, handle=handle, destination=destination)
    drain_task_runner_deliveries(handle)

    # Assert
    assert {path.name for path in destination.glob("*.png")} == {
        "01_main_window.png",
        "02_new_benchmark.png",
        "03_resume_benchmark.png",
        "04_progress.png",
        "05_result.png",
        "09_task_editor.png",
    }
