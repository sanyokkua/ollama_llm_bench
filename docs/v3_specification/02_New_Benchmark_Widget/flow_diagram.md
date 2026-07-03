# New Benchmark Widget — Flow Diagrams

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:**
`02_New_Benchmark_Widget/description.md`,
`02_New_Benchmark_Widget/state_machine.md`,
`07_Common_Dialogs/run_summary_dialog.md`,
`08_Cross_Cutting/08-E_interfaces_contracts.md`,
`08_Cross_Cutting/08-J_event_bus_catalog.md`,
`11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`

This document contains the sequence and flow diagrams for the major user actions in the
New Benchmark widget: starting a run end-to-end, refreshing section visibility on a mode
change, refreshing provider lists after a Settings save, drag-dropping task files,
selecting models across multiple providers, the validation feedback loop, and the judge
analysis toggle interplay.

---

## Table of Contents

1. End-to-end Start flow
2. Mode-change visibility refresh
3. Provider-list refresh on Settings save
4. Drag-drop into Task Files
5. Multi-provider model selection
6. Validation feedback loop
7. Judge analysis toggle interplay

---

## 1. End-to-end Start flow

```mermaid
flowchart TB
    pick[User picks mode + models + tasks-or-sizes + judge + advanced overrides] --> validate{Run Validator}
    validate -- hard errors --> tooltip[Start button disabled, tooltip lists reasons]
    validate -- no hard error --> build[Build RunStartEvent]
    build --> dialog[Open Run Summary Dialog]
    dialog -- Back --> back[Return to widget Idle state]
    dialog -- Start Benchmark --> rc[Run Configuration Controller handles Start]
    rc --> snap[Snapshot per-run-overridable settings into run.run_settings_snapshot]
    snap --> createrun[Data Store: create run]
    createrun --> modecheck{mode == SYNTHETIC?}
    modecheck -- yes --> gen[Pipeline generates synthetic tasks, no result pre-rows]
    modecheck -- no --> prerows[Data Store: create result pre-rows for task x model]
    gen --> emit[Emit _run_id_changed and _run_ids_changed]
    prerows --> emit
    emit --> start[Benchmark Pipeline starts, emits _run_started]
    start --> lock[Widget receives _run_started, transitions to Locked]
```

## 2. Mode-change visibility refresh

```mermaid
sequenceDiagram
    actor U as User
    participant MS as Mode Radio List
    participant W as New Benchmark Widget
    participant MVP as Mode Visibility Policy
    participant SS as Settings Store
    U->>MS: select "Graded Benchmark"
    MS->>W: mode_changed(GRADED)
    W->>SS: persist benchmark.last_mode = GRADED
    W->>MVP: visible_sections(GRADED, flags)
    MVP-->>W: {judge, embedding_status, task_files, test_models, advanced}
    W->>W: show / hide section primitives
    W->>W: re-run Run Validator, update Start button
```

## 3. Provider-list refresh on Settings save

```mermaid
sequenceDiagram
    participant SD as Settings Dialog
    participant EB as Event Bus
    participant TM as Test Models section
    participant JD as Judge section
    SD->>EB: emit _provider_registry_reloaded
    EB->>TM: handler invoked (ownership-bound subscription)
    EB->>JD: handler invoked (ownership-bound subscription)
    TM->>TM: rebuild Provider dropdown with enabled providers
    TM->>TM: keep current selection if still enabled, else select first
    JD->>JD: rebuild Judge Provider dropdown with enabled providers
    JD->>JD: re-validate, refresh Start button
```

## 4. Drag-drop into Task Files

```mermaid
sequenceDiagram
    actor U as User
    participant DZ as Task Files drop target (placeholder or List View)
    participant DDH as Drag-drop handler
    participant TFL as Task File Loader
    participant TF as Task Files section
    U->>DZ: drag YAML files or a folder over the drop target
    DZ->>DDH: drag-enter (accept)
    U->>DZ: drop
    DZ->>DDH: drop event with paths
    DDH->>TFL: parse each YAML path
    TFL-->>DDH: BenchmarkTask records, or a parse error
    alt parse succeeded
        DDH->>TF: add row with (N tasks) badge
        TF->>TF: switch from empty placeholder to populated List View
        TF->>TF: re-validate, refresh Start button
    else parse failed
        DDH->>TF: show inline error, add no row (EC-TASK-1)
    end
```

## 5. Multi-provider model selection

```mermaid
sequenceDiagram
    actor U as User
    participant TM as Test Models section
    participant Store as Selection store (held by Run Configuration Controller)
    U->>TM: browse provider "ollama_local"
    TM->>TM: render available models for ollama_local
    U->>TM: toggle 3 models on
    TM->>Store: add (ollama_local, model_a), (ollama_local, model_b), (ollama_local, model_c)
    U->>TM: browse provider "lm_studio_local"
    TM->>TM: render available models for lm_studio_local
    U->>TM: toggle 2 models on
    TM->>Store: add (lm_studio_local, model_d), (lm_studio_local, model_e)
    TM->>TM: update summary "Selected models (5 across 2 providers)"
    TM->>TM: re-validate, refresh Start button
```

## 6. Validation feedback loop

```mermaid
flowchart TB
    field[Any configuration field changes] --> reval[Re-run Run Validator]
    reval --> entries[Validation entries with severities]
    entries --> haserr{Any hard error?}
    haserr -- yes --> dis[Disable Start, tooltip lists hard-error messages]
    haserr -- no --> haswarn{Any soft warning?}
    haswarn -- yes --> enw[Enable Start, tooltip = review warnings before starting]
    haswarn -- no --> en[Enable Start, default tooltip]
```

## 7. Judge analysis toggle interplay

```mermaid
flowchart TB
    init[Widget constructed] --> resolvemode{Resolve run mode}
    resolvemode -- SYNTHETIC / TASKS --> off[Toggle visible, default OFF]
    resolvemode -- GRADED --> on[Toggle visible, default ON]
    off --> idle((Idle))
    on --> idle
    idle -- user toggles in any mode --> store[Store value in panel state, do not persist to user settings]
    store --> idle
    idle -- Start confirmed --> evt[Build RunStartEvent with current judge_analysis_enabled]
    evt --> done([Pipeline reads run snapshot judge_analysis_enabled])
```
