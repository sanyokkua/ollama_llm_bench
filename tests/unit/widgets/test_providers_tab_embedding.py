"""Unit tests for ProvidersTabWidget embedding section — crash guard, filtering, caching, warnings."""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import (
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.ui.widgets.settings.providers_tab_widget import ProvidersTabWidget

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _provider_config(*, provider_id: str = "p1") -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        label=f"Provider {provider_id}",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key="",
        api_key_raw="",
        enabled=True,
        base_url="http://localhost:11434/v1",
    )


def _make_controller(
    mocker: MockerFixture,
    providers: tuple[ProviderConfig, ...] = (),
    *,
    provider_id: str = "p1",
    embedding_model: str = "",
) -> MagicMock:
    mock = cast(MagicMock, mocker.Mock(spec=SettingsWidgetControllerApi))
    mock.get_providers_config.return_value = ProvidersConfig(
        providers=providers,
        embedding=EmbeddingConfig(provider_id=provider_id, model=embedding_model),
    )
    mock.get_models_for_provider.return_value = None
    mock.is_embedding_model.return_value = False
    return mock


def _make_tab(mocker: MockerFixture, controller: MagicMock) -> ProvidersTabWidget:
    return ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))


# ---------------------------------------------------------------------------
# Crash guard — shiboken6.isValid
# ---------------------------------------------------------------------------


class TestShibokenGuard:
    def test_shiboken_guard_prevents_crash_after_widget_deleted(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """_on_models must not raise after the widget is destroyed."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")

        captured_callback: list[object] = []

        def capture_callback(provider_id: str, callback: object, *, parent: object = None) -> None:
            captured_callback.append(callback)

        controller.get_models_for_provider.side_effect = capture_callback

        tab = _make_tab(mocker, controller)

        assert captured_callback, "callback should have been captured"
        on_models = captured_callback[0]

        # Destroy the widget
        tab.deleteLater()
        qapp.processEvents()

        # Calling the closure on a dead widget must not raise RuntimeError
        try:
            on_models(["bge-m3", "llama3"])  # type: ignore[operator]
        except RuntimeError as exc:  # pragma: no cover
            pytest.fail(f"RuntimeError raised after widget deleted: {exc}")


# ---------------------------------------------------------------------------
# Model filtering
# ---------------------------------------------------------------------------


class TestModelFiltering:
    def test_models_filtered_to_embedding_only(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Combo must contain only embedding-classified models when some match."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")

        captured_callback: list[object] = []

        def capture_callback(provider_id: str, callback: object, *, parent: object = None) -> None:
            captured_callback.append(callback)

        controller.get_models_for_provider.side_effect = capture_callback

        def classify(name: str) -> bool:
            return "embed" in name or "bge" in name or "nomic" in name

        controller.is_embedding_model.side_effect = classify

        tab = _make_tab(mocker, controller)
        on_models = captured_callback[0]
        on_models(["bge-m3", "llama3", "nomic-embed-text"])  # type: ignore[operator]

        combo = tab._embedding_model_combo
        items = [combo.itemText(i) for i in range(combo.count())]
        assert "bge-m3" in items
        assert "nomic-embed-text" in items
        assert "llama3" not in items

    def test_all_models_shown_when_none_match_filter(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Combo must show all models when none pass the embedding filter (fallback)."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")

        captured_callback: list[object] = []

        def capture_callback(provider_id: str, callback: object, *, parent: object = None) -> None:
            captured_callback.append(callback)

        controller.get_models_for_provider.side_effect = capture_callback
        controller.is_embedding_model.return_value = False  # nothing matches

        tab = _make_tab(mocker, controller)
        on_models = captured_callback[0]
        on_models(["llama3", "mistral"])  # type: ignore[operator]

        combo = tab._embedding_model_combo
        items = [combo.itemText(i) for i in range(combo.count())]
        assert "llama3" in items
        assert "mistral" in items
        assert len(items) == 2


# ---------------------------------------------------------------------------
# Model discovery caching
# ---------------------------------------------------------------------------


class TestDiscoveredModelsCaching:
    def test_discovered_models_cached_after_fetch(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """After _on_models fires, discovered list must be cached on the widget."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")

        captured_callback: list[object] = []

        def capture_callback(provider_id: str, callback: object, *, parent: object = None) -> None:
            captured_callback.append(callback)

        controller.get_models_for_provider.side_effect = capture_callback

        def classify(name: str) -> bool:
            return "embed" in name or "bge" in name

        controller.is_embedding_model.side_effect = classify

        tab = _make_tab(mocker, controller)
        on_models = captured_callback[0]
        on_models(["bge-m3", "llama3"])  # type: ignore[operator]

        assert tab._discovered_embedding_models == ["bge-m3"]


