# Resume Benchmark Widget — Flow Diagrams

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `03_Resume_Benchmark_Widget/description.md`, `03_Resume_Benchmark_Widget/state_machine.md`, `07_Common_Dialogs/`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `10_Domain_and_Data/05_EXPORT_FORMATS.md`, `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md`

This document gives a Mermaid sequence or flow diagram for every major user action of the Resume Benchmark widget: resume a run, retry selected tasks, clone a run, rename a run, delete a run, export a run, show the run-log file, and the live-update path. Each diagram names the concrete Protocol methods and event-bus events involved; the definitions of those are in `08_Cross_Cutting/08-E_interfaces_contracts.md` and `08_Cross_Cutting/08-J_event_bus_catalog.md`.

---

## Table of Contents

1. Resume a run
2. Retry selected tasks
3. Clone as new retry run
4. Rename a run
5. Delete a run
6. Export a run
7. Show the run-log file
8. Live update

---

## 1. Resume a run

The user selects a resumable run and clicks Resume Run. The Resume use case runs the drift detector against a fresh readiness snapshot, the Resume Summary dialog surfaces drift and a task picker, and on confirm the pipeline resumes.

```mermaid
sequenceDiagram
    actor U as User
    participant RB as Resume Benchmark Widget
    participant RU as Resume use case
    participant RS_ as RunsStore
    participant RES as ResultsStore
    participant RS as ReadinessService
    participant DD as Run Drift Detector
    participant RSD as Resume Summary Dialog
    participant FA as BenchmarkFlowApi
    participant EB as Event Bus

    U->>RB: select a resumable row
    U->>RB: click Resume Run
    RB->>RU: resume(run_id)
    RU->>RS_: get_run(run_id)
    RU->>RES: list_resumable_results(run_id)
    alt no resumable result
        RU-->>EB: emit _global_message("Fully completed — nothing to resume")
        EB-->>RB: toast shown, no dialog opens
    else resumable
        RU->>RS: refresh readiness snapshot
        RS-->>RU: AppReadinessSnapshot
        RU->>DD: detect(run, live config, snapshot)
        DD-->>RU: tuple of DriftWarning
        RU->>RSD: open(run, resumable results, drift warnings)
        RSD->>RSD: pre-check PENDING + non-terminal + retryable-failure results
        RSD->>RSD: render drift panel (BLOCKING gates Resume behind "Resume anyway")
        alt user cancels or a BLOCKING warning is unacknowledged
            RSD-->>RB: dialog dismissed, no resume
        else user confirms
            U->>RSD: adjust task selection, acknowledge any BLOCKING, Confirm
            RSD->>FA: resume(run_id)
            Note over FA: pipeline re-runs PENDING + retryable results from the run snapshot
            FA-->>EB: emit _run_started (RunStartedEvent)
            EB-->>RB: re-evaluate gating — the run is now executing
        end
    end
```

The pipeline resumes against the run's **frozen snapshot**, captured at the original run start — the providers, models, embedding selection, and settings the run was created with. The drift detector's job is to warn, before confirm, that the live environment no longer satisfies that snapshot; the resumed pipeline still uses the snapshot regardless. See `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md`.

## 2. Retry selected tasks

A context-menu-only action that acts within the selected run. The user picks individual result rows in the Retry Selection dialog; those results are reset to `PENDING` and the run is resumed.

```mermaid
sequenceDiagram
    actor U as User
    participant RB as Resume Benchmark Widget
    participant CM as Context menu
    participant RSD as Retry Selection Dialog
    participant RU as Resume use case
    participant RS_ as RunsStore
    participant RES as ResultsStore
    participant FA as BenchmarkFlowApi
    participant EB as Event Bus

    U->>RB: right-click a row
    RB->>CM: open context menu
    U->>CM: pick "Retry selected tasks…"
    CM->>RES: list_results(run_id)
    RES-->>CM: results
    CM->>RSD: open(results)
    Note over RSD: retryable-failure results pre-checked,<br/>COMPLETED results unchecked but selectable
    alt user cancels
        RSD-->>RB: dialog dismissed, nothing changed
    else user confirms a non-empty selection
        U->>RSD: toggle result rows, Confirm
        RSD->>RU: retry(run_id, selected result_ids)
        RU->>RES: update_result(result_id, ResultPatch -> status PENDING, errors cleared) for each selected id
        RU->>RS_: update_run_status(run_id, RunStatusPatch -> status INCOMPLETE)
        RU->>FA: resume(run_id)
        FA-->>EB: emit _run_started (RunStartedEvent)
    end
```

