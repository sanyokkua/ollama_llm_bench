# Developer Guide — Adding New Features

This guide shows how to add new functionality while respecting the project's layer rules, dependency injection pattern, and threading model.
Every example is adapted from real code in the repository; every file path is live.

## Before You Start

Read these first:

- [architecture.md](architecture.md) — layer boundaries and import rules
- [services-reference.md](services-reference.md) — existing ABCs to extend or emulate
- [data-model.md](data-model.md) — dataclass and enum conventions
- The `.claude/rules/*.md` files for the full coding standards

The golden rules:

1. **`core/` has no Qt imports.** Ever.
2. **Services have no Qt imports.** They must be unit-testable without a `QApplication`.
3. **All background-to-UI communication goes through `QtEventBus`.** No direct widget mutation from workers.
4. **Every dependency is injected via keyword-only constructor arguments.**
5. **Every data-holder class is `@dataclass(frozen=True)`.**
6. **Every overridden method carries `@override`.**
7. **No `print()` — use `logger = logging.getLogger(__name__)` at module level.**

## Recipe 1 — Add a New Dataclass to `core/models.py`

Models are pure, frozen, and strictly typed.

```python
# src/ollama_llm_bench/core/models.py
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ModelSpec:
    """
    Describes a model's runtime characteristics for benchmark planning.
    """
    model_name: str
    context_window: int
    parameter_count_b: float         # billions of parameters
    last_measured_ms: Optional[int] = None
```

Conventions from existing models:

- Module docstring is omitted — `models.py` does not have one currently.
- Class docstring is a one-line summary.
- Optional fields always use `Optional[T] | None = None` with a default.
- Required fields have no default.
- Use `tuple[str, ...]` for immutable sequences (see `NewRunWidgetStartEvent`).

The rule `kw_only=True` from the coding-style guide is **not** currently used in this project.
Existing dataclasses all use positional fields.
When adding new dataclasses you may adopt `kw_only=True` for classes with >2 fields, but update the whole file consistently if you do.

## Recipe 2 — Add a New Interface

### Decision: `Protocol` or `ABC`?

| Situation | Use |
|---|---|
| Pure behavioural contract, no shared state | `Protocol` (recommended by the coding rules) |
| Base class holds state or a default `__init__` | `ABC` (consistent with existing code) |

**Today's reality**: every interface in `core/interfaces.py` uses `ABC`.
Follow that pattern unless you have a reason to diverge.

### ABC Example

```python
# src/ollama_llm_bench/core/interfaces.py
from abc import ABC, abstractmethod
from typing import Optional

from ollama_llm_bench.core.models import ModelSpec


class ModelCatalogApi(ABC):
    """
    Abstract interface for discovering and describing available models.
    """

    @abstractmethod
    def list_specs(self) -> list[ModelSpec]:
        """
        Return metadata for every model the catalog knows about.

        Returns:
            List of ModelSpec instances, sorted by model_name.
        """

    @abstractmethod
    def get_spec(self, model_name: str) -> Optional[ModelSpec]:
        """
        Fetch a single model's metadata by name.

        Args:
            model_name: Name of the model.

        Returns:
            The matching ModelSpec, or None if no such model is known.
        """
```

Notes:

- No `pass` body — the `"""..."""` docstring is the body. Matches every existing ABC.
- Return concrete types (`list`, `Optional[T]`), accept abstract where possible.
- All signatures fully typed.

## Recipe 3 — Implement a New Service

Place the concrete class under `services/`.

```python
# src/ollama_llm_bench/services/json_model_catalog_api.py
import json
import logging
from pathlib import Path
from typing import Optional, override

from ollama_llm_bench.core.interfaces import ModelCatalogApi
from ollama_llm_bench.core.models import ModelSpec

logger = logging.getLogger(__name__)


class JsonModelCatalogApi(ModelCatalogApi):
    """
    JSON-backed implementation of ModelCatalogApi.
    Loads model specs from a single JSON file on first access.
    """

    def __init__(self, *, catalog_path: Path) -> None:
        """
        Initialize the JSON catalog.

        Args:
            catalog_path: Path to a JSON file containing a list of model specs.
        """
        self._catalog_path = catalog_path
        self._specs: list[ModelSpec] = []

    def _ensure_loaded(self) -> None:
        if self._specs:
            return
        logger.debug("Loading model specs from %s", self._catalog_path)
        with self._catalog_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        self._specs = [
            ModelSpec(
                model_name=entry["model_name"],
                context_window=int(entry["context_window"]),
                parameter_count_b=float(entry["parameter_count_b"]),
                last_measured_ms=entry.get("last_measured_ms"),
            )
            for entry in raw
        ]
        self._specs.sort(key=lambda s: s.model_name)

    @override
    def list_specs(self) -> list[ModelSpec]:
        self._ensure_loaded()
        return list(self._specs)

    @override
    def get_spec(self, model_name: str) -> Optional[ModelSpec]:
        self._ensure_loaded()
        for spec in self._specs:
            if spec.model_name == model_name:
                return spec
        return None
```

