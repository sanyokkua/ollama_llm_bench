---
id: STORY-097
title: Add accessible names, objectNames, and tooltips to the main window, common dialogs, and shared primitives
status: done
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names
modules:
  - ui/main_window/
  - ui/common_dialogs/
  - ui/shared/
  - ui/shared/provider_dropdown/
  - ui/shared/model_dropdown/
acceptance_criteria:
  - STORY-097-AC-1
  - STORY-097-AC-2
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: L
---

# STORY-097 — Add accessible names, objectNames, and tooltips to the main window, common dialogs, and shared primitives

## Goal

Bring the application shell and the reusable primitives up to the accessible-name floor: every
interactive control in the main window, the shared modal dialogs, the shared visual primitives, and
the two reusable dropdowns exposes a non-empty accessible name, and the icon-only/ambiguous controls
in these modules carry their exact pinned objectName, accessible name, and tooltip. This is the
first of three per-workspace child stories under the STORY-089 sweep.

Today the whole application calls `setAccessibleName` four times — in `ui/progress/`'s stage badge
and `ui/shared/`'s health dot and badge label — and never calls `setAccessibleDescription`. Every
other control in these modules is anonymous to assistive technology and to a name-based UI test.

## In scope

- A non-empty, descriptive accessible name (`setAccessibleName`) on every interactive control in
  `ui/main_window/`, `ui/common_dialogs/`, `ui/shared/`, `ui/shared/provider_dropdown/`, and
  `ui/shared/model_dropdown/` — including the status dot (health state in words), tabs, tables, and
  input fields (from their associated label).
- The exact pinned objectName, accessible name, and tooltip for the ten §7.2 registry rows this
  story owns (listed in STORY-097-AC-2): the six Main Window rows, the shared dialog-close button,
  the two About dialog buttons, and the gate-busy indicator.
- Introducing the gate-busy indicator as a shared primitive in `ui/shared/` carrying the pinned
  `gate_busy_indicator` values, so the Settings dialog and every other dialog mount one instance
  rather than each inventing its own.

## Out of scope

- New Benchmark, Resume, and Progress controls — owned by STORY-098.
- Result, Settings, and Task Editor controls — owned by STORY-099.
- **The `rename_run_button` registry row** — owned by STORY-098. The rename pencil is not mounted
  anywhere in this story's modules: the only two instances in the codebase are
  `ui/progress/_internal/header.py`'s pencil button and `ui/resume_benchmark/`'s delegate-painted
  ✎ glyph, both of which are STORY-098 modules. `ui/common_dialogs/` owns the rename *dialog*, not
  the pencil that opens it.
