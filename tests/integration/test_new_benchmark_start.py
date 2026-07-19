"""Integration test: New Benchmark Start -> Run Summary dialog -> start_run wiring
(STORY-055-AC-6).

``NewBenchmarkController._on_start_clicked`` deferred-imports
``ui.common_dialogs.make_run_summary_dialog`` at first use (to break a genuine circular
import between the two packages -- see the controller's own module docstring), so this
exercises a real cross-module behaviour and belongs in ``tests/integration/`` rather than
either module's colocated ``tests/`` (testing-standard-pyqt skill; 07_TESTING_STANDARD.md
layout).
"""

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QPushButton
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.workspace_controller.testing import FakeWorkspaceController
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ModelDescriptor,
    ProviderConfig,
    ProviderHealth,
    ProviderType,
    ReadinessState,
    RunMode,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_STARTED,
    EventBus,
    RunStartedEvent,
    Subscription,
)
from ollama_llm_bench.backend.mode_visibility import visible_sections
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.ui.new_benchmark import NewBenchmarkCollaborators, make_new_benchmark_widget
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark.testing import FakeNewBenchmarkGateway, FakeRunValidator
from ollama_llm_bench.ui.theme import PlatformKind, ThemeSetting, make_theme_manager

_PROVIDER_OTHER_ID = "eeeeeeee-0000-4000-8000-000000000000"
_PROVIDER_OTHER = ProviderConfig(
    provider_id=_PROVIDER_OTHER_ID,
    name="Other Provider",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    enabled=True,
    default_models=("mixtral",),
)
_PROVIDER_ID = "ffffffff-0000-4000-8000-000000000000"
_PROVIDER = ProviderConfig(
    provider_id=_PROVIDER_ID,
    name="Ollama Local",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    enabled=True,
    default_models=("llama3",),
)
_READY_SNAPSHOT = AppReadinessSnapshot(
    overall=ReadinessState.READY,
    per_provider=(
        ProviderHealth(
            provider_id=_PROVIDER_OTHER_ID,
            reachable=True,
            discovery_supported=True,
            model_count=1,
            last_probe_ms=5,
            probed_at=0,
        ),
        ProviderHealth(
            provider_id=_PROVIDER_ID,
            reachable=True,
            discovery_supported=True,
            model_count=1,
            last_probe_ms=5,
            probed_at=0,
        ),
    ),
    embedding_reachable=True,
)


class _FakeSubscription:
    """A cancellable handle mirroring the real EventBus's Subscription contract."""

    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn

    def cancel(self) -> None:
        self._cancel_fn()


class _FakeEventBus:
    """A synchronous, in-process EventBus test double, local to this integration test."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[object], None]]] = {}

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        self._handlers.setdefault(signal_name, []).append(handler)
        return _FakeSubscription(lambda: self._handlers[signal_name].remove(handler))

    def emit(self, signal_name: str, payload: object) -> None:
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)


class _RealBackedModeVisibilityPolicy:
    """Wraps the real backend.mode_visibility.visible_sections."""

    def visible_sections(self, mode: RunMode) -> tuple:  # type: ignore[type-arg]  # matches Protocol's bare tuple return
        return visible_sections(mode)


def _confirm_run_summary_dialog(qtbot: QtBot) -> None:
    """Find the modal Run Summary dialog opened by Start and click its own Start button."""
    dialog = cast("QDialog", QApplication.activeModalWidget())
    start_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "common_dialogs.run_summary.start_button")
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        start_button, Qt.MouseButton.LeftButton
    )


def test_confirm_run_summary_starts_run_and_locks(qtbot: QtBot, qapp: QApplication) -> None:
    """Proves: STORY-055-AC-6

    Given a valid configuration, when the user clicks Start Benchmark and confirms
    the Run Summary dialog, then NewBenchmarkGateway.start_run(request) is called
    exactly once with the assembled request. On the subsequent _run_started event
    the widget transitions to its read-only Locked state -- observably, a second
    click of Start Benchmark (still isEnabled(), since no fresh validation ran) is
    a no-op: no second dialog opens and start_run is not called again.
    """
    # Arrange
    gateway = FakeNewBenchmarkGateway()
    gateway.set_providers((_PROVIDER_OTHER, _PROVIDER))
    gateway.set_readiness(_READY_SNAPSHOT)
    event_bus: EventBus = _FakeEventBus()
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.MACOS
    )
    collaborators = NewBenchmarkCollaborators(
        gateway=gateway,
        event_bus=event_bus,
        task_file_loader=FakeTaskFileLoader(),
        mode_visibility_policy=_RealBackedModeVisibilityPolicy(),
        run_validator=FakeRunValidator(entries=()),
        native_pickers=FakeNativePickers(),
        workspace=FakeWorkspaceController(),
        theme_manager=theme_manager,
        platform_kind=PlatformKind.MACOS,
    )
    view = make_new_benchmark_widget(collaborators=collaborators)
    assert isinstance(view, NewBenchmarkView)
    qtbot.addWidget(view)

    provider_dropdown = cast(
        "QComboBox",
        view.test_models_section.findChild(
            QComboBox, "new_benchmark.test_models.provider_dropdown"
        ),
    )
    provider_dropdown.setCurrentIndex(1)  # a genuine index change: _PROVIDER_OTHER -> _PROVIDER
    view.test_models_section.toggle_model_for_test("llama3")

    # Act (open + confirm the Run Summary dialog)
    QTimer.singleShot(0, lambda: _confirm_run_summary_dialog(qtbot))
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        view.start_button, Qt.MouseButton.LeftButton
    )

    # Assert (start_run called exactly once with the assembled request)
    assert len(gateway.recorded_start_run_requests) == 1
    assert gateway.recorded_start_run_requests[0].test_models == (
        ModelDescriptor(provider_id=_PROVIDER_ID, model_name="llama3"),
    )

    # Act (the run-started event locks the controller against a repeat Start)
    event_bus.emit(
        SIGNAL_RUN_STARTED,
        RunStartedEvent(
            run_id=1,
            run_name="Run 1",
            run_mode=RunMode.SYNTHETIC,
            started_at="2026-07-19T00:00:00Z",
            total_tasks=1,
            test_targets=((_PROVIDER_ID, "llama3"),),
        ),
    )
    assert view.start_button.isEnabled()
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        view.start_button, Qt.MouseButton.LeftButton
    )

    # Assert (Locked: the second click is a no-op -- no second start_run call)
    assert len(gateway.recorded_start_run_requests) == 1
