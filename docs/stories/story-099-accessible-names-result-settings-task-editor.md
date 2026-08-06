---
id: STORY-099
title: Add accessible names, objectNames, and tooltips to the Result, Settings, and Task Editor widgets
status: ready
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names
modules:
  - ui/results/
  - ui/settings_dialog/
  - ui/task_editor/
  - adapters/qt_table_models/
acceptance_criteria:
  - STORY-099-AC-1
  - STORY-099-AC-2
  - STORY-099-AC-3
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: L
---

# STORY-099 — Add accessible names, objectNames, and tooltips to the Result, Settings, and Task Editor widgets

## Goal

Bring the Result surface, the Settings dialog, and the Task Editor workspace up to the
accessible-name floor: every interactive control in these three modules exposes a non-empty
accessible name, and the icon-only/ambiguous controls carry their exact pinned objectName, accessible
name, and tooltip. Third of three per-workspace child stories under the STORY-089 sweep.

These modules hold the densest cluster of delegate-painted row controls in the application — the
Providers table's Enabled checkbox, Test ⚡, and More ⋯ are drawn by a `QStyledItemDelegate`, not
built as widgets — so they need the model-role naming mechanism described under Design constraints
rather than a `setAccessibleName` call.

## In scope

- A non-empty, descriptive accessible name on every interactive control in `ui/results/`,
  `ui/settings_dialog/`, and `ui/task_editor/` — including the run selector, the four result tabs,
  the summary/details tables, the export footer buttons, the Providers/General tab controls, the
  files/tasks panes, the field editor rows, and the YAML preview controls.
- The exact pinned objectName, accessible name, and tooltip for the five §7.2 registry rows this
  story owns: the three Result · Charts buttons and the two Task Editor rows.
- Giving the Providers table's delegate-painted row actions an accessible name through the table
  model's `Qt.ItemDataRole.AccessibleTextRole`.

## Out of scope

- Main window, common dialogs, shared primitives, dropdowns — owned by STORY-097.
- New Benchmark, Resume, and Progress controls — owned by STORY-098.
- **The `gate_busy_indicator` registry row** — owned by STORY-097, which introduces it as a shared
  `ui/shared/` primitive. The Settings dialog mounts that primitive; it does not restate the pinned
  strings, so the pinned-value assertion for the row lives in STORY-097.
- **The `dialog_close_button` registry row** — likewise owned by STORY-097. The Settings
  sub-dialogs and the detached chart window mount STORY-097's shared close button.
- **The `AccessibleTextRole` support in `adapters/qt_table_models/`** as a mechanism — first added
  by STORY-098 for the Resume table. This story consumes it for the Providers table; if STORY-098
  has not landed yet, this story adds it, and whichever lands second must extend rather than fork
  it.
- The app-wide registry-conformance assertion over all 17 rows — owned by the parent STORY-089.
- The generic floor verification suite — owned by STORY-091.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — every interactive element
  exposes a programmatically queryable accessible name; the accessible-name source per element
  kind, including each tab's visible label, the table content-describing names used by the summary
  and details tables, and the field label as an input's name.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names`
  — the pinned canonical values for the chart navigation/detach buttons, the Task Editor per-field
  help icons (objectName suffixed with the field key), and the validation-summary pill; and the
  rule that per-field controls suffix the objectName with the field key.

## Design constraints

- The accessible name (user-facing) and the objectName (test handle) are independent and both
  mandatory.
