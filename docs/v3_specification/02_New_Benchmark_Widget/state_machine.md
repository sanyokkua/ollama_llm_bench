# New Benchmark Widget — State Machine

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:**
`02_New_Benchmark_Widget/description.md`,
`02_New_Benchmark_Widget/flow_diagram.md`,
`08_Cross_Cutting/08-H_app_modes.md`,
`08_Cross_Cutting/08-J_event_bus_catalog.md`,
`11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`

This document defines the lifecycle states of the New Benchmark widget and its
sub-machines. The widget-level machine covers loading, the interactive idle state, the
confirmation step, and the read-only lock that applies once a run starts. The sub-machines
describe section visibility per run mode, the multi-provider Test Models selection, the
Task Files empty/populated states, and the Judge section's enabled/disabled controls.

---

## Table of Contents

1. Widget-level state machine
2. Section-visibility sub-machine
3. Test Models multi-provider sub-machine
4. Task Files sub-machine
5. Judge section sub-machine
6. State affordances

---

## 1. Widget-level state machine

```mermaid
stateDiagram-v2
    [*] --> Loading: widget constructed
    Loading --> Idle: providers loaded, mode restored from benchmark.last_mode

    state Idle {
        [*] --> NoSelection
        NoSelection --> SomeSelection: any field touched
        SomeSelection --> NoSelection: all configuration cleared
        NoSelection --> StartDisabled: validate
        SomeSelection --> StartConditional: re-validate
        StartConditional --> StartEnabled: no hard error
        StartConditional --> StartDisabled: at least one hard error
    }

    Idle --> Idle: mode_changed (re-render visibility, re-validate)
    Idle --> Confirming: click Start (no hard error)
    Confirming --> Idle: cancel Run Summary Dialog
    Confirming --> Starting: confirm Run Summary Dialog
    Starting --> Locked: _run_started received
    Starting --> Idle: _run_start_failed received (creation failed before the pipeline began)
    Locked --> Idle: _run_finished / _run_failed / _run_stopped
```

**Creation event sequence (MISS-15).** On `confirm Run Summary Dialog` the widget calls the adapter's `start_run(...)` command and enters **Starting**. Run creation — building and persisting the run snapshot (the `benchmark_runs` row, the model/provider/settings snapshot tables, the `PENDING` result rows) and scheduling the pipeline on the `TaskRunner` — then runs. Exactly one of two events follows and is the **only** way to leave Starting:

- `_run_started` — the pipeline has begun executing → **Starting → Locked**.
- `_run_start_failed` — creation failed *before* the pipeline began (a persistence write failed, the snapshot build raised, or the single-inference gate could not be acquired) → **Starting → Idle**. The widget re-enables its controls, restores the validated Start button, and surfaces the failure via a blocking error notification. No run is left half-created — creation is one atomic transaction (`12_Quality_and_NFRs/06_DATA_INTEGRITY.md`), so a failure rolls back and no `benchmark_runs` row persists.

