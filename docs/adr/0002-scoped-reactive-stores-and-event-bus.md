# ADR-0002 — Adopt scoped reactive state stores plus a typed event bus

**Status:** accepted
**Date:** 2026-07-09
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** ADR-P-002, decision D-021

## Context and problem statement

The application has many widgets that must stay coordinated: run controls, progress, result
tables, charts, and settings all reflect shared state. Some of that state is cross-cutting (the
active run, the selected run, the current theme, table filters); some is purely local to one
widget; and some interactions are one-shot intents rather than state (a run started, a chart
drill-down requested). Backend work runs on `QThreadPool` worker threads via the adapter's
`TaskRunner` (D-R-01), so updates frequently originate on a thread other than the one the widget
runs on. Where should each kind of state live, and how do cross-thread updates reach the UI,
so that an AI implementation agent does not invent ad-hoc coupling?

## Decision drivers

- One clear, testable rule for where a given piece of state or interaction belongs.
- Explicit, auditable cross-thread delivery to the Qt main thread.
- No global state singletons; stores wired only through the composition root.
- Avoiding stores accumulating transient, one-shot flags.

## Considered options

- Option A — A single global application state object.
- Option B — Scoped reactive state stores plus a typed event bus, with a strict
  state-versus-intent split and an adapter-layer thread boundary.
- Option C — An event bus for everything, including durable state.

## Decision outcome

Chosen option: **Option B**, because it gives a single testable rule for where any piece of
state or interaction belongs, keeps stores free of transient flags, and puts cross-thread
correctness in one auditable place. Adopt a hybrid pattern with three clearly separated
mechanisms: cross-cutting state lives in scoped reactive state stores, each holding a frozen
snapshot of one slice of state and emitting a change signal when the snapshot is atomically
swapped, constructed and wired by the composition root with no global state singletons; purely
local widget state lives in a frozen view-model object inside the widget's own module and never
becomes a store; one-shot domain events travel on a typed event bus as frozen typed objects
owned by the publishing module, carrying intents and notifications, not durable state. The
adapter layer marshals cross-thread signals onto the Qt main thread; backend code never touches
a widget directly.

### Consequences

- Positive — A single, testable rule decides where any piece of state or interaction belongs,
  removing a common source of ad-hoc coupling. Frozen snapshots with atomic swaps make state
  transitions explicit and make stale reads detectable. The event bus keeps one-shot intents
  out of stores, so stores never accumulate transient flags. The adapter-layer thread boundary
  is one place to audit for cross-thread correctness, supporting an architecture test.
- Negative — Two coordination mechanisms exist; contributors must internalize the
  state-versus-intent rule, and a wrong choice produces awkward code. Scoped stores plus
  per-widget view models is more structure than a single shared state object, with more wiring
  in the composition root. The reactive store layer is an additional dependency whose behaviour
  the team must understand.
- Neutral — Every cross-thread update from backend work must be routed through the adapter
  layer's bridge rather than emitted directly from a worker thread.

## Pros and cons of the options

### Option A — A single global application state object

- Good — One place to look for all state; no state-versus-intent distinction to learn.
- Bad — A god-store couples unrelated widgets, makes change-tracking coarse, and accumulates
  transient flags that belong on an event bus.

### Option B — Scoped reactive stores plus a typed event bus

- Good — Testable state-ownership rule, atomic snapshot swaps, one audited thread boundary.
- Bad — Two mechanisms to learn; more composition-root wiring than a single shared object.

### Option C — An event bus for everything, including durable state

- Good — One uniform mechanism for both state and intents.
- Bad — Modelling durable state as a stream of events forces every consumer to rebuild current
  state from history and loses a single authoritative snapshot.

## Links

- Related ADRs: —
- Spec clauses: `08_Cross_Cutting/08-A_architecture_principles.md`,
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`,
  `15_Risks_and_Open_Questions/03_PROPOSED_ADRS.md#adr-p-002--scoped-reactive-state-stores-plus-a-typed-event-bus`
- Stories: —
