---
id: STORY-098
title: Add accessible names, objectNames, and tooltips to the New Benchmark, Resume, and Progress widgets
status: draft
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names
modules:
  - ui/new_benchmark/
  - ui/resume_benchmark/
  - ui/progress/
acceptance_criteria:
  - STORY-098-AC-1
  - STORY-098-AC-2
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: M
---

# STORY-098 — Add accessible names, objectNames, and tooltips to the New Benchmark, Resume, and Progress widgets

## Goal

Bring the three benchmark-workflow surfaces up to the accessible-name floor: every interactive
control in the New Benchmark panel, the Resume panel, and the live Progress surface exposes a
non-empty accessible name, and the icon-only/ambiguous controls in these modules carry their exact
pinned objectName, accessible name, and tooltip. Second of three per-workspace child stories under
the STORY-089 sweep.

## In scope

- A non-empty, descriptive accessible name on every interactive control in `ui/new_benchmark/`,
  `ui/resume_benchmark/`, and `ui/progress/` — including the mode toggles, size toggles, steppers,
  the past-run table, search fields, action buttons, and the stability/log surfaces.
- The exact pinned objectName, accessible name, and tooltip for the §7.2 registry controls that live
  in these modules: the New Benchmark judge-model refresh button, and any shared rename-run pencil
  instance mounted on the Resume run list.

## Out of scope

- Main window, common dialogs, shared primitives, dropdowns — owned by STORY-097.
- Result, Settings, and Task Editor controls — owned by STORY-099.
- The app-wide registry-conformance assertion — owned by the parent STORY-089.
- The generic floor verification suite — owned by STORY-091.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — the accessible-name source
  per element kind, including a table's content-describing name and its column header text, and an
  input field's label as its name.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#72-icon-only-and-ambiguous-control-registry-canonical-names`
  — the pinned canonical values for the New Benchmark judge-model refresh button and the shared
  rename-run pencil where it appears on these surfaces.

## Design constraints

- The accessible name (user-facing) and the objectName (test handle) are independent and both
  mandatory.
- The shared rename-run pencil uses the one shared `rename_run_button` objectName pattern.
- No `setStyleSheet`, no colour literal, no `asyncio` in the touched modules.

## Acceptance criteria

### STORY-098-AC-1

For every interactive control in `ui/new_benchmark/`, `ui/resume_benchmark/`, and `ui/progress/`,
the control reports a non-empty accessible name when mounted.

### STORY-098-AC-2

For each §7.2 registry control that lives in these modules (the New Benchmark judge-model refresh
button, and each shared rename-run pencil instance on the Resume run list), the control exposes
exactly its pinned objectName, accessible name, and tooltip.

## Test plan

- STORY-098-AC-1 — integration (`pytest-qt`, offscreen),
  `tests/integration/test_a11y_names_benchmark_surfaces.py`,
  `test_every_benchmark_surface_control_has_a_nonempty_accessible_name`.
- STORY-098-AC-2 — integration, table-driven (`pytest-qt`), same file,
  `test_benchmark_surface_registry_controls_use_pinned_values`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-098.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
