---
id: STORY-084
title: Complete drag-and-drop of task files onto the New Benchmark task-files list
status: ready
spec_clauses:
  - 02_New_Benchmark_Widget/description.md#43-task-files--task-benchmark-and-graded-benchmark
  - 02_New_Benchmark_Widget/description.md#5-behaviour-per-element
  - 02_New_Benchmark_Widget/description.md#13-edge-cases
modules:
  - ui/new_benchmark/
acceptance_criteria:
  - STORY-084-AC-1
  - STORY-084-AC-2
  - STORY-084-AC-3
edge_cases:
  - EC-TASK-1
depends_on: []
adrs: []
owner: coder
estimate: S
---

# STORY-084 — Complete drag-and-drop of task files onto the New Benchmark task-files list

## Goal

Finish the New Benchmark task-files drag-and-drop. Today the user can drag a YAML task file over
the Task Files list and the cursor accepts it, but letting go does nothing at all — no row appears,
no error appears. The specification requires the task-files list (both its empty drop zone and its
populated state) to accept dragged YAML files and folders in Task Benchmark and Graded Benchmark
modes, parse them, and append rows. This story wires the two missing handlers so a drop behaves
exactly like the Add File / Add Folder buttons already do.

## In scope

- `src/ollama_llm_bench/ui/new_benchmark/_internal/task_files.py`: `TaskFilesSectionWidget.__init__`
  calls `self.setAcceptDrops(True)` at **line 76**, directly under the `# TODO` comment at **line
  75** reading "drag-and-drop acceptance is not yet wired to a dragEnterEvent/dropEvent handler".
  Neither `dragEnterEvent` nor `dropEvent` exists anywhere in `ui/new_benchmark/` — the whole
  package's only drop-related call is that one `setAcceptDrops(True)`. Add the two handlers and
  **delete the TODO comment**.
- `dragEnterEvent`: accept a drag carrying local YAML file or folder paths while the mode is Task
  Benchmark or Graded Benchmark; otherwise ignore it, so the cursor never signals a drop the widget
  cannot honour.
- `dropEvent`: hand the dropped paths to the same `TaskFileLoader` the Add File / Add Folder buttons
  already use, and append the resulting rows.
- Surfacing a malformed dropped file the way the buttons do: the loader rejects it and an inline
  error appears without a row being added.
- Correcting the stale module docstring in
  `src/ollama_llm_bench/ui/new_benchmark/__init__.py`, whose sentence ending "are stubbed." at
  **line 4** still claims the Judge / Advanced Options / Start controls (STORY-055) and the
  Performance Matrix content are stubs. Both shipped — STORY-055 and STORY-071 are `done` — so the
  claim is simply false and misleads the next reader of the package.

The reference implementation to copy is the Task Editor's own pair of handlers,
`ui/task_editor/_internal/view.py` (`dragEnterEvent` line 225, `dropEvent` line 229) and
`ui/task_editor/_internal/files_pane.py` (lines 185 and 189).

## Out of scope

- The Task Editor's own drag-and-drop — already delivered; this story reuses its shape but changes
  nothing there.
- The Task File Loader and the Task File Validator themselves — delivered by STORY-031; this story
  only routes dropped paths into the existing loader.
- Mode-visibility of the Task Files section — delivered by STORY-054; the drop target simply follows
  the section's existing Task-Benchmark / Graded-Benchmark visibility.
- **Re-testing EC-TASK-2, EC-TASK-3, and EC-TASK-8** (duplicate `task_id` across files, a task
  missing a required field, a folder containing no YAML file). These are `TaskFileLoader`
  behaviours that the drop path *inherits* unchanged, because the drop path calls the same loader
  the buttons call. STORY-054 already proves all three and its tests stay authoritative — do not
  duplicate them here.

## Spec inputs

