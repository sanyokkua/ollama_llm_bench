---
id: STORY-050
title: Switch themes live and satisfy the accessibility floor in the theme module
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#13-theme-switching
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#14-wcag-aa-contrast-matrix
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#15-accessibility-rules
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#12-shadow-and-motion-tokens
  - 08_Cross_Cutting/08-L_ui_standardization.md#11-theme-handling
modules:
  - ui/theme/
acceptance_criteria:
  - STORY-050-AC-1
  - STORY-050-AC-2
  - STORY-050-AC-3
  - STORY-050-AC-4
  - STORY-050-AC-5
  - STORY-050-AC-6
depends_on:
  - STORY-049
adrs:
  - ADR-0001
owner: coder
estimate: M
---

# STORY-050 — Switch themes live and satisfy the accessibility floor in the theme module

## Goal

Make the theme module select, apply, and live-switch the active theme per the `ui.theme`
setting, re-applying styling and notifying custom-painted surfaces without a restart or loss of
unsaved input, and prove that both delivered themes meet the accessibility floor: the full WCAG
AA contrast matrix, reduced-motion handling, and high-contrast handling. This closes the Phase 9
theme gate — after this story a live OS light/dark switch repaints the whole app correctly and
both themes are verified against every contrast pair.

## In scope

- The `ui.theme` selection logic (`system` / `dark` / `light`): choosing the Dark or Light
  container, tracking the live OS colour-scheme change under `system`, and honouring an explicit
  `dark`/`light` override against a live OS change.
- The switch sequence: replace the active container, rebuild and re-apply the stylesheet and
  `QPalette` to the `QApplication`, and emit a theme-changed notification custom-painted surfaces
  subscribe to.
- The full 13-pair WCAG AA contrast verification across both themes.
- Reduced-motion handling (instant repaint, no health-dot pulse) and high-contrast handling
  (increased border-width emphasis, soft `*.fill` backgrounds replaced by solid borders).

## Out of scope

- The token values, the QSS generator, and the `QPalette` builder — owned by STORY-049; this
  story drives them through the switch sequence.
- The custom-painted surfaces that repaint on the notification (charts, badges, dots) —
  `HealthDot`'s theme-follow behaviour is owned by STORY-051; other charts by later phases.
- Persisting or reading the `ui.theme` setting value itself — owned by the settings service
  (STORY-014); this story consumes the resolved value.
- The "a run continues unaffected while the OS theme changes mid-run" half of EC-PLAT-2 — owned
  by a later `ui/main_window/` integration story (per `06_EDGE_CASE_TO_TEST_MAPPING.md`, which
  maps EC-PLAT-2 to `ui/main_window/` + `tests/integration/`). This story delivers the live
  theme re-render that behaviour depends on, but does not claim EC-PLAT-2 coverage.

## Spec inputs

- `08-D §13 (#13-theme-switching)` — the three `ui.theme` values, the launch-time and live OS
  colour-scheme tracking under `system`, the six-step switch sequence (replace container, rebuild
  and re-apply stylesheet + `QPalette`, emit the theme-changed notification, re-render tinted
  icons, no restart, no discarded input, cross-fade over `motion.standard`).
- `08-D §14 (#14-wcag-aa-contrast-matrix)` — the 13 foreground/background pairs and each pair's
  minimum required ratio, which both themes must satisfy.
- `08-D §15 (#15-accessibility-rules)` — the contrast, reduced-motion, high-contrast, and
  focus-visibility rules the module enforces.
- `08-D §12 (#12-shadow-and-motion-tokens)` — the `motion.standard` cross-fade duration and the
  rule that a reduced-motion preference disables all transitions and the health-dot pulse.
- `08-L §11 (#11-theme-handling)` — the corroborating standardization rule: `system` tracks live
  OS changes, a runtime change re-applies tokens and repaints every surface without restart or
  loss of unsaved input.

## Design constraints

