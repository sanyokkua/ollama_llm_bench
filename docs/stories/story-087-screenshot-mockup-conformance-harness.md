---
id: STORY-087
title: Capture every spec screen in both themes and review the captures against the mockups
status: done
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

- [x] Every acceptance criterion has a passing test that names STORY-087.
- [x] The findings report exists and covers every screen in the screen index for both themes.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.

## Outcome

`just screenshots` renders all 14 screens of the screen index in both themes — 28 PNGs into
`artifacts/screenshots/{light,dark}/` — and `docs/development/mockup_conformance_review.md`
records a verdict for all 13 standardization-review-checklist items per screen per theme
(16 tables, 208 verdicts: 88 `conforms`, 40 `discrepancy`, 80 `not-applicable`).

Screens 01–05 and 09 come from one real offline `build_app()`; the Settings dialog and the seven
shared modal dialogs are constructed standalone, since the composition root builds them lazily and
`.exec()`s them, which would block the suite. The theme is chosen by seeding `ui.theme` *before*
`build_app()` runs, so the application's own `ThemeManager` performs the switch — the harness sets
no styling itself.

Verification: full gate `2446 passed`; `mypy --strict` clean over 1051 files; `import-linter`
5 contracts kept / 0 broken; `arch-test` 1345 passed; `trace-check` zero gaps. Nothing under `src/`
changed — `git diff` against the story's base commit is empty for `src/`.

## Discrepancies found — follow-ups, not defects of this story

Per ADR-0011 this harness reviews and never changes a widget, so every finding below belongs to a
later story. All are listed in the report's `## Follow-ups` section. The three most significant,
each independently verified against source:

1. **19 of 22 design-token style roles are no-ops.** Widget code across `src/ollama_llm_bench/ui/`
   sets 22 distinct `role` dynamic-property values, but `ui/theme/_internal/stylesheet_builder.py`
   defines QSS rules for only three (`primary-button`, `destructive-button`,
   `filter-chip-active`). The other 19 — including `running-pill`, `section-title`,
   `outlined-muted-button`, `muted-caption`, `warning-callout`, `success-badge`,
   `segmented-control`, `icon-button` — have no rule, so those controls fall back to default
   native Qt styling instead of the mockups' appearance. This single root cause explains most of
   the visual discrepancies recorded on screens 01, 02, 05, 06 and 07.

1. **The Run Summary dialog displays raw `provider_id` UUID4s.**
   `ui/common_dialogs/_internal/view_model_select.py:48` renders
   `f"{target.provider_id} · {target.model_name}"` with no name lookup (lines 81 and 91 do the
   same for the judge and embedding models), and `RunSummaryGateway` exposes no method that could
   supply a provider name. This violates the project's non-negotiable that `provider_id` is
   internal and never shown to the user, on the confirmation shown immediately before a run
   starts. The sibling `resume_summary_select.py` documents the rule explicitly and resolves names
   from `run.providers`; Run Summary has no equivalent path.

1. **`src/ollama_llm_bench/ui/task_editor/` sets no `role` property at all**, so the Task Editor's
   Save and New File buttons can never render as the mockup's filled-primary call to action. This
   is distinct from finding 1 — the role is never assigned in the first place.

Separately, the harness surfaced a **live crash** outside this story's scope:
`ui/common_dialogs/_internal/generate_analysis_view.py:107-115` calls `event_bus.subscribe(...)`
three times without the `owner=` argument that `QtEventBusDeliverer.subscribe` requires via an
`icontract` precondition (`adapters/qt_event_bus/_internal/deliverer.py:110-114`). Contracts stay
enabled in release builds, so opening Generate/Regenerate Analysis from the Result widget
(`ui/results/_internal/controller.py:167`) raises a `ProgrammerError` and terminates the process.
It is masked in that module's colocated unit tests by a hand-rolled fake event bus that accepts a
missing owner. Task 4 works around it with a local test-file stub rather than touching `src/`.
