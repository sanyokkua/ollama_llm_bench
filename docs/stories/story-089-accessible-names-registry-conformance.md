---
id: STORY-089
title: Assert every icon-only and ambiguous control uses its pinned name, objectName, and tooltip app-wide
status: draft
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#11-accessibility-floor-summary
modules:
  - ui/main_window/
  - ui/common_dialogs/
  - ui/shared/
  - ui/new_benchmark/
  - ui/progress/
  - ui/results/
  - ui/settings_dialog/
  - ui/task_editor/
acceptance_criteria:
  - STORY-089-AC-1
edge_cases: []
depends_on:
  - STORY-097
  - STORY-098
  - STORY-099
adrs: []
owner: tester
estimate: L
---

# STORY-089 — Assert every icon-only and ambiguous control uses its pinned name, objectName, and tooltip app-wide

## Goal

Add the single regression net that holds the icon-only / ambiguous-control registry together: one
table-driven test that asserts **all 17 rows** of the §7.2 registry, in one place, against the
mounted application.

**Blocked:** stays `draft` until STORY-097, STORY-098 and STORY-099 are all `done`.

**This is not duplicate work, and must not be deleted as such.** The three child stories partition
the registry by module: STORY-097 asserts only the ten rows that live in its own modules, STORY-098
only its two, STORY-099 only its five. Each child's test is therefore blind to every row outside its
own modules — and, critically, blind to a control **moving** between screens. If the detach-chart
button is later relocated from the Charts tab into a common dialog, or the gate-busy indicator moves
out of `ui/shared/`, every child test still passes: the row simply stops being asserted by anyone,
because the child that owned it no longer mounts it and the child that now does was never told to
look for it. STORY-089's one table over all 17 rows is what makes that silent disappearance a
failure. It is the reason the partition can be trusted at all.

## In scope

- One table-driven conformance test covering every row of the §7.2 registry, asserting **exactly**
  the pinned `objectName`, accessible name, and tooltip (`setToolTip`) text against the control as
  mounted in the running application.
- The test is total over the registry: adding a row to §7.2 without adding a case here is itself a
  failure, so the "New icon-only controls added later MUST be appended to this registry" rule has an
  enforcement point.

## Out of scope

- Setting the names, objectNames, and tooltips this story asserts — delivered by the three child
  stories. The registry partition is fixed as follows, and each child restates its own share in its
  `## In scope`, so no row is owned twice and none is unowned:

  | Rows                                                                                                                              | Owner     |
  | --------------------------------------------------------------------------------------------------------------------------------- | --------- |
  | The six Main Window rows, `dialog_close_button`, `open_data_folder_button`, `copy_data_folder_path_button`, `gate_busy_indicator` | STORY-097 |
  | `rename_run_button`, `judge_model_refresh_button`                                                                                 | STORY-098 |
  | `chart_prev_button`, `chart_next_button`, `detach_chart_button`, `<field_key>_help_button`, `validation_summary_button`           | STORY-099 |

- Accessible names on ordinary (non-registry) interactive controls — each child story's AC-1.

- The generic floor verification suite (objectName architecture test, accessible-name walker,
  click-target, focus-ring, no-shortcut grep) — owned by STORY-091.

- Reduced-motion and high-contrast preference support — permanently excluded by ADR-0018; see
  STORY-090.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — every interactive element
  exposes a non-empty accessible name; an icon-only control must never ship with an empty or
  generic one.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names`
  — the canonical table this story asserts verbatim: implementers MUST use the exact `objectName`,
  accessible name, and tooltip values pinned for each icon-only or ambiguous control; repeated
  controls share one objectName pattern; per-field controls suffix the objectName with the field
  key; new icon-only controls MUST be appended to the registry in the same change that introduces
  them.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#11-accessibility-floor-summary` — accessible names
  on every interactive element, including every icon-only button, block release.

## Design constraints

- The registry's three attributes are distinct and all mandatory per row: the accessible name
  (`setAccessibleName`, user-facing/assistive), the `objectName` (the stable test handle, never
  shown to the user), and the tooltip (`setToolTip`, pointer-hover). The AC asserts all three match
  the pinned values exactly — an equal comparison, never a substring or case-insensitive match.
- This story writes **one test file and edits no application module**. If a row fails, the fix
  belongs in the child story's module, not here.
- The `<field_key>_help_button` row is a pattern, not a literal objectName: the case is parametrized
  over at least two real Task Editor field keys, and asserts the objectName is that field's key
  followed by `_help_button` and the accessible name is `Help: ` followed by that field's visible
  label.
- This story adds no public API symbol.

## Acceptance criteria

### STORY-089-AC-1

For every row of the icon-only / ambiguous-control registry (§7.2), the control it names, when
mounted in its screen, exposes exactly the pinned `objectName`, the pinned accessible name, and the
pinned tooltip text — no substitute, abbreviated, or generic value:

| Screen · control                                   | objectName                     | Accessible name                                       | Tooltip                                                         |
| -------------------------------------------------- | ------------------------------ | ----------------------------------------------------- | --------------------------------------------------------------- |
| Main Window · Settings menu (gear)                 | `settings_menu_button`         | "Settings"                                            | Open the Settings dialog                                        |
| Main Window · About menu (info)                    | `about_menu_button`            | "About"                                               | Application information: version, links, data folders           |
| Main Window · Benchmark workspace tab              | `workspace_benchmark_button`   | "Benchmark workspace"                                 | Benchmark workspace                                             |
| Main Window · Task Editor workspace tab            | `workspace_task_editor_button` | "Task Editor workspace"                               | Task Editor workspace                                           |
| Main Window · Running pill                         | `running_pill_button`          | "Run in progress — open Progress"                     | Switch to the Benchmark workspace and focus the Progress widget |
| Main Window · Provider-readiness indicator (dot)   | `provider_readiness_indicator` | "Provider readiness status"                           | Provider readiness — click to open Settings / Providers         |
| All widgets · Rename-run pencil (✎)                | `rename_run_button`            | "Rename run"                                          | Rename run                                                      |
| All dialogs · Dialog close (✕)                     | `dialog_close_button`          | "Close dialog"                                        | Close                                                           |
| New Benchmark · Judge model refresh (↻)            | `judge_model_refresh_button`   | "Refresh judge model list"                            | Refresh the judge provider's model list                         |
| Result · Charts · Previous chart (◀)               | `chart_prev_button`            | "Previous chart"                                      | Previous chart                                                  |
| Result · Charts · Next chart (▶)                   | `chart_next_button`            | "Next chart"                                          | Next chart                                                      |
| Result · Charts · Detach chart                     | `detach_chart_button`          | "Detach chart"                                        | Open the chart in its own window                                |
| About dialog · Open data folder                    | `open_data_folder_button`      | "Open application data folder"                        | Open the application data folder                                |
| About dialog · Copy data-folder path               | `copy_data_folder_path_button` | "Copy application data folder path"                   | Copy the application data folder path                           |
| Settings / dialogs · Gate-busy indicator (spinner) | `gate_busy_indicator`          | "Inference in flight — controls temporarily disabled" | An inference is in flight; please wait.                         |
| Task Editor · Field-help icon (ⓘ)                  | `<field_key>_help_button`      | "Help: \<field label>"                                | About this field                                                |
| Task Editor · Validation-summary pill              | `validation_summary_button`    | "Validation summary — focus first issue"              | Click to focus the first task with a warning                    |

## Test plan

- STORY-089-AC-1 — e2e, table-driven (`pytest-qt`), parametrized one case per registry row,
  `tests/e2e/test_icon_only_registry_conformance.py`,
  `test_every_registry_control_uses_its_pinned_name_objectname_and_tooltip`. Each case mounts the
  wired application, navigates to the control's screen, and asserts `objectName()`,
  `accessibleName()`, and `toolTip()` equal the pinned values. Placed in the e2e tier because it
  mounts the whole wired application and `just test-e2e` is the only recipe that pins
  `QT_QPA_PLATFORM=offscreen` (justfile line 46); `tests/integration/` is not run offscreen and is
  known to fail under it. Passes only once STORY-097/098/099 have realized every row.

## Definition of done

- [ ] STORY-089-AC-1 has a passing table-driven test that names STORY-089 and covers every registry
  row.
- [ ] The three child stories (STORY-097, STORY-098, STORY-099) are `done`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-091** (accessibility-floor verification suite) — flip it `draft` → `ready` immediately.
  STORY-089 is its only remaining dependency once STORY-090 is removed from its `depends_on`
  (STORY-090 is superseded by ADR-0018).
- **STORY-093** (Phase-12 traceability, risk, and architecture docs) — flip it `draft` → `ready`
  only once every other story it depends on is also `done`.

**What to do on completion**

Once STORY-089's acceptance-criteria test passes:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependency in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping
   silently. STORY-091 is the natural next pick: it is unblocked by this story and is the last
   accessibility-floor story before STORY-093 closes the phase.

## Notes

- **The `modules:` list is the assertion surface, not the edit surface.** This story adds a single
  test file under `tests/e2e/` and edits no module in `src/`. The eight paths in `modules:` are the
  UI packages that *mount* the 17 registry controls the test asserts, which is what makes the test
  meaningful for traceability; the code changes that make those assertions pass are delivered by
  STORY-097/098/099 and are attributed to those stories' own `modules:` entries. Eight modules
  exceeds the `L` bound of five, and the story is still `L` rather than split, because splitting it
  would recreate exactly the per-module partition that already exists as STORY-097/098/099 and
  would destroy the single-table regression property that is the entire point of this story. This
  disclosure follows the precedent set by STORY-094 and STORY-096, whose `modules:` likewise cite
  the modules their non-`src/` deliverable relates to rather than the files they change.
- `ui/resume_benchmark/` is deliberately **not** in `modules:`. Its rename pencil is painted by a
  `QStyledItemDelegate` and has no `objectName` or `toolTip` to assert (STORY-098 covers it through
  the table model's `Qt.ItemDataRole.AccessibleTextRole` instead); the `rename_run_button` row is
  asserted against the widget-backed pencil in `ui/progress/`.
