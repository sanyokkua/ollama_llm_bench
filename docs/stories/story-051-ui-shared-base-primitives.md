---
id: STORY-051
title: Provide the shared visual primitives that render status by theme role plus text or glyph
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-L_ui_standardization.md#8-verdict-and-status-colours
  - 08_Cross_Cutting/08-L_ui_standardization.md#9-iconography
  - 08_Cross_Cutting/08-L_ui_standardization.md#6-button-styles
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#5-verdict-palette
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#6-health-palette
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/shared/
acceptance_criteria:
  - STORY-051-AC-1
  - STORY-051-AC-2
  - STORY-051-AC-3
  - STORY-051-AC-4
depends_on:
  - STORY-049
  - STORY-050
adrs:
  - ADR-0001
owner: coder
estimate: M
---

# STORY-051 — Provide the shared visual primitives that render status by theme role plus text or glyph

## Goal

Deliver the reusable, pure-presentation primitives that every Phase 10 widget composes from —
`BadgeLabel`, `HealthDot`, and `MultiCheckFilterButton` — so status, verdict, health, and
multi-select filtering have one canonical form across the application. Each primitive resolves
its appearance from theme roles, never a literal, and never uses colour as the sole channel:
every state it shows by colour is paired with a text label and/or glyph, so the interface stays
legible in greyscale and for colour-blind users.

## In scope

- `make_badge_label(...)` — a badge/pill that renders a semantic status (pass, fail, warning,
  info, neutral) by setting the theme role dynamic-property and showing the accompanying text.
- `make_health_dot(...)` — a status dot for provider/embedding health that resolves the 08-D §6
  health colour per state, is shown with a text label, and pulses (opacity animation) in the
  "checking" state subject to the reduced-motion rule.
- `make_multi_check_filter_button(...)` — a button that opens a multi-check option set, reflects
  the checked count in its label, and emits a selection-changed signal.
- Each primitive expresses appearance through theme role dynamic-properties only (no
  `setStyleSheet`), and custom-painted primitives repaint on a theme change.

## Out of scope

- The design tokens, the QSS generator, and the theme-changed notification transport — owned by
  STORY-049 and STORY-050; these primitives consume them.
- The provider and model dropdown sub-packages — owned by STORY-052.
- The concrete widgets that embed these primitives (Progress stability panel, Results verdict
  cells, Resume table) — later Phase 10 stories.

## Spec inputs

- `08-L §8 (#8-verdict-and-status-colours)` — the semantic role each status maps to (pass →
  `success.base`, warning → `warning.base`, fail → `error.base`, pending/neutral → `muted.base`,
  informational → `info.base`) and the binary-verdict / pending-is-not-a-verdict rule.
- `08-L §9 (#9-iconography)` — the fixed glyph meanings and the rule that a status glyph is
  always paired with a text label where the status is decision-relevant; colour and glyph alone
  are never the sole channel; theme-tinted icons re-render on a theme change.
- `08-L §6 (#6-button-styles)` — the button styles (including the icon-button style and the
  outlined-muted style) the `MultiCheckFilterButton` conforms to, and the tooltip requirement.
- `08-D §5 (#5-verdict-palette)` — the verdict PASS/FAIL/pending colours and the "verdict colour
  is always accompanied by the verdict text label and a glyph" rule for `BadgeLabel`.
- `08-D §6 (#6-health-palette)` — the five health-dot states, their colour roles, and the
  "checking" opacity pulse that obeys the reduced-motion cap.
- `08-D §16 (#16-the-theme-module-contract)` — appearance is expressed through role dynamic
  properties; no widget calls `setStyleSheet` or embeds a colour literal.

## Design constraints

- `ui/shared/` holds no domain logic; it is pure presentation with dynamic-property roles
  (`01_MODULE_INVENTORY.md` §6). It imports PySide6, `ui/theme`, and `backend/domain` (for the
  status/health enum types) only.
- No primitive calls `setStyleSheet` or embeds a colour literal; appearance comes from theme
  role dynamic-properties resolved by `ui/theme` (ADR-0001, 08-D §16) — enforced by an
  architecture test.
- **Design decision (recorded here, not escalated per the investigator's noted convention):** the
  exact primitive factory signatures are an implementation judgment. Each primitive is exposed as
  a `make_*(...) -> QWidget` factory taking its state/options plus theme access, matching the
  module's factory-function public-surface convention.
- Colour is never the sole channel: every primitive that conveys a state by colour also renders a
  text label and/or glyph (08-L §9, §13; 08-D §15).
- The "checking" pulse and any transition are disabled under a reduced-motion preference; no
  `asyncio`.

## Acceptance criteria

### STORY-051-AC-1

For each badge status, `make_badge_label(status, text)` sets the theme role dynamic-property the
08-L §8 / 08-D §5 mapping assigns that status and renders the supplied text label alongside the
colour (colour is never the sole channel):

| Badge status      | Theme role     |
| ----------------- | -------------- |
| pass              | `success.base` |
| fail              | `error.base`   |
| warning           | `warning.base` |
| info              | `info.base`    |
| neutral / pending | `muted.base`   |

### STORY-051-AC-2

For each health state, `make_health_dot(state)` resolves the 08-D §6 colour role that state maps
to and renders the dot with an accompanying text label; the `checking` state additionally runs an
opacity pulse:

| Health state                | Theme role     | Pulses |
| --------------------------- | -------------- | ------ |
| live                        | `success.base` | no     |
| reachable, zero models      | `warning.base` | no     |
| down                        | `error.base`   | no     |
| not tested / probe disabled | `muted.base`   | no     |
| checking                    | `muted.base`   | yes    |

### STORY-051-AC-3

Given a `MultiCheckFilterButton` built over a set of options, when the user toggles an option,
then the button's label reflects the current checked count and the button emits its
selection-changed signal carrying the current checked option set.

### STORY-051-AC-4

Given a `HealthDot` rendered under one active theme, when the theme-changed notification fires,
then the dot re-reads its colour from the newly active theme container and repaints, so the
custom-painted surface follows the theme switch.

## Test plan

- STORY-051-AC-1 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/shared/tests/test_badge_label.py`,
  `test_badge_sets_role_and_shows_text_per_status`.
- STORY-051-AC-2 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/shared/tests/test_health_dot.py`,
  `test_health_dot_resolves_role_and_pulses_per_state`.
- STORY-051-AC-3 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/shared/tests/test_multi_check_filter_button.py`,
  `test_toggle_updates_count_label_and_emits_selection`.
- STORY-051-AC-4 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/shared/tests/test_health_dot.py`,
  `test_health_dot_repaints_on_theme_change`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-051.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/shared/`.
- [ ] An architecture test confirms no `ui/shared/` primitive references `setStyleSheet` or
  embeds a colour literal, and that the module imports no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
