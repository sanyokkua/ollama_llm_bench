---
name: python-developer
description: Python coding standards for Ollama LLM Bench — frozen dataclasses, ABC/Protocol interfaces, constructor DI via ContextProvider, strict type hints, and project conventions. Use when writing or reviewing any Python code.
allowed-tools: Read, Grep, Glob
---

# Python Developer — Ollama LLM Bench

## This Project's Stack

- **Python 3.13+** with strict type hints on every function, method, and variable
- **PySide6** — Qt framework for UI
- **UV** — package manager with hatchling build backend
- **SQLite** via stdlib `sqlite3` — benchmark data persistence
- **openai** — OpenAI-compatible provider client (Ollama, LM Studio, OpenAI, Azure)
- **anthropic** — Anthropic provider client
- **google-genai** — Gemini provider client
- **PyYAML** — dataset parsing
- Constructor-based DI wired in `app_context.py` via `ContextProvider` singleton

Supporting files:
- [architecture.md](architecture.md) — Clean Architecture role mapping, layered feature mix, composition root, backend ↔ UI boundary, anti-patterns
- [repository-and-services.md](repository-and-services.md) — what a Repository / Service / Use-Case / Utility / Adapter is, with project examples
- [refactoring-guide.md](refactoring-guide.md) — step-by-step playbook for migrating legacy code (god services, util grab-bags, slot-driven logic) to the target architecture
- [examples.md](examples.md) — complete code templates for this project's patterns
- [logging.md](logging.md) — structlog log levels, placeholders, exception logging, hot path rules
- [docstrings.md](docstrings.md) — Google-style docstrings, tag ordering, prohibited practices
- [dependencies.md](dependencies.md) — approved libraries with versions, per-library rules, prohibited list

> **Companion skill:** [pyside6-ui](../pyside6-ui/SKILL.md) covers the UI half (Qt widgets, presenters, theming). This skill covers the backend half (Domain, Application, Infrastructure roles) and project-wide Python rules. They share the architecture and refactoring vocabulary.

---

## Core Coding Rules

**Be clear, not clever.** Code is read far more than written.

**Immutability by default:**
- Data classes: always `@dataclass(frozen=True)` — never mutate after construction
- Use `StrEnum` for string-based enumerations
- Fields should be `Final` unless mutation is explicitly required

**Constructor injection only:**
```python
# CORRECT for this project
class MyService(MyServiceApi):
    def __init__(self, *, data_api: DataApi, event_bus: EventBus) -> None:
        self._data_api = data_api
        self._event_bus = event_bus

# NEVER create dependencies internally
class MyService(MyServiceApi):
    def __init__(self) -> None:
        self._data_api = SqLiteDataApi(Path("db.sqlite"))  # WRONG
```

**Frozen dataclass pattern:**
```python
@dataclass(frozen=True)
class BenchmarkResult:
    result_id: int
    run_id: int
    task_id: str
    model_name: str
    status: BenchmarkResultStatus = BenchmarkResultStatus.NOT_COMPLETED
    llm_response: Optional[str] = None
    time_taken_ms: Optional[int] = None
```

---

## Python Type System

- **Prefer `Protocol`** for new interfaces — structural subtyping, no inheritance required
- **Use `ABC`** for existing interfaces and when shared state/default implementations are needed
- **`@dataclass(frozen=True)`** for all data-holder classes
- **`StrEnum`** for string enumerations — MUST NOT use plain strings or `Enum`
- **`Optional[T]`**: return type only — prefer `T | None` syntax in Python 3.13+
- **`typing.Final`** for constants and immutable bindings
- **`@override`** on every method that overrides a parent
- Streams: max 5 chained operations; extract complex pipelines to named functions
- Nesting depth: max 3 levels — use guard clauses (early returns) to flatten

### ABC vs Protocol Decision

