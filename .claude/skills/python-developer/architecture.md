# Python Developer — Architecture Reference

Project-wide architectural rules for Ollama LLM Bench. See [SKILL.md](SKILL.md) for the layered-rules quick reference; this file is the full architectural contract.

This skill and [pyside6-ui](../pyside6-ui/SKILL.md) share this vocabulary. When working inside `ui/`, also read [pyside6-ui/references/component-architecture.md](../pyside6-ui/references/component-architecture.md).

---

## 1. Clean Architecture Role Mapping

The project uses simple folder names; their architectural roles are from **Clean Architecture** (entity → use-case → adapter → framework). Both vocabularies are correct — use folder names when navigating code, role names when discussing design.

| Folder | Clean Architecture role | Allowed external deps | Responsibility |
|---|---|---|---|
| `backend/core/` | **Domain** (entities, value objects, ports) | stdlib only | What the app *is* — invariants, types, abstract interfaces. Could be lifted into a separate library tomorrow. |
| `backend/services/` | **Application** (use-cases) + **Infrastructure** (adapters to external systems) | stdlib + approved SDKs (`openai`, `anthropic`, `google-genai`, `sqlite3`, `yaml`, `httpx`) | The "doing" — orchestrate domain objects, talk to external systems via abstract interfaces declared in `core/`. |
| `backend/utils/` | **Cross-cutting helpers** | stdlib + `backend/core/` | Pure, generic, ≥ 3-consumer functions. See [repository-and-services.md §"Utility test"](repository-and-services.md). |
| `ui/qt_classes/` | **UI Adapter** (boundary crossing) | PySide6 + everything backend | Bridges the synchronous, thread-safe backend to Qt's main-thread event loop. The **only** place threading and Qt signals exist for non-presentation reasons. |
| `ui/controllers/` | **Presentation** (Controllers / Presenters) | PySide6 + everything backend (via ABCs only) | One class per feature/screen/dialog mediating user input → use-case → view update. |
| `ui/widgets/` | **View** | PySide6 + `backend/core/` types | Rendering. No service or repository calls. Reads view state from a presenter; emits user-intent signals up. |

### Dependency Inversion Principle in practice

- A `controller` depends on `LLMApi` (ABC in `backend/core/interfaces.py`), **not** on `OpenAICompatibleProvider` (concrete class in `backend/services/`).
- A `use-case` depends on `RunsRepository` (Protocol), **not** on `SqLiteDataApi` (concrete class).
- The composition root (`app_context.py`) is the only file that imports concretes from both sides — it wires them together. If any other file imports a concrete from the wrong side, the boundary has leaked.

---

## 2. Layered Feature Mix (target structure)

Pure layered architecture (one folder per technical role) starts to hurt past ~5 KLOC because every feature change touches five folders. The project is past that threshold.

**Target:** keep `backend/core/`, `backend/utils/`, and `ui/qt_classes/` as cross-cutting layers, but organize new and refactored work into **feature folders** under `backend/services/` and `ui/widgets/` / `ui/controllers/`. Each feature folder is internally layered.

### Cross-cutting layers (keep flat)

```
backend/core/
    models.py           # Frozen dataclasses, StrEnums
    interfaces.py       # All ABCs (LLMApi, DataApi, EventBus, etc.)
    constants.py        # Application-wide constants
    events.py           # Domain event dataclasses (and psygnal signals when migrated)
    sql_schema.py       # SQL DDL strings

backend/utils/
    text_parsing.py     # 3+ consumers, pure
    time_formatting.py
    run_sorting.py

ui/qt_classes/
    qt_event_bus.py            # QtEventBus
    qt_benchmark_execution_task.py
    meta_class.py              # MetaQObjectABC
```

### Feature folders (new and refactored work)

```
backend/services/benchmark/
    __init__.py                # public API of the feature
    use_cases.py               # StartBenchmarkRunUseCase, PauseRunUseCase, StopRunUseCase
    repository.py              # BenchmarkRepository (Infrastructure)
    judge.py                   # JudgeRunner (Infrastructure, wraps LLM call)
    _utils.py                  # benchmark-specific helpers (NOT in backend/utils/)
    _internal_types.py         # types used only inside this feature
    tests/
        test_use_cases.py

backend/services/provider/
    __init__.py
    registry.py                # ProviderRegistry
    openai_compatible.py       # OpenAICompatibleProvider implements LLMApi
    anthropic.py               # AnthropicProvider implements LLMApi
    gemini.py                  # GeminiProvider implements LLMApi
    health.py                  # ProviderHealthChecker
    tests/
```

### UI feature components

