"""Unit tests for TestModelsWidget provider-refresh subscription wiring."""

from collections.abc import Callable

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.widgets.panels.control.test_models_widget import TestModelsWidget

# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLACEHOLDER = "(no providers)"


def _build_widget(mocker: MockerFixture, provider_names: list[str]) -> TestModelsWidget:
    mock_ctrl = mocker.Mock(spec=RunConfigController)
    mock_ctrl.get_provider_names.return_value = provider_names
    mock_ctrl.get_healthy_provider_ids.return_value = provider_names
    return TestModelsWidget(controller=mock_ctrl)


def _capture_refresh_callback(mock_ctrl: RunConfigController) -> Callable[[], None]:
    """Return the callback registered via subscribe_to_provider_registry_reloaded."""
    from unittest.mock import Mock

    assert isinstance(mock_ctrl, Mock)
    mock_ctrl.subscribe_to_provider_registry_reloaded.assert_called_once()  # type: ignore[attr-defined]
    return mock_ctrl.subscribe_to_provider_registry_reloaded.call_args[0][0]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Subscription tests
# ---------------------------------------------------------------------------


def test_init_subscribes_to_provider_registry_reloaded(qapp: QApplication, mocker: MockerFixture) -> None:
    """TestModelsWidget.__init__ must call subscribe_to_provider_registry_reloaded exactly once."""
    mock_ctrl = mocker.Mock(spec=RunConfigController)
    mock_ctrl.get_provider_names.return_value = ["ollama_local"]
    mock_ctrl.get_healthy_provider_ids.return_value = ["ollama_local"]

    TestModelsWidget(controller=mock_ctrl)

    mock_ctrl.subscribe_to_provider_registry_reloaded.assert_called_once()


def test_provider_registry_reloaded_refreshes_combo(qapp: QApplication, mocker: MockerFixture) -> None:
    """Firing the registered callback must repopulate the browse combo."""
    mock_ctrl = mocker.Mock(spec=RunConfigController)
    mock_ctrl.get_provider_names.return_value = ["ollama_local"]
    mock_ctrl.get_healthy_provider_ids.return_value = ["ollama_local"]

    widget = TestModelsWidget(controller=mock_ctrl)
    refresh_cb = _capture_refresh_callback(mock_ctrl)

    # Simulate a new provider becoming available
    mock_ctrl.get_provider_names.return_value = ["ollama_local", "lm_studio"]
    refresh_cb()

    items = [widget._browse_combo.itemText(i) for i in range(widget._browse_combo.count())]
    assert "ollama_local" in items
    assert "lm_studio" in items
    assert len(items) == 2


def test_refresh_preserves_existing_selection_if_still_present(qapp: QApplication, mocker: MockerFixture) -> None:
    """If the previously selected provider is still in the refreshed list, it must remain selected."""
    mock_ctrl = mocker.Mock(spec=RunConfigController)
    mock_ctrl.get_provider_names.return_value = ["ollama_local", "lm_studio"]
    mock_ctrl.get_healthy_provider_ids.return_value = ["ollama_local", "lm_studio"]

    widget = TestModelsWidget(controller=mock_ctrl)
    refresh_cb = _capture_refresh_callback(mock_ctrl)

    # Select the second provider
    idx = widget._browse_combo.findText("lm_studio")
    widget._browse_combo.setCurrentIndex(idx)

    # Provider list is unchanged
    mock_ctrl.get_provider_names.return_value = ["ollama_local", "lm_studio"]
    refresh_cb()

    assert widget._browse_combo.currentText() == "lm_studio"


def test_refresh_falls_to_first_when_selection_gone(qapp: QApplication, mocker: MockerFixture) -> None:
    """If the selected provider is removed, the combo must fall back to the first entry."""
    mock_ctrl = mocker.Mock(spec=RunConfigController)
    mock_ctrl.get_provider_names.return_value = ["ollama_local", "lm_studio"]
    mock_ctrl.get_healthy_provider_ids.return_value = ["ollama_local", "lm_studio"]

    widget = TestModelsWidget(controller=mock_ctrl)
    refresh_cb = _capture_refresh_callback(mock_ctrl)

    # Select lm_studio
    idx = widget._browse_combo.findText("lm_studio")
    widget._browse_combo.setCurrentIndex(idx)
    assert widget._browse_combo.currentText() == "lm_studio"

    # lm_studio disappears from the registry
    mock_ctrl.get_provider_names.return_value = ["ollama_local"]
    refresh_cb()

    assert widget._browse_combo.currentText() == "ollama_local"