```python
# Protocol — preferred for NEW interfaces (structural typing)
from typing import Protocol

class Serializable(Protocol):
    def to_dict(self) -> dict[str, str]: ...

# ABC — use for EXISTING interfaces and when shared state is needed
from abc import ABC, abstractmethod

class ResultApi(ABC):
    def __init__(self, *, data_api: DataApi):
        self._data_api = data_api  # Shared state in ABC

    @abstractmethod
    def retrieve_results(self, run_id: int) -> list[SummaryTableItem]: ...
```

---

## Package / Layer Rules

### Clean Architecture role mapping

Folders use the existing project names; their **architectural roles** come from Clean Architecture. Use both vocabularies — folder names when navigating code, role names when discussing design.

| Folder | Role | Allowed imports | What lives here |
|---|---|---|---|
| `backend/core/` | **Domain** | stdlib only | Frozen dataclasses, `StrEnum`, ABCs / Protocols, SQL schema constants, invariants. **NO Qt, NO I/O, NO providers.** |
| `backend/services/` | **Application + Infrastructure** | stdlib, third-party SDKs (`openai`, `anthropic`, `google-genai`, `sqlite3`, `yaml`), `backend/core/` | Use-case orchestrators (Application) and concrete repositories/clients (Infrastructure). **NO `PySide6.QtWidgets`. Limited `PySide6.QtCore` only when an existing ABC requires `QObject`+`Signal`.** |
| `backend/utils/` | **Cross-cutting helpers** | stdlib + `backend/core/` only | Pure functions used by ≥ 3 unrelated callers. **No state, no I/O, no Qt.** See [repository-and-services.md](repository-and-services.md) for the strict "what qualifies as a utility" test. |
| `ui/qt_classes/` | **UI Adapter (background → main thread bridge)** | stdlib, PySide6, `backend/core/`, `backend/services/` | `QRunnable`, `QThreadPool` wrappers, `EventBus`, `MetaQObjectABC`. **The only place where backend code crosses into Qt threading.** |
| `ui/controllers/` | **Presentation (Controllers / Presenters)** | stdlib, `backend/core/`, `backend/services/`, `ui/qt_classes/` | Existing classes keep the name **`*Controller`**. New components for refactored features use the name **`*Presenter`** (MVP Passive View — see [pyside6-ui/SKILL.md §"MVP for QWidgets"](../pyside6-ui/SKILL.md)). |
| `ui/widgets/` | **View** | stdlib, PySide6, `backend/core/` types, `ui/controllers/` | Rendering only. No business logic, no service or repository calls. |

### Import direction (strict — enforced by `import-linter`)

```
backend/core/ ← backend/services/ ← ui/qt_classes/ ← ui/controllers/ ← ui/widgets/
                                          ↑
                                    backend/utils/
```

Arrow = "is allowed to import from". `backend/core/` imports nothing from the project; `ui/widgets/` may import any layer to its left.

**Reverse imports are forbidden** and MUST be enforced in CI. See [architecture.md §"import-linter contracts"](architecture.md) for the exact `pyproject.toml` snippet.

### Cross-cutting rules

- **Absolute imports only** from root package: `from ollama_llm_bench.backend.core.models import BenchmarkRun`
- MUST NOT use relative imports
- No cyclic dependencies — insert an ABC / Protocol in `backend/core/interfaces.py` to break cycles
- A file's location dictates what it may do — if logic needs to live in Qt-aware code, move the file; **never weaken the rule for one file**

### Layered Feature Mix (target structure during refactoring)

Pure layered (current state) works up to ~5 KLOC; past that, change-locality suffers — touching one feature requires editing five folders. The project is already past that threshold.

**Target:** keep `backend/core/`, `backend/utils/`, `ui/qt_classes/` as cross-cutting layers, but group new / refactored work into **feature folders** under `backend/services/` and `ui/` that each contain their own internal layers.

