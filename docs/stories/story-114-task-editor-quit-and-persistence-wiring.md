---
id: STORY-114
title: Wire the Task Editor into the quit sequence and give its persisted settings their writers
status: draft
spec_clauses:
  - 09_Task_Editor/description.md#37-leave-confirmation-and-quit-confirmation
  - 09_Task_Editor/description.md#6-persistence
  - 08_Cross_Cutting/08-M_app_lifecycle.md#7-quit-sequence
  - 09_Task_Editor/description.md#EC-TE-11
modules:
  - ui/task_editor/
  - ui/main_window/
acceptance_criteria:
  - STORY-114-AC-1
  - STORY-114-AC-2
  - STORY-114-AC-3
  - STORY-114-AC-4
  - STORY-114-AC-5
  - STORY-114-AC-6
edge_cases:
  - EC-TE-11
depends_on:
  - STORY-068
  - STORY-069
  - STORY-080
adrs:
  - ADR-0010
owner: coder
estimate: M
---

# STORY-114 — Wire the Task Editor into the quit sequence and give its persisted settings their writers

## Goal

Stop the application from silently throwing away a user's unsaved task-file edits when they quit.
Today the quit sequence asks about unsaved changes only if something tells it how many dirty
buffers exist, and nothing does — the count is hard-wired to zero, so the prompt can never appear
and every unsaved edit is lost without a word. This story connects the Task Editor's real buffer
state to that prompt, makes "Save all" actually write the files, and gives the Task Editor's two
persisted settings — the last folder the user opened and the workspace they were last in — the
writers the specification says they should have but which no code supplies.

## In scope

- **The real dirty-buffer count.** The Task Editor exposes the number of open buffers with unsaved
  edits on its public surface; the composition root injects that supplier into the main window
  factory's `dirty_buffer_count` parameter (added by STORY-080), so the unsaved-changes prompt
  reports the true count and appears exactly when there are unsaved edits.
- **The real save-all implementation.** The Task Editor exposes a save-all operation that writes
  every dirty buffer that has no hard validation error, and reports back which dirty buffers could
  not be saved because they still hold a hard error. The composition root injects it into the main
  window factory's `save_all_buffers` parameter (added by STORY-080).
- **Holding the quit when a dirty file cannot be saved.** Per §3.7, a dirty file with an unresolved
  hard error cannot be saved; the dialog reports it by name and the quit is held so the user can
  resolve or discard it, rather than the quit proceeding and losing that file's edits.
- **`ui.task_editor_last_folder` gets a writer.** The Task Editor persists it through its gateway
  whenever a file or folder is opened or created, so the Open and New File pickers pre-fill with
  the user's last location on the next launch. The setting key already exists in the settings
  registry and in `TaskEditorGateway.set_workspace_setting`; nothing calls it.
- **`ui.active_workspace` gets its on-switch writer.** `MainWindowController` already handles the
  workspace-changed event and already holds `MainWindowGateway.set_active_workspace(...)`; this
  story has that handler persist the new workspace on every switch, so the setting survives a crash
  rather than only a clean quit.

## Out of scope

- **The quit-confirmation dialog and its three choices** — already built by STORY-053
  (`ui/main_window/_internal/close_handler.py`). This story supplies the two callables that dialog
  consumes; it does not change the dialog.
- **The `dirty_buffer_count` / `save_all_buffers` parameters on `make_main_window` and
  `CloseHandler`** — added by STORY-080. This story injects real implementations into parameters
  that already exist.
- **The ordered shutdown, the WAL checkpoint, the crash-recovery sweep, and the quit-time
  `ui.active_workspace` write** — all owned by STORY-080. This story adds only the *on every
  switch* write that the Task Editor's own persistence table requires in addition.
- **The leave-confirmation on a workspace switch away from a dirty Task Editor.** §3.7 covers both
  the switch and the quit with one dialog; this story wires the quit half only, because that is the
  half whose absence silently destroys data at process exit. The switch half stays with the Task
  Editor's own workspace-switch handling and is named here as a known remaining gap.