- `02_New_Benchmark_Widget/description.md#43-task-files--task-benchmark-and-graded-benchmark` — the
  Task Files body is a List View with drag-and-drop; the empty state shows a dashed drop zone
  reading "Drop YAML task files or folders here"; both the empty placeholder and the populated list
  accept drops, and dropped files/folders are parsed and appended as rows.
- `02_New_Benchmark_Widget/description.md#5-behaviour-per-element` — the Task File drop target is
  active for `mode in {TASKS, GRADED}` and accepts dragged YAML files or folders, parsing and
  appending rows; a malformed file is rejected by the loader with an inline error.
- `02_New_Benchmark_Widget/description.md#13-edge-cases` — this widget's own edge-case list, whose
  EC-TASK-1 row reads "Malformed YAML file **dropped** or added. The Task File Loader rejects the
  file; the widget shows an inline error and does not add the row." The word "dropped" is what
  makes EC-TASK-1 this story's obligation and not only STORY-054's.

## Design constraints

- `ui/new_benchmark/` reaches the backend only through its `NewBenchmarkGateway` and the
  `TaskFileLoader` Protocol the widget is already constructed with — the drop handlers add no new
  backend dependency and no new constructor argument.
- The handlers accept only local file/folder paths (`QMimeData.hasUrls()` with local files); a drag
  carrying anything else is ignored rather than accepted-then-rejected.
- The parse/append decision runs through the existing loader path; the view adds no parsing logic of
  its own.
- No `setStyleSheet`, no colour literal, no `asyncio` in the touched module.

## Acceptance criteria

### STORY-084-AC-1

Given the New Benchmark task-files list in Task Benchmark or Graded Benchmark mode,
when a drag carrying local YAML task-file paths is moved over it,
then the drag-enter event is accepted, so the drop is permitted.

### STORY-084-AC-2

Given the New Benchmark task-files list,
when one or more valid YAML task files are dropped onto it,
then each file is parsed by the `TaskFileLoader` and appended as a task-file row.

### STORY-084-AC-3

Given the New Benchmark task-files list,
when a malformed YAML file is dropped onto it,
then the loader rejects that file, an inline error is surfaced, and no row is added (EC-TASK-1).

## Test plan

- STORY-084-AC-1 — integration (`pytest-qt`), `tests/integration/test_new_benchmark_drag_drop.py`,
  `test_drag_enter_accepts_yaml_files_in_task_modes`.
- STORY-084-AC-2 — integration (`pytest-qt`), same file,
  `test_dropping_valid_task_files_appends_rows`.
- STORY-084-AC-3 — integration (`pytest-qt`), same file,
  `test_dropping_malformed_file_shows_inline_error_and_adds_no_row`. **This is EC-TASK-1's test for
  this story** — the drop half of "Malformed YAML file dropped or added", mapped Given/When/Then per
  `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`. EC-TASK-1 is already claimed and
  proven by the `done` STORY-054 for the *added* half, so claiming it here adds a second proving
  test rather than opening a coverage gap.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-084.
- [ ] EC-TASK-1 has a passing test.
- [ ] The `# TODO` at `ui/new_benchmark/_internal/task_files.py:75` is deleted, and no `# TODO`
  about unwired drag-and-drop remains in `ui/new_benchmark/`.
- [ ] The `ui/new_benchmark/__init__.py` module docstring no longer claims any part of the widget is
  stubbed.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-093** — the Phase-12 traceability, risk, and architecture documentation story. Flip it
  `draft` → `ready` **only once every other story it depends on is `done`**: STORY-076 through
  STORY-088, STORY-089, STORY-091, STORY-092, and STORY-114. STORY-084 is one input among many, so
  finishing it alone does not unblock STORY-093.

**What to do on completion**

Once STORY-084's acceptance-criteria tests pass:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependencies in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   The natural next picks are the other independently-`ready` finalization stories that also gate
   STORY-093 — STORY-085, STORY-088, and STORY-092 — since none of them depends on this one.
