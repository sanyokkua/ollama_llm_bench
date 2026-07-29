---
id: STORY-112
title: Implement the on-disk task-file change watcher in the file-system-actions adapter
status: done
spec_clauses:
  - 09_Task_Editor/state_machine.md#8-external-file-change-watch
  - 09_Task_Editor/state_machine.md#3-per-file-state
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#21c-filesystemactions
  - 09_Task_Editor/implementation_structure.md#7-dependency-protocols
  - 14_Process_and_Traceability/01_MODULE_INVENTORY.md#5-adapters-modules
modules:
  - adapters/file_system_actions/
  - ui/task_editor/
acceptance_criteria:
  - STORY-112-AC-1
  - STORY-112-AC-2
  - STORY-112-AC-3
  - STORY-112-AC-4
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: M
---

# STORY-112 — Implement the on-disk task-file change watcher in the file-system-actions adapter

## Goal

Stop the Task Editor from silently overwriting someone else's edit. While a task file is open in the
editor, the application notices when that file's contents change on disk — because the user edited it
in another program, or a version-control checkout replaced it — and flags the file so the editor can
offer to reload it or keep the in-editor edits. A save that merely touches the file without changing
what is in it raises no alarm, and neither does the editor's own save of that file.

## In scope

- The concrete `FileChangeWatcher` implementation and its `make_file_change_watcher(...)` factory on
  `adapters/file_system_actions/`'s public surface.
- Registering a per-path watch that reports back only when the watched path's on-disk **content**
  actually differs from what was last read.
- The `FileWatchSubscription` handle returned by each watch, including its idempotent cancellation.
- Re-baselining the watch inside the Task Editor controller after a successful save, so the editor's
  own write is never reported back to it as somebody else's change.

## Out of scope

- The reload-pending glyph on the file's row and the Reload action (toolbar and row context menu) —
  already delivered by STORY-069; this story only supplies the notification that drives them.
- The "This file changed on disk. [Reload] [Keep my edits]" banner and its Keep-my-edits action —
  **not** yet built anywhere (verified by repository grep: no such banner string and no
  Keep-my-edits handler exists in `src/ollama_llm_bench/ui/`). It needs its own story before the
  Task Editor matches `09_Task_Editor/state_machine.md` §8 in full. It does not block this story:
  the watcher is the right unit of work on its own, and the reload-pending glyph is a real,
  observable effect of it.
- Re-reading and re-validating a reloaded file — already delivered by the Task Editor's own reload
  path.
- The `TaskEditorGateway` the same collaborator bundle requires — owned by STORY-111. That one is an
  `08-E` §7b gateway and lands in a different module.
- Watching anything other than an open task file — no directory watch, no application-data watch, no
  database-file watch.

## Spec inputs

- `09_Task_Editor/state_machine.md#3-per-file-state` — a successful Save moves a file from `Dirty`
  back to `Loaded`, writing the file to disk. That write is what forces AC-4: the watcher compares
  the on-disk bytes against the ones it last read and cannot tell who wrote them, so the save path
  must re-baseline the watch or every save would immediately drive its own file into `Conflict`.
- `09_Task_Editor/state_machine.md#8-external-file-change-watch` — the watcher tracks each open file
  and raises the conflict state **only** when the on-disk content actually differs; a touch that does
  not change content is ignored. The conflict state resolves either way (Reload or Keep my edits) back
  to watching.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#21c-filesystemactions` — the existing contract of the
  module that gains this code, and the operating-system-integration character it must keep.
- `09_Task_Editor/implementation_structure.md#7-dependency-protocols` — the workspace's dependency set,
  which includes the file-change watcher as a collaborator supplied by the composition root.
- `14_Process_and_Traceability/01_MODULE_INVENTORY.md#5-adapters-modules` — the
  `adapters/file_system_actions/` row: an operating-system-integration adapter whose per-operating-system
  branches are isolated in `_internal/` and tested with platform-aware fakes.

## Design constraints

- **Why this lands in `adapters/file_system_actions/` and needs no new module.** Watching a file for
  content changes is an operating-system-integration file concern, which is exactly that module's
  character: the module inventory already describes it as an operating-system-integration adapter with
  per-operating-system branches isolated in `_internal/` and platform-aware fakes in its tests. The
  module path is already in the inventory, so this story needs no inventory correction and no ADR — per
  `14_Process_and_Traceability/04_ADR_FORMAT.md` §2 a cheaply reversible placement of one small class is
  not ADR material. This is deliberately **not** covered by ADR-0014, which settles only where the seven
  `08-E` §7b gateways live.
