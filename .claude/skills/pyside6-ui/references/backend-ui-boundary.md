# Backend ↔ UI Boundary

This file defines the contract between `backend/` (pure Python, Qt-free) and `ui/` (PySide6) so that **either side can be replaced without rewriting the other**. Read this when:

- Designing a new feature that needs both a use-case and UI.
- Refactoring code that mixes backend logic with widget code.
- Adding a long-running operation that crosses the threading boundary.
- Considering whether to import PySide6 anywhere in `backend/`.

See also:
- [../SKILL.md §1 Architecture Layer Rules](../SKILL.md) for the quick rules.
- [../../python-developer/architecture.md §4 Backend ↔ UI Boundary](../../python-developer/architecture.md) for the backend-side contract.

---

## 1. The Three Zones

```
┌─────────────────────────────────────────────────────────────────┐
│  PURE PYTHON BACKEND                                            │
│  backend/core/   ← Domain: frozen dataclasses, ABCs             │
│  backend/services/ ← Application + Infrastructure: use-cases,   │
│                       repositories, providers                   │
│                                                                 │
│  Communicates by:                                               │
│  - Synchronous return values (frozen dataclasses)               │
│  - Generators / iterators (streaming)                           │
│  - psygnal.Signal (target) or callback Protocols (current)      │
│                                                                 │
│  Imports NOTHING from PySide6.QtWidgets                         │
│  Avoids PySide6.QtCore (acceptable only for legacy ABCs)        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ crosses thread boundary
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  UI ADAPTER LAYER                                               │
│  ui/qt_classes/                                                 │
│                                                                 │
│  THE ONLY place that imports BOTH backend use-cases AND         │
│  QObject / QRunnable / QThreadPool.                             │
│                                                                 │
│  Responsibilities:                                              │
│  - Wrap backend calls in QRunnable / moveToThread workers       │
│  - Bridge psygnal events / callback Protocols into Qt signals   │
│  - Own the QtEventBus singleton                                 │
│  - Maintain main-thread invariants                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ Qt signals (queued, main-thread)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  UI (Presentation + View)                                       │
│  ui/controllers/  ← Controllers / Presenters                    │
│  ui/widgets/      ← Views                                       │
│                                                                 │
│  Subscribes to QtEventBus.                                      │
│  Calls backend through ABCs (constructor-injected).             │
│  Never sees concrete backend classes.                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. What May Cross the Boundary

| Direction | Allowed | Forbidden |
|---|---|---|
| **UI → Backend** | Method calls on injected ABCs with frozen-dataclass / primitive arguments | Passing `QObject`, `QWidget`, or any Qt type |
| **Backend → UI (sync return)** | Frozen dataclass, `StrEnum`, primitive, `list`/`dict`/`tuple` of those | `QObject`, `QWidget`, `Signal` reference, anything Qt |
| **Backend → UI (event/async)** | `psygnal.Signal` (target) or callback Protocol declared in `backend/core/interfaces.py` (current) | Direct Qt `Signal` on a backend class |
| **Backend → UI (stream)** | Generator / iterator yielding domain objects | Generator that imports Qt, calls UI, or assumes a Qt event loop |

**Litmus test:** could you run the backend in a pure-Python REPL with no `QApplication` constructed anywhere? If not, the boundary has leaked.

---

## 3. The Three Communication Patterns

### Pattern A — Synchronous use-case call

For operations that complete quickly (< 50 ms). The presenter calls the use-case directly:

```python
# ui/controllers/settings_presenter.py
class SettingsPresenter(QObject):
    def __init__(self, *, save_settings_uc: SaveSettingsUseCase, ...) -> None:
        super().__init__()
        self._save_settings_uc = save_settings_uc

    @Slot()
    def _on_save_clicked(self) -> None:
        settings = self._view.collect_settings()
        self._save_settings_uc.execute(settings)  # direct call, OK if fast
        self._view.show_success("Settings saved")
