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
import re
from typing import Final, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog, QLabel, QSplitter, QStackedWidget, QTabWidget, QWidget
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.clipboard import make_clipboard
from ollama_llm_bench.adapters.file_system_actions import make_file_system_actions
from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.settings_dialog import (
    SettingsDialogCollaborators,
    make_settings_dialog,
)
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway
from tests.integration.common_dialog_builders import build_common_dialogs

_ARTIFACTS_ENV_VAR: Final[str] = "SCREENSHOT_ARTIFACTS_DIR"

_PROVIDER_ID: Final[str] = "550e8400-e29b-41d4-a716-446655440000"
_MODEL_NAME: Final[str] = "llama3.1:8b"
_RUN_ID: Final[int] = 1
_TIMESTAMP: Final[str] = "2026-08-05T12:00:00Z"

_DIALOG_SIZE: Final[tuple[int, int]] = (900, 700)

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


def _artifacts_root(tmp_path: Path, *, use_override: bool = True) -> Path:
    """Return the directory captures are written to.

    Honours the ``SCREENSHOT_ARTIFACTS_DIR`` environment variable so ``just
    screenshots`` can collect reviewable output, and falls back to the test's own
    temporary directory so the pull-request gate stays hermetic. Pass
    ``use_override=False`` to always use ``tmp_path`` regardless of the
    environment variable -- for test-fixture captures (the probe tests) that
    are not part of the reviewable deliverable and must never land alongside
    it in ``artifacts/screenshots/``.
    """
    override = os.environ.get(_ARTIFACTS_ENV_VAR) if use_override else None
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
    destination = _artifacts_root(tmp_path, use_override=False) / "probe.png"

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

    left_panel = cast("QTabWidget | None", window.findChild(QTabWidget, "benchmark_left_panel"))
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

    stack = cast("QStackedWidget | None", window.findChild(QStackedWidget, "workspace_region"))
    assert stack is not None
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
    destination = _artifacts_root(tmp_path, use_override=False) / "probe-app"

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


def _build_settings_dialog(*, qtbot: QtBot) -> QDialog:
    """Construct the Settings dialog standalone, shown but never exec()'d.

    ``compose.py`` builds this dialog lazily inside ``_open_settings()`` and
    calls ``.exec()``, which would block the whole suite. Building it here
    instead means the screenshot harness never opens a real modal.
    """
    collaborators = SettingsDialogCollaborators(
        gateway=FakeSettingsGateway(),
        event_bus=make_qt_event_bus_deliverer(),
        native_pickers=FakeNativePickers(),
        clipboard=make_clipboard(),
        file_system_actions=make_file_system_actions(),
        notifications=FakeNotificationService(),
    )
    dialog = make_settings_dialog(collaborators=collaborators)
    qtbot.addWidget(dialog)
    dialog.resize(*_DIALOG_SIZE)
    dialog.show()
    qtbot.wait(0)
    return dialog


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_settings_dialog_is_constructed_standalone_without_exec(qtbot: QtBot) -> None:
    # Arrange / Act
    dialog = _build_settings_dialog(qtbot=qtbot)

    # Assert
    assert dialog.isVisible()


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_every_shared_modal_dialog_is_constructed_for_capture(qtbot: QtBot) -> None:
    # Arrange
    expected = frozenset(capture_id for capture_id in _CAPTURE_IDS if capture_id.startswith("07_"))

    # Act
    dialogs = build_common_dialogs(qtbot=qtbot)

    # Assert
    assert frozenset(dialogs) == expected


_EXPECTED_CAPTURES: Final[frozenset[str]] = frozenset(
    f"{capture_id}.png" for capture_id in _CAPTURE_IDS
)


