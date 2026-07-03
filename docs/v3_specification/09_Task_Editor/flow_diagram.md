# Task Editor — Flow Diagrams

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-05-22
**Cross-references:** `09_Task_Editor/description.md`, `09_Task_Editor/state_machine.md`, `09_Task_Editor/field_reference.md`, `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`, `11_Services_and_Algorithms/12_YAML_FORMATTER.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`

This document specifies the Task Editor's major user actions as Mermaid sequence and flow diagrams: entering and leaving the workspace, opening a file, creating a file, adding and duplicating tasks, the validation cascade, Save and Save All, drag-drop, external file changes, the cross-workspace open, and the effect of a running benchmark. Each diagram is the binding interaction contract for that action, including its error branches.

---

## Table of Contents

1. Enter and leave the workspace
2. Open a file
3. Create a new file
4. Add a task
5. Duplicate a task
6. Validation cascade
7. Save and Save All
8. Drag-drop a file or folder
9. External file changed on disk
10. Open in Task Editor from the Benchmark workspace
11. Saving a file in use by a running benchmark

---

## 1. Enter and leave the workspace

```mermaid
sequenceDiagram
    actor U as User
    participant MW as MainWindow
    participant WC as WorkspaceController
    participant TE as TaskEditor
    participant ST as SettingsStore
    participant EB as EventBus

    U->>MW: click "Task Editor"
    MW->>WC: switch_to(TASK_EDITOR)
    WC->>TE: ensure_constructed()
    WC->>MW: replace the central region with the Task Editor
    WC->>ST: set("ui.active_workspace", "task_editor")
    WC->>EB: emit _workspace_changed(task_editor)
    MW-->>U: Task Editor visible, in-memory state restored

    U->>MW: click "Benchmark" / click the Running pill
    MW->>WC: switch_to(BENCHMARK)
    alt any buffer dirty
        WC-->>U: Modal Dialog "Save changes to N file(s)?"
        alt Save All
            WC->>TE: save_all()
            WC->>MW: swap to the Benchmark workspace
        else Discard All
            WC->>MW: swap to the Benchmark workspace
        else Cancel
            Note over WC: stay in the Task Editor
        end
    else no buffer dirty
        WC->>MW: swap to the Benchmark workspace
    end
    WC->>EB: emit _workspace_changed(benchmark)
```

`Save All` writes only files free of hard errors. A dirty file with a hard error cannot be saved; the dialog reports it and the switch is held until the user resolves or discards.

## 2. Open a file

```mermaid
sequenceDiagram
    actor U as User
    participant TE as TaskEditor
    participant TC as TaskEditorController
    participant TFL as TaskFileLoader
    participant TFV as TaskFileValidator

    U->>TE: "Open File" / drop a .yaml file
    TE->>TC: open_path(path)
    alt path already open
        TC->>TE: focus the existing buffer
    else not open
        TC->>TFL: load_tasks(path)
        alt malformed YAML or unsupported extension
            TFL-->>TC: parse failure
            TC->>TE: add the file with the error glyph and a banner
        else parsed
            TFL-->>TC: list of BenchmarkTask records (bad tasks skipped)
            TC->>TFV: validate_file(path)
            TFV-->>TC: ValidationReport
            TC->>TE: open the buffer (tasks plus the report)
            TE-->>U: file listed in the Files pane, first task selected
        end
    end
```

The editor runs two passes. The **Task File Loader** is loader-tolerant — the same parse the Benchmark Pipeline uses; tasks with missing required fields are skipped. The **Task File Validator** is editor-strict — it re-reads the raw YAML and emits per-row diagnostics, including "this task would be dropped by the loader", which is what powers the error badges.

## 3. Create a new file

```mermaid
sequenceDiagram
    actor U as User
    participant TE as TaskEditor
    participant TC as TaskEditorController
    participant NP as NativePickers
    participant FMT as YamlFormatter

    U->>TE: click "New File" on the toolbar
    TE->>TC: request_new_file()
    TC->>NP: save_file (filename plus destination folder)
    Note over NP: pre-fills the currently open folder, else ui.task_editor_last_folder
    alt user cancels
        NP-->>TC: cancelled
        Note over TC: no file created
    else user confirms
        NP-->>TC: chosen path
        TC->>FMT: write the seed scaffold (one task) atomically
        FMT-->>TC: file written
        TC->>TE: open the file as a buffer
        TE-->>U: file open, task_id / question / golden_answer flagged as hard errors
    end
```

The file exists on disk the moment New File completes. There is never an untitled in-memory file; unsaved edits to an already-created file are tracked normally as dirty state.

## 4. Add a task

```mermaid
sequenceDiagram
    actor U as User
    participant TE as TaskEditor
    participant TC as TaskEditorController

    U->>TE: click "Add task" in the Tasks-pane footer
    TE->>TC: add_task(file)
    TC->>TC: id = "<stem>_new_<N>", N = 1 + count of existing _new_ ids
    TC->>TE: append a blank task, mark the file dirty
    TE-->>U: select the new row, focus the task_id field
```

## 5. Duplicate a task

```mermaid
flowchart TD
    A[User clicks Duplicate in the Tasks-pane footer] --> B{a task is selected?}
    B -- no --> N([no-op])
    B -- yes --> C[Clone the task record]
    C --> D[New task_id = original + _copy<N>, unique in file]
    D --> E[Insert the clone below the original]
    E --> F[Mark the file dirty]
    F --> G[Select the clone, focus its task_id field]
```