Conventions:

- Keyword-only constructor (`*,`).
- Module-level `logger = logging.getLogger(__name__)`.
- `@override` on every implementation of an abstract method.
- Never throw to the caller in getter methods — log and return empty/`None` (see `YamlBenchmarkTaskApi` for the pattern).
- No Qt imports anywhere in this file.

## Recipe 4 — Wire It Into `ApplicationContext`

Add the service in `src/ollama_llm_bench/app_context.py`.

1. **Import** the interface and implementation:

   ```python
   from ollama_llm_bench.core.interfaces import ModelCatalogApi
   from ollama_llm_bench.services.json_model_catalog_api import JsonModelCatalogApi
   ```

2. **Add a slot** on `ApplicationContext`:

   ```python
   __slots__ = (
       # ... existing slots ...
       '_model_catalog_api',
   )
   ```

3. **Accept it** in `ApplicationContext.__init__` (keyword-only) and store it:

   ```python
   def __init__(self, *, ..., model_catalog_api: ModelCatalogApi) -> None:
       ...
       self._model_catalog_api = model_catalog_api
   ```

4. **Expose a getter** via `AppContext` ABC **and** `ApplicationContext`:

   ```python
   # core/interfaces.py
   @abstractmethod
   def get_model_catalog_api(self) -> ModelCatalogApi: ...

   # app_context.py
   @override
   def get_model_catalog_api(self) -> ModelCatalogApi:
       return self._model_catalog_api
   ```

5. **Instantiate** inside `_create_app_context` and pass it to `ApplicationContext(...)`:

   ```python
   model_catalog_api = JsonModelCatalogApi(catalog_path=app_root / "models.json")
   return ApplicationContext(
       ...,
       model_catalog_api=model_catalog_api,
   )
   ```

Any controller that needs the new service simply adds it as a constructor kwarg and receives it in `_create_app_context`.

## Recipe 5 — Add a New EventBus Signal

All signals live in `QtEventBus` in `src/ollama_llm_bench/qt_classes/qt_event_bus.py`.

1. **Define the signal**:

   ```python
   class QtEventBus(QObject, EventBus, metaclass=MetaQObjectABC):
       # ...
       _model_catalog_changed = pyqtSignal(list)  # list[ModelSpec]
   ```

2. **Add the abstract methods** to the `EventBus` ABC in `core/interfaces.py`:

   ```python
   @abstractmethod
   def subscribe_to_model_catalog_changed(
       self, callback: Callable[[list[ModelSpec]], None],
   ) -> None: ...

   @abstractmethod
   def emit_model_catalog_changed(self, value: list[ModelSpec]) -> None: ...
   ```

3. **Implement them** in `QtEventBus`:

   ```python
   @override
   def subscribe_to_model_catalog_changed(self, callback):
       logger.debug(f"subscribe_to_model_catalog_changed: {callback}")
       self._model_catalog_changed.connect(callback)

   @override
   def emit_model_catalog_changed(self, value):
       logger.debug(f"emit_model_catalog_changed: {value}")
       self._model_catalog_changed.emit(value)
   ```

4. **Use it** from emitters (controllers, `StatusListener`, background task bridges in `_create_app_context`).
5. **Update** [architecture.md](architecture.md)'s signal catalogue and [technical-debt.md](technical-debt.md) if the new signal replaces anything.

### Gotcha: `None` and `pyqtSignal(int)`

`pyqtSignal(int)` cannot transport `None`.
See how `QtEventBus.emit_run_id_changed` encodes `None` as `-1`:

```python
self._run_id_changed.emit(value or -1)
```

If you need "no value" for a new `int` signal, use the same convention and document the sentinel.

## Recipe 6 — Create a New Widget + Controller Pair

### The Controller (under `ui/controllers/`)

