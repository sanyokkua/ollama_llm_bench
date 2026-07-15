---
id: STORY-044
title: Bridge the psygnal-driven reactive stores to Qt signals on the main thread
status: done
spec_clauses:
  - 14_Process_and_Traceability/01_MODULE_INVENTORY.md#5-adapters-modules
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#19-workspace-controller
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#8-thread-boundary-rules
modules:
  - adapters/store_qt_bridge/
acceptance_criteria:
  - STORY-044-AC-1
  - STORY-044-AC-2
  - STORY-044-AC-3
depends_on:
  - STORY-039
  - STORY-008
  - STORY-009
  - STORY-010
  - STORY-011
  - STORY-012
  - STORY-013
adrs:
  - ADR-0007
owner: coder
estimate: M
---

# STORY-044 — Bridge the psygnal-driven reactive stores to Qt signals on the main thread

## Goal

Provide the single adapter that connects the psygnal change signals of the `backend/stores/*`
reactive stores (the `RunRegistryStore` and `WorkspaceStore` snapshots) to Qt signals delivered
on the main thread, so a Qt widget can observe reactive state changes with correct thread
affinity. This is the only adapter allowed to subscribe to a psygnal signal from a Qt thread.

## In scope

- The `make_store_qt_bridge(...)` factory: subscribes to each backend store's psygnal change
  signal and re-emits it as a Qt `Signal` on the main thread, carrying the store's new frozen
  snapshot.
- Marshalling every psygnal emission — which may originate on a non-GUI thread — onto the Qt
  main thread via a queued connection so widget slots always run on the GUI thread.
- Clean teardown: the bridge unsubscribes from the psygnal signals when disposed so no dangling
  subscription outlives it.

## Out of scope

- The `RunRegistryStore` / `WorkspaceStore` Protocols, snapshots, and psygnal signals — owned by
  STORY-039 (per ADR-0007); this bridge only marshals what those stores already emit.
- The single-inference gate marshalling (the gate is method-only, D-R-06, not psygnal-driven) —
  owned by `adapters/qt_inference_activity_bridge/` (STORY-043).
- The event-bus Qt delivery — a separate channel, owned by `adapters/qt_event_bus/` (STORY-040).
- The six persistence stores (STORY-008–STORY-013) are sequencing dependencies (they are
  co-constructed over the same database and their run rows feed the run-registry state), but they
  emit no psygnal signal, so this bridge does not subscribe to them.

## Spec inputs

- `14_Process_and_Traceability/01_MODULE_INVENTORY.md#5-adapters-modules` — `store_qt_bridge`
  bridges psygnal-driven `backend/stores/*` signals to Qt signals and is the only adapter
  allowed to subscribe to a psygnal signal from a Qt thread.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#19-workspace-controller` — the workspace state
  the bridge surfaces (`"benchmark"`/`"task_editor"`) is held in the workspace store and read
  across the boundary.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#8-thread-boundary-rules` — a worker thread
  never touches a Qt widget directly; every cross-thread reactive update is marshalled onto the
  GUI thread through this bridge.

## Design constraints

- `adapters/store_qt_bridge/` imports PySide6, `backend/stores`, and `psygnal`
  (`01_MODULE_INVENTORY.md` §5); it is the sole psygnal-subscribing adapter.
- Re-emission uses a queued connection so a psygnal emission from a non-GUI thread still delivers
  to widget slots on the Qt main thread.
- The bridge carries no store logic; the stores remain the single owners of their snapshots.
- No `asyncio`.

## Acceptance criteria

### STORY-044-AC-1

Given the bridge is wired to a `RunRegistryStore`, when the store's `active_run_changed` psygnal
signal fires, then the bridge emits its corresponding Qt signal carrying the store's new
`RunRegistryState` snapshot.

### STORY-044-AC-2

Given the bridge is wired to a `WorkspaceStore` and a Qt slot connected to the bridge, when the
store's `active_workspace_changed` psygnal fires from a non-GUI thread, then the connected Qt
slot runs on the Qt main thread with the new `WorkspaceState` snapshot.

### STORY-044-AC-3

Given a bridge with active psygnal subscriptions, when the bridge is disposed, then it
unsubscribes from every store's psygnal signal and a subsequent store change emits no Qt signal
from the disposed bridge.

## Test plan

- STORY-044-AC-1 — unit, colocated
  `src/ollama_llm_bench/adapters/store_qt_bridge/tests/test_bridge.py`,
  `test_run_registry_psygnal_reemits_as_qt_signal`.
- STORY-044-AC-2 — integration (`pytest-qt`), `tests/integration/test_store_qt_bridge.py`,
  `test_workspace_change_from_worker_delivers_on_gui_thread`.
- STORY-044-AC-3 — unit, colocated test file,
  `test_dispose_unsubscribes_from_store_signals`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-044.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/store_qt_bridge/`.
- [ ] An architecture test confirms `store_qt_bridge` is the only adapter subscribing to a
  psygnal signal and imports no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
