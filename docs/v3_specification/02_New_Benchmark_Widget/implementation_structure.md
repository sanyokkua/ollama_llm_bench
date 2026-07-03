# New Benchmark Widget — Implementation Structure

**Status:** Draft
**Owner:** arch, coder
**Audience:** arch, coder
**Last Updated:** 2026-06-06
**Cross-references:**
`02_New_Benchmark_Widget/description.md`,
`02_New_Benchmark_Widget/state_machine.md`,
`08_Cross_Cutting/08-E_interfaces_contracts.md`,
`08_Cross_Cutting/08-J_event_bus_catalog.md`,
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`,
`11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`

This document defines the module layout, public API, view-model, controller, factory
wiring, and test boundary for the New Benchmark widget. It follows the standard nine-point
implementation-structure template. The widget is built as programmatic PySide6 Qt Widgets
with an MVC-family separation: a passive view, a frozen view-model Struct, and a controller
that owns the selection store, runs validation, and publishes the `RunStartEvent`.

---

## Table of Contents

1. Module path
2. Public API
3. Sub-modules
4. View-model Struct
5. Controller
6. Factory wiring
7. Dependency Protocols
8. Stores fanout
9. Test boundary

---

## 1. Module path

```
src/ollama_llm_bench/ui/new_benchmark/
├── __init__.py            # re-exports make_new_benchmark_widget
├── factory.py             # make_new_benchmark_widget(...)
├── view.py                # passive QWidget tree; no domain logic
├── view_model.py          # NewBenchmarkViewModel msgspec.Struct
├── controller.py          # NewBenchmarkController
├── _internal/
│   ├── mode_selector.py       # Radio List section
│   ├── performance_matrix.py  # Input/Output Sizes + Repeats section
│   ├── task_files.py          # Task Files section + drag-drop handler
│   ├── test_models.py         # multi-provider model picker section
│   ├── judge_section.py       # Judge + embedding status section
│   ├── advanced_options.py    # Advanced Options section
│   └── selection_store.py     # in-memory (provider, model) selection store
└── tests/
    ├── test_controller.py
    ├── test_view_model.py
    └── test_selection_store.py
```

## 2. Public API

```python
def make_new_benchmark_widget(
    *,
    bus: EventBus,
    gateway: NewBenchmarkGateway,
    task_file_loader: TaskFileLoader,
    run_validator: RunValidator,
    mode_visibility_policy: ModeVisibilityPolicy,
    workspace_controller: WorkspaceController,
) -> QWidget: ...
```

The factory constructs the controller, the section sub-widgets, and the view, wires the
event-bus subscriptions, and returns the assembled root `QWidget`. No other module
imports the internal classes.

## 3. Sub-modules

The widget's public surface exceeds five files and its section logic is non-trivial, so it
is split into `_internal/` section modules. Each section module exposes a single
`make_<section>(...)` factory returning a `QWidget` and a small per-section signal set.
The split keeps each section independently readable and unit-testable:

| Section module | Responsibility |
|---|---|
| `mode_selector.py` | Render the Radio List; emit `mode_changed`; persist `benchmark.last_mode` |
| `performance_matrix.py` | Input/Output size Toggles, Repeats Stepper, live task estimate |
| `task_files.py` | List View, drag-drop handler, Add/Remove buttons, dirty-marker rendering |
| `test_models.py` | Provider dropdown, available-models list, Select/Clear All, selected-models summary |
| `judge_section.py` | Judge toggle, provider/model dropdowns, embedding status row |
| `advanced_options.py` | Collapsible group of per-run override controls |
| `selection_store.py` | In-memory ordered set of `(provider_id, model_name)` pairs |

## 4. View-model Struct

```python
class NewBenchmarkViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_mode: RunMode
    visible_sections: frozenset[str]
    selected_models: tuple[tuple[str, str], ...]   # (provider_id, model_name)
    task_paths: tuple[str, ...]
    performance_config: PerformanceConfig | None
    judge_provider: str
    judge_model: str
    judge_analysis_enabled: bool
    judge_analysis_toggle_locked: bool             # true in GRADED
    embedding_ready: bool
    warmup_enabled: bool
    reasoning_effort: ReasoningEffort
    min_timeout_seconds: int
    max_timeout_seconds: int
    retry_count: int
    consecutive_max_timeouts_to_exclude: int
    estimated_task_count: int
    validation_entries: tuple[ValidationEntry, ...]
    start_enabled: bool
