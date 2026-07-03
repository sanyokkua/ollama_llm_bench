# Main Window — Implementation Structure

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder
**Last Updated:** 2026-05-22
**Cross-references:** `01_Main_Window/description.md`, `01_Main_Window/state_machine.md`, `08_Cross_Cutting/08-A_architecture_principles.md`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`

This document specifies how the Main Window is structured as a feature module: its module path, its public factory function, its view-model Struct, its controller, the dependency Protocols it consumes, how the composition root wires it, and the boundary at which it is tested. It defines structure and contracts only — no implementation bodies. The Main Window is a UI-layer feature; it depends on adapter-facing controllers and the backend service Protocols, and it never imports a concrete service class (`08-E_interfaces_contracts.md` §2, §23).

---

## Table of Contents

1. Module path and layout
2. Public API — the factory function
3. Sub-modules
4. View-model Struct
5. Controller
6. Dependency Protocols
7. Composition wiring
8. Stores fanout
9. Test boundary

---

## 1. Module path and layout

```
src/ollama_llm_bench/ui/main_window/
    __init__.py            # re-exports make_main_window only
    factory.py             # make_main_window(...) — assembles the shell
    view_model.py          # MainWindowViewModel Struct
    controller.py          # MainWindowController — subscriptions, derived state
    _internal/
        shell.py           # the QMainWindow subclass: menu bar, regions, status bar
        menu_bar.py        # the minimal menu bar widget
        status_bar.py      # the status bar widget (health dot, toast region, version)
        close_handler.py   # the quit-confirmation sequence
        geometry.py        # geometry / splitter / workspace persistence
        tests/             # colocated unit tests for the internal pieces
```

The module follows the standard five-file feature template of `08-A_architecture_principles.md`: a public `__init__.py`, a `factory.py`, a `view_model.py`, a `controller.py`, and a private `_internal/` package. The public surface is exactly one symbol — `make_main_window` — so the module stays within the public-surface limit and the `_internal/` package is free to be split as shown without widening the contract.

## 2. Public API — the factory function

```python
from PySide6.QtWidgets import QMainWindow

from ollama_llm_bench.backend.domain.contracts import EventBus
from ollama_llm_bench.adapters.gateways import MainWindowGateway
from ollama_llm_bench.adapters.workspace_controller import WorkspaceController
from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions


def make_main_window(
    *,
    event_bus: EventBus,
    gateway: MainWindowGateway,
    workspace: WorkspaceController,
    notifications: NotificationService,
    file_system_actions: FileSystemActions,
    benchmark_workspace_factory: "BenchmarkWorkspaceFactory",
    task_editor_workspace_factory: "TaskEditorWorkspaceFactory",
    app_version: str,
) -> QMainWindow:
    """Construct the application shell.

    Builds the menu bar, the swappable workspace region, and the status bar,
    wires the MainWindowController to the Event Bus, restores the persisted
    window geometry, splitter sizes, and active workspace, and returns the
    top-level QMainWindow ready to be shown.
    """
    ...
```

The two `*_workspace_factory` parameters are callables that build the Benchmark and Task Editor workspace widgets on demand; the Main Window invokes the task-editor factory lazily, on the first activation of that workspace (`08-M_app_lifecycle.md` §2 step 10). The factory returns a plain `QMainWindow`; the caller — the composition root entry point — shows it and runs the Qt event loop.

## 3. Sub-modules

The Main Window's `_internal/` package is split into five focused pieces because the shell aggregates several distinct concerns; none of them is a public surface. The split keeps each file small and independently testable:

| Sub-module | Responsibility |
|---|---|
| `_internal/shell.py` | The `QMainWindow` subclass: composes the menu bar, the workspace region container, and the status bar; owns the show handler that schedules the deferred readiness-probe tick. |
| `_internal/menu_bar.py` | The minimal menu bar: the Settings action, the About action, the workspace-switcher segmented control, and the running pill. No File/Edit/View/Help menus. |
| `_internal/status_bar.py` | The status bar: the health dot and label, the toast region, and the version string. |
| `_internal/close_handler.py` | The quit-confirmation sequence — the running-benchmark prompt then the unsaved-buffer prompt — and the final persist-and-exit steps. |
| `_internal/geometry.py` | The debounced read and write of `ui.window_geometry` and `ui.splitter_sizes`, and the off-screen clamp. |

## 4. View-model Struct

The Main Window's displayed shell state is a single frozen Struct, recomputed by the controller and applied to the shell widget. It is not persisted and never crosses a service boundary.

```python
import msgspec

