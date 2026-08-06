---
id: STORY-098
title: Add accessible names, objectNames, and tooltips to the New Benchmark, Resume, and Progress widgets
status: ready
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names
modules:
  - ui/new_benchmark/
  - ui/resume_benchmark/
  - ui/progress/
  - adapters/qt_table_models/
acceptance_criteria:
  - STORY-098-AC-1
  - STORY-098-AC-2
  - STORY-098-AC-3
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: L
---

# STORY-098 — Add accessible names, objectNames, and tooltips to the New Benchmark, Resume, and Progress widgets

## Goal

Bring the three benchmark-workflow surfaces up to the accessible-name floor: every interactive
control in the New Benchmark panel, the Resume panel, and the live Progress surface exposes a
non-empty accessible name, and the icon-only/ambiguous controls in these modules carry their exact
pinned objectName, accessible name, and tooltip. Second of three per-workspace child stories under
the STORY-089 sweep.

These modules contain the application's only two accessible-name calls that already exist
(`ui/progress/`'s stage badge), and the Resume run table's per-row Rename and overflow actions,
which are painted glyphs rather than widgets and therefore need a different naming mechanism —
see Design constraints.

## In scope

- A non-empty, descriptive accessible name on every interactive control in `ui/new_benchmark/`,
  `ui/resume_benchmark/`, and `ui/progress/` — including the mode toggles, size toggles, steppers,
  the past-run table, search fields, action buttons, and the stability/log surfaces.
- The exact pinned objectName, accessible name, and tooltip for the two §7.2 registry rows this
  story owns: the New Benchmark judge-model refresh button and the rename-run pencil.
- Extending `adapters/qt_table_models/` so a table model can answer
  `Qt.ItemDataRole.AccessibleTextRole`, and using it to give the Resume table's delegate-painted
  row actions an accessible name.

## Out of scope

- Main window, common dialogs, shared primitives, dropdowns — owned by STORY-097.
- Result, Settings, and Task Editor controls — owned by STORY-099. In particular the Providers
  table's own delegate-painted row actions (`ui/settings_dialog/_internal/providers_tab/row_actions_delegate.py`
  — the Enabled checkbox, Test ⚡, More ⋯) are STORY-099's, even though they use the same
  `AccessibleTextRole` mechanism this story adds to `adapters/qt_table_models/`.
- The `dialog_close_button` and `gate_busy_indicator` registry rows — owned by STORY-097, which
  defines both as shared primitives; any dialog these modules open mounts STORY-097's primitive
  rather than restating the pinned strings.
- The app-wide registry-conformance assertion over all 17 rows — owned by the parent STORY-089.
- The generic floor verification suite — owned by STORY-091.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — every interactive element
  exposes a programmatically queryable accessible name; the accessible-name source per element
  kind, including a table's content-describing name and its column header text, and an input
  field's label as its name; an icon-only control must never ship with an empty or generic name.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names`
  — the pinned canonical values for the judge-model refresh button and the rename-run pencil, and
  the rule that a repeated control (the pencil) shares one objectName pattern across every screen
  it appears on.

## Design constraints

- The accessible name (user-facing) and the objectName (test handle) are independent and both
  mandatory.
- The rename-run pencil uses the one shared `rename_run_button` objectName pattern wherever it is
  a real widget.
- **A control painted by a `QStyledItemDelegate` is not a `QWidget`, so `setAccessibleName` cannot
  be called on it.** `ui/resume_benchmark/_internal/row_actions_delegate.py` draws the rename
  pencil (`✎`) and the overflow (`⋯`) with `painter.drawText` into rects computed by
  `icon_rects_for_cell`, and hit-tests them in `editorEvent`. Nothing is instantiated per row —
  that is deliberate, so the table stays virtualised for hundreds of rows (EC-RB-12) — so there is
  no object for Qt accessibility to address and no object to hold an `objectName`. For these
  glyphs the accessible name must instead be published **by the table model**, as the cell's
  `Qt.ItemDataRole.AccessibleTextRole` text. `adapters/qt_table_models/_internal/base.py`'s
  `data()` currently short-circuits every role other than `Qt.ItemDataRole.DisplayRole` and returns
  nothing, so the model must be extended to answer `AccessibleTextRole` for the actions column with
  text that names the row's available actions using the registry's canonical wording ("Rename run"
  for the pencil). The `objectName` half of the registry row is satisfied by the widget-backed
  pencil in `ui/progress/_internal/header.py`, which is a real `QPushButton`.
- The virtualisation property is load-bearing: do not "solve" the naming problem by replacing the
  delegate with per-row widgets.
- No `setStyleSheet`, no colour literal, no `asyncio` in the touched modules.

## Acceptance criteria

### STORY-098-AC-1

For every interactive control in `ui/new_benchmark/`, `ui/resume_benchmark/`, and `ui/progress/`,
the control reports a non-empty accessible name when mounted.

### STORY-098-AC-2

Each of the two §7.2 registry rows this story owns, when mounted on its screen as a widget, reports
exactly the pinned `objectName`, accessible name, and tooltip below — no substitute, abbreviated,
or generic value:

| Screen · control                    | objectName                   | Accessible name            | Tooltip                                 |
| ----------------------------------- | ---------------------------- | -------------------------- | --------------------------------------- |
| Progress · Rename-run pencil (✎)    | `rename_run_button`          | "Rename run"               | Rename run                              |
| New Benchmark · Judge model refresh | `judge_model_refresh_button` | "Refresh judge model list" | Refresh the judge provider's model list |

### STORY-098-AC-3

Given the Resume run table with at least one row, when the actions cell is queried for
`Qt.ItemDataRole.AccessibleTextRole`, then it returns non-empty text naming the row's rename action
with the registry's canonical wording "Rename run", and the delegate is still the only thing that
paints those glyphs — no per-row widget is created.

## Test plan

- STORY-098-AC-1 — integration (`pytest-qt`),
  `tests/integration/test_a11y_names_benchmark_surfaces.py`,
  `test_every_benchmark_surface_control_has_a_nonempty_accessible_name`.
- STORY-098-AC-2 — integration, table-driven (`pytest-qt`), same file,
  `test_benchmark_surface_registry_controls_use_pinned_values` — one
  `@pytest.mark.parametrize` case per row of the AC-2 table.
- STORY-098-AC-3 — unit, colocated
  `src/ollama_llm_bench/adapters/qt_table_models/tests/test_accessible_text_role.py`,
  `test_actions_cell_exposes_rename_run_as_accessible_text`, plus
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_row_actions_delegate.py`,
  `test_delegate_creates_no_per_row_widget`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-098.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-089** — the whole-registry conformance story. Flip it `draft` → `ready` **only once
  STORY-097 and STORY-099 are also `done`**; STORY-089 depends on all three children.

**What to do on completion**

Once STORY-098's acceptance-criteria tests pass:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependency in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping
   silently. The natural next pick is whichever of STORY-097 / STORY-099 is still open; STORY-099
   in particular reuses the `AccessibleTextRole` mechanism this story adds to
   `adapters/qt_table_models/`, so doing it immediately afterwards keeps that knowledge fresh.