```
ui/widgets/new_run/
    __init__.py                # exports NewRunComponent
    view.py                    # NewRunView(QWidget) — passive view
    presenter.py               # NewRunPresenter(QObject) — Qt-aware, no widgets
    model.py                   # optional: model adapters for tables
    state.py                   # frozen dataclass: NewRunViewState
    _ui_helpers.py             # widget construction helpers (component-private)
```

### Rules for the mix

1. **Cross-cutting layers stay flat.** `backend/core/` is not subdivided by feature — it holds project-wide types.
2. **Feature folders are internally layered.** `use_cases.py` (Application) + `repository.py` (Infrastructure) + `_utils.py` (helpers) + `tests/`.
3. **Feature-private helpers** use a leading underscore in the filename (`_utils.py`, `_internal_types.py`) and are NOT imported from outside the feature folder.
4. **Cross-feature coordination** flows through `QtEventBus` (UI) or domain events (backend). **No sibling-feature imports** — `benchmark/` and `provider/` may both import `core/`, but not each other.
5. **Composition root may import everything.** Only `app_context.py` reaches into every feature's public `__init__.py` to wire things up.
6. **The feature's `__init__.py` defines its public API** with `__all__`. Anything not in `__all__` is internal.

### Decision: when to introduce a feature folder

Introduce one when ALL of these hold:

- The feature has its own use-case(s) — at least one operation a user cares about.
- The feature has ≥ 2 internal files (a use-case + a repository, or a presenter + a view).
- The feature has its own data shape or external dependency (SDK, file format).

Until then, a flat file in `backend/services/` is acceptable. The point is locality of change — once a single feature spans 3+ files, group them.

---

## 3. Composition Root

The **composition root** is the one place in the program where concrete classes are instantiated and wired together. In this project: `src/ollama_llm_bench/app_context.py`, function `_create_app_context()`.

### Rules

1. **Only the composition root may import concretes from both layers.** Every other module imports the ABC.
2. **All dependencies passed as keyword-only constructor arguments.** No service locator pattern, no `QApplication.instance()` lookup, no global registry.
3. **Single instantiation point.** A given concrete class is constructed once in the composition root, then shared. Singletons via `__new__` or metaclass are forbidden.
4. **`ContextProvider` is a thin façade** providing `get_context()` for cases where constructor injection is impractical (e.g., framework callbacks). MUST NOT use it as a service locator from inside services or presenters that could have received the dep via constructor.

### Adding a new service

1. Define the ABC / Protocol in `backend/core/interfaces.py`.
2. Implement the concrete class in `backend/services/<feature>/`.
3. Add a parameter to `ApplicationContext.__init__()` with `@property` accessor and `@override`.
4. Instantiate and pass in `_create_app_context()`.
5. Constructor-inject into every consumer.

### Anti-pattern: hidden service locator

```python
# WRONG — leaf widget reaches into the context provider
class MyWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx = ContextProvider.get_context()  # service locator anti-pattern
        self._data_api = self._ctx.data_api

# RIGHT — controller is injected explicitly
class MyWidget(QWidget):
    def __init__(self, *, controller: MyController, parent=None):
        super().__init__(parent)
        self._controller = controller
```

---

## 4. Backend ↔ UI Boundary (full contract)

The boundary contract is the project's most important architectural rule. See [SKILL.md §"Backend ↔ UI Boundary"](SKILL.md) for the quick version and [pyside6-ui/references/backend-ui-boundary.md](../pyside6-ui/references/backend-ui-boundary.md) for the UI side.

### What flows across the boundary

| Direction | Allowed | Forbidden |
|---|---|---|
| **UI → Backend** | Method calls on injected ABCs with frozen-dataclass / primitive arguments | Passing widgets, `QObject`s, mutable state |
| **Backend → UI (sync)** | Return values: frozen dataclasses, primitives, lists/dicts of those | Returning `QObject`, `QWidget`, anything Qt |
| **Backend → UI (async/event)** | `psygnal.Signal` (target) or callback Protocol (current) — re-emitted as Qt signal by an Adapter in `ui/qt_classes/` | Direct `Signal` on a backend class (couples backend to Qt) |
| **Backend → UI (stream)** | Generator / iterator yielding domain objects | Generator that yields widgets, calls UI methods, or assumes a Qt event loop |

### The adapter pattern at the boundary

`ui/qt_classes/` exists because:
- Backend code is synchronous and Qt-agnostic.
- The UI's main thread must remain responsive (50 ms budget).
- Therefore some component must take a synchronous backend call, run it on a background thread, and deliver results into the Qt main loop.

