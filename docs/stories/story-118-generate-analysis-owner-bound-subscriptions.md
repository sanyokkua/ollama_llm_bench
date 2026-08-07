---
id: STORY-118
title: Bind the Generate Analysis dialog's event-bus subscriptions to its own lifetime
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-J_event_bus_catalog.md#2-subscription-ownership-binding-rule
  - 07_Common_Dialogs/generate_analysis_dialog.md#8-confirm-behaviour-and-the-single-inference-gate
  - 07_Common_Dialogs/generate_analysis_dialog.md#81-live-progress-line-during-the-analysis-call
  - 16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md#2-the-error-category-model
modules:
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-118-AC-1
  - STORY-118-AC-2
  - STORY-118-AC-3
  - STORY-118-AC-4
edge_cases: []
depends_on:
  - STORY-065
  - STORY-089
adrs: []
owner: coder
estimate: M
---

# STORY-118 — Bind the Generate Analysis dialog's event-bus subscriptions to its own lifetime

## Goal

Clicking **Generate analysis** / **Regenerate analysis** in the shipped application must open
the dialog instead of terminating the process. Today the dialog registers its three event-bus
subscriptions without naming an owner; the real event bus rejects an owner-less subscription as
a programmer error, so the dialog crashes the app the moment it is constructed against the real
bus. This story makes each subscription owned by the dialog, so it is accepted at subscribe time
and automatically cancelled when the dialog is destroyed, and removes the three test doubles
that have been hiding the defect.

## In scope

- `ui/common_dialogs/_internal/generate_analysis_view.py`: pass the dialog itself as the owner
  on all three `event_bus.subscribe(...)` calls in `GenerateAnalysisDialog.__init__`
  (`_inference_activity_changed`, `_inference_progress`, `_run_analysis_received`).
- Removing the two harness workarounds that exist only because of this defect, so both harnesses
  build the dialog against the application's real event bus:
  - `_StubGenerateAnalysisEventBus` in `tests/integration/conftest.py` and the
    `event_bus=_StubGenerateAnalysisEventBus()` override at its single call site;
  - `_GenerateAnalysisEventBusFake` (and its `_NoOpGenerateAnalysisSubscription`) in
    `tests/e2e/test_icon_only_registry_conformance.py`, together with the
    `msgspec.structs.replace(..., event_bus=...)` line that installs it.
- Tightening the colocated unit double `_FakeEventBus` in
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_generate_analysis_dialog.py` so it rejects a
  `None` owner exactly as the real bus does, so the unit tier can never re-mask this class of
  defect.
- A repository-wide architecture guard that fails the gate if any `src/` call site subscribes
  without an owner again.

## Out of scope

- Any other behaviour of the Generate Analysis dialog — the gate-busy message, the live progress
  line's two sub-states, the `JudgeTimeoutExhausted` sub-state, and the default-selection rule
  are owned by STORY-065 and are not re-specified here.
- Changing `QtEventBusDeliverer` or its precondition — the contract in
  `adapters/qt_event_bus/` is correct as written; the dialog is the defect.
- The other findings recorded in STORY-087's Findings section (missing style-role rules, raw
  `provider_id` UUIDs in Run Summary, Task Editor role properties) — each is owned by its own
  story.

## Spec inputs

- `08_Cross_Cutting/08-J_event_bus_catalog.md#2-subscription-ownership-binding-rule` — every
  `subscribe` call MUST pass an owner whose lifetime bounds the subscription; a widget subscribes
  with itself as the owner; a subscription with no owner is a programming error rejected at
  subscribe time; destroying the owner *is* the unsubscribe.
- `07_Common_Dialogs/generate_analysis_dialog.md#8-confirm-behaviour-and-the-single-inference-gate`
  — the dialog subscribes to `_inference_activity_changed` and must stay open and usable when the
  gate is held, which is only possible if the subscription is accepted at construction time.
- `07_Common_Dialogs/generate_analysis_dialog.md#81-live-progress-line-during-the-analysis-call`
  — the live progress line is driven by the dialog's `_inference_progress` subscription, and that
  subscription is cleared on the dialog's terminal event; owner-binding is what guarantees the
  clearing when the dialog goes away.
- `16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md#2-the-error-category-model` — a
  contract violation is the programmer-error category: it is never caught, it reaches the user
  only as a crash dialog, and it crashes the app. This is why the missing owner is a live crash
  and not a cosmetic omission.

## Design constraints

- The owner passed must be the `QDialog` instance itself. `GenerateAnalysisDialog` is a
  `QObject`, so the real deliverer binds cancellation to its `destroyed` signal; a non-`QObject`
  owner would instead be bound through `weakref.finalize`, which is the wrong lifetime for a
  widget.