- **The Protocols are mirrored, not moved.** `FileChangeWatcher` and `FileWatchSubscription` stay
  declared in `ui/task_editor/protocols.py`, which remains the source of truth for their shape.
  `adapters/file_system_actions/` must not import `ui` (`import-linter`), so `api.py` cannot use the
  UI module's copy as its return-type annotation — the two Protocols are re-declared verbatim in
  `adapters/file_system_actions/protocols.py` and the concrete class satisfies both structurally,
  with no import in either direction. This is the same seam ADR-0014 chose for the seven UI gateways
  ("Protocol ownership stays in the UI module … each concrete class satisfies it structurally — no
  import of the UI module"); the adapter-side declaration carries a docstring saying why the
  duplicate exists and that a change to the UI declaration must be mirrored.
- **Polling, not `QFileSystemWatcher`.** One shared `QTimer` on the graphical thread stats every
  watched path each tick and re-reads a path only when its modification time or size moved. Qt's
  native watcher silently loses its watch when the path is *replaced by rename* — which is precisely
  how both the application's own YAML save and a version-control checkout replace a task file — and
  this story's acceptance tests rewrite in place, so they would never catch a bug in the re-arming
  logic. Polling is immune to that, needs no per-operating-system branch (so the module's
  platform-isolation architecture test holds trivially), and is deterministic under test. The cost
  is up to one poll interval of latency; the interval is a constructor argument so tests drive it
  fast.
- A path-modified signal alone is not enough: the watcher must compare content before reporting, because
  the specification requires a content-preserving touch to be ignored. Keep the last-read content (or a
  digest of it) per watched path.
- `on_changed` runs on the graphical thread — the Task Editor controller updates widgets from it
  directly. If the underlying mechanism reports from another thread, the adapter marshals onto the
  graphical thread before calling back, per the adapter layer's marshalling responsibility.
- `cancel()` is idempotent: calling it a second time is a no-op, never an error, because the workspace
  cancels on file close and again on workspace teardown.
- Watching a path that is deleted or becomes unreadable must not raise out of the watcher; the Task
  Editor treats absence through its own state machine, not through an exception from this adapter.
- No `setStyleSheet`, no colour literal, no `asyncio`/`anyio`/`qasync` (architecture-test enforced).

## Acceptance criteria

### STORY-112-AC-1

Given a task file being watched through `watch(path, on_changed)`,
when that file's content on disk is replaced with different content,
then `on_changed` is invoked exactly once with that path.

### STORY-112-AC-2

Given a task file being watched through `watch(path, on_changed)`,
when that file is rewritten with byte-identical content,
then `on_changed` is never invoked.

### STORY-112-AC-3

Given a watch whose subscription has already been cancelled once,
when `cancel()` is called again and the file's content is then changed on disk,
then the second `cancel()` raises no exception and `on_changed` is never invoked.

### STORY-112-AC-4

Given a task file open and edited in the Task Editor,
when the user saves it and the save succeeds,
then the controller cancels that file's existing watch and starts a fresh one — leaving exactly one
live watch on the path, baselined on the bytes just written — so the file's row does not enter the
reload-pending state as a result of the editor's own save.

## Test plan

- STORY-112-AC-1 — integration (crosses a real file-system boundary, so it uses `tmp_path` and
  `qtbot.waitUntil` rather than a colocated unit test),
  `tests/integration/test_task_file_change_watcher.py`,
  `test_changed_content_notifies_the_watcher_once`.
- STORY-112-AC-2 — integration, same file, `test_content_preserving_rewrite_does_not_notify`.
- STORY-112-AC-3 — integration, same file, `test_cancel_is_idempotent_and_stops_notifications`.
- Design constraint (no acceptance criterion of its own) — integration, same file,
  `test_an_absent_watched_path_is_never_reported_as_a_change`: a watched path that is deleted, and
  one that never existed, are skipped on every tick rather than raising out of the watcher.
- STORY-112-AC-4 — colocated unit test (the behaviour under test is the controller's own contract,
  so it is asserted directly against `FakeFileChangeWatcher` rather than by waiting on real poll
  ticks), `src/ollama_llm_bench/ui/task_editor/tests/test_controller_watch_rebaseline.py`,
  `test_saving_through_the_editor_does_not_raise_a_conflict`. `FakeFileChangeWatcher` gains a
  `live_watch_count(path)` test helper so the test can tell a cancelled-then-re-registered watch
  (one live) from a leaked stale watch (two live) — `watched_paths` alone only ever grows.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-112.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/file_system_actions/` and
  `ui/task_editor/`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged. **Recorded divergence:** `01_MODULE_INVENTORY.md` line 223
  lists this module's public API as "`FileSystemActions` Protocol; `make_file_system_actions`".
  Adding `make_file_change_watcher` makes that cell stale. The specification is read-only, so
  this story leaves it alone — noted here so the drift is recorded rather than silent.
