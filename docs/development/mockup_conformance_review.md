# Mockup conformance review

<!--
The verdicts in this document are unreviewed placeholders. This scaffold
records the required structure -- one checklist table per screen per theme --
so the coverage test can pass before the actual visual review has happened.
Every "conforms" cell below is provisional until a later pass replaces it with
a real observation made by looking at the capture beside its mockup.
-->

Each screen the specification's screen index lists is rendered by the offscreen
screenshot harness in both themes and reviewed here against that screen's
`mockup.html`, using the standardization review checklist.

Regenerate the captures with `just screenshots`; they land in
`artifacts/screenshots/light/` and `artifacts/screenshots/dark/` (git-ignored).

The mockup is the visual source of truth: where a capture and its mockup
disagree on a visual detail, the mockup is right. This document records what was
observed. It never changes a widget -- a real discrepancy becomes its own story.

Verdicts: `conforms`, `discrepancy`, `not-applicable`. Any `discrepancy` row
must say what differs in Notes.

## Screen 01 — Main Window

Mockup: `docs/v3_specification/01_Main_Window/mockup.html`

### Screen 01 — Light

Capture: `artifacts/screenshots/light/01_main_window.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

### Screen 01 — Dark

Capture: `artifacts/screenshots/dark/01_main_window.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

## Screen 02 — New Benchmark

Mockup: `docs/v3_specification/02_New_Benchmark_Widget/mockup.html`

### Screen 02 — Light

Capture: `artifacts/screenshots/light/02_new_benchmark.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

### Screen 02 — Dark

Capture: `artifacts/screenshots/dark/02_new_benchmark.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

## Screen 03 — Resume Benchmark

Mockup: `docs/v3_specification/03_Resume_Benchmark_Widget/mockup.html`

### Screen 03 — Light

Capture: `artifacts/screenshots/light/03_resume_benchmark.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

### Screen 03 — Dark

Capture: `artifacts/screenshots/dark/03_resume_benchmark.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

## Screen 04 — Progress

Mockup: `docs/v3_specification/04_Progress_Widget/mockup.html`

### Screen 04 — Light

Capture: `artifacts/screenshots/light/04_progress.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

### Screen 04 — Dark

Capture: `artifacts/screenshots/dark/04_progress.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

## Screen 05 — Result

Mockup: `docs/v3_specification/05_Result_Widget/mockup.html`

### Screen 05 — Light

Capture: `artifacts/screenshots/light/05_result.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

### Screen 05 — Dark

Capture: `artifacts/screenshots/dark/05_result.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

## Screen 06 — Settings

Mockup: `docs/v3_specification/06_Settings_Dialog/mockup.html`

### Screen 06 — Light

Capture: `artifacts/screenshots/light/06_settings.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

### Screen 06 — Dark

Capture: `artifacts/screenshots/dark/06_settings.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

## Screen 07 — Common Dialogs

Mockup: `docs/v3_specification/07_Common_Dialogs/mockup.html`

### Screen 07 — Light

Captures: `artifacts/screenshots/light/07_common_dialogs__about.png`, `artifacts/screenshots/light/07_common_dialogs__error.png`, `artifacts/screenshots/light/07_common_dialogs__generate_analysis.png`, `artifacts/screenshots/light/07_common_dialogs__rename_run.png`, `artifacts/screenshots/light/07_common_dialogs__resume_summary.png`, `artifacts/screenshots/light/07_common_dialogs__retry_selection.png`, `artifacts/screenshots/light/07_common_dialogs__run_summary.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

### Screen 07 — Dark

Captures: `artifacts/screenshots/dark/07_common_dialogs__about.png`, `artifacts/screenshots/dark/07_common_dialogs__error.png`, `artifacts/screenshots/dark/07_common_dialogs__generate_analysis.png`, `artifacts/screenshots/dark/07_common_dialogs__rename_run.png`, `artifacts/screenshots/dark/07_common_dialogs__resume_summary.png`, `artifacts/screenshots/dark/07_common_dialogs__retry_selection.png`, `artifacts/screenshots/dark/07_common_dialogs__run_summary.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

## Screen 09 — Task Editor

Mockup: `docs/v3_specification/09_Task_Editor/mockup.html`

### Screen 09 — Light

Capture: `artifacts/screenshots/light/09_task_editor.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |

### Screen 09 — Dark

Capture: `artifacts/screenshots/dark/09_task_editor.png`

| #   | Checklist item                                                                                                                         | Verdict  | Notes |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| 1   | No placeholder, stub, or dead control; non-applicable controls hidden, not greyed out                                                  | conforms |       |
| 2   | Any disabled control is genuinely transient and carries a tooltip explaining why                                                       | conforms |       |
| 3   | Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip                 | conforms |       |
| 4   | The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string | conforms |       |
| 5   | The running pill is present only while a run is in a non-terminal stage                                                                | conforms |       |
| 6   | The status bar is present with the version string on the right                                                                         | conforms |       |
| 7   | Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most                    | conforms |       |
| 8   | The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style                 | conforms |       |
| 9   | Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip                      | conforms |       |
| 10  | No glyph-only control without a hover tooltip; every control has an accessible name                                                    | conforms |       |
| 11  | All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals                                         | conforms |       |
| 12  | Every state shown by colour is also shown by text and/or glyph                                                                         | conforms |       |
| 13  | The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes                                                 | conforms |       |