```
backend/services/benchmark/        ← feature folder
    use_cases.py                   ← Application layer (orchestrates)
    repository.py                  ← Infrastructure layer (SQLite I/O)
    judge.py                       ← Infrastructure layer (LLM call)
    __init__.py                    ← public API of the feature

ui/widgets/new_run/                ← feature component
    view.py                        ← View (QWidget)
    presenter.py                   ← Presenter (QObject, no widgets)
    model.py                       ← optional: QAbstractTableModel adapter
    state.py                       ← optional: frozen dataclass for view state
    __init__.py                    ← public API of the component
```

**Rules:**

- Feature folders MAY have their own `_utils.py` for helpers used only within that feature — keep utilities co-located with their single consumer.
- A helper graduates to `backend/utils/` only when it is consumed by **≥ 3 unrelated features** AND is pure and generic.
- Cross-feature coordination flows through `QtEventBus` (UI) or domain events (backend) — **never via direct imports between sibling feature folders**.
- The composition root (`app_context.py`) is allowed to import any feature's public API and wire them together.

See [architecture.md](architecture.md) for the full template, decision matrix by project size, and refactor migration order.

---

## Service vs Utility vs Repository vs Manager (decision table)

A frequent confusion: "where does this code go?" Use this decision table — when in doubt, read [repository-and-services.md](repository-and-services.md) for full examples.

| Concept | Lives in | Role (Clean Architecture) | Test |
|---|---|---|---|
| **Domain Entity** | `backend/core/models.py` | Domain | Frozen dataclass with invariants. No I/O, no Qt. Example: `BenchmarkRun`, `BenchmarkResult`. |
| **Value Object** | `backend/core/models.py` | Domain | Frozen dataclass with no identity, equal by value. Example: `InferenceResponse`. |
| **Repository** | `backend/services/<feature>/` | Infrastructure | A class that owns persistence for one aggregate. Method names are domain verbs (`save_run`, `list_runs`), not SQL verbs (`insert`, `update`). Example: `SqLiteDataApi` (one per aggregate is preferred long-term). |
| **Use-Case (Application Service)** | `backend/services/<feature>/use_cases.py` | Application | A single business operation. Takes repositories/clients as constructor args, returns a domain object. Prefer **one class or function per use case** over a god-service with 20 methods. |
| **Provider / Client** | `backend/services/<feature>/` | Infrastructure | Wraps an external SDK (`openai`, `anthropic`, `ollama`). Implements an ABC defined in `backend/core/interfaces.py`. |
| **Utility** | `backend/utils/` OR feature-local `_utils.py` | Cross-cutting | **Pure function**, **generic**, **used by ≥ 3 unrelated features**. If any of those three is false, it's not a utility — it's domain logic or feature-private helper in disguise. |
| **Adapter** | `ui/qt_classes/` | UI Adapter | Crosses the backend → UI threading boundary. Wraps a use-case call inside a `QRunnable` and exposes a `QObject` for signals. |
| **Controller (existing)** | `ui/controllers/` | Presentation | Mediates between widget and services. Use this name only when modifying existing files. |
| **Presenter (new code)** | `ui/controllers/` | Presentation (MVP Passive View) | New components introduced during refactoring use this name. See [pyside6-ui/SKILL.md](../pyside6-ui/SKILL.md). |
| **Manager** | ❌ DO NOT CREATE | — | "Manager" is a smell. Replace with a precise noun: `SessionStore`, `ConnectionPool`, `WindowRegistry`, `ProviderRegistry`. |

### Use-case pattern (preferred over god-service)

```python
# GOOD — one use-case per business operation
class StartBenchmarkRunUseCase:
    def __init__(self, *, runs_repo: RunsRepository, task_loader: TaskLoader) -> None:
        self._runs_repo = runs_repo
        self._task_loader = task_loader

    def execute(self, *, models: list[str], dataset_path: Path) -> BenchmarkRun:
        tasks = self._task_loader.load(dataset_path)
        run = BenchmarkRun.new(models=models, tasks=tasks)
        self._runs_repo.create(run)
        return run

# BAD — god-service collecting every benchmark operation
class BenchmarkService:
    def start_run(self, ...): ...
    def pause_run(self, ...): ...
    def stop_run(self, ...): ...
    def export_results(self, ...): ...
    def compute_averages(self, ...): ...
    def re_judge_run(self, ...): ...
    # ...30 more methods, 12-arg __init__
```

