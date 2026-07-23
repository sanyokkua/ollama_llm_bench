---
id: STORY-091
title: Add the accessibility-floor verification suite of objectName, accessible-name, click-target, focus-ring, and no-shortcut checks
status: draft
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#10-verification-method
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#6-click-target-size
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#5-focus-indication
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#4-mouse-only-operation
modules:
  - ui/main_window/
  - ui/theme/
  - ui/shared/
acceptance_criteria:
  - STORY-091-AC-1
  - STORY-091-AC-2
  - STORY-091-AC-3
  - STORY-091-AC-4
  - STORY-091-AC-5
edge_cases: []
depends_on:
  - STORY-089
  - STORY-090
adrs: []
owner: tester
estimate: M
---

# STORY-091 — Add the accessibility-floor verification suite of objectName, accessible-name, click-target, focus-ring, and no-shortcut checks

## Goal

Make the accessibility floor's five automated release-blocking checks real and enforced. The floor's
verification-method table names five automated tests, none of which exist today: an objectName
architecture test, an accessible-name walker over every interactive control, a minimum click-target
size check, a focus-ring visibility check on focus-retaining input controls, and a mouse-only grep
gate asserting no custom keyboard shortcut, accelerator, or mnemonic is registered. This story adds
all five as generic, app-wide checks so a regression in any widget fails the build.

## In scope

- An architecture test asserting every interactive control sets a non-empty, author-assigned
  `objectName` (§7.1, §10).
- An accessible-name walker that mounts the application and asserts every interactive element,
  especially every icon-only button, reports a non-empty accessible name (§7, §10).
- A click-target check that queries the bounding rect of every interactive control and asserts a
  minimum hit area of 24 × 24 logical pixels at default scale (§6, §10).
- A focus-ring check asserting each focus-retaining input control (text inputs, combos, spinners,
  lists, tables — not momentary buttons) reports a focus state and renders the ring after a click
  (§5, §10).
- A mouse-only grep gate over the source asserting no custom `QShortcut`, `QAction`
  accelerator/mnemonic, or `&`-mnemonic is registered; the toolkit's built-in modal Enter/Esc
  defaults are exempt (§4, §10).

## Out of scope

- Setting the accessible names, objectNames, and tooltips the walker/objectName tests assert —
  delivered by STORY-089 and its children; this story is the verification, and depends on that work.
- Implementing reduced-motion/high-contrast behaviour — delivered by STORY-090; the two §10
  preference tests belong with that behaviour, not this suite.
- The WCAG contrast matrix and the colour-never-sole-channel checks — already covered by STORY-049 /
  STORY-050; not re-implemented here.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#10-verification-method` — the verification table
  that assigns each floor requirement its automated check; this story implements the objectName,
  accessible-name, click-target, focus-indication, and mouse-only rows.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — every interactive element
  reports a non-empty accessible name; the walker asserts it.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#6-click-target-size` — the 24 × 24 logical-pixel
  minimum hit area for every clickable control.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#5-focus-indication` — the focus ring is rendered on
  every focus-retaining input control when it holds focus.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#4-mouse-only-operation` — no custom shortcut,
  accelerator, or mnemonic is registered anywhere; the built-in modal Enter/Esc defaults are exempt.

## Design constraints

- The walker and click-target checks run under the offscreen Qt platform plugin and mount the wired
  application, so they observe the real widget tree (cited modules `ui/main_window/`, `ui/theme/`,
  `ui/shared/` are the load-bearing shell, focus-ring source, and primitives the checks traverse;
  the walk reaches every widget mounted in the shell).
- The objectName and mouse-only checks are static/architecture tests over the source tree.
- The focus-ring check distinguishes focus-retaining input controls from momentary buttons, per the
  floor's DD-52 carve-out.

## Acceptance criteria

### STORY-091-AC-1

Given the application source tree, when the objectName architecture test runs, then it fails if any
interactive control sets an empty or auto-generated `objectName`, and passes when every interactive
control sets a non-empty author-assigned one.

### STORY-091-AC-2

Given the wired application mounted offscreen, when the accessible-name walker runs, then it fails if
any interactive element (especially any icon-only button) reports an empty accessible name, and
passes when every interactive element reports a non-empty one.

### STORY-091-AC-3

For every clickable control in the mounted application, its hit area is at least 24 × 24 logical
pixels at the default scale.

### STORY-091-AC-4

Given a focus-retaining input control, when it acquires focus by a click, then it reports a focus
state and renders the focus ring.

### STORY-091-AC-5

Given the application source tree, when the mouse-only grep gate runs, then it fails if any custom
`QShortcut`, `QAction` accelerator/mnemonic, or `&`-mnemonic is registered, treating the toolkit's
built-in modal Enter/Esc defaults as exempt.

## Test plan

- STORY-091-AC-1 — architecture, `tests/architecture/test_objectnames_present.py`,
  `test_every_interactive_control_sets_a_nonempty_objectname`.
- STORY-091-AC-2 — integration (`pytest-qt`, offscreen), `tests/integration/test_accessible_name_walker.py`,
  `test_every_interactive_element_has_a_nonempty_accessible_name`.
- STORY-091-AC-3 — integration (`pytest-qt`, offscreen), `tests/integration/test_click_target_size.py`,
  `test_every_clickable_control_meets_24px_minimum_hit_area`.
- STORY-091-AC-4 — integration (`pytest-qt`, offscreen), `tests/integration/test_focus_ring_visibility.py`,
  `test_focus_retaining_input_renders_focus_ring_on_click`.
- STORY-091-AC-5 — architecture, `tests/architecture/test_no_custom_keyboard_shortcuts.py`,
  `test_no_custom_shortcut_accelerator_or_mnemonic_is_registered`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-091.
- [ ] The five checks run in the offline pull-request gate.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
