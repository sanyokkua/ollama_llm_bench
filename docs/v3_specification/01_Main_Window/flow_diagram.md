# Main Window — Flow Diagrams

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-05-22
**Cross-references:** `01_Main_Window/description.md`, `01_Main_Window/state_machine.md`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `08_Cross_Cutting/08-M_app_lifecycle.md`

This document gives the Mermaid sequence and flow diagrams for every major shell-level interaction of the Main Window: application launch, starting a benchmark, the status-bar readiness update, closing the window while a run is in progress, switching the workspace, and the blocked attempt to open Settings during a run. Each diagram names the concrete contract methods and Event Bus signals involved so the flows are directly testable. Threading callouts mark which steps run on a background worker.

---

## Table of Contents

1. Launch flow
2. Start-benchmark flow
3. Status-bar readiness update flow
4. Close-with-running-run flow
5. Workspace-switch flow
6. Settings-blocked-during-run flow

---

## 1. Launch flow

The launch sequence is the ordered set of steps from process start to the Main Window's `Idle` state. The full sequence is normative in `08-M_app_lifecycle.md` §2; the diagram below is the Main-Window-facing view.

```mermaid
sequenceDiagram
    actor U as User
    participant P as Process entry point
    participant L as Launch sequence
    participant CR as Composition root
    participant W as Main Window
    participant WC as Workspace Controller
    participant RS as Readiness Service
    participant EB as Event Bus

    U->>P: Start the application
    P->>L: Run launch steps 1-9
    Note over L: detect platform, configure logging,<br/>ensure app-data dir, open + schema-check DB,<br/>seed defaults
    L->>CR: Build the composition root
    CR->>CR: Construct every service, wire the object graph
    L->>L: Start the UI toolkit, apply the theme
    L->>W: Construct the Main Window
    W->>WC: Read ui.active_workspace, install the workspace
    W->>U: Show the window (state: Initialising)
    W->>W: Schedule a single deferred tick
    Note over W: deferred tick fires after the window is painted
    W->>RS: probe_all()  [background worker]
    W->>W: Transition Initialising -> Idle
    RS-->>EB: emit _app_readiness_changed
    EB-->>W: readiness handler runs (UI thread)
    alt probe verdict READY
        W->>W: Status-bar dot -> green Ready
    else probe verdict DEGRADED or NOT_READY
        W->>W: Status-bar dot -> amber Degraded / red Not ready
        W->>U: Raise the startup-environment modal (what changed + how to fix)
    end
```

A failure in launch steps 1 through 5 aborts launch with an explanatory modal before the Main Window is ever constructed (`08-M_app_lifecycle.md` §2). The deferred tick guarantees the readiness probe never delays the first paint; the window is interactive in the `Idle` state while the probe is still in flight.

## 2. Start-benchmark flow

The user configures a run in the left panel and clicks Start; the Main Window reacts to the resulting `_run_started` event.

```mermaid
sequenceDiagram
    actor U as User
    participant NB as New Benchmark widget
    participant RC as Run-creation use case
    participant DS as Data Store
    participant FA as Benchmark Flow API
    participant EB as Event Bus
    participant W as Main Window
    participant PR as Progress widget
    participant RW as Result widget

    U->>NB: Pick mode, models, tasks, options
    U->>NB: Click Start Benchmark
    NB->>NB: Build a RunStartRequest
    NB->>RC: validate the request
    alt validation fails
        RC-->>EB: emit _global_message(reason)
        EB-->>W: show the reason as a status-bar toast
    else validation passes
        RC->>FA: start(RunStartRequest)
        FA->>DS: create_run(...), create_tasks(...), create_results(...)
        Note over FA: freeze the model / provider / settings snapshots
        FA-->>EB: emit _run_started(RunStartedEvent)  [worker -> UI]
        EB-->>W: run-started handler runs
        W->>W: show running pill, disable Settings,<br/>set running title, reflow to running layout
        EB-->>PR: switch to the running progress view
        EB-->>RW: run-selection store moves to the new run
    end
```

The Main Window's only role in this flow is the shell reaction to `_run_started` — the running pill, the disabled Settings action, the running title, and the layout reflow. It does not build the request, validate it, or call `start(...)`; those belong to the New Benchmark widget and the run-creation use case (`08-E_interfaces_contracts.md` §11).

## 3. Status-bar readiness update flow

The status-bar health dot is repainted whenever the aggregate readiness changes.