```

The view-model is rebuilt (never mutated) on every configuration change. The view diffs
the new instance against the old to update only the changed primitives.

## 5. Controller

`NewBenchmarkController` owns:

- The `SelectionStore` instance.
- The current configuration state used to build the view-model.
- Derived-state computations: visible section set (via `ModeVisibilityPolicy`), estimated
  task count, validation entries (via `RunValidator`), and the `start_enabled` flag. Provider
  and model selection lists, the Advanced-Options defaults, and the pre-run readiness snapshot
  are read through the `NewBenchmarkGateway`.

Subscriptions (all ownership-bound to the widget):

| Event | Controller action |
|---|---|
| `_provider_registry_reloaded` | Rebuild provider/model lists; re-validate; rebuild view-model |
| `_task_file_changed` | Refresh dirty markers; re-count affected task files; rebuild view-model |
| `_workspace_changed` | On return to `benchmark`, refresh Task Files dirty markers |
| `_run_started` | Transition to Locked; render read-only |
| `_run_finished` / `_run_failed` / `_run_stopped` | Return to Idle; re-enable |

On Start confirmation the controller assembles the run-start request and issues it through
`NewBenchmarkGateway.start_run(...)` (see `08_Cross_Cutting/08-E_interfaces_contracts.md` §7b.2);
the adapter constructs the backend command record and drives the run-start over the wrapped
backend Protocols. The controller never holds the pipeline or registry Protocol directly.

## 6. Factory wiring

`compose.py` invokes the factory once, passing the shared services constructed at the
composition root:

```python
new_benchmark = make_new_benchmark_widget(
    bus=event_bus,
    gateway=new_benchmark_gateway,
    task_file_loader=task_file_loader,
    run_validator=run_validator,
    mode_visibility_policy=mode_visibility_policy,
    workspace_controller=workspace_controller,
)
benchmark_workspace.add_left_panel_tab("New Benchmark", new_benchmark)
```

## 7. Dependency Protocols

The widget consumes interfaces only; it never imports concrete service classes:

| Protocol | Source |
|---|---|
| `EventBus` | `ollama_llm_bench.backend.events.protocols` |
| `NewBenchmarkGateway` | `ollama_llm_bench.adapters.gateways` — the adapter gateway (08-E §7b.2) exposing the widget's query/command surface: `get_setting`/`set_setting` for the Advanced-Options defaults, `benchmark.last_mode`, and `embedding.hide_from_test_models`; `provider_list()` for the model picker; `readiness_snapshot()` for the pre-run readiness gate; and `start_run(request)` to start the run. It wraps `SettingsStore`, `ProviderRegistry`, `ReadinessService`, and the run-start command (D-R-06). |
| `TaskFileLoader` | `ollama_llm_bench.backend.task_files.protocols` |
| `RunValidator` | `ollama_llm_bench.backend.benchmark_pipeline.protocols` |
| `ModeVisibilityPolicy` | `ollama_llm_bench.backend.mode_visibility.protocols` |
| `WorkspaceController` | `ollama_llm_bench.adapters.workspace_controller.protocols` |

**Adapter boundary (D-R-06).** The controller depends only on `NewBenchmarkGateway` for every backend store/service interaction (settings, provider/model lists, readiness, run start), never on a backend Protocol — no `SettingsStore`, `ProviderRegistry`, or `ReadinessService` reaches the controller (08-A §5/§6). The remaining direct params (`TaskFileLoader`, `RunValidator`, `ModeVisibilityPolicy`, `WorkspaceController`, the Event Bus) are not persistence stores or backend domain/compute services in the D-R-06 wrap set; the `SelectionStore` is widget-local.

## 8. Stores fanout

The widget reads from its single `NewBenchmarkGateway` (settings, provider/model lists, readiness) and subscribes to a
small fixed set of event-bus signals (§5). The fan-out is well within the soft limit, so no
controller split is proposed. The `SelectionStore` is widget-local and not a shared store.

## 9. Test boundary

| Target | Test type | Location |
|---|---|---|
| `NewBenchmarkController` derived-state and validation wiring | Unit, with a fake `NewBenchmarkGateway` (plus fake `EventBus` and retained helpers) | `_internal/.../tests/test_controller.py` |
| `NewBenchmarkViewModel` construction and field invariants | Unit | `tests/test_view_model.py` |
| `SelectionStore` add/remove/multi-provider behaviour | Unit | `tests/test_selection_store.py` |
| Mode-change visibility, drag-drop, Start-to-`RunStartEvent` | Integration, with `qtbot` | top-level `tests/integration/test_new_benchmark.py` |
