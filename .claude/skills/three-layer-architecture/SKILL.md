---
name: three-layer-architecture
description: Use when creating a new module/package, deciding whether code belongs in backend/, adapters/, or ui/, wiring a new dependency in compose.py, or when unsure which of the five public-surface files a piece of code belongs in.
---

# Three-Layer Architecture and the Module Public Surface

Source of truth: `docs/v3_specification/16_Engineering_Standards/01_PROJECT_STRUCTURE.md` (physical layout, module framework, composition root) and `docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md` §3 (the layering map).

## The three layers, in one picture

```
+================ UI LAYER (PySide6) ===============================+
|  Views / Widgets  -- UI primitives only                            |
|        v                                                           |
|  Controllers / ViewModels -- orchestrate views and gateways        |
+================|====================================================+
                 v
+================ ADAPTER LAYER (Qt-binding glue) ====================+
|  Adapters -- view-model conversion; command translation;           |
|              cross-thread marshalling; Gateway implementations     |
+================|====================================================+
                 v
+================ BACKEND LAYER (Qt-free, headless) ==================+
|  Services -- business logic; no UI imports                         |
|        v                                                           |
|  Domain models + Data -- pure value types + data access            |
+======================================================================+
```

Dependency direction is strictly inward, enforced by `import-linter` contracts in `pyproject.toml`, never just convention:

- `backend/*` is pure Python: imports no PySide6, no `adapters/*`, no `ui/*`. Runs headlessly under `pytest` with no `QApplication` present.
- `adapters/*` is the **only** layer permitted to import both `backend/*` and PySide6. Everything Qt-specific that bridges the two lives here.
- `ui/*` depends on PySide6, `adapters/*`, and a strictly limited slice of `backend/*` (`domain`, `errors`, `events`, `stores`, `settings`, and Protocol re-exports only). It must never import a *concrete* backend implementation directly.

## Decision tree: where does this code go?

```
Does it touch PySide6 at all (QWidget, QThreadPool, Signal, setStyleSheet, ...)?
│
├─ NO  → Is it business logic, a domain model, persistence, or a provider client?
│         │
│         ├─ YES → backend/<feature>/
│         │
│         └─ NO (it's a UI-agnostic helper) → backend/<feature>/ or backend/domain,
│              backend/errors, backend/infra depending on its cross-cutting role
│
└─ YES → Does it ALSO need to call into backend/* (a Store, a Service, an LLMClient)?
          │
          ├─ YES → adapters/<binding>/  (Qt-binding glue: table models, QRunnable
          │         wrappers, the event-bus Qt bridge, a Gateway implementation)
          │
          └─ NO (it's pure rendering/layout, talks only to its own Gateway/controller)
                → ui/<feature>/
```

Concrete examples from the actual repository tree:

| Code | Layer | Why |
|---|---|---|
| `BenchmarkPipeline`, `RunsStore`, `LLMClient` provider adapters, `CancellationToken` | `backend/` | Pure logic/data, zero Qt, runs headless under pytest |
| `QAbstractTableModel` summary-table adapter, `QRunnable` work-unit wrapper, the psygnal→Qt store bridge, `ResumeGateway`'s concrete implementation | `adapters/` | Qt-binding glue that imports *both* `backend/*` and PySide6 |
| `make_new_benchmark_widget(...)` factory, the `QWidget` subclass, the controller that calls `self._gateway.start_run(...)` | `ui/` | PySide6 rendering/control flow that reaches the backend only through its Gateway |

A useful litmus test: **if a test for this code needs a running `QApplication` to pass, it does not belong in `backend/`.** If a backend test needs to import PySide6 at all, that is itself a defect.

## The module is the unit, not the file

The repository is **feature-first**: the top level lists *what the application does* (`backend/benchmark_pipeline`, `backend/evaluation`, `ui/results`), never *technical layers* (`models/`, `services/`, `controllers/` at the top level do not exist). A 50-line utility and a 2000-line widget both get their own module directory with the same five-file public surface — there is no "loose file in a parent package" pattern.

## The five-file public surface — every module's contract

Every module exposes at most these five public files; everything else is hidden under `_internal/`:

```
src/ollama_llm_bench/<feature>/
    __init__.py        # Thin facade: docstring + __all__ + re-exports from .api
    api.py              # Public functions, factories, Protocol re-exports — NO logic
    models.py           # msgspec.Struct DTOs and event types owned by this module
    protocols.py        # OPTIONAL — only when the module offers a swap point
    testing.py          # OPTIONAL — fakes / stubs / fixtures for downstream tests
    _internal/          # PRIVATE — all implementation
        __init__.py     # Docstring: "Private internals; do not import."
        *.py
    tests/               # Colocated unit tests scoped to THIS module only
```

| File | Contains | Must not contain |
|---|---|---|
| `__init__.py` | Docstring, literal `__all__: list[str]`, re-exports from `.api` | Implementation logic; anything beyond docstring/imports/`__all__` |
| `api.py` | Public functions/factories with `icontract` decorators; Protocol re-imports | Implementation bodies of non-trivial logic; un-prefixed private helpers |
| `models.py` | `msgspec.Struct(frozen=True, kw_only=True, gc=False)` DTOs; module-owned event types | Imports from `_internal/`; mutable module-level state |
| `protocols.py` | `typing.Protocol` definitions for swap points | Concrete implementations |
| `testing.py` | Fakes implementing the module's Protocols; canned fixtures | Real I/O, network, or database access |
| `_internal/*.py` | All implementation; may import `..models` and `..protocols` | Imports from `..api` (creates a cycle); module-level mutable globals |

**Consumers import from the package root only:**

```python
# Correct
from ollama_llm_bench.backend.csv_export import write_rows, CsvRow

# Forbidden — bypasses the public facade
from ollama_llm_bench.backend.csv_export.api import write_rows

# Forbidden — reaches into private internals
from ollama_llm_bench.backend.csv_export._internal.writer import _write_rows_impl
```

`__all__` must be a **literal** `list[str]` written directly in `__init__.py` — a computed `__all__` assembled from submodule `__all__` lists breaks under `mypy --strict --no-implicit-reexport`.

### Choosing the public API shape

| Module character | API shape |
|---|---|
| Pure transformation, no state, no swap point | Free function in `api.py` |
| Two or more interchangeable implementations | `Protocol` in `protocols.py` + concrete classes in `_internal/` |
| One implementation with constructor configuration | Class factory in `api.py` returning a Protocol type |
| Qt widget | Mountable widget factory in `api.py` returning a `QWidget` |
| Event publisher | Event types as frozen `msgspec.Struct` in `models.py`, owned by the publisher |

### Layering depth scales with complexity, the surface never does

- A **leaf utility** (`backend/csv_export`) has a flat `_internal/` with two or three files.
- A **mid-complexity** module (`backend/adaptive_timeout`, `backend/embedding`) layers `_internal/` into a couple of files plus one `protocols.py` swap point.
- A **complex feature** (`backend/benchmark_pipeline`, `ui/results`) layers `_internal/` into sub-directories and contains nested **sub-feature packages** (e.g. `ui/results/summary_tab/`, `ui/results/charts_tab/`), each itself a full module with the same five-file surface.

A module whose `_internal/` grows beyond roughly 1500 lines, or whose public surface would need more than five files, signals a split into a parent feature with sub-features — a structural split only, never a change to how consumers import it.

UI feature modules specifically follow an MVC-family layout inside `_internal/`:

```
src/ollama_llm_bench/ui/new_benchmark/
    __init__.py
    api.py                       # make_new_benchmark_widget(...) -> QWidget
    models.py                    # frozen ViewModel Struct + UI event types
    _internal/
        view.py                  # QWidget subclass: rendering only
        controller.py             # store subscriptions + signal handlers
        view_model_select.py      # pure functions: store state -> ViewModel
    tests/
```

## `compose.py` — the single composition root

There is exactly **one** composition root: `src/ollama_llm_bench/compose.py`. It is roughly 50–200 lines of plain keyword-argument factory calls — no dependency-injection container, no `@inject` decorators, no `Annotated[..., Depends(...)]`, no service locator, no reflection-based wiring.

