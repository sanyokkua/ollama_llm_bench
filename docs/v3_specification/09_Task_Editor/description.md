# Task Editor

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `09_Task_Editor/field_reference.md`, `09_Task_Editor/state_machine.md`, `09_Task_Editor/flow_diagram.md`, `09_Task_Editor/implementation_structure.md`, `09_Task_Editor/mockup.html`, `10_Domain_and_Data/04_YAML_TASK_FORMAT.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `11_Services_and_Algorithms/12_YAML_FORMATTER.md`, `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `01_Main_Window/description.md`

The Task Editor is the application's second workspace: a full-window workspace for creating and editing benchmark task YAML files. It replaces the Benchmark workspace layout when active, presenting a Files pane, a Tasks pane, a structured Field-editor pane, and an optional raw-YAML preview, all wired to inline validation and atomic, comment-preserving saves. Every editor action is exposed as a toolbar button, pane control, or context-menu item — the workspace is operated by mouse only. This document is the primary specification for the workspace: its layout, the behaviour of every control, validation gating, persistence, event-bus integration, edge cases, and the complete inventory of callable behaviours.

---

## Table of Contents

1. Role and ownership
2. Layout
3. Behaviour per element
4. Validation rules
5. State transitions
6. Persistence
7. Event-bus integration
8. Service dependencies
9. Edge cases
10. Function inventory

---

## 1. Role and ownership

The Task Editor owns the lifecycle of benchmark task files on disk: opening them, presenting their tasks for structured editing, validating them against the schema, and writing them back. It is one of the two workspaces hosted by the Main Window; the other is the Benchmark workspace. The Workspace Controller swaps the Main Window's central region between the two; the Menu Bar and Status Bar persist across the swap.

The Task Editor **is responsible for**:

- Loading, displaying, and editing `.yaml` / `.yml` task files in a three-pane workspace.
- Per-field structured editing of every `BenchmarkTask` field, with inline validation and per-field help.
- Running the validation cascade (`11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`) and gating Save on hard errors.
- Writing files back through the YAML Formatter (`11_Services_and_Algorithms/12_YAML_FORMATTER.md`) — atomic, canonically ordered, comment-preserving.
- Showing a read-only raw-YAML preview of the file that Save would write.
- Announcing every save through the Event Bus so the Benchmark workspace stays consistent.

The Task Editor **is not responsible for**:

- Running benchmarks or reading task files for execution — the Benchmark Pipeline owns that and reads task files only at run-start.
- Defining the YAML schema or the per-field rules — those are owned by `10_Domain_and_Data/04_YAML_TASK_FORMAT.md` and this folder's `field_reference.md`.
- Serializing YAML — the YAML Formatter is the single writer of task files.
- Editing the YAML text directly — the raw-YAML view is read-only; all editing is form-driven.
- Persisting tasks to the database — task files live only on disk; the database stores per-run task snapshots, not the source files.

The workspace is fully usable while a benchmark is running. The pipeline cached its task list at run-start, so edits made here never affect a run already in progress (see §9, EC-TE-07).

## 2. Layout

The Task Editor occupies the entire Main Window central region. The Menu Bar (workspace switcher, Settings, About) sits above it and the Status Bar below it; both belong to the Main Window and persist across workspace switches. The mockup is `09_Task_Editor/mockup.html`.

```
+-------------------------------------------------------------------------------+
| Settings  About   [ Benchmark | (*) Task Editor ]   (*) Running: <run>  v1.0  |  Menu Bar
+-------------------------------------------------------------------------------+
| [Open File] [Open Folder] [New File] | [Save] [Save All] [Reload] [View YAML] |  Editor Toolbar
|                                                       (validation pill)       |
+-------------------------------------------------------------------------------+
| FILES (240px)   | TASKS (300px)        | FIELD EDITOR (flex, min 480px)        |
|                 |                      |                                       |
| top-level YAML  | per-task validation  | structured field rows for the         |
| files; per-file | badge; add /         | selected task, grouped; inline        |
| validation badge| duplicate / remove / | validation strips and help icons      |
| and dirty mark  | reorder controls     |                                       |
+-------------------------------------------------------------------------------+
| <editor status: N tasks across M files, K dirty, last saved HH:MM>            |  Status Bar
+-------------------------------------------------------------------------------+
```

