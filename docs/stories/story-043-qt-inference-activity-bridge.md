---
id: STORY-043
title: Bridge the inference-activity gate onto the Qt thread and expose the immediate-check gateway
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store
  - 08_Cross_Cutting/08-Q_event_payload_schemas.md#82-inferenceactivitychangedevent--_inference_activity_changed
modules:
  - adapters/qt_inference_activity_bridge/
acceptance_criteria:
  - STORY-043-AC-1
  - STORY-043-AC-2
  - STORY-043-AC-3
depends_on:
  - STORY-015
  - STORY-040
owner: coder
estimate: M
---

# STORY-043 — Bridge the inference-activity gate onto the Qt thread and expose the immediate-check gateway

## Goal

Give the UI a Qt-safe view of the application-wide single-inference gate. The bridge forwards
the store's `_inference_activity_changed` publications onto the Qt main thread as the typed
`InferenceActivityChangedEvent`, and exposes an immediate-check `is_inference_busy()` gateway a
controller can call in place to decide whether to disable its inference trigger. The UI never
imports the store and never subscribes to a backend reactive primitive directly.

## In scope

- The `make_qt_inference_activity_bridge` factory: an adapter over the
  `InferenceActivityStore` (method-only Protocol, D-R-06) and the event bus.
- Forwarding every gate acquire/release change as the typed `InferenceActivityChangedEvent`
  marshalled onto the Qt main thread through the `qt_event_bus` deliverer.
- The immediate-check `is_inference_busy()` gateway method that returns the current gate
  busy-state synchronously for an in-place controller check.

## Out of scope

- The `InferenceActivityStore` gate, its lease/watchdog semantics, and its
  `_inference_activity_changed` publication — owned by STORY-015; this bridge marshals what the
  store already publishes and reads the store's busy-state.
- The generic event-bus Qt delivery machinery — owned by `adapters/qt_event_bus/` (STORY-040),
  which this bridge uses.
- The individual UI triggers that subscribe to the event or call the gateway (New Benchmark
  Start, Settings Test connection, Result Run Analysis) — later UI phases.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store` — the store is
  method-only; the adapter marshals `_inference_activity_changed` onto the Qt main thread and
  additionally exposes an immediate-check gateway (e.g. `is_inference_busy()`); the UI observes
  the gate only through the adapter, never the store directly.
- `08_Cross_Cutting/08-Q_event_payload_schemas.md#82-inferenceactivitychangedevent--_inference_activity_changed`
  — the `InferenceActivityChangedEvent(state: InferenceActivityState)` payload, the
  emitter/subscribers, the `any → UI` threading, and the no-coalescing rule (one event per
  acquire and per release).

## Design constraints

- `adapters/qt_inference_activity_bridge/` imports PySide6, `backend/stores/inference_activity`,
  and `backend/events` (`01_MODULE_INVENTORY.md` §5). No `asyncio`.
- Every gate change forwards as exactly one typed `InferenceActivityChangedEvent`; no coalescing.
- `is_inference_busy()` is a synchronous immediate read of the gate's current busy-state, callable
  on the GUI thread.
- The bridge carries no gate logic; the store remains the single owner of acquire/release.

## Acceptance criteria

### STORY-043-AC-1

Given the bridge is wired to the store's `_inference_activity_changed` publications, when the
store publishes a change, then the bridge delivers exactly one `InferenceActivityChangedEvent`
carrying the new `InferenceActivityState` onto the Qt main thread (no coalescing across acquire
and release).

### STORY-043-AC-2

Given the gate currently holds an activity, when a controller calls `is_inference_busy()`, then
it returns `True`; given the gate is idle, the same call returns `False` — the immediate check
reflects the current gate state synchronously.

### STORY-043-AC-3

Given a subscriber wired only through the bridge, when the gate changes on a non-GUI thread, then
the subscriber's handler runs on the Qt main thread, and the subscriber never imports or
subscribes to the `InferenceActivityStore` directly.

## Test plan

- STORY-043-AC-1 — integration (`pytest-qt`),
  `tests/integration/test_qt_inference_activity_bridge.py`,
  `test_gate_change_forwards_one_typed_event_on_gui_thread`.
- STORY-043-AC-2 — unit, colocated
  `src/ollama_llm_bench/adapters/qt_inference_activity_bridge/tests/test_gateway.py`,
  `test_is_inference_busy_reflects_current_gate_state`.
- STORY-043-AC-3 — architecture, `tests/architecture/test_ui_gate_access.py`,
  `test_gate_observed_only_through_bridge_on_gui_thread`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-043.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for
  `adapters/qt_inference_activity_bridge/`.
- [ ] An architecture test confirms the bridge is the sole UI-facing access to the gate and the
  module imports no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