- **The general save-failure path (disk full, permission denied — EC-TE-10)** — that belongs to the
  Task Editor's ordinary Save action, not to the quit sequence, and no story owns it yet.
- **The YAML formatter, the task-file validator, and the validation cascade** — consumed through
  their existing Protocols.

## Spec inputs

- `09_Task_Editor/description.md#37-leave-confirmation-and-quit-confirmation` — when the user quits
  while any buffer is dirty, a modal asks "Save changes to N file(s)?" with three choices: Save All
  saves every dirty file with no hard error and then proceeds; a dirty file that still has a hard
  error cannot be saved, the dialog reports it, and the quit is held until the user resolves or
  discards it; Discard All proceeds without saving and the unsaved edits are lost; Cancel stays in
  the Task Editor and nothing is saved or discarded.
- `09_Task_Editor/description.md#6-persistence` — the persistence table's write triggers:
  `ui.active_workspace` is written **on every workspace switch** and restored on launch;
  `ui.task_editor_last_folder` is written **when a file or folder is opened or created** and
  pre-fills the Open and New File pickers. Open buffers, the active file, the selected task and the
  preview-shown flag are in-memory only and are deliberately *not* persisted across a restart.
- `08_Cross_Cutting/08-M_app_lifecycle.md#7-quit-sequence` — the unsaved-changes confirmation is
  quit step 3, shown after the running-benchmark confirmation when both apply; "Save all" writes
  every unsaved task file, "Discard all" proceeds without saving, and Cancel aborts the quit
  entirely.
- `09_Task_Editor/description.md#EC-TE-11` — when the application quits with dirty buffers while a
  run is in progress, the §3.7 quit-confirmation dialog is shown, the run continues independently
  of the editor, and quitting follows the standard application-shutdown flow once the dialog
  resolves.

## Design constraints

- The Task Editor controller depends only on its `TaskEditorGateway` Protocol plus the non-store
  helpers it already holds (`EventBus`, `TaskFileLoader`, `NativePickers`, `FileSystemActions`,
  `FileChangeWatcher`, `YamlFormatter`, the validation cascade) — it never holds a persistence
  store directly (D-R-06).
- **The two quit callables cross the boundary as plain callables, not as a Protocol the main window
  imports.** `ui/main_window/` must not import `ui/task_editor/`; the composition root reads the
  Task Editor's public surface and injects two plain callables into `make_main_window`, exactly as
  it already does for the Settings-open and About-open callbacks.
- **Save-all reports failures as data, never as an exception.** A dirty file that cannot be saved
  because it still holds a hard error is an ordinary, expected outcome, so it comes back as a value
  the quit path inspects — not a raised error and not an `icontract` violation.
- `ui.active_workspace` is persisted from `MainWindowController`'s existing workspace-changed
  handler, which already holds `MainWindowGateway`. Do not add a settings collaborator to
  `adapters/workspace_controller/` — it would duplicate a write path that already has a natural
  home and would reopen a module nothing else in this story touches.
- No `setStyleSheet`, no colour literal, no `asyncio` in either module.

## Acceptance criteria

### STORY-114-AC-1

Given the Task Editor holds three buffers of which two have unsaved edits, when the user requests a
quit, then the unsaved-changes confirmation is shown and reports two files.

### STORY-114-AC-2

Given the Task Editor holds dirty buffers and none of them has a hard validation error, when the
user chooses "Save all" at the quit confirmation, then every dirty buffer is written to its file on
disk and the quit proceeds.

### STORY-114-AC-3

Given the Task Editor holds two dirty buffers of which one still has a hard validation error, when
the user chooses "Save all" at the quit confirmation, then the error-free buffer is written, the
quit is held rather than proceeding, and the file that could not be saved is named to the user.

### STORY-114-AC-4

Given the Task Editor holds dirty buffers, when the user chooses "Discard all" at the quit
confirmation, then no task file on disk is modified and the quit proceeds.

### STORY-114-AC-5

Each of the Task Editor's two persisted settings is written at its specified trigger:

