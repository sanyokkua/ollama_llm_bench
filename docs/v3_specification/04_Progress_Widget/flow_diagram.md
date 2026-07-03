# Progress Widget — Flow Diagrams

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `description.md`, `state_machine.md`, `implementation_structure.md`; `08_Cross_Cutting/08-B_benchmark_state_machine.md`; `08_Cross_Cutting/08-J_event_bus_catalog.md`; `11_Services_and_Algorithms/15_LOG_FORMATTING.md`

This document gives one sequence or flow diagram per major user action and per major live-update path of the Progress Widget. Each diagram names the participating actors, the trigger, and the method or event at each step. Background-worker steps are marked `[bg-worker]`; UI-thread steps run on the main thread.

---

## Table of Contents

1. Pause and Resume
2. Stop
3. Rename the running run
4. Live counter and stage update
5. Live log append
6. Verbosity change
7. Switch to a past run
8. Provider circuit-breaker trip and retry probe

---

## 1. Pause and Resume

```mermaid
sequenceDiagram
    actor User
    participant Widget as Progress Widget
    participant Flow as Benchmark flow service
    participant Pipeline as Benchmark pipeline [bg-worker]
    participant Bus as Event bus
    User->>Widget: click Pause
    Widget->>Flow: pause(run_id)
    Flow->>Pipeline: request pause
    Pipeline->>Pipeline: finish the in-flight task, persist its result
    Pipeline-->>Bus: emit _run_paused(run_id)
    Bus-->>Widget: enter Paused state, freeze counters
    Note over Widget: layout unchanged, left panel stays hidden
    User->>Widget: click Resume
    Widget->>Flow: resume(run_id)
    Flow->>Pipeline: request resume
    Pipeline-->>Bus: emit _run_resumed(run_id)
    Bus-->>Widget: leave Paused, return to the frozen active stage
```

Pause never aborts the in-flight task. The pipeline halts cleanly with no stale worker threads; only after the in-flight task is persisted does `_run_paused` fire.

## 2. Stop

```mermaid
sequenceDiagram
    actor User
    participant Widget as Progress Widget
    participant Dialog as Confirmation modal dialog
    participant Flow as Benchmark flow service
    participant Pipeline as Benchmark pipeline [bg-worker]
    participant Store as Data store
    participant Bus as Event bus
    User->>Widget: click Stop
    Widget->>Dialog: open "Stop this run?"
    alt user cancels
        Dialog-->>Widget: dismissed, no operation
    else user confirms
        Dialog-->>Widget: confirmed
        Widget->>Flow: stop(run_id)
        Flow->>Pipeline: request stop
        Pipeline->>Pipeline: finish the in-flight task, then terminate the worker
        Pipeline->>Store: write RunStatus = STOPPED
        Pipeline-->>Bus: emit _run_stopped(run_id)
        Bus-->>Widget: enter Stopping, then ViewingPastRun
        Note over Widget: idle layout restored, left panel reappears
    end
```

## 3. Rename the running run

```mermaid
sequenceDiagram
    actor User
    participant Widget as Progress Widget
    participant Dialog as Rename Run modal dialog
    participant Runs as Run-registry store
    participant Store as Data store
    participant Bus as Event bus
    User->>Widget: click the rename pencil
    Widget->>Dialog: open(current_name)
    User->>Dialog: type a new name, click OK
    Dialog-->>Widget: new_name
    Widget->>Runs: rename_run(run_id, new_name)
    Runs->>Store: persist the new run name
    Runs-->>Bus: emit _run_renamed(run_id, new_name)
    Bus-->>Widget: update the run-name label
    Bus-->>Widget: every other widget showing this run also updates
```

The pencil is reachable only while the displayed run is in a non-terminal stage; see `state_machine.md` section 5.

## 4. Live counter and stage update

```mermaid
sequenceDiagram
    participant Pipeline as Benchmark pipeline [bg-worker]
    participant Bus as Event bus
    participant Counters as Counters sub-controller
    participant Stability as Stability sub-controller
    participant View as Progress Widget view
    Pipeline-->>Bus: emit _progress_updated(counts_by_status, current_provider, current_model)
    Bus-->>Counters: handler on the UI thread
    Counters->>Counters: derive counter values, stage-bar segments, ETA
    Counters->>View: apply(counters view-model)
    Pipeline-->>Bus: emit _stage_changed(stage, prev_stage)
    Bus-->>Counters: handler on the UI thread
    Counters->>View: apply(stage badge)
    Pipeline-->>Bus: emit _model_stability_changed(...)
    Bus-->>Stability: handler on the UI thread
    Stability->>View: apply(stability view-model)
```

Under high-rate completion the counters sub-controller coalesces consecutive `_progress_updated` events and applies the last payload; see `state_machine.md` section 6.

## 5. Live log append

```mermaid
flowchart TB
    ev[Pipeline emits a per-task or stage event] --> bus[Event bus delivers on the UI thread]
    bus --> cache[Log sub-controller stores the raw event]
    cache --> fmt[Log-formatting service builds an HTML line at the current verbosity]
    fmt --> append[Append the line to the log view]
    append --> cap{buffer over ui.run_log_max_lines?}
    cap -- yes --> trim[Remove the oldest lines from the top]
    cap -- no --> scroll
    trim --> scroll{user at the bottom?}
    scroll -- yes --> bottom[Auto-scroll to the newest line]
    scroll -- no --> hold[Hold scroll position]
```

The raw event is always cached so a later verbosity change can re-render without data loss; see flow 6.

## 6. Verbosity change

```mermaid
flowchart LR
    pick[User picks Short, Normal, or Verbose] --> persist[Persist ui.run_log_verbosity]
    persist --> rerender[Log sub-controller re-renders cached raw events at the new level]
    rerender --> done[Replace the visible buffer]
    note[The per-run log file is unchanged; it always records full Verbose detail]
```

## 7. Switch to a past run

```mermaid
sequenceDiagram
    actor User
    participant Resume as Resume Benchmark Widget
    participant Bus as Event bus
    participant Widget as Progress Widget
    participant Store as Data store
    participant Reader as Run-log file reader
    User->>Resume: select a past run
    Resume-->>Bus: emit _run_id_changed(run_id)
    Bus-->>Widget: handler invoked, no run active
    Widget->>Store: read the run summary and final counters
    Widget->>Reader: load <app-data>/logs/run/run_<run_id>_<ts>.log
    Reader-->>Widget: saved log lines
    Widget->>Widget: enter ViewingPastRun, paint the terminal badge and frozen counters
```

When a run is active the `_run_id_changed` handler is a no operation; the widget keeps showing the live run.

## 8. Provider circuit-breaker trip and retry probe

```mermaid
sequenceDiagram
    actor User
    participant Pipeline as Benchmark pipeline [bg-worker]
    participant Breaker as Provider circuit breaker
    participant Bus as Event bus
    participant Stability as Stability sub-controller
    participant View as Progress Widget view
    Pipeline->>Breaker: record repeated provider failures
    Breaker->>Breaker: trip to OPEN
    Breaker-->>Bus: emit _model_stability_changed(provider_state = open)
    Bus-->>Stability: handler on the UI thread
    Stability->>View: apply OPEN provider callout with the retry-probe link
    User->>View: click "retry probe"
    View->>Breaker: request an immediate health probe
    Breaker-->>Bus: emit _model_stability_changed(provider_state = half_open or closed)
    Bus-->>Stability: handler on the UI thread
    Stability->>View: repaint the provider callout
```
