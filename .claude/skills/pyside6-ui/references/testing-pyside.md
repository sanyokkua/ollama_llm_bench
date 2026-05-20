# Testing PySide6 — `pytest-qt`, `qtbot`, `qtmodeltester`

Testing patterns for the project's three test tiers. The MVP architecture pays off here: **most tests don't need Qt**, and the ones that do use `pytest-qt` for ergonomic widget testing.

See also:
- [../SKILL.md](../SKILL.md) for architectural rules that enable headless tests.
- [component-architecture.md](component-architecture.md) for the View Protocol pattern (mockable presenter tests).
- [model-view-adapters.md](model-view-adapters.md) for item-model rules.

---

## 1. Tooling Required

Add to `[dependency-groups.dev]` in `pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "pytest-mock>=3.12",
    "pytest-qt>=4.4",         # qtbot, qtmodeltester
    "pytest-xvfb>=3.0",       # virtual display on Linux CI (optional)
    "pytest-randomly>=3.15",  # order randomization
]
```

CI environments without a display server run with:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest
```

`offscreen` is the official Qt headless platform plugin and works on all OSes — no Xvfb needed on macOS or Windows. On Linux CI without a desktop, use `pytest-xvfb` for `xvfb-run` semantics.

---

## 2. Test Pyramid for the Project

```
              ┌────────────────────────┐
              │ End-to-end smoke (~5%) │  pytest-qt, full app
              ├────────────────────────┤
              │ View / widget tests    │  pytest-qt + qtbot
              │ (~20%)                 │  qtmodeltester for models
              ├────────────────────────┤
              │ Presenter tests (~35%) │  pytest, Mock(spec=ViewProtocol)
              ├────────────────────────┤
              │ Use-case tests (~25%)  │  pytest, fake repositories
              ├────────────────────────┤
              │ Domain tests (~15%)    │  pytest, no mocks at all
              └────────────────────────┘
```

The bottom three layers run without Qt. If a unit test for business logic needs `qtbot`, that logic is in the wrong layer.

---

## 3. Domain Tests (no Qt, no mocks)

For frozen dataclasses, pure functions, and `StrEnum`s. Fastest tier.

```python
# tests/unit/backend/core/test_models.py
def test_benchmark_run_new_with_no_models_raises_value_error() -> None:
    with pytest.raises(ValueError, match="at least one model"):
        BenchmarkRun.new(models=[], tasks=[sample_task()])

def test_benchmark_result_score_is_normalized_to_zero_one_range() -> None:
    result = BenchmarkResult(score=0.85, ...)
    assert 0.0 <= result.score <= 1.0
```

No mocks. No fixtures beyond simple data factories. < 1 ms per test.

---

## 4. Use-Case Tests (no Qt, mock repositories)

Test orchestration with **fake / mock repositories**. The use-case knows nothing about Qt.

```python
# tests/unit/backend/services/benchmark/test_use_cases.py
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    RunsRepository, TaskLoader,
)
from ollama_llm_bench.backend.services.benchmark.use_cases import (
    StartBenchmarkRunUseCase, NoModelsSelected,
)


def test_start_run_with_no_models_raises(mocker: MockerFixture) -> None:
    # Arrange
    runs_repo = mocker.Mock(spec=RunsRepository)
    task_loader = mocker.Mock(spec=TaskLoader)
    use_case = StartBenchmarkRunUseCase(
        runs_repo=runs_repo, task_loader=task_loader,
    )

    # Act / Assert
    with pytest.raises(NoModelsSelected):
        use_case.execute(models=[], dataset_path=Path("/tmp/ds"))
    runs_repo.save.assert_not_called()


def test_start_run_persists_and_returns_run(mocker: MockerFixture) -> None:
    # Arrange
    runs_repo = mocker.Mock(spec=RunsRepository)
    task_loader = mocker.Mock(spec=TaskLoader)
    task_loader.load.return_value = [sample_task()]
    use_case = StartBenchmarkRunUseCase(
        runs_repo=runs_repo, task_loader=task_loader,
    )

    # Act
    run = use_case.execute(
        models=["llama3"], dataset_path=Path("/tmp/ds"),
    )

    # Assert
    assert run.models == ["llama3"]
    runs_repo.save.assert_called_once_with(run)
