---
id: STORY-003
title: Define the EventBus Protocol and every event payload Struct
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#6-event-bus
  - 08_Cross_Cutting/08-J_event_bus_catalog.md#2-subscription-ownership-binding-rule
  - 08_Cross_Cutting/08-J_event_bus_catalog.md#3-threading-model
  - 08_Cross_Cutting/08-J_event_bus_catalog.md#5-event-catalog
  - 08_Cross_Cutting/08-J_event_bus_catalog.md#7-event-to-payload-index
  - 08_Cross_Cutting/08-Q_event_payload_schemas.md#1-conventions
modules:
  - backend/events/
acceptance_criteria:
  - STORY-003-AC-1
  - STORY-003-AC-2
  - STORY-003-AC-3
  - STORY-003-AC-4
  - STORY-003-AC-5
depends_on:
  - STORY-001
  - STORY-002
owner: coder
estimate: L
---

# STORY-003 — Define the EventBus Protocol and every event payload Struct

## Goal

Provide the single typed publish/subscribe channel every cross-component, cross-thread
message in the application travels on, and the complete, closed catalogue of event payload
Structs it carries. This is the mechanism by which a background worker thread (the pipeline,
a provider client, a readiness probe) ever reaches the UI: no service calls a UI object
directly, so `backend/events/` is on the critical path of every other Phase-1-and-later
module that needs to announce something happened.

## In scope

- The `EventBus` Protocol and its `Subscription` companion Protocol
  (`08-E_interfaces_contracts.md` §6): `subscribe(signal_name, handler, owner=None) -> Subscription`, `emit(signal_name, payload) -> None`, `Subscription.cancel() -> None`.
- Every event payload `msgspec.Struct` named in the event-to-payload index
  (`08-J_event_bus_catalog.md` §7) and field-defined in `08-Q_event_payload_schemas.md`:
  the 7 run-lifecycle payloads, 8 stage/progress payloads, 6 per-task payloads, 3
  run-name/run-list payloads, 4 table/chart-data payloads, 3 settings/providers payloads,
  4 global/app-readiness payloads, and 2 workspace/task-file payloads (33 payload Structs
  total, one per event name in the §7 index).
- The closed set of `signal_name` string constants matching the catalogue's leading-underscore
  event names (`_run_started`, `_task_completed`, `_inference_progress`, …), exported so
  callers never hand-type a string literal.
- Re-export of the `EventBus` Protocol, `Subscription` Protocol, every payload Struct, and
  every signal-name constant from `backend/events/`'s public surface.

## Out of scope

- The concrete `EventBus` implementation and the Qt delivery bridge — owned by
  `adapters/qt_event_bus/` in a later phase; this story defines the Protocol and payloads
  only, both Qt-free.
- The scoped reactive state stores (`backend/stores/`) — a different channel entirely per
  `08-J_event_bus_catalog.md` §1; this story's catalogue is the Event Bus events only.
- Any emitter or subscriber logic — every module that emits or subscribes (pipeline,
  providers, widgets) does so in its own later story; this story only defines what can be
  emitted.
- The debounce/coalescing *implementation* (a Status Listener) — this story's Structs record
  which rule applies (informationally, in-scope of the schema) but building the coalescing
  mechanism is a later concern of the module that needs it.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#6-event-bus` — the exact `EventBus` /
  `Subscription` Protocol surface, its threading contract (`emit` callable from any thread,
  handlers always run on the main thread), and its no-raise-to-emitter error contract.
- `08_Cross_Cutting/08-J_event_bus_catalog.md#2-subscription-ownership-binding-rule` — every
  `subscribe` call requires an owner; a subscription with no owner is a programming error
  rejected at subscribe time.
