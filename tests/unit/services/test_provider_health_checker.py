"""Unit tests for ProviderHealthChecker."""

import threading

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import LLMProviderApi
from ollama_llm_bench.backend.core.models import ModelDescriptor
from ollama_llm_bench.backend.services.provider_health_checker import HealthCheckResult, ProviderHealthChecker


def _fake_descriptor(provider_id: str = "p1", model_name: str = "llama3") -> ModelDescriptor:
    return ModelDescriptor(
        provider_id=provider_id,
        provider_type="openai_compatible",
        model_name=model_name,
        display_label=model_name,
    )


class TestProviderHealthChecker:
    def test_check_success_returns_is_healthy_true_with_model_count_and_latency(self, mocker: MockerFixture) -> None:
        """When get_available_models returns models, result is healthy with correct count and non-negative latency."""
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p1"
        mock_provider.get_available_models.return_value = [_fake_descriptor(), _fake_descriptor(model_name="qwen")]

        checker = ProviderHealthChecker()
        result: HealthCheckResult = checker.check(mock_provider)

        assert result.is_healthy is True
        assert result.model_count == 2
        assert result.latency_ms >= 0
        assert result.error_message == ""
        assert result.provider_id == "p1"

    def test_check_failure_returns_is_healthy_false_with_error_message(self, mocker: MockerFixture) -> None:
        """When get_available_models raises, result is not healthy and carries the error message."""
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p2"
        mock_provider.get_available_models.side_effect = RuntimeError("connection refused")

        checker = ProviderHealthChecker()
        result: HealthCheckResult = checker.check(mock_provider)

        assert result.is_healthy is False
        assert "connection refused" in result.error_message
        assert result.model_count == 0
        assert result.latency_ms == 0

    @pytest.mark.slow
    def test_check_timeout_returns_is_healthy_false(self, mocker: MockerFixture) -> None:
        """When get_available_models blocks indefinitely, the 5-second timeout fires and result is not healthy."""
        barrier = threading.Event()

        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p3"

        def _block() -> list[ModelDescriptor]:
            barrier.wait(timeout=60)
            return []

        mock_provider.get_available_models.side_effect = _block

        checker = ProviderHealthChecker()
        result: HealthCheckResult = checker.check(mock_provider)

        # Unblock the background thread so it can finish cleanly
        barrier.set()

        assert result.is_healthy is False