A class is justified when several closely-related operations share state or configuration. Otherwise, prefer a module of plain functions or one class per use-case.

### Utility test — the "3 + pure + generic" rule

Before adding to `backend/utils/`, the function MUST satisfy ALL THREE:

1. **Pure** — no I/O, no global state, deterministic given inputs
2. **Generic** — domain-agnostic (no `BenchmarkResult`-shaped arguments; works on `str`, `int`, `list`, generic types)
3. **Used by ≥ 3 unrelated features** — if only the benchmark feature uses it, it lives in `backend/services/benchmark/_utils.py`

If any test fails, the function does **not** belong in `backend/utils/`. Move it into the feature folder that uses it.

Generic names (`utils.py`, `helpers.py`, `common.py`, `misc.py`, `lib.py`) are FORBIDDEN at the top of any feature folder — name files by what they do (`text_parsing.py`, `time_formatting.py`, `run_sorting.py`).

---

## Backend ↔ UI Boundary

This is the most important architectural rule for the project: **the backend must not know the UI exists, and the UI must talk to the backend only through abstract APIs (ABCs / Protocols).** If either side needs to be replaced (e.g., a CLI front-end, a different LLM SDK), only the boundary moves.

### The three zones

```
┌──────────────────────────────────────────────────────────────┐
│ Pure Python Backend                                          │
│   backend/core/   ← Domain (no Qt, no I/O)                   │
│   backend/services/ ← Application + Infrastructure          │
│                                                              │
│   Communicates results via:                                  │
│   - return values (synchronous)                              │
│   - generators / iterators (streaming)                       │
│   - psygnal.Signal or callback Protocols (events) [target]   │
└────────────────────┬─────────────────────────────────────────┘
                     │ crosses the boundary
┌────────────────────▼─────────────────────────────────────────┐
│ UI Adapter (qt_classes/)                                     │
│   - Wraps backend calls in QRunnable / QThreadPool           │
│   - Translates backend events into Qt Signals (QtEventBus)   │
│   - This is the ONLY layer that bridges threads              │
└────────────────────┬─────────────────────────────────────────┘
                     │ Qt signals (thread-safe, queued)
┌────────────────────▼─────────────────────────────────────────┐
│ UI (controllers/ + widgets/)                                 │
│   - Subscribes to QtEventBus                                 │
│   - Calls backend through injected ABCs                      │
│   - Never imports backend/services concrete classes directly │
└──────────────────────────────────────────────────────────────┘
```

### Rules — kept simple

1. **Backend** (`backend/core/` + `backend/services/`) imports nothing from `PySide6.QtWidgets` and avoids `PySide6.QtCore` except where existing ABCs require it. New backend code MUST be Qt-free.
2. **UI** never imports a backend `*Service` concrete class — it depends on the ABC defined in `backend/core/interfaces.py`. The composition root in `app_context.py` is the only place that wires concrete to abstract.
3. **Threading bridge** lives exclusively in `ui/qt_classes/`. Backend code returns plain Python values or yields from generators; the adapter wraps those in `QRunnable`s and emits Qt signals.
4. **Domain events** (events that the backend wants to publish, e.g., "run completed", "task failed") use one of:
   - **Today**: synchronous return values + `QtEventBus` re-emission in the adapter.
   - **Target**: `psygnal.Signal` declared in `backend/core/events.py` (Qt-free observer pattern). The UI adapter subscribes to `psygnal` and re-emits as a Qt `Signal` on the main thread. See [repository-and-services.md §"Domain events"](repository-and-services.md).
5. **What may cross the boundary** = frozen dataclasses, `StrEnum`s, primitives, lists, dicts of primitives. **Never** Qt objects, **never** widget references.

