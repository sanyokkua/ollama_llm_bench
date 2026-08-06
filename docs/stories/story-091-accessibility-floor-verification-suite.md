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
adrs:
  - ADR-0018
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

**Blocked:** stays `draft` until STORY-089 is `done`. That is now its only dependency — STORY-090
was previously listed too, and has been removed because ADR-0018 retires it as `superseded` and it
will never reach `done`.

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
  delivered by STORY-089 and its children (STORY-097, STORY-098, STORY-099); this story is the
  verification, and depends on that work.
- **The floor's reduced-motion and high-contrast verification rows.** Those two §10 rows are
  permanently excluded by ADR-0018, which records the product owner's decision that the application
  ships without honoring the OS "Reduce motion" and "Increase contrast" settings. There is no
  behaviour for a test to assert, so no test is written. This is not a scope reduction of this
  story: the five checks below never covered motion or contrast in any revision of it.
- The WCAG contrast matrix and the colour-never-sole-channel checks — already covered by STORY-049 /
  STORY-050; not re-implemented here.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#10-verification-method` — the verification table
  that assigns each floor requirement its automated check; this story implements the objectName,
  accessible-name, click-target, focus-indication, and mouse-only rows, and deliberately leaves the
  reduced-motion and high-contrast rows unimplemented per ADR-0018.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#7-accessible-names` — every interactive element
  reports a non-empty accessible name; the walker asserts it. §7.1 additionally fixes the
  stable-`objectName` test-handle rule the architecture test enforces.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#6-click-target-size` — the 24 × 24 logical-pixel
  minimum hit area for every clickable control.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#5-focus-indication` — the focus ring is rendered on
  every focus-retaining input control when it holds focus; momentary buttons are exempt (DD-52).
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#4-mouse-only-operation` — no custom shortcut,
  accelerator, or mnemonic is registered anywhere; the built-in modal Enter/Esc defaults are exempt.

## Design constraints

- The walker, click-target, and focus-ring checks mount the **whole wired application**, so they
  belong in the **e2e tier**, not `tests/integration/`. `just test-e2e` is the only test recipe that
  pins `QT_QPA_PLATFORM=offscreen` (justfile line 46; the only other place that pins it is the
  `screenshots` recipe, line 58). `tests/integration/` is not run offscreen and is known to fail
  under it, so an "integration, offscreen" test is not a thing this repository can run.
- The cited modules `ui/main_window/`, `ui/theme/`, and `ui/shared/` are the load-bearing shell, the
  focus-ring token source, and the primitives the checks traverse; mounting the shell is what makes
  the walk reach every widget in the tree.
- The objectName and mouse-only checks are static/architecture tests over the source tree and need
  no `QApplication`; they stay in `tests/architecture/`.
- The focus-ring check distinguishes focus-retaining input controls from momentary buttons, per the
  floor's DD-52 carve-out — asserting the ring on a push button would fail on platforms where a
  push button does not take click-focus.
- The mouse-only grep gate must not flag the toolkit's built-in modal Enter/Esc behaviour (D-R-07),
  which registers nothing and therefore appears nowhere in the source it scans.

## Acceptance criteria

### STORY-091-AC-1

Given the application source tree, when the objectName architecture test runs, then it fails if any
interactive control sets an empty or auto-generated `objectName`, and passes when every interactive
control sets a non-empty author-assigned one.

### STORY-091-AC-2

Given the wired application mounted in the e2e tier, when the accessible-name walker runs, then it
fails if any interactive element (especially any icon-only button) reports an empty accessible name,
and passes when every interactive element reports a non-empty one.

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
- STORY-091-AC-2 — e2e (`pytest-qt`, mounts the wired application),
  `tests/e2e/test_accessible_name_walker.py`,
  `test_every_interactive_element_has_a_nonempty_accessible_name`.
- STORY-091-AC-3 — e2e (`pytest-qt`, mounts the wired application),
  `tests/e2e/test_click_target_size.py`,
  `test_every_clickable_control_meets_24px_minimum_hit_area`.
- STORY-091-AC-4 — e2e (`pytest-qt`, mounts the wired application),
  `tests/e2e/test_focus_ring_visibility.py`,
  `test_focus_retaining_input_renders_focus_ring_on_click`.
- STORY-091-AC-5 — architecture, `tests/architecture/test_no_custom_keyboard_shortcuts.py`,
  `test_no_custom_shortcut_accelerator_or_mnemonic_is_registered`.

Each of the three e2e tests must be proven to fail for the right reason before it is trusted:
falsify the condition (blank one control's accessible name, shrink one control below the minimum,
suppress one input's focus ring) and confirm the test goes red — deleting the assertion proves
nothing.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-091.
- [ ] The two architecture checks run in `just arch-test` and the three e2e checks run in
  `just test-e2e`; all five therefore run in the offline pull-request gate via `just check`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] Every story under **Unblocks** whose remaining dependencies are now `done` has been flipped
  `draft` → `ready`, and `just trace` re-run.
- [ ] The next candidate stories are proposed in the closing report.

## Unblocks and next steps

**Unblocks**

- **STORY-093** (Phase-12 traceability, risk, and architecture docs) — flip it `draft` → `ready`
  only once every other story it depends on is also `done`. STORY-093 is the terminal story of the
  finalization batch and depends on nearly all of it.

**What to do on completion**

Once STORY-091's acceptance-criteria tests pass:

1. For each story listed under **Unblocks**, check its remaining `depends_on` entries. Flip its
   `status` from `draft` to `ready` only if every one of them is now `done`; otherwise leave it
   `draft` and name the outstanding dependency in the closing report.
1. Re-run `just trace` — the traceability record embeds each story's `status`, so it goes stale the
   moment a status changes — and then `just trace-check`.
1. Propose the next stories to pick up, ranked, in the closing report rather than stopping silently.
   With this story `done` the accessibility thread is closed; the remaining finalization work is the
   packaging/release chain (STORY-094 → STORY-095 / STORY-096) and then STORY-093.
