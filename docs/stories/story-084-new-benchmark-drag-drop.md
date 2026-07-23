---
id: STORY-084
title: Complete drag-and-drop of task files onto the New Benchmark task-files list
status: draft
spec_clauses:
  - 02_New_Benchmark_Widget/description.md#43-task-files--task-benchmark-and-graded-benchmark
  - 02_New_Benchmark_Widget/description.md#5-behaviour-per-element
modules:
  - ui/new_benchmark/
acceptance_criteria:
  - STORY-084-AC-1
  - STORY-084-AC-2
  - STORY-084-AC-3
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: S
---

# STORY-084 — Complete drag-and-drop of task files onto the New Benchmark task-files list

## Goal

Finish the New Benchmark task-files drag-and-drop. The widget already sets `setAcceptDrops(True)` but
has no `dragEnterEvent`/`dropEvent` handlers, so dropping YAML task files or folders does nothing.
The specification requires the task-files list (both its empty drop zone and its populated state) to
accept dragged YAML files and folders in Task Benchmark and Graded Benchmark modes, parse them, and
append rows. This story wires the two handlers, matching the behaviour the Add File / Add Folder
buttons already provide, and corrects the stale module docstring that still claims the parts are
"stubbed".

## In scope

- `ui/new_benchmark/_internal/`: implement `dragEnterEvent` to accept a drag carrying local YAML
  files or folders while the mode is Task Benchmark or Graded Benchmark, and `dropEvent` to hand the
  dropped paths to the Task File Loader and append the resulting rows — the same loader path the Add
  File / Add Folder buttons use.
- Surfacing a malformed dropped file the same way the buttons do: the loader rejects it and an inline
  error is shown without adding a row.
- Correcting the stale `ui/new_benchmark/__init__.py` module docstring that claims parts are stubbed.

## Out of scope

- The Task Editor's own drag-and-drop — already delivered; this story reuses its pattern but does not
  change it.
- The Task File Loader / validator themselves — already delivered (STORY-031); this story only routes
  dropped paths into the existing loader.
- Mode-visibility of the Task Files section — already delivered; the drop target simply follows the
  section's existing Task-Benchmark / Graded-Benchmark visibility.

## Spec inputs

- `02_New_Benchmark_Widget/description.md#43-task-files--task-benchmark-and-graded-benchmark` — the
  Task Files body is a List View with drag-and-drop; the empty state shows a dashed drop zone reading
  "Drop YAML task files or folders here"; both the empty placeholder and the populated list accept
  drops, and dropped files/folders are parsed and appended as rows.
- `02_New_Benchmark_Widget/description.md#5-behaviour-per-element` — the Task File drop target is
  active for `mode in {TASKS, GRADED}` and accepts dragged YAML files or folders, parsing and
  appending rows; a malformed file is rejected by the loader with an inline error.

## Design constraints

- `ui/new_benchmark/` reaches the backend only through its adapter gateway and the Task File Loader
  Protocol it is already wired with — the drop handlers add no new backend dependency.
- The drop handlers accept only local file/folder paths; a drag without local YAML paths is not
  accepted, so the cursor never signals a drop the widget cannot honour.
- Rendering-only concerns stay in the view; the parse/append decision runs through the existing
  loader path.

## Acceptance criteria

### STORY-084-AC-1

Given the New Benchmark task-files list in Task Benchmark or Graded Benchmark mode,
when a drag carrying local YAML task files is moved over it,
then the drag-enter is accepted so the drop is permitted.

### STORY-084-AC-2

Given the New Benchmark task-files list,
when one or more valid YAML task files are dropped onto it,
then each file is parsed by the Task File Loader and appended as a task-file row.

### STORY-084-AC-3

Given the New Benchmark task-files list,
when a malformed YAML file is dropped onto it,
then the loader rejects that file and an inline error is surfaced without adding a row.

## Test plan

- STORY-084-AC-1 — integration (`pytest-qt`), `tests/integration/test_new_benchmark_drag_drop.py`,
  `test_drag_enter_accepts_yaml_files_in_task_modes`.
- STORY-084-AC-2 — integration (`pytest-qt`), same file,
  `test_dropping_valid_task_files_appends_rows`.
- STORY-084-AC-3 — integration (`pytest-qt`), same file,
  `test_dropping_malformed_file_shows_inline_error_and_adds_no_row`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-084.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
