---
id: STORY-089
title: Set an accessible name, objectName, and tooltip on every interactive control across the UI
status: draft
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#11-accessibility-floor-summary
modules:
  - ui/main_window/
  - ui/common_dialogs/
  - ui/results/
acceptance_criteria:
  - STORY-089-AC-1
edge_cases: []
depends_on:
  - STORY-097
  - STORY-098
  - STORY-099
adrs: []
owner: coder
estimate: M
---

# STORY-089 — Set an accessible name, objectName, and tooltip on every interactive control across the UI

## Goal

Bring the whole application up to the accessibility floor's release-blocking accessible-name
requirement: every interactive control exposes a programmatically queryable accessible name, and
every icon-only or ambiguous control uses the exact canonical name, test handle, and tooltip the
spec pins for it. This is the umbrella story for a repo-wide sweep that is too large for one coding
session; it delivers the single cross-cutting guarantee — the pinned icon-only/ambiguous-control
registry is realized exactly, app-wide — and depends on the three per-workspace child stories that
do the module-by-module implementation.

## In scope

- The app-wide conformance guarantee that every row of the icon-only / ambiguous-control registry
  (§7.2) is realized with **exactly** its pinned `objectName`, accessible name, and tooltip
  (`title=` / `setToolTip`) text, across every screen the registry names.
- Coordinating the three child stories that add accessible names, objectNames, and tooltips to the
  interactive controls in each ui module group (STORY-097, STORY-098, STORY-099).

## Out of scope

- The per-module implementation of accessible names on ordinary (non-registry) interactive controls
  — split across STORY-097 (main window, common dialogs, shared primitives, dropdowns), STORY-098
  (new benchmark, resume, progress), and STORY-099 (results, settings, task editor); this parent
  only asserts the pinned-registry values app-wide.
- The generic floor verification suite (objectName architecture test, accessible-name walker,
  click-target, focus-ring, no-shortcut grep) — owned by STORY-091.
- Reduced-motion and high-contrast preference support — owned by STORY-090.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — every interactive element
  exposes a non-empty accessible name; an icon-only control must never ship with an empty or
  generic one.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names`
  — the canonical table: implementers MUST use the exact `objectName`, accessible name, and tooltip
  values pinned for each icon-only or ambiguous control; repeated controls share one objectName
  pattern; per-field controls suffix the objectName with the field key.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#11-accessibility-floor-summary` — accessible names
  on every interactive element, including every icon-only button, block release.

## Design constraints

- The registry's three attributes are distinct and all mandatory per row: the accessible name
  (`setAccessibleName`, user-facing/assistive), the `objectName` (the stable test handle, never
  shown to the user), and the tooltip (`setToolTip`, pointer-hover). The parent AC asserts all three
  match the pinned values exactly.
- No `setStyleSheet`, no colour literal, no `asyncio` in any touched module (architecture-test
  enforced).
- This story adds no public API symbol; it is verification plus coordination over work delivered by
  the child stories.

## Acceptance criteria

### STORY-089-AC-1

For every row of the icon-only / ambiguous-control registry (§7.2), the control it names, when
mounted in its screen, exposes exactly the pinned `objectName`, the pinned accessible name, and the
pinned tooltip text — no substitute, abbreviated, or generic value:

| Screen                                   | objectName                     | Accessible name                                       | Tooltip                                                         |
| ---------------------------------------- | ------------------------------ | ----------------------------------------------------- | --------------------------------------------------------------- |
| Main Window · Settings menu              | `settings_menu_button`         | "Settings"                                            | Open the Settings dialog                                        |
| Main Window · About menu                 | `about_menu_button`            | "About"                                               | Application information: version, links, data folders           |
| Main Window · Benchmark workspace tab    | `workspace_benchmark_button`   | "Benchmark workspace"                                 | Benchmark workspace                                             |
| Main Window · Task Editor workspace tab  | `workspace_task_editor_button` | "Task Editor workspace"                               | Task Editor workspace                                           |
| Main Window · Running pill               | `running_pill_button`          | "Run in progress — open Progress"                     | Switch to the Benchmark workspace and focus the Progress widget |
| Main Window · Provider-readiness dot     | `provider_readiness_indicator` | "Provider readiness status"                           | Provider readiness — click to open Settings / Providers         |
| All widgets · Rename-run pencil          | `rename_run_button`            | "Rename run"                                          | Rename run                                                      |
| All dialogs · Dialog close               | `dialog_close_button`          | "Close dialog"                                        | Close                                                           |
| New Benchmark · Judge model refresh      | `judge_model_refresh_button`   | "Refresh judge model list"                            | Refresh the judge provider's model list                         |
| Result · Charts · Previous chart         | `chart_prev_button`            | "Previous chart"                                      | Previous chart                                                  |
| Result · Charts · Next chart             | `chart_next_button`            | "Next chart"                                          | Next chart                                                      |
| Result · Charts · Detach chart           | `detach_chart_button`          | "Detach chart"                                        | Open the chart in its own window                                |
| About dialog · Open data folder          | `open_data_folder_button`      | "Open application data folder"                        | Open the application data folder                                |
| About dialog · Copy data-folder path     | `copy_data_folder_path_button` | "Copy application data folder path"                   | Copy the application data folder path                           |
| Settings / dialogs · Gate-busy indicator | `gate_busy_indicator`          | "Inference in flight — controls temporarily disabled" | An inference is in flight; please wait.                         |
| Task Editor · Field-help icon            | `<field_key>_help_button`      | "Help: \<field label>"                                | About this field                                                |
| Task Editor · Validation-summary pill    | `validation_summary_button`    | "Validation summary — focus first issue"              | Click to focus the first task with a warning                    |

## Test plan

- STORY-089-AC-1 — integration, table-driven (`pytest-qt`, offscreen), parametrized one case per
  registry row, `tests/integration/test_icon_only_registry_conformance.py`,
  `test_every_registry_control_uses_its_pinned_name_objectname_and_tooltip`. Each row mounts the
  control on its screen and asserts `objectName()`, `accessibleName()`, and `toolTip()` equal the
  pinned values. Passes only once STORY-097/098/099 have realized every row.

## Definition of done

- [ ] STORY-089-AC-1 has a passing table-driven test that names STORY-089 and covers every registry
  row.
- [ ] The three child stories (STORY-097, STORY-098, STORY-099) are `done`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
