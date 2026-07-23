"""Integration tests: Start-admission gate arbitration for the New Benchmark widget
(STORY-074, EC-RUN-1a).

These build a real ``InferenceActivityStore`` to prove gate arbitration end-to-end, which
requires importing ``backend.stores.inference_activity`` directly -- a real cross-module
dependency forbidden inside ``ui/``'s colocated ``tests/`` (no file under ``ui/`` may import
that module; see ``tests/architecture/test_ui_gate_access.py``) -- so these live in
``tests/integration/`` instead (testing-standard-pyqt skill; 07_TESTING_STANDARD.md layout),
mirroring ``tests/integration/test_new_benchmark_start.py``'s local test-double idiom.
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
    GateLease,
    InferenceActivity,
    InferenceActivityContext,
    ProviderConfig,
    ProviderHealth,
    ProviderType,
    ReadinessState,
    RunId,
    RunMode,
    RunStartRequest,
)
from ollama_llm_bench.backend.events import EventBus, Subscription
from ollama_llm_bench.backend.mode_visibility import visible_sections
from ollama_llm_bench.backend.stores.inference_activity import (
    InferenceActivityStore,
    make_inference_activity_store,
)
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


class _FixedClock:
    """A deterministic ``Clock`` stand-in for the real ``InferenceActivityStore``."""

    def now_utc(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


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


class _AdmissionRecordingGateway(FakeNewBenchmarkGateway):
    """``start_run`` performs the production gate-first admission contract
    (mirrors ``BenchmarkFlowApi.start``): first acquire wins and is recorded;
    a held gate is a complete no-op returning the ``RunId(0)`` sentinel.
    """

    def __init__(self, *, gate: InferenceActivityStore) -> None:
        super().__init__()
        self._gate = gate
        self.rejected_start_requests: list[RunStartRequest] = []
        self.held_lease: GateLease | None = None

    def start_run(self, request: RunStartRequest) -> RunId:
        lease = self._gate.try_acquire(
            InferenceActivity.BENCHMARK_RUN,
            InferenceActivityContext(activity=InferenceActivity.BENCHMARK_RUN, started_at=0),
        )
        if lease is None:
            self.rejected_start_requests.append(request)
            return 0
        self.held_lease = lease
        self.recorded_start_run_requests.append(request)
        return 1


def _confirm_run_summary_dialog(qtbot: QtBot) -> None:
    """Find the modal Run Summary dialog opened by Start and click its own Start button."""
    dialog = cast("QDialog", QApplication.activeModalWidget())
    start_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "common_dialogs.run_summary.start_button")
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        start_button, Qt.MouseButton.LeftButton
    )


def test_double_start_admission_is_a_noop(qtbot: QtBot, qapp: QApplication) -> None:
    """Proves: STORY-074-AC-1

    Two New Benchmark Start admissions firing before the first has flipped
    the gate state: the first acquires BENCHMARK_RUN and proceeds; the
    second hits a held gate and is a complete no-op -- no second run record,
    no second result-row reset, no second pipeline.
    """
    # Arrange -- real gate + admission-recording fake gateway; widget arrange
    # mirrors tests/integration/test_new_benchmark_start.py.
    event_bus: EventBus = _FakeEventBus()
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.MACOS
    )
    gate = make_inference_activity_store(clock=_FixedClock(), event_bus=event_bus)
    gateway = _AdmissionRecordingGateway(gate=gate)
    gateway.set_providers((_PROVIDER_OTHER, _PROVIDER))
    gateway.set_readiness(_READY_SNAPSHOT)
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

    # Act -- first admission via the widget: click Start Benchmark and confirm
    # the Run Summary dialog, which calls gateway.start_run(...) and acquires
    # the real gate.
    QTimer.singleShot(0, lambda: _confirm_run_summary_dialog(qtbot))
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        view.start_button, Qt.MouseButton.LeftButton
    )
    assert len(gateway.recorded_start_run_requests) == 1

    # Act -- second admission. In this harness the first admission's
    # _inference_activity_changed event flips gate_idle to False, which
    # NewBenchmarkController's compute_start_button_state immediately uses to
    # disable Start Benchmark -- so a second widget click never opens a second
    # Run Summary dialog and never reaches start_run at all (no genuine second
    # admission call to arbitrate). Per the plan's sanctioned fallback, fire
    # the second admission directly at the seam the EC actually targets: a
    # second call into NewBenchmarkGateway.start_run with the same assembled
    # request, exercising the real two-admission-calls race the gate
    # arbitrates.
    assert not view.start_button.isEnabled()
    gateway.start_run(gateway.recorded_start_run_requests[0])

    # Assert -- first admission proceeded, second was a complete no-op.
    assert len(gateway.recorded_start_run_requests) == 1
    assert len(gateway.rejected_start_requests) == 1
    assert gateway.held_lease is not None
    assert gate.state().current is InferenceActivity.BENCHMARK_RUN