from ollama_llm_bench.backend.domain.enums import ReadinessState


class MainWindowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    window_title: str                 # the resolved title for the current run state
    active_workspace: str              # "benchmark" or "task_editor"
    settings_action_enabled: bool      # False while a run is non-terminal
    running_pill_visible: bool         # True only while a run is non-terminal
    running_pill_label: str            # effective run name; "" when the pill is hidden
    health_state: ReadinessState       # drives the status-bar dot colour and label
    health_tooltip: str                # per-provider readiness detail
    health_dot_clickable: bool         # False while a run is non-terminal
    toast_text: str                    # current status-bar toast; "" when none
```

`ReadinessState` is the enum defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.2. The view-model carries no domain records — the run name is pre-resolved to a string, and the readiness detail is pre-formatted — so the shell widget renders it without further computation.

## 5. Controller

```python
class MainWindowController:
    """Owns the Main Window's shell state. Subscribes to the Event Bus,
    derives the MainWindowViewModel, and applies it to the shell widget.
    """
```

**Subscriptions.** The controller subscribes to the events below, each with itself as the owner so every subscription auto-cancels when the controller is destroyed (`08-J_event_bus_catalog.md` §2):

| Event | Derived effect on the view-model |
|---|---|
| `_run_started` | `running_pill_visible = True`; `settings_action_enabled = False`; `health_dot_clickable = False`; running title |
| `_run_paused` | paused title; pill and disabled-Settings state unchanged |
| `_run_resumed` | running title restored |
| `_run_stopped`, `_run_finished`, `_run_failed` | `running_pill_visible = False`; `settings_action_enabled = True`; `health_dot_clickable = True`; default title |
| `_run_renamed` | `running_pill_label` and `window_title` refreshed when the renamed run is the running run |
| `_app_readiness_changed` | `health_state` and `health_tooltip` refreshed |
| `_global_message` | `toast_text` set; a timer clears it after 5 s |
| `_workspace_changed` | `active_workspace` updated; the shell swaps the workspace region and the status-bar left region |

**Derived state.** The controller computes the view-model from three inputs: the latest run-lifecycle event, the current `AppReadinessSnapshot` read from the readiness state store, and the active workspace read from the workspace store. It holds no business logic — it never starts, pauses, or stops a run; it only reflects state. The close-confirmation decision is delegated to `_internal/close_handler.py`, which queries `MainWindowGateway.is_run_active()` and the Task Editor's dirty-buffer count at the moment a quit is requested.

## 6. Dependency Protocols

The Main Window consumes the following interfaces, all defined in `08-E_interfaces_contracts.md`:

| Protocol | Section | Used for |
|---|---|---|
| `EventBus` | §6 | Subscribing to the run-lifecycle, readiness, message, and workspace events |
| `MainWindowGateway` | §7b.1 | The adapter gateway exposing the shell's query/command surface — read/write `ui.window_geometry`, `ui.splitter_sizes`, `ui.active_workspace`, `ui.theme`; read the readiness snapshot and trigger a re-probe; `is_run_active()` for the quit decision and `shutdown(timeout_ms)` on quit; wraps `SettingsService`, `ReadinessService`, and `BenchmarkFlowApi` (D-R-06). |
| `WorkspaceController` | §18 | Reading the active workspace; switching workspaces; carrying the focus hint |
| `NotificationService` | §19 | Surfacing toasts and modal error dialogs |
| `FileSystemActions` | §20 | The "open in file manager" affordances exposed from the Main Window menu (the OS colour-scheme preference is read via a thin platform query that lives outside the three OS-adapter Protocols) |

**Adapter boundary (D-R-06).** The controller depends only on `MainWindowGateway` (plus the Event Bus and the retained adapter/platform helpers), never on a backend Protocol — no `SettingsService`, `ReadinessService`, or `BenchmarkFlowApi` reaches the controller. The gateway is constructed once by the composition root and injected; the adapter holds the backend Protocols behind it (08-A §5/§6). No view inside the Main Window imports a service directly — a view talks to its controller, and the controller talks to the gateway above (`08-E_interfaces_contracts.md` §2, §7b).

## 7. Composition wiring

The composition root constructs every service, then the two workspace factories, then the Main Window, in that order:

```python
def compose_main_window(ctx: "ApplicationContext") -> QMainWindow:
    benchmark_workspace_factory = make_benchmark_workspace_factory(ctx)
    task_editor_workspace_factory = make_task_editor_workspace_factory(ctx)

    return make_main_window(
        event_bus=ctx.event_bus,
        gateway=ctx.main_window_gateway,
        workspace=ctx.workspace,
        notifications=ctx.notifications,
        file_system_actions=ctx.file_system_actions,
        benchmark_workspace_factory=benchmark_workspace_factory,
        task_editor_workspace_factory=task_editor_workspace_factory,
        app_version=APP_VERSION,
    )
