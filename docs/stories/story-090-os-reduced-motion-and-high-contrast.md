---
id: STORY-090
title: Honor the OS reduced-motion and high-contrast preferences per the accessibility floor
status: draft
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
  - ADR-0012
owner: coder
estimate: M
---

# STORY-090 — Honor the OS reduced-motion and high-contrast preferences per the accessibility floor

## Goal

Meet the two remaining release-blocking accessibility-floor requirements that ADR-0008 previously
excluded and ADR-0012 now reinstates. When the operating system reports a reduced-motion preference,
the application disables every transition and the health-dot pulse and applies state changes
instantly. When the operating system reports a high-contrast preference, the theme increases
border-width emphasis and replaces the soft `*.fill` callout backgrounds with solid borders. Both
preferences are read at launch and re-applied live if the OS setting changes while the application
runs, with no restart.

## In scope

- Reading the OS reduced-motion preference (via Qt's style hints) in `ui/theme/` and gating every
  transition on it, so state changes apply instantly with all motion off; disabling the
  `HealthDot` "checking" pulse in `ui/shared/` under the same preference.
- Reading the OS high-contrast preference in `ui/theme/` and, when set, increasing border-width
  emphasis and replacing the soft `*.fill` callout backgrounds with solid borders.
- Re-applying both preferences live when the OS setting changes while the application is running.

## Out of scope

- The accessibility-floor verification suite (the two §10 tests plus the other floor checks) —
  owned by STORY-091; this story delivers the behaviour those tests assert.
- Accessible names, objectNames, and tooltips — owned by STORY-089 and its children.
- Text/display scaling (§9) — already honoured through the token system; not part of this story.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#8-reduced-motion-and-high-contrast` — the exact
  behaviour: under reduced motion every transition and the health-dot pulse are disabled and state
  changes apply instantly; under high contrast border-width emphasis increases and soft `*.fill`
  backgrounds are replaced with solid borders; both are read at launch and re-applied live.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#10-verification-method` — the two verification
  rows this story's behaviour must satisfy (reduced-motion and high-contrast preference tests).
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#11-accessibility-floor-summary` — both preferences
  are enforcement "Blocks release".

## Design constraints

- Only `ui/theme/` calls `setStyleSheet` and owns tokens; the high-contrast variant is produced
  there, not in individual widgets.
- No colour literal outside `ui/theme/`; no `asyncio`.
- The health-dot pulse is gated by the reduced-motion preference read through the theme module, not
  by a per-widget flag duplicated in `ui/shared/`.
- This reverses a prior product-owner decision (ADR-0008) and applies ADR-0012; ADR-0012 requires
  product-owner ratification before this story moves from `draft` to `ready`.

## Acceptance criteria

### STORY-090-AC-1

Given the operating system reports a reduced-motion preference, when the interface renders and state
changes occur, then every transition and the `HealthDot` pulse are disabled and state changes apply
instantly.

### STORY-090-AC-2

Given the operating system reports a high-contrast preference, when the theme is applied, then
border-width emphasis increases and the soft `*.fill` callout backgrounds are replaced with solid
borders.

### STORY-090-AC-3

Given the application is running, when the operating system's reduced-motion or high-contrast
preference changes, then the corresponding behaviour is re-applied live without a restart.

## Test plan

- STORY-090-AC-1 — integration (`pytest-qt`, offscreen), `tests/integration/test_reduced_motion.py`,
  `test_reduced_motion_disables_transitions_and_health_dot_pulse`.
- STORY-090-AC-2 — integration (`pytest-qt`, offscreen), `tests/integration/test_high_contrast.py`,
  `test_high_contrast_increases_borders_and_replaces_soft_fills`.
- STORY-090-AC-3 — integration (`pytest-qt`, offscreen), same files,
  `test_preference_change_reapplies_live_without_restart`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-090.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] ADR-0012 is ratified by the product owner before this story leaves `draft`.