```mermaid
flowchart LR
    subgraph triggers[Triggers]
        T1[Application launch deferred tick]
        T2[Provider registry reloaded after a Settings save]
        T3[A run reached a terminal state]
        T4[Health dot clicked]
    end

    triggers --> probe["ReadinessService.probe_all()  [background worker]"]
    probe --> per[Probe every enabled provider and the embedding model]
    per --> agg["Aggregate into an AppReadinessSnapshot (overall: ReadinessState)"]
    agg --> emit["emit _app_readiness_changed (coalesced, <= 2/s)"]
    emit --> ui[Main Window readiness handler on the UI thread]
    ui --> dot[Repaint the status-bar dot in the ReadinessState colour role]
    ui --> tip[Refresh the dot tooltip with per-provider detail]
```

Overlapping probes are coalesced by the Readiness Service so the dot does not flicker (`08-J_event_bus_catalog.md` §5.7; edge case EC-PERF-2). A health-dot click additionally opens the Settings dialog on the Providers tab — but only when no run is non-terminal; see §6.

## 4. Close-with-running-run flow

```mermaid
flowchart TD
    click["Quit requested (window close (X) control)"] --> running{"BenchmarkFlowApi.is_running()?"}
    running -- no --> dirty{"Task Editor has dirty buffers?"}
    running -- yes --> rc["Modal: Stop the benchmark and quit?"]
    rc -- Cancel --> abort["Abort quit - return to the prior run state"]
    rc -- Confirm --> shutdown["BenchmarkFlowApi.shutdown(timeout_ms)"]
    shutdown --> wait["Wait for _run_stopped or the bounded timeout"]
    wait --> dirty
    dirty -- no --> persist["Persist ui.window_geometry, ui.splitter_sizes, ui.active_workspace"]
    dirty -- yes --> dc["Modal: Save changes to N file(s)? - Save All / Discard All / Cancel"]
    dc -- Cancel --> abort
    dc -- Save All --> save["Save every dirty task buffer"]
    dc -- Discard All --> persist
    save --> persist
    persist --> closedb["Close the SQLite database cleanly (WAL checkpoint)"]
    closedb --> exit["Exit the process"]
```

When both conditions hold, the running-benchmark prompt is shown first, then the unsaved-buffer prompt; a cancel at either step aborts the entire quit (`08-M_app_lifecycle.md` §7; edge cases EC-RUN-4 and EC-WS-2).

## 5. Workspace-switch flow

```mermaid
sequenceDiagram
    actor U as User
    participant W as Main Window
    participant TE as Task Editor controller
    participant WC as Workspace Controller
    participant SS as Settings Service
    participant EB as Event Bus

    U->>W: Click a switcher segment
    alt leaving the Task Editor with one or more dirty buffers
        W->>TE: query the aggregate dirty-buffer count
        W->>U: Modal: Save changes to N file(s)? - Save All / Discard All / Cancel
        alt Cancel
            W->>W: Abort the switch - no state change
        else Save All
            W->>TE: Save every dirty buffer
        else Discard All
            W->>TE: Discard the unsaved edits
        end
    end
    W->>WC: switch_to(target, hint)
    WC->>WC: Install the target workspace (lazy-construct on first activation)
    WC->>SS: write ui.active_workspace = target
    WC-->>EB: emit _workspace_changed(WorkspaceChangedEvent)
    EB-->>W: swap the workspace region, switch the status-bar left region
```

Switching the workspace never stops, pauses, or disturbs a benchmark run — the Benchmark Pipeline runs on a background worker independent of the active workspace. A click on the running pill is the same flow with `target = "benchmark"` and `hint = WorkspaceHint(focus_widget="progress")`, and no dirty-buffer prompt because it does not originate inside the Task Editor's leave path.

## 6. Settings-blocked-during-run flow

```mermaid
flowchart LR
    open["Click the Settings menu action"] --> check{"A run in a non-terminal state?"}
    check -- no --> show["Open the Settings modal dialog"]
    check -- yes --> noop["No-op - the action is shown disabled, with a tooltip explaining why"]
```

The same gate covers the status-bar health-dot click, which opens Settings on the Providers tab: while a run is non-terminal the click is ignored and a status-bar toast appears reading `Disabled - a benchmark is in progress.` (`08-H_app_modes.md` §10; edge case EC-SET-4). The Settings action is shown disabled in the menu bar so the user cannot reach the dialog during a run.