This guarantees **Starting** can never be a terminal trap: `_run_start_failed` is distinct from `_run_failed` (the latter is a fatal error *during* an already-running pipeline, handled from **Locked**). Creation is also bounded by construction — the snapshot writes go through the single synchronous DB writer with no queue/back-pressure (DD-41), so the creation worker cannot wedge on write contention. As a **safety net** against any other stall (SPEC-112), entering **Starting** arms a bounded reconciliation watchdog (the same pattern as the Progress widget's draining sub-state, SPEC-098): on expiry the widget re-reads `BenchmarkFlowApi.is_running()` / the run's authoritative status and reconciles — proceeding to **Locked** if a run is active, or back to **Idle** with an error notice if not — so Starting can never hang indefinitely even if neither event is delivered.

## 2. Section-visibility sub-machine

The Mode Visibility Policy maps `(mode, flags)` to the visible section set. The widget
re-renders on every `mode_changed` event.

```mermaid
stateDiagram-v2
    [*] --> ResolveMode
    ResolveMode --> ModePerf: mode == SYNTHETIC
    ResolveMode --> ModeSpeed: mode == TASKS
    ResolveMode --> ModeGrade: mode == GRADED

    state ModePerf {
        PerfMatrixP: Performance Matrix VISIBLE
        JudgeP: Judge VISIBLE (analysis toggle default OFF, judge optional)
        TestModelsP: Test Models VISIBLE
        AdvancedP: Advanced Options VISIBLE
    }
    state ModeSpeed {
        JudgeS: Judge VISIBLE (analysis toggle default OFF, judge optional)
        TestModelsS: Test Models VISIBLE
        TaskFilesS: Task Files VISIBLE
        AdvancedS: Advanced Options VISIBLE
    }
    state ModeGrade {
        JudgeG: Judge VISIBLE — analysis toggle default ON, judge required when either the per-task judge phase or the analysis toggle is on
        EmbeddingG: Embedding status row VISIBLE
        TestModelsG: Test Models VISIBLE
        TaskFilesG: Task Files VISIBLE
        AdvancedG: Advanced Options VISIBLE
    }

    ModePerf --> ResolveMode: mode_changed
    ModeSpeed --> ResolveMode: mode_changed
    ModeGrade --> ResolveMode: mode_changed
```

## 3. Test Models multi-provider sub-machine

Selected `(provider, model)` pairs persist across provider switches in the selection
store.

```mermaid
stateDiagram-v2
    [*] --> Empty
    Empty --> Browsing: provider selected in dropdown
    Browsing --> SomeChecked: user toggles a model on
    SomeChecked --> SomeChecked: user toggles more models
    SomeChecked --> MultiProvider: user switches provider and toggles a model
    MultiProvider --> MultiProvider: more changes across providers
    SomeChecked --> Empty: Clear All on the only browsed provider
    MultiProvider --> SomeChecked: all pairs of one provider cleared
    MultiProvider --> Empty: every pair removed
```

## 4. Task Files sub-machine

Applies only in `TASKS` and `GRADED`.

```mermaid
stateDiagram-v2
    [*] --> EmptyDropZone: task list empty — dashed placeholder shown
    EmptyDropZone --> Populated: file added (drop, Add File, or Add Folder)
    Populated --> Populated: more files added or removed (at least one remains)
    Populated --> EmptyDropZone: all rows removed
```

## 5. Judge section sub-machine

```mermaid
stateDiagram-v2
    [*] --> ResolveMode
    ResolveMode --> ToggleDefaultOff: SYNTHETIC or TASKS (toggle visible, defaults OFF)
    ResolveMode --> ToggleDefaultOn: GRADED (toggle visible, defaults ON)

    ToggleDefaultOff --> ControlsGreyed: provider/model dropdowns visible but disabled
    ControlsGreyed --> ControlsActive: user turns the toggle ON
    ControlsActive --> ControlsGreyed: user turns the toggle OFF
    ToggleDefaultOn --> ControlsRequired: provider/model dropdowns active and required (default case — judge phase and analysis both ON)
    ControlsRequired --> ControlsOptional: user disables BOTH the per-task judge phase and the analysis toggle
    ControlsOptional --> ControlsRequired: user re-enables either the per-task judge phase or the analysis toggle
```

## 6. State affordances

| State | Interactive | Notes |
|---|---|---|
| Loading | No | Provider dropdowns and mode selector show a loading state until populated |
| Idle / NoSelection | Yes | Start disabled; tooltip lists missing inputs |
| Idle / SomeSelection / StartDisabled | Yes | Start disabled; tooltip lists hard errors |
| Idle / SomeSelection / StartEnabled | Yes | Start enabled; tooltip reflects soft warnings if any |
| Confirming | Partly | Underlying panel is non-interactive while the Run Summary Dialog is modal |
| Starting | No | Brief; awaiting `_run_started`/`_run_start_failed`, with a bounded reconciliation watchdog (SPEC-112) |
| Locked | No | Entire widget read-only for the duration of the run; see `08_Cross_Cutting/08-H_app_modes.md` |