### 2.1 Pane proportions

| Pane | Default width | Minimum width | Role |
|---|---|---|---|
| Files | 240 px | 200 px | Open task files; per-file validation badge and dirty marker; context menu. |
| Tasks | 300 px | 240 px | Tasks of the active file; per-task validation badge; add / duplicate / remove / reorder. |
| Field editor | flexible | 480 px | Structured per-field editor for the selected task. |
| YAML preview | 430 px | 360 px | Read-only raw-YAML side panel; shown only when toggled (§3.5). When shown it occupies the right edge and the Field editor shrinks to accommodate it. |

Splitter positions are persisted (§6). When the YAML preview is shown, the splitter set is `Files | Tasks | Field editor | YAML preview`; when hidden it is `Files | Tasks | Field editor`.

### 2.2 Workspace states

The editor has three top-level visual states, each documented in `09_Task_Editor/state_machine.md`:

| State | Trigger | Appearance |
|---|---|---|
| Empty | No files open. | The three-pane body is replaced by a centred drop target ("Drop YAML files or folders here") plus the toolbar buttons and a recent-files list (§2.3). |
| With files | At least one file open. | The three-pane body is shown; one file is active and one of its tasks is selected. |
| With files, preview shown | YAML preview toggled on while files are open. | The four-pane body is shown. |

### 2.3 Recent-files list (Empty state)

Below the drop target, the Empty state shows a **Recent files** list of the most recently opened task files, so the user can reopen a file without re-navigating a picker.

- **Data source.** The list is **session view state**, not a persisted setting — there is no `task_editor.recent_files` key in `08_Cross_Cutting/08-G_feature_flags.md`, and the editor's open buffers are in-memory only (§6). The recent-files list is held in memory by the controller for the lifetime of the session and is **not** restored across an application restart; on a fresh launch the list is empty until the first file is opened. (The only persisted picker state is the default folder `ui.task_editor_last_folder`, which pre-fills the Open / New File pickers — it is not the recent-files list.)
- **Membership and ordering.** An entry is added whenever a file is opened (via Open File, drag-drop, New File, or a recent-file click) and is the file's path. The list is ordered **most-recent-first** and holds at most **10** entries; opening an 11th file evicts the least-recently-opened entry, and re-opening a file already in the list moves it to the top rather than duplicating it.
- **Empty variant.** When no file has been opened yet this session, the list shows the muted placeholder text `No recent files`.
- **Click behaviour.** Clicking a recent-file entry opens that file as a buffer (identical to Open File on that single path) and moves the editor out of the Empty state into `With files` (`09_Task_Editor/state_machine.md`), with the opened file active. Clicking an entry whose file no longer exists on disk surfaces the standard open-failure toast and removes the stale entry from the list.

### 2.4 Status-bar contents

The Status Bar belongs to the Main Window and persists across workspace switches, but while the Task Editor is active it renders the editor's aggregate state. Its segments, left to right:

- **Editor status (left).** The aggregate sentence `<N> tasks across <M> files · <K> dirty` together with the aggregate validation pill (`Valid` / `<M> warning(s)` / `<M> error(s)`), as shown in the §2 layout template. It mirrors the toolbar validation aggregate (§3.2) and recomputes on every edit, open, close, and Save.
- **Last saved (left, after the editor status).** A `Last saved HH:MM` indicator. Its source is the **active file's** most recent successful Save time (not a global across-all-buffers time); the format is 24-hour local `HH:MM`. It updates whenever the active file is saved (via Save or Save All) and re-reads when the active file changes (selecting a different file shows that file's last-saved time). It is **absent** when the active file has never been saved in this session (a freshly created or just-opened, never-saved buffer) and in the Empty state (no active file).
- **Right region — focused field.** A `Field: <name>` indicator naming the currently focused Field-editor field (for example `Field: question`). Its value is the field key of the focused input in the Field-editor pane; it updates on focus change and clears when no field is focused (for example in the Empty state or while focus is outside the Field-editor pane).
- **Right region — YAML-preview state.** A `YAML preview: on` / `YAML preview: off` indicator reflecting the View YAML toggle (§3.5); it tracks the same `Hidden` / `Shown` state as the toolbar View YAML active-dot and updates whenever the preview is toggled.

## 3. Behaviour per element

### 3.1 Workspace switcher

A Segmented Control rendered in the Menu Bar area, owned by the Main Window, with two options: `Benchmark` and `Task Editor`. It is always visible, in both workspaces, and works while a benchmark is running.

- Clicking the inactive option switches workspaces.
- A switch away from the Task Editor while any buffer is dirty raises the leave-confirmation dialog (§3.7).
- The active workspace is persisted to the setting `ui.active_workspace` and restored on next launch.
- A **Running pill** to the right of the switcher is visible whenever any run is in a non-terminal state. Its label is the run's effective display name. Clicking it switches to the Benchmark workspace and focuses the Progress widget. The pill's presence and label are driven by the `_run_started`, `_run_finished`, `_run_stopped`, `_run_failed`, and `_run_renamed` events.

The Task Editor's in-memory state — every open buffer, the active file, the selected task, scroll positions, the preview-shown flag — is preserved across a workspace switch. Switching to the Benchmark workspace and back restores the editor exactly as left.

### 3.2 Editor Toolbar

The toolbar sits directly below the Menu Bar in the Task Editor workspace. The Main Window Menu Bar carries no File / Edit / View menus (see `01_Main_Window/description.md`); every editor operation is exposed as a toolbar button, a pane control, or a context-menu item. There are no keyboard shortcuts or accelerators.

