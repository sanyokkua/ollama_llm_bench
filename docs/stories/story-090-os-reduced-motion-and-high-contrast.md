---
id: STORY-090
title: Honor the OS reduced-motion and high-contrast preferences per the accessibility floor
status: superseded
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#8-reduced-motion-and-high-contrast
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#10-verification-method
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#11-accessibility-floor-summary
modules:
  - ui/theme/
  - ui/shared/
acceptance_criteria:
  - STORY-090-AC-1
  - STORY-090-AC-2
  - STORY-090-AC-3
edge_cases: []
depends_on: []
adrs:
  - ADR-0018
owner: coder
estimate: M
---

# STORY-090 — Honor the OS reduced-motion and high-contrast preferences per the accessibility floor

## Goal

**This story will not be implemented. It is retired as `superseded` by
[ADR-0018](../adr/0018-exclude-os-reduced-motion-and-high-contrast-preferences.md) (accepted
2026-08-05).**

The product owner decided that the application will **not** read or honor the operating system's
"Reduce motion" and "Increase contrast" settings. In plain terms: a user who has turned either
setting on at the OS level gets no accommodation from this application. The health-dot "checking"
pulse animates regardless, transitions play regardless, and the theme's soft callout backgrounds
stay soft rather than becoming solid-bordered. No build check verifies either behaviour, and none
will be added.

This is a deliberate deviation from two of the ten requirements the specification calls
release-blocking (`12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §8, §10, §11). ADR-0018 is the
record of that deviation and carries the full reasoning; it supersedes ADR-0012, which had proposed
implementing both preferences and which explicitly made itself conditional on a product-owner
ratification that was ultimately refused. ADR-0018 re-adopts the exclusion first recorded in
ADR-0008.

Nothing else in the accessibility work is affected. Accessible names, stable objectNames, tooltips,
the 24 × 24 px click-target minimum, focus-ring visibility, and the no-custom-shortcut check are all
still required, and are delivered by STORY-089, STORY-091, STORY-097, STORY-098, and STORY-099.

Per the story lifecycle a superseded story keeps its identifier and its file; this file stays in
`docs/stories/` permanently, and its acceptance criteria are retained below unchanged as the record
of what was scoped and dropped. They are not to be implemented.

## In scope

- Nothing. The story is retired.

## Out of scope

- Reading the OS reduced-motion preference and gating transitions and the `HealthDot` pulse on it —
  excluded by ADR-0018.
- Reading the OS high-contrast preference and producing a higher-contrast theme variant —
  excluded by ADR-0018.
- Re-applying either preference live while the application runs — excluded by ADR-0018.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#8-reduced-motion-and-high-contrast` — the
  behaviour ADR-0018 declines to implement: under reduced motion every transition and the
  health-dot pulse are disabled and state changes apply instantly; under high contrast border-width
  emphasis increases and soft `*.fill` backgrounds are replaced with solid borders.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#10-verification-method` — the two verification rows
  that will have no test. STORY-091 implements the other five automated rows of this table.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#11-accessibility-floor-summary` — the summary table
  marking both preferences "Blocks release"; these are the two rows the application knowingly does
  not meet.

## Design constraints

- `08_ACCESSIBILITY_FLOOR.md` is vendored, read-only specification and is **not** edited to match
  this decision. ADR-0018 is the deviation record; the spec still says what it says.
- No further work is scheduled against `ui/theme/` or `ui/shared/` for these preferences. A future
  session that wants to implement them must write a **new** story and a new ADR superseding
  ADR-0018 — this file is not reopened.

## Acceptance criteria

The three criteria below are retained verbatim as the historical record of the dropped scope. They
have no tests and will not get any.

### STORY-090-AC-1

Given the operating system reports a reduced-motion preference, when the interface renders and state
changes occur, then every transition and the `HealthDot` pulse are disabled and state changes apply
instantly. **Not implemented — excluded by ADR-0018.**

### STORY-090-AC-2

Given the operating system reports a high-contrast preference, when the theme is applied, then
border-width emphasis increases and the soft `*.fill` callout backgrounds are replaced with solid
borders. **Not implemented — excluded by ADR-0018.**

### STORY-090-AC-3

Given the application is running, when the operating system's reduced-motion or high-contrast
preference changes, then the corresponding behaviour is re-applied live without a restart.
**Not implemented — excluded by ADR-0018.**

## Test plan

- None. A `superseded` story has no acceptance-criterion tests; the traceability validator requires
  proven acceptance criteria only for a `done` story.

## Definition of done

- [x] ADR-0018 is accepted and records the deviation, its reasoning, and its consequences.
- [x] ADR-0012 is marked `superseded by ADR-0018` and the ADR index reflects the chain.
- [x] STORY-090 is removed from STORY-091's and STORY-093's `depends_on`.
- [x] This file remains in `docs/stories/` with a structurally valid front-matter block.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- Nothing. STORY-090 was named in STORY-091's and STORY-093's `depends_on`; both citations are
  removed in this pass, because a story that will never be `done` would block them forever.
  STORY-091's only remaining dependency is STORY-089.

**What to do on completion**

There is no implementation to complete. The follow-up is bookkeeping, and is done once:

1. Confirm no story's `depends_on` still names STORY-090 (`grep -rn 'STORY-090' docs/stories/`).
   The only remaining references should be prose ones in STORY-089 and STORY-091 explaining the
   exclusion.
1. Re-run `just trace` — the traceability record embeds each story's `status`, and this file's
   status changed — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   The accessibility thread continues at STORY-097 / STORY-098 / STORY-099, which are `ready` and
   have no dependencies.
