"""Unit tests for ProviderHealthChecker."""

import threading

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import LLMProviderApi
from ollama_llm_bench.backend.core.models import HealthProbeResult
from ollama_llm_bench.backend.services.provider_health_checker import HealthCheckResult, ProviderHealthChecker


class TestProviderHealthChecker:
    def test_check_reachable_with_models_returns_healthy_with_count(self, mocker: MockerFixture) -> None:
        """When probe_health returns reachable=True with models, result is healthy with correct count."""
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p1"
        mock_provider.probe_health.return_value = HealthProbeResult(reachable=True, model_count_observed=3)

        result: HealthCheckResult = ProviderHealthChecker().check(mock_provider)

        assert result.is_healthy is True
        assert result.model_count == 3
        assert result.latency_ms >= 0
        assert result.error_message == ""
        assert result.provider_id == "p1"

    def test_check_reachable_no_models_returns_healthy_with_zero_count(self, mocker: MockerFixture) -> None:
        """When probe_health returns reachable=True with zero models, is_healthy=True and model_count=0."""
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p2"
        mock_provider.probe_health.return_value = HealthProbeResult(reachable=True, model_count_observed=0)

        result: HealthCheckResult = ProviderHealthChecker().check(mock_provider)

        assert result.is_healthy is True
        assert result.model_count == 0
        assert result.error_message == ""

    def test_check_connection_refused_returns_unhealthy_with_error(self, mocker: MockerFixture) -> None:
        """When probe_health returns reachable=False, result is not healthy and carries the error message."""
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p3"
        mock_provider.probe_health.return_value = HealthProbeResult(reachable=False, error_message="Connection refused")

        result: HealthCheckResult = ProviderHealthChecker().check(mock_provider)

        assert result.is_healthy is False
        assert "Connection refused" in result.error_message
        assert result.model_count == 0

    def test_check_auth_error_returns_unhealthy_with_auth_message(self, mocker: MockerFixture) -> None:
        """When probe_health returns an auth error, result carries the authentication failure message."""
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p4"
        mock_provider.probe_health.return_value = HealthProbeResult(
            reachable=False, error_message="Authentication failed — check API key."
        )

        result: HealthCheckResult = ProviderHealthChecker().check(mock_provider)

        assert result.is_healthy is False
        assert "Authentication" in result.error_message

    def test_check_probe_raises_returns_unhealthy(self, mocker: MockerFixture) -> None:
        """When probe_health raises an unexpected exception, result is not healthy."""
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p5"
        mock_provider.probe_health.side_effect = RuntimeError("unexpected error")

        result: HealthCheckResult = ProviderHealthChecker().check(mock_provider)

        assert result.is_healthy is False
        assert "unexpected error" in result.error_message
        assert result.model_count == 0

    @pytest.mark.slow
    def test_check_timeout_returns_unhealthy_with_timeout_message(self, mocker: MockerFixture) -> None:
        """When probe_health blocks indefinitely, the 5-second timeout fires and result is not healthy."""
        barrier = threading.Event()

        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p6"

        def _block() -> HealthProbeResult:
            barrier.wait(timeout=60)
            return HealthProbeResult(reachable=True)

        mock_provider.probe_health.side_effect = _block

        result: HealthCheckResult = ProviderHealthChecker().check(mock_provider)
        barrier.set()

        assert result.is_healthy is False
        assert "timed out" in result.error_message
