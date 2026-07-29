---
id: STORY-111
title: Implement the concrete Task Editor gateway over the settings, workspace, and run-registry reads
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b7-taskeditorgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 09_Task_Editor/implementation_structure.md#7-dependency-protocols
modules:
  - ui/task_editor/
  - adapters/ui_gateways/
acceptance_criteria:
  - STORY-111-AC-1
  - STORY-111-AC-2
edge_cases: []
depends_on: []
adrs:
  - ADR-0014
owner: coder
estimate: M
---

# STORY-111 — Implement the concrete Task Editor gateway over the settings, workspace, and run-registry reads

## Goal

Connect the Task Editor workspace to the real configuration. It honours the user's auto-format-on-save,
empty-grading-criteria-warning and validation-debounce preferences, reopens at the folder they last
used and remembers a new one, knows which workspace is currently showing, and marks any task file the
running benchmark is currently using so the user does not edit it out from under a live run.

## In scope

- The concrete `TaskEditorGateway` implementation and its `make_task_editor_gateway(...)` factory on
  the adapters layer's public surface — all four methods.
- The workspace settings read and write (`task_editor.auto_format_on_save`,
  `task_editor.warn_on_empty_grading_criteria`, `task_editor.validation_debounce_ms`,
  `ui.task_editor_last_folder`).
- The active-workspace read and the active run's task-file-path read that drives the in-use marker.

## Out of scope

- Wiring the gateway into `make_task_editor_workspace` and `build_app` — owned by STORY-077.
- The workspace's own behaviour — its files pane, tasks pane, field editor, YAML preview and save
  cascade — already delivered by STORY-069; this story changes no user-interface code.
- The `FileChangeWatcher` the same collaborator bundle requires — owned by STORY-112. It is not an
  `08-E` §7b gateway and it lands in a different module.
- Task-file loading, validation and writing — already delivered by `backend/task_files/` and
  `backend/yaml_formatter/`, which the workspace holds directly rather than through this gateway
  because task files are files on disk, not database rows.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b7-taskeditorgateway` — the four method signatures,
  verbatim, and the statement that this gateway wraps the settings layer (workspace settings keys), the
  workspace store (current workspace state), and the run registry (the active run's task paths for the
  in-use marker).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the gateway is
  method-only, carries stdlib and `msgspec` types only, no `psygnal` and no Qt symbol, and is scoped to
  the methods its controller actually calls (SPEC-074).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract` — all four methods are
  *fast-synchronous* and callable from the graphical thread; none may block.
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — the adapter holds the
  backend Protocols and decides how to satisfy each gateway method.
- `09_Task_Editor/implementation_structure.md#7-dependency-protocols` — the workspace's dependency set,
  read as the capabilities the adapter wires behind this gateway.

## Design constraints

- **Where the code lands.** The implementation lands in `adapters/ui_gateways/`. ADR-0014 is
  accepted and its inventory row now exists, so `modules:` names that path directly.

## Acceptance criteria

### STORY-111-AC-1

Each `TaskEditorGateway` method performs exactly the stated backend interaction against its injected
collaborators and returns that collaborator's value unchanged:

| Gateway method            | Backend interaction                                                |
| ------------------------- | ------------------------------------------------------------------ |
| `get_setting(key)`        | reads `key` from the app-settings store; returns `None` when unset |
| `set_setting(key, value)` | writes `key` through the settings service                          |
| `active_workspace()`      | returns the workspace store's current workspace identifier         |
| `active_run_task_paths()` | returns the run registry's task-file paths for the executing run   |

### STORY-111-AC-2

Given a run registry reporting that no run is active,
when `active_run_task_paths()` is called,
then it returns an empty tuple and raises no exception.

## Test plan

- STORY-111-AC-1 — unit, table-driven (one `@pytest.mark.parametrize` row per gateway method, total
  over all four), colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_task_editor_gateway.py`,
  `test_each_method_performs_its_backend_interaction`.
- STORY-111-AC-2 — unit, same file, `test_active_run_task_paths_is_empty_when_no_run_is_active`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-111.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.
