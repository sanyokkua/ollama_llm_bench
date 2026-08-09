---
id: STORY-119
title: Raise the theme's minimum control sizes to the 24x24 click-target floor and make the focus-ring check pass on the native platform
status: done
spec_clauses:
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#6-click-target-size
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#5-focus-indication
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#10-verification-method
  - 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#4-mouse-only-operation
  - 16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment
  - 01_Main_Window/description.md#2-window-layout
  - 01_Main_Window/description.md#14-accessibility
modules:
  - ui/theme/
  - ui/main_window/
acceptance_criteria:
  - STORY-119-AC-1
  - STORY-119-AC-2
  - STORY-119-AC-3
edge_cases: []
depends_on:
  - STORY-091
adrs: []
owner: coder
estimate: M
---

# STORY-119 — Raise the theme's minimum control sizes to the 24x24 click-target floor and make the focus-ring check pass on the native platform

## Goal

On a real desktop the application ships combo boxes 18 pixels tall, spin boxes 19 pixels tall
and text-less checkboxes 19 pixels wide — well under the accessibility floor's 24 x 24 logical
pixel minimum, which the floor calls a release-blocking defect. Nobody noticed because both
`just check`'s e2e tier under CI and `just test-e2e` pin the offscreen Qt platform plugin, where
the metrics differ. This story raises the floor in the one module allowed to style anything, so
a real macOS/Windows/Linux user gets controls they can actually aim at, and repairs the focus
check so it verifies what the floor requires on every platform rather than only offscreen.

This also unblocks the project: `just check` has been red on `feature/spec-v3-implementation`
since commit `efb06fa`, so no story can honestly claim "gate green" until this lands. STORY-085
is finished and parked at `ready` for exactly this reason.

## In scope

- `src/ollama_llm_bench/ui/theme/_internal/stylesheet_builder.py::render_stylesheet` gains
  minimum-size rules for the interactive classes the application stylesheet pulls off the native
  platform style. **Measured outcome** (the values below are what the rendered widgets do on
  macOS, not what the declarations suggest):
  - `QComboBox, QAbstractSpinBox { min-height: 24px }` — combos land exactly on 24, spin boxes on
    26 (their 2 px frame adds on top of the content height).
  - `QCheckBox::indicator { width: 24px; height: 24px }` — the checkbox violation is width
    (19x24), and `min-width` on `QCheckBox` itself is the wrong lever: it grows the *contents*
    box beside the indicator, giving a 43 px-wide widget without enlarging the aim target.
    Sizing the indicator subcontrol gives 26x24 and moves the **real** click rect to 24x24 — see
    "Third finding" for why the obvious alternatives do not. The drawn glyph is platform-dependent:
    on macOS it stays at its native size inside the larger box (pixel histogram byte-identical in
    both themes, checked and unchecked), while under the Fusion style used offscreen and on
    Linux/Windows it scales up with the indicator. That visual change is deliberate — see "Second
    finding".
  - **No `QPushButton` rule.** A styled `QPushButton` already hints 24 px tall; adding
    `min-height: 24px` inflates it to 32 because `padding: 4px 8px` applies, which would then not
    fit the menu bar. The two 20 px buttons are not a stylesheet problem — see below.
- `src/ollama_llm_bench/ui/main_window/_internal/menu_bar.py` — `_WorkspaceSwitcherWidget` gains
  `setMinimumHeight(24)`. **`_MENU_BAR_HEIGHT` stays 32**: `01_Main_Window/description.md` §2
  pins the menu bar at "Fixed height 32 px", so raising it is not available. The real cause,
  reproduced in isolation with no application code, is that a nested `QWidget` inside a
  `QHBoxLayout` raises that layout's minimum height by 12 px over its tallest child — the bar's
  layout asks for 36 and has 32, and Qt resolves the shortfall by shrinking that one nested
  branch to 20 px, taking both segment buttons with it. An explicit minimum is honoured strictly,
  so the buttons render 24 inside the unchanged 32 px bar (measured 77x20 before, 77x24 after).
