"""Unit tests for ProvidersTabWidget auto-health-check behaviour (Brief 08)."""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import LLMProviderApi
from ollama_llm_bench.backend.core.models import (
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.ui.widgets.settings.providers_tab_widget import ProvidersTabWidget

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _provider_config(
    *,
    provider_id: str = "p1",
    enabled: bool = True,
    api_key_raw: str = "plain-key",
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        label=f"Provider {provider_id}",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key=api_key_raw if not api_key_raw.startswith("${") else "",
        api_key_raw=api_key_raw,
        enabled=enabled,
        base_url="http://localhost:11434/v1",
    )


def _make_controller(mocker: MockerFixture, providers: tuple[ProviderConfig, ...]) -> MagicMock:
    mock = cast(MagicMock, mocker.Mock(spec=SettingsWidgetControllerApi))
    mock.get_providers_config.return_value = ProvidersConfig(
        providers=providers,
        embedding=EmbeddingConfig(provider_id="p1", model="bge-m3"),
    )
    mock.get_models_for_provider.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunInitialHealthChecks:
    def test_spawns_runnable_for_enabled_provider(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Enabled provider with plain API key gets a QThreadPool start call."""
        config = _provider_config(provider_id="p1", enabled=True, api_key_raw="plain-key")
        controller = _make_controller(mocker, (config,))
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        controller.get_provider_instance.return_value = mock_provider

        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QThreadPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.globalInstance.return_value = mock_pool
            tab._run_initial_health_checks()

        mock_pool.start.assert_called_once()

    def test_skips_disabled_provider_and_sets_unknown(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Disabled provider must not trigger a network call; its dot is set to unknown."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))

        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QThreadPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.globalInstance.return_value = mock_pool
            tab._run_initial_health_checks()

        mock_pool.start.assert_not_called()
        assert tab._model.get_health_state("p1") == "unknown"

    def test_sets_down_for_unset_env_var_without_network(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Provider with unresolved env-var key must be marked down immediately, no thread spawned."""
        monkeypatch.delenv("MISSING_VAR_BRIEF08_XYZ", raising=False)
        config = _provider_config(
            provider_id="p1",
            enabled=True,
            api_key_raw="${MISSING_VAR_BRIEF08_XYZ}",
        )
        controller = _make_controller(mocker, (config,))

        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QThreadPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.globalInstance.return_value = mock_pool
            tab._run_initial_health_checks()

        mock_pool.start.assert_not_called()
        assert tab._model.get_health_state("p1") == "down"

    def test_does_not_spawn_for_enabled_provider_when_env_var_is_set(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Provider with resolved env-var key proceeds to network check (thread spawned)."""
        monkeypatch.setenv("MY_SET_KEY_BRIEF08", "sk-real")
        config = _provider_config(
            provider_id="p1",
            enabled=True,
            api_key_raw="${MY_SET_KEY_BRIEF08}",
        )
        controller = _make_controller(mocker, (config,))
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        controller.get_provider_instance.return_value = mock_provider

        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QThreadPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.globalInstance.return_value = mock_pool
            tab._run_initial_health_checks()

        mock_pool.start.assert_called_once()


class TestRunHealthCheckForDedup:
    def test_deduplicates_inflight_requests(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Second call to _run_health_check_for for the same provider_id is silently ignored."""
        config = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (config,))
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        controller.get_provider_instance.return_value = mock_provider

        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        tab._in_flight.add("p1")

        with patch("ollama_llm_bench.ui.widgets.settings.providers_tab_widget.QThreadPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.globalInstance.return_value = mock_pool
            tab._run_health_check_for("p1")

        mock_pool.start.assert_not_called()


class TestOnTestRequested:
    def test_delegates_to_run_health_check_for(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """_on_test_requested must reset the card and call _run_health_check_for."""
        config = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (config,))

        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        mock_run_check = mocker.patch.object(tab, "_run_health_check_for")

        tab._on_test_requested(0)

        mock_run_check.assert_called_once_with("p1")

    def test_sets_testing_state_before_running_check(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Model health must be set to 'testing' state before the runnable is spawned."""
        config = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (config,))

        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        mock_set_health = mocker.patch.object(tab._model, "set_health")
        mocker.patch.object(tab, "_run_health_check_for")

        tab._on_test_requested(0)

        mock_set_health.assert_called_once_with("p1", "testing", "Testing…")