That component is an **adapter**. The canonical example is `BenchmarkExecutionTask`:

```
[Use-case (backend/services/benchmark/use_cases.py)]
     ↓ called from
[QtBenchmarkFlowApi adapter (ui/qt_classes/qt_benchmark_flow_api.py)]
     ↓ wraps in
[BenchmarkExecutionTask (QRunnable, ui/qt_classes/qt_benchmark_execution_task.py)]
     ↓ emits
[Signals on Signals(QObject)]
     ↓ connected to
[QtEventBus.emit_*()]
     ↓ subscribed by
[Controllers / Presenters (ui/controllers/)]
     ↓ updates
[Widgets (ui/widgets/)]
```

The adapter is the ONLY thing in the codebase that:
- Imports both the backend use-case and `QObject`.
- Crosses threads.
- Translates backend events into Qt signals.

Everything else either lives entirely on one side or sees only the adapter's Qt-side API.

### Why this enables independent evolution

- **To replace the UI** with a CLI: write a `cli_main.py` that instantiates use-cases directly. No adapter, no Qt — just synchronous calls. Backend untouched.
- **To replace the backend** (e.g., move LLM calls to a remote service): implement the existing ABCs against the new backend. Adapter and UI untouched.
- **To split into two processes** (UI separate from backend): replace the adapter with an IPC adapter (gRPC / pipe / WebSocket). Backend untouched, presenters untouched.

If any of these requires editing multiple layers, the boundary has leaked.

### Target: `psygnal` for Qt-free domain events

Today, backend code emits events by either (a) returning them from the use-case or (b) calling a callback Protocol. Target state introduces `psygnal` for native publish/subscribe inside the backend:

```python
# backend/core/events.py — Qt-free
from psygnal import Signal
from dataclasses import dataclass

@dataclass(frozen=True)
class TaskCompleted:
    task_id: str
    duration_ms: int

class BenchmarkEvents:
    """Qt-free domain events published by backend use-cases."""
    task_completed = Signal(TaskCompleted)
    run_finished = Signal(object)   # BenchmarkRun
    run_failed = Signal(str)        # error message

# backend/services/benchmark/use_cases.py
class StartBenchmarkRunUseCase:
    def __init__(self, *, events: BenchmarkEvents, repo: RunsRepository) -> None:
        self._events = events
        self._repo = repo

    def execute(self, ...) -> BenchmarkRun:
        ...
        self._events.task_completed.emit(TaskCompleted(task_id=..., duration_ms=...))
        ...

# ui/qt_classes/event_bridge.py — adapter
class BackendEventBridge:
    def __init__(self, *, backend_events: BenchmarkEvents, qt_event_bus: QtEventBus) -> None:
        backend_events.task_completed.connect(self._on_task_completed)
        self._bus = qt_event_bus

    def _on_task_completed(self, evt: TaskCompleted) -> None:
        self._bus.emit_task_completed(evt)
```

This keeps backend code 100% Qt-free while preserving Qt's main-thread guarantees in the UI. Adopt incrementally — one event source at a time. Add `psygnal` to `pyproject.toml` only when the first migration begins.

---

## 5. `import-linter` Contracts

Encode the architectural rules in `pyproject.toml` so CI fails when the boundary is violated:

```toml
[tool.importlinter]
root_packages = ["ollama_llm_bench"]

[[tool.importlinter.contracts]]
name = "Core must not import Qt modules"
type = "forbidden"
source_modules = ["ollama_llm_bench.backend.core"]
forbidden_modules = ["PySide6", "PyQt6"]

[[tool.importlinter.contracts]]
name = "Backend services must not import PySide6.QtWidgets"
type = "forbidden"
source_modules = ["ollama_llm_bench.backend.services"]
forbidden_modules = ["PySide6.QtWidgets"]

[[tool.importlinter.contracts]]
name = "Backend must not import the UI"
type = "forbidden"
source_modules = ["ollama_llm_bench.backend"]
forbidden_modules = ["ollama_llm_bench.ui"]

[[tool.importlinter.contracts]]
name = "Layered dependency direction"
type = "layers"
layers = [
    "ollama_llm_bench.ui.widgets",
    "ollama_llm_bench.ui.controllers",
    "ollama_llm_bench.ui.qt_classes",
    "ollama_llm_bench.backend.services",
    "ollama_llm_bench.backend.core",
]

[[tool.importlinter.contracts]]
name = "Backend utils must not import backend services or ui"
type = "forbidden"
source_modules = ["ollama_llm_bench.backend.utils"]
forbidden_modules = [
    "ollama_llm_bench.backend.services",
    "ollama_llm_bench.ui",
]
```