- `tests/e2e/test_focus_ring_visibility.py`: a new check that drives focus with
  `QWidget.setFocus()` instead of a click, covering every focus-retaining type including
  `QComboBox`, with the existing `_image_contains_color` ring assertion untouched. The
  `hidePopup()` workaround — which exists only to service the click path — is deleted along with
  the click path for combos.
- `tests/e2e/test_click_target_size.py`: a new check proving no walked control is under either
  dimension, with the walked-count floor asserted **before** the violation assert so it actually
  executes.
- An architecture check that neither e2e module can be made to "pass" by skipping.

## Out of scope

- **Any edit under `docs/v3_specification/`.** That tree is read-only. The §10-versus-§5 conflict
  this story surfaces is recorded below under "Open spec conflict" for an owner ruling; it is
  never resolved silently in code or by editing the spec.
- **Changing the product's combo-box focus behaviour.** Forcing a `QComboBox` to retain focus
  through a click would fight the macOS Human Interface Guidelines, where popup buttons are
  deliberately not click-focusable, and would mean re-implementing Qt's popup focus handling. The
  product behaviour is correct; the test's mechanism was wrong.
- **Removing the nine existing `setMinimumHeight(24)  # 08_ACCESSIBILITY_FLOOR.md §6` call
  sites.** After the QSS change they are redundant, but they are not wrong, and deleting them is
  churn with a blast radius this story does not need.
- **`tests/e2e/test_accessible_name_walker.py`.** It passes on both platforms; it is not touched.
- Re-specifying the five accessibility checks themselves — STORY-091 owns their existence; this
  story fixes the product defect one of them found and the platform assumption another made.

## Spec inputs

- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#6-click-target-size` — the binding rule: **every
  clickable control** offers a hit area of at least 24 x 24 logical pixels at the application's
  default scale; the list is explicit ("every button … every checkbox and toggle, every dropdown
  chevron …") and carries no platform or widget-class exemption; a control shipping below the
  minimum "is a release-blocking defect". This is what makes the 27 measured violations a product
  defect rather than a measurement artifact.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#5-focus-indication` — what the focus check must
  actually assert: the ring is rendered "for the focused control at all times" for focus-retaining
  input controls, and "a control that can receive focus but shows no focus ring is a
  release-blocking defect". The obligation is on a control **that holds focus**; §5 does not make
  acquiring focus from a click part of the ring requirement.
- `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md#10-verification-method` — the two verification
  rows this story repairs: the click-target row ("an automated test queries the bounding rect of
  every interactive control and asserts the minimum hit area") and the focus row, whose wording
  ("reports a focus state and renders the ring **after a click**") is the clause in conflict — see
  "Open spec conflict" below.
- `16_Engineering_Standards/07_TESTING_STANDARD.md#12-the-ci-test-environment` — the Qt-platform
  row of the local/CI parity table: local runs use "the native platform", CI uses "the offscreen
  Qt platform plugin". Parity is the standard's stated intent, so a check that passes offscreen
  and fails natively is a parity break the standard does not sanction — the fix is to make the
  check hold on both, never to pin one platform or skip the other.

## Design constraints

- **The fix belongs in the theme, class-wide in the QSS — not per widget.** `ui/theme/` is the
  single styling authority and is itself the *cause*: the `QMainWindow, QDialog, QWidget { … }`
  rule in `render_stylesheet` switches these classes off the native style onto Qt's
  `QStyleSheetStyle`, whose default metrics collapse below the floor (bare styled sizeHints
  measured on macOS: `QComboBox` 85x18 against 103x32 unstyled, `QPushButton` 75x24 against
  99x32, `QSpinBox` 36x19 against 36x21). Patching the handful of controls the walker happens to
  reach would leave every other combo and spin box in the application under the floor, and would
  put sizing decisions in widget code, which is exactly what the styling-authority rule forbids.
  This is a **new precedent for `stylesheet_builder.py`** — today it emits no height or width of
  any kind, only `padding` on three button roles — and it is deliberate: a floor that derives from
  the stylesheet must be repaired in the stylesheet.
- **Measure the padding interaction; do not assume it.** In Qt style sheets `min-height` is the
  *content* height and padding adds on top: a styled `QPushButton` carrying
  `padding: 4px 8px` goes from 24 to 32 px when given `min-height: 24px`. Pick each selector's
  declared value so the rendered total clears 24 px without ballooning the control, and verify by
  measuring the rendered widget — not by reasoning about the value you wrote.
- **Express the floor as a named constant, not a bare literal.** The 24 px minimum is a
  specification constant, not a design token; declare it once in the theme module (for example
  `_MIN_CLICK_TARGET_PX: Final = 24`) with a comment citing §6, and derive each selector's
  declared minimum from it. Do not invent a new spacing or colour token for this.
- **The menu bar is a fixed-height container, so it is the one place the change can bite.**
  `menu_bar.py` sets `_MENU_BAR_HEIGHT = 32` and `setFixedHeight(_MENU_BAR_HEIGHT)` with zero
  layout margins, and its two workspace buttons currently render 75x20 even though a bare styled
  `QPushButton` hints 24. Never shrink the buttons back under the floor to fit the bar. Raising
  `_MENU_BAR_HEIGHT` is **not** an available fix either: `01_Main_Window/description.md` §2 pins
  the bar at "Fixed height 32 px". The floor and the pinned height are compatible — see "In
  scope" for the nested-layout cause and the one-line fix that satisfies both.
- **The class-wide QSS change alters control heights on every screen.** That is the accepted cost
  of fixing the cause rather than the symptoms, and it is this story's main risk. The
  STORY-087 screenshot/mockup-conformance harness is the control for it — see "Verification".
- **Do not repoint an existing `Proves:` line.** `tests/e2e/test_click_target_size.py`'s
  `test_every_clickable_control_meets_24px_minimum_hit_area` keeps `Proves: STORY-091-AC-3` and
  `tests/e2e/test_focus_ring_visibility.py`'s `test_focus_retaining_input_renders_focus_ring_on_click`
  keeps `Proves: STORY-091-AC-4`. STORY-091 is `done`; moving its proof onto this story's ids
  would leave a `done` story with an unproven acceptance criterion and fail `just trace-check`.
  This story therefore **adds** a sibling test per file and narrows the existing click-based focus
  test to the control types that genuinely acquire focus from a click (`QLineEdit`, `QTextEdit`,
  `QAbstractSpinBox`, `QAbstractItemView` — verified to work on both platforms), leaving combo
  coverage to the new `setFocus()` check.
- **Extract the shared walk.** The two click-target tests must share one module-level helper that
  collects the violation list; do not copy the comprehension. Both `mounted_app_surfaces` and
  `qtbot` are function-scoped, so the second test pays a second application mount — keep each test
  inside the 60-second e2e budget.
- **Never fix a red check by skipping it.** No `pytest.mark.skipif`, no `pytest.mark.xfail`, no
  `pytest.skip(...)`, no branch on `QT_QPA_PLATFORM` or `QGuiApplication.platformName()` in either
  e2e module. AC-3 exists to make that permanent.
- **The `_MIN_EXPECTED_CHECKED` / `_MIN_EXPECTED_WALKED` coverage floors have never executed on a
  native run**, because both sit after the violation assert that has always failed first.
  Re-derive each from an actual passing native run rather than assuming the current numbers still
  describe the walked set after the tests are split.
- Both e2e modules already carry `@pytest.mark.allow_qt_warnings` for the offscreen plugin's
  `propagateSizeHints()` warning; keep it on the new tests.

## Acceptance criteria

### STORY-119-AC-1

For every interactive control reached by the accessibility walker across `mounted_app_surfaces`
— the mounted application plus the Settings dialog and the seven shared modal dialogs — running
on the host's native Qt platform plugin, the control's width is at least 24 logical pixels and
its height is at least 24 logical pixels.

### STORY-119-AC-2

For every enabled, visible focus-retaining input control reached by the walker — `QComboBox`,
`QLineEdit`, `QTextEdit`, `QAbstractSpinBox`, `QAbstractItemView` — while that control holds
focus, its grabbed image contains the active theme's `border_focus` colour; this holds on the
host's native Qt platform plugin and on the offscreen plugin alike.

### STORY-119-AC-3

For every test function in `tests/e2e/test_click_target_size.py` and
`tests/e2e/test_focus_ring_visibility.py`, the test carries no skip, xfail, or
platform-conditional guard — no `pytest.mark.skipif`, no `pytest.mark.xfail`, no `pytest.skip(...)`
call, and no branch on `QT_QPA_PLATFORM` or `QGuiApplication.platformName()` — so the identical
assertions execute under `just check` on the native platform and under `just test-e2e` offscreen.

## Test plan

- STORY-119-AC-1 — e2e (`pytest-qt`, mounts the wired application),
  `tests/e2e/test_click_target_size.py`,
  `test_no_walked_control_is_below_the_click_target_floor_in_either_dimension`. Reuses the
  `mounted_app_surfaces` and `interactive_descendants` fixtures and the extracted violation-list
  helper. Asserts the walked-count floor **first**, then that the violation list is empty, so the
  coverage floor is genuinely exercised.
- STORY-119-AC-1 (unit) — `src/ollama_llm_bench/ui/theme/tests/test_build_stylesheet.py`,
  `test_stylesheet_holds_interactive_classes_to_the_24px_click_target_floor`. Pins the emitted
  rules themselves, so a later token or selector edit that drops them fails in the theme's own
  fast suite rather than only in the e2e tier.
- STORY-119-AC-2 — e2e (`pytest-qt`, mounts the wired application),
  `tests/e2e/test_focus_ring_visibility.py`,
  `test_focus_retaining_input_renders_focus_ring_while_it_holds_focus`. Calls `control.setFocus()`
  in place of `qtbot.mouseClick`, drops the `hidePopup()` call, and keeps the
  `_image_contains_color` assertion against both themes' `border_focus` byte-for-byte. Disabled
  and hidden controls stay exempt for the reason already documented in the file.
- STORY-119-AC-3 — architecture, `tests/architecture/test_accessibility_e2e_platform_parity.py`,
  `test_accessibility_e2e_checks_carry_no_platform_skip`. AST-walks the two named e2e modules and
  asserts no decorator, call, or comparison in them matches the skip/xfail/platform-branch set
  named in AC-3.
- No `edge_cases:` entries. This story removes a product defect and repairs a test's platform
  assumption; it introduces no new error condition, and the accessibility floor's requirements are
  not modelled in the `EC-*` catalogs.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-119.
- [ ] `just check` is green on the host's **native** Qt platform — the state that has been red
  since `efb06fa`.
- [ ] `just test-e2e` is green offscreen, with no test skipped.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/theme/` and `ui/main_window/`.
- [ ] The STORY-087 screenshot harness has been re-run and its output re-reviewed against the
  mockups, with any changed control height judged acceptable or corrected.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
- [ ] The open spec conflict below is reported to the owner in the closing report, unresolved in
  code.
- [ ] STORY-085 has been re-checked and flipped to `done` if the now-green gate is its only
  remaining blocker.

## Second finding — the mockup's checkbox is below the floor

`02_New_Benchmark_Widget/mockup.html:40` declares `.checkbox{width:14px;height:14px}`. §6 requires
24 x 24 for "every checkbox and toggle". A 14 px checkbox cannot satisfy the floor, so the mockup
and the accessibility floor are in direct conflict, and the floor wins — §6 calls a control below
the minimum a release-blocking defect, while the mockup's 14 px is a decorative choice.

The consequence is visible: after this story a checkbox indicator renders 24 x 24 rather than the
mockup's 14 px, on every screen carrying one. That is recorded as a deliberate discrepancy in
`docs/development/mockup_conformance_review.md`, not silently absorbed. If the owner would rather
keep the mockup's proportions, that is a spec change to §6 or to the mockups, and needs its own
story — it must not be resolved by shrinking the control back under the floor.

## Third finding — the §10 bounding-rect method can pass vacuously

§10 prescribes verifying click-target size by querying "the bounding rect of every interactive
control". For `QCheckBox` that rect is **not** the aim target: Qt overrides `hitButton` to test
`SE_CheckBoxClickRect`, so a click landing inside the widget rect but outside that sub-rect is
ignored. Measured on this machine (text-less checkbox, both platforms):

| Strategy                                 | Widget rect | Real click rect (cocoa / offscreen) |
| ---------------------------------------- | ----------- | ----------------------------------- |
| unchanged                                | 19x24       | 19x18 / 18x18                       |
| `QCheckBox::indicator { 24px }` (chosen) | 26x24       | **24x24 / 24x24**                   |
| `QCheckBox { padding: 3px }` (rejected)  | 27x24       | 19x18 / **14x14**                   |

The rejected padding variant would have satisfied AC-1's rect assertion while leaving the aim
target unchanged on macOS and *shrinking* it under the Fusion style — a passing test over a
control the user still cannot hit. The chosen rule is the only one that moves the real hit area.

AC-1 keeps the rect assertion, because that is the method §10 names. The gap is recorded here:
a follow-up story should verify `SE_CheckBoxClickRect`/`hitButton` for composite controls, so the
floor cannot be met on paper by a widget that merely reserves space.

## Independent conformance review — findings carried to the owner

A `spec-conformance-reviewer` re-derived the ACs from the cited clauses and returned **conforms
with concerns**. One finding was a real defect and is fixed; the rest are escalations.

**Fixed during review.** The AC-3 architecture test could not detect `QGuiApplication.platformName()`
— the exact spelling AC-3 names — because attribute names were matched only against the skip set.
The walker now matches attribute names, bare names and string constants against both sets, and
covers `importorskip`, `skipIf`, `skipUnless`, `sys.platform`, and bare `"offscreen"`/`"cocoa"`
literals. Falsified with all three spellings (`QGuiApplication.platformName()`, `sys.platform`,
`pytest.importorskip`): each reddens the check, and the check passes again once removed.

**Escalation 1 — §4's click-focus mandate now has no combo-box coverage.** §4 ("Visible focus on
click … the only path by which focus is reached") is a product mandate, not just a verification
mechanism. Narrowing the click-based test to non-combo types leaves that mandate unverified for
combos, while STORY-091 stays `done` and `trace-check` stays green — the gate cannot see the
erosion. Stated plainly: this story's recommended resolution of the §5-versus-§10 conflict is
**already in force in the test suite**. Ratifying it is a formality; rejecting it means the gate
goes red again and a different mechanism must be found. That is the owner's call to make knowingly.

**Escalation 2 — the 22 px status bar cannot host a 24 px click target.** `01_Main_Window`
§2 pins the status bar at "Fixed height 22 px", and §4.2 makes the health dot clickable
(`status_bar.py` forwards `MouseButtonPress` on it). It structurally cannot reach 24 px inside a
22 px bar. It is never measured today because `make_health_dot` returns a plain `QWidget`, outside
the walker's interactive types. This is the same shape of collision as the menu bar, but without a
nested-layout escape hatch — it needs a ruling, not a fix.

**Escalation 3 — AC-1 is narrower than §6.** The walker collects only `QAbstractButton`,
`QComboBox`, `QLineEdit`, `QTextEdit`, `QAbstractSpinBox`, `QAbstractItemView`, and excludes
anything parented inside a composite. So §6's explicitly enumerated dropdown chevrons,
delegate-painted table-row selection checkboxes, chip-remove glyphs, menu items and title-bar
close glyphs are never measured. AC-1 should be read as "no regression in the measurable set",
not "§6 is now met". Inherited from STORY-091's walker design; worth its own story alongside the
`SE_CheckBoxClickRect` gap in "Third finding".

**Noted, no action.** After this change, `08_ACCESSIBILITY_FLOOR.md` §9's statement that "all
sizes derive from the design tokens in 08-D rather than from fixed pixel literals" is no longer
literally true of the emitted stylesheet. The 24 px floor is a specification constant rather than
a design token, and Qt treats stylesheet `px` as logical pixels, so text-scaling behaviour is
unaffected — but §9 is the clause a future reviewer will trip over.

## Open spec conflict — owner ruling required

`08_ACCESSIBILITY_FLOOR.md` §10's verification row for focus states the automated test asserts a
focus-retaining control "reports a focus state and renders the ring **after a click**". On macOS
that is unachievable for a **populated** combo box: clicking it opens the popup, the popup takes
keyboard focus, and `hidePopup()` does not hand it back — `hasFocus()` was still `False` after 50
`processEvents()` turns, so no amount of `qtbot.waitUntil` waiting fixes it. An **empty** combo
(for example `result_widget.run_dropdown` in the smoke app, which has no runs) does report `True`,
which is why the observed pass/fail split looks arbitrary. Offscreen there is no real popup
window, so focus never leaves and the clause appears to hold. `QLineEdit` and `QAbstractSpinBox`
acquire click focus fine on both platforms.

§5 — the clause the check exists to enforce — requires only that a control **which holds focus**
renders the ring. The click-acquisition claim lives in §4 and in §10's verification row, not in
§5's ring rule. DD-52 already carved momentary buttons out of this same check for precisely this
reason: "platform-dependent click focus … a verification that can actually pass on every
platform". It simply did not anticipate combo boxes.

**Recommendation:** extend DD-52's carve-out reasoning from momentary buttons to click-focus
acquisition generally, so the §10 focus row verifies the ring on a control that holds focus rather
than on the act of clicking. Whether that is recorded as an ADR or as a spec-issue entry against
§10 is the owner's call. `docs/v3_specification/` is read-only, so this story proposes no edit to
it and must not resolve the conflict silently in code.

## Verification

Run in this order:

1. `uv run pytest tests/e2e/test_click_target_size.py tests/e2e/test_focus_ring_visibility.py -q -p no:randomly`
   on the **native** platform (`platformName` `cocoa` on this machine) — the run that is currently
   red with 27 undersized controls and 4 focus failures.
1. `just test-e2e` — the same tests under the pinned offscreen plugin, confirming the fix did not
   trade one platform for the other.
1. `uv run pytest src/ollama_llm_bench/ui/theme -q` — the theme module's own colocated suite,
   which the new QSS rules can break.
1. `just check` — the full gate. **Budget roughly 30 minutes**: this repository has a known
   teardown slowdown that keeps a full run at about 100 % CPU throughout. A genuine hang shows
   near-zero CPU — use that to tell the two apart rather than the clock alone.
1. `just trace` then `just trace-check`.
1. `just screenshots`, re-reviewed against the STORY-087 mockup-conformance harness. This is the
   **main risk of the class-wide approach**: the QSS change alters control heights on every screen,
   not only the ones the walker reached.

## Negative controls

Prove each new assertion bites by falsifying the condition — never by deleting the assertion.

- **Click-target floor.** Set the new `min-height` to `1px` in `render_stylesheet` and re-run the
  click-target tests natively: both must go red, naming the same controls as today's failure list.
- **Focus ring.** Delete the `:focus` border rule from `render_stylesheet` and re-run the focus
  test: it must go red, proving the `_image_contains_color` ring assertion still bites after the
  switch from click to `setFocus()` and that the new test is not passing merely because focus is
  now easy to acquire.
- **Coverage floors.** With the suite green natively, confirm `_MIN_EXPECTED_WALKED` and the
  focus-check floors are actually reached and are still the right numbers. They sit after the
  violation assert, so they have never once executed on a native run; treat the current values as
  unverified until a green native run reports the real counts.
  **Measured:** `_MIN_EXPECTED_WALKED = 225` holds unchanged. The single `_MIN_EXPECTED_CHECKED = 17` splits into `_MIN_EXPECTED_CLICKED = 10` (the click path, combos removed) and
  `_MIN_EXPECTED_FOCUSED = 17` (the `setFocus()` path: the same 10 plus 7 combos). Both counts
  were read off a deliberately-failing run with the floors raised to 999, and are identical on
  the native and offscreen platforms.