- The app-wide registry-conformance assertion over all 17 rows — owned by the parent STORY-089.
- The generic floor verification suite — owned by STORY-091.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — the accessible-name source
  per element kind (visible text for labelled controls; an explicit descriptive name for icon-only
  controls; the field label for inputs; a words-based health state for the status dot; the visible
  label for a tab; the title for a dialog).
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names`
  — the pinned canonical values for the registry controls that appear on the main window, the shared
  dialogs, and the About dialog; the rule that the accessible name, the objectName, and the tooltip
  are three distinct mandatory attributes; and the rule that repeated controls share one objectName
  pattern across every screen they appear on.

## Design constraints

- The accessible name (user-facing) and the objectName (test handle) are independent and both
  mandatory; renaming a label never changes an objectName.
- Repeated controls (dialog close) share one objectName pattern across every screen. `ui/shared/`
  is the single place the shared close button and the gate-busy indicator are defined, so
  STORY-099's sub-dialogs mount the same primitive instead of duplicating the pinned strings.
- **A control painted by a `QStyledItemDelegate` is not a `QWidget`, so `setAccessibleName` cannot
  be called on it.** For a painted glyph the accessible name must instead be published by the table
  model as the cell's `Qt.ItemDataRole.AccessibleTextRole` text — the delegate only draws pixels
  inside a cell rect and owns no object Qt accessibility can address. This story's five modules
  contain no `QStyledItemDelegate` subclass today (they live only in `ui/resume_benchmark/`,
  `ui/settings_dialog/`, and `ui/results/`), so every control here is named with a direct
  `setAccessibleName` call; if a delegate-painted interactive control is ever added to these
  modules it follows the model-role rule instead, and the registry row it realizes must be
  re-partitioned in STORY-089.
- No `setStyleSheet`, no colour literal, no `asyncio` in the touched modules.

## Acceptance criteria

### STORY-097-AC-1

For every interactive control in `ui/main_window/`, `ui/common_dialogs/`, `ui/shared/`,
`ui/shared/provider_dropdown/`, and `ui/shared/model_dropdown/`, the control reports a non-empty
accessible name when mounted.

### STORY-097-AC-2

Each of the ten §7.2 registry rows this story owns, when mounted on its screen, reports exactly the
pinned `objectName`, accessible name, and tooltip below — no substitute, abbreviated, or generic
value:

| Screen · control                         | objectName                     | Accessible name                                       | Tooltip                                                         |
| ---------------------------------------- | ------------------------------ | ----------------------------------------------------- | --------------------------------------------------------------- |
| Main Window · Settings menu (gear)       | `settings_menu_button`         | "Settings"                                            | Open the Settings dialog                                        |
| Main Window · About menu (info)          | `about_menu_button`            | "About"                                               | Application information: version, links, data folders           |
| Main Window · Benchmark workspace tab    | `workspace_benchmark_button`   | "Benchmark workspace"                                 | Benchmark workspace                                             |
| Main Window · Task Editor workspace tab  | `workspace_task_editor_button` | "Task Editor workspace"                               | Task Editor workspace                                           |
| Main Window · Running pill               | `running_pill_button`          | "Run in progress — open Progress"                     | Switch to the Benchmark workspace and focus the Progress widget |
| Main Window · Provider-readiness dot     | `provider_readiness_indicator` | "Provider readiness status"                           | Provider readiness — click to open Settings / Providers         |
| All dialogs · Dialog close (✕)           | `dialog_close_button`          | "Close dialog"                                        | Close                                                           |
| About dialog · Open data folder          | `open_data_folder_button`      | "Open application data folder"                        | Open the application data folder                                |
| About dialog · Copy data-folder path     | `copy_data_folder_path_button` | "Copy application data folder path"                   | Copy the application data folder path                           |
| Settings / dialogs · Gate-busy indicator | `gate_busy_indicator`          | "Inference in flight — controls temporarily disabled" | An inference is in flight; please wait.                         |

## Test plan

- STORY-097-AC-1 — integration (`pytest-qt`), `tests/integration/test_a11y_names_shell.py`,
  `test_every_shell_control_has_a_nonempty_accessible_name` (walks the mounted subtree of each
  module and asserts a non-empty accessible name on every interactive control).

- STORY-097-AC-2 — integration, table-driven (`pytest-qt`), same file, proven by **three**
  branch-free tests, each declaring `Proves: STORY-097-AC-2` and each asserting `objectName()`,
  `accessibleName()`, and `toolTip()`:

  - `test_shell_registry_controls_use_pinned_values` — the five Main Window rows, one
    `@pytest.mark.parametrize` case each, asserting the tooltip in full.
  - `test_dialog_registry_controls_use_pinned_values` — the five dialog rows (the shared close
    button on two dialogs, the two About buttons, the gate-busy strip), likewise.
  - `test_readiness_dot_tooltip_leads_with_the_pinned_sentence` — the provider-readiness dot,
    asserting the **first line** of its tooltip, because the lines beneath carry the per-provider
    reachability detail the Main Window specification separately requires.

  Split into three rather than one because a single test covering both the shell and the dialogs
  would need an `if` in its body to choose which surface to mount, which `.claude/rules/testing.md`
  forbids.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-097.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.
- [x] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [x] The next candidate stories are proposed in the closing report.

## Notes

### What shipped

Both acceptance criteria pass as 12 tests in `tests/integration/test_a11y_names_shell.py`. Every
interactive control in the menu bar, the status bar, the seven shared modal dialogs, and the shared
visual primitives now reports a non-empty accessible name, and the ten registry-pinned controls
carry their exact objectName, announced name, and tooltip.

Two new shared primitives were added so the repeated pinned strings are written down once rather
than retyped per dialog: `make_dialog_close_button` and `make_gate_busy_indicator` in `ui/shared/`.

### Decisions taken during implementation

**The pinned "dialog close (✕)" control is the existing footer Close button.** The mockups draw a
✕ inside a coloured dialog header, but the real application uses ordinary windows, so that ✕ is
drawn by the operating system and no Qt object exists to name. `Cancel` and `Back` buttons that sit
beside a distinct confirm button are not dialog-close buttons and were left alone.

**The gate-busy indicator is a static text strip, not an animated spinner.** The registry table
calls it a spinner, but every mockup draws a static strip, and ADR-0018 removed support for the
operating system's reduced-motion preference — so a looping animation would have no way for a user
to switch it off.

**The provider-readiness dot's tooltip leads with the pinned sentence and keeps the per-provider
reachability list beneath it,** separated by a blank line. This resolves a direct contradiction
between the Main Window specification (which requires the per-provider detail) and the
accessibility registry (which pins one fixed sentence) without removing anything a user can see
today. Its test asserts a first-line match; the other nine rows assert full equality.

**The Settings button's tooltip is state-dependent** — the pinned "Open the Settings dialog" when
enabled, and the specification's "Disabled - a benchmark is in progress." when disabled. Before
this story the enabled state carried an empty tooltip.

**This story resolves a second spec contradiction, not just the tooltip one above.**
`ui/shared/_internal/health_dot.py`'s `make_health_dot` sets the dot's own accessible name to the
health state in words (for example `"LIVE: Ready"`), matching the accessibility floor's §7
element table and this story's own **In scope** bullet, both of which say a status dot's
accessible name states the health state in words. But `status_bar.py` immediately overwrites
that name with the registry's pinned static string `"Provider readiness status"`, because §7.2
pins that exact string for this control. Nothing is lost to a user: the dot's child `QLabel`
still carries "Ready"/"Degraded"/"Not ready" as its own accessible text, and the tooltip keeps
the per-provider detail. `status_bar.py` is `make_health_dot`'s only real consumer (the one other
reference, in `ui/main_window/api.py`, is a docstring mention, not a call), so the
state-in-words name `make_health_dot` builds is now unused by every mounted instance in the
application — it is immediately overwritten every time. This is recorded here so STORY-089's
whole-registry sweep does not independently re-derive §7's status-dot row as unmet and "fix" it
back to the state-in-words name, which would break the pinned registry value instead.

**Acceptance criterion 2 is proven by three tests rather than one.** A single parametrised test
covering both the shell and the dialogs would need an `if` in its body to choose which surface to
mount, which `.claude/rules/testing.md` forbids. The traceability generator accepts more than one
test per criterion.

**The accessible-name walker deliberately skips Qt's own internal parts of composite controls** —
a dropdown's popup list view, and a table's column headers and corner button. No application code
constructs any of them, so no amount of naming work could ever have made the walker green. A
`_has_composite_ancestor` helper excludes any control whose ancestor chain contains a `QComboBox`
or `QAbstractItemView`; both classes remain in the walker's interactive set, so a dropdown and a
table each still need their own name. Known limitation: a control placed inside a table cell via
`setCellWidget` would also be skipped. No such control exists today. A second, opposite-direction
limitation: a `QSpinBox` carries one Qt-constructed, anonymous `QLineEdit` child, and
`QAbstractSpinBox` is in the walker's interactive set but **not** in `_COMPOSITE_TYPES` — so if
STORY-098 or STORY-099 reuse this walker on a surface containing a spin box, that internal edit
will be reported as an unnamed control that no application code can name. This fails *safe* (a
spurious test failure demanding attention, not a silent skip that hides a real gap); the fix when
that day comes is adding `QAbstractSpinBox` to `_COMPOSITE_TYPES`. No spin box exists in this
story's five modules today, so no code changes for this now — it is a note only.

**The shared dialog builders are exposed as a `common_dialogs` fixture in
`tests/integration/conftest.py`, not as an importable helper module.** The first attempt created a
standalone module and imported it as `from tests.integration.common_dialog_builders import ...`,
which requires `tests/__init__.py` to exist or `mypy --strict` fails with "Source file found twice
under different module names" — and the `mypy-strict` pre-commit hook passes staged files in one
invocation, so it would have fired at commit time. STORY-083 deliberately deleted those
`__init__.py` files, and this repository has zero package-style test imports. Handing the dialogs
over through a fixture matches the pattern STORY-083 established for `seed_setting`.

### Scope taken beyond the two acceptance criteria

**Eight buttons across the shared dialogs, plus five quit-confirmation buttons, were given a test
handle they previously lacked**, following the existing `common_dialogs.<dialog>.<name>`
convention. This is wider than the acceptance criteria and was a deliberate choice so STORY-091's
automated handle check does not fail on day one. (The plan estimated nine dialog buttons; the
measured number is eight — the ninth was Generate Analysis's Cancel, handled in the same pass.)

**Three controls gained a new tooltip, not two.** Two controls that were disabled with no
explanation gained the tooltip the project's UI rules require: the Rename button in the Rename
Run dialog now explains which validation rule failed, and the Retry Selected button now says
"Select at least one row to retry." Each of those two tooltips sits on the only code path that
changes its button's enabled state. The third is the About dialog's repository link, which
gained the plain informational tooltip "Open the project's GitHub repository in your browser" —
that control is always enabled, so its tooltip does not explain a disabled state; it only tells
the user what clicking the link does.

**One architecture allowlist was extended.** `tests/architecture/test_story_065_run_analysis_and_generate_dialog.py`
pins the modules the Generate Analysis dialog may import; it already permitted
`ui.shared.model_dropdown` and `ui.shared.provider_dropdown`, and now also permits
`ollama_llm_bench.ui.shared` for the gate-busy primitive. That test's purpose is to stop the dialog
importing a backend Store/Service Protocol directly, which this change does not affect.

### Verification

Full suite `2464 passed` (baseline 2446 plus this story's 18 tests), run without
`QT_QPA_PLATFORM=offscreen`. `just lint`, `just format-check`, `just typecheck`
(1055 files), `just import-check`, and `just arch-test` (1345 passed) all clean;
`just coverage-layers` 88.6% against an 80% floor; `just trace-check` reports zero gaps.

### Follow-up filed: this story's tests add measurable suite pressure

STORY-117 records a measured finding from this story's close-out. Eleven sequential full-suite
runs — five at the pre-story commit, six after — showed 2 native crashes and 2 unrelated
`ui/resume_benchmark` menu-action failures after this story, against zero of either before. The
failures are not defects in this story's code (`ui/resume_benchmark/` is untouched, the factory
those tests mock is unchanged, and that file passes 18/18 in isolation), but this story's tests
build the whole application 7 times and construct 42 dialogs in one process, against a suite with
a documented Qt-accumulation crash sensitivity. STORY-117 reduces that churn and re-measures.

The suite is flaky at this commit and at the pre-story baseline alike — the project's documented
~1-in-3 native crash inside CPython's cyclic GC, plus independent timing flakes. Two clean
full-suite runs at HEAD and two at the baseline were used to separate genuine failures from noise.

## Unblocks and next steps

**Unblocks**

- **STORY-089** — the whole-registry conformance story. Flip it `draft` → `ready` **only once
  STORY-098 and STORY-099 are also `done`**; STORY-089 depends on all three children.

**What to do on completion**

Once STORY-097's acceptance-criteria tests pass:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependency in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping
   silently. The natural next pick is whichever of STORY-098 / STORY-099 is still open, since both
   are unblocked from the start and both gate STORY-089.
