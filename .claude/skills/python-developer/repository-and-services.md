# Repository, Service, Use-Case, Utility, Adapter — Definitions and Project Examples

This file resolves the most common "where does this code go?" question. See [SKILL.md](SKILL.md) for the short decision table and [architecture.md](architecture.md) for the layer mapping.

---

## 1. Repository

**Definition:** A class that owns persistence for one aggregate (the unit-of-consistency in your domain). It hides storage details behind domain-shaped methods.

**Where:** `backend/services/<feature>/repository.py` (or, for legacy, `backend/services/sq_lite_data_api.py`).

**Rules:**

- Method names are **domain verbs** (`save_run`, `list_runs_for_model`), not SQL verbs (`insert`, `update`, `select_by_id`).
- Accepts and returns **domain dataclasses** — never raw rows, tuples, or ORM objects.
- Owns connection management, transactions, and serialization.
- Implements an ABC declared in `backend/core/interfaces.py`.
- Does NOT contain business logic — only persistence logic.

**Project example:**

```python
# backend/core/interfaces.py
from abc import ABC, abstractmethod

class RunsRepository(ABC):
    """Persistence boundary for BenchmarkRun aggregates."""

    @abstractmethod
    def save(self, run: BenchmarkRun) -> None: ...

    @abstractmethod
    def get(self, run_id: int) -> Optional[BenchmarkRun]: ...

    @abstractmethod
    def list_recent(self, limit: int = 50) -> list[BenchmarkRun]: ...

# backend/services/benchmark/repository.py
class SqliteRunsRepository(RunsRepository):
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path

    @override
    def save(self, run: BenchmarkRun) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_INSERT_RUN_SQL, (run.id, run.created_at, ...))
```

**Migration note:** the existing `SqLiteDataApi` is multi-aggregate (runs, results, settings). Long-term, split into one repository per aggregate; short-term, the class is acceptable — but new aggregates SHOULD use their own repository.

---

## 2. Use-Case (Application Service)

**Definition:** A class or function implementing **exactly one business operation** the user cares about. Orchestrates repositories and external clients to fulfill the operation.

**Where:** `backend/services/<feature>/use_cases.py`.

**Rules:**

- Name follows the verb-noun convention of the operation: `StartBenchmarkRunUseCase`, `PauseRunUseCase`, `ExportResultsUseCase`.
- Takes repositories and clients as **constructor-injected ABCs**, never as concrete classes.
- Returns a domain dataclass, raises a domain exception, or yields a generator.
- Stateless between calls — no `self._run = ...` retention.
- Does NOT contain UI code, persistence code, or HTTP code — it orchestrates objects that do.
- Prefer one class per use-case. Group multiple closely-related operations into one class only when they share configuration.

**Project example:**

```python
# backend/services/benchmark/use_cases.py
class StartBenchmarkRunUseCase:
    def __init__(
        self,
        *,
        runs_repo: RunsRepository,
        task_loader: TaskLoaderApi,
        provider_registry: ProviderRegistry,
    ) -> None:
        self._runs_repo = runs_repo
        self._task_loader = task_loader
        self._providers = provider_registry

    def execute(self, *, models: list[ModelId], dataset_path: Path) -> BenchmarkRun:
        if not models:
            raise NoModelsSelected()
        tasks = self._task_loader.load(dataset_path)
        run = BenchmarkRun.new(models=models, tasks=tasks)
        self._runs_repo.save(run)
        return run
```

The use-case never touches Qt, never touches SQLite directly, never reads files directly. Each external concern is satisfied by an ABC dependency.

### When NOT to write a use-case

- For trivial CRUD wrappers — just call the repository directly from the controller / presenter.
- For pure computations — use a domain service (a function in `backend/core/`) or a utility (in `backend/utils/`).
- For framework callbacks — those belong in adapters (`ui/qt_classes/`).

### Function vs class

A use-case is a class when it has constructor-injected dependencies. If it's pure (only computation, no dependencies), it's a function — usually a domain service in `backend/core/` rather than an Application use-case.

```python
# Function — pure computation, lives in backend/core/
def calculate_average_score(results: list[BenchmarkResult]) -> float:
    if not results:
        return 0.0
    return sum(r.score for r in results) / len(results)

# Class — orchestrates dependencies, lives in backend/services/
class StartBenchmarkRunUseCase:
    def __init__(self, *, runs_repo: RunsRepository, ...) -> None: ...
    def execute(self, ...) -> BenchmarkRun: ...
```

---

## 3. Provider / Client (Infrastructure Adapter)

**Definition:** A concrete class that wraps an external SDK (`openai`, `anthropic`, `ollama`, `google-genai`) behind an ABC.