- `ui/theme/` remains the only module permitted to call `setStyleSheet()` (ADR-0001, 08-D §16).
- **Design decision (recorded here, not escalated per the investigator's noted convention):** the
  theme-changed notification is a Qt signal owned by the theme module, not a `backend/events`
  bus event. `ui/theme/` is the foundational styling authority that every widget imports directly
  without a gateway, so its change notification is a local Qt signal a custom-painted surface
  connects to — keeping the module free of a backend Protocol dependency.
- **Design decision (recorded here):** high-contrast emphasis values (the increased
  `border.width` and the removal of soft `*.fill` backgrounds) are qualitative in 08-D §15; the
  concrete pixel emphasis is an implementation judgment. The generator increases border width and
  drops the `*.fill` backgrounds to solid borders when high-contrast is reported; the exact
  emphasis is chosen for visible distinctness, not read literally from the spec.
- The live OS colour-scheme preference and the reduced-motion / high-contrast preferences are
  read through the OS surface (Qt `QStyleHints`); no `QFontDatabase` probing, no `asyncio`.
- A theme switch never triggers an application restart and never discards unsaved user input.

## Acceptance criteria

### STORY-050-AC-1

For each combination of `ui.theme` setting and reported OS colour scheme, the theme module
selects the correct token container:

| `ui.theme` | OS colour scheme | Selected container |
| ---------- | ---------------- | ------------------ |
| `system`   | dark             | Dark               |
| `system`   | light            | Light              |
| `dark`     | dark             | Dark               |
| `dark`     | light            | Dark               |
| `light`    | dark             | Light              |
| `light`    | light            | Light              |

### STORY-050-AC-2

Given `ui.theme` is `system`, when the OS colour scheme changes at runtime, then the theme module
rebuilds and re-applies the stylesheet and `QPalette` to the `QApplication` for the newly matching
container and emits the theme-changed notification, without an application restart.

### STORY-050-AC-3

Given `ui.theme` is an explicit `dark` (or `light`), when the OS colour scheme changes at runtime,
then the applied theme does not change — the explicit override ignores the live OS change.

### STORY-050-AC-4

For each foreground/background pair in the 08-D §14 contrast matrix, in both the Dark and the
Light theme, the contrast ratio computed from the resolved token values is greater than or equal
to that pair's minimum required ratio (table-driven, total over the 13 pairs in both themes).

### STORY-050-AC-5

Given the OS reports a reduced-motion preference, when the theme is re-applied, then the repaint
applies instantly (no cross-fade) and the health-dot pulse is disabled, rather than transitioning
over `motion.standard`.

### STORY-050-AC-6

Given the OS reports a high-contrast preference, when `build_stylesheet` runs for the active
container, then the generated stylesheet renders component boundaries as solid borders with
increased border-width emphasis and omits the soft `*.fill` background fills.

## Test plan

- STORY-050-AC-1 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/theme/tests/test_theme_selection.py`,
  `test_active_container_matches_setting_and_os_scheme`.
- STORY-050-AC-2 — integration (`pytest-qt`), `tests/integration/test_theme_switching.py`,
  `test_system_theme_reapplies_and_notifies_on_os_change`.
- STORY-050-AC-3 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/theme/tests/test_theme_selection.py`,
  `test_explicit_override_ignores_live_os_change`.
- STORY-050-AC-4 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/theme/tests/test_wcag_contrast.py`,
  `test_contrast_pair_meets_minimum_in_both_themes`.
- STORY-050-AC-5 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/theme/tests/test_reduced_motion.py`,
  `test_reduced_motion_applies_theme_instantly`.
- STORY-050-AC-6 — unit, colocated
  `src/ollama_llm_bench/ui/theme/tests/test_high_contrast.py`,
  `test_high_contrast_uses_solid_borders_without_soft_fills`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-050.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/theme/`.
- [ ] An architecture test confirms `ui/theme/` remains the only module referencing
  `setStyleSheet` and that the module imports no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
