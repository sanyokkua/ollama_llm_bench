---
id: STORY-053
title: Build the Main Window application shell — menu bar, workspace region, status bar, and quit sequence
status: ready
spec_clauses:
  - 01_Main_Window/description.md#3-menu-bar
  - 01_Main_Window/description.md#4-status-bar
  - 01_Main_Window/description.md#5-workspace-switcher-and-the-workspace-region
  - 01_Main_Window/description.md#6-window-level-run-states
  - 01_Main_Window/description.md#8-close-confirmation-behaviour
  - 01_Main_Window/description.md#10-event-bus-integration
  - 01_Main_Window/state_machine.md#2-state-semantics
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b1-mainwindowgateway
  - 08_Cross_Cutting/08-H_app_modes.md#2-run-state-function-matrix
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/main_window/
acceptance_criteria:
  - STORY-053-AC-1
  - STORY-053-AC-2
  - STORY-053-AC-3
  - STORY-053-AC-4
  - STORY-053-AC-5
  - STORY-053-AC-6
  - STORY-053-AC-7
  - STORY-053-AC-8
  - STORY-053-AC-9
edge_cases:
  - EC-RUN-4
  - EC-WS-2
  - EC-SET-1
  - EC-PLAT-3
depends_on:
  - STORY-049
  - STORY-051
adrs:
  - ADR-0001
  - ADR-0007
  - ADR-0008
owner: coder
estimate: L
---

# STORY-053 — Build the Main Window application shell — menu bar, workspace region, status bar, and quit sequence

## Goal

Deliver the single top-level application shell: a `QMainWindow` that hosts the minimal
menu bar (Settings action, About action, workspace switcher, running pill, version), the
swappable workspace region, and the persistent status bar (health dot, toast region,
version). The shell reflects the window-level run state driven entirely by `_run_*`
lifecycle events, gates the Settings action while a run is non-terminal, runs the
close-confirmation sequence on quit, and restores/persists window geometry, splitter sizes,
and the active workspace — so every other Phase 10 widget has a shell to mount into.

## In scope

- `ui/main_window/protocols.py`: the `MainWindowGateway` Protocol declared locally with the
  exact method signatures of 08-E §7b.1 (window geometry / splitter / workspace / theme
  get-set, `readiness_snapshot`, `reprobe`, `is_run_active`, `shutdown`).
- `ui/main_window/api.py` (or `factory.py`): `make_main_window(...) -> QMainWindow` — the
  single public symbol — assembling the shell from its `_internal/` pieces (`shell`,
  `menu_bar`, `status_bar`, `close_handler`, `geometry`).
- `MainWindowViewModel` and `MainWindowController`: subscribe to `_run_started`,
  `_run_paused`, `_run_resumed`, `_run_stopped`, `_run_finished`, `_run_failed`,
  `_run_renamed`, `_app_readiness_changed`, `_global_message`, `_workspace_changed`; derive
  the shell view-model.
- The quit-confirmation sequence (running-benchmark prompt then unsaved-buffer prompt).
- Geometry / splitter / active-workspace restore-on-launch and debounced persist-on-change,
  including the off-screen clamp.

## Out of scope

- The Settings dialog, the two workspace bodies, and any panel content — mounted through the
  injected `benchmark_workspace_factory` / `task_editor_workspace_factory` callables, owned by
  their own stories (STORY-054..069).
- The About and Error dialogs — owned by STORY-070.
- Wiring the concrete `MainWindowGateway` implementation and the workspace factories — done in
  `compose.py`, which this story **must not touch** (Phase 11 owns `compose.py`).
- The dirty-buffer count source: the close handler queries it through the injected task-editor
  hook; the Task Editor owns producing it (STORY-068).
- This is a widget-level proxy; the real headless full-application launch/shutdown smoke test
  remains Phase 11's `tests/e2e/` deliverable once `compose.py` exists, and Phase 11 should
  build on this coverage rather than duplicate it.

## Spec inputs

- `01_Main_Window/description.md#3-menu-bar` — the exact menu-bar items, their order, and the
  Settings-disabled-while-non-terminal / running-pill-visible-only-while-non-terminal rules.
- `01_Main_Window/description.md#4-status-bar` — the three status-bar regions and the health-dot
  state-to-colour-and-label table.
- `01_Main_Window/description.md#5-workspace-switcher-and-the-workspace-region` — atomic
  workspace swap, lazy Task Editor construction, dirty-buffer prompt on leaving the editor.
- `01_Main_Window/description.md#6-window-level-run-states` — the affordance each window-level
  state imposes on the shell; the single run-activity source shared with Progress and Result.
- `01_Main_Window/description.md#8-close-confirmation-behaviour` — the up-to-two-confirmations
  quit sequence and the bounded graceful shutdown.
- `01_Main_Window/description.md#10-event-bus-integration` — the ten subscribed events and the
  shell reaction each produces.
