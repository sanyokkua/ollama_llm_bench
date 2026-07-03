# Result Widget — Flow Diagrams

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `description.md`, `state_machine.md`, `implementation_structure.md`; `08_Cross_Cutting/08-E_interfaces_contracts.md`; `08_Cross_Cutting/08-J_event_bus_catalog.md`; `10_Domain_and_Data/05_EXPORT_FORMATS.md`; `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`; `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md`; `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`; `tabs/charts_tab.md`; `tabs/run_analysis_tab.md`

This document gives one sequence or flow diagram per major Result Widget action: switching the displayed run, the live update during an active run, exporting a table, exporting a chart, opening the Exports Folder, detaching a window, and regenerating the run analysis. Each flow names the services it calls; the abstract contracts are in `08_Cross_Cutting/08-E_interfaces_contracts.md`.

---

## Table of Contents

- A. Run-switch from the dropdown
- B. Live update during an active run
- C. Export a table tab (Summary or Details)
- D. Export a chart (PNG or SVG)
- E. Open the Exports Folder
- F. Detach a window
- G. Regenerate the run analysis
- H. Export gating while a run is in progress

---

## A. Run-switch from the dropdown

The user picks a different run; the parent controller refreshes the tab caches and announces the selection so the other workspace panels follow.

```mermaid
sequenceDiagram
    actor U as User
    participant RW as Result Widget
    participant PC as Result parent controller
    participant DS as Data Store
    participant AGG as Chart aggregators
    participant BUS as Event Bus
    U->>RW: pick a run in the dropdown
    RW->>PC: on_run_selected(run_id)
    PC->>PC: set selected run id, mark selection user-locked if not the active run
    PC->>PC: restore per-run view state for run_id
    PC->>BUS: emit _run_id_changed(run_id)
    PC->>DS: list_results(run_id)
    DS-->>PC: results
    PC->>PC: refresh Summary and Details caches
    PC->>RW: repaint the active tab
    Note over PC,AGG: Charts and Run Analysis caches refresh lazily on first tab activation
```

The Progress and Resume Benchmark widgets also subscribe to `_run_id_changed` and follow the same selection. When the change instead originates elsewhere, the same `_run_id_changed` handler updates the dropdown without re-emitting the event.

## B. Live update during an active run

While the active run is selected, the pipeline mutates result rows; the debounced data-changed events drive the tab repaints.

```mermaid
sequenceDiagram
    participant PIPE as Benchmark pipeline (background worker)
    participant SL as Table / chart Status Listener
    participant BUS as Event Bus
    participant RW as Result Widget
    PIPE-->>SL: a result row reached a terminal status
    SL->>SL: hold the latest dataset, debounce 250 ms
    SL->>BUS: emit _summary_data_changed + _detailed_data_changed + _chart_data_changed
    BUS-->>RW: deliver on the UI thread
    RW->>RW: refresh the cache of each tab
    RW->>RW: repaint the active tab, mark the others stale
```

The 250 ms debounce window (see `08_Cross_Cutting/08-J_event_bus_catalog.md` §4) bounds the repaint rate regardless of how fast tasks resolve (EC-PERF-3). A past run selected during an active run does not receive these repaints — its tabs render frozen persisted data.

## C. Export a table tab (Summary or Details)

The footer Export button on a table tab. The save-destination toggle decides whether a picker appears.

```mermaid
sequenceDiagram
    actor U as User
    participant RW as Result Widget
    participant SET as Settings Service
    participant TS as Table serialisation service
    participant FN as Export-filename helper
    participant OS as OS Adapter
    participant FS as File system
    participant NS as Notification Service
    U->>RW: click Export CSV or Export Markdown
    RW->>SET: get_bool("ui.export_save_directly")
    SET-->>RW: true or false
    RW->>TS: serialise the filtered, visible table to CSV / Markdown
    TS-->>RW: document text (redacted)
    RW->>FN: canonical filename(run, kind, ext)
    FN-->>RW: filename
    alt save-directly is true
        RW->>FS: atomic write to <app-data>/exports/<filename>
        FS-->>RW: written path
        RW->>NS: show_info("Saved to <path>")
    else save-directly is false
        RW->>OS: open_save_picker(Desktop, filename)
        OS-->>RW: chosen path or None
        opt the user chose a path
            RW->>FS: atomic write at the chosen path
            FS-->>RW: written path
            RW->>NS: show_info("Saved to <path>")
        end
    end
```

The serialised document covers only the filtered rows and visible columns of the active table, in the fixed column order from `10_Domain_and_Data/05_EXPORT_FORMATS.md`. Every write is a temp-file-then-rename, so a failed write leaves no partial file; a failure raises an error modal through the Notification Service (EC-RES-5).

## D. Export a chart (PNG or SVG)