```python
# src/ollama_llm_bench/ui/controllers/model_catalog_widget_controller.py
import logging
from typing import Callable, List, override

from ollama_llm_bench.core.interfaces import EventBus, ModelCatalogApi
from ollama_llm_bench.core.models import ModelSpec
# Define a new ABC alongside the existing controller ABCs
from ollama_llm_bench.core.ui_controllers import ModelCatalogWidgetControllerApi

logger = logging.getLogger(__name__)


class ModelCatalogWidgetController(ModelCatalogWidgetControllerApi):
    """Controller for the Model Catalog widget."""

    def __init__(self, *, catalog_api: ModelCatalogApi, event_bus: EventBus) -> None:
        self._catalog_api = catalog_api
        self._event_bus = event_bus

    @override
    def handle_refresh_click(self, _) -> None:
        specs = self._catalog_api.list_specs()
        self._event_bus.emit_model_catalog_changed(specs)

    @override
    def subscribe_to_catalog_changed(
        self, callback: Callable[[List[ModelSpec]], None],
    ) -> None:
        self._event_bus.subscribe_to_model_catalog_changed(callback)
```

### The Widget (under `ui/widgets/...`)

```python
# src/ollama_llm_bench/ui/widgets/panels/control/model_catalog_widget.py
from PyQt6.QtWidgets import QPushButton, QTableWidget, QVBoxLayout, QWidget

from ollama_llm_bench.core.interfaces import AppContext


class ModelCatalogWidget(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._controller = ctx.get_model_catalog_widget_controller_api()
        self._table = QTableWidget(0, 3)
        self._refresh_button = QPushButton("Refresh Catalog")

        self._build_layout()
        self._wire_signals()

    def _build_layout(self) -> None:
        layout = QVBoxLayout()
        layout.addWidget(self._refresh_button)
        layout.addWidget(self._table)
        self.setLayout(layout)

    def _wire_signals(self) -> None:
        self._refresh_button.clicked.connect(self._controller.handle_refresh_click)
        self._controller.subscribe_to_catalog_changed(self._populate_table)

    def _populate_table(self, specs) -> None:
        self._table.setRowCount(len(specs))
        for row, spec in enumerate(specs):
            # populate columns ...
            pass
```

Patterns to follow:

- Widget **only** imports from `core/` and its own controller ABC — never from `services/` directly.
- Widget holds a reference to the controller, not to the event bus.
- Widget builds layout first, then wires signals, then subscribes to events (see `ResultWidget` for a large-scale example).

### Register in `ApplicationContext`

Same process as Recipe 4: add a slot, a getter, and an instantiation in `_create_app_context`.

## Recipe 7 — Add Background Work via `QRunnable`

Use this pattern whenever the new work takes more than ~50 ms and would otherwise freeze the UI.

```python
# src/ollama_llm_bench/qt_classes/qt_long_task.py
import logging
import time

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

logger = logging.getLogger(__name__)


class LongTask(QRunnable):
    """Runs a long-running job off the UI thread."""

    class Signals(QObject):
        started = pyqtSignal()
        progress = pyqtSignal(int)   # 0..100
        finished = pyqtSignal(str)   # result payload
        failed = pyqtSignal(str)     # error message

    def __init__(self, *, payload: str) -> None:
        super().__init__()
        self._payload = payload
        self.signals = self.Signals()
        self._stop_requested = False
        self.setAutoDelete(True)

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:  # executes on worker thread
        try:
            self.signals.started.emit()
            for pct in range(0, 101, 10):
                if self._stop_requested:
                    return
                time.sleep(0.1)
                self.signals.progress.emit(pct)
            self.signals.finished.emit(f"done: {self._payload}")
        except Exception as exc:
            logger.exception("LongTask failed")
            self.signals.failed.emit(str(exc))
```

**Critical points** (from `BenchmarkExecutionTask`):

- `QRunnable` does **not** inherit from `QObject`, so the nested `Signals(QObject)` class owns the signals.
- `self.setAutoDelete(True)` — Qt will delete the runnable after `run()` returns.
- `run()` catches *every* exception and emits it as a signal. Never raise.
- Cancellation is cooperative: set a flag, check it at loop boundaries.
- Store a logger on `self` that includes context: `self.logger = logging.getLogger(f"{__name__}.LongTask[{id}]")`.

Submit the task through a `QThreadPool` (the project has exactly one, configured with `maxThreadCount=1`).
Controller code should not touch the thread pool directly — wrap the task in a `BenchmarkFlowApi`-style lifecycle object (see `QtBenchmarkFlowApi` for the template).

## Recipe 8 — Add an Integration Point with `ContextProvider`