```

**Use `spec=` on every mock** — without it, typos in mocked method names pass silently. With it, any unexpected attribute access fails fast.

---

## 5. Presenter Tests (no `qtbot`, Mock view)

The View Protocol pattern (see [component-architecture.md §3](component-architecture.md)) makes presenter tests fast and headless.

```python
# tests/unit/ui/widgets/new_run/test_presenter.py
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    EventBus, StartBenchmarkRunUseCase, ListProvidersUseCase,
)
from ollama_llm_bench.ui.widgets.new_run.presenter import NewRunPresenter
from ollama_llm_bench.ui.widgets.new_run.view import NewRunViewProtocol
from ollama_llm_bench.ui.widgets.new_run.state import NewRunFormData


def test_start_with_no_models_shows_error_and_skips_use_case(
    mocker: MockerFixture,
) -> None:
    # Arrange
    view = mocker.Mock(spec=NewRunViewProtocol)
    start_uc = mocker.Mock(spec=StartBenchmarkRunUseCase)
    presenter = NewRunPresenter(
        view=view,
        start_run_uc=start_uc,
        list_providers_uc=mocker.Mock(spec=ListProvidersUseCase),
        event_bus=mocker.Mock(spec=EventBus),
    )

    # Act
    presenter._on_start_requested(NewRunFormData(selected_models=[]))

    # Assert
    view.show_error.assert_called_once_with("Select at least one model.")
    start_uc.execute.assert_not_called()


def test_start_with_models_calls_use_case_and_emits_run_started(
    mocker: MockerFixture,
) -> None:
    # Arrange
    view = mocker.Mock(spec=NewRunViewProtocol)
    start_uc = mocker.Mock(spec=StartBenchmarkRunUseCase)
    run = sample_run()
    start_uc.execute.return_value = run
    presenter = NewRunPresenter(
        view=view, start_run_uc=start_uc,
        list_providers_uc=mocker.Mock(),
        event_bus=mocker.Mock(),
    )
    run_started_handler = mocker.Mock()
    presenter.run_started.connect(run_started_handler)

    # Act
    presenter._on_start_requested(
        NewRunFormData(selected_models=["llama3"], dataset_path=Path("/tmp/ds")),
    )

    # Assert
    start_uc.execute.assert_called_once_with(
        models=["llama3"], dataset_path=Path("/tmp/ds"),
    )
    run_started_handler.assert_called_once_with(run)
```

Note: even though `NewRunPresenter` is a `QObject`, you don't need a `QApplication` — pytest-qt's `qtbot` fixture (auto-loaded when `pytest-qt` is installed) handles the `QCoreApplication` setup transparently. Signals like `run_started` work because they don't cross threads.

If you have a presenter test that fails because of "no QApplication," include `qtbot` as a parameter (just include it — you don't need to use it):

```python
def test_signal_emission_with_qcoreapp(qtbot, mocker):
    # qtbot ensures a QCoreApplication exists
    ...
```

---

## 6. View / Widget Tests (`qtbot`)

When testing the `QWidget` view directly, use `pytest-qt`'s `qtbot`:

```python
# tests/unit/ui/widgets/new_run/test_view.py
from PySide6.QtCore import Qt

from ollama_llm_bench.ui.widgets.new_run.view import NewRunView
from ollama_llm_bench.ui.widgets.new_run.state import NewRunViewState


def test_view_apply_state_updates_status_label(qtbot) -> None:
    # Arrange
    view = NewRunView()
    qtbot.addWidget(view)

    # Act
    view.apply_state(NewRunViewState(
        available_models=("llama3",),
        selected_model_ids=(),
        can_start=False,
        status_text="Ready",
        dataset_path=Path("/tmp/ds"),
    ))

    # Assert
    assert view._status_label.text() == "Ready"


