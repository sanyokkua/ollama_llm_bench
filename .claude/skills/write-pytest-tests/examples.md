# Write Pytest Tests — Test Examples

Complete test templates for Ollama LLM Bench. See [SKILL.md](SKILL.md) for rules.

---

## Unit Test: Service with Mocked Dependencies

```python
import pytest
from unittest.mock import MagicMock

from ollama_llm_bench.core.interfaces import DataApi, EventBus
from ollama_llm_bench.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
)
from ollama_llm_bench.services.app_result_api import AppResultApi
from ollama_llm_bench.services.sq_lite_data_api import SqLiteDataApi


@pytest.fixture
def mock_data_api() -> MagicMock:
    return MagicMock(spec=SqLiteDataApi)


@pytest.fixture
def result_api(mock_data_api: MagicMock) -> AppResultApi:
    return AppResultApi(data_api=mock_data_api)


def test_retrieve_avg_results_returns_empty_for_no_results(
    result_api: AppResultApi,
    mock_data_api: MagicMock,
) -> None:
    # Arrange
    mock_data_api.retrieve_benchmark_results_for_run.return_value = []

    # Act
    results = result_api.retrieve_avg_benchmark_results_for_run(run_id=1)

    # Assert
    assert results == []
    mock_data_api.retrieve_benchmark_results_for_run.assert_called_once_with(1)


def test_retrieve_avg_results_computes_averages(
    result_api: AppResultApi,
    mock_data_api: MagicMock,
) -> None:
    # Arrange
    mock_data_api.retrieve_benchmark_results_for_run.return_value = [
        BenchmarkResult(
            result_id=1,
            run_id=1,
            task_id="task1",
            model_name="llama3",
            status=BenchmarkResultStatus.COMPLETED,
            time_taken_ms=1000,
            tokens_generated=50,
            evaluation_score=8.0,
        ),
        BenchmarkResult(
            result_id=2,
            run_id=1,
            task_id="task2",
            model_name="llama3",
            status=BenchmarkResultStatus.COMPLETED,
            time_taken_ms=2000,
            tokens_generated=100,
            evaluation_score=6.0,
        ),
    ]

    # Act
    results = result_api.retrieve_avg_benchmark_results_for_run(run_id=1)

    # Assert
    assert len(results) == 1
    assert results[0].model_name == "llama3"
    assert results[0].avg_score == pytest.approx(7.0)
```

---

## Integration Test: Real SQLite Database

```python
import pytest
from pathlib import Path

from ollama_llm_bench.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
)
from ollama_llm_bench.services.sq_lite_data_api import SqLiteDataApi


@pytest.fixture
def data_api(tmp_path: Path) -> SqLiteDataApi:
    db_path = tmp_path / "test.sqlite"
    return SqLiteDataApi(db_path)


def test_create_and_retrieve_benchmark_run(data_api: SqLiteDataApi) -> None:
    # Arrange
    run = BenchmarkRun(
        run_id=0,
        timestamp="2024-01-15T10:30:00",
        judge_model="llama3",
        status=BenchmarkRunStatus.NOT_COMPLETED,
    )

    # Act
    run_id = data_api.create_benchmark_run(run)
    retrieved = data_api.retrieve_benchmark_run(run_id)

    # Assert
    assert retrieved.run_id == run_id
    assert retrieved.judge_model == "llama3"
    assert retrieved.status == BenchmarkRunStatus.NOT_COMPLETED


def test_retrieve_results_filtered_by_status(data_api: SqLiteDataApi) -> None:
    # Arrange
    run = BenchmarkRun(
        run_id=0,
        timestamp="2024-01-15",
        judge_model="llama3",
        status=BenchmarkRunStatus.NOT_COMPLETED,
    )
    run_id = data_api.create_benchmark_run(run)

    completed = BenchmarkResult(
        result_id=0,
        run_id=run_id,
        task_id="task1",
        model_name="llama3",
        status=BenchmarkResultStatus.COMPLETED,
    )
    pending = BenchmarkResult(
        result_id=0,
        run_id=run_id,
        task_id="task2",
        model_name="llama3",
        status=BenchmarkResultStatus.NOT_COMPLETED,
    )
    data_api.create_benchmark_result(completed)
    data_api.create_benchmark_result(pending)

    # Act
    results = data_api.retrieve_benchmark_results_for_run_with_status(
        run_id=run_id,
        status=BenchmarkResultStatus.COMPLETED,
    )

    # Assert
    assert len(results) == 1
    assert results[0].task_id == "task1"
```

