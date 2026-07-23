---
id: STORY-097
title: Add accessible names, objectNames, and tooltips to the main window, common dialogs, and shared primitives
status: draft
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

## In scope

- A non-empty, descriptive accessible name (`setAccessibleName`) on every interactive control in
  `ui/main_window/`, `ui/common_dialogs/`, `ui/shared/`, `ui/shared/provider_dropdown/`, and
  `ui/shared/model_dropdown/` — including the status dot (health state in words), tabs, tables, and
  input fields (from their associated label).
- The exact pinned objectName, accessible name, and tooltip for the §7.2 registry controls that
  live in these modules: the Settings/About menu buttons, the two workspace tabs, the running pill,
  the provider-readiness dot, the shared rename-run pencil, the shared dialog-close button, and the
  About dialog's open-data-folder and copy-path buttons.

## Out of scope

- New Benchmark, Resume, and Progress controls — owned by STORY-098.
- Result, Settings, and Task Editor controls — owned by STORY-099.
- The app-wide registry-conformance assertion and coordination — owned by the parent STORY-089.
- The generic floor verification suite — owned by STORY-091.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — the accessible-name source
  per element kind (visible text for labelled controls; an explicit descriptive name for icon-only
  controls; the field label for inputs; a words-based health state for the status dot; the visible
  label for a tab; the title for a dialog).
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names`
  — the pinned canonical values for the registry controls that appear on the main window, the shared
  dialogs, and the About dialog.

## Design constraints

- The accessible name (user-facing) and the objectName (test handle) are independent and both
  mandatory; renaming a label never changes an objectName.
- Repeated controls (rename pencil, dialog close) share one objectName pattern across every screen.
- No `setStyleSheet`, no colour literal, no `asyncio` in the touched modules.

## Acceptance criteria

### STORY-097-AC-1

For every interactive control in `ui/main_window/`, `ui/common_dialogs/`, `ui/shared/`,
`ui/shared/provider_dropdown/`, and `ui/shared/model_dropdown/`, the control reports a non-empty
accessible name when mounted.

### STORY-097-AC-2

For each §7.2 registry control that lives in these modules (the Settings and About menu buttons, the
Benchmark and Task Editor workspace tabs, the running pill, the provider-readiness dot, the shared
rename-run pencil, the shared dialog-close button, and the About dialog's open-data-folder and
copy-path buttons), the control exposes exactly its pinned objectName, accessible name, and tooltip.

## Test plan

- STORY-097-AC-1 — integration (`pytest-qt`, offscreen), `tests/integration/test_a11y_names_shell.py`,
  `test_every_shell_control_has_a_nonempty_accessible_name` (walks the mounted subtree of each
  module and asserts a non-empty accessible name on every interactive control).
- STORY-097-AC-2 — integration, table-driven (`pytest-qt`), same file,
  `test_shell_registry_controls_use_pinned_values` (one parametrized case per registry control in
  these modules).

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-097.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
