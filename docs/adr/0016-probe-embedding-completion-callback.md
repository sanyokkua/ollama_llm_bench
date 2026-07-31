# ADR-0016 — Give `probe_embedding()` a completion callback alongside `ReadinessService`'s emit-on-change state update

**Status:** accepted
**Date:** 2026-08-01
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** ADR-0014, ADR-0015, STORY-110

## Context and problem statement

ADR-0015 settled how every network-bound `SettingsGateway` method delivers its result without
blocking the graphical thread. For `probe_embedding()` specifically, it decided: "`probe_all`
and `probe_embedding` need **no** callback and no new channel: `ReadinessService` already
'emit[s] the readiness-changed signal' itself (`08-E` §12), `_app_readiness_changed` is already
catalogued with the Settings dialog as a subscriber (`08-J` §5.7), and the Settings controller
already subscribes to it." That claim held for `probe_all` — the free, automatic on-open
handshake — but a second spec-conformance review of STORY-110's first implementation found it
does not hold for `probe_embedding` specifically.

`ReadinessService.record_embedding_capability_result(reachable=…)` — the method
`SettingsGateway.probe_embedding()`'s worker hands its billable `embed("probe")` outcome to —
recomputes the readiness snapshot and calls the same `_store_and_maybe_emit` path `probe_all`
uses, which emits `_app_readiness_changed` **only when the recomputed snapshot actually differs
from the cached one**. That conditional-emit rule is correct for `ReadinessService` as a cache:
there is no reason to publish an event that changes nothing. But `probe_embedding()` is not
`probe_all()` — it is triggered by one user click on the Settings dialog's Test Embedding
button, and that click's own widget (`EmbeddingSectionWidget`) had, before this fix, no way to
learn the check settled other than that same conditional event. In the common case — the
automatic on-open `probe_all()` handshake already found the embedding endpoint reachable, so a
user-initiated re-check reproduces the same `reachable=True` value — the snapshot does not
change, no event fires, and the diagnostic label the click set to "Testing…" is never repainted.
This directly undermines the very acceptance criterion (STORY-110-AC-10, now corrected to add
AC-11) requiring that the embedding diagnostic label never sticks on "Testing…" indefinitely.

So: how does the one-shot user action that triggered a billable capability check get a
guaranteed terminal signal, when the state store it reports into is deliberately silent on "no
change"?

## Decision drivers

- The billable check is a **one-shot user action**, not a batch or a state refresh — it needs a
  guaranteed completion signal regardless of whether the fact it discovered was already known.
- `ReadinessService`'s emit-only-on-change rule for its cached snapshot must stay correct and
  unchanged — it is the right behaviour for the store, and `probe_all`'s and
  `record_embedding_capability_result`'s state-update responsibility must not be diluted or
  duplicated.
- `08_Cross_Cutting/08-J_event_bus_catalog.md` §6 rule 2: "Is the data needed by exactly one
  widget and never crosses a widget boundary? Then keep it inside that widget's own local
  signal mechanism; do not add a bus channel." A per-click completion signal for one widget's
  own button is exactly this case — it is not new cross-widget state, so it must not become a
  new bus channel, matching the same reasoning ADR-0015 itself already applied to
  `test_provider`/`discover_models`.
- The fix must be minimal and must not touch `ReadinessService`'s change-detection behaviour,
  since that behaviour is independently correct and already covered by its own tests
  (`test_record_embedding_capability_result_emits_only_on_a_real_change`).
- The shape should reuse an existing, already-shipped pattern rather than invent a new delivery
  mechanism — `test_provider`/`discover_models` (STORY-110) and
  `ResultGateway.regenerate_run_analysis` (STORY-108) already solve "a worker result must reach
  one caller on the graphical thread" with an `on_complete` callback and a `_CompletionRelay`.

## Considered options

- Option A — Give `probe_embedding()` a keyword-only `on_complete: Callable[[bool], None]`
  callback, delivered via the same `_CompletionRelay` pattern `test_provider`/`discover_models`
  already use, running alongside the unchanged `ReadinessService.record_embedding_capability_ result()` call.
- Option B — Make `ReadinessService.record_embedding_capability_result` emit
  unconditionally (drop the change-detection guard) so `probe_embedding` always produces an
  event.
- Option C — Have the embedding-section widget re-read `readiness_snapshot()` on a short poll
  or timer after calling `probe_embedding()`, instead of any push-based completion signal.

## Decision outcome

Chosen option: **Option A**, because it is the only option that gives the one-shot click a
guaranteed completion signal without weakening `ReadinessService`'s independently-correct
cache-emission rule, and because it reuses an already-shipped, already-tested delivery pattern
rather than inventing a new one.

Concretely: `probe_embedding()` gains a keyword-only `on_complete: Callable[[bool], None]`
parameter. Its worker body still calls `ReadinessService.record_embedding_capability_result (reachable=…)` exactly as ADR-0015/STORY-110 already specified — that call keeps owning the
app-wide readiness *state* update and its own conditional `_app_readiness_changed` emission,
untouched. Separately, and in addition, the same worker body's boolean outcome is delivered to
`on_complete`, marshalled onto the graphical thread by a `_CompletionRelay[bool]`, following the
identical `TaskRunner.submit` + `future.add_done_callback` shape `test_provider`/
`discover_models` already use. `EmbeddingSectionWidget._on_test_embedding_clicked` repaints its
diagnostic label directly from this callback's delivered value, giving the click a definite
terminal state regardless of whether `ReadinessService` also emitted an event for the same call.
The existing `_app_readiness_changed` subscription one layer above the widget
(`ProvidersTabController.apply_embedding_diagnostic`) is left wired unchanged — it still
legitimately repaints the same label when a *different* trigger (the on-open `probe_all()`
handshake, or another future readiness source) changes the cached snapshot; the two paths write
to the same widget method and are safe to coexist.

