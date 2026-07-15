# ADR-0007 — Derive the RunRegistryStore and WorkspaceStore protocol surfaces from their Phase-8 consumers

**Status:** accepted
**Date:** 2026-07-15
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** ADR-0002 (scoped reactive state stores plus a typed event bus)

## Context and problem statement

`RunRegistryStore` and `WorkspaceStore` are named in `14_Process_and_Traceability/01_MODULE_INVENTORY.md` §4.2 (the `backend/stores/` module) and are referenced by name in `08_Cross_Cutting/08-E_interfaces_contracts.md` §19 (Workspace Controller), `09_Task_Editor/implementation_structure.md` §7, and `01_Main_Window/implementation_structure.md` §8.
No spec file, however, defines their exact method or signal surface the way §7–§22 of `08-E` define every other Protocol.
Phase 8 (the adapters layer) is the first phase that must *construct* these two stores, because `adapters/store_qt_bridge/` bridges their psygnal signals to Qt signals and `adapters/workspace_controller/` reads and writes the active workspace through `WorkspaceStore`.
The implementation agent therefore needs a concrete surface to build against, and inventing an open-ended one risks speculative methods that no consumer calls (an orphaned surface the tests cannot justify).

## Decision drivers

- The two stores must exist before their Phase-8 consumers can be wired, but the spec fixes no method list.
- A reactive store's surface should be justified by a real caller, not invented — an unused method is untestable dead surface.
- The store pattern is already fixed by `backend/stores/inference_activity/` (STORY-015) and by ADR-0002: a frozen snapshot, a change signal, a factory, and a `testing.py` fake.
- `backend/stores/` is the only module path the inventory offers; new sub-package paths (`backend/stores/run_registry/`, `backend/stores/workspace/`) are not in the inventory and cannot be cited without editing the read-only vendored spec.

## Considered options

- Option A — Invent a broad, speculative store surface now (active run, run list, selection, filters, …) to pre-empt future needs.
- Option B — Derive a minimal surface strictly from the two concrete Phase-8 consumers (`store_qt_bridge`, `workspace_controller`), following the `inference_activity` store's structure.
- Option C — Defer the stores entirely and have the adapters hold ad-hoc state, adding the stores only when a UI phase forces them.

## Decision outcome

Chosen option: **Option B**. The `RunRegistryStore` and `WorkspaceStore` Protocols are derived from exactly what their two Phase-8 consumers call, and no further:

- `RunRegistryStore` — `active_run_id() -> RunId | None`, `set_active_run(run_id: RunId | None) -> None`, and a psygnal `active_run_changed` change signal carrying the new frozen snapshot.
- `WorkspaceStore` — `active_workspace() -> str`, `set_active_workspace(name: str) -> None`, and a psygnal `active_workspace_changed` change signal carrying the new frozen snapshot.

Both stores follow the `inference_activity` structure — a method-plus-signal Protocol, a frozen `msgspec.Struct` snapshot, a `make_*_store` factory, and a `testing.py` fake — and remain Qt-free and asyncio-free.
Unlike `inference_activity` (method-only, D-R-06), these two stores *do* expose psygnal change signals, because they are the scoped reactive stores of ADR-0002 that `store_qt_bridge` is explicitly the one adapter allowed to subscribe to.
Both stores live in the single `backend/stores/` module path (the only path the inventory offers), not in new sub-package paths.
A later UI phase that needs a wider surface adds one method with its own story and its own consumer, never a speculative batch.

### Consequences

- Positive — Every method on both stores has a named caller and a test; there is no speculative dead surface. The stores unblock all four Phase-8 consumers that need reactive run-identity and workspace state. Reusing the `inference_activity` structure keeps the reactive-store pattern uniform.
- Negative — The surface is deliberately narrow, so a future UI phase will likely add methods; those additions are new stories, which is more process than defining a broad surface once.
- Neutral — Both stores share one module (`backend/stores/`) rather than one package each, because the module inventory offers no finer path; the split into per-store `_internal/` sub-packages is an internal, non-inventory concern.

## Pros and cons of the options

### Option A — Invent a broad speculative surface now

- Good — Fewer future stories; the surface is defined once.
- Bad — Unused methods have no caller and no honest test; violates the "surface justified by a consumer" rule and risks locking in a shape the real UI phases contradict.

### Option B — Derive a minimal surface from the two Phase-8 consumers

- Good — Every method is caller-justified and testable; unblocks Phase 8; reuses the established store pattern.
- Bad — Future UI phases will extend the surface through additional stories.

### Option C — Defer the stores, use ad-hoc adapter state

- Good — No new backend module now.
- Bad — Pushes cross-cutting reactive state into the adapters, contradicting ADR-0002's state-ownership rule and leaving `store_qt_bridge` with nothing to bridge.

## Links

- Spec clauses:
  `14_Process_and_Traceability/01_MODULE_INVENTORY.md#42-settings-stores-and-readiness-modules`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#19-workspace-controller`,
  `09_Task_Editor/implementation_structure.md#7-dependency-protocols`,
  `01_Main_Window/implementation_structure.md#8-stores-fanout`
- Related ADRs: ADR-0002 (scoped reactive state stores plus a typed event bus)
- Stories: STORY-039, STORY-044, STORY-045
