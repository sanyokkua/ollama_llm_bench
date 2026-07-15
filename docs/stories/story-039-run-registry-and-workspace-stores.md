---
id: STORY-039
title: Provide the RunRegistryStore and WorkspaceStore reactive state stores
status: done
spec_clauses:
  - 14_Process_and_Traceability/01_MODULE_INVENTORY.md#42-settings-stores-and-readiness-modules
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#19-workspace-controller
  - 09_Task_Editor/implementation_structure.md#7-dependency-protocols
  - 01_Main_Window/implementation_structure.md#8-stores-fanout
  - 08_Cross_Cutting/08-Q_event_payload_schemas.md#91-workspacechangedevent--_workspace_changed
modules:
  - backend/stores/
acceptance_criteria:
  - STORY-039-AC-1
  - STORY-039-AC-2
  - STORY-039-AC-3
  - STORY-039-AC-4
  - STORY-039-AC-5
  - STORY-039-AC-6
  - STORY-039-AC-7
depends_on:
  - STORY-014
  - STORY-015
  - STORY-016
adrs:
  - ADR-0007
owner: coder
estimate: L
---

# STORY-039 — Provide the RunRegistryStore and WorkspaceStore reactive state stores

## Goal

Give the application the two scoped reactive state stores that hold cross-cutting UI state:
which run is the active run, and which of the two workspaces (benchmark or task editor) is
active. Each store holds a frozen snapshot of its single slice of state and emits a psygnal
change signal when that snapshot is atomically swapped, so the adapters layer can bridge those
signals to Qt and drive workspace switching and run-identity updates. The exact surface of the
two Protocols is derived from their Phase-8 consumers per ADR-0007, not invented.

## In scope

- The `RunRegistryStore` Protocol and its concrete store: `active_run_id() -> RunId | None`,
  `set_active_run(run_id: RunId | None) -> None`, a frozen `RunRegistryState` snapshot, and a
  psygnal `active_run_changed` signal emitted on every change of the active run.
- The `WorkspaceStore` Protocol and its concrete store: `active_workspace() -> str`,
  `set_active_workspace(name: str) -> None`, a frozen `WorkspaceState` snapshot, and a psygnal
  `active_workspace_changed` signal emitted on every change of the active workspace.
- The `make_run_registry_store` and `make_workspace_store` factories on the module's `api.py`,
  guarded by `icontract` on programmer invariants only.
- A `testing.py` fake for each store, mirroring the `backend/stores/inference_activity/` pattern.

## Out of scope

- Bridging these psygnal signals to Qt signals — owned by `adapters/store_qt_bridge/`
  (STORY-044); this story defines the Qt-free stores only.
- The workspace-switch coordination (lazy widget construction, theme reapply, focus hint) and
  the `_workspace_changed` bus event emission — owned by `adapters/workspace_controller/`
  (STORY-045); this store holds the active-workspace state the controller reads and writes.
- The `backend/stores/inference_activity/` gate — a separate, already-implemented store
  (STORY-015) with a deliberately method-only surface (D-R-06); these two stores are the
  psygnal-driven reactive stores of ADR-0002.
- Any run-list, run-selection, or filter state — not called by either Phase-8 consumer, so out
  of scope per ADR-0007's minimal-surface rule.

## Spec inputs

- `14_Process_and_Traceability/01_MODULE_INVENTORY.md#42-settings-stores-and-readiness-modules`
  — `backend/stores/` holds the reactive UI state stores (run registry, workspace); Qt-free,
  asyncio-free, psygnal-driven, no `ui`/`adapters` import.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#19-workspace-controller` — the workspace names
  (`"benchmark"`, `"task_editor"`) and the fact that the current workspace is held as store
  state that the controller reads and writes.
- `09_Task_Editor/implementation_structure.md#7-dependency-protocols` — the Task Editor's
  `WorkspaceStore` and `RunRegistryStore` needs, wired behind the `TaskEditorGateway`
  (active-workspace read, active-run in-use marker).