---

## Unit Test: Controller with EventBus

```python
import pytest
from unittest.mock import MagicMock, call

from ollama_llm_bench.core.interfaces import DataApi, EventBus
from ollama_llm_bench.qt_classes.qt_event_bus import QtEventBus
from ollama_llm_bench.services.sq_lite_data_api import SqLiteDataApi


@pytest.fixture
def mock_event_bus() -> MagicMock:
    return MagicMock(spec=QtEventBus)


@pytest.fixture
def mock_data_api() -> MagicMock:
    return MagicMock(spec=SqLiteDataApi)


def test_controller_subscribes_to_events_on_init(
    mock_event_bus: MagicMock,
    mock_data_api: MagicMock,
) -> None:
    # Act
    from ollama_llm_bench.ui.controllers.result_widget_controller import ResultWidgetController
    controller = ResultWidgetController(
        event_bus=mock_event_bus,
        data_api=mock_data_api,
        table_serializer=MagicMock(),
    )

    # Assert
    mock_event_bus.subscribe_to_run_id_changed.assert_called_once()
```

---

## Parametrized Test: Utility Function

```python
import pytest

from ollama_llm_bench.utils.text_utils import parse_judge_response


@pytest.mark.parametrize(
    ("response_text", "expected_error", "expected_grade"),
    [
        ("Grade: 10/10\nReason: Perfect answer", False, 10.0),
        ("Grade: 0/10\nReason: Completely wrong", False, 0.0),
        ("Grade: 5/10\nReason: Partial", False, 5.0),
        ("This is not a valid judge response", True, None),
        ("", True, None),
    ],
    ids=[
        "perfect_score",
        "zero_score",
        "partial_score",
        "invalid_format",
        "empty_response",
    ],
)
def test_parse_judge_response(
    response_text: str,
    expected_error: bool,
    expected_grade: float | None,
) -> None:
    # Act
    has_error, grade, reason = parse_judge_response(response_text)

    # Assert
    assert has_error == expected_error
    if not expected_error:
        assert grade == expected_grade
        assert reason is not None
```

---

## Fixture: Conftest.py Shared Fixtures

```python
"""Shared test fixtures for Ollama LLM Bench."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from ollama_llm_bench.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
)
from ollama_llm_bench.services.ollama_llm_api import OllamaApi
from ollama_llm_bench.services.sq_lite_data_api import SqLiteDataApi
from ollama_llm_bench.qt_classes.qt_event_bus import QtEventBus


@pytest.fixture
def mock_llm_api() -> MagicMock:
    """Mock OllamaApi with spec enforcement."""
    return MagicMock(spec=OllamaApi)


@pytest.fixture
def mock_data_api() -> MagicMock:
    """Mock SqLiteDataApi with spec enforcement."""
    return MagicMock(spec=SqLiteDataApi)


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Mock QtEventBus with spec enforcement."""
    return MagicMock(spec=QtEventBus)


@pytest.fixture
def sample_run() -> BenchmarkRun:
    """Create a sample benchmark run for testing."""
    return BenchmarkRun(
        run_id=1,
        timestamp="2024-01-15T10:30:00",
        judge_model="llama3",
        status=BenchmarkRunStatus.NOT_COMPLETED,
    )


@pytest.fixture
def sample_result(sample_run: BenchmarkRun) -> BenchmarkResult:
    """Create a sample benchmark result for testing."""
    return BenchmarkResult(
        result_id=1,
        run_id=sample_run.run_id,
        task_id="task_001",
        model_name="llama3",
        status=BenchmarkResultStatus.COMPLETED,
        llm_response="Sample response",
        time_taken_ms=1500,
        tokens_generated=75,
        evaluation_score=7.5,
    )
```
