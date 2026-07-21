"""Tests for the Generate Analysis dialog (STORY-065-AC-5, AC-6, AC-7).

Every ``ProviderListSource``/``ModelFetcher``/``EventBus``/``RunAnalysisDispatcher``
test double is declared locally, scoped to this file only -- mirrors
``ui/results/tests/conftest.py``'s locally-declared Protocol fakes and
``ui/resume_benchmark/tests/test_controller.py``'s precedent (STORY-065's Notes).
"""

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import (
    BenchmarkRun,
    InferenceActivity,
    InferenceActivityState,
    ModelName,
    ProviderConfig,
    ProviderId,
    ProviderType,
    RunId,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    InferenceActivityChangedEvent,
    Subscription,
)
from ollama_llm_bench.ui.common_dialogs import (
    GenerateAnalysisCollaborators,
    make_generate_analysis_dialog,
)

_GATE_BUSY_TOOLTIP = "Another inference activity is in flight — please wait."

_PROVIDER_A = ProviderConfig(
    provider_id="aaaaaaaa-1111-4111-8111-111111111111",
    name="Ollama Local",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    enabled=True,
)
_PROVIDER_B = ProviderConfig(
    provider_id="bbbbbbbb-2222-4222-8222-222222222222",
    name="Anthropic",
    provider_type=ProviderType.ANTHROPIC,
    enabled=True,
)


class _FakeSubscription:
    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn

    def cancel(self) -> None:
        self._cancel_fn()


