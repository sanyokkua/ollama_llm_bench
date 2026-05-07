"""Unit tests for ProviderCardWidget.set_health and reset_health."""

import pytest
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import ProviderConfig, ProviderType
from ollama_llm_bench.ui.widgets.settings.provider_card_widget import ProviderCardWidget


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _card(qapp: QApplication) -> ProviderCardWidget:
    config = ProviderConfig(
        provider_id="test_p",
        label="Test Provider",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key="key",
        api_key_raw="key",
        enabled=True,
        base_url="http://localhost:11434/v1",
    )
    return ProviderCardWidget(config=config, used_ids=set())


class TestSetHealth:
    def test_live_shows_model_count_and_latency(self, qapp: QApplication) -> None:
        """set_health with state='live' must set dot property, tooltip, and show model/latency text."""
        card = _card(qapp)
        card.set_health(state="live", tooltip="ok", model_count=5, latency_ms=120)

        assert card._health_dot.property("health") == "live"
        assert card._health_dot.toolTip() == "ok"
        assert not card._status_label.isHidden()
        label_text = card._status_label.text()
        assert "5" in label_text
        assert "120" in label_text

    def test_down_shows_error_message(self, qapp: QApplication) -> None:
        """set_health with state='down' must set dot property and show the error message."""
        card = _card(qapp)
        card.set_health(state="down", tooltip="no key", error_message="OPENAI_API_KEY missing")

        assert card._health_dot.property("health") == "down"
        assert not card._status_label.isHidden()
        assert "OPENAI_API_KEY missing" in card._status_label.text()

    def test_unknown_hides_status_label(self, qapp: QApplication) -> None:
        """set_health with state='unknown' must set dot property and hide the status label."""
        card = _card(qapp)
        # First set something visible, then switch to unknown
        card.set_health(state="live", tooltip="was live", model_count=3, latency_ms=50)
        card.set_health(state="unknown", tooltip="disabled")

        assert card._health_dot.property("health") == "unknown"
        assert card._status_label.isHidden()

    def test_test_button_re_enabled_after_set_health(self, qapp: QApplication) -> None:
        """set_health must re-enable the Test button regardless of state."""
        card = _card(qapp)
        card._test_button.setEnabled(False)
        card.set_health(state="live", tooltip="ok", model_count=1, latency_ms=10)
        assert card._test_button.isEnabled()

    def test_down_without_error_message_shows_unavailable(self, qapp: QApplication) -> None:
        """When error_message is empty for a down state, 'Unavailable' fallback is shown."""
        card = _card(qapp)
        card.set_health(state="down", tooltip="no detail")
        assert "Unavailable" in card._status_label.text()


class TestResetHealth:
    def test_disables_test_button_and_shows_testing(self, qapp: QApplication) -> None:
        """reset_health must disable the Test button and show 'Testing…' in the status label."""
        card = _card(qapp)
        card.reset_health()

        assert not card._test_button.isEnabled()
        assert card._health_dot.property("health") == "unknown"
        assert not card._status_label.isHidden()
        assert "Testing" in card._status_label.text()