def test_view_start_button_emits_start_requested(qtbot, mocker) -> None:
    # Arrange
    view = NewRunView()
    qtbot.addWidget(view)
    handler = mocker.Mock()
    view.start_requested.connect(handler)

    # Act
    qtbot.mouseClick(view._start_btn, Qt.LeftButton)

    # Assert
    handler.assert_called_once()
```

### `qtbot` highlights

| Method | Use for |
|---|---|
| `qtbot.addWidget(widget)` | Ensure cleanup at end of test |
| `qtbot.mouseClick(widget, button)` | Simulate a click |
| `qtbot.keyClicks(widget, "text")` | Type characters into a focused widget |
| `qtbot.waitSignal(signal, timeout=1000)` | Async-await a signal emission |
| `qtbot.waitSignals([s1, s2], order="strict")` | Multi-signal sequencing |
| `qtbot.waitUntil(lambda: condition, timeout=1000)` | Poll for a state change |
| `qtbot.wait(milliseconds)` | Use sparingly; prefer `waitSignal` / `waitUntil` |

### `pytest-qt` advice

> "In general, prefer to use a widget's own methods to interact with it: `QComboBox.setCurrentIndex`, `QLineEdit.setText`, etc. Use `qtbot.mouseClick` / `keyClicks` only when testing the click/key wiring itself."

This makes view tests faster, less flaky, and more focused.

---

## 7. Item-Model Tests (`qtmodeltester`)

Custom `QAbstractItemModel` subclasses must satisfy Qt's model protocol. Verify with `qtmodeltester`:

```python
# tests/unit/ui/widgets/result/test_model.py
def test_results_table_model_protocol(qtmodeltester) -> None:
    model = ResultsTableModel([sample_result(), sample_result()])
    qtmodeltester.check(model, force_py=True)
```

`force_py=True` makes the tester report row indexes Python-friendly. The check covers:

- Index validity and parent-child relationships
- Row/column count consistency
- Role data returning correct types
- Signal protocol (`beginInsertRows` paired with `endInsertRows`, etc.)

If your model has bugs, this test catches them before they crash production.

### Item-model behavior tests

Beyond protocol, test specific behaviors:

```python
def test_results_model_display_role_formats_score_to_two_decimals() -> None:
    result = sample_result(score=0.7234)
    model = ResultsTableModel([result])

    idx = model.index(0, ResultsTableModel._COL_SCORE)
    assert model.data(idx, Qt.DisplayRole) == "0.72"


def test_replace_all_emits_model_reset(qtbot) -> None:
    model = ResultsTableModel()
    with qtbot.waitSignal(model.modelReset, timeout=100):
        model.replace_all([sample_result()])
    assert model.rowCount() == 1
```

---

## 8. Threading Tests

Test that workers emit signals correctly and that the main-thread handlers receive them. Use `qtbot.waitSignal`:

```python
def test_benchmark_execution_task_emits_completed_on_success(qtbot, mocker) -> None:
    # Arrange
    use_case = mocker.Mock(spec=StartBenchmarkRunUseCase)
    use_case.execute.return_value = sample_run()
    task = BenchmarkExecutionTask(
        use_case=use_case, models=["llama3"], dataset_path=Path("/tmp/ds"),
    )

    # Act + Assert
    with qtbot.waitSignal(task.signals.completed, timeout=1000) as blocker:
        QThreadPool.globalInstance().start(task)
    assert isinstance(blocker.args[0], BenchmarkRun)


def test_benchmark_execution_task_emits_failed_on_exception(qtbot, mocker) -> None:
    # Arrange
    use_case = mocker.Mock(spec=StartBenchmarkRunUseCase)
    use_case.execute.side_effect = RuntimeError("disk full")
    task = BenchmarkExecutionTask(
        use_case=use_case, models=["llama3"], dataset_path=Path("/tmp/ds"),
    )

    # Act + Assert
    with qtbot.waitSignal(task.signals.failed, timeout=1000) as blocker:
        QThreadPool.globalInstance().start(task)
    assert "disk full" in blocker.args[0]