class _FakeEventBus:
    """A synchronous, in-process ``EventBus`` test double (immediate delivery)."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[object], None]]] = {}

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        self._handlers.setdefault(signal_name, []).append(handler)

        def _cancel() -> None:
            self._handlers[signal_name].remove(handler)

        return _FakeSubscription(_cancel)

    def emit(self, signal_name: str, payload: object) -> None:
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)


class _FakeProviderListSource:
    def __init__(self, providers: tuple[ProviderConfig, ...]) -> None:
        self._providers = providers

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        return self._providers


class _FakeModelFetcher:
    def __init__(self, models_by_provider: dict[ProviderId, tuple[ModelName, ...]]) -> None:
        self._models_by_provider = models_by_provider

    def fetch_models(
        self,
        provider_id: ProviderId,
        *,
        on_success: Callable[[ProviderId, tuple[ModelName, ...]], None],
        on_error: Callable[[ProviderId, Exception], None],
    ) -> None:
        on_success(provider_id, self._models_by_provider.get(provider_id, ()))


class _FakeRunAnalysisDispatcher:
    """Structurally satisfies ``ui.common_dialogs.protocols.RunAnalysisDispatcher``."""

    def __init__(self, *, acquire: bool = True) -> None:
        self._acquire = acquire
        self.calls: list[tuple[RunId, ProviderId, ModelName]] = []

    def regenerate_analysis(
        self, run_id: RunId, provider_id: ProviderId, model_name: ModelName
    ) -> bool:
        self.calls.append((run_id, provider_id, model_name))
        return self._acquire


def _make_run(run_id: RunId, *, judge_provider_id: ProviderId | None = None) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name="My Run",
        timestamp="2026-07-21T00:00:00Z",
        run_mode=RunMode.GRADED,
        status=RunStatus.COMPLETED,
        total_tasks=1,
        completed_tasks=1,
        total_elapsed_ms=1000,
        judge_provider_id=judge_provider_id,
        schema_version=1,
        created_at="2026-07-21T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# STORY-065-AC-5
# ---------------------------------------------------------------------------


def test_model_filter_and_confirm_dispatch(qtbot: QtBot) -> None:
    """Proves: STORY-065-AC-5

    Given the Generate Analysis dialog is open, when the user selects a
    provider, then the model dropdown repopulates filtered to chat-capable,
    non-embedding models; and when the user confirms, then the generation is
    dispatched through the parent controller's
    ``regenerate_analysis(run_id, provider_id, model_name)`` with the
    selected pair.
    """
    # Arrange
    dispatcher = _FakeRunAnalysisDispatcher()
    provider_source = _FakeProviderListSource((_PROVIDER_A, _PROVIDER_B))
    model_fetcher = _FakeModelFetcher(
        {
            _PROVIDER_A.provider_id: ("llama3", "nomic-embed-text"),
            _PROVIDER_B.provider_id: ("claude-3-5-sonnet", "text-embedding-3-small"),
        }
    )
    run = _make_run(1, judge_provider_id=_PROVIDER_A.provider_id)
    dialog = make_generate_analysis_dialog(
        run=run,
        collaborators=GenerateAnalysisCollaborators(
            dispatcher=dispatcher,
            provider_source=provider_source,
            model_fetcher=model_fetcher,
            event_bus=_FakeEventBus(),
        ),
    )
    qtbot.addWidget(dialog)
    provider_combo = cast(
        "QComboBox",
        dialog.findChild(QComboBox, "common_dialogs.generate_analysis.provider_dropdown"),
    )
    model_combo = cast(
        "QComboBox",
        dialog.findChild(QComboBox, "common_dialogs.generate_analysis.model_dropdown"),
    )
    # Assert: the default provider's models are filtered to the one chat-capable model
    assert model_combo.count() == 1
    assert model_combo.itemText(0) == "llama3"
    # Act: the user picks the second provider
    provider_combo.setCurrentIndex(provider_combo.findData(_PROVIDER_B.provider_id))
    # Assert: the model dropdown repopulates, filtered again
    assert model_combo.count() == 1
    assert model_combo.itemText(0) == "claude-3-5-sonnet"
    # Act: the user confirms
    confirm_button = cast(
        "QPushButton",
        dialog.findChild(QPushButton, "common_dialogs.generate_analysis.confirm_button"),
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        confirm_button, Qt.MouseButton.LeftButton
    )
    # Assert
    assert dispatcher.calls == [(1, _PROVIDER_B.provider_id, "claude-3-5-sonnet")]


# ---------------------------------------------------------------------------
# STORY-065-AC-6
# ---------------------------------------------------------------------------


def test_gate_busy_keeps_dialog_open_and_re_enables_on_idle(qtbot: QtBot) -> None:
    """Proves: STORY-065-AC-6

    Covers: EC-GA-3, EC-GA-4, EC-GA-5

    Given the dialog Confirm is clicked while ``try_acquire(JUDGE_ANALYSIS)``
    would fail (the gate is held by another activity), then the dialog stays
    open, shows the inline busy message, disables Confirm, and re-enables it
    when ``_inference_activity_changed`` reports the gate ``IDLE``.
    """
    # Arrange
    dispatcher = _FakeRunAnalysisDispatcher(acquire=False)
    provider_source = _FakeProviderListSource((_PROVIDER_A,))
    model_fetcher = _FakeModelFetcher({_PROVIDER_A.provider_id: ("llama3",)})
    bus = _FakeEventBus()
    run = _make_run(1)
    dialog = make_generate_analysis_dialog(
        run=run,
        collaborators=GenerateAnalysisCollaborators(
            dispatcher=dispatcher,
            provider_source=provider_source,
            model_fetcher=model_fetcher,
            event_bus=bus,
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(0)
    confirm_button = cast(
        "QPushButton",
        dialog.findChild(QPushButton, "common_dialogs.generate_analysis.confirm_button"),
    )
    busy_label = cast(
        "QLabel", dialog.findChild(QLabel, "common_dialogs.generate_analysis.busy_label")
    )
    # Act: Confirm is clicked while the gate would fail to acquire
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        confirm_button, Qt.MouseButton.LeftButton
    )
    # Assert: the dialog stays open, shows the busy message, disables Confirm
    assert dispatcher.calls == [(1, _PROVIDER_A.provider_id, "llama3")]
    assert dialog.isVisible() is True
    assert busy_label.isVisible() is True
    assert confirm_button.isEnabled() is False
    assert confirm_button.toolTip() == _GATE_BUSY_TOOLTIP
    # Act: the gate returns to IDLE
    bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(state=InferenceActivityState(current=InferenceActivity.IDLE)),
    )
    # Assert: Confirm re-enables; the dialog remains open (never auto-accepted)
    assert busy_label.isVisible() is False
    assert confirm_button.isEnabled() is True
    assert dialog.isVisible() is True


# ---------------------------------------------------------------------------
# STORY-065-AC-7
# ---------------------------------------------------------------------------


def test_generate_analysis_dialog_constructs_and_shows_with_no_error_logs(qtbot: QtBot) -> None:
    """Proves: STORY-065-AC-7

    Constructed via its own factory (``make_generate_analysis_dialog``) with a
    fake ``ResultGateway``-adjacent collaborator bundle and mounted under
    ``qtbot``, no exception is raised, the dialog reports ``isVisible()``, and
    no ``error``/``critical``-level ``structlog`` record is captured.
    """
    # Arrange
    dispatcher = _FakeRunAnalysisDispatcher()
    provider_source = _FakeProviderListSource((_PROVIDER_A,))
    model_fetcher = _FakeModelFetcher({_PROVIDER_A.provider_id: ("llama3",)})
    run = _make_run(1)
    # Act
    with structlog.testing.capture_logs() as logs:
        dialog = make_generate_analysis_dialog(
            run=run,
            collaborators=GenerateAnalysisCollaborators(
                dispatcher=dispatcher,
                provider_source=provider_source,
                model_fetcher=model_fetcher,
                event_bus=_FakeEventBus(),
            ),
        )
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)
    # Assert
    assert dialog.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)