## 6. Validation cascade

```mermaid
sequenceDiagram
    actor U as User
    participant FR as FieldRow
    participant VC as ValidationCascade
    participant TE as TaskEditor

    U->>FR: type into a field
    FR->>FR: reset the field debounce timer
    Note over FR: 250 ms after the last keystroke, or on focus loss, or on a chip change
    FR->>VC: validate_field(field)
    VC-->>FR: field-level diagnostics
    FR-->>U: field strip clean / info / warning / error
    VC->>VC: aggregate the task badge from the field badges plus task rules
    VC->>VC: aggregate the file badge from the task badges plus file rules
    VC->>VC: re-run the duplicate task_id check on a task_id change
    VC-->>TE: ValidationReport for the file
    TE-->>U: update the Files pane, Tasks pane, and toolbar pill badges
    TE->>TE: enable Save if the file badge is not error, else disable it
```

The cascade and its debounce timing, severity aggregation, and Save gating are specified in `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`.

## 7. Save and Save All

```mermaid
sequenceDiagram
    actor U as User
    participant TE as TaskEditor
    participant VC as ValidationCascade
    participant FMT as YamlFormatter
    participant EB as EventBus

    U->>TE: click "Save" / "Save All" on the toolbar
    loop each target file (one for Save, every dirty file for Save All)
        TE->>VC: file validation state
        alt file has a hard error
            VC-->>TE: error
            TE-->>U: skip the file (toast "Cannot save <name> - N errors")
        else clean or warnings only
            VC-->>TE: ok
            TE->>FMT: serialize and atomically write (temp file then rename)
            alt write fails
                FMT-->>TE: SaveFailed (disk full, permission denied)
                TE-->>U: Error Dialog, the file stays dirty
            else write succeeds
                FMT-->>TE: ok
                TE->>EB: emit _task_file_changed(path)
                TE->>EB: emit _global_message "Saved <name>"
                TE-->>U: the file badge clears its dirty marker
            end
        end
    end
```

`_task_file_changed` lets the New Benchmark task-files panel recount tasks in the saved file and clear its stale dirty marker, and lets the Resume Benchmark widget refresh runs whose snapshot referenced that path.

## 8. Drag-drop a file or folder

```mermaid
sequenceDiagram
    actor U as User
    participant TE as TaskEditor
    participant TC as TaskEditorController

    U->>TE: drag a .yaml file or a folder over the workspace
    TE->>TE: accept the proposed drop action
    U->>TE: drop
    alt single file
        TE->>TC: open_path(path)
    else multiple files
        TE->>TC: open_path for each .yaml / .yml file
    else folder
        TE->>TC: scan the folder top level
        TC->>TC: open_path for each .yaml / .yml file found at the top level
    end
    TE-->>U: files added to the Files pane
```

A dropped folder is equivalent to Open Folder — only the top-level task files are loaded, and the Files pane shows the "Showing top-level task files only" line. A dropped file already open focuses the existing buffer rather than opening a duplicate.

## 9. External file changed on disk

```mermaid
sequenceDiagram
    participant FW as FileSystemChangeWatcher
    participant TE as TaskEditor
    actor U as User

    FW-->>TE: file changed at path
    TE->>TE: read the on-disk content, compare with the in-memory model
    alt content differs
        TE->>TE: mark the file row with the reload-pending glyph and a conflict banner
        U->>TE: pick "Reload"
        TE->>TE: re-parse and re-validate
        TE-->>U: banner cleared
    else content identical
        Note over TE: nothing to do
    end
    Note over U,TE: alternatively the user picks "Keep my edits": the banner is dismissed and the next Save overwrites the on-disk file
```

## 10. Open in Task Editor from the Benchmark workspace

```mermaid
sequenceDiagram
    actor U as User
    participant NB as TaskFilesPanel
    participant WC as WorkspaceController
    participant TE as TaskEditor
    participant MW as MainWindow

    U->>NB: select one or more rows in the Task Files list
    U->>NB: click "Open in Task Editor"
    NB->>WC: switch_to(TASK_EDITOR, open_paths)
    WC->>TE: ensure_constructed()
    WC->>TE: open_paths(selected_paths)
    WC->>MW: swap the central region to the Task Editor
    TE-->>U: Task Editor active, the selected files open and focused
```

## 11. Saving a file in use by a running benchmark

```mermaid
sequenceDiagram
    actor U as User
    participant TE as TaskEditor
    participant RR as RunRegistryStore
    participant VC as ValidationCascade
    participant FMT as YamlFormatter

    Note over TE: the user opens a file whose path is in the active run's task list
    TE->>RR: active run task paths
    RR-->>TE: list of paths
    TE->>TE: mark the file row with the in-use banner
    U->>TE: edit a task and click "Save" on the toolbar
    TE-->>U: Modal Dialog "A running benchmark is reading this file. The run already cached its tasks at run-start, so this save will not affect it. Continue?"
    alt Save Anyway
        TE->>VC: file validation state
        TE->>FMT: serialize and atomically write
    else Defer
        TE-->>U: edits retained, the file stays dirty until the run completes
    end
```

The Benchmark Pipeline reads task files once at run-start and caches the parsed list, so a mid-run save never affects tasks already scheduled. The dialog exists only to make that guarantee explicit to the user.