A related, narrower fix landed alongside this one in the same STORY-110 review pass: when
`probe_embedding`'s worker finds the `PROVIDER_TEST` gate busy (`try_acquire` returning `None`),
it must **not** call `record_embedding_capability_result(reachable=False)` at all — gate
contention is a fact about scheduling, not about the embedding endpoint's capability, and
reporting it as `reachable=False` could spuriously downgrade the app-wide `GRADED` run-start
gate over mere contention. That branch now leaves `ReadinessService` untouched (mirroring
`ReadinessService._probe_all_once`'s own gate-refusal branch, which likewise returns the
existing cached snapshot rather than recording a fact it never observed) and reports
`on_complete(False)` for the click's own widget-local terminal repaint only. This is not a
second decision requiring its own ADR — it does not change the shape ADR-0015 fixed, only which
branch of the existing worker body calls the existing `ReadinessService` method — but it depends
on the same `on_complete` callback this ADR adds, since without it the gate-busy click would
otherwise have no completion signal at all.

### Consequences

- Positive — The Test Embedding click always reaches a definite terminal diagnostic state,
  closing a real STORY-110-AC-10 gap (a stuck "Testing…" label) that a second independent
  spec-conformance review caught.
- Positive — `ReadinessService.record_embedding_capability_result`'s emit-only-on-change rule,
  and its existing test coverage, are untouched — this ADR does not touch the store side at all.
- Positive — Reuses the exact `_CompletionRelay`/`TaskRunner` delivery shape already shipped for
  `test_provider`/`discover_models` in the same file, so no new concurrency pattern is
  introduced.
- Negative — `probe_embedding()`'s signature now diverges further from `08-E` §7b.6's verbatim
  text (already diverged by ADR-0015; this ADR adds a parameter ADR-0015 explicitly said would
  not be needed). Both `ui/settings_dialog/protocols.py` and
  `adapters/ui_gateways/protocols.py`'s mirrored signatures must cite this ADR alongside
  ADR-0015 so a future reader finds the full history of the divergence.
- Negative — Two independent signals (the callback and the conditional event) can now legitimately
  disagree about whether "anything changed" for the same call — the callback always fires, the
  event only fires on a real change. Callers must not conflate the two; `on_complete` answers
  "did this click's check finish and what did it find", the event answers "did the app's cached
  readiness fact change".
- Neutral — This ADR does not change how `probe_all()` delivers its result; `08-J` §6 rule 2
  still correctly routes `probe_all`'s batch-wide result through the event bus only, because a
  full re-probe batch is new information worth an event by construction — it is only the
  single-widget, single-click, may-reproduce-a-known-value case that needed a callback.

## Pros and cons of the options

### Option A — Add an `on_complete` callback alongside the unchanged state update

- Good — Guarantees the click a terminal signal without touching `ReadinessService`'s cache
  semantics.
- Good — Reuses an already-shipped, already-tested pattern (`_CompletionRelay`).
- Good — Keeps the two concerns (state update vs. one-click completion) cleanly separated,
  matching `08-J` §6 rule 2's own reasoning.
- Bad — One more divergence from `08-E` §7b.6's verbatim signature, requiring an ADR citation in
  both Protocol copies.

### Option B — Make `record_embedding_capability_result` emit unconditionally

- Good — No new parameter; `probe_embedding()`'s shape stays exactly as ADR-0015 left it.
- Bad — Weakens a store-level guarantee (`ReadinessService` only emits on a real change) for the
  benefit of one caller's one-shot completion signal, when nothing else about the state
  changed — every other subscriber (the New Benchmark widget's `GRADED` gate, the Main Window
  health dots) would now see a redundant, no-op event on every Test Embedding click, even one
  that reproduced an already-known value.
- Bad — Breaks the existing, independently-valuable
  `test_record_embedding_capability_result_emits_only_on_a_real_change` test's guarantee.

### Option C — Poll `readiness_snapshot()` after the click

- Good — No signature change to `probe_embedding()` at all.
- Bad — Introduces a polling/timer mechanism the specification does not call for anywhere else
  in this dialog, adds latency (the label would not repaint the instant the check settles, only
  on the next poll tick), and needs its own cancellation/cleanup handling if the dialog closes
  mid-poll — strictly worse than a callback that already tolerates firing after its widget is
  gone (the `_CompletionRelay` pattern this ADR reuses already handles that).
- Bad — `readiness_snapshot()` alone cannot distinguish "the check I just triggered settled" from
  "some unrelated readiness change happened to land at the same moment", which a callback
  carrying the specific call's own outcome trivially can.

## Links

- Related ADRs: ADR-0015 (settled the general blocking-method delivery shape this ADR narrowly
  corrects for one method), ADR-0014 (housed `adapters/ui_gateways/`)
- Spec clauses: `08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#12-readiness-service`,
  `08_Cross_Cutting/08-J_event_bus_catalog.md#6-when-to-add-a-new-event`,
  `08_Cross_Cutting/08-J_event_bus_catalog.md#57-global-and-app-readiness`,
  `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#66a-embedding-capability-validation-d-r-11-miss-11`
- Stories: STORY-110 applies this decision (AC-11)
