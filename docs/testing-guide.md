# Testing Guide

> **Current state**: the `tests/` directory does **not** exist. `uv run pytest` currently collects zero tests. Coverage is **0 %**.
> `pyproject.toml` is already configured for the test pyramid described here — once the first test file is created, the tooling will pick it up automatically.

This document describes the intended test layout, fixtures, and mocking conventions.
It is the standard to adopt when test writing begins.

## Configuration (Already in Place)

From `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = [
    "-q", "--tb=short", "--no-header",
    "-p", "no:warnings",
    "--import-mode=importlib",
    "--strict-markers", "--strict-config",
]
markers = [
    "unit: Unit tests (fast, isolated)",
    "integration: Integration tests (require real resources)",
    "slow: Tests exceeding standard time budget",
]

[tool.coverage.run]
source = ["src"]
branch = true
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
fail_under = 80
```

- **`pythonpath = ["src"]`** means tests import the package as `ollama_llm_bench.*` without needing an editable install.
- **`--strict-markers`** rejects any unknown `@pytest.mark.*` decorator — add markers to the config before using them.
- **Branch coverage** is enabled; **80 %** is the target.

## Test Pyramid

| Tier | Share of tests | Characteristics |
|---|---|---|
| Unit | 70 – 80 % | Fast (< 1 s each). All external deps mocked via `spec=`. Target: every service, controller, and util function. |
| Integration | 15 – 25 % | Use real filesystems (`tmp_path`), real SQLite databases, real YAML parsing. Up to 30 s per test. |
| E2E / UI | 5 – 10 % | Optional. Would require `pytest-qt` — not currently in dependencies. |

Focus **unit** testing on:

| Target | Why |
|---|---|
| `utils/text_utils.py:parse_judge_response` | Pure function, many edge cases, high fan-in |
| `services/app_result_api.py` | Aggregation math — property-based tests are ideal |
| `services/simple_prompt_builder_api.py` | Template substitution is easy to get wrong |
| `services/table_serializer.py` | Output format is verifiable byte-for-byte |
| `ui/controllers/*` | Plain Python, no Qt — just mock services |
| `ui/controllers/status_listener.py` | Most branching logic in the UI layer lives here |

Focus **integration** testing on:

| Target | Why |
|---|---|
| `services/sq_lite_data_api.py` | The SQL is in constants; the mapping is in code. Worth verifying against a real SQLite file |
| `services/yaml_benchmark_task_api.py` | The YAML parsing has fall-backs that are hard to mock |

## Target Directory Layout

```
tests/
├── conftest.py
├── unit/
│   ├── conftest.py
│   ├── core/
│   │   └── test_models.py
│   ├── services/
│   │   ├── test_app_result_api.py
│   │   ├── test_simple_prompt_builder_api.py
│   │   └── test_table_serializer.py
│   ├── ui/
│   │   └── controllers/
│   │       ├── test_new_run_widget_controller.py
│   │       └── test_status_listener.py
│   └── utils/
│       ├── test_text_utils.py
│       ├── test_time_utils.py
│       └── test_run_utils.py
└── integration/
    ├── conftest.py
    ├── test_sq_lite_data_api.py
    └── test_yaml_benchmark_task_api.py
```

Mirror the source tree exactly.
Run tiers independently:

```bash
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest -m unit        # by marker
uv run pytest -m integration
```

## Test Naming

Follow the rule: `test_<what>_<condition>_<expected>`.

```python
def test_parse_judge_response_with_valid_json_returns_grade() -> None: ...
def test_parse_judge_response_with_missing_grade_returns_error() -> None: ...
def test_create_run_with_empty_models_raises_value_error() -> None: ...
def test_avg_results_with_zero_total_time_returns_zero_tokens_per_second() -> None: ...
```

Every test function must have a return type annotation `-> None`.

## Arrange-Act-Assert

```python
def test_parse_judge_response_with_valid_json_returns_grade() -> None:
    # Arrange
    raw = '{"reason":"ok","grade":0.85}'

    # Act
    has_error, grade, reason = parse_judge_response(raw)

    # Assert
    assert has_error is False
    assert grade == 0.85
    assert reason == "ok"
```

- One logical concept per test.
- No loops, no conditionals in test bodies.
- Use `@pytest.mark.parametrize` for variations.

## Mocking Rules

### Always `spec=`

```python
# GOOD — typo-safe
mock_data = mocker.Mock(spec=DataApi)

# BAD — allows any attribute
mock_data = mocker.Mock()
```

### What to Mock

| Dependency | How |
|---|---|
| LLM provider (external HTTP) | `mocker.Mock(spec=LLMProviderApi)` |
| Embedding provider | `mocker.Mock(spec=EmbeddingProviderApi)` |
| `ProviderRegistry` | `mocker.Mock(spec=ProviderRegistryApi)` |
| `SqLiteDataApi` (in unit tests) | `mocker.Mock(spec=DataApi)` |
| `EventBus` | `mocker.Mock(spec=EventBus)` |
| `BenchmarkFlowApi` | `mocker.Mock(spec=BenchmarkFlowApi)` |
| `TaskFileLoader` | `mocker.Mock(spec=TaskFileLoaderApi)` |
| `JudgePromptService` | `mocker.Mock(spec=JudgePromptServiceApi)` |
| File system (in unit tests) | `tmp_path` fixture |