```

No adapter needed — but the presenter still depends on the ABC `SaveSettingsUseCase`, not a concrete class.

### Pattern B — Background work via `QRunnable` adapter

For operations that may take longer (HTTP, LLM inference, large file reads). The presenter delegates to an adapter in `ui/qt_classes/`:

```python
# ui/qt_classes/benchmark_execution_task.py
class BenchmarkExecutionTask(QRunnable):
    """Adapter: runs the StartBenchmarkRunUseCase on a worker thread."""

    class Signals(QObject):
        completed = Signal(object)  # BenchmarkRun
        failed = Signal(str)
        progress = Signal(int, int)  # done, total

    def __init__(
        self,
        *,
        use_case: StartBenchmarkRunUseCase,
        models: list[str],
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
            logger.error("Benchmark failed: %s", e, exc_info=True)
            self.signals.failed.emit(str(e))


# ui/controllers/new_run_presenter.py
class NewRunPresenter(QObject):
    def _on_start_requested(self, form: NewRunFormData) -> None:
        task = BenchmarkExecutionTask(
            use_case=self._start_run_uc,
            models=form.selected_models,
            dataset_path=form.dataset_path,
        )
        task.signals.completed.connect(self._on_run_completed)
        task.signals.failed.connect(self._on_run_failed)
        self._threadpool.start(task)
```

**Key property:** the use-case (`StartBenchmarkRunUseCase`) is unchanged from how it would look in a CLI tool. The adapter wraps it for Qt.

### Pattern C — Backend events via `psygnal` bridge (target)

For events that the backend emits during a long operation (one per task in a run). The backend uses `psygnal`; the adapter bridges to `QtEventBus`:

```python
# backend/core/events.py — Qt-free
from psygnal import Signal
from dataclasses import dataclass

@dataclass(frozen=True)
class TaskCompleted:
    task_id: str
    duration_ms: int

class BenchmarkEvents:
    """Qt-free domain events. Subscribers may be UI or other backend code."""
    task_completed = Signal(TaskCompleted)
    run_finished = Signal(object)  # BenchmarkRun
    run_failed = Signal(str)


# backend/services/benchmark/use_cases.py — Qt-free
class StartBenchmarkRunUseCase:
    def __init__(self, *, events: BenchmarkEvents, repo: RunsRepository, ...) -> None:
        self._events = events
        self._repo = repo

    def execute(self, *, models: list[str], dataset_path: Path) -> BenchmarkRun:
        run = BenchmarkRun.new(...)
        for task in tasks:
            result = self._run_task(task)
            self._events.task_completed.emit(TaskCompleted(task_id=task.id, duration_ms=...))
        self._events.run_finished.emit(run)
        return run


# ui/qt_classes/backend_event_bridge.py — the adapter
class BackendEventBridge:
    """Subscribes to backend psygnal events; re-emits as Qt signals on the main thread."""

    def __init__(self, *, backend_events: BenchmarkEvents, qt_bus: QtEventBus) -> None:
        # psygnal connections execute in the calling thread.
        # To stay safe on the main thread, use Qt.QueuedConnection
        # by routing through a QObject-bound slot.
        backend_events.task_completed.connect(self._on_task_completed)
        backend_events.run_finished.connect(self._on_run_finished)
        self._qt_bus = qt_bus

    def _on_task_completed(self, evt: TaskCompleted) -> None:
        self._qt_bus.emit_task_completed(evt)

    def _on_run_finished(self, run: BenchmarkRun) -> None:
        self._qt_bus.emit_run_finished(run)
```

> **Note on thread safety:** `psygnal` connections run in the *emitting* thread by default. If the use-case runs on a worker thread, the bridge slot also runs on that thread, and emitting `QtEventBus` Qt signals from a worker is fine *as long as those signals are connected with `Qt.QueuedConnection`* (or `Qt.AutoConnection` which auto-queues across threads). Verify that any slot receiving `QtEventBus` signals lives on the main thread.

---

## 4. Mapping Existing Project Code to the Pattern

| Component today | Pattern | Notes |
|---|---|---|
| `SqLiteDataApi` (backend) | Repository (Infra layer) | Today: god-DataApi. Target: split per aggregate. No Qt imports. |
| `OllamaApi` / `OpenAICompatibleProvider` / `AnthropicProvider` / `GeminiProvider` | Provider (Infra layer, implements `LLMApi` ABC) | No Qt imports. |
| `BenchmarkExecutionTask` (`ui/qt_classes/`) | **Adapter (Pattern B)** | Wraps the run-execution use-case in `QRunnable`. Correctly placed. |
| `QtBenchmarkFlowApi` | **Adapter (Pattern B/C)** | Lifecycle wrapper around the benchmark flow. Correct location. |
| `QtEventBus` | Adapter helper | Lives in `ui/qt_classes/`. UI subscribes; adapter publishes. Correct. |
| `NewRunWidgetController` / `ResultWidgetController` / `LogWidgetController` | Presentation | Today these are `*Controller`; new refactored ones use `*Presenter`. |
| `*Widget` classes | View | Many today mix logic in slots — extract during refactor (see [refactoring-playbook.md](refactoring-playbook.md)). |

---

## 5. Swap Properties (acceptance criteria for the boundary)

If the boundary is correct, ALL of these swaps require editing **exactly one** layer:

### Swap UI for a CLI
- Replace `ui/` with `cli/main.py` that constructs the same use-cases and calls them synchronously.
- `backend/` untouched. `ui/qt_classes/` adapters not used.
- If this requires changes in `backend/`, the backend has Qt leaking into it.

### Swap SQLite for Postgres
- Add `PostgresRunsRepository(RunsRepository)` in `backend/services/<feature>/repository.py`.
- Edit `app_context.py` to instantiate the new class.
- `backend/core/` and `ui/` untouched.

### Swap `openai` SDK for direct `httpx`
- Add `HttpxOpenAIProvider(LLMApi)` implementation.
- Edit `app_context.py`.
- `backend/core/`, presenters, views untouched.

### Add a web UI alongside the desktop UI
- Wire a new composition root reading the same ABCs.
- `backend/` shared between both UIs.
- The desktop UI is unaffected.

If any of the above requires touching more than one layer, file the leak as a refactor TODO and fix the boundary.

---

## 6. Anti-Patterns at the Boundary

| Anti-pattern | Symptom | Why it's wrong | Fix |
|---|---|---|---|
| `from PySide6.QtCore import Signal` in `backend/services/foo.py` | Backend depends on Qt | Backend can't be tested without `QApplication`; can't be swapped | Use `psygnal.Signal` (target) or callback Protocol |
| `import ollama_llm_bench.ui` in `backend/` | Backend imports UI | Reverse dependency direction | Move the symbol the backend uses into `backend/core/` |
| Widget instantiates a `RunsRepository` directly | Widget knows persistence shape | Widget can't be tested in isolation | Constructor-inject the presenter / controller |
| `ContextProvider.get_context()` inside a widget | Service locator anti-pattern | Hidden dependency; un-testable | Constructor-inject |
| Use-case `execute()` calls `QtEventBus` | Backend depends on Qt's event bus | Same problem as importing Signal | Backend uses `psygnal` or a callback Protocol; adapter re-emits to `QtEventBus` |
| `QObject` subclass in `backend/services/` | Backend is Qt-aware | Same as above | Move the `QObject` half into `ui/qt_classes/` as an adapter |
| Presenter imports a concrete `OpenAICompatibleProvider` | Presenter depends on Infrastructure | Can't test presenter without instantiating the real provider | Depend on the `LLMApi` ABC |
| Worker thread updates a widget directly | `widget.setText(...)` from `QRunnable.run()` | Race conditions, crashes | Emit a signal, handle on main thread |
| Backend `Iterator` that holds an open SQLite connection across yields | Connection lifetime tied to UI's consumption rate | Connection leaks, locks held | Use a snapshot list, or scope connection inside `__next__`, or accept callback to handle each yielded item |

---

## 7. Migration to `psygnal` — when and how

Today (acceptable): backend events flow through synchronous returns + adapter-emitted Qt signals.

Target: backend events flow through `psygnal` + a `BackendEventBridge` adapter.

**Why migrate:**

- Today, a backend method that emits multiple events forces the caller (adapter) to iterate. The use-case can't naturally emit "task completed" mid-execution.
- With `psygnal`, the use-case emits events as it processes; the adapter subscribes once and re-emits. Code is more linear.

**Migration steps:**

1. Add `psygnal>=0.10` to `pyproject.toml` runtime dependencies.
2. Pick ONE use-case to migrate (recommend `StartBenchmarkRunUseCase` since it has the most events).
3. Create `backend/core/events.py` with the event dataclasses + `BenchmarkEvents` class.
4. Modify the use-case to take `BenchmarkEvents` in `__init__` and emit during `execute()`.
5. Create `ui/qt_classes/backend_event_bridge.py` that subscribes to `BenchmarkEvents` and re-emits via `QtEventBus`.
6. Update `app_context.py` to wire both.
7. Run `./scripts/ai-check.sh`. The presenters continue to subscribe to `QtEventBus` — they don't know `psygnal` exists.

**Don't migrate:**

- Single-event use-cases (returning the event is simpler).
- One-shot health checks (synchronous return is fine).

---

## 8. Decision: Pattern A, B, or C?

```
Is the operation expected to complete in < 50 ms on the main thread?
  └─ YES → Pattern A (synchronous use-case call from presenter)
  └─ NO ↓

Does the operation emit a stream of events during execution?
  └─ YES → Pattern C (psygnal events + bridge), or Pattern B if not yet migrated
  └─ NO ↓

The operation is one-shot but slow → Pattern B (QRunnable adapter)
```

If unsure, default to Pattern B — it's never wrong to put slow work on a worker. The overhead is negligible compared to a UI freeze.