- Per-field controls suffix their objectName with the field key (`<field_key>_help_button`), so the
  accessible name varies per field ("Help: " plus that field's label) while the objectName pattern
  is fixed.
- **A control painted by a `QStyledItemDelegate` is not a `QWidget`, so `setAccessibleName` cannot
  be called on it.** `ui/settings_dialog/_internal/providers_tab/row_actions_delegate.py` draws the
  Enabled checkbox (`☑`/`☐`), the Test-connection glyph (`⚡`), and the overflow (`⋯`) with
  `painter.drawText` into rects computed by `icon_rects_for_cell`, and hit-tests them in
  `editorEvent`; no widget is instantiated per row. The same is true of that tab's
  `health_auth_delegate.py` and of `ui/results/_internal/details_tab/view.py`'s delegate. For these
  glyphs the accessible name must be published **by the table model**, as the cell's
  `Qt.ItemDataRole.AccessibleTextRole` text. `adapters/qt_table_models/_internal/base.py`'s
  `data()` currently short-circuits every role other than `Qt.ItemDataRole.DisplayRole` and returns
  nothing, so the model must answer `AccessibleTextRole` for the Enabled column with text naming
  the row's provider, its enabled state in words, and the Test and More actions available on it.
- Do not replace a delegate with per-row widgets to make naming easier — the delegate exists so the
  table stays virtualised.
- No `setStyleSheet`, no colour literal, no `asyncio` in the touched modules.

## Acceptance criteria

### STORY-099-AC-1

For every interactive control in `ui/results/`, `ui/settings_dialog/`, and `ui/task_editor/`, the
control reports a non-empty accessible name when mounted.

### STORY-099-AC-2

Each of the five §7.2 registry rows this story owns, when mounted on its screen, reports exactly the
pinned `objectName`, accessible name, and tooltip below — no substitute, abbreviated, or generic
value:

| Screen · control                      | objectName                  | Accessible name                          | Tooltip                                      |
| ------------------------------------- | --------------------------- | ---------------------------------------- | -------------------------------------------- |
| Result · Charts · Previous chart (◀)  | `chart_prev_button`         | "Previous chart"                         | Previous chart                               |
| Result · Charts · Next chart (▶)      | `chart_next_button`         | "Next chart"                             | Next chart                                   |
| Result · Charts · Detach chart        | `detach_chart_button`       | "Detach chart"                           | Open the chart in its own window             |
| Task Editor · Field-help icon (ⓘ)     | `<field_key>_help_button`   | "Help: \<field label>"                   | About this field                             |
| Task Editor · Validation-summary pill | `validation_summary_button` | "Validation summary — focus first issue" | Click to focus the first task with a warning |

### STORY-099-AC-3

Given the Providers table with at least one provider row, when the Enabled cell is queried for
`Qt.ItemDataRole.AccessibleTextRole`, then it returns non-empty text stating the row's enabled state
in words and naming the Test-connection and More actions, and the delegate is still the only thing
that paints those glyphs — no per-row widget is created.

## Test plan

- STORY-099-AC-1 — integration (`pytest-qt`),
  `tests/integration/test_a11y_names_result_settings_task_editor.py`,
  `test_every_result_settings_task_editor_control_has_a_nonempty_accessible_name`.
- STORY-099-AC-2 — integration, table-driven (`pytest-qt`), same file,
  `test_result_settings_task_editor_registry_controls_use_pinned_values` — one
  `@pytest.mark.parametrize` case per row of the AC-2 table, with the field-help row parametrized
  over at least two distinct field keys to prove the suffix and the per-field name both vary.
- STORY-099-AC-3 — unit, colocated
  `src/ollama_llm_bench/adapters/qt_table_models/tests/test_accessible_text_role.py`,
  `test_providers_enabled_cell_exposes_state_and_actions_as_accessible_text`, plus
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_row_actions_delegate.py`,
  `test_providers_delegate_creates_no_per_row_widget`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-099.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-089** — the whole-registry conformance story. Flip it `draft` → `ready` **only once
  STORY-097 and STORY-098 are also `done`**; STORY-089 depends on all three children.

**What to do on completion**

Once STORY-099's acceptance-criteria tests pass:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependency in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping
   silently. If STORY-097 and STORY-098 are already `done`, STORY-089 is the next pick and it in
   turn unblocks STORY-091.
