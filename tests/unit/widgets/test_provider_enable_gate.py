"""Unit tests for the enable-after-test gate in ProvidersTabWidget (Phase 2 / PR-T1)."""

from typing import cast
from unittest.mock import MagicMock

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
from ollama_llm_bench.backend.services.provider_health_checker import HealthCheckResult
from ollama_llm_bench.ui.widgets.settings.providers_tab_widget import ProvidersTabWidget

# ---------------------------------------------------------------------------
# Fixtures / helpers
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
        embedding=EmbeddingConfig(provider_id="p1", model=""),
    )
    mock.get_models_for_provider.return_value = None
    return mock


def _healthy_result(*, provider_id: str = "p1", model_count: int = 3) -> HealthCheckResult:
    return HealthCheckResult(
        provider_id=provider_id,
        is_healthy=True,
        model_count=model_count,
        error_message="",
        latency_ms=42,
    )


def _down_result(*, provider_id: str = "p1") -> HealthCheckResult:
    return HealthCheckResult(
        provider_id=provider_id,
        is_healthy=False,
        model_count=0,
        error_message="Connection refused",
        latency_ms=0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEnableAfterTest:
    def test_health_check_enables_provider_when_in_pending_enable(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """A healthy result auto-enables a provider that is in _pending_enable."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        tab._pending_enable.add("p1")

        tab._on_health_check_completed(_healthy_result(provider_id="p1", model_count=5))

        assert tab._model.is_enabled("p1") is True
        assert "p1" not in tab._pending_enable

    def test_health_check_enables_provider_on_warning_result_when_in_pending_enable(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """A warning health result (server reachable, no models) also auto-enables when in _pending_enable."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        tab._pending_enable.add("p1")

        tab._on_health_check_completed(_healthy_result(provider_id="p1", model_count=0))

        assert tab._model.is_enabled("p1") is True

    def test_down_result_does_not_enable_provider(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """A failed health check does not enable a provider even if in _pending_enable."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        tab._pending_enable.add("p1")

        tab._on_health_check_completed(_down_result(provider_id="p1"))

        assert tab._model.is_enabled("p1") is False
        assert "p1" not in tab._pending_enable

    def test_already_enabled_provider_set_enable_not_called(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """When the provider is already enabled, set_enable must not be called again."""
        config = _provider_config(provider_id="p1", enabled=True)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        spy = mocker.spy(tab._model, "set_enable")

        tab._on_health_check_completed(_healthy_result(provider_id="p1", model_count=3))

        spy.assert_not_called()

    def test_non_matching_provider_id_leaves_provider_disabled(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """A result for an unknown provider_id leaves all providers untouched."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        tab._on_health_check_completed(_healthy_result(provider_id="other", model_count=3))

        assert tab._model.is_enabled("p1") is False


class TestLastHealthTracking:
    def test_last_health_stored_on_completion(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """_last_health is populated after a health check result arrives."""
        config = _provider_config(provider_id="p1", enabled=True)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        result = _healthy_result(provider_id="p1", model_count=2)
        tab._on_health_check_completed(result)

        assert tab._last_health["p1"] is result

    def test_last_health_overwritten_on_retest(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """A second result for the same provider_id overwrites the first in _last_health."""
        config = _provider_config(provider_id="p1", enabled=True)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        first = _healthy_result(provider_id="p1", model_count=2)
        second = _down_result(provider_id="p1")
        tab._on_health_check_completed(first)
        tab._on_health_check_completed(second)

        assert tab._last_health["p1"] is second

    def test_last_health_stores_down_result(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Down results are stored in _last_health just like healthy ones."""
        config = _provider_config(provider_id="p1", enabled=True)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        result = _down_result(provider_id="p1")
        tab._on_health_check_completed(result)

        assert tab._last_health["p1"] is result

    def test_last_health_not_updated_for_non_health_check_result(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Passing a non-HealthCheckResult object leaves _last_health empty."""
        config = _provider_config(provider_id="p1", enabled=True)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        tab._on_health_check_completed("not-a-result")

        assert "p1" not in tab._last_health


class TestEnableGate:
    def test_enable_toggle_without_prior_test_runs_health_check(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Enabling a provider with no prior health result triggers a health check and reverts enable."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        mock_run = mocker.patch.object(tab, "_run_health_check_for")

        tab._gate_enable("p1")

        assert tab._model.is_enabled("p1") is False
        assert "p1" in tab._pending_enable
        mock_run.assert_called_once_with("p1")

    def test_enable_toggle_after_failed_test_blocks_enable(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """A provider with a failing health result cannot be freely enabled."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        tab._last_health["p1"] = _down_result(provider_id="p1")
        mock_run = mocker.patch.object(tab, "_run_health_check_for")

        tab._gate_enable("p1")

        assert tab._model.is_enabled("p1") is False
        assert "p1" in tab._pending_enable
        mock_run.assert_called_once_with("p1")

    def test_enable_toggle_after_passing_test_is_allowed(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """A provider with a passing health result can be enabled without a new test."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        tab._last_health["p1"] = _healthy_result(provider_id="p1", model_count=3)
        mock_run = mocker.patch.object(tab, "_run_health_check_for")

        tab._gate_enable("p1")

        mock_run.assert_not_called()
        assert "p1" not in tab._pending_enable

    def test_pending_enable_set_cleared_on_healthy_result(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """_pending_enable is cleared after _on_health_check_completed fires with a healthy result."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        tab._pending_enable.add("p1")

        tab._on_health_check_completed(_healthy_result(provider_id="p1", model_count=3))

        assert "p1" not in tab._pending_enable

    def test_pending_enable_set_cleared_on_down_result(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """_pending_enable is cleared even when the health check fails."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        tab._pending_enable.add("p1")

        tab._on_health_check_completed(_down_result(provider_id="p1"))

        assert "p1" not in tab._pending_enable

    def test_health_check_without_pending_enable_does_not_auto_enable(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """A healthy result for a provider NOT in _pending_enable does not auto-enable it."""
        config = _provider_config(provider_id="p1", enabled=False)
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        # _pending_enable is empty by default

        tab._on_health_check_completed(_healthy_result(provider_id="p1", model_count=3))

        assert tab._model.is_enabled("p1") is False
