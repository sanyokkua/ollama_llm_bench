# ADR-0009 — Add `tokens_estimated` to `InferenceProgressEvent` as an additive DTO field

**Status:** accepted
**Date:** 2026-07-20
**Deciders:** user (product owner), coder session (STORY-059)
**Supersedes:** —
**Superseded by:** —

## Context and problem statement

STORY-059 (`docs/stories/story-059-progress-current-task-controller.md`) requires the
Progress widget's Current-task sub-controller to prefix a live token count with `~` when
that count is the emitter's 4-character heuristic rather than a provider-reported
`delta_tokens` count (AC-6, EC-RUN-17). `04_Progress_Widget/implementation_structure.md`
§4.2 states that the `_inference_progress` payload "does not carry it explicitly" and
implies the `CurrentTaskController` should infer the approximation itself.

That inference is not actually possible from the payload as specified. The event carries
only `elapsed_ms`, `tokens_received`, and `first_token_received` — no per-chunk
`delta_tokens` history, and no discriminator for which counting strategy produced the
current `tokens_received` value. The emitter (`backend/inference_progress/_internal/emit.py`)
already computes this decision internally (a `token_source` local variable, `"estimate"` vs
`"delta_tokens"`) but drops it before constructing the event. The UI layer has no
independent signal to reconstruct it from.

The canonical DTO contract (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.7a) and the event-bus
schema (`08_Cross_Cutting/08-Q_event_payload_schemas.md` §4.1a) both enumerate
`InferenceProgressEvent`'s fields without a token-estimation-source flag — so threading the
already-computed value through as a new field is a change to a spec-enumerated payload, not a
clarification of an already-open question. Should the payload be widened to close this gap, or
should AC-6 be dropped/deferred until the spec's own inference mechanism is made workable?

## Decision drivers

- AC-6 and EC-RUN-17 are binding acceptance criteria for STORY-059; dropping them regresses
  the story's scope rather than resolving the conflict.
- The emitter already computes the exact signal needed — no new heuristic or Qt-side
  approximation logic would need to be invented in the UI layer.
- `msgspec.Struct` schema evolution rules (`coding-style.md`) make an optional field with a
  default a strictly additive, backward-compatible change: every existing construction site
  and every existing test (STORY-030, STORY-035) continues to work unmodified.
- The spec's own "controller infers it" mechanism (§4.2) is unimplementable as written, so
  leaving the contradiction unresolved would block AC-6 indefinitely, not just for this story.

## Considered options

- Option A — Add `InferenceProgressEvent.tokens_estimated: bool = False`, populated by the
  emitter from its existing `token_source` decision.
- Option B — Revert the field; drop AC-6 from STORY-059 and mark it out of scope pending a
  future spec amendment that defines a real inference mechanism.
- Option C — Reconstruct the estimate/exact distinction in the UI layer from `tokens_received`
  alone (e.g., re-deriving the 4-char heuristic client-side and comparing).

## Decision outcome

Chosen option: **Option A**, because it satisfies AC-6/EC-RUN-17 with the least invented
surface area (the emitter already has the answer; the UI does no new heuristic work), is a
strictly additive and safe schema change, and Option C would require the UI layer to
independently reimplement a backend heuristic it has no business owning — a worse violation of
layering than a small, additive DTO field.

### Consequences

- Positive — AC-6/EC-RUN-17 are implementable exactly as specified, with a single source of
  truth (the emitter) for the estimate/exact distinction.
- Negative — `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.7a and
  `08_Cross_Cutting/08-Q_event_payload_schemas.md` §4.1a are now out of date relative to the
  shipped code; they list `InferenceProgressEvent`'s fields without `tokens_estimated`. This
  ADR is the record of that divergence until the vendored spec documents are next revised
  upstream (the vendored spec tree is read-only within this repository — see
  `repository-documentation.md` — so the fix is this ADR, not an edit to the spec files).
- Neutral — `implementation_structure.md` §4.2's "the controller infers it" language is
  superseded in practice by "the emitter computes and emits it, the controller reads it" —
  functionally equivalent from the controller's point of view (it still receives a boolean it
  did not derive itself), but the mechanism moved one layer down.

## Pros and cons of the options

### Option A — Additive `tokens_estimated` field on the event

- Good — Single source of truth in the emitter; no duplicated heuristic logic.
- Good — Strictly additive; zero risk to existing callers/tests.
- Bad — Diverges from the current text of two spec documents until they are revised.

### Option B — Drop AC-6 from STORY-059

- Good — No divergence from the current spec text.
- Bad — Regresses a binding acceptance criterion the story was written to satisfy.
- Bad — Defers the underlying problem (the spec's inference mechanism doesn't work) rather
  than resolving it.

### Option C — Re-derive the heuristic in the UI layer

- Good — No DTO change.
- Bad — Duplicates backend counting logic in `ui/progress/`, a layering violation worse than an
  additive field; the two implementations could drift out of sync.
- Bad — The UI layer would need `tokens_received`'s full history per call to distinguish
  "still counting via heuristic" from "provider just started reporting exact counts", data the
  event stream does not carry at all.

## Links

- Related ADRs: ADR-0006 (shared inference-progress helper — the emitter this ADR extends)
- Spec clauses: `docs/v3_specification/04_Progress_Widget/implementation_structure.md` §4.2;
  `docs/v3_specification/10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.7a;
  `docs/v3_specification/08_Cross_Cutting/08-Q_event_payload_schemas.md` §4.1a;
  `docs/v3_specification/11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9
- Stories: STORY-059
