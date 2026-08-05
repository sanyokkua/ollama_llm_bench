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
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    ModelDescriptor,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ProviderType,
    ReadinessState,
    ResultId,
    ResultStatus,
    RunId,
    RunMode,
    RunStartRequest,
    RunStatus,
)
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.common_dialogs import (
    AboutDialogCollaborators,
    ErrorDialogPattern,
    ErrorDialogPayload,
    GenerateAnalysisCollaborators,
    make_about_dialog,
    make_error_dialog,
    make_generate_analysis_dialog,
    make_rename_run_dialog,
    make_resume_summary_dialog,
    make_retry_selection_dialog,
    make_run_summary_dialog,
)
from ollama_llm_bench.ui.new_benchmark.testing import FakeRunValidator
from ollama_llm_bench.ui.settings_dialog import (
    SettingsDialogCollaborators,
    make_settings_dialog,
)
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway

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


class _StubRenameRunGateway:
    """Structural ``RenameRunGateway`` returning one canned run header."""

    def __init__(self, *, runs: tuple[BenchmarkRun, ...]) -> None:
        self._runs = runs

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return self._runs

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        return None


class _StubRunSummaryGateway:
    """Structural ``RunSummaryGateway`` whose readiness passes preflight."""

    def __init__(self, *, readiness: AppReadinessSnapshot) -> None:
        self._readiness = readiness

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        return self._readiness

    def start_run(self, request: RunStartRequest) -> RunId:
        return _RUN_ID


class _StubResumeSummaryGateway:
    """Structural ``ResumeSummaryGateway`` with non-empty resumable results."""

    def __init__(self, *, run: BenchmarkRun, results: tuple[BenchmarkResult, ...]) -> None:
        self._run = run
        self._results = results

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return self._run

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        return ()

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        return len(result_ids)

    def resume_run(self, run_id: RunId) -> None:
        return None


class _StubRetrySelectionGateway:
    """Structural ``RetrySelectionGateway`` with a non-empty result table."""

    def __init__(self, *, results: tuple[BenchmarkResult, ...]) -> None:
        self._results = results

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        return len(result_ids)

    def resume_run(self, run_id: RunId) -> None:
        return None


class _StubRunAnalysisDispatcher:
    """Structural ``RunAnalysisDispatcher`` that always accepts a dispatch."""

    def regenerate_analysis(
        self, run_id: RunId, provider_id: ProviderId, model_name: ModelName
    ) -> bool:
        return True


class _StubProviderListSource:
    """Structural ``ProviderListSource`` offering one enabled provider."""

    def __init__(self, *, providers: tuple[ProviderConfig, ...]) -> None:
        self._providers = providers

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        return self._providers


class _StubModelFetcher:
    """Structural ``ModelFetcher`` delivering a canned catalogue synchronously."""

    def fetch_models(
        self,
        provider_id: ProviderId,
        *,
        on_success: Callable[[ProviderId, tuple[ModelName, ...]], None],
        on_error: Callable[[ProviderId, Exception], None],
    ) -> None:
        on_success(provider_id, (_MODEL_NAME,))


class _StubSubscription:
    """Structural ``Subscription`` handle; cancellation is a no-op for a capture."""

    def cancel(self) -> None:
        return None


class _StubGenerateAnalysisEventBus:
    """Structural ``EventBus`` fake routing around a real production defect.

    ``ui/common_dialogs/_internal/generate_analysis_view.py`` calls
    ``event_bus.subscribe(signal, handler)`` three times with no ``owner=``
    keyword. The real ``QtEventBusDeliverer.subscribe`` (used everywhere else
    in this harness) carries an ``icontract`` precondition requiring a non-
    ``None`` owner (08-J §2), so building this one dialog against the real
    bus raises ``icontract.errors.ViolationError`` -- a genuine bug that would
    crash any real user opening this dialog, masked in
    ``ui/common_dialogs/tests/test_generate_analysis_dialog.py`` by that
    module's own ``_FakeEventBus``, which accepts a missing owner silently.
    This mirrors that same fake, scoped to this one dialog only, so the
    screenshot capture is not blocked by a defect outside this story's scope
    (no ``src/`` change here -- see the task report).
    """

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> _StubSubscription:
        return _StubSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        return None


def _canned_provider() -> ProviderConfig:
    """Return one enabled provider entry for the Generate Analysis dropdown."""
    return ProviderConfig(
        provider_id=_PROVIDER_ID,
        name="Ollama (local)",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


def _canned_readiness() -> AppReadinessSnapshot:
    """Return a snapshot with one reachable provider and a reachable embedding."""
    return AppReadinessSnapshot(
        overall=ReadinessState.READY,
        per_provider=(
            ProviderHealth(
                provider_id=_PROVIDER_ID,
                reachable=True,
                discovery_supported=True,
                model_count=3,
                last_probe_ms=12,
                probed_at=0,
            ),
        ),
        embedding_reachable=True,
    )


def _canned_request() -> RunStartRequest:
    """Return a start request that passes the Run Summary preflight."""
    return RunStartRequest(
        run_mode=RunMode.SYNTHETIC,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
    )


def _canned_run() -> BenchmarkRun:
    """Return one completed run header."""
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=None,
        timestamp=_TIMESTAMP,
        run_mode=RunMode.SYNTHETIC,
        status=RunStatus.INCOMPLETE,
        total_tasks=4,
        completed_tasks=2,
        total_elapsed_ms=42_000,
        schema_version=1,
        created_at=_TIMESTAMP,
    )