**Where:** `backend/services/provider/<name>.py`.

**Rules:**

- Implements an ABC from `backend/core/interfaces.py` (e.g., `LLMApi`).
- Takes its SDK client as a constructor argument — never instantiates the client itself.
- Maps SDK-shaped responses into domain dataclasses (`InferenceResponse`).
- Catches SDK-specific exceptions and translates them to domain exceptions or fills `has_error=True` fields.

**Project example:**

```python
# backend/core/interfaces.py
class LLMApi(ABC):
    @abstractmethod
    def inference(self, *, model_name: str, user_prompt: str) -> InferenceResponse: ...

# backend/services/provider/openai_compatible.py
class OpenAICompatibleProvider(LLMApi):
    def __init__(self, *, client: openai.Client) -> None:
        self._client = client

    @override
    def inference(self, *, model_name: str, user_prompt: str) -> InferenceResponse:
        try:
            response = self._client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return InferenceResponse(
                llm_response=response.choices[0].message.content,
                time_taken_ms=...,
                has_error=False,
            )
        except openai.APIError as e:
            logger.error("Inference failed: %s", e, exc_info=True)
            return InferenceResponse(has_error=True, error_message=str(e))
```

---

## 4. Utility

**Definition:** A pure, generic function used by ≥ 3 unrelated features.

**Where:**
- `backend/utils/<name>.py` — when the rule below is satisfied.
- `backend/services/<feature>/_utils.py` OR `ui/widgets/<component>/_helpers.py` — when used by exactly one feature.

### The "3 + pure + generic" test (MUST pass all three)

1. **Pure** — same inputs always produce same output; no I/O, no clock, no global state, no mutation.
2. **Generic** — works on stdlib types or generic types (`str`, `int`, `list[T]`); does NOT take or return a domain dataclass.
3. **≥ 3 unrelated consumers** — already used (or planned within the same change) by at least three features that have no other relationship.

### Examples

**GOOD utility (pure, generic, multi-consumer):**

```python
# backend/utils/text_parsing.py
def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    return _THINK_PATTERN.sub("", text)
```

Used by the benchmark feature, the judge feature, and the export feature → qualifies.

**BAD "utility" (domain-shaped):**

```python
# WRONG — takes a BenchmarkResult, lives in utils
def format_benchmark_result_for_display(result: BenchmarkResult) -> str:
    return f"{result.model_name}: {result.score:.2f}"
```

This belongs in `backend/services/benchmark/_utils.py` (single feature) or in the presenter (UI concern).

**BAD "utility" (single-consumer):**

```python
# WRONG — only the new_run feature uses this
def format_provider_combobox_label(provider: ProviderConfig) -> str:
    return f"{provider.name} ({provider.url})"
```

Move to `ui/widgets/new_run/_ui_helpers.py`.

### Forbidden names

At the top level of any feature folder, these filenames are FORBIDDEN once the project leaves prototype:

- `utils.py`
- `helpers.py`
- `common.py`
- `misc.py`
- `lib.py`
- `tools.py`

Use precise names instead: `text_parsing.py`, `path_resolver.py`, `model_name_normalization.py`. Inside a feature, a single `_utils.py` is acceptable because the feature folder itself scopes the name — but if it exceeds ~200 lines, split it.

### Lifecycle

A function starts life in `feature/_utils.py`. It graduates to `backend/utils/` only when a third unrelated caller appears. Moving "in case it might be useful later" is FORBIDDEN — utilities must earn their generality.

---

## 5. Adapter (boundary crossing)

**Definition:** A class that bridges two layers with incompatible contracts. In this project, the most important adapter is the **UI Adapter** in `ui/qt_classes/` that bridges synchronous backend calls to Qt's main-thread event loop.

**Where:** `ui/qt_classes/` for backend → UI bridging.

**Rules:**

- The adapter is the **only** class that imports both the backend use-case and `QObject` / `QRunnable` / `QThreadPool`.
- The adapter never contains business logic — it strictly translates.
- The adapter owns thread lifecycle (start, cancel, cleanup).
- Backend code passed to the adapter must remain Qt-free; the adapter wraps it.

**Project example:**