The Charts footer renders the current chart off-screen at a fixed resolution and writes the image. The save-destination branch is the same as flow C.

```mermaid
flowchart TB
    click["User clicks Export PNG or Export SVG"] --> direct{"save-directly toggle on?"}
    direct -- yes --> render1["render the current chart off-screen at 2400x1600,<br>background and palette from the active theme"]
    render1 --> name1["compose canonical filename Chart_&lt;chart-slug&gt;.png / .svg"]
    name1 --> write1["atomic write to &lt;app-data&gt;/exports/"]
    write1 --> toast1(["toast: Saved to &lt;path&gt;"])
    direct -- no --> picker["open Save Picker, default Desktop / filename"]
    picker --> chosen{"path chosen?"}
    chosen -- no --> cancelled(["cancelled — no file written"])
    chosen -- yes --> render2["render the current chart off-screen at 2400x1600"]
    render2 --> write2["atomic write at the chosen path"]
    write2 --> toast2(["toast: Saved to &lt;path&gt;"])
```

The exported image is the single chart currently shown, including its title, axes, legend, and labels. A detached chart window's Export produces the identical file (see `10_Domain_and_Data/05_EXPORT_FORMATS.md` §8 and §9).

## E. Open the Exports Folder

The `Open Exports Folder` Button reveals the Exports Folder; it is visible only while the save-destination toggle is on.

```mermaid
sequenceDiagram
    actor U as User
    participant RW as Result Widget
    participant OS as OS Adapter
    U->>RW: click Open Exports Folder
    RW->>OS: open_in_file_manager(<app-data>/exports/)
    OS-->>U: the host OS file manager opens the Exports Folder
```

Turning the save-destination toggle off hides the Button immediately through the `_app_settings_changed` event; turning it on shows the Button on every tab footer and detached window at once.

## F. Detach a window

A tab's `Detach window` Button opens a Modeless Dialog that replicates the tab content and the uniform footer.

```mermaid
sequenceDiagram
    actor U as User
    participant TAB as Result tab (Summary / Details / Charts)
    participant PC as Result parent controller
    participant DW as Detached Modeless Dialog
    participant BUS as Event Bus
    U->>TAB: click Detach window
    TAB->>PC: request_detach(content kind, run_id, view state)
    PC->>DW: open(run_id, view state, current chart or filters)
    DW->>BUS: subscribe to the data-changed event for its content, owner = DW
    Note over DW: replicates the toolbar and the uniform footer<br>(prev/next, export, save-directly)
    U->>DW: filter, navigate, or export inside the dialog
    U->>DW: close the dialog
    DW->>BUS: subscription auto-cancelled on destruction
```

The detached window stays open when the user switches workspace (EC-WS-1). Export and Regenerate inside the dialog obey the same view-only-during-run rule as the main footer (flow H).

## G. Regenerate the run analysis

The Run Analysis tab's `Regenerate` Button asks the run-analysis service to produce a fresh consolidated narrative.

```mermaid
sequenceDiagram
    actor U as User
    participant RA as Run Analysis tab
    participant PC as Result parent controller
    participant RAS as Run-analysis service
    participant DS as Data Store
    participant BUS as Event Bus
    U->>RA: click Regenerate
    RA->>PC: regenerate_analysis(run_id)
    PC->>DS: get_run(run_id) + list_results(run_id)
    DS-->>PC: run + results
    PC->>RAS: generate_run_analysis(run, results)  [background worker]
    RAS-->>PC: narrative text
    PC->>DS: persist BenchmarkRun.run_analysis
    PC->>BUS: emit _run_analysis_received(run_id)
    BUS-->>RA: deliver on the UI thread
    RA->>RA: repaint the analysis text
```

`Regenerate` is disabled while any run is non-terminal (flow H). The same `_run_analysis_received` event also delivers the first analysis the pipeline produces when a run finishes; the tab handles both identically.

## H. Export gating while a run is in progress

Every export and the Regenerate action are disabled while any run is non-terminal, regardless of which run is displayed.

```mermaid
flowchart TB
    start["Run lifecycle event arrives"] --> kind{"event kind"}
    kind -- "_run_started" --> disable["disable every Export button and Regenerate,<br>set tooltip 'Disabled — a benchmark is in progress.'"]
    kind -- "_run_finished / _run_stopped / _run_failed" --> enable["re-enable every Export button and Regenerate atomically"]
    disable --> hold["dropdown, tab switch, filter, detach, copy,<br>chart navigation stay enabled"]
    enable --> hold
```

The gate is "no run is in a non-terminal state", not "the selected run is non-terminal": selecting a finished past run while a different run is still executing keeps the exports disabled. The full composite blocked-states contract is in `08_Cross_Cutting/08-H_app_modes.md` §10.
