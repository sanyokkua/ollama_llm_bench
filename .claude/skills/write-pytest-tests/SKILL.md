---
name: write-pytest-tests
description: Pytest testing standards for Ollama LLM Bench — test pyramid, fixtures, mocking with spec=, coverage, GUI isolation, and test categories. Use when writing or reviewing test code.
allowed-tools: Read, Write, Edit, Grep, Glob
---

# Write Pytest Tests — Ollama LLM Bench

## Critical Rules

- MUST use **pytest** as the sole test framework — MUST NOT use `unittest.TestCase`
- MUST mock external boundaries (Ollama API, file system, SQLite) — MUST NOT mock internal models or dataclasses
- Every `Mock()` / `MagicMock()` MUST use `spec=ConcreteClass` — specless mocks are forbidden
- MUST structure tests as **Arrange → Act → Assert** with blank lines between sections
- MUST NOT test private methods directly — test through the public API
- MUST NOT share mutable state between tests — use fresh fixtures

Supporting files:
- [examples.md](examples.md) — complete test templates for this project's patterns

---

## Test Pyramid

| Level | Ratio | What to test | Isolation |
|-------|-------|-------------|-----------|
| **Unit** | 70-80% | Single class/function, injected mocks | Full — no I/O, no Qt |
| **Integration** | 15-25% | Multi-class with real SQLite (`tmp_path`) | Real DB, mocked Ollama |
| **E2E** | 5-10% | Full pipeline from controller down | Headless Qt if needed |

---

## File Organization

```
tests/
├── conftest.py           # Shared fixtures (mock factories, tmp_path DB)
├── unit/
│   ├── core/             # Model and interface tests
│   ├── services/         # Service implementation tests
│   └── utils/            # Utility function tests
├── integration/
│   └── services/         # Multi-service with real SQLite
└── e2e/                  # Full pipeline tests
```

Test file naming: `test_<module_name>.py` (e.g., `test_sq_lite_data_api.py`).

---

## What to Mock vs. What NOT to Mock

### MUST mock (external boundaries)

| Component | Why |
|-----------|-----|
| `OllamaApi` / `LLMApi` | Network I/O to Ollama server |
| `DataApi` (in unit tests) | SQLite I/O |
| `EventBus` | Signal emissions, side effects |
| `QThreadPool` | Thread management |
| File system reads | Disk I/O |

### MUST NOT mock (internal logic)

| Component | Why |
|-----------|-----|
| `BenchmarkResult`, `BenchmarkRun` | Frozen dataclasses — test with real instances |
| `BenchmarkResultStatus`, `BenchmarkRunStatus` | StrEnums — use real values |
| Utility functions (`parse_judge_response`, etc.) | Pure functions — test directly |
| `PromptBuilderApi` (in integration) | Logic under test |

---

## Fixture Patterns

### Mock Factory with `spec=`

```python
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_data_api() -> MagicMock:
    return MagicMock(spec=SqLiteDataApi)

@pytest.fixture
def mock_llm_api() -> MagicMock:
    return MagicMock(spec=OllamaApi)

@pytest.fixture
def mock_event_bus() -> MagicMock:
    return MagicMock(spec=QtEventBus)
```

### Real SQLite via `tmp_path`

```python
@pytest.fixture
def real_data_api(tmp_path: Path) -> SqLiteDataApi:
    db_path = tmp_path / "test.sqlite"
    return SqLiteDataApi(db_path)
```

### Service Under Test

```python
@pytest.fixture
def service(mock_data_api: MagicMock, mock_event_bus: MagicMock) -> MyService:
    return MyService(data_api=mock_data_api, event_bus=mock_event_bus)
```

---

## Test Structure (AAA Pattern)

```python
def test_create_benchmark_run_returns_valid_id(
    real_data_api: SqLiteDataApi,
) -> None:
    # Arrange
    run = BenchmarkRun(
        run_id=0,
        timestamp="2024-01-01",
        judge_model="llama3",
        status=BenchmarkRunStatus.NOT_COMPLETED,
    )

    # Act
    run_id = real_data_api.create_benchmark_run(run)

    # Assert
    assert run_id > 0
    retrieved = real_data_api.retrieve_benchmark_run(run_id)
    assert retrieved.judge_model == "llama3"
```

---

## Parametrized Testing

```python
@pytest.mark.parametrize(
    ("input_text", "expected_grade", "expected_has_error"),
    [
        ("Grade: 8/10\nReason: Good", 8.0, False),
        ("Grade: 0/10\nReason: Wrong", 0.0, False),
        ("Invalid response", None, True),
    ],
)
def test_parse_judge_response(
    input_text: str,
    expected_grade: float | None,
    expected_has_error: bool,
) -> None:
    has_error, grade, reason = parse_judge_response(input_text)

    assert has_error == expected_has_error
    if not has_error:
        assert grade == expected_grade
```

---

## Mocking Best Practices

```python
# CORRECT — spec enforces interface
mock_api = MagicMock(spec=OllamaApi)
mock_api.inference.return_value = InferenceResponse(
    llm_response="test output",
    time_taken_ms=100,
    tokens_generated=10,
)

# WRONG — specless mock accepts any attribute
mock_api = MagicMock()  # FORBIDDEN
mock_api.nonexistent_method()  # silently passes — hides bugs
```

### Verifying Calls

```python
# Verify method was called with expected args
mock_data_api.update_benchmark_result.assert_called_once()
call_args = mock_data_api.update_benchmark_result.call_args[0][0]
assert call_args.status == BenchmarkResultStatus.COMPLETED

# Verify method was NOT called
mock_event_bus.emit_log_append.assert_not_called()
```

---

## Coverage Configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers -ra"

[tool.coverage.run]
source = ["src/ollama_llm_bench"]
omit = ["*/ui/widgets/*", "*/main.py"]

[tool.coverage.report]
fail_under = 70
show_missing = true
```

- Unit test coverage target: 80%+
- UI widget code excluded from coverage (visual logic)
- `main.py` excluded (application entry point)

---

## GUI Test Isolation

For tests that must interact with Qt objects:
- MUST NOT create `QApplication` in individual tests — use a session-scoped fixture
- MUST NOT show windows — test controller logic, not widget rendering
- Prefer testing controllers (which mediate UI) over widgets directly

```python
@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for tests that need Qt."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
```

---

## Running Tests

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/unit/services/test_sq_lite_data_api.py

# Specific test
uv run pytest tests/unit/services/test_sq_lite_data_api.py::test_create_benchmark_run

# With coverage
uv run pytest --cov=src/ollama_llm_bench --cov-report=term-missing

# Verbose output
uv run pytest -v
```
