---
id: STORY-040
title: Deliver the Qt-free event bus onto the Qt main thread via a queued-signal bridge
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#6-event-bus
  - 08_Cross_Cutting/08-J_event_bus_catalog.md#3-threading-model
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#2-the-concurrency-model-at-a-glance
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#8-thread-boundary-rules
modules:
  - adapters/qt_event_bus/
acceptance_criteria:
  - STORY-040-AC-1
  - STORY-040-AC-2
  - STORY-040-AC-3
  - STORY-040-AC-4
depends_on:
  - STORY-003
owner: coder
estimate: M
---

# STORY-040 — Deliver the Qt-free event bus onto the Qt main thread via a queued-signal bridge

## Goal

Provide the single adapter that connects the Qt-free typed event bus to Qt: an `emit` from any
worker thread is re-delivered to every subscriber on the Qt main thread through a queued
signal/slot connection. This is the one place backend→UI notifications cross the thread
boundary, so every widget subscriber's handler always runs on the GUI thread regardless of
which thread emitted the event.

## In scope

- The `QtEventBusDeliverer` and its `make_qt_event_bus_deliverer` factory: a concrete
  `EventBus` implementation that accepts `emit` from any thread and marshals delivery onto the
  Qt main thread using a queued `Signal`/slot connection.
- `subscribe(signal_name, handler, owner=None) -> Subscription` on the main thread, with
  owner-scoped auto-cancel so a destroyed widget owner never leaves a dangling handler, and an
  idempotent `Subscription.cancel()`.
- Handler-exception isolation: an exception raised inside one subscriber's handler is caught
  and logged, and never breaks delivery to the other subscribers or raises to the emitter.

## Out of scope

- The `EventBus` / `Subscription` Protocols and the payload Structs — owned by STORY-003; this
  story provides the concrete Qt-bound implementation of that Protocol.
- The `_inference_activity_changed` marshalling and the immediate-check gateway — owned by
  `adapters/qt_inference_activity_bridge/` (STORY-043), which uses this deliverer.
- The psygnal→Qt store bridge — a different channel entirely, owned by
  `adapters/store_qt_bridge/` (STORY-044).

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#6-event-bus` — the `EventBus` surface, the
  "`emit` callable from any thread, handlers run on the main thread" threading contract, the
  owner-scoped auto-cancel rule, and the "bus never raises to the emitter; a faulty handler is
  isolated" error contract this implementation must satisfy.
- `08_Cross_Cutting/08-J_event_bus_catalog.md#3-threading-model` — the `worker → UI`, `UI → UI`,
  `any → UI` per-event threading rules and the delivery-ordering guarantees the bridge preserves.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#2-the-concurrency-model-at-a-glance` —
  the "adapter's Qt bridge re-emits each event onto the GUI thread via a queued signal/slot
  connection" model this adapter implements; the backend never imports Qt.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#8-thread-boundary-rules` — the rule that
  a worker thread never touches a Qt widget directly and every cross-thread UI update crosses
  this bridge.

## Design constraints

- `adapters/qt_event_bus/` is the only place the pure bus is connected to Qt signals
  (`01_MODULE_INVENTORY.md` §5); it imports PySide6, `backend/events`, and `backend/infra`.
- Delivery to subscribers uses a **queued** connection so a handler always runs on the GUI
  thread even when `emit` is called from a worker or the dispatcher thread.
- The deliverer carries no business logic; it is a thin marshalling bridge.
- No `asyncio`; the concurrency stack is stdlib + Qt only.

## Acceptance criteria

### STORY-040-AC-1

Given a handler subscribed on the main thread, when `emit(signal_name, payload)` is called from
a non-GUI worker thread, then the handler is invoked on the Qt main thread with that payload
(never on the emitting thread).

### STORY-040-AC-2

Given a handler subscribed with an `owner`, when that owner object is destroyed, then the
subscription auto-cancels and a subsequent `emit` on that signal does not invoke the handler.

### STORY-040-AC-3

Given two handlers subscribed to the same signal where the first raises an exception, when the
signal is emitted, then the first handler's exception is caught and logged, the second handler
is still invoked, and `emit` returns normally to the caller (the bus never raises to the
emitter).

### STORY-040-AC-4

Given an active subscription, when `Subscription.cancel()` is called twice, then the first call
stops further delivery to that handler and the second call is a no-op that does not raise
(cancel is idempotent).

## Test plan

- STORY-040-AC-1 — integration (`pytest-qt`), `tests/integration/test_qt_event_bus.py`,
  `test_emit_from_worker_thread_delivers_on_gui_thread`.
- STORY-040-AC-2 — integration (`pytest-qt`), same file,
  `test_owner_destruction_auto_cancels_subscription`.
- STORY-040-AC-3 — unit, colocated
  `src/ollama_llm_bench/adapters/qt_event_bus/tests/test_deliverer.py`,
  `test_faulty_handler_is_isolated_and_emit_never_raises`.
- STORY-040-AC-4 — unit, same file, `test_subscription_cancel_is_idempotent`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-040.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/qt_event_bus/`.
- [ ] An architecture test confirms `adapters/qt_event_bus/` is the only module connecting the
  pure bus to a Qt signal, and that it imports no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
