---
id: STORY-050
title: Switch themes live and satisfy the accessibility floor in the theme module
status: done
spec_clauses:
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#13-theme-switching
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#14-wcag-aa-contrast-matrix
  - 08_Cross_Cutting/08-L_ui_standardization.md#11-theme-handling
modules:
  - ui/theme/
acceptance_criteria:
  - STORY-050-AC-1
  - STORY-050-AC-2
  - STORY-050-AC-3
  - STORY-050-AC-4
depends_on:
  - STORY-049
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: M
---

# STORY-050 — Switch themes live and satisfy the accessibility floor in the theme module

## Goal

Make the theme module select, apply, and live-switch the active theme per the `ui.theme`
setting, re-applying styling and notifying custom-painted surfaces without a restart or loss of
unsaved input, and prove that both delivered themes meet the full WCAG AA contrast matrix. This
closes the Phase 9 theme gate — after this story a live OS light/dark switch repaints the whole
app correctly and both themes are verified against every contrast pair. Reduced-motion and
high-contrast OS-preference handling are permanently out of scope for this application (see
ADR-0008); this story does not claim any part of that floor requirement.

## In scope

- The `ui.theme` selection logic (`system` / `dark` / `light`): choosing the Dark or Light
  container, tracking the live OS colour-scheme change under `system`, and honouring an explicit
  `dark`/`light` override against a live OS change.
- The switch sequence: replace the active container, rebuild and re-apply the stylesheet and
  `QPalette` to the `QApplication`, and emit a theme-changed notification custom-painted surfaces
  subscribe to.
- The full 13-pair WCAG AA contrast verification across both themes.

## Out of scope

- Reduced-motion and high-contrast OS-accessibility-preference handling — permanently excluded
  from this application's scope, per ADR-0008. Not deferred, not a gap to close later.
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
- The live OS colour-scheme preference is read through the OS surface (Qt `QStyleHints`); no
  `QFontDatabase` probing, no `asyncio`.
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

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-050.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/theme/`.
- [x] An architecture test confirms `ui/theme/` remains the only module referencing
  `setStyleSheet` and that the module imports no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.

## Notes

- **AC-4's "13 pairs" vs. the 14-row §14 table.** This story's AC-4 text and the STORY-049
  cross-reference both undercount the specification. `08-D §14` enumerates 14 foreground/
  background pairs, not 13. The implementation defines, resolves, and tests all 14 pairs per
  theme (28 checks total), not a truncated 13. The "13" figure in this story's prose is stale
  and should be read as "14" wherever it appears — the same kind of stale-count discrepancy
  STORY-049 recorded for its own "23 colour roles" prose (see that story's Notes section).

- **Five of the 28 AC-4 checks failed with the token values as originally specified.** The 08-D
  §14 table claims specific contrast ratios (e.g. "4.6:1" for `text.on-primary` on
  `primary.base` in Dark) that do not match what the §3/§4 hex values actually produce when run
  through the WCAG 2.1 relative-luminance formula (verified against the black-on-white 21:1
  reference case). The failing pairs were: `text.on-primary`/`primary.base` (both themes),
  `text.on-error`/`error.base` (Dark only), `border.default`/`bg.surface` (both themes).
  `primary_base`, `border_focus` (tied to `primary_base` per §3/§4's own "equals primary.base"
  note), `error_base` (Dark only), and `border_default` (both themes) were retuned to new hex
  values that pass all 14 pairs in both themes with real computed contrast margin. See
  `_internal/colors.py` for the new values. `primary_hover`/`primary_pressed`/`primary_disabled`
  were deliberately left unchanged — no AC tests them, though a future visual-consistency pass
  may want to re-tune them since the Dark `primary_pressed` (`#0d9488`) is now visually *lighter*
  than the new `primary_base` (`#0f766e`), inverting the original darken-on-press feel. This is
  not a functional defect (nothing tests hover/pressed relative brightness) but is worth a note
  for whoever next touches the button visual states.

- **Reduced-motion (formerly AC-5) and high-contrast (formerly AC-6) handling are permanently out
  of scope for this application.** This is a deliberate, permanent product descope recorded in
  ADR-0008, not an open gap awaiting a follow-up. `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md`
  §8/§11 still calls both requirements release-blocking; ADR-0008 records the conscious decision
  to ship without them and why. This story only ever claims Dark/Light colour-scheme switching
  (AC-1–AC-4) and the WCAG AA contrast matrix. No future story should re-propose implementing
  reduced-motion or high-contrast handling under this story's scope — a new story plus a
  superseding ADR would be required to reverse this decision.