```python
# src/ollama_llm_bench/compose.py — illustrative fragment
def build_app(*, app: QApplication, loop: QEventLoop) -> AppHandle:
    configure_logging()                                            # 1. logging first

    db_path = user_data_dir() / "backend.sqlite"                   # 2. persistence
    runs_store      = make_runs_store(path=db_path)
    results_store   = make_results_store(path=db_path)

    settings = make_settings_service(app_settings_store=app_settings_store)  # 3.
    bus = EventBus()

    registry = make_provider_registry(providers_store=providers_store,        # 4. services
                                       settings=settings, bus=bus)
    pipeline = make_benchmark_pipeline(registry=registry, runs_store=runs_store,
                                        results_store=results_store, bus=bus)

    window = make_main_window(run_registry=run_registry, settings=settings, bus=bus)  # 5. UI

    return AppHandle(window=window, pipeline=pipeline, loop=loop)
```

`compose.py` is the **only** file allowed to import concrete provider adapters, the six concrete persistence-store implementations, and concrete evaluators. Every other file imports Protocols. An `import-linter` `forbidden` contract enforces this:

```toml
[[tool.importlinter.contracts]]
name = "Only compose.py wires concrete adapters"
type = "forbidden"
source_modules = ["ollama_llm_bench.ui", "ollama_llm_bench.adapters"]
forbidden_modules = [
    "ollama_llm_bench.backend.provider_openai_compatible",
    "ollama_llm_bench.backend.provider_anthropic",
    "ollama_llm_bench.backend.provider_gemini",
]
```

`src/ollama_llm_bench/__main__.py` is the process entry point: it creates the single `QApplication`, calls `build_app`, shows the main window, and runs the Qt event loop. It contains no business logic.

## Worked example — adding a brand-new feature: a new chart kind

Say you're adding a thirteenth `ChartKind` — a new aggregation the Result widget's charts tab can render. Walk it through the layers:

1. **`backend/domain/`** — add the new member to the `ChartKind` `StrEnum` in `models.py` (see the `msgspec-domain-modeling` skill for the enum rules).
2. **`backend/charts/`** — this is the Qt-free chart-aggregation service. Add the new aggregator (it likely follows the existing `BaseChartAggregator` composition pattern already in `_internal/aggregators/`) and wire it into the dispatch table in `_internal/`. The aggregator is a pure function: it takes persisted `BenchmarkResult` rows in, returns a `ChartData`/`HeatmapData` struct out — no Qt, no painting.
3. **`adapters/`** — usually **no change** here: `ChartService` is already wrapped behind `ResultGateway.chart_data(run_id, chart_kind)` (see the `protocol-first-interfaces` skill), so a new enum member flowing through the same method needs no new adapter code unless the new chart kind needs a genuinely new marshalling shape.
4. **`ui/results/charts_tab/`** — add the rendering branch: a new `QPainter`-based widget or a new series configuration for the existing chart-rendering surface, reading its colors from the theme module (see the `pyside6-spec-ui` skill) and resolving its data via `ResultGateway.chart_data(...)`, never by importing `backend/charts` directly.
5. **`compose.py`** — no change needed if the aggregator was wired into `backend/charts`'s own internal dispatch and the existing `ChartService` factory call in `compose.py` already constructs it with no new top-level dependency.

Notice what never happens: the UI layer never imports `backend.charts` directly, and the new aggregation logic never imports anything from `ui/` or `adapters/`. If a step in your own change requires reaching across that boundary, the design is wrong — go back to the decision tree above.

## Anti-patterns to flag in review

| Anti-pattern | Correct approach |
|---|---|
| A flat (src-less) package directory | `src/` layout, no exceptions |
| A loose single-file module dropped into a parent package | Module directory with the full five-file surface |
| A file named `interfaces.py` collecting unrelated Protocols | One `protocols.py` per module, scoped to that module's own swap point |
| A consumer importing through `.api` or `._internal` | Import from the package root only |
| A computed `__all__` | A literal `list[str]` in `__init__.py` |
| A concrete adapter constructed outside `compose.py` | Construct in `compose.py`, pass the Protocol everywhere else |
| `_internal/` importing `..api` | `_internal/` imports `..models` and `..protocols` only |
| A DI container or service locator | Manual constructor wiring in `compose.py` |
| Top-level technical-layer directories (`services/`, `models/`) | Feature packages under `backend/`, `adapters/`, or `ui/`, each owning its own models and logic |
