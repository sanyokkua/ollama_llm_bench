# Resume Benchmark Widget — Implementation Structure

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder
**Last Updated:** 2026-06-06
**Cross-references:** `03_Resume_Benchmark_Widget/description.md`, `03_Resume_Benchmark_Widget/state_machine.md`, `03_Resume_Benchmark_Widget/flow_diagram.md`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `16_Engineering_Standards/01_PROJECT_STRUCTURE.md`, `16_Engineering_Standards/03_CODING_STANDARDS.md`

This document specifies the implementation structure of the Resume Benchmark widget as a module: its package path, its public API, its internal MVC-family layout, the view-model `msgspec.Struct` it renders, the controller and its subscriptions, the factory wiring example, the dependency Protocols it consumes, the store-fanout assessment, and the test boundary. It defines structure, not implementation code; it follows the module framework fixed in `16_Engineering_Standards/01_PROJECT_STRUCTURE.md`.

---

## Table of Contents

1. Module path
2. Public API
3. Sub-modules
4. View-model Struct
5. Controller
6. Factory wiring example
7. Dependency Protocols
8. Stores fanout assessment
9. Test boundary

---

## 1. Module path

```
src/ollama_llm_bench/ui/resume_benchmark/
```

The Resume Benchmark widget is a single feature module under the PySide6 UI layer. It is not large enough to need sub-feature packages: its public surface is one widget factory and the rendered state lives in one view-model. It exposes the fixed module public surface — `api.py`, `models.py`, `__init__.py`, an `_internal/` package, and a colocated `tests/` directory — and hides every implementation file under `_internal/`.

```
src/ollama_llm_bench/ui/resume_benchmark/
    __init__.py            # re-exports the public surface; literal __all__
    api.py                 # make_resume_benchmark_widget(...) -> QWidget
    models.py              # ResumeBenchmarkViewModel, RunRow, and module-owned view DTOs
    _internal/             # PRIVATE — all implementation
        controller.py      # ResumeBenchmarkController — subscriptions, derived state
        view.py            # the QWidget tree: search row, run table, footer
        run_table_model.py # QAbstractTableModel adapter over RunRow tuples
        context_menu.py    # builds the right-click menu, gates each action
        actions.py         # invokes the Resume / Retry / Clone / Rename / Delete / Export use cases
    tests/                 # colocated unit tests scoped to this module
        test_controller.py
        test_run_table_model.py
        test_context_menu_gating.py
        test_actions.py
```

The widget is a UI-layer module: it imports the backend Protocols from `08_Cross_Cutting/08-E_interfaces_contracts.md` and the DTOs from `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, and it never imports a concrete backend implementation class.

## 2. Public API

The module's only public entry point is a mountable widget factory in `api.py`:

```python
def make_resume_benchmark_widget(
    *,
    bus: EventBus,
    gateway: ResumeGateway,
    native_pickers: NativePickers,
    file_system_actions: FileSystemActions,
) -> QWidget:
    """Build the Resume Benchmark widget — the Resume tab of the Benchmark
    workspace left panel — fully wired to its controller, and return the
    mounted QWidget. All dependencies are passed by keyword.
    """
