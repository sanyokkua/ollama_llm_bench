# ADR-0018 — Ship without honoring the OS reduced-motion and high-contrast preferences

**Status:** accepted
**Date:** 2026-08-05
**Deciders:** owner (product), architect
**Supersedes:** ADR-0012
**Superseded by:** —

## Context and problem statement

`12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` defines ten accessibility requirements and states
that all ten are release-blocking: "A build that fails any floor requirement does not ship"
(§1). Two of the ten are about operating-system accessibility preferences. §8 says the application
"reads and respects" them: under a reduced-motion preference "every transition and the health-dot
pulse animation are disabled" and state changes apply instantly; under a high-contrast preference
the theme "increases border-width emphasis and replaces the soft `*.fill` callout backgrounds with
solid borders". §10 assigns each its own verification test, and §11's summary table marks both
"Blocks release".

This decision has already been taken twice, in opposite directions. ADR-0008 (2026-07-18, product
owner and architect) permanently excluded both preferences to unblock Phase 10, accepting the
non-conformance on the record. ADR-0012 (2026-07-23, architect, during finalization-backlog
planning) reversed that: it argued the spec's release-blocking language was genuinely mandatory,
superseded ADR-0008, and scoped STORY-090 to implement both preferences. ADR-0012 was written
explicitly conditional — its own text says it "requires product-owner ratification before STORY-090
moves from `draft` to `ready`", and that "the owner may instead choose to keep the exclusion and
formally narrow the floor, in which case this ADR would itself be superseded."

The product owner has now made that call, and it is the opposite of ADR-0012's proposal. So: does
the application implement the OS reduced-motion and high-contrast preferences before release, or
does it ship knowingly without them?

## Decision drivers

- **The ratification ADR-0012 required was never granted, and has now been refused.** ADR-0012 was
  an architect's re-derivation from the spec, not a product decision; it named the product owner as
  the deciding authority and named refusal as an anticipated outcome. Refusal is the anticipated
  branch, not an override of a settled decision.
- **The deviation must be visible, not buried.** The floor is stated as release-blocking, so a
  decision not to meet two of its ten requirements has to be recorded somewhere a future
  contributor will find it before re-litigating it for a third time. That is the primary purpose of
  this ADR.
- **The cost is real and was never funded.** Honoring the preferences means new OS-preference
  plumbing (Qt `QStyleHints`), a live re-apply path when the preference changes at runtime, a
  reduced-motion gate threaded through every transition and the `HealthDot` pulse, and a
  high-contrast variant of the whole token/QSS surface — plus the two §10 verification tests. None
  of it is exercised by any existing consumer.
- **The rest of the accessibility work is not affected and stays mandatory.** Accessible names,
  stable objectNames, tooltips, the 24 × 24 px click-target minimum, focus-ring visibility, and the
  no-custom-shortcut check are independent of OS preference handling and remain in scope.

## Considered options

- **Option A — Implement both preferences** as ADR-0012 proposed (STORY-090), meeting all ten floor
  requirements before release.
- **Option B — Ship without them**, re-adopting ADR-0008's exclusion, superseding ADR-0012,
  retiring STORY-090 as `superseded`, and recording the two-requirement deviation here.
- **Option C — Implement only reduced motion** (the cheaper of the two, since the application's
  motion surface is small) and exclude high contrast.

## Decision outcome

Chosen option: **Option B**. The application will **not** read or honor the operating system's
reduce-motion and increase-contrast settings, in this release or any planned one. ADR-0012 is
superseded and ADR-0008's exclusion is re-adopted, now as a first-class product decision rather
than a phase-unblocking expedient.

**Stated plainly, because the whole point of this record is that the deviation is on the file:** the
application knowingly ships in non-conformance with two of the ten requirements its own
specification calls release-blocking (`08_ACCESSIBILITY_FLOOR.md` §8, §10, §11). A user who has
turned on "Reduce motion" or "Increase contrast" at the OS level gets no accommodation from this
application: the `HealthDot` "checking" pulse animates regardless, transitions play regardless, and
the theme's soft `*.fill` callout backgrounds stay soft. No build check verifies either row, and
none will be added; the §11 summary table's "Blocks release" enforcement is, for those two rows,
not enforced by this codebase.

The remaining eight floor requirements are unaffected and still required. In particular the
accessible-name, objectName, tooltip, click-target, focus-ring, and no-shortcut work continues
exactly as scoped (STORY-089, STORY-091, STORY-097, STORY-098, STORY-099). Those items sit under
the "accessibility" heading largely by filing accident — what they actually deliver is controls
that describe themselves and can be addressed by name from a test, which is a testability and
maintainability property this project depends on regardless of any accessibility target.

### Consequences

- Positive — No OS-preference plumbing, no live re-apply path, no high-contrast token variant, and
  no `HealthDot` pulse conditionality to build or maintain. STORY-090 retires; STORY-091 loses a
  dependency and becomes reachable as soon as STORY-089 is `done`. The decision stops being
  re-litigated once per phase.
- Negative — A permanent, knowing accessibility gap. Users relying on OS motion or contrast
  settings are not served. The project cannot truthfully claim it meets its own accessibility
  floor, and any future statement about the floor must carry this exception. Reversing this later
  costs strictly more than doing it now, because the theme and animation surfaces will have grown.
- Neutral — `08_ACCESSIBILITY_FLOOR.md` is vendored, read-only spec and is **not** edited; this ADR
  is the deviation record, not a correction to the specification. STORY-090's file stays in
  `docs/stories/` permanently with `status: superseded`, per the story lifecycle.

## Pros and cons of the options

### Option A — Implement both preferences (ADR-0012's proposal)

- Good — Full conformance with the floor as written; nothing to disclose; the §10 verification
  tests become achievable.
- Bad — Funds work no current consumer exercises, at the point in the schedule where the remaining
  budget is aimed at packaging and release; reverses a decision the product owner had already taken
  once, without the product owner asking for it.

### Option B — Ship without them, record the deviation

- Good — Matches the product owner's explicit instruction; frees the finalization backlog;
  the reasoning and the exact scope of the gap survive in one findable place.
- Bad — Accepts a permanent, acknowledged failure against two release-blocking requirements, and
  makes any future accessibility claim conditional on this footnote.

### Option C — Reduced motion only

- Good — Cheaper than Option A; removes the most user-visible motion complaint (the pulsing dot).
- Bad — Still non-conformant, so it buys none of Option A's "no disclosure needed" benefit while
  paying part of its cost; leaves a half-implemented OS-preference layer that invites the same
  question again next phase.

## Links

- Related ADRs: supersedes ADR-0012; re-adopts the exclusion originally recorded in ADR-0008.
- Spec clauses: `docs/v3_specification/12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §8, §10, §11;
  `docs/v3_specification/08_Cross_Cutting/08-D_color_palette_and_typography.md` §12, §15.
- Stories: STORY-090 (retired as `superseded` by this decision), STORY-091 (accessibility-floor
  verification suite, which never covered motion or contrast and is unchanged in substance),
  STORY-050 and STORY-051 (the original `ui/theme/` and `HealthDot` stories whose AC-5/AC-6 gap
  started this thread).