- `01_Main_Window/state_machine.md#2-state-semantics` — every window-level shell state and its
  affordances; the state suite the `pytest-qt` tests must exercise.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b1-mainwindowgateway` — the exact gateway
  method surface this widget's `protocols.py` declares and the controller depends on.
- `08_Cross_Cutting/08-H_app_modes.md#2-run-state-function-matrix` — the terminal /
  non-terminal run-state definition that drives the Settings gate and the running pill.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` —
  appearance is set through theme roles resolved by `ui/theme`; the shell calls no
  `setStyleSheet` and embeds no colour literal.

## Design constraints

- The controller depends only on its own `MainWindowGateway` Protocol (plus `EventBus`,
  `WorkspaceController`, `NotificationService`, `FileSystemActions`); it never holds a backend
  store/service Protocol (D-R-06, SPEC-074) — enforced by a `pytest-archon` test.
- The public surface of `ui/main_window/` is exactly one symbol, `make_main_window`.
- No `setStyleSheet` and no colour literal outside `ui/theme/` (ADR-0001); no `asyncio`.
- Every `EventBus` subscription is owner-bound to the shell so it auto-cancels on destruction.
- The shell derives its state from the event stream and `MainWindowGateway.is_run_active()` at
  quit time; it never reads pipeline in-memory state directly.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-053-AC-1

Given the shell is in the `Idle` state, when a `_run_started` event is delivered, then the
running pill becomes visible, the Settings action becomes disabled, the health dot becomes
non-clickable, and the window title switches to the running title.

### STORY-053-AC-2

For each window-level run state, the shell imposes the affordances the specification assigns
it:

| Window state | Settings action | Running pill | Health dot clickable |
| ------------ | --------------- | ------------ | -------------------- |
| Idle         | enabled         | hidden       | yes                  |
| RunStarting  | disabled        | hidden       | no                   |
| Running      | disabled        | visible      | no                   |
| Paused       | disabled        | visible      | no                   |
| Stopping     | disabled        | visible      | no                   |
| Finishing    | disabled        | visible      | no                   |

### STORY-053-AC-3

Given a run is non-terminal, when a `_run_finished`, `_run_stopped`, or `_run_failed` event is
delivered, then the running pill is hidden, the Settings action is re-enabled, and the window
title returns to the default `Ollama LLM Bench v{version}` form.

### STORY-053-AC-4

Given the Benchmark workspace is active and no run is active, when a `_run_started` event is
delivered, then the left run-configuration panel is removed from the layout and the centre
panel expands; and when the run reaches a terminal state, the left panel reappears and the
idle three-panel layout with the persisted splitter sizes is restored.

### STORY-053-AC-5

Given a run is non-terminal, when the user requests a quit, then the running-benchmark
confirmation is shown first; on Confirm `MainWindowGateway.shutdown(timeout_ms)` is called and
the shell waits for `_run_stopped` or the bounded timeout before the process exits; on Cancel
the quit is aborted and the shell returns to its prior run state.

### STORY-053-AC-6

Given both a non-terminal run and one or more dirty task buffers, when the user requests a
quit, then the running-benchmark confirmation is shown before the unsaved-buffer confirmation,
and Cancel at either step aborts the entire quit.

### STORY-053-AC-7

Given a burst of window resize events, when the geometry writer runs, then it coalesces the
burst into a single `MainWindowGateway.set_window_geometry` write after the debounce interval.

### STORY-053-AC-8

Given a persisted window geometry that lies fully off-screen, when the shell restores geometry
on launch, then it clamps the geometry to the available screen area, falling back to the
centred default when no valid placement exists.

### STORY-053-AC-9

Given the shell is constructed with fakes for every declared collaborator — a fake
`MainWindowGateway`, `EventBus`, `WorkspaceController`, `NotificationService`, and
`FileSystemActions`, plus stub `benchmark_workspace_factory` and `task_editor_workspace_factory`
callables each returning a placeholder `QWidget` — and mounted under `qtbot`, when it is shown
(`qtbot.addWidget(...)`, `.show()`, one `qtbot.wait(0)`/event-loop pump), then no exception is
raised, the shell reports `isVisible()`, no `error`/`critical`-level `structlog` record is
captured, and at least one `DEBUG`-level construction event is captured — verified by wrapping
construction and show in `structlog.testing.capture_logs()` and asserting no captured entry's
`log_level` is in `{"error", "critical"}` while at least one entry's `log_level` equals
`"debug"`.

## Test plan

- STORY-053-AC-1 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/main_window/_internal/tests/test_controller.py`,
  `test_run_started_shows_pill_disables_settings`.
- STORY-053-AC-2 — table-driven unit (`pytest-qt`), same file,
  `test_shell_affordances_per_run_state`.
- STORY-053-AC-3 — unit (`pytest-qt`), same file,
  `test_terminal_event_restores_idle_affordances`.
- STORY-053-AC-4 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/main_window/_internal/tests/test_shell.py`,
  `test_benchmark_layout_reflows_on_run_lifecycle`.
- STORY-053-AC-5 — unit (`pytest-qt`, fake `MainWindowGateway`), colocated
  `src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py`,
  `test_quit_with_running_run_confirms_and_shuts_down`. Covers EC-RUN-4.
- STORY-053-AC-6 — unit (`pytest-qt`), same file,
  `test_quit_with_running_run_and_dirty_buffers_confirms_in_order`. Covers EC-WS-2.
- STORY-053-AC-7 — unit, colocated
  `src/ollama_llm_bench/ui/main_window/_internal/tests/test_geometry.py`,
  `test_resize_burst_coalesces_into_one_write`.
- STORY-053-AC-8 — unit, same file, `test_offscreen_geometry_is_clamped`. Covers EC-PLAT-3.
- EC-SET-1 — unit (`pytest-qt`), `test_controller.py`,
  `test_settings_action_disabled_while_run_non_terminal`.
- STORY-053-AC-9 — unit (`pytest-qt`, fakes for every collaborator), colocated
  `src/ollama_llm_bench/ui/main_window/_internal/tests/test_shell.py`,
  `test_main_window_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-053.
- [ ] EC-RUN-4, EC-WS-2, EC-SET-1, and EC-PLAT-3 each have a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises every window-level
  state in `01_Main_Window/state_machine.md`.
- [ ] An architecture test confirms `MainWindowController` depends only on `MainWindowGateway`
  (no backend store/service Protocol), that `ui/main_window/` references no `setStyleSheet`
  and embeds no colour literal, and that it imports no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/main_window/`.
- [ ] `just trace` resolves this story's spec clauses and the traceability record validates
  with no orphan clause and no orphan test for STORY-053.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