- `01_Main_Window/implementation_structure.md#8-stores-fanout` — the Main Window consumes the
  workspace store and reacts to run identity; the run-registry store's active-run role.
- `08_Cross_Cutting/08-Q_event_payload_schemas.md#91-workspacechangedevent--_workspace_changed`
  — the workspace-state values (`"benchmark"`/`"task_editor"`) and the current-workspace-held-as-
  store-state statement the `WorkspaceStore` snapshot must match.

## Design constraints

- `backend/stores/` is Qt-free and asyncio-free; it imports only `backend/infra`,
  `backend/events`, `backend/domain`, `msgspec`, and `psygnal`
  (`01_MODULE_INVENTORY.md` §4.2). No PySide6.
- Every snapshot is a `msgspec.Struct(frozen=True, kw_only=True, gc=False)`; a change is an
  atomic swap of the whole snapshot, then the signal fires (ADR-0002).
- Each store's public surface stays minimal — exactly the methods and signals its two Phase-8
  consumers call — per ADR-0007. No speculative methods.
- `icontract` on the `api.py` factories guards programmer invariants only — never a user value.
- `set_active_workspace` accepts only `"benchmark"` or `"task_editor"`; any other name is a
  `ProgrammerError` (the workspace name is a code-controlled constant, not user input).

## Acceptance criteria

### STORY-039-AC-1

Given a freshly constructed `RunRegistryStore`, when `active_run_id()` is read before any set,
then it returns `None` (no active run at construction).

### STORY-039-AC-2

Given a `RunRegistryStore`, when `set_active_run(run_id)` is called with a run id different from
the current one, then `active_run_id()` returns that run id and exactly one `active_run_changed`
signal is emitted carrying the new `RunRegistryState` snapshot.

### STORY-039-AC-3

Given a `RunRegistryStore` whose active run is already `run_id`, when `set_active_run(run_id)` is
called again with the same value, then the snapshot is unchanged and no `active_run_changed`
signal is emitted (a no-op set fires no signal).

### STORY-039-AC-4

Given a freshly constructed `WorkspaceStore`, when `active_workspace()` is read before any set,
then it returns `"benchmark"` (the default workspace).

### STORY-039-AC-5

Given a `WorkspaceStore`, when `set_active_workspace(name)` is called with a valid name different
from the current one, then `active_workspace()` returns that name and exactly one
`active_workspace_changed` signal is emitted carrying the new `WorkspaceState` snapshot.

### STORY-039-AC-6

Given a `WorkspaceStore`, when `set_active_workspace(name)` is called with a name that is neither
`"benchmark"` nor `"task_editor"`, then it raises `ProgrammerError` and does not change the
snapshot or emit a signal.

### STORY-039-AC-7

Each store's snapshot is a frozen `msgspec.Struct`, and each store publishes its change signal
only after the new snapshot has been installed, so a signal handler that reads the store
observes the post-change snapshot (the swap-then-signal ordering holds for both stores).

## Test plan

- STORY-039-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/stores/tests/test_run_registry_store.py`,
  `test_active_run_id_is_none_at_construction`.
- STORY-039-AC-2 — unit, same file, `test_set_active_run_updates_snapshot_and_emits_signal`.
- STORY-039-AC-3 — unit, same file, `test_noop_set_active_run_emits_no_signal`.
- STORY-039-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/stores/tests/test_workspace_store.py`,
  `test_active_workspace_defaults_to_benchmark`.
- STORY-039-AC-5 — unit, same file,
  `test_set_active_workspace_updates_snapshot_and_emits_signal`.
- STORY-039-AC-6 — unit, same file,
  `test_invalid_workspace_name_raises_programmer_error_without_change`.
- STORY-039-AC-7 — unit (one per store), same two files,
  `test_signal_fires_after_snapshot_swap`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-039.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/stores/`.
- [ ] An architecture test confirms `backend/stores/` imports no Qt and no `asyncio`, and every
  snapshot Struct is `frozen=True, kw_only=True, gc=False`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