def _canned_results() -> tuple[BenchmarkResult, ...]:
    """Return two result rows: one completed, one failed and retryable."""
    return (
        BenchmarkResult(
            result_id=1,
            run_id=_RUN_ID,
            task_id="synthetic_small_1",
            provider_id=_PROVIDER_ID,
            provider_name="Ollama (local)",
            model_name=_MODEL_NAME,
            status=ResultStatus.COMPLETED,
            created_at=_TIMESTAMP,
        ),
        BenchmarkResult(
            result_id=2,
            run_id=_RUN_ID,
            task_id="synthetic_small_2",
            provider_id=_PROVIDER_ID,
            provider_name="Ollama (local)",
            model_name=_MODEL_NAME,
            status=ResultStatus.FAILED_TIMEOUT,
            created_at=_TIMESTAMP,
        ),
    )


def _build_common_dialogs(*, qtbot: QtBot) -> dict[str, QDialog]:
    """Construct all seven shared modal dialogs, shown but never exec()'d.

    Three of the seven factories (``make_run_summary_dialog``,
    ``make_resume_summary_dialog``, ``make_retry_selection_dialog``) return
    ``QDialog | None`` -- ``None`` when their gateway's canned data is too
    thin to pass the dialog's own precondition. The canned data above is
    constructed specifically to satisfy every one of those preconditions, so
    a ``None`` here means the canned data regressed, not a normal outcome to
    tolerate.
    """
    bus = make_qt_event_bus_deliverer()
    clipboard = make_clipboard()
    candidates: dict[str, QDialog | None] = {
        "07_common_dialogs__about": make_about_dialog(
            collaborators=AboutDialogCollaborators(
                clipboard=clipboard,
                file_system_actions=make_file_system_actions(),
                event_bus=bus,
            ),
            version="0.0.0",
            data_folder_path="/home/user/.local/share/OllamaLLMBench",
        ),
        "07_common_dialogs__error": make_error_dialog(
            payload=ErrorDialogPayload(
                title="Provider unreachable",
                message="The benchmark could not reach the configured provider.",
                detail="HttpConnectionError: connection refused (127.0.0.1:11434)",
                pattern=ErrorDialogPattern.RECOVERABLE,
            ),
            clipboard=clipboard,
            event_bus=bus,
        ),
        "07_common_dialogs__rename_run": make_rename_run_dialog(
            gateway=_StubRenameRunGateway(runs=(_canned_run(),)),
            run_id=_RUN_ID,
            current_custom_name=None,
            computed_default_name="Synthetic run — 2026-08-05 12:00",
        ),
        "07_common_dialogs__run_summary": make_run_summary_dialog(
            gateway=_StubRunSummaryGateway(readiness=_canned_readiness()),
            run_validator=FakeRunValidator(),
            request=_canned_request(),
        ),
        "07_common_dialogs__resume_summary": make_resume_summary_dialog(
            gateway=_StubResumeSummaryGateway(run=_canned_run(), results=_canned_results()),
            event_bus=bus,
            run_id=_RUN_ID,
        ),
        "07_common_dialogs__retry_selection": make_retry_selection_dialog(
            gateway=_StubRetrySelectionGateway(results=_canned_results()),
            run_id=_RUN_ID,
        ),
        "07_common_dialogs__generate_analysis": make_generate_analysis_dialog(
            run=_canned_run(),
            collaborators=GenerateAnalysisCollaborators(
                dispatcher=_StubRunAnalysisDispatcher(),
                provider_source=_StubProviderListSource(providers=(_canned_provider(),)),
                model_fetcher=_StubModelFetcher(),
                # Not the shared real `bus` -- see `_StubGenerateAnalysisEventBus`'s
                # docstring for the real production defect this routes around.
                event_bus=_StubGenerateAnalysisEventBus(),
            ),
        ),
    }
    dialogs: dict[str, QDialog] = {}
    for capture_id, dialog in candidates.items():
        if dialog is None:
            message = f"{capture_id} factory returned None; its gateway data is insufficient"
            raise AssertionError(message)
        qtbot.addWidget(dialog)
        dialog.resize(*_DIALOG_SIZE)
        dialog.show()
        dialogs[capture_id] = dialog
    qtbot.wait(0)
    return dialogs


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_every_shared_modal_dialog_is_constructed_for_capture(qtbot: QtBot) -> None:
    # Arrange
    expected = frozenset(capture_id for capture_id in _CAPTURE_IDS if capture_id.startswith("07_"))

    # Act
    dialogs = _build_common_dialogs(qtbot=qtbot)

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
    for capture_id, dialog in _build_common_dialogs(qtbot=qtbot).items():
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