Run as part of `./scripts/ai-check.sh`. Add to CI before merge.

---

## 6. Anti-Patterns (project-specific)

### God Service

> A `BenchmarkService` with 30 methods covering start/pause/stop/export/judge/re-judge/compute.

**Why it fails:** Every change touches the same class. Tests need huge fixtures. New developers can't see what each method depends on.

**Fix:** Split into use-cases. One class per business operation, each with a focused 1–3 line `execute()`.

### Manager Smell

> `ConfigurationManager`, `WindowManager`, `BenchmarkManager`.

**Why it fails:** "Manager" carries no information about what the class does.

**Fix:** Rename with a precise noun.
- `ConfigurationManager` → `AppSettingsRepository` or `AppSettingsStore`
- `WindowManager` → `WindowRegistry`
- `BenchmarkManager` → split into `BenchmarkFlow`, `BenchmarkRepository`, or specific use-cases.

### Java-style Interface Explosion

> Every concrete class has an `I*Api` ABC, and there's only one implementation.

**Why it fails:** Pure ceremony. Adds 2 files for every 1 needed.

**Fix:** Define an ABC only when (a) you have ≥ 2 implementations OR a planned test double, OR (b) the ABC crosses a layer boundary (Domain ↔ Infrastructure). For an internal helper used in one place, just use the concrete class.

> **Project caveat:** existing project ABCs follow this pattern broadly. Keep them — refactoring them all is not worth the churn. Apply the rule to new code.

### Backend Importing Qt

> `backend/services/foo.py` imports `Signal` to emit events.

**Why it fails:** Backend becomes un-testable without `QApplication`; backend can't be swapped out.

**Fix:** Use `psygnal.Signal` (target) or a callback Protocol declared in `backend/core/interfaces.py`. Re-emit as Qt signal in `ui/qt_classes/`.

### Util Grab-Bag

> `backend/utils/utils.py` with 2000 lines of unrelated functions.

**Why it fails:** No cohesion; every change risks unrelated regressions.

**Fix:** Apply the "3 + pure + generic" test. Co-locate single-feature helpers in `backend/services/<feature>/_utils.py`. Keep `backend/utils/` files small and single-purpose.

### Side Effects on Import

> `backend/services/foo.py` opens a DB connection at module load time.

**Why it fails:** Slow imports, untestable (importing `foo` requires the DB to be reachable), breaks tooling.

**Fix:** All side effects inside functions / `__init__`. Imports must be free of work beyond declaration.

### Cyclic Imports

> `a.py` imports `b.py`, `b.py` imports `a.py`.

**Why it fails:** `ImportError: cannot import name X from partially initialized module`.

**Fix order:**
1. Move the shared symbol to a "below" module (typically into `backend/core/`).
2. If the cycle exists only for type hints, use `if TYPE_CHECKING: from x import Y` plus `from __future__ import annotations`.
3. If neither works, the dependency is bidirectional — add an ABC in `backend/core/interfaces.py` and let one side depend on the abstraction.

### Hidden Service Locator

> A widget reaches into `ContextProvider.get_context()` to find its services.

**Why it fails:** Widget can't be tested in isolation; dependencies are invisible from the constructor signature.

**Fix:** Constructor-inject the controller. Only the composition root knows about `ContextProvider`.

---

## 7. Project-Size Decision Matrix

This project is in the **5–30 KLOC** band. Apply these defaults:

| Concern | This project's default | Stricter (if pain appears) |
|---|---|---|
| Layout | hybrid (cross-cutting layers + feature folders) | + plugin contracts |
| Domain/UI separation | mandatory; PySide6 only in `ui/` | enforced by `import-linter` in CI |
| Interfaces | Protocols at boundaries, ABCs where shared state | Protocols everywhere |
| DI | manual constructor injection via `app_context.py` | + scoped factories |
| Repository pattern | recommended for new code | mandatory |
| Use-case pattern | recommended | mandatory |
| Testing | pytest + pytest-qt | + integration + contract tests |
| Threading | `QThreadPool` + `QRunnable` | + `QThread.moveToThread` for long-lived workers; consider `qasync` for I/O-bound |
| Configuration | dataclass + project conventions | `pydantic-settings` for env, `QSettings` for user prefs |
| Logging | stdlib `logging` | `structlog` (migration target) |

When the project grows past 30 KLOC, revisit: introduce explicit `domain/application/infrastructure` folders inside `backend/services/<feature>/`, adopt `psygnal` everywhere, consider plugin architecture only if extensibility becomes a product requirement.