Retry is deliberately kept out of the footer to avoid confusing "select a different run in the table" with "re-run tasks within the selected run". Resetting a result writes a `ResultPatch` that sets `status = PENDING` and clears the `error_kind`, error-message, and in-flight columns; the subsequent `resume` then re-runs every `PENDING` result, exactly as a Resume does.

## 3. Clone as new retry run

A context-menu-only action that creates a new run from the selected run, preserving the original for comparison.

```mermaid
flowchart TD
    A[Right-click row → Clone as new retry run] --> B[RunsStore.get_run + TasksStore.list_tasks + ResultsStore.list_results on the source]
    B --> C["Build new BenchmarkRun:<br/>copy mode + frozen task/model/provider/settings snapshots,<br/>name = source name + ' (retry)', run_analysis cleared, status INCOMPLETE"]
    C --> D[RunsStore.create_run -> new run_id]
    D --> E[TasksStore.create_tasks -- copy the frozen task snapshot]
    E --> F[Build result rows:<br/>COMPLETED source results copied as-is,<br/>all others created PENDING with errors cleared]
    F --> G[ResultsStore.create_results]
    G --> H[create_run / create_results path emits _run_list_changed]
    H --> I[Widget rebuilds the table, new run appears at top]
    I --> J[Widget selects the new run -> emits _run_id_changed]
```

The clone reuses the source's snapshot verbatim, so it is reproducible against the same providers, models, and settings the original used. The clone is always resumable — it has `PENDING` results — and the user resumes it through the standard Resume flow (Section 1).

## 4. Rename a run

Context-menu item, or the inline pencil Icon Button on a row. The Resume Benchmark widget is the only surface that renames a non-executing run.

```mermaid
sequenceDiagram
    actor U as User
    participant RB as Resume Benchmark Widget
    participant RRD as Rename Run Dialog
    participant RNU as Rename use case
    participant RS_ as RunsStore
    participant EB as Event Bus

    U->>RB: pick "Rename…" (context menu or inline pencil)
    RB->>RRD: open(current effective name)
    alt user cancels
        RRD-->>RB: dialog dismissed, name unchanged
    else user confirms
        U->>RRD: type a new name, Confirm
        RRD->>RNU: rename(run_id, new_name)
        RNU->>RS_: rename_run(run_id, new_name)
        Note over RNU: new_name = None restores the generated name
        RNU-->>EB: emit _run_renamed (RunRenamedEvent)
        RNU-->>EB: emit _run_list_changed (RunListChangedEvent)
        EB-->>RB: _run_renamed patches the row name in place
    end
```

`_run_renamed` lets every single-name surface (the Result widget header, a tab label) update without rebuilding a list; `_run_list_changed` lets list surfaces rebuild their rows. The Resume Benchmark widget reacts to `_run_renamed` by patching just the affected Run name cell.

## 5. Delete a run

Context-menu item only. The Resume Benchmark widget is the only surface that deletes a run.

```mermaid
sequenceDiagram
    actor U as User
    participant RB as Resume Benchmark Widget
    participant CM as Context menu
    participant DCD as Delete Confirmation Dialog
    participant DLU as Delete use case
    participant RS_ as RunsStore
    participant EB as Event Bus

    U->>RB: right-click a non-executing row
    RB->>CM: open context menu
    U->>CM: pick "Delete"
    CM->>DCD: confirm "Delete run '<name>'? This cannot be undone."
    alt user cancels
        DCD-->>RB: dialog dismissed, nothing deleted
    else user confirms
        DCD->>DLU: delete(run_id)
        DLU->>RS_: delete_run(run_id)
        Note over RS_: cascade removes results, tasks, and snapshot child rows
        DLU-->>EB: emit _run_list_changed (RunListChangedEvent)
        EB-->>RB: row removed, if it was selected, selection clears
    end
```