| Setting                      | Trigger                                       | Written value                   |
| ---------------------------- | --------------------------------------------- | ------------------------------- |
| `ui.task_editor_last_folder` | A file is opened                              | The opened file's parent folder |
| `ui.task_editor_last_folder` | A folder is opened                            | The opened folder               |
| `ui.task_editor_last_folder` | A new file is created                         | The new file's parent folder    |
| `ui.active_workspace`        | The active workspace changes to `task_editor` | `task_editor`                   |
| `ui.active_workspace`        | The active workspace changes to `benchmark`   | `benchmark`                     |

### STORY-114-AC-6

Given a benchmark run is in progress and the Task Editor holds dirty buffers, when the user quits
and both confirmations resolve toward quitting, then the Task Editor issues no run-control call —
no pause, no stop, no cancel — and the quit proceeds through the standard shutdown path (EC-TE-11).

## Test plan

- STORY-114-AC-1 — integration, `tests/integration/test_task_editor_quit_integration.py`,
  `test_unsaved_prompt_reports_the_real_dirty_buffer_count`.
- STORY-114-AC-2 — integration, same file, `test_save_all_writes_every_clean_dirty_buffer`.
- STORY-114-AC-3 — integration, same file, `test_save_all_holds_the_quit_when_a_file_has_a_hard_error`.
- STORY-114-AC-4 — integration, same file, `test_discard_all_writes_nothing_and_quits`.
- STORY-114-AC-5 — unit (`pytest-qt`, table-driven, one `@pytest.mark.parametrize` row per trigger,
  with a recording fake gateway), colocated
  `src/ollama_llm_bench/ui/task_editor/tests/test_persistence_writes.py` for the three
  `ui.task_editor_last_folder` rows and
  `src/ollama_llm_bench/ui/main_window/_internal/tests/test_controller.py` for the two
  `ui.active_workspace` rows, both named `test_setting_written_per_trigger`.
- STORY-114-AC-6 — integration, `tests/integration/test_task_editor_quit_integration.py`,
  `test_quit_with_dirty_buffers_during_a_run_never_touches_run_control`. Covers EC-TE-11.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-114.
- [ ] EC-TE-11 has a passing test.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/task_editor/` and
  `ui/main_window/`.
- [ ] An architecture test confirms `ui/main_window/` does not import `ui/task_editor/`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.

## Notes

- **Why this is a separate story from STORY-080.** STORY-080 already sits at the `L` ceiling
  (four modules, eight acceptance criteria) for the ordered shutdown and the crash-recovery sweep.
  Folding the Task Editor work into it would take it to five modules and ten-plus criteria — the
  hard ceiling — and well past what one coding session can carry. The split is also a clean seam:
  STORY-080 delivers and proves the two injection points with test-supplied callables; this story
  supplies the real implementations behind them and changes nothing about the shutdown itself.
- **Why neither STORY-068 nor STORY-069 can absorb this.** Both are `done`, and a `done` story is
  never re-edited to take on new scope — a change to work a `done` story covers requires a new
  story. STORY-068's own notes hand the "leave/quit/close/reload/in-use/save-failure confirmation
  dialogs" to STORY-069, and STORY-069 delivered the Task Editor's own dialogs but never wired the
  application-level quit hook, because that hook (`CloseHandler`'s `dirty_buffer_count` parameter)
  lives in `ui/main_window/` and had no injection path until STORY-080 adds one. This story is that
  missing link, not a re-opening of either.
- **`EC-TE-10` (a Save fails from disk full, permission denied, or a removed directory) has no
  owning story anywhere.** It is deliberately left out of this story's scope — it is a property of
  the Task Editor's ordinary Save action rather than of the quit path — but it will show as an
  uncovered edge case in `just trace-check` until some story claims it. Flagged here so it is not
  mistaken for fallout from this story.
- **The leave-confirmation half of §3.7 (switching workspace away from a dirty Task Editor) is
  still unowned.** This story covers only the quit half. The switch half loses no data at process
  exit — the buffers survive a workspace switch in memory per §6 — which is why it is the lower
  priority of the two, but it is a real remaining gap in §3.7's coverage.
  </content>
