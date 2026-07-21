"""Tests for ``EmbeddingSectionWidget``'s Test Embedding gate wiring and its
persisted-selection / first-start bootstrap initialisation
(STORY-066 spec-conformance fix pass -- §3.4, §14)."""

from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    InferenceActivity,
    InferenceActivityState,
    ReadinessState,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    InferenceActivityChangedEvent,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.embedding_section import (
    EmbeddingSectionWidget,
)
from ollama_llm_bench.ui.settings_dialog.models import EmbeddingSectionCollaborators
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway
from ollama_llm_bench.ui.settings_dialog.tests.conftest import PROVIDER_A, PROVIDER_B, FakeEventBus

_GATE_BUSY_TOOLTIP = "Another inference activity is in flight — please wait."


def _make_widget(
    *, gateway: FakeSettingsGateway | None = None, bus: FakeEventBus | None = None
) -> EmbeddingSectionWidget:
    gateway = gateway or FakeSettingsGateway()
    bus = bus or FakeEventBus()
    return EmbeddingSectionWidget(
        collaborators=EmbeddingSectionCollaborators(
            provider_configs_source=gateway.list_providers,
            discover_models=gateway.discover_models,
            get_setting=gateway.get_setting,
            probe_embedding=gateway.probe_embedding,
            event_bus=bus,
        )
    )


def _test_embedding_button(widget: EmbeddingSectionWidget) -> QPushButton:
    return cast(
        "QPushButton",
        widget.findChild(QPushButton, "settings_dialog.embedding_section.test_embedding"),
    )


def _diagnostic_label(widget: EmbeddingSectionWidget) -> QLabel:
    return cast("QLabel", widget.findChild(QLabel, "settings_dialog.embedding_section.diagnostic"))


# ---------------------------------------------------------------------------
# Test Embedding -- gate wiring
# ---------------------------------------------------------------------------


def test_test_embedding_button_gated_on_inference_activity(qtbot: QtBot) -> None:
    """Mirrors AC-5's gate pattern for the Provider Edit Test buttons: the
    Test Embedding button disables with the in-flight tooltip while a foreign
    activity holds the single-inference gate, and re-enables on IDLE."""
    # Arrange
    bus = FakeEventBus()
    widget = _make_widget(bus=bus)
    qtbot.addWidget(widget)
    button = _test_embedding_button(widget)
    # Act: another activity holds the gate
    bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(
            state=InferenceActivityState(current=InferenceActivity.BENCHMARK_RUN)
        ),
    )
    # Assert
    assert button.isEnabled() is False
    assert button.toolTip() == _GATE_BUSY_TOOLTIP
    # Act: the gate returns to IDLE
    bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(state=InferenceActivityState(current=InferenceActivity.IDLE)),
    )
    # Assert
    assert button.isEnabled() is True


def test_test_embedding_click_probes_and_renders_diagnostic(qtbot: QtBot) -> None:
    """Clicking Test Embedding calls ``SettingsGateway.probe_embedding`` and
    renders the resulting ``embedding_reachable`` flag into the diagnostic label."""
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_readiness(
        AppReadinessSnapshot(
            overall=ReadinessState.READY, per_provider=(), embedding_reachable=True
        )
    )
    widget = _make_widget(gateway=gateway)
    qtbot.addWidget(widget)
    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        _test_embedding_button(widget), Qt.MouseButton.LeftButton
    )
    # Assert
    assert gateway.recorded_probe_embedding_calls == 1
    assert _diagnostic_label(widget).text() == "✓ embedding reachable"


# ---------------------------------------------------------------------------
# Persisted-selection / first-start bootstrap initialisation (§1.4, §14)
# ---------------------------------------------------------------------------


def test_dropdowns_initialize_from_persisted_embedding_selection(qtbot: QtBot) -> None:
    """When ``embedding.selected_provider_name``/``embedding.selected_model_name``
    are already persisted, the dropdowns preselect that exact pair at construction."""
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A, PROVIDER_B))
    gateway.set_discovered_models(PROVIDER_A.provider_id, ("llama3", "mistral"))
    gateway.set_discovered_models(PROVIDER_B.provider_id, ("claude-3", "text-embedding-3-small"))
    gateway.set_setting_value("embedding.selected_provider_name", PROVIDER_B.name)
    gateway.set_setting_value("embedding.selected_model_name", "text-embedding-3-small")
    # Act
    widget = _make_widget(gateway=gateway)
    qtbot.addWidget(widget)
    # Assert
    assert widget.selected_pair() == (PROVIDER_B.provider_id, "text-embedding-3-small")


def test_first_start_bootstrap_selects_first_embedding_model_across_providers(
    qtbot: QtBot,
) -> None:
    """When no embedding selection is persisted, the widget auto-selects the
    first available embedding-likely model found across all enabled providers,
    in provider order -- skipping a provider offering no embedding model."""
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A, PROVIDER_B))
    gateway.set_discovered_models(PROVIDER_A.provider_id, ("llama3", "mistral"))
    gateway.set_discovered_models(PROVIDER_B.provider_id, ("claude-3", "voyage-embed-2"))
    # Act
    widget = _make_widget(gateway=gateway)
    qtbot.addWidget(widget)
    # Assert
    assert widget.selected_pair() == (PROVIDER_B.provider_id, "voyage-embed-2")


def test_no_bootstrap_when_no_provider_offers_an_embedding_model(qtbot: QtBot) -> None:
    """When no enabled provider offers any embedding-likely model and nothing
    is persisted, the model half of the pair is left empty (never defaults to
    an arbitrary chat model) -- the provider dropdown itself still shows its
    own shared-widget default of the first enabled provider, per §14: "the
    embedding pair is left empty and the user must choose one manually"."""
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    gateway.set_discovered_models(PROVIDER_A.provider_id, ("llama3", "mistral"))
    # Act
    widget = _make_widget(gateway=gateway)
    qtbot.addWidget(widget)
    # Assert
    assert widget.selected_pair()[1] is None