# ---------------------------------------------------------------------------
# Save warning behaviour
# ---------------------------------------------------------------------------


class TestSaveWarningDisabledProvider:
    def test_save_warns_when_embedding_provider_is_disabled(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """QMessageBox.warning fires when the embedding combo shows a provider that is disabled in the model.

        Scenario: provider starts enabled (so the combo includes it), user disables it in the
        table without reloading, then saves.  The model now has the provider disabled but the
        combo still holds its id.
        """
        enabled_cfg = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (enabled_cfg,), provider_id="p1")
        controller.save_providers_config_to_standard_path.return_value = True

        tab = _make_tab(mocker, controller)
        # Simulate the user disabling p1 in the table after init
        disabled_cfg = ProviderConfig(
            provider_id="p1",
            label="Provider p1",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="",
            api_key_raw="",
            enabled=False,
            base_url="http://localhost:11434/v1",
        )
        tab._model.update_config(0, disabled_cfg)
        tab._embedding_model_combo.setCurrentText("bge-m3")

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QMessageBox.warning") as mock_warn:
            tab._handle_save_changes()

        mock_warn.assert_called_once()

    def test_no_warning_when_embedding_provider_is_enabled(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """No QMessageBox.warning when the selected embedding provider is enabled."""
        cfg = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (cfg,), provider_id="p1")
        controller.save_providers_config_to_standard_path.return_value = True

        tab = _make_tab(mocker, controller)
        tab._embedding_model_combo.setCurrentText("bge-m3")

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QMessageBox.warning") as mock_warn:
            tab._handle_save_changes()

        mock_warn.assert_not_called()

    def test_no_warning_when_no_embedding_provider_selected(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """No warning when no embedding provider is selected (empty provider_id)."""
        controller = _make_controller(mocker, (), provider_id="", embedding_model="")
        controller.save_providers_config_to_standard_path.return_value = True

        tab = _make_tab(mocker, controller)

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QMessageBox.warning") as mock_warn:
            tab._handle_save_changes()

        mock_warn.assert_not_called()


class TestSaveWarning:
    def test_no_warning_when_model_in_discovered_list(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """No QMessageBox.information when the typed model IS in the discovered list."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")
        controller.save_providers_config_to_standard_path.return_value = True

        tab = _make_tab(mocker, controller)
        tab._discovered_embedding_models = ["nomic-embed-text"]
        tab._embedding_model_combo.setCurrentText("nomic-embed-text")

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QMessageBox.information") as mock_info:
            tab._handle_save_changes()

        mock_info.assert_not_called()

    def test_warning_shown_when_model_not_in_discovered_list(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """QMessageBox.information is called once when typed model is NOT in discovered list."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")
        controller.save_providers_config_to_standard_path.return_value = True

        tab = _make_tab(mocker, controller)
        tab._discovered_embedding_models = ["nomic-embed-text"]
        tab._embedding_model_combo.setCurrentText("custom-model")

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QMessageBox.information") as mock_info:
            tab._handle_save_changes()

        mock_info.assert_called_once()

    def test_no_warning_when_discovered_list_empty(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """No warning when the discovered list is empty (user may have skipped discovery)."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")
        controller.save_providers_config_to_standard_path.return_value = True

        tab = _make_tab(mocker, controller)
        tab._discovered_embedding_models = []
        tab._embedding_model_combo.setCurrentText("any-model")

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QMessageBox.information") as mock_info:
            tab._handle_save_changes()

        mock_info.assert_not_called()


# ---------------------------------------------------------------------------
# Registry reload subscription
# ---------------------------------------------------------------------------


class TestRegistryReloadSubscription:
    def test_populate_providers_called_on_registry_reloaded(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Calling _on_provider_registry_reloaded must invoke _populate_providers."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")

        tab = _make_tab(mocker, controller)

        call_count_before = controller.get_providers_config.call_count
        tab._on_provider_registry_reloaded()
        assert controller.get_providers_config.call_count > call_count_before


# ---------------------------------------------------------------------------
# Default model selection — auto-select first discovered when placeholder active
# ---------------------------------------------------------------------------


class TestDefaultModelSelection:
    def test_saved_model_selected_when_present_in_discovered_list(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """When saved model is in the discovered list, it must be selected."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1", embedding_model="nomic-embed-text")

        captured_callback: list[object] = []

        def capture_callback(provider_id: str, callback: object, *, parent: object = None) -> None:
            captured_callback.append(callback)

        controller.get_models_for_provider.side_effect = capture_callback

        def classify(name: str) -> bool:
            return "embed" in name or "nomic" in name

        controller.is_embedding_model.side_effect = classify

        tab = _make_tab(mocker, controller)
        on_models = captured_callback[0]
        on_models(["nomic-embed-text", "llama3"])  # type: ignore[operator]

        assert tab._embedding_model_combo.currentText() == "nomic-embed-text"

    def test_first_model_selected_when_saved_model_not_in_discovered_list(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """When saved model is not in the discovered list, the first available model is selected."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1", embedding_model="old-embed-model")

        captured_callback: list[object] = []

        def capture_callback(provider_id: str, callback: object, *, parent: object = None) -> None:
            captured_callback.append(callback)

        controller.get_models_for_provider.side_effect = capture_callback

        def classify(name: str) -> bool:
            return "embed" in name

        controller.is_embedding_model.side_effect = classify

        tab = _make_tab(mocker, controller)
        on_models = captured_callback[0]
        on_models(["nomic-embed-text", "llama3"])  # type: ignore[operator]

        assert tab._embedding_model_combo.currentText() == "nomic-embed-text"

    def test_show_all_check_repopulates_combo_with_all_models(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Toggling 'Show all models' causes provider models to reload without filtering."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")

        captured_callback: list[object] = []

        def capture_callback(provider_id: str, callback: object, *, parent: object = None) -> None:
            captured_callback.append(callback)

        controller.get_models_for_provider.side_effect = capture_callback

        # Only "nomic-embed-text" passes the embedding filter; "llama3" does not
        def classify(name: str) -> bool:
            return "embed" in name

        controller.is_embedding_model.side_effect = classify

        tab = _make_tab(mocker, controller)
        # First load: only embedding-classified models shown
        on_models_filtered = captured_callback[0]
        on_models_filtered(["nomic-embed-text", "llama3"])  # type: ignore[operator]

        combo = tab._embedding_model_combo
        items_filtered = [combo.itemText(i) for i in range(combo.count())]
        assert "nomic-embed-text" in items_filtered
        assert "llama3" not in items_filtered

        # Toggle "Show all models" checkbox — triggers another fetch
        tab._embedding_show_all_check.setChecked(True)
        on_models_all = captured_callback[-1]
        on_models_all(["nomic-embed-text", "llama3"])  # type: ignore[operator]

        items_all = [combo.itemText(i) for i in range(combo.count())]
        assert "nomic-embed-text" in items_all
        assert "llama3" in items_all


# ---------------------------------------------------------------------------
# Model fetch count during populate
# ---------------------------------------------------------------------------


class TestPopulateProvidersFetchCount:
    def test_populate_providers_fetches_models_exactly_once(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """_populate_providers must call get_models_for_provider exactly once when a provider is pre-selected."""
        cfg = _provider_config()
        controller = _make_controller(mocker, (cfg,), provider_id="p1")
        tab = _make_tab(mocker, controller)

        # Reset call count after __init__ (which calls _populate_providers once)
        controller.get_models_for_provider.reset_mock()

        tab._populate_providers()

        assert controller.get_models_for_provider.call_count == 1