- The existing per-signal `Subscription` handles the dialog already stores stay as they are —
  owner-binding is additional to, not a replacement for, explicit cancellation.
- `ui/common_dialogs/` is a passive presentation module: it holds no domain logic and must not
  grow a new public API symbol for this fix.
- The two proving tests that need the real `QtEventBusDeliverer` live under `tests/integration/`
  and `tests/e2e/`, **not** in the module's colocated `tests/` directory — the UI gate-access
  architecture scan covers colocated `ui/**/tests/` files, and a colocated test wiring a real
  adapter would trip it.
- The e2e test must never call `exec()` on the dialog. Use the already-established non-blocking
  pattern from `tests/e2e/test_icon_only_registry_conformance.py`: `QTimer.singleShot` schedules
  the dismissal before the click that opens the modal. A blocking modal in a test produces no
  output at all and hangs the whole suite.
- `tests/integration/conftest.py` is a shared fixture file. Changing it puts the entire suite in
  the blast radius, so the full `just check` gate — not a module-scoped run — is the verification
  for this story.
- Note for the implementer: `.claude/rules/pyside6-app-development.md` describes this rule using
  the older `subscribe_to_*(..., parent=self)` spelling. The real, current surface is
  `subscribe(signal_name, handler, owner=...)`; follow the code and `08-J` §2, not the stale
  spelling in the rule file.

## Acceptance criteria

### STORY-118-AC-1

Given a real `QtEventBusDeliverer` instance,
when a `GenerateAnalysisDialog` is constructed with that deliverer as its `event_bus`
collaborator,
then construction completes and raises no `icontract.errors.ViolationError`.

### STORY-118-AC-2

Each of the dialog's three subscriptions is bound to the dialog's own lifetime, so delivery
follows the owner:

| Signal                        | Emitted while the dialog is alive | Emitted after the dialog is destroyed |
| ----------------------------- | --------------------------------- | ------------------------------------- |
| `_inference_activity_changed` | the dialog's handler runs         | the dialog's handler does not run     |
| `_inference_progress`         | the dialog's handler runs         | the dialog's handler does not run     |
| `_run_analysis_received`      | the dialog's handler runs         | the dialog's handler does not run     |

### STORY-118-AC-3

Given the fully assembled application showing the Result widget's Run Analysis tab for a run,
wired to the application's own real event bus with no test double substituted,
when the user clicks **Generate analysis**,
then the Generate Analysis dialog becomes visible and the application is still running.

### STORY-118-AC-4

For every call to `subscribe(...)` on an event bus anywhere under `src/ollama_llm_bench/`
— excluding the two declarations of `subscribe` itself, in `backend/events/protocols.py` and
`adapters/qt_event_bus/_internal/deliverer.py` — the call passes an `owner` argument.

## Test plan

- STORY-118-AC-1 — integration, `tests/integration/test_generate_analysis_real_event_bus.py`,
  `test_dialog_constructs_against_the_real_event_bus`. Builds a real `QtEventBusDeliverer` and
  constructs the dialog through `make_generate_analysis_dialog`. Negative control: temporarily
  drop the `owner` argument in the source and confirm the test fails with
  `icontract.errors.ViolationError` — do not "prove" this by deleting the assertion.
- STORY-118-AC-2 — integration, same file,
  `test_dialog_subscriptions_are_bound_to_dialog_lifetime`, one
  `@pytest.mark.parametrize` case per signal in the AC-2 table. Emits each signal once with the
  dialog alive and once after `deleteLater()` plus a `qtbot` round-trip, asserting the handler
  ran only the first time.
- STORY-118-AC-3 — e2e, `tests/e2e/test_generate_analysis_button_opens_dialog.py`,
  `test_generate_analysis_button_opens_dialog_with_the_real_event_bus`. Uses the existing
  assembled-app e2e fixture with no event-bus substitution, schedules the dismissal with
  `QTimer.singleShot` before clicking, and asserts the dialog is visible.
- STORY-118-AC-4 — architecture,
  `tests/architecture/test_event_bus_subscription_ownership.py`,
  `test_every_subscribe_call_site_passes_owner`. AST-walks `src/ollama_llm_bench/`, collects every
  `Call` whose function attribute is `subscribe`, skips the two `FunctionDef` declarations named
  in AC-4, and asserts each remaining call carries an `owner` keyword.
- No `edge_cases:` entries: this story restores specified behaviour on the happy path and adds no
  new error condition of its own. The dialog's own edge cases (EC-GA-\*) remain owned by
  STORY-065.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-118.
- [ ] `_StubGenerateAnalysisEventBus` and `_GenerateAnalysisEventBusFake` no longer exist, and
  both harnesses build the dialog against the real event bus.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/common_dialogs/`.
- [ ] The full `just check` gate is green — required, not optional, because
  `tests/integration/conftest.py` is a shared fixture.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
