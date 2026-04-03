---
description: "Testing standards — pytest, test pyramid, mocking with spec=, fixtures, coverage, desktop GUI isolation"
globs: "tests/**/*.py,conftest.py"
alwaysApply: false
---

# Python Desktop Project Testing Standards

## Critical Rules

- MUST distribute tests as a pyramid: **70-80% unit, 15-25% integration, 5-10% E2E**
- MUST mock all external services, databases, and I/O in unit tests
- MUST NOT mock dataclasses, Pydantic models, DTOs, pure functions, or stdlib types
- MUST use `mocker` fixture from `pytest-mock` with `spec=` on every mock
- MUST NOT use `@mock.patch` decorators or `unittest.mock.patch` context managers
- MUST enforce >= 80% branch coverage via `pytest-cov` with `branch = true`
- Every test MUST be independently executable — no shared mutable state, no order dependency
- MUST use `@pytest.fixture` for all setup/teardown — MUST NOT use `setUp`/`tearDown`
- MUST configure pytest exclusively in `pyproject.toml` under `[tool.pytest.ini_options]`

## Project Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── conftest.py
│   ├── core/
│   │   └── test_models.py
│   ├── services/
│   │   ├── test_app_result_api.py
│   │   └── test_simple_prompt_builder_api.py
│   └── utils/
│       ├── test_text_utils.py
│       └── test_time_utils.py
└── integration/
    ├── conftest.py
    └── test_sq_lite_data_api.py
```

Run tiers independently:
```bash
uv run pytest tests/unit/
uv run pytest tests/integration/
```

## Test Naming

- MUST follow: `test_<what>_<condition>_<expected>`
- MUST include type hints on all parameters and `-> None` return

```python
def test_parse_judge_response_with_valid_json_returns_grade() -> None: ...
def test_create_run_with_no_models_raises_value_error() -> None: ...
```

## Arrange-Act-Assert (AAA) Pattern

- MUST follow Arrange → Act → Assert in every test
- MUST verify one logical concept per test
- MUST NOT contain conditional logic or loops in tests

```python
def test_calculate_elapsed_time_returns_formatted_string(
    mocker: MockerFixture,
) -> None:
    # Arrange
    start = datetime(2024, 1, 1, 10, 0, 0)
    end = datetime(2024, 1, 1, 10, 5, 30)

    # Act
    result = calculate_elapsed(start, end)

    # Assert
    assert result == "5m 30s"
```

## Fixtures

- MUST use `yield` for fixtures requiring cleanup
- MUST use smallest scope possible — default `scope="function"`
- Reserve `scope="session"` for expensive resources only (database containers)
- MUST NOT use `autouse=True` except for environment-level concerns
- MUST use factory fixtures when tests need multiple instances with varying configs

## Mocking Rules

### spec= on Every Mock

```python
# GOOD
mock_data_api = mocker.Mock(spec=DataApi)

# BAD — accepts any attribute including typos
mock_data_api = mocker.Mock()
```

### Patch at Point of Use

```python
# GOOD — patch where it's USED
mocker.patch("ollama_llm_bench.services.ollama_llm_api.Client")

# BAD — patching the source module
mocker.patch("ollama.Client")
```

### What to Mock vs Not Mock

**MUST mock in unit tests:**

| Dependency | Mock Tool |
|---|---|
| `OllamaApi` (external LLM) | `mocker.Mock(spec=LLMApi)` |
| `SqLiteDataApi` (database) | `mocker.Mock(spec=DataApi)` |
| `EventBus` (Qt signals) | `mocker.Mock(spec=EventBus)` |
| File system I/O | `tmp_path` fixture |
| System clock | `freezegun` |

**MUST NOT mock:**

| Type | Action |
|---|---|
| `BenchmarkTask`, `BenchmarkRun`, `BenchmarkResult` | Instantiate directly |
| `InferenceResponse`, `SummaryTableItem` | Instantiate directly |
| `text_utils`, `time_utils`, `run_utils` | Call directly |
| `list`, `dict`, `str`, `Path` | Use directly |

## Integration Testing

- For SQLite tests: use `tmp_path` fixture to create isolated database files
- MUST NOT share database instances across tests
- MUST reset state between tests

```python
@pytest.fixture
def db_api(tmp_path: Path) -> SqLiteDataApi:
    db_path = tmp_path / "test.sqlite"
    return SqLiteDataApi(str(db_path))
```

## Parametrized Testing

- MUST use `@pytest.mark.parametrize` with `ids=` — MUST NOT use loops in tests

```python
@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("<think>reasoning</think>answer", "answer"),
        ("no tags here", "no tags here"),
        ("", ""),
    ],
    ids=["with_think_tags", "no_tags", "empty_string"],
)
def test_strip_think_tags(input_text: str, expected: str) -> None:
    assert strip_think_tags(input_text) == expected
```

## Property-Based Testing

- PREFER Hypothesis for parsers, serializers, validators (e.g., `text_utils` functions)

## Non-Determinism Elimination

- MUST use `freezegun` for time-dependent tests
- MUST use `mocker.patch` for UUID/random value injection
- PREFER `pytest-randomly` for randomized test ordering in CI

## Desktop-Specific Testing

- MUST separate GUI code from business logic for testability
- MUST NOT require a display server or GUI event loop for unit tests
- MUST use `tmp_path` for all file operations in tests
- MUST test event handlers as isolated functions with injected dependencies

## Configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = ["--import-mode=importlib", "--strict-markers", "--strict-config", "-ra"]
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
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "@abstractmethod",
]
```

## Test Execution Time Budgets

| Tier | Maximum Per-Test |
|------|-----------------|
| Unit | < 1 second |
| Integration | < 30 seconds |

## Approved Tooling

| Tool | Min Version | Role |
|---|---|---|
| pytest | >= 8.0 | Test framework |
| pytest-cov | >= 4.0 | Coverage |
| pytest-mock | >= 3.12 | Mocking |
| pytest-randomly | >= 3.15 | Order randomization |
| freezegun | >= 1.4 | Time freezing |
| Hypothesis | >= 6.100 | Property-based testing |
| factory-boy | >= 3.3 | Test data factories |