- `08_Cross_Cutting/08-J_event_bus_catalog.md#3-threading-model` — `worker → UI`, `UI → UI`,
  `any → UI` threading rules per event, and the ordering guarantees (dispatcher-emitted
  run-domain events are totally ordered; `_inference_progress` is best-effort latest-wins
  except relative to its own task's `_task_completed`).
- `08_Cross_Cutting/08-J_event_bus_catalog.md#5-event-catalog` — the full 33-event catalogue
  (tables 5.1–5.8), each event's purpose, payload type name, emitter, subscribers, threading
  rule, and coalescing/debounce rule.
- `08_Cross_Cutting/08-J_event_bus_catalog.md#7-event-to-payload-index` — the one-to-one
  event-name-to-Struct-name mapping this story's Struct set must match exactly.
- `08_Cross_Cutting/08-Q_event_payload_schemas.md#1-conventions` — the field-naming and
  typing conventions every payload Struct follows (plus the per-event sections of that same
  file for the concrete field lists of each of the 33 Structs).

## Design constraints

- `backend/events/` is Qt-free; standard library and `msgspec` only
  (`01_MODULE_INVENTORY.md` §4.1). No `ui` or `adapters` imports.
- Every payload is a `msgspec.Struct(frozen=True, kw_only=True, gc=False)`, per the project's
  universal DTO rule — never `@dataclass`, never `dict[str, Any]`.
- A payload that names a provider carries only `provider_id` (the internal UUID4) for
  linkage, never the user-facing `name` (DD-33) — the subscriber resolves the display name
  from the relevant snapshot field or the live registry, not from the event.
- `_task_completed`'s optional `Verdict` field is `PASS`/`FAIL` only when the task is
  `COMPLETED` in a graded run and is otherwise absent; no payload anywhere carries a judge
  numeric score — the only numeric quality value in any payload is `cosine_similarity`.
- The `EventBus` Protocol carries no concrete queueing, threading, or Qt logic — it is a
  pure interface; `Subscription.cancel()` is documented idempotent.

## Acceptance criteria

### STORY-003-AC-1

The `EventBus` Protocol declares exactly `subscribe(signal_name, handler, owner=None) -> Subscription` and `emit(signal_name, payload) -> None`; the `Subscription` Protocol declares
exactly `cancel() -> None`. Both are `typing.Protocol` types, not `abc.ABC`.

### STORY-003-AC-2

For every event name in the `08-J_event_bus_catalog.md` §7 event-to-payload index, a
matching `msgspec.Struct(frozen=True, kw_only=True, gc=False)` payload type exists in
`backend/events/`, is named exactly as in the index, and its field set matches the
corresponding section of `08-Q_event_payload_schemas.md` (table-driven over all 33 events).

### STORY-003-AC-3

Every payload Struct that names a provider (per the catalogue's provider-identity rule,
DD-33) declares a `provider_id: ProviderIdStr` field and declares no `name`/`provider_name`
field; where a run-scoped provider name is needed the payload instead carries the run's
snapshot-name field, never a live-registry name.

### STORY-003-AC-4

`TaskCompletedEvent` declares `status: ResultStatus` and an optional `verdict: Verdict | None` field; constructing it with `verdict` set while `status != ResultStatus.COMPLETED`
is representable (the Struct does not forbid it, since the pipeline guarantees the
invariant at the call site) but no payload Struct anywhere in this module declares a
numeric judge-score field.

### STORY-003-AC-5

Every signal-name constant, the `EventBus` Protocol, the `Subscription` Protocol, and every
payload Struct named in the In-scope list is importable directly from the `backend/events/`
package root (re-exported from `__init__.py`), and the set of exported signal-name constants
has no member absent from, and no member beyond, the §7 index.

## Test plan

- STORY-003-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/events/tests/test_protocols.py`,
  `test_event_bus_and_subscription_protocol_shape`.
- STORY-003-AC-2 — table-driven unit, same directory
  `src/ollama_llm_bench/backend/events/tests/test_payload_catalogue.py`,
  `test_every_cataloged_event_has_a_matching_frozen_payload_struct`.
- STORY-003-AC-3 — table-driven unit, same file,
  `test_provider_naming_payloads_carry_provider_id_never_live_name`.
- STORY-003-AC-4 — unit, `src/ollama_llm_bench/backend/events/tests/test_task_completed.py`,
  `test_task_completed_event_verdict_field_and_no_numeric_score`.
- STORY-003-AC-5 — unit,
  `src/ollama_llm_bench/backend/events/tests/test_public_surface.py`,
  `test_events_public_symbols_and_signal_names_are_reexported_and_total`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-003.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/events/`.
- [ ] `test_dtos_are_frozen_kw_only` (from STORY-001's architecture test) passes for every
  Struct this story adds.
- [ ] Backend branch coverage for `backend/events/` meets the Phase 1 ≥90% gate.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
