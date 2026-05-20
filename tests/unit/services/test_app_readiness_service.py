"""Unit tests for AppReadinessService."""

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    EmbeddingProviderApi,
    LLMProviderApi,
    ProviderRegistryApi,
)
from ollama_llm_bench.backend.core.models import AppReadinessChangedEvent, ReadinessVerdict, RunMode
from ollama_llm_bench.backend.services.app_readiness_service import AppReadinessService
from ollama_llm_bench.backend.services.provider_health_checker import HealthCheckResult, ProviderHealthChecker


@pytest.fixture
def mock_registry(mocker: MockerFixture) -> object:
    return mocker.Mock(spec=ProviderRegistryApi)


@pytest.fixture
def mock_embedding(mocker: MockerFixture) -> object:
    return mocker.Mock(spec=EmbeddingProviderApi)


@pytest.fixture
def mock_settings(mocker: MockerFixture) -> object:
    return mocker.Mock(spec=AppSettingsServiceApi)


@pytest.fixture
def mock_health_checker(mocker: MockerFixture) -> object:
    return mocker.Mock(spec=ProviderHealthChecker)


@pytest.fixture
def service(
    mock_registry: object,
    mock_embedding: object,
    mock_settings: object,
    mock_health_checker: object,
) -> AppReadinessService:
    return AppReadinessService(
        provider_registry=mock_registry,  # type: ignore[arg-type]
        embedding_provider=mock_embedding,  # type: ignore[arg-type]
        app_settings=mock_settings,  # type: ignore[arg-type]
        health_checker=mock_health_checker,  # type: ignore[arg-type]
    )


class TestVerdictFor:
    def test_verdict_for_performance_mode_no_models_is_not_ready(
        self,
        service: AppReadinessService,
    ) -> None:
        # Arrange
        snapshot = AppReadinessChangedEvent(
            has_any_models=False,
            embedding_ok=True,
            embedding_error="",
            unhealthy_providers=(),
        )

        # Act
        verdict: ReadinessVerdict = service.verdict_for(RunMode.PERFORMANCE, snapshot)

        # Assert
        assert verdict.is_ready is False
        assert verdict.severity == "error"
        combined_issues = " ".join(verdict.issues).lower()
        assert "models" in combined_issues

    def test_verdict_for_performance_mode_with_models_is_ready(
        self,
        service: AppReadinessService,
    ) -> None:
        # Arrange
        snapshot = AppReadinessChangedEvent(
            has_any_models=True,
            embedding_ok=False,
            embedding_error="not found",
            unhealthy_providers=(),
        )

        # Act
        verdict: ReadinessVerdict = service.verdict_for(RunMode.PERFORMANCE, snapshot)

        # Assert
        assert verdict.is_ready is True
        assert verdict.severity == "ok"

    def test_verdict_for_full_grading_no_embedding_is_not_ready(
        self,
        service: AppReadinessService,
    ) -> None:
        # Arrange
        snapshot = AppReadinessChangedEvent(
            has_any_models=True,
            embedding_ok=False,
            embedding_error="bge-m3 not found",
            unhealthy_providers=(),
        )

        # Act
        verdict: ReadinessVerdict = service.verdict_for(RunMode.FULL_GRADING, snapshot)

        # Assert
        assert verdict.is_ready is False
        assert verdict.severity == "error"
        combined_issues = " ".join(verdict.issues).lower()
        assert "embedding" in combined_issues

    def test_verdict_for_prompt_eval_no_embedding_is_not_ready(
        self,
        service: AppReadinessService,
    ) -> None:
        # Arrange
        snapshot = AppReadinessChangedEvent(
            has_any_models=True,
            embedding_ok=False,
            embedding_error="bge-m3 not found",
            unhealthy_providers=(),
        )

        # Act
        verdict: ReadinessVerdict = service.verdict_for(RunMode.PROMPT_EVAL, snapshot)

        # Assert
        assert verdict.is_ready is False
        assert verdict.severity == "error"

    def test_verdict_for_full_grading_all_ok(
        self,
        service: AppReadinessService,
    ) -> None:
        # Arrange
        snapshot = AppReadinessChangedEvent(
            has_any_models=True,
            embedding_ok=True,
            embedding_error="",
            unhealthy_providers=(),
        )

        # Act
        verdict: ReadinessVerdict = service.verdict_for(RunMode.FULL_GRADING, snapshot)

        # Assert
        assert verdict.is_ready is True
        assert verdict.severity == "ok"
        assert verdict.issues == ()

    def test_verdict_for_degraded_providers_but_models_exist_is_ready_with_warning(
        self,
        service: AppReadinessService,
    ) -> None:
        # Arrange
        snapshot = AppReadinessChangedEvent(
            has_any_models=True,
            embedding_ok=True,
            embedding_error="",
            unhealthy_providers=("ollama_local",),
        )

        # Act
        verdict: ReadinessVerdict = service.verdict_for(RunMode.SPEED, snapshot)

        # Assert
        assert verdict.is_ready is True
        assert verdict.severity == "warning"
        combined_issues = " ".join(verdict.issues)
        assert "ollama_local" in combined_issues


class TestComputeSnapshot:
    def test_compute_snapshot_healthy_provider_sets_has_any_models(
        self,
        service: AppReadinessService,
        mock_registry: object,
        mock_settings: object,
        mock_health_checker: object,
        mocker: MockerFixture,
    ) -> None:
        # Arrange
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.provider_id = "p1"
        mock_registry.get_enabled_providers.return_value = [mock_provider]  # type: ignore[attr-defined]
        mock_health_checker.check.return_value = HealthCheckResult(  # type: ignore[attr-defined]
            provider_id="p1",
            is_healthy=True,
            model_count=3,
            error_message="",
            latency_ms=10,
        )
        mock_settings.get_bool.return_value = False  # type: ignore[attr-defined]

        # Act
        snapshot: AppReadinessChangedEvent = service.compute_snapshot()

        # Assert
        assert snapshot.has_any_models is True
        assert snapshot.embedding_ok is True

    def test_compute_snapshot_embedding_failure_sets_embedding_error(
        self,
        service: AppReadinessService,
        mock_registry: object,
        mock_settings: object,
        mock_embedding: object,
    ) -> None:
        # Arrange
        mock_registry.get_enabled_providers.return_value = []  # type: ignore[attr-defined]
        mock_settings.get_bool.return_value = True  # type: ignore[attr-defined]
        mock_embedding.encode.side_effect = RuntimeError("bge-m3 not found")  # type: ignore[attr-defined]

        # Act
        snapshot: AppReadinessChangedEvent = service.compute_snapshot()

        # Assert
        assert snapshot.embedding_ok is False
        assert "bge-m3 not found" in snapshot.embedding_error