def _capture_every_screen(
    *,
    qtbot: QtBot,
    handle: AppHandle,
    destination: Path,
) -> frozenset[str]:
    """Capture every screen in the index and return the filenames written."""
    _capture_app_screens(qtbot=qtbot, handle=handle, destination=destination)
    _capture(_build_settings_dialog(qtbot=qtbot), path=destination / "06_settings.png")
    for capture_id, dialog in build_common_dialogs(qtbot=qtbot).items():
        _capture(dialog, path=destination / f"{capture_id}.png")
    return frozenset(path.name for path in destination.glob("*.png"))


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_harness_captures_every_screen_in_light_theme(  # noqa: PLR0913  # the real app-composition rig needs seed_setting/app_data_root_all_providers_disabled alongside build_real_app_without_enabled_providers/drain_task_runner_deliveries/qtbot/tmp_path
    qtbot: QtBot,
    tmp_path: Path,
    app_data_root_all_providers_disabled: Path,
    seed_setting: Callable[..., None],
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-087-AC-1

    Running the offscreen harness under the Light theme writes one PNG per screen
    enumerated in the 08-R §2 screen index into the artifacts directory.
    """
    # Arrange
    seed_setting(app_data_root_all_providers_disabled, key="ui.theme", value="light")
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    destination = _artifacts_root(tmp_path) / "light"

    # Act
    written = _capture_every_screen(qtbot=qtbot, handle=handle, destination=destination)
    drain_task_runner_deliveries(handle)

    # Assert
    assert written == _EXPECTED_CAPTURES


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_harness_captures_every_screen_in_dark_theme(  # noqa: PLR0913  # the real app-composition rig needs seed_setting/app_data_root_all_providers_disabled alongside build_real_app_without_enabled_providers/drain_task_runner_deliveries/qtbot/tmp_path
    qtbot: QtBot,
    tmp_path: Path,
    app_data_root_all_providers_disabled: Path,
    seed_setting: Callable[..., None],
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-087-AC-2

    Running the offscreen harness under the Dark theme writes one PNG per screen
    enumerated in the 08-R §2 screen index into the artifacts directory.
    """
    # Arrange
    seed_setting(app_data_root_all_providers_disabled, key="ui.theme", value="dark")
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    destination = _artifacts_root(tmp_path) / "dark"

    # Act
    written = _capture_every_screen(qtbot=qtbot, handle=handle, destination=destination)
    drain_task_runner_deliveries(handle)

    # Assert
    assert written == _EXPECTED_CAPTURES


_REPORT_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2] / "docs" / "development" / "mockup_conformance_review.md"
)

_VERDICTS: Final[frozenset[str]] = frozenset({"conforms", "discrepancy", "not-applicable"})

_CHECKLIST_ITEM_COUNT: Final[int] = 13

_ROW_RE: Final[re.Pattern[str]] = re.compile(
    r"^\|\s*(\d{1,2})\s*\|[^|]*\|\s*([a-z-]+)\s*\|", re.MULTILINE
)

_THEMES: Final[tuple[str, ...]] = ("light", "dark")

_REPORT_CASES: Final[tuple[tuple[str, str], ...]] = tuple(
    (screen_id, theme) for screen_id in _SCREEN_INDEX_IDS for theme in _THEMES
)

_REPORT_CASE_IDS: Final[tuple[str, ...]] = tuple(
    f"{screen_id}-{theme}" for screen_id, theme in _REPORT_CASES
)


def _report_section(text: str, *, screen_id: str, theme: str) -> str:
    """Return the report text for one screen under one theme."""
    heading = re.compile(
        rf"^###\s+Screen\s+{screen_id}\b.*\b{theme}\b.*$", re.MULTILINE | re.IGNORECASE
    )
    match = heading.search(text)
    if match is None:
        message = f"no '### Screen {screen_id} ... {theme}' section in the report"
        raise AssertionError(message)
    rest = text[match.end() :]
    following = re.search(r"^##+\s", rest, re.MULTILINE)
    return rest if following is None else rest[: following.start()]


def _verdicts_in(section: str) -> tuple[str, ...]:
    """Return the verdict cell of every numbered checklist row in ``section``."""
    return tuple(match.group(2) for match in _ROW_RE.finditer(section))


@pytest.mark.parametrize(("screen_id", "theme"), _REPORT_CASES, ids=_REPORT_CASE_IDS)
def test_mockup_conformance_report_covers_every_screen(screen_id: str, theme: str) -> None:
    """Proves: STORY-087-AC-3

    The findings report records a valid standardization-review-checklist verdict
    for all thirteen 08-L §14 items, for every screen in the screen index, under
    both the Light and the Dark theme.
    """
    # Arrange
    section = _report_section(
        _REPORT_PATH.read_text(encoding="utf-8"), screen_id=screen_id, theme=theme
    )

    # Act
    verdicts = _verdicts_in(section)

    # Assert
    assert (len(verdicts), tuple(v for v in verdicts if v not in _VERDICTS)) == (
        _CHECKLIST_ITEM_COUNT,
        (),
    )
