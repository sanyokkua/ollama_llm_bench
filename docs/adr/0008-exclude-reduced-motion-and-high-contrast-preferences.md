# ADR-0008 — Exclude OS reduced-motion and high-contrast preferences from the theme module

**Status:** accepted
**Date:** 2026-07-18
**Deciders:** owner (product), architect
**Supersedes:** —
**Superseded by:** —

## Context and problem statement

`12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §8 and §11 name reading and honouring two
operating-system accessibility preferences — reduced motion and high contrast — as part of the
accessibility floor, and call both requirements release-blocking. STORY-050 (`ui/theme/`) was
scoped with AC-5 (reduced-motion: instant repaint, no health-dot pulse) and AC-6 (high-contrast:
increased border-width emphasis, solid borders replacing soft `*.fill` backgrounds) to satisfy
that floor.

By the time STORY-050's other four acceptance criteria (theme selection, live OS switching,
explicit-override behaviour, and the WCAG AA contrast matrix) were implemented and tested, AC-5
and AC-6 had zero implementation and zero test coverage — `traceability.yaml` showed empty
`tests: []` for both. STORY-051's `HealthDot` pulse likewise ships unconditionally, with its own
story notes flagging that reduced-motion gating was never wired in. Should the project close this
gap by implementing AC-5/AC-6 now, or accept a permanent, documented deviation from the
accessibility floor as written?

## Decision drivers

- The application is explicitly scoped as mouse-only with no keyboard-accessibility layer
  (`00_Foundation/05_CONSTRAINTS.md`); the accessibility floor already accepts a reduced target
  or this product (`08_ACCESSIBILITY_FLOOR.md` §4, DD-52). Reduced-motion/high-contrast handling
  is the next accessibility layer beyond that already-reduced floor.
  - A change to an already-`Accepted` spec clause (the floor's §8/§11 release-blocking language)
    that a `done` story would depend on requires an ADR recording the deviation and its
    reasoning (`04_ADR_FORMAT.md` §2), not a silent story edit.
- Cost of finishing the work now versus cost of leaving it permanently unimplemented, given no
  other Phase 9/10 story or consumer currently depends on either preference being honoured.
- Avoiding repeated re-litigation: without a durable record, a future session re-reading
  STORY-050/051's citations of `08-D §12`/`§15` and the floor document would reasonably conclude
  the gap is a defect to fix, not a decision to respect.

## Considered options

- Option A — Implement AC-5 (reduced motion) and AC-6 (high contrast) now, closing the floor gap
  as originally scoped.
- Option B — Permanently exclude reduced-motion and high-contrast preference handling from the
  application, record the deviation in this ADR, and amend STORY-050/051 accordingly.
- Option C — Defer indefinitely with no formal decision, leaving AC-5/AC-6 as open items on an
  `in-progress` STORY-050.

## Decision outcome

Chosen option: **Option B**, because the product owner made an explicit, informed decision to
accept this deviation rather than fund the remaining implementation, and Option C's status quo —
an indefinitely `in-progress` STORY-050 with silently stale front-matter — was already blocking
Phase 10 bootstrap and would keep recurring as a source of confusion without a durable record of
*why* the gap exists and that it is intentional.

### Consequences

- Positive — STORY-050 and STORY-051 can close cleanly; Phase 10 is no longer blocked on
  finishing an accessibility surface nobody has asked to use yet. Future sessions reading the
  story notes or this ADR see a decision, not an unexplained gap.
- Negative — The application ships in permanent, acknowledged non-conformance with
  `08_ACCESSIBILITY_FLOOR.md` §8/§11 for these two preferences; a user who relies on OS
  reduced-motion or high-contrast settings gets no accommodation from this application. The
  `HealthDot` "checking" pulse (STORY-051-AC-2) always animates, and no build check ever verifies
  the floor's reduced-motion/high-contrast rows — those two rows of the §11 summary table are
  now permanently unenforceable by this codebase.
- Neutral — `08_ACCESSIBILITY_FLOOR.md` itself is not edited (it is vendored, read-only spec);
  this ADR is the record of the accepted deviation, not a correction to the spec document.

## Pros and cons of the options

### Option A — Implement AC-5/AC-6 now

- Good — Full accessibility-floor conformance as originally specified; no deviation to record.
- Bad — Nontrivial new work (OS `QStyleHints` preference plumbing, a reduced-motion gate on every
  transition and the health-dot pulse, a high-contrast QSS variant) for a requirement no current
  consumer exercises; keeps blocking Phase 10 while it's built.

### Option B — Permanently exclude, record in an ADR

- Good — Unblocks Phase 10 immediately; the decision and its rationale survive for future
  contributors; matches the product owner's explicit instruction.
- Bad — Accepts a known, permanent accessibility gap against the spec's stated floor.

### Option C — Defer with no formal decision

- Good — No immediate work, no ADR overhead.
- Bad — Leaves STORY-050 `in-progress` indefinitely, re-blocks every future phase-readiness check,
  and gives no future session a way to distinguish "not done yet" from "decided against."

## Links

- Related ADRs: —
- Spec clauses: `docs/v3_specification/12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §8, §11;
  `docs/v3_specification/08_Cross_Cutting/08-D_color_palette_and_typography.md` §12, §15
- Stories: STORY-050, STORY-051