```

The factory constructs the controller, the view, and the run-table model, wires the controller's event-bus subscriptions with owner-binding to the returned widget, and returns the widget. The dialog factories (Resume Summary, Retry Selection, Rename Run, Delete confirmation) live in the `07_Common_Dialogs` modules and are invoked by `_internal/actions.py`; they are not part of this module's public API.

## 3. Sub-modules

The module does not split into sub-feature packages. Per the module framework, a split is warranted only when the public surface would exceed five files or `_internal/` would exceed roughly 1500 lines. The Resume Benchmark widget's `_internal/` is a flat set of five files well under that threshold, and its public surface is one factory. The internal files are organised by responsibility:

| File | Responsibility |
|---|---|
| `controller.py` | Owns the view-model, subscribes to the event bus, recomputes derived state (resumability, action gating) and pushes a new view-model into the view. |
| `view.py` | Builds and owns the `QWidget` tree — the search input, the run table view, the footer buttons — and renders a view-model into it. Holds no domain logic. |
| `run_table_model.py` | A `QAbstractTableModel` that adapts the immutable `tuple[RunRow, ...]` for the table view, including sort and the search-filter predicate. |
| `context_menu.py` | Constructs the right-click `QMenu`, enables or disables each item from the selected `RunRow`'s gating flags, and routes a chosen item to `actions.py`. |
| `actions.py` | The thin layer that invokes the Resume, Retry, Clone, Rename, Delete, Export, and Show-log use cases and translates their outcomes into `_global_message` events. |

## 4. View-model Struct

The displayed state of the widget is a single immutable `msgspec.Struct`, declared in `models.py` with `frozen=True, kw_only=True, gc=False`. The controller produces a fresh instance on every state change and hands it to the view; the view never mutates it.

```python
class RunRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    effective_name: str               # user name if set, else generated name
    mode_label: str                   # display label for RunMode
    started_at_display: str           # 'YYYY-MM-DD HH:MM', local time
    status: RunStatus
    status_label: str                 # 'Done' | 'Stopped' | 'Failed' | 'Pending'
    completed_count: int
    total_count: int
    is_resumable: bool                # RunStatus resumable AND >=1 resumable result
    has_resumable_results: bool       # >=1 PENDING / non-terminal / retryable result
    has_analysis: bool                # BenchmarkRun.run_analysis is non-empty
    log_file_exists: bool             # the run-log file is present on disk
    is_executing: bool                # this run is the one currently executing (gateway run-activity)

class ResumeBenchmarkViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    rows: tuple[RunRow, ...]          # every persisted run, newest first
    selected_run_id: RunId | None
    search_text: str
    sort_column: str                 # one of: name | mode | started | status | tasks
    sort_descending: bool
    is_empty: bool                    # the gateway's list_runs() returned an empty tuple
```

`RunRow` carries pre-derived booleans (`is_resumable`, `is_executing`, `has_analysis`, `log_file_exists`) so the view and the context menu never re-derive gating logic — the controller computes them once. The `started_at_display` is pre-formatted by the controller; the view does no date arithmetic.

## 5. Controller

`ResumeBenchmarkController` (in `_internal/controller.py`) owns the view-model and mediates between the backend and the view.

### Subscriptions

The controller subscribes to the event bus with owner-binding to the widget; each subscription is torn down when the widget is destroyed (`08_Cross_Cutting/08-J_event_bus_catalog.md`).

| Event | Handler effect |
|---|---|
| `_run_list_changed` | Reload `gateway.list_runs()`, rebuild `rows`, re-apply filter and sort, preserve `selected_run_id` when it still exists. |
| `_run_renamed` | Patch the matching `RunRow.effective_name` without a full reload. |
| `_run_id_changed` | Sync `selected_run_id` when the selected run was changed by another widget. |
| `_run_started` | Recompute `is_executing` for the affected row and re-derive its gating flags. |
| `_run_finished` / `_run_stopped` / `_run_failed` | Refresh that run's `status`, counts, and gating flags. |
| `_run_analysis_received` | Set `has_analysis = True` for the affected run. |
| `_task_file_changed` | Refresh the `completed_count` / `total_count` of runs whose snapshot referenced the saved file. |

### Derived-state computations

The controller computes, per run, `is_resumable`, `has_resumable_results`, and `is_executing`:

- `is_resumable` — `RunStatus` in `{INCOMPLETE, STOPPED, FAILED}` **and** `gateway.resumable_results(run_id)` is non-empty. To avoid a per-row query on every reload, the controller derives resumability from the result counts already loaded with the run header where available, and falls back to `resumable_results` only when the counts are inconclusive.
- `is_executing` — `gateway.is_run_active()` is true and `gateway.active_run_id()` equals the row's `run_id`.
- `has_analysis` — `BenchmarkRun.run_analysis` is a non-empty string.
- `log_file_exists` — the run-log path resolved from `run_id` and `started_at` exists on disk.

The controller emits `_run_id_changed` when the user selects a row, and `_global_message` for toast-worthy outcomes.

## 6. Factory wiring example

The composition root (`src/ollama_llm_bench/compose.py`) builds the widget with plain keyword arguments — no dependency-injection container, no service locator.

```python
# in compose.py
resume_benchmark_widget = make_resume_benchmark_widget(
    bus=event_bus,
    gateway=resume_gateway,
    native_pickers=native_pickers,
    file_system_actions=file_system_actions,
)
# the Benchmark workspace mounts resume_benchmark_widget as the "Resume" tab
# of its left panel.
```

## 7. Dependency Protocols

The widget consumes the following interfaces, all defined in `08_Cross_Cutting/08-E_interfaces_contracts.md`. It depends on interfaces only — never on a concrete implementation.

| Protocol | Methods this widget uses |
|---|---|
| `ResumeGateway` | The adapter gateway (08-E §7b.3) exposing the run-list / results / tasks query+command surface this widget needs: `list_runs`, `get_run`, `create_run`, `update_run_status`, `rename_run`, `delete_run`, `list_results`, `resumable_results`, `reset_results`, `create_results`, `update_result`, `list_tasks`, `create_tasks`, `refresh_readiness`, `get_sort_setting`/`set_sort_setting`, `resume_run`, `is_run_active`/`active_run_id`; wraps `RunsStore`, `ResultsStore`, `TasksStore`, `ReadinessService`, `SettingsService`, and the `BenchmarkFlowApi` resume command (D-R-06). |
| `FileSystemActions` | `open_in_file_manager` (Show run-log file). |
| `NativePickers` | `save_file` for the export-to-file path. |
| `EventBus` | `subscribe` (owner-bound) and `emit` for the events in Section 5 and `description.md` §7. |

**Adapter boundary (D-R-06).** The controller depends only on `ResumeGateway` (plus the Event Bus and the retained OS-adapter helpers), never on a backend Protocol — no `RunsStore`, `ResultsStore`, `TasksStore`, `BenchmarkFlowApi`, `ReadinessService`, or `SettingsService` reaches the controller (08-A §5/§6); the adapter holds those behind the gateway.

Exports do not apply a redaction step — the user's own task prompts and the model responses produced on the user's own machine are written verbatim, per `10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1 and `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md` §6.5. The export path in `_internal/actions.py` therefore imports no redaction function.