### What NOT to Mock

| Type | Reason |
|---|---|
| `BenchmarkTask`, `BenchmarkRun`, `BenchmarkResult`, `InferenceResponse` | Frozen dataclasses — instantiate directly |
| `AvgSummaryTableItem`, `SummaryTableItem`, `ReporterStatusMsg` | Same |
| `text_utils.*`, `time_utils.*`, `run_utils.*` | Pure functions — call directly |
| `list`, `dict`, `str`, `Path`, `datetime` | Stdlib types |

### Patch at Point of Use

```python
# GOOD — patch where imported
mocker.patch("ollama_llm_bench.backend.services.providers.openai_compatible_provider.OpenAI")

# BAD — patch at source
mocker.patch("openai.OpenAI")
```

## Fixture Patterns

### Shared Fixtures (`tests/conftest.py`)

```python
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import DataApi, EventBus, LLMProviderApi


@pytest.fixture
def mock_data_api(mocker: MockerFixture) -> DataApi:
    return mocker.Mock(spec=DataApi)


@pytest.fixture
def mock_llm_provider(mocker: MockerFixture) -> LLMProviderApi:
    return mocker.Mock(spec=LLMProviderApi)


@pytest.fixture
def mock_event_bus(mocker: MockerFixture) -> EventBus:
    return mocker.Mock(spec=EventBus)
```

### Integration Fixtures (`tests/integration/conftest.py`)

```python
from pathlib import Path

import pytest

from ollama_llm_bench.services.sq_lite_data_api import SqLiteDataApi


@pytest.fixture
def db_api(tmp_path: Path) -> SqLiteDataApi:
    db_path = tmp_path / "test.sqlite"
    return SqLiteDataApi(db_path)
```

Every integration test gets a fresh, isolated SQLite file via `tmp_path`.

### Factory Fixtures

When tests need many instances with slight variations:

```python
from typing import Callable

import pytest

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkResultStatus


@pytest.fixture
def make_result() -> Callable[..., BenchmarkResult]:
    def _factory(**overrides) -> BenchmarkResult:
        defaults = dict(
            result_id=0,
            run_id=1,
            task_id="task_a",
            model_name="model_x",
            status=BenchmarkResultStatus.COMPLETED,
            time_taken_ms=1000,
            tokens_generated=100,
            evaluation_score=0.75,
        )
        return BenchmarkResult(**{**defaults, **overrides})

    return _factory
```

## Example Tests

### Pure Function — `parse_judge_response`

```python
import pytest

from ollama_llm_bench.utils.text_utils import parse_judge_response


@pytest.mark.parametrize(
    "raw,expected_error,expected_grade,expected_reason",
    [
        ('{"reason":"ok","grade":0.85}', False, 0.85, "ok"),
        ('```json\n{"reason":"ok","grade":1.0}\n```', False, 1.0, "ok"),
        ('<start_of_turn>{"reason":"x","grade":0}<end_of_turn>', False, 0.0, "x"),
        ('not json at all', True, 0.0, pytest.approx),
        ('{"reason":"missing grade"}', True, 0.0, pytest.approx),
        ('{"reason":"bad grade","grade":"high"}', True, 0.0, pytest.approx),
    ],
    ids=[
        "clean_json",
        "markdown_wrapped",
        "turn_markers",
        "plain_text",
        "missing_grade",
        "non_numeric_grade",
    ],
)
def test_parse_judge_response_variants(
    raw: str,
    expected_error: bool,
    expected_grade: float,
    expected_reason,
) -> None:
    has_error, grade, reason = parse_judge_response(raw)
    assert has_error == expected_error
    assert grade == expected_grade
    if not expected_error:
        assert reason == expected_reason
```

### Service Unit Test — `AppResultApi`

```python
from pytest_mock import MockerFixture

from ollama_llm_bench.core.interfaces import DataApi
from ollama_llm_bench.core.models import (
    BenchmarkResult, BenchmarkResultStatus,
)
from ollama_llm_bench.services.app_result_api import AppResultApi


def test_avg_results_averages_time_per_model(mocker: MockerFixture) -> None:
    # Arrange
    data_api = mocker.Mock(spec=DataApi)
    data_api.retrieve_benchmark_results_for_run.return_value = [
        BenchmarkResult(
            result_id=1, run_id=1, task_id="t1", model_name="m1",
            status=BenchmarkResultStatus.COMPLETED,
            time_taken_ms=1000, tokens_generated=100, evaluation_score=0.8,
        ),
        BenchmarkResult(
            result_id=2, run_id=1, task_id="t2", model_name="m1",
            status=BenchmarkResultStatus.COMPLETED,
            time_taken_ms=3000, tokens_generated=200, evaluation_score=0.6,
        ),
    ]
    api = AppResultApi(data_api=data_api)

    # Act
    summaries = api.retrieve_avg_benchmark_results_for_run(run_id=1)

    # Assert
    assert len(summaries) == 1
    assert summaries[0].model_name == "m1"
    assert summaries[0].avg_time_ms == 2000.0
    assert summaries[0].avg_score == pytest.approx(0.7)
    # total_tokens=300, total_time=4000ms → 75 tokens/s
    assert summaries[0].avg_tokens_per_second == pytest.approx(75.0)
```