### Why this matters for swap-out

| Want to do | What changes |
|---|---|
| Replace PySide6 with a CLI front-end | Re-implement `ui/` only. Backend untouched. |
| Replace SQLite with Postgres | Replace `SqLiteDataApi` with `PostgresDataApi`, rewire in `app_context.py`. Domain untouched. |
| Replace `openai` SDK with `httpx` calls | Replace the `OpenAICompatibleProvider` concrete class, keep the `LLMApi` ABC. UI untouched. |
| Add a second UI (web) | Wire a new web composition root reading the same ABCs. Backend untouched. |

If a swap-out requires editing more than one layer, the boundary is wrong — see [architecture.md §"Anti-patterns"](architecture.md).

---

## DI Patterns

**Wiring location:** `app_context.py` — `_create_app_context()` function

**Startup chain:**
```
ContextProvider.initialize(app_root, dataset_path)
  → _create_app_context() builds all services and controllers
  → ApplicationContext stores references
  → ContextProvider.get_context() provides access
```

**Adding a new service requires:**
1. ABC in `backend/core/interfaces.py`
2. Concrete class in `backend/services/`
3. Constructor parameter in `ApplicationContext.__init__()`
4. Property accessor with `@override` in `ApplicationContext`
5. Instantiation in `_create_app_context()`

---

## Threading

- **Main thread**: all widget reads/writes, signal emissions
- **Background**: `QThreadPool` + `QRunnable` (see `BenchmarkExecutionTask`)
- **Signal bridge**: `QRunnable` holds a nested `Signals(QObject)` class for emitting progress
- **MetaQObjectABC**: required metaclass when combining `QObject` + `ABC`

```python
# Correct: emit signal from QRunnable
self.signals.progress.emit(status_msg)

# WRONG: mutate widget from background thread
self.table_widget.setItem(0, 0, item)  # crashes
```

---

## Error Handling

- Never throw from pipeline methods (`run()`, `_execute_benchmark()`) to callers
- Capture errors in model fields: `BenchmarkResult.error_message`, `InferenceResponse.has_error`
- Use `logging.getLogger(__name__)` — never `print()`
- Never log AND reraise — pick one
- Use specific exception types, not bare `except Exception`

---

## Naming & Style

- Classes: `UpperCamelCase`, nouns — suffix ABCs with `Api` (e.g., `DataApi`, `LLMApi`)
- Methods/functions: `snake_case`, verbs; boolean accessors: `is_`/`has_`/`can_` prefix
- Constants (`Final`): `UPPER_SNAKE_CASE`
- Private members: single leading underscore `_`
- No magic numbers — extract to named constants
- Functions ≤ 30 lines; refactor if > 50 lines
- No empty except blocks

---

## What NOT to Do

- Never use Django, Flask, FastAPI, SQLAlchemy — wrong stack entirely
- Never use `datetime.datetime.now()` without timezone — use `time.time()` for timestamps
- Never use `os.path` — use `pathlib.Path`
- Never use mutable default arguments (`def f(items=[])`)
- Never use `print()` for logging — use `logging.getLogger(__name__)`
- Never use field injection or service locator patterns
- Never return `None` from methods that promise a collection — return empty list
- Never use `# type: ignore` without specific error code
- Never use `# noqa` without specific rule code

---

## Checklist Before Finishing

- [ ] Uses constructor injection with keyword-only args (`def __init__(self, *, dep: Dep)`)
- [ ] Data classes use `@dataclass(frozen=True)`
- [ ] No exceptions thrown to callers from pipeline methods
- [ ] New ABCs added to `backend/core/interfaces.py`
- [ ] `@override` on all overridden methods
- [ ] Absolute imports from `ollama_llm_bench.*`
- [ ] No Django/Flask/SQLAlchemy imports
- [ ] `logging.getLogger(__name__)` for logging
- [ ] Type hints on every function, method, and variable