Delete is disabled for the run currently executing (application-modes contract). When the deleted run was the one shown in the centre and right panels, those panels return to their no-selection state once the row is removed.

## 6. Export a run

Context-menu items. Summary and Details export to CSV or Markdown; Run Analysis exports to Markdown only. The diagram covers all three; the per-format content is fixed by `10_Domain_and_Data/05_EXPORT_FORMATS.md`.

```mermaid
sequenceDiagram
    actor U as User
    participant RB as Resume Benchmark Widget
    participant CM as Context menu
    participant RS_ as RunsStore
    participant RES as ResultsStore
    participant TS as TasksStore
    participant EX as Export writer
    participant NP as NativePickers
    participant EB as Event Bus

    U->>RB: right-click a row
    RB->>CM: open context menu
    U->>CM: pick an Export item
    alt Export Run Analysis and run_analysis is empty
        CM-->>EB: emit _global_message("No analysis for this run")
    else exportable
        CM->>RS_: get_run as the kind needs
        CM->>RES: list_results as the kind needs
        CM->>TS: list_tasks as the kind needs
        CM->>NP: save_file('<effective_run_name>_<kind>.<ext>')
        CM->>EX: build rows for kind (Summary | Details | RunAnalysis)
        EX->>EX: write to chosen path atomically (temp file + rename) - no redaction step
        alt write fails (permissions, full disk, path gone)
            EX-->>EB: emit _global_message("Export failed: <reason>")
        else write succeeds
            EX-->>EB: emit _global_message("Exported <filename>")
        end
    end
```

Exports write user-authored task content and user-machine model responses verbatim — the application does not apply a redaction step to exports (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1, `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md` §6.5). API-key material is not a column of any export. The filename pattern, column order, escaping, and encoding are defined authoritatively in `10_Domain_and_Data/05_EXPORT_FORMATS.md` — this widget never redefines them.

## 7. Show the run-log file

```mermaid
sequenceDiagram
    actor U as User
    participant RB as Resume Benchmark Widget
    participant CM as Context menu
    participant FSA as FileSystemActions
    participant EB as Event Bus

    U->>RB: right-click a row
    RB->>CM: open context menu
    Note over CM: "Show run-log file" enabled only when the file exists
    U->>CM: pick "Show run-log file"
    CM->>FSA: open_in_file_manager('<app-data>/logs/run/run_<run_id>_<started_at>.log')
    alt the file was removed after the menu opened
        FSA-->>EB: FileSystemActionsError -> emit _global_message("Run log file not found")
    else success
        FSA-->>U: OS file manager opens with the log file revealed
    end
```

Per-run log files live in their own `logs/run/` subfolder of the application data directory; the path layout is fixed in `10_Domain_and_Data/07_FILE_LAYOUT.md`.

## 8. Live update

The widget keeps its table consistent without polling by reacting to event-bus signals. Every subscription is owner-bound to the widget.

```mermaid
flowchart LR
    P[Benchmark Pipeline] -->|_run_started / _run_finished /<br/>_run_stopped / _run_failed| EB[Event Bus]
    R[Rename use case] -->|_run_renamed| EB
    L[Clone / Delete / Create use cases] -->|_run_list_changed| EB
    AN[Run-analysis use case] -->|_run_analysis_received| EB
    TF[Task Editor] -->|_task_file_changed| EB
    SEL[Run-selection controller] -->|_run_id_changed| EB

    EB --> RB[Resume Benchmark Widget]
    RB --> A[_run_list_changed: rebuild table, re-apply filter+sort, keep selection by run_id]
    RB --> B[_run_renamed: patch the affected Run name cell in place]
    RB --> C[_run_started / terminal events: refresh Status badge + Tasks fraction, re-gate actions]
    RB --> D[_run_analysis_received: enable Export Run Analysis for that run]
    RB --> E[_task_file_changed: refresh Tasks count for runs referencing that file]
    RB --> F[_run_id_changed: sync table selection to the changed run]
```

The widget also emits `_run_id_changed` when the user selects a row, and `_global_message` for toast-worthy outcomes (export results, refused resume, file-open failure).