## 8. Stores fanout assessment

The widget depends on a single `ResumeGateway` (its run-list / results / tasks query+command surface) plus the event bus; the run-selection store remains widget-local for the selected run id. This is well under the soft fanout limit of four sources per controller, so the controller does **not** need to be split. The widget's complexity is in its action set (resume, retry, clone, rename, delete, export), and that complexity is partitioned by file responsibility inside `_internal/` (Section 3), not by additional store subscriptions. No controller split is proposed.

## 9. Test boundary

| Scope | Tested where | What is verified |
|---|---|---|
| Unit — controller | `tests/test_controller.py` (colocated) | View-model assembly from a fake `ResumeGateway`; resumability and gating derivation; subscription handlers for every event in Section 5 with a fake `EventBus`; selection-preservation across `_run_list_changed`. |
| Unit — run-table model | `tests/test_run_table_model.py` (colocated) | Column rendering; default descending sort by `started_at`; the case-insensitive name-or-mode search predicate; virtualised access. |
| Unit — context menu gating | `tests/test_context_menu_gating.py` (colocated) | Each menu item's enabled/disabled state across `Resumable`, `Terminal`, and `executing` `RunRow` states; the empty-state case. |
| Unit — actions | `tests/test_actions.py` (colocated) | Each use-case invocation with fakes; the `_global_message` emitted on success and on failure; the no-op path when Export Run Analysis is chosen on a run with no analysis. |
| Integration — widget with `qtbot` | top-level `tests/integration/` | Mount via `make_resume_benchmark_widget` with a fake `ResumeGateway`; row selection emits `_run_id_changed`; Resume Run opens the Resume Summary dialog; Delete opens the confirmation dialog; live `_run_list_changed` rebuilds the table preserving selection. |
| Integration — resume against the pipeline | top-level `tests/integration/` | A resumed run hands off through the adapter's `ResumeGateway.resume_run` over a real (or fake) `BenchmarkFlowApi`; the drift-detector path is exercised end-to-end with the Resume use case. |

The widget UNIT tests fake the `ResumeGateway` (plus the `EventBus`, `NativePickers`, and `FileSystemActions` fakes from each module's `testing.py`); the widget's own `tests/` directory holds only unit tests scoped to this module, and cross-module behaviour — including the adapter+backend integration that exercises the real stores and pipeline behind the gateway — is verified in the top-level `tests/integration/` directory.