```python
# ui/qt_classes/benchmark_execution_task.py
class BenchmarkExecutionTask(QRunnable):
    """Adapter: runs the start-benchmark use-case on a background thread."""

    class Signals(QObject):
        progress = Signal(str)
        completed = Signal(object)  # BenchmarkRun
        failed = Signal(str)

    def __init__(
        self,
        *,
        use_case: StartBenchmarkRunUseCase,
        models: list[ModelId],
        dataset_path: Path,
    ) -> None:
        super().__init__()
        self._use_case = use_case
        self._models = models
        self._dataset_path = dataset_path
        self.signals = self.Signals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            run = self._use_case.execute(
                models=self._models, dataset_path=self._dataset_path
            )
            self.signals.completed.emit(run)
        except Exception as e:
            logger.error("Benchmark task failed: %s", e, exc_info=True)
            self.signals.failed.emit(str(e))
```

**Key property:** if you wanted to call the same `StartBenchmarkRunUseCase` from a CLI, you would not need this adapter — you would just call `use_case.execute(...)` synchronously. The adapter only exists because the UI needs main-thread safety.

---

## 6. Domain Events (Qt-free pub/sub)

**Today:** the backend communicates events to the UI through synchronous return values, then the UI's adapter re-emits them as Qt signals.

**Target:** introduce `psygnal` for Qt-free publish/subscribe inside the backend, while keeping the UI's `QtEventBus` as the only Qt-aware publisher.

### Why

A use-case that emits multiple events (one per task completed in a run) can't return them all — it's a stream. Today the project handles this by having the adapter (`BenchmarkExecutionTask.run()`) drive the iteration and emit Qt signals per step. That works, but the use-case has implicit coupling to "something is iterating me."

With `psygnal`, the use-case can emit events directly inside its own logic, without depending on Qt:

```python
# backend/core/events.py — Qt-free
from psygnal import Signal
from dataclasses import dataclass

@dataclass(frozen=True)
class TaskCompletedEvent:
    task_id: str
    duration_ms: int
    score: float

class BenchmarkEvents:
    task_completed = Signal(TaskCompletedEvent)
    run_finished = Signal(object)  # BenchmarkRun

# backend/services/benchmark/use_cases.py — still Qt-free
class StartBenchmarkRunUseCase:
    def __init__(self, *, events: BenchmarkEvents, ...) -> None:
        self._events = events

    def execute(self, ...) -> BenchmarkRun:
        for task in tasks:
            result = self._run_task(task)
            self._events.task_completed.emit(TaskCompletedEvent(...))
        return run

# ui/qt_classes/event_bridge.py — adapter
class BackendEventBridge:
    """Subscribes to backend psygnal events, re-emits as Qt signals."""

    def __init__(self, *, backend_events: BenchmarkEvents, qt_bus: QtEventBus) -> None:
        backend_events.task_completed.connect(self._on_task_completed)
        backend_events.run_finished.connect(self._on_run_finished)
        self._qt_bus = qt_bus

    def _on_task_completed(self, evt: TaskCompletedEvent) -> None:
        self._qt_bus.emit_task_completed(evt)
```

### Adoption strategy

1. Add `psygnal>=0.10` to `pyproject.toml` only when the first migration begins.
2. Migrate one event source at a time. Start with the smallest use-case.
3. Keep the existing `QtEventBus` — it remains the UI's pub/sub bus. The new psygnal events live in `backend/core/events.py` and are bridged via an adapter.

### Why not just use `QObject` + `Signal` in the backend?

It works mechanically, but it imports PySide6 into the backend. That breaks the "swap UI for CLI" property (CLI can't import PySide6 just to listen to events) and forces backend tests to instantiate a `QApplication`. Stay Qt-free in `backend/`.

---

## 7. Quick "where does this code go?" decision flow

```
Is the code computing a value from inputs only, with no I/O?
  ├─ Domain-specific (operates on a BenchmarkRun)?  →  backend/core/ as a function or method
  └─ Generic + reusable in 3+ features?            →  backend/utils/<precise_name>.py
                                                    or backend/services/<feature>/_utils.py

Does it talk to an external system (DB, HTTP, file, LLM)?
  ├─ Persistence-shaped (CRUD on an aggregate)?    →  Repository (backend/services/<feature>/repository.py)
  └─ External service / SDK?                       →  Provider/Client (backend/services/provider/<name>.py)

Does it orchestrate domain + infrastructure to fulfill a user-meaningful operation?
  └─ Use-Case (backend/services/<feature>/use_cases.py)

Does it bridge synchronous backend calls into Qt's main-thread event loop?
  └─ Adapter (ui/qt_classes/<name>.py)

Does it mediate between a widget and a controller's services?
  ├─ Existing module?                              →  Controller (ui/controllers/)
  └─ New refactored component?                     →  Presenter (ui/widgets/<feature>/presenter.py)

Does it render UI?
  └─ View (ui/widgets/<feature>/view.py)

Does it organize multiple services and present them as one?
  └─ Likely a Manager smell — split it into specific roles instead.
```
