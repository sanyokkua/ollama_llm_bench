---
id: STORY-099
title: Add accessible names, objectNames, and tooltips to the Result, Settings, and Task Editor widgets
status: draft
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names
modules:
  - ui/results/
  - ui/settings_dialog/
  - ui/task_editor/
acceptance_criteria:
  - STORY-099-AC-1
  - STORY-099-AC-2
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: M
---

# STORY-099 — Add accessible names, objectNames, and tooltips to the Result, Settings, and Task Editor widgets

## Goal

Bring the Result surface, the Settings dialog, and the Task Editor workspace up to the
accessible-name floor: every interactive control in these three modules exposes a non-empty
accessible name, and the icon-only/ambiguous controls carry their exact pinned objectName, accessible
name, and tooltip. Third of three per-workspace child stories under the STORY-089 sweep.

## In scope

- A non-empty, descriptive accessible name on every interactive control in `ui/results/`,
  `ui/settings_dialog/`, and `ui/task_editor/` — including the run selector, the four result tabs,
  the summary/details tables, the export footer buttons, the Providers/General tab controls, the
  files/tasks panes, the field editor rows, and the YAML preview controls.
- The exact pinned objectName, accessible name, and tooltip for the §7.2 registry controls that live
  in these modules: the Result · Charts previous/next/detach buttons, the Settings/dialogs gate-busy
  indicator, and the Task Editor per-field help icon (`<field_key>_help_button`) and
  validation-summary pill.

## Out of scope

- Main window, common dialogs, shared primitives, dropdowns — owned by STORY-097.
- New Benchmark, Resume, and Progress controls — owned by STORY-098.
- The app-wide registry-conformance assertion — owned by the parent STORY-089.
- The generic floor verification suite — owned by STORY-091.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — the accessible-name source
  per element kind, including each tab's visible label and the table content-describing names used
  by the summary and details tables.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names`
  — the pinned canonical values for the chart navigation/detach buttons, the gate-busy indicator,
  and the Task Editor per-field help icons (objectName suffixed with the field key) and
  validation-summary pill.

## Design constraints

- The accessible name (user-facing) and the objectName (test handle) are independent and both
  mandatory.
- Per-field controls suffix their objectName with the field key (`<field_key>_help_button`).
- No `setStyleSheet`, no colour literal, no `asyncio` in the touched modules.

## Acceptance criteria

### STORY-099-AC-1

For every interactive control in `ui/results/`, `ui/settings_dialog/`, and `ui/task_editor/`, the
control reports a non-empty accessible name when mounted.

### STORY-099-AC-2

For each §7.2 registry control that lives in these modules (the chart previous/next/detach buttons,
the gate-busy indicator, and each per-field help icon and the validation-summary pill in the Task
Editor), the control exposes exactly its pinned objectName, accessible name, and tooltip.

## Test plan

- STORY-099-AC-1 — integration (`pytest-qt`, offscreen),
  `tests/integration/test_a11y_names_result_settings_task_editor.py`,
  `test_every_result_settings_task_editor_control_has_a_nonempty_accessible_name`.
- STORY-099-AC-2 — integration, table-driven (`pytest-qt`), same file,
  `test_result_settings_task_editor_registry_controls_use_pinned_values`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-099.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
