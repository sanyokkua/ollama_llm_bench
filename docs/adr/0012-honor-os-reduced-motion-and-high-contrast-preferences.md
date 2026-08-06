# ADR-0012 — Honor the OS reduced-motion and high-contrast preferences to meet the release-blocking accessibility floor

**Status:** superseded by ADR-0018
**Date:** 2026-07-23
**Deciders:** architect (finalization backlog) — requires product-owner ratification
**Supersedes:** ADR-0008
**Superseded by:** ADR-0018

## Context and problem statement

`12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` is the mandatory accessibility floor, and it is
explicit that a build failing any floor requirement does not ship (§1, "The floor is
release-blocking"). Two of the ten floor requirements are honoring the operating system's
reduced-motion and high-contrast preferences:

- §8 states the application "reads and respects" both preferences: under reduced motion "every
  transition and the health-dot pulse animation are disabled; state changes apply instantly", and
  under high contrast "the theme module increases border-width emphasis and replaces the soft
  `*.fill` callout backgrounds with solid borders". Both are read at launch and re-applied live.
- §10 assigns each a concrete verification test ("A test sets the reduced-motion preference and
  asserts transitions and the health-dot pulse are disabled"; "A test sets the high-contrast
  preference and asserts border emphasis increases and soft fills are replaced").
- §11's summary table lists both rows with an Enforcement of **"Blocks release"**.

ADR-0008 (2026-07-18) recorded an accepted decision to **permanently exclude** exactly these two
preferences, taken during Phase-10 bootstrap to unblock that phase rather than fund the remaining
implementation. That deviation left the application in acknowledged, permanent non-conformance with
the release-blocking floor.

The finalization backlog (Phase 12 in the phase breakdown) exists specifically to "verify the
accessibility floor's 10 release-blocking requirements" before the product can ship. At that gate,
a permanent exclusion of two release-blocking floor rows is no longer tenable: either the floor
requirement is met, or the product cannot pass its own stated release gate. This ADR re-derives the
requirement from the spec, finds it genuinely mandatory, and reverses ADR-0008.

## Decision drivers

- The accessibility floor is the single source of truth and marks both preferences release-blocking
  (§8, §10, §11); the spec is authoritative and is not silently overridden.
- Phase 12's definition of done requires the ten floor requirements to be verifiably in place; two
  permanently-excluded rows would make that gate unachievable as written.
- ADR-0008's driver was cost/scheduling at an earlier phase ("rather than fund the remaining
  implementation"), not a finding that the spec makes the preferences optional — so its rationale
  does not survive contact with the release gate.
- A superseding ADR (not a silent story edit) is the required mechanism to reverse a prior accepted
  decision that a `done` story depended on (`04_ADR_FORMAT.md`; the ADR lifecycle in
  `traceability-and-stories.md`).

## Considered options

- **Option A — Keep ADR-0008's permanent exclusion.** Ship in acknowledged non-conformance with two
  release-blocking floor rows; accept that Phase 12's floor-verification gate can never fully pass.
- **Option B — Supersede ADR-0008 and implement both preferences** as the floor specifies, with the
  two §10 verification tests, before the release gate. Owned by STORY-090 (implementation) and
  covered by STORY-091 (the floor verification suite).

## Decision outcome

Chosen option: **Option B**. Honor the OS reduced-motion and high-contrast preferences per
`08_ACCESSIBILITY_FLOOR.md` §8, read at launch and re-applied live, with the two §10 verification
tests in place, so the accessibility floor's release-blocking requirements are all met. ADR-0008 is
superseded; its file is retained per the ADR lifecycle, and any story that already cited it keeps
that citation.

This decision reverses a prior **product-owner** cost decision (ADR-0008) on the strength of the
spec's release-blocking language and the finalization phase's mandate. It is recorded as accepted so
STORY-090 can cite it, but it **requires product-owner ratification** before STORY-090 moves from
`draft` to `ready`: the owner may instead choose to keep the exclusion and formally narrow the
floor, in which case this ADR would itself be superseded.

> **Superseded by ADR-0018 (2026-08-05).** The product-owner ratification this ADR made a
> precondition was refused: the owner chose the branch named directly above — keep the exclusion —
> so the application will ship without honoring the OS reduce-motion and increase-contrast
> settings, in deliberate, recorded non-conformance with two of the floor's ten release-blocking
> requirements. ADR-0018 is that record; it re-adopts ADR-0008's exclusion as a product decision.
> STORY-090 is retired as `superseded` and STORY-091 keeps its five checks, none of which ever
> covered motion or contrast. This body is retained unedited below the status line, per the ADR
> lifecycle; only the `Status`/`Superseded by` lines and this note record the supersession.

### Consequences

- Positive — The accessibility floor's two remaining release-blocking rows become satisfiable and
  verifiable; Phase 12's floor-verification gate can pass; users who rely on OS reduced-motion or
  high-contrast settings get the accommodation the floor promises.
- Negative — Reintroduces the implementation work ADR-0008 deferred: OS-preference plumbing (Qt
  `QStyleHints`), a reduced-motion gate on every transition and the health-dot pulse, and a
  high-contrast QSS variant. The `HealthDot` pulse (STORY-051) must become conditional.
- Neutral — `08_ACCESSIBILITY_FLOOR.md` is vendored and unchanged; this ADR is the record of the
  reversal, not a spec edit. Pending product-owner ratification, the direction could change.

## Pros and cons of the options

### Option A — Keep the permanent exclusion (ADR-0008)

- Good — No new work; Phase 10's closure stays as-is.
- Bad — The product cannot pass its own release-blocking accessibility floor as written; the gap is
  permanent and unenforceable.

### Option B — Supersede and implement

- Good — Meets the release-blocking floor; makes the §10 verification tests achievable; aligns the
  product with the authoritative spec.
- Bad — Costs the deferred implementation work; reverses a product-owner decision and so needs
  explicit ratification.

## Links

- Related ADRs: supersedes ADR-0008; superseded by ADR-0018.
- Spec clauses: `docs/v3_specification/12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §8, §10, §11.
- Stories: STORY-090 (implementation), STORY-091 (accessibility floor verification suite).