| Control | Action | Enabled when |
|---|---|---|
| Open File | Opens a File Picker filtered to `*.yaml` / `*.yml`; multi-select allowed. Each chosen file is opened as a buffer. | Always. |
| Open Folder | Opens a Folder Picker, then loads every `.yaml` / `.yml` file at the **top level** of the chosen folder. The Files pane shows them as a flat list with a muted line "Showing top-level task files only"; sub-folders are not traversed. | Always. |
| New File | Opens a Create-File dialog (a Save Picker — filename plus destination folder chosen up front). The file is created on disk immediately with one seeded task (§3.8), then opened as a buffer with a known path. There is never an untitled in-memory file. | Always. |
| Save | Validates the active file and writes it in place via the YAML Formatter. | Active file is dirty and has no hard error. |
| Save All | Saves every dirty file that has no hard error; files with hard errors are skipped and stay dirty. The button label carries a parenthetical dirty-count suffix `Save All (N)`, where `N` is the count of dirty files (the view-model's `ToolbarViewModel.save_all_count`, see `09_Task_Editor/implementation_structure.md` §4). The suffix reads `(0)` when nothing is dirty, in which case the button is disabled. | At least one dirty file has no hard error. |
| Reload | Re-reads the active file from disk. If the file is dirty, a confirmation is shown first. | A file is active. |
| View YAML | Toggles the read-only YAML preview side panel (§3.5). | Always. |
| Validation pill | Right-aligned. Shows the toolbar aggregate validation state across all open files: `N tasks, 0 errors` (green), `N tasks, M warnings` (amber), or `N tasks, M errors` (red). Clicking it focuses the first offending file and task. | Always; shows a muted "no file open" when the editor is empty. |

### 3.3 Files pane

A flat List View of every open task buffer — never a hierarchical tree. When a folder was opened, a muted info line at the top reads "Showing top-level task files only".

Each row shows the filename and a status icon:

| Icon | Meaning |
|---|---|
| Clean glyph | The file is saved and valid (no hard error, no warning). |
| Dirty marker | The file has unsaved edits. |
| Warning glyph | The file has soft warnings (for example empty grading criteria). |
| Error glyph | The file has hard errors (missing required field, duplicate `task_id`, malformed YAML). |
| Reload-pending glyph | The file changed on disk while open and awaits a reload decision. |

The active file is highlighted with the primary-coloured left border. Behaviour:

- Selecting a row makes that file active and loads its tasks into the Tasks pane.
- Drag-drop: dropping `.yaml` / `.yml` files anywhere in the workspace adds them as buffers; dropping a folder behaves as Open Folder.
- Right-click context menu: `Save`, `Save As`, `Close`, `Close Others`, `Reveal in File Manager`, `Reload from Disk`, `Show in Task Files Panel` (switches to the Benchmark workspace and adds the path to the New Benchmark task-files list).
- Closing the active buffer is done through its context-menu `Close` item or its close (X) glyph in the Files-pane row; if it is dirty, the close-confirmation dialog is shown first.
- Footer controls: a footer below the file list carries **Open File**, **Open Folder**, and **New File** buttons. These **mirror the three open/create toolbar buttons** of §3.2 — same actions, same always-enabled gating — and are duplicated here purely for convenience so the user can open or create a file without reaching back to the toolbar. They are the same controls, not additional behaviours.

### 3.4 Tasks pane

For the active file, a List View of its tasks. Each row shows the `task_id` and a per-task validation badge (clean / warning / error), aggregated from the task's field badges and task-level rules per the validation cascade.

- Selecting a row loads that task into the Field editor.
- Multi-select is supported for batch remove and batch duplicate.
- Reorder: drag-to-reorder with the mouse, or the Move Up / Move Down toolbar buttons in the Tasks-pane footer for the selected task. Reordering marks the file dirty.
- Footer controls:
  - **Add Task** appends a blank task at the end, selects it, and focuses its `task_id` field. The generated `task_id` is `<filename_stem>_new_<N>`, where `N` is `1` plus the count of existing ids matching that pattern.
  - **Duplicate** clones the selected task immediately below the original, with `_copy<N>` appended to its `task_id` to keep it unique, then selects the clone and focuses its `task_id` field.
  - **Remove** deletes the selected task(s) after a confirmation.
  - **Move Up / Move Down** reorder the selected task.

### 3.5 Field-editor pane

A vertically scrollable Form rendering every field of the selected task as a Field Row. The per-field meaning, type, requirement, default, validation rules, help text, and examples are the authoritative content of `09_Task_Editor/field_reference.md`; this section specifies the row structure and control behaviour.

The pane head shows `Editing: <task_id>` for the selected task, followed by a **position counter** `(K of N)` — `K` is the selected task's 1-based index within the active file's task list and `N` is the file's total task count (for example `Editing: translation_uk_en_greeting (1 of 3)`). The counter updates as the selection moves up or down the Tasks pane and as tasks are added, duplicated, removed, or reordered. The head also carries the per-task validation pill (`1 warning` / `2 errors`) when the task has diagnostics.

Each Field Row has:

| Element | Description |
|---|---|
| Label | Bold for required fields, normal for optional. A required field carries a red asterisk. |
| Format hint | A muted single line below the label (for example "snake_case, max 80 characters", "ISO 639-1 code"). |
| Help icon | A round info button. Hover or click opens a Popover whose content is rendered from `field_reference.md` — the field meaning, valid values, and an example. |
| Input control | The type-specific control (§3.5.1). |
| Validation strip | A strip at the bottom of the row showing the field's current validation state (clean / info / warning / error) and the reason. |

#### 3.5.1 Input control types

| Field kind | Fields | Control |
|---|---|---|
| Identifier | `task_id` | Single-line input; live uniqueness check within the file. |
| Short free text | `category`, `sub_category`, `source_language`, `target_language` | Single-line input. |
| Long text | `question`, `golden_answer`, `pass_criteria`, `fail_criteria`, `source_material`, `fail_example` | Auto-growing multi-line input; monospace font for `golden_answer`. |
| Closed enum | `difficulty` | Dropdown bound to the `Difficulty` enum members from `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`. |
| Boolean | `cosine_enabled` | Checkbox, default checked (DD-46); unchecked = the cosine phase skips this task. |
| Term lists | `required_terms.exact`, `.semantic`, `.forbidden` | Chip Input — typing plus a comma or clicking the inline "Add" button adds a chip; each chip carries an "x" remove glyph; pasting comma-separated text splits into chips. |

#### 3.5.2 Field grouping and conditional groups

Fields are grouped into collapsible sections. The "Required terms" group holds the three chip inputs; the "Optional context" group holds `fail_example`.

All optional groups are **always available** (DD-46 — with `task_type` retired there is no
conditional driver): "Translation extras" (`source_language`, `target_language`),
"Input material" (`source_material`), and "Optional context" (`fail_example`) are plain
collapsible sections the author fills when relevant. An empty optional field is simply
omitted from the saved YAML.

### 3.6 YAML preview side panel

The toolbar View YAML control toggles a read-only side panel on the right edge. It shows the exact YAML that Save would write — canonical field order and preserved comments, produced by the YAML Formatter in the same configuration Save uses. The preview re-renders on form edits, debounced by 200 ms. A `Copy YAML` control copies the text to the System Clipboard via the OS Adapter. The preview is read-only by design: the round-trip is form-driven, and editing raw YAML in place is out of scope.

### 3.7 Leave-confirmation and quit-confirmation

When the user switches to the Benchmark workspace, or quits the application, while any buffer is dirty, a Modal Dialog asks "Save changes to N file(s)?" with three choices:

- **Save All** — saves every dirty file with no hard error, then proceeds with the switch or quit. A dirty file that still has a hard error cannot be saved; the dialog reports it and the switch or quit is held until the user resolves or discards it.
- **Discard All** — proceeds without saving; all unsaved edits are lost.
- **Cancel** — stays in the Task Editor; nothing is saved or discarded.

### 3.8 New-file seed scaffold

When New File creates a file on disk, the seed content is one task scaffold with the required fields empty and the optional fields at their defaults:

```yaml
schema_version: 1
tasks:
  - task_id: ""
    difficulty: medium
    question: ""
    golden_answer: ""
    pass_criteria: ""
    fail_criteria: ""
    required_terms:
      exact: []
      semantic: []
      forbidden: []
```

The seeded task opens with `task_id`, `question`, and `golden_answer` flagged as hard errors (empty required fields); Save stays disabled until they are filled.

## 4. Validation rules

The Task Editor applies the validation cascade specified in `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`, against the per-field and per-file rules owned by `09_Task_Editor/field_reference.md` and `10_Domain_and_Data/04_YAML_TASK_FORMAT.md`. The cascade has three levels — field, task, file — and three severities.

| Severity | Save behaviour | Badge |
|---|---|---|
| Hard error | Save disabled for the file. | Red. The Files pane row and the Tasks pane row carry the error glyph; the offending field input carries a red border. |
| Soft warning | Save allowed. | Amber. |
| Soft info | Save allowed. | Blue. |

Cascade behaviour the editor depends on:

- Field-level validation runs `task_editor.validation_debounce_ms` (default 250 ms) after the last keystroke, immediately on focus loss, and immediately on a chip add or remove.
- Task-level and file-level validation run synchronously after the level below them completes; the duplicate-`task_id` file rule additionally re-runs whenever any `task_id` field validation completes.
- A level's badge is the maximum severity of everything at or below it. A single hard error therefore propagates to the toolbar pill and disables Save for its file.
- Save is gated per file: a file with no hard error is saveable; a file with any hard error is not. Save All saves only the saveable files.
- An empty file (`tasks: []`) is a soft warning, not an error, and remains saveable.

The hard-error rules that gate Save: empty `task_id`, empty `question`, empty `golden_answer`, duplicate `task_id` within the file, malformed YAML on reload, and a non-`.yaml`/`.yml` extension. The complete rule set and severities are in `field_reference.md`.

## 5. State transitions

Full state diagrams are in `09_Task_Editor/state_machine.md`. Summary:

- **Workspace level** — the Main Window is in either the Benchmark or the Task Editor workspace; a dirty-buffer leave routes through the leave-confirmation choice.
- **Editor level** — `Empty` (no files) and `With files`; opening the first file or creating one moves to `With files`, closing the last file returns to `Empty`.
- **Per-file** — `Loaded`, `Dirty`, `Reloading`, `ParseError`, and `ExternalChanged`; an edit makes a `Loaded` file `Dirty`, a successful Save returns it to `Loaded`, an on-disk change moves it to `ExternalChanged`.
- **Per-file validation** — `Valid`, `Warnings`, `Errors`, recomputed on every edit; only `Errors` disables Save.
- **Per-task** — `New`, `Loaded`, `Dirty`; per-task dirtiness drives only the preview highlight, while file dirtiness gates Save.
- **Per-field validation** — `Clean`, `Info`, `Warn`, `Err`, transitioning on each completed field-level pass.
- **YAML preview** — `Hidden` and `Shown`, toggled by the View YAML control.

## 6. Persistence

| State | Stored where | When written | When restored |
|---|---|---|---|
| Active workspace | Setting `ui.active_workspace` | On every workspace switch. | On launch — the app opens in the last workspace. |
| Default Open / New folder | Setting `ui.task_editor_last_folder` | When a file or folder is opened or created. | Pre-fills the Open and New File pickers. |
| Auto-format on save | Setting `task_editor.auto_format_on_save` (default `true`) | In the Settings dialog. | Read on Save and on `_app_settings_changed`. |
| Warn on empty grading criteria | Setting `task_editor.warn_on_empty_grading_criteria` (default `true`) | In the Settings dialog. | Read by the validation cascade. |
| Validation debounce | Setting `task_editor.validation_debounce_ms` (default `250`) | In the Settings dialog. | Read by the validation cascade. |
| Splitter positions | Window-geometry settings | On splitter drag. | On entering the workspace. |

Open buffers, the active file, the selected task, and the preview-shown flag are **in-memory only**. They survive a workspace switch within a session but are not persisted across an application restart; the editor opens empty on a fresh launch unless the recent-files list is used.

The setting keys are catalogued in `08_Cross_Cutting/08-C_settings_hierarchy.md`.

## 7. Event-bus integration

All subscriptions use ownership-binding (`08_Cross_Cutting/08-J_event_bus_catalog.md` §2): each is bound to the Task Editor's lifetime and auto-cancelled when the workspace controller is destroyed.

**Subscribes to:**

| Event | Reason |
|---|---|
| `_app_settings_changed` | Refresh `auto_format_on_save`, the default folder, the warn-on-empty toggle, and the validation debounce. |
| `_run_started` | Show the Running pill in the workspace switcher; mark file rows whose path is in the run's task list as in-use (§9, EC-TE-07). |
| `_run_finished` / `_run_stopped` / `_run_failed` | Hide the Running pill; clear in-use markers. |
| `_run_renamed` | Refresh the Running pill label. |
| `_workspace_changed` | Resume the workspace: restore in-memory state when the editor becomes active. |

**Emits:**

| Event | When | Payload |
|---|---|---|
| `_task_file_changed` | After every successful Save of a file. | `TaskFileChangedEvent` — the saved file path. |
| `_workspace_changed` | On every workspace switch involving the Task Editor. | `WorkspaceChangedEvent`. |
| `_global_message` | On a save success ("Saved <filename>") and on a save failure. | `GlobalMessageEvent` — surfaced as a Status Bar toast. |

`_task_file_changed` lets the New Benchmark task-files panel recount tasks in the changed file and clear any stale dirty marker, and lets the Resume Benchmark widget refresh runs whose snapshot referenced that path. Both events route on the Event Bus with the threading rule `UI → UI` and coalescing `none`.

## 8. Service dependencies

The Task Editor's factory receives these dependencies as constructor parameters (Protocols; see `09_Task_Editor/implementation_structure.md` for the contracts):

| Dependency | Used for |
|---|---|
| Task File Loader | Loader-tolerant parse of a file into `BenchmarkTask` records on open. |
| Task File Validator | Editor-strict per-row diagnostics that power the validation badges. |
| YAML Formatter | The single writer of task files — canonical order, comment preservation, atomic save. |
| Validation cascade service | The three-level field / task / file cascade and Save gating. |
| Settings store | Reads and writes the workspace's settings keys (§6). |
| Event Bus | Subscriptions and emissions in §7. |
| Workspace store | Holds the current workspace as reactive state. |
| OS Adapter | File pickers, "Reveal in File Manager", clipboard write for Copy YAML, atomic temp-then-rename file operations. |
| File-System Change Watcher | Detects an open file changing on disk and raises the conflict banner. |
| Run-registry store | Reads the active run's task paths to mark in-use files (§9, EC-TE-07). |

## 9. Edge cases

| ID | Description | Handling |
|---|---|---|
| EC-TE-01 | A task file is malformed YAML on open. | The Task File Loader fails to parse; the file is added to the Files pane with the error glyph and a banner "This file is not valid YAML and cannot be edited"; the Field editor shows the parse error location; Save is disabled. The user must fix the file externally and Reload. |
| EC-TE-02 | Two tasks share the same `task_id` within a file. | A file-level hard error reported on every row sharing the id; both Tasks pane rows carry the error glyph and the `task_id` field strip explains the conflict; Save disabled until one id is changed. |
| EC-TE-03 | A task is missing a required field. | A field-level hard error on the empty `task_id`, `question`, or `golden_answer`; the field strip names the rule; the task and file badges aggregate to error; Save disabled. |
| EC-TE-04 | A task contains the retired `task_type` key (legacy file). | A soft warning on the task strip ("`task_type` is retired and ignored — DD-46"); the key is dropped on the next save; Save allowed. |
| EC-TE-05 | A task has an invalid `difficulty`. | The validator falls back to the default (`medium`) and shows a soft warning on the field; Save allowed. The editor's dropdown only offers valid members, so this arises only for files edited externally. |
| EC-TE-06 | A file changes on disk while open in the editor. | The File-System Change Watcher detects the change; the file's row gets the reload-pending glyph and a banner "This file changed on disk. [Reload] [Keep my edits]". Reload re-parses and re-validates; Keep my edits dismisses the banner and the next Save overwrites the on-disk version. |
| EC-TE-07 | The user saves a file currently being read by a running benchmark. | When a run is active, files whose path is in the run's task list carry an in-use banner. On Save of such a file, a Modal Dialog warns "A running benchmark is reading this file. The running benchmark already cached its tasks at run-start, so this save will not affect it. Continue?" with Save Anyway and Defer. Defer keeps the edits and leaves the file dirty until the run completes. |
| EC-TE-08 | The Open Folder picker selects a folder with no `.yaml` / `.yml` files. | No buffers are added; the Files pane stays in its current state; a Status Bar toast reports "No task files found in that folder". |
| EC-TE-09 | The user reloads a dirty file. | A confirmation dialog warns that unsaved edits will be lost; on confirm the file is re-read and re-validated; on cancel nothing changes. |
| EC-TE-10 | A Save fails (disk full, permission denied, directory removed). | The YAML Formatter reports a typed save failure; an Error Dialog explains the OS reason; the buffer stays dirty so the user can retry; the on-disk file is byte-for-byte unchanged. |
| EC-TE-11 | The application quits with dirty buffers while a run is in progress. | The quit-confirmation dialog (§3.7) is shown; the run continues independently of the editor, and quitting follows the standard application-shutdown flow once the dialog resolves. |
| EC-TE-12 | The YAML preview is requested for a task with a hard error. | The preview still renders the YAML the Formatter would produce (the Formatter always emits syntactically valid YAML); the preview header notes "Preview only — Save is disabled while this file has errors". |
| EC-TE-13 | A file declares a `schema_version` newer than the build understands. | The Task File Loader rejects the file; it is shown with the error glyph and a banner "Written by a newer version of the application"; Save is disabled. |
| EC-TE-14 | A file is loaded in bare-sequence (Form B) or single-mapping (Form C) shape. | The loader converts it to canonical Form A in memory; the editor edits it normally; the first Save rewrites the file as Form A. |
| EC-TE-15 | A file or task carries an unknown YAML key. | The key is preserved verbatim through the round-trip; a soft-info notice is shown; the key is never dropped and never a hard error. |

## 10. Function inventory

A flat list of every callable behaviour for tester traceability. Each line names the action, what it does, and what gates it.

| Action | Description | Gate |
|---|---|---|
| Enter Task Editor workspace | Make the Task Editor the active workspace. | Always; updates `ui.active_workspace`. |
| Leave Task Editor workspace | Switch to the Benchmark workspace. | If any buffer is dirty: leave-confirmation dialog. |
| Open File | File Picker for `.yaml` / `.yml`; opens chosen files as buffers. | Always. |
| Open Folder | Folder Picker; loads top-level task files as a flat list. | Always; EC-TE-08 if the folder has none. |
| New File | Create-File dialog, create file on disk with the seed scaffold, open it. | Always; no untitled in-memory file is created. |
| Save | Validate then atomically write the active file via the YAML Formatter. | Active file dirty and free of hard errors. |
| Save All | Save every dirty file free of hard errors; skip the rest. | At least one dirty file free of hard errors. |
| Reload from Disk | Re-read and re-validate the active file. | A file is active; confirmation if dirty. |
| Close File | Close the active buffer. | A file is active; close-confirmation if dirty. |
| Toggle YAML preview | Show or hide the read-only YAML side panel. | Always. |
| Copy YAML | Copy the preview text to the System Clipboard. | The YAML preview is shown. |
| Add Task | Append a blank task and focus its `task_id`. | A file is active. |
| Duplicate Task | Clone the selected task with a unique `_copy<N>` id. | A task is selected. |
| Remove Task | Delete the selected task(s) after confirmation. | At least one task selected. |
| Move Task Up / Down | Reorder the selected task. | A task is selected. |
| Validate File | Re-run the validation cascade for the active file. | A file is active. |
| Reveal in File Manager | Open the file's folder in the OS file manager. | A file is selected and exists on disk. |
| Show in Task Files Panel | Switch to the Benchmark workspace and add the path to New Benchmark's task files. | A file is selected. |
| Edit a field | Change a field value; trigger the validation cascade. | A task is selected. |
| Add / remove a term chip | Add or remove a chip in a `required_terms` list. | A task is selected. |
| Drag-drop a file or folder | Add dropped `.yaml` / `.yml` files, or open a dropped folder. | Always. |
| Open in Task Editor (from New Benchmark) | Cross-workspace open of the paths selected in the Benchmark workspace. | At least one path selected in New Benchmark task files. |
| Respond to external change | Reload or keep edits when a file changes on disk. | The file changed on disk while open (EC-TE-06). |