### Controller Unit Test

Controllers are plain Python — no Qt, no `QApplication` required. Mock dependencies through their Protocol or ABC.

```python
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    DataApi,
    EventBus,
    TableSerializerApi,
)
from ollama_llm_bench.ui.controllers.result_widget_controller import ResultWidgetController


def test_handle_summary_export_csv_emits_success_message(mocker: MockerFixture) -> None:
    # Arrange
    data_api = mocker.Mock(spec=DataApi)
    event_bus = mocker.Mock(spec=EventBus)
    table_serializer = mocker.Mock(spec=TableSerializerApi)
    settings = mocker.Mock(spec=AppSettingsServiceApi)
    controller = ResultWidgetController(
        data_api=data_api,
        event_bus=event_bus,
        table_serializer=table_serializer,
        app_settings_service=settings,
    )

    # Act
    controller.handle_summary_export_csv_click(None)

    # Assert
    table_serializer.save_summary_as_csv.assert_called_once()
    event_bus.emit_global_event_msg.assert_called_once_with("Summary exported as CSV")
```

### Integration Test — `SqLiteDataApi`

```python
from pathlib import Path

from ollama_llm_bench.backend.core.models import (
    BenchmarkRun, BenchmarkRunStatus,
)
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi


def test_create_and_retrieve_run_round_trip(tmp_path: Path) -> None:
    # Arrange
    db = SqLiteDataApi(tmp_path / "db.sqlite")
    run = BenchmarkRun(
        run_id=0,
        timestamp="2026-04-10T12:00:00",
        judge_model="llama3:8b",
        status=BenchmarkRunStatus.NOT_COMPLETED,
    )

    # Act
    run_id = db.create_benchmark_run(run)
    retrieved = db.retrieve_benchmark_run(run_id)

    # Assert
    assert retrieved.run_id == run_id
    assert retrieved.timestamp == "2026-04-10T12:00:00"
    assert retrieved.judge_model == "llama3:8b"
    assert retrieved.status == BenchmarkRunStatus.NOT_COMPLETED
```

## Non-Determinism

### Time

Use `freezegun`:

```python
from freezegun import freeze_time

@freeze_time("2026-04-10 12:00:00")
def test_new_run_uses_frozen_timestamp(...) -> None:
    ...
```

`freezegun` is **not currently in dev dependencies**.
Add with `uv add --dev freezegun` when first needed.

### Random / UUIDs

Patch at point of use:

```python
mocker.patch(
    "ollama_llm_bench.services.your_service.uuid4",
    return_value="fixed-id-123",
)
```

## GUI Isolation

The coding rules say unit tests must not require a GUI event loop.

- **Do not** import anything from `PySide6.QtWidgets` in unit tests.
- **Do not** create a `QApplication` instance.
- **Do not** instantiate widgets in unit tests.
- **Do** test controllers directly — they have no Qt dependencies.
- **Do** test `QtEventBus` via an integration test if needed, but prefer mocking the `EventBus` ABC.

## Running Tests

```bash
# All tests (will report 0 collected until tests exist)
uv run pytest

# With coverage
uv run pytest --cov --cov-report=term-missing

# Single file
uv run pytest tests/unit/utils/test_text_utils.py

# Single test
uv run pytest tests/unit/utils/test_text_utils.py::test_parse_judge_response_with_valid_json_returns_grade

# By marker
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m "not slow"

# Stop at first failure
uv run pytest -x

# Show captured logs
uv run pytest -o log_cli=true --log-cli-level=DEBUG
```

Or via the full pipeline:

```bash
./scripts/ai-check.sh
```

## Coverage Status

Current: **0 %** (no tests exist).
Target: **80 %** branch coverage (`pyproject.toml [tool.coverage.report] fail_under = 80`).

Recommended first pass to make coverage actually meaningful:

1. `utils/text_utils.py` — easy wins, pure functions, many edge cases.
2. `services/app_result_api.py` — arithmetic, no I/O.
3. `services/simple_prompt_builder_api.py` — templating, no I/O.
4. `services/table_serializer.py` — file output via `tmp_path`.
5. `services/yaml_benchmark_task_api.py` — YAML parsing via `tmp_path`.
6. `services/sq_lite_data_api.py` — integration tests with `tmp_path`.
7. `ui/controllers/*` — heavy mocking but every branch counts.

## Related Documents

- [developer-guide.md](developer-guide.md) — patterns to test against
- [services-reference.md](services-reference.md) — service APIs to mock
- [data-model.md](data-model.md) — dataclass fixtures
- [technical-debt.md](technical-debt.md) — why test coverage is 0 % today