`ContextProvider` is a singleton.
Anywhere in the codebase you can retrieve it:

```python
from ollama_llm_bench.app_context import ContextProvider

ctx = ContextProvider.get_context()
event_bus = ctx.get_event_bus()
```

Call `get_context()` only from the main thread during normal operation — it's fine to call from worker code as long as you understand that any returned reference (e.g. `DataApi`) is thread-safe by virtue of opening a fresh SQLite connection per call.

**Prefer constructor injection** over `ContextProvider.get_context()`.
The only reason `ContextProvider` exists is so that `MainWindow(ctx)` can be constructed in `main.py` — see `src/ollama_llm_bench/main.py:146`.

## Recipe 9 — Testing New Code

The project has no tests yet.
When adding them, follow the skeleton in [testing-guide.md](testing-guide.md):

- Place files under `tests/unit/...` mirroring `src/ollama_llm_bench/...`.
- Use `pytest` + `pytest-mock`.
- Always pass `spec=` when building mocks: `mocker.Mock(spec=DataApi)`.
- Use `tmp_path` for any filesystem work (SQLite, YAML loading, exports).
- Never require a `QApplication` in a unit test — test controllers and services directly, skip the widgets.

## Common Patterns from Existing Code

### Constructor Injection

```python
class NewRunWidgetController(NewRunWidgetControllerApi):
    def __init__(
        self,
        *,
        data_api: DataApi,
        llm_api: LLMApi,
        task_api: BenchmarkTaskApi,
        benchmark_flow_api: BenchmarkFlowApi,
        event_bus: EventBus,
    ):
        self.data_api = data_api
        self.llm_api = llm_api
        ...
```

Source: `src/ollama_llm_bench/ui/controllers/new_run_widget_controller.py`.

### EventBus Subscribe + Emit

```python
# subscribe
self.event_bus.subscribe_to_background_thread_is_running(self._on_running_changed)

# emit
self.event_bus.emit_global_event_msg("Run deleted")
```

### Frozen Dataclass Update Pattern

Because dataclasses are frozen, "update" means "construct a new one":

```python
updated = BenchmarkResult(
    result_id=task.result_id,
    run_id=task.run_id,
    task_id=task.task_id,
    model_name=task.model_name,
    status=BenchmarkResultStatus.WAITING_FOR_JUDGE,
    llm_response=response.llm_response,
    ...
)
self.data_api.update_benchmark_result(updated)
```

Source: `qt_benchmark_execution_task.py:_execute_benchmark_task`.

## Pitfalls

| Pitfall | Fix |
|---|---|
| Importing `PyQt6` from `core/` or `services/` | Move the code into `qt_classes/` or inject a callback |
| Mutating a widget from `BenchmarkExecutionTask` | Emit a signal; let the main thread do the update |
| Calling `print()` | Use `logger = logging.getLogger(__name__)` at module top |
| Constructing a dependency inside a class | Inject it via `__init__` keyword argument |
| Catching `Exception` with a one-line `except: pass` | Catch the specific type; `logger.exception(...)`; chain with `raise ... from e` if re-raising |
| Using `threading.Thread` for background work | Use `QRunnable` + the existing `QThreadPool` |
| Using `pyqtSignal(int)` with a `None` value | Encode `None` as a sentinel (the project uses `-1`) |
| Forgetting `@override` on an overridden method | Add it — Python 3.12+ and the coding rule require it |
| Using a mutable default arg | Replace with `None` and build inside the body |

## PyQt6 → PySide6 Migration Checklist (Per File)

When you touch a file during normal work, you *may* migrate it in the same commit.
The migration has not started — see [technical-debt.md](technical-debt.md).

1. Replace `from PyQt6.QtCore import ...` → `from PySide6.QtCore import ...` (and same for `QtWidgets`, `QtGui`).
2. Replace `pyqtSignal` → `Signal`.
3. Replace `pyqtSlot` → `Slot`.
4. Verify `MetaQObjectABC` still works (PySide6 uses `shiboken` metaclass which may behave differently).
5. Check any `exec_` calls are spelled `exec` under PySide6.
6. Run the full quality pipeline (`scripts/ai-check.sh`).
7. Do **not** mix PyQt6 and PySide6 in the same file.

## Related Documents

- [architecture.md](architecture.md)
- [services-reference.md](services-reference.md)
- [data-model.md](data-model.md)
- [ui-architecture.md](ui-architecture.md)
- [testing-guide.md](testing-guide.md)
- [technical-debt.md](technical-debt.md)
