# ADR-0011 — Extend the testing standard with an env-gated live tier and a screenshot/mockup-review harness

**Status:** accepted
**Date:** 2026-07-23
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** DD-36

## Context and problem statement

The testing standard (`16_Engineering_Standards/07_TESTING_STANDARD.md`) fixes two rules that the
finalization backlog now needs to extend without breaking:

1. **CI is fully offline and never contacts a live LLM server.** §6a and §7a require the `LLMClient`
   real leg to run against a `pytest-httpserver` wire stub, and §12 states the pull-request gate runs
   under the offscreen Qt platform with no scheduled/nightly workflow (DD-36). Yet the project owner
   explicitly wants proof that the application works against a locally installed Ollama and LM Studio —
   which, by definition, means contacting a real local server.

1. **Visual conformance is defined only as a manual checklist.** `08-R` §2 declares each screen's
   `mockup.html` the visual source of truth, and `08-L` §14 supplies a standardization review
   checklist — but nothing captures what the real Qt widgets render, so the checklist can only be
   applied by eye against a running app, with no persisted artifact.

Both gaps sit at the seam between "what the offline gate can prove" and "what the owner wants
demonstrated." Neither is settled by the specification, and each is a deliberate, potentially
contentious extension of a standard the rest of the project treats as binding — so the decision is
recorded here rather than made silently inside a story.

## Decision drivers

- The offline-CI rule (§6a/§7a/§12, DD-36) must stay intact: the pull-request gate and `just check`
  must remain fully offline and deterministic. Any live-server testing must be strictly opt-in and
  outside the gate.
- The owner's request for real-server proof is a legitimate, recurring need on a machine that actually
  has Ollama and LM Studio installed.
- The mockups are the declared visual source of truth (`08-R` §2), but "the mockup wins" is
  unenforceable without a way to see the real render; a persisted capture plus a checklist-based
  review is the lightest mechanism that makes the rule actionable.
- The mockups are HTML and the widgets are Qt: a pixel-exact gate is neither meaningful nor
  maintainable, so the review must be documented and human-judged, not an automated pixel assertion.
- Adding either capability inside a normal story, with no ADR, would embed a real deviation from the
  testing standard in test code where no one would find the rationale later.

## Considered options

- **Option A — Do neither; keep the standard as written.** Rely on offline fakes and the manual
  checklist only.
- **Option B — Add both as deliberate, documented extensions:** an env-gated `live_local` tier
  (local-only, excluded from CI and `just check`, auto-skipping when absent) and an offscreen
  screenshot/mockup-review harness (captures every screen in both themes plus a checklist-based
  findings report), each honouring the letter of the offline-CI and mockup-source-of-truth rules.
- **Option C — Add the live tier but not the harness (or vice versa).**

## Decision outcome

Chosen option: **Option B** — add both, as explicit extensions of the testing standard, with these
boundaries:

1. **Env-gated live tier.** A new `live_local` pytest marker tier, selected only when its opt-in
   environment variable is set, lives at the top-level `tests/` tree and is excluded from `just check`
   and the CI gate. Per local provider (Ollama and LM Studio, both via the OpenAI-compatible adapter)
   it probes health, discovers models, and executes one tiny real benchmark run. It auto-skips cleanly
   when the opt-in variable is unset or the server is unreachable (bounded connection timeout). This
   honours the letter of the offline-CI rule (§6a/§7a/§12, DD-36): the offline gate never contacts a
   live server; the live proof is a separate, opt-in, local-only surface. Owned by STORY-086.

1. **Screenshot / mockup-review harness.** A new offscreen-Qt harness renders every screen in the
   `08-R` §2 screen index in both the Light and Dark themes to PNGs in an artifacts directory, plus a
   documented findings report that walks the `08-L` §14 standardization review checklist per screen
   against its `mockup.html`. It is a review tool and process artifact, not a pass/fail pixel gate —
   discrepancies it surfaces become their own follow-up stories. Owned by STORY-087.

### Consequences

- Positive — The owner gets reproducible proof against real local Ollama and LM Studio, and a
  persisted, checklist-driven visual conformance review, while the offline pull-request gate and
  `just check` stay exactly as deterministic and offline as before.
- Negative — Two test surfaces now sit outside the offline gate and are only as useful as the operator
  who runs them locally; the live tier's pass depends on the local environment, and the harness's
  findings depend on human review.
- Neutral — The testing standard is extended, not amended: the vendored spec is unchanged; this ADR is
  the record of the extension, cited by the two stories that implement it.

## Pros and cons of the options

### Option A — Keep the standard as written

- Good — Zero new surfaces; the gate stays minimal.
- Bad — Leaves the owner's real-server need unmet and the mockup-source-of-truth rule unenforceable in
  practice.

### Option B — Add both, as documented opt-in extensions

- Good — Meets both needs while preserving the offline-CI and mockup-authority rules verbatim; the
  rationale is recorded where a future reader will find it.
- Bad — Adds two surfaces the gate does not run, so their value depends on local, on-demand execution.

### Option C — Add only one of the two

- Good — Smaller change.
- Bad — Leaves one of the two genuine gaps open; both were explicitly requested, and both share the
  same "deliberate extension of the testing standard" character, so recording them together is
  clearer than splitting the rationale.

## Links

- Spec clauses: `16_Engineering_Standards/07_TESTING_STANDARD.md#6a-shared-contract-test-suite-per-protocol`,
  `16_Engineering_Standards/07_TESTING_STANDARD.md#7a-the-provider-wire-stub-transport-level-test-double`,
  `16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment`,
  `16_Engineering_Standards/07_TESTING_STANDARD.md#3-test-layout`,
  `08_Cross_Cutting/08-R_screen_index_and_traceability.md#2-screen-index--every-mockup-and-its-drawn-states`,
  `08_Cross_Cutting/08-L_ui_standardization.md#14-standardization-review-checklist`
- Stories: STORY-086 (env-gated live tier), STORY-087 (screenshot / mockup-review harness)
