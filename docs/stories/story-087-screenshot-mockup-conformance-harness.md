---
id: STORY-087
title: Capture every spec screen in both themes and review the captures against the mockups
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-R_screen_index_and_traceability.md#2-screen-index--every-mockup-and-its-drawn-states
  - 08_Cross_Cutting/08-L_ui_standardization.md#14-standardization-review-checklist
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#13-theme-switching
modules:
  - ui/theme/
  - ui/main_window/
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-087-AC-1
  - STORY-087-AC-2
  - STORY-087-AC-3
edge_cases: []
depends_on:
  - STORY-083
adrs:
  - ADR-0011
owner: tester
estimate: M
---

# STORY-087 — Capture every spec screen in both themes and review the captures against the mockups

## Goal

The per-screen `mockup.html` files are the declared visual source of truth, but the only conformance
mechanism today is a manual review checklist — there is no way to actually see what the widgets
render. This story adds an offscreen-Qt screenshot harness that renders every spec screen in both the
Light and Dark themes to PNGs in an artifacts directory, and produces a documented findings report
comparing those captures against each screen's mockup using the standardization review checklist. The
harness makes the visual conformance question answerable instead of purely aspirational; ADR-0011
records this new process artifact.

## In scope

- An offscreen-Qt screenshot harness (under `tests/` / `scripts/`) that constructs each spec screen
  listed in the screen index — the two workspaces mounted in the main window shell and the shared
  modal dialogs — and captures it to a PNG in an artifacts directory.
- Rendering each captured screen in both the Light and the Dark theme (two captures per screen),
  driving the theme module's theme switch between passes.
- A documented findings report that walks the standardization review checklist against each capture
  versus its `mockup.html`, recording conformance and any discrepancies.

## Out of scope

- Pixel-diffing against the mockups or asserting exact pixel equality — the mockups are HTML, not Qt
  renders; the review is checklist-based and documented, not a pixel gate.
- Changing any widget's appearance to resolve a discrepancy — a real discrepancy the report surfaces
  becomes its own follow-up story, not part of this harness story.
- The theme switch mechanism itself — delivered by STORY-083 (this story's prerequisite); here it is
  used to drive the two-theme capture pass.

## Spec inputs

- `08_Cross_Cutting/08-R_screen_index_and_traceability.md#2-screen-index--every-mockup-and-its-drawn-states`
  — the authoritative index of every screen and its `mockup.html`; the mockup is the visual source of
  truth, so the harness renders exactly the screens this index enumerates.
- `08_Cross_Cutting/08-L_ui_standardization.md#14-standardization-review-checklist` — the checklist
  applied when reviewing any UI surface or mockup; the findings report walks it per captured screen.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#13-theme-switching` — the two token
  containers (Light, Dark) and the switch sequence; each screen is captured under both.

## Design constraints

- The harness runs under the offscreen Qt platform plugin so it needs no display and runs on a
  headless runner.
- The theme is switched only through `ui/theme/`'s public switch path; the harness sets no styling
  itself.
- Captures are written to a dedicated artifacts directory (not committed as gate fixtures); the
  harness is a review tool, not a pass/fail pixel gate.

## Acceptance criteria

### STORY-087-AC-1

Given the offscreen screenshot harness in the Light theme,
when it runs,
then it writes one PNG per screen enumerated in the screen index to the artifacts directory.

### STORY-087-AC-2

Given the offscreen screenshot harness in the Dark theme,
when it runs,
then it writes one PNG per screen enumerated in the screen index to the artifacts directory.

### STORY-087-AC-3

Given the Light and Dark captures,
when the mockup-conformance review is produced,
then a documented findings report records, per screen, the standardization-review-checklist outcome
against that screen's `mockup.html`.

## Test plan

- STORY-087-AC-1 — integration (`pytest-qt`, offscreen), `tests/integration/test_screenshot_harness.py`,
  `test_harness_captures_every_screen_in_light_theme`.
- STORY-087-AC-2 — integration (`pytest-qt`, offscreen), same file,
  `test_harness_captures_every_screen_in_dark_theme`.
- STORY-087-AC-3 — integration (`pytest-qt`, offscreen), same file,
  `test_mockup_conformance_report_covers_every_screen`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-087.
- [ ] The findings report exists and covers every screen in the screen index for both themes.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