```

`waitSignal` blocks the test until the signal fires (or timeout). The `blocker.args` tuple contains the emitted values.

---

## 9. Integration Tests (real SQLite)

For `SqLiteDataApi` / `SqliteRunsRepository`, use `tmp_path` to give each test an isolated database file:

```python
# tests/integration/backend/services/benchmark/test_repository.py
@pytest.fixture
def runs_repo(tmp_path: Path) -> SqliteRunsRepository:
    db_path = tmp_path / "test.sqlite"
    return SqliteRunsRepository(db_path=db_path)


def test_save_and_get_round_trips(runs_repo: SqliteRunsRepository) -> None:
    # Arrange
    run = sample_run()

    # Act
    runs_repo.save(run)
    retrieved = runs_repo.get(run.run_id)

    # Assert
    assert retrieved == run
```

No shared state between tests; `tmp_path` is per-test.

---

## 10. Common Patterns

### Factory fixtures for domain dataclasses

```python
# tests/conftest.py
@pytest.fixture
def make_result():
    def _make(*, model_name="llama3", score=0.85, **kwargs) -> BenchmarkResult:
        return BenchmarkResult(
            result_id=kwargs.pop("result_id", 1),
            run_id=kwargs.pop("run_id", 1),
            task_id=kwargs.pop("task_id", "t1"),
            model_name=model_name,
            score=score,
            **kwargs,
        )
    return _make


def test_something(make_result) -> None:
    result = make_result(score=0.9)
    ...
```

### Freezing time

```python
from freezegun import freeze_time

@freeze_time("2026-01-01 12:00:00")
def test_run_uses_frozen_clock() -> None:
    run = BenchmarkRun.new(...)
    assert run.created_at == datetime(2026, 1, 1, 12, 0, 0)
```

### Parametrized tests with `ids=`

```python
@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("<think>x</think>answer", "answer"),
        ("no tags", "no tags"),
        ("", ""),
    ],
    ids=["with_think_tags", "no_tags", "empty"],
)
def test_strip_think_tags(input_text: str, expected: str) -> None:
    assert strip_think_tags(input_text) == expected
```

---

## 11. Anti-Patterns to Refuse

| Anti-pattern | Why it's wrong | Fix |
|---|---|---|
| Test of business logic uses `qtbot` | Logic is in the wrong layer | Push logic into a use-case or domain function |
| Mock without `spec=` | Typos in method names pass silently | Always `spec=SomeProtocol` or `spec=SomeClass` |
| `@mock.patch` decorator | Hides what is mocked; harder to read | Use `mocker.patch` from `pytest-mock` |
| Patching the source module | Patches don't apply at the use-site | Patch where the symbol is USED, not defined |
| Shared mutable state between tests | Order-dependent failures | Each test creates its own data via fixtures |
| `setUp` / `tearDown` from unittest | Verbose; non-composable | Use `@pytest.fixture` with `yield` |
| `time.sleep(1)` to "let UI update" | Flaky on slow CI | Use `qtbot.waitSignal` / `qtbot.waitUntil` |
| Mocks of domain dataclasses | They're immutable values | Instantiate them directly |
| Mocks of `Path` / `list` / `dict` / `str` | They're stdlib | Use the real types |
| Tests that depend on each other | Independence requirement violated | Each test independently executable |

---

## 12. Coverage Targets

```toml
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

**Tier targets** (project-specific):

| Tier | Branch coverage target |
|---|---|
| Domain | 95%+ (pure code, easy to cover) |
| Use-cases | 90%+ (mock repositories, all branches reachable) |
| Presenters | 80%+ (view-protocol mocking) |
| Views | 60% (qtbot can be heavy; focus on key flows) |
| Item-models | 90% (qtmodeltester + behavior tests) |

If domain or use-case coverage drops below target, that's a real gap. View coverage gaps usually indicate that more logic should move down.
