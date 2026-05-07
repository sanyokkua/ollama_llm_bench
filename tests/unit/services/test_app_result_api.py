"""Unit tests for AppResultApi — V2 field name correctness and aggregation logic."""

from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import DataApi
from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkResultStatus
from ollama_llm_bench.backend.services.app_result_api import AppResultApi


@pytest.fixture
def mock_data_api(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=DataApi))


@pytest.fixture
def service(mock_data_api: MagicMock) -> AppResultApi:
    return AppResultApi(data_api=cast(DataApi, mock_data_api))


def _make_result(
    *,
    model_name: str = "llama3:8b",
    task_id: str = "task_1",
    total_time_ms: int | None = 1000,
    completion_tokens: int | None = 50,
    judge_score: float | None = 8.0,
    judge_reasoning: str | None = "Good answer",
    status: BenchmarkResultStatus = BenchmarkResultStatus.COMPLETED,
) -> BenchmarkResult:
    return BenchmarkResult(
        model_name=model_name,
        task_id=task_id,
        total_time_ms=total_time_ms,
        completion_tokens=completion_tokens,
        judge_score=judge_score,
        judge_reasoning=judge_reasoning,
        status=status,
    )


class TestRetrieveAvgBenchmarkResultsForRun:
    def test_invalid_run_id_returns_empty_without_calling_data_api(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Act
        result = service.retrieve_avg_benchmark_results_for_run(0)

        # Assert
        assert result == []
        mock_data_api.retrieve_benchmark_results_for_run.assert_not_called()

    def test_negative_run_id_returns_empty(self, service: AppResultApi) -> None:
        result = service.retrieve_avg_benchmark_results_for_run(-5)
        assert result == []

    def test_empty_results_returns_empty(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Arrange
        mock_data_api.retrieve_benchmark_results_for_run.return_value = []
        # Act
        result = service.retrieve_avg_benchmark_results_for_run(1)

        # Assert
        assert result == []

    def test_single_model_averages_computed_correctly(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Arrange
        mock_data_api.retrieve_benchmark_results_for_run.return_value = [
            _make_result(model_name="llama3:8b", total_time_ms=1000, completion_tokens=50, judge_score=8.0),
            _make_result(model_name="llama3:8b", total_time_ms=2000, completion_tokens=100, judge_score=6.0),
        ]

        # Act
        items = service.retrieve_avg_benchmark_results_for_run(1)

        # Assert
        assert len(items) == 1
        item = items[0]
        assert item.model_name == "llama3:8b"
        assert item.avg_time_ms == 1500.0
        assert item.avg_score == 7.0
        # tokens_per_second = (50+100) / (1000+2000) * 1000 = 150/3000*1000 = 50.0
        assert item.avg_tokens_per_second == pytest.approx(50.0)

    def test_two_models_produce_two_items(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Arrange
        mock_data_api.retrieve_benchmark_results_for_run.return_value = [
            _make_result(model_name="llama3:8b"),
            _make_result(model_name="mistral:7b"),
        ]

        # Act
        items = service.retrieve_avg_benchmark_results_for_run(1)

        # Assert
        assert len(items) == 2
        model_names = {i.model_name for i in items}
        assert model_names == {"llama3:8b", "mistral:7b"}

    def test_none_metric_fields_handled_without_crash(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Arrange — all optional fields are None
        mock_data_api.retrieve_benchmark_results_for_run.return_value = [
            _make_result(model_name="llama3:8b", total_time_ms=None, completion_tokens=None, judge_score=None),
        ]

        # Act
        items = service.retrieve_avg_benchmark_results_for_run(1)

        # Assert — should not raise; defaults to 0
        assert len(items) == 1
        assert items[0].avg_time_ms == 0.0
        assert items[0].avg_score == 0.0
        assert items[0].avg_tokens_per_second == 0.0


class TestRetrieveDetailedBenchmarkResultsForRun:
    def test_invalid_run_id_returns_empty_without_calling_data_api(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Act
        result = service.retrieve_detailed_benchmark_results_for_run(0)

        # Assert
        assert result == []
        mock_data_api.retrieve_benchmark_results_for_run.assert_not_called()

    def test_empty_results_returns_empty(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Arrange
        mock_data_api.retrieve_benchmark_results_for_run.return_value = []
        # Act
        result = service.retrieve_detailed_benchmark_results_for_run(1)

        # Assert
        assert result == []

    def test_result_fields_mapped_to_summary_item_correctly(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Arrange
        mock_data_api.retrieve_benchmark_results_for_run.return_value = [
            _make_result(
                model_name="llama3:8b",
                task_id="task_42",
                total_time_ms=2000,
                completion_tokens=80,
                judge_score=9.0,
                judge_reasoning="Excellent",
                status=BenchmarkResultStatus.COMPLETED,
            )
        ]

        # Act
        items = service.retrieve_detailed_benchmark_results_for_run(1)

        # Assert
        assert len(items) == 1
        item = items[0]
        assert item.model_name == "llama3:8b"
        assert item.task_id == "task_42"
        assert item.time_ms == 2000
        assert item.tokens == 80
        assert item.score == pytest.approx(9.0)
        assert item.score_reason == "Excellent"
        # tokens_per_second = 80 / 2000 * 1000 = 40.0
        assert item.tokens_per_second == pytest.approx(40.0)

    def test_none_total_time_ms_gives_zero_time_and_no_division(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Arrange
        mock_data_api.retrieve_benchmark_results_for_run.return_value = [
            _make_result(total_time_ms=None, completion_tokens=50)
        ]

        # Act
        items = service.retrieve_detailed_benchmark_results_for_run(1)

        # Assert — no ZeroDivisionError; defaults applied
        assert len(items) == 1
        assert items[0].time_ms == 0
        assert items[0].tokens_per_second == pytest.approx(0.0)

    def test_none_judge_fields_default_to_zero_and_empty(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Arrange
        mock_data_api.retrieve_benchmark_results_for_run.return_value = [
            _make_result(judge_score=None, judge_reasoning=None)
        ]

        # Act
        items = service.retrieve_detailed_benchmark_results_for_run(1)

        # Assert
        assert items[0].score == pytest.approx(0.0)
        assert items[0].score_reason == ""

    def test_multiple_results_all_returned(
        self,
        service: AppResultApi,
        mock_data_api: MagicMock,
    ) -> None:
        # Arrange
        mock_data_api.retrieve_benchmark_results_for_run.return_value = [
            _make_result(model_name="llama3:8b", task_id="task_1"),
            _make_result(model_name="llama3:8b", task_id="task_2"),
            _make_result(model_name="mistral:7b", task_id="task_1"),
        ]

        # Act
        items = service.retrieve_detailed_benchmark_results_for_run(1)

        # Assert
        assert len(items) == 3
