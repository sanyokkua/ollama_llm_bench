---
id: STORY-045
title: Coordinate workspace switching with lazy widget construction, focus hint, and theme reapply
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#19-workspace-controller
  - 08_Cross_Cutting/08-Q_event_payload_schemas.md#91-workspacechangedevent--_workspace_changed
  - 01_Main_Window/implementation_structure.md#8-stores-fanout
modules:
  - adapters/workspace_controller/
acceptance_criteria:
  - STORY-045-AC-1
  - STORY-045-AC-2
  - STORY-045-AC-3
  - STORY-045-AC-4
depends_on:
  - STORY-039
  - STORY-040
adrs:
  - ADR-0007
owner: coder
estimate: M
---

# STORY-045 — Coordinate workspace switching with lazy widget construction, focus hint, and theme reapply

## Goal

Provide the Qt-bound coordinator that switches the main window between its two workspaces —
`"benchmark"` and `"task_editor"`. On a switch it constructs the destination workspace's widget
lazily on first entry (then keeps it alive), records the new active workspace in the
`WorkspaceStore`, reapplies the theme to the newly shown widget, applies any focus hint, and
emits the `_workspace_changed` event so the shell and panels react.

## In scope

- The `WorkspaceController` Protocol implementation and its `make_workspace_controller` factory:
  `active() -> str` and `switch_to(name, hint=None) -> None`.
- Lazy construction of each workspace widget via the factories registered by `compose.py` — the
  destination widget is built on first `switch_to` to it and retained thereafter.
- On a switch: write the active workspace to the `WorkspaceStore`, reapply the theme to the
  shown workspace, apply the optional `WorkspaceHint` (pre-open paths / focus widget), and emit
  one `_workspace_changed` event carrying the new and previous workspace names.

## Out of scope

- The `WorkspaceStore` state store itself — owned by STORY-039 (ADR-0007); this controller reads
  and writes it.
- The event-bus Qt delivery machinery — owned by `adapters/qt_event_bus/` (STORY-040).
- The workspace widgets' internals (New Benchmark, Task Editor) — later UI phases; this
  controller only constructs and shows them via injected factories.
- Persisting `ui.active_workspace` to settings — the Main Window's `MainWindowGateway` concern,
  not this controller.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#19-workspace-controller` — the
  `WorkspaceController` surface (`active()`, `switch_to(name, hint)`), the `WorkspaceHint`
  contract-local struct (`open_paths`, `focus_widget`), the two valid workspace names, and the
  synchronous, never-raises-for-a-valid-name contract.
- `08_Cross_Cutting/08-Q_event_payload_schemas.md#91-workspacechangedevent--_workspace_changed`
  — the `WorkspaceChangedEvent(workspace, previous_workspace)` payload, its emitter (the
  Workspace Controller), its subscribers, and the `UI → UI` threading rule.
- `01_Main_Window/implementation_structure.md#8-stores-fanout` — the workspace store's role in
  the Main Window fan-out and the workspace-switch coordination this controller drives.

## Design constraints

- `adapters/workspace_controller/` imports PySide6, `backend/events`, and `backend/stores`
  (`01_MODULE_INVENTORY.md` §5); it holds references to lazy widget factories registered by
  `compose.py`. No `asyncio`.
- `switch_to` is synchronous, called on the main thread, and never raises for a valid workspace
  name; an invalid name is a `ProgrammerError` (the name is a code constant).
- The destination widget is constructed at most once (lazy, then retained).
- Exactly one `_workspace_changed` event is emitted per actual switch.

## Acceptance criteria

### STORY-045-AC-1

Given the controller has never shown the task-editor workspace, when `switch_to("task_editor")`
is called, then the task-editor widget factory is invoked exactly once to construct the widget,
and a second `switch_to("task_editor")` after switching away and back does not construct it
again (lazy-once, then retained).

### STORY-045-AC-2

Given the active workspace is `"benchmark"`, when `switch_to("task_editor")` is called, then the
`WorkspaceStore` active workspace becomes `"task_editor"`, `active()` returns `"task_editor"`,
and exactly one `_workspace_changed` event is emitted carrying `workspace="task_editor"` and
`previous_workspace="benchmark"`.

### STORY-045-AC-3

Given a `switch_to(name, hint)` call with a non-empty `WorkspaceHint`, when the switch completes,
then the destination workspace has the theme reapplied and the hint applied (focus widget /
pre-open paths forwarded to the shown workspace).

### STORY-045-AC-4

Given the active workspace is already `name`, when `switch_to(name)` is called again with the
same name, then no widget is re-constructed and no `_workspace_changed` event is emitted (a
same-workspace switch is a no-op).

## Test plan

- STORY-045-AC-1 — integration (`pytest-qt`), `tests/integration/test_workspace_controller.py`,
  `test_destination_widget_is_constructed_lazily_once`.
- STORY-045-AC-2 — integration (`pytest-qt`), same file,
  `test_switch_updates_store_and_emits_workspace_changed`.
- STORY-045-AC-3 — integration (`pytest-qt`), same file,
  `test_switch_reapplies_theme_and_applies_hint`.
- STORY-045-AC-4 — unit, colocated
  `src/ollama_llm_bench/adapters/workspace_controller/tests/test_controller.py`,
  `test_same_workspace_switch_is_noop`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-045.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/workspace_controller/`.
- [ ] An architecture test confirms the module imports no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
