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
- [examples.md](examples.md) — complete code templates for this project's patterns
- [logging.md](logging.md) — structlog log levels, placeholders, exception logging, hot path rules
- [docstrings.md](docstrings.md) — Google-style docstrings, tag ordering, prohibited practices
- [dependencies.md](dependencies.md) — approved libraries with versions, per-library rules, prohibited list

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

- `backend/core/`: domain models, ABCs, constants — no Qt imports allowed
- `backend/services/`: concrete service implementations
- `ui/qt_classes/`: Qt infrastructure (EventBus, QRunnable tasks, MetaQObjectABC)
- `ui/controllers/`: controller classes mediating between UI and services
- `ui/widgets/`: PySide6 widget classes
- `backend/utils/`: standalone utilities — never imported by `backend/core/`

**Import direction** (strict — enforced by import-linter):
```
backend/core/ ← backend/services/ ← ui/qt_classes/ ← ui/controllers/ ← ui/widgets/
```

- **Absolute imports only** from root package: `from ollama_llm_bench.backend.core.models import BenchmarkRun`
- MUST NOT use relative imports
- No cyclic dependencies — insert an ABC in `core/interfaces.py` to break cycles

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