```

`ApplicationContext` is the assembled set of service handles defined in `08-E_interfaces_contracts.md` §23. The application entry point calls `compose_main_window(...)`, shows the returned window, and enters the Qt event loop; the window's show handler schedules the deferred readiness-probe tick.

## 8. Stores fanout

The Main Window's controller depends on a small fixed fan-out: its single `MainWindowGateway` (the in-place readiness / settings / run-activity surface), the workspace store, plus the Event Bus channels listed in §6 (the push signal for readiness and run-lifecycle state). That fan-out is well within the soft limit of `08_Cross_Cutting/08-A_architecture_principles.md`; no controller split is needed. The run-selection store and the run-registry store are deliberately **not** consumed by the Main Window: run selection and the run list belong to the Result and Resume widgets, and the Main Window reacts to run identity only through the `_run_started` / `_run_renamed` events, never by holding the selection itself.

## 9. Test boundary

| Layer | Test target | Tooling |
|---|---|---|
| `_internal/menu_bar.py`, `_internal/status_bar.py` | Each shell widget renders a `MainWindowViewModel` correctly — the running pill appears only when `running_pill_visible`, the Settings action is disabled when `settings_action_enabled` is false, the health dot matches `health_state` | `pytest-qt` unit tests, colocated in `_internal/tests/` |
| `_internal/close_handler.py` | The quit sequence shows the correct confirmations in the correct order for each combination of running-run and dirty-buffer state, and a cancel aborts the quit | `pytest-qt` unit tests with a fake `MainWindowGateway` (its `is_run_active()` / `shutdown()` stubbed) |
| `_internal/geometry.py` | The debounced write coalesces a burst of resize events into one settings write; the off-screen clamp returns a valid placement | unit tests with a fake `MainWindowGateway` (its geometry get/set stubbed) |
| `MainWindowController` | Each subscribed event produces the expected `MainWindowViewModel` — verified against a fake `EventBus`, a fake `MainWindowGateway`, and the workspace store | unit tests, colocated |
| `make_main_window` end to end | The shell launches, the deferred tick schedules a readiness probe, a `_run_started` event reflows the layout and shows the pill, a `_run_finished` event restores the idle layout | integration test at the top-level `tests/` with the fake service suite from each service's `testing.py` |

The Main Window's unit tests substitute a fake `MainWindowGateway` (plus the Event Bus and the retained adapter helpers); the Main Window is never tested against a concrete backend service nor a raw backend Protocol.
