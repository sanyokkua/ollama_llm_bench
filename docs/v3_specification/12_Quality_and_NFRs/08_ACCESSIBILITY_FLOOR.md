# Accessibility Floor

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester, human
**Last Updated:** 2026-06-06
**Cross-references:** 08_Cross_Cutting/08-D_color_palette_and_typography.md, 08_Cross_Cutting/08-L_ui_standardization.md, 00_Foundation/05_CONSTRAINTS.md

This document defines the accessibility floor for Ollama LLM Bench: the minimum, mandatory accessibility bar every release must meet. It is a floor, not an aspiration — the requirements below are non-negotiable and verifiable, and a build that fails one of them does not ship. The application is operated by mouse only (see 00_Foundation/05_CONSTRAINTS.md): there are no **custom** keyboard shortcuts, accelerators, or mnemonics, and no required keyboard-navigation paths; the toolkit's built-in modal defaults — Enter activates a dialog's default button, Esc triggers Cancel/Close — are permitted as incidental host-toolkit behaviour (D-R-07). The floor therefore covers purely visual and pointer-input properties — WCAG 2.1 AA colour contrast, a visible focus indicator when a control acquires focus, sufficient click-target size, colour-independent state encoding, accessible names on every interactive element, and respect for the operating system's reduced-motion and high-contrast preferences. The colour and contrast values the floor depends on are owned by 08_Cross_Cutting/08-D_color_palette_and_typography.md; this document owns the floor itself and how it is verified.

---

## Table of Contents

1. Floor principles
2. Colour contrast — WCAG 2.1 AA
3. Colour is never the sole channel
4. Mouse-only operation
5. Focus indication
6. Click-target size
7. Accessible names
8. Reduced motion and high contrast
9. Text scaling and resizing
10. Verification method
11. Accessibility floor summary

---

## 1. Floor principles

- **It is a minimum bar, not a target.** The application is not optimised for screen readers, is not internationalised, and provides no keyboard-shortcut layer; that scope is fixed in 00_Foundation/05_CONSTRAINTS.md. The floor is the set of accessibility properties that are mandatory regardless.
- **Every floor requirement is verifiable.** Each one has a defined check — a contrast ratio, a hit-area measurement, an inspector query — so a release can be objectively gated on it.
- **The floor is release-blocking.** A build that fails any floor requirement does not ship. Accessibility is not deferred to a later version.
- **The floor holds in both themes.** Every requirement is satisfied in both the Dark and the Light theme; neither theme is a partial implementation.

## 2. Colour contrast — WCAG 2.1 AA

The application meets at least **WCAG 2.1 AA** contrast in both themes:

- **Normal text** — a contrast ratio of at least **4.5 : 1** against its background.
- **Large text** — at least **3 : 1**, where large text is 18.66 px or larger at regular weight, or 14 px or larger at semibold weight.
- **Non-text UI components** — borders, focus rings, status dots, control outlines, and chart elements that convey information — at least **3 : 1** against the adjacent surface.

The full contrast matrix of foreground/background pairs, with the measured ratio for each pair in each theme, is in 08_Cross_Cutting/08-D_color_palette_and_typography.md §14. Every pair in that matrix meets or exceeds the floor.

Rule: a change to any colour token is not accepted until the contrast matrix has been re-verified with a contrast tool. A palette change that drops a pair below the floor is a release blocker.

## 3. Colour is never the sole channel

Every piece of information the interface communicates with colour is **also** communicated by a text label, a glyph, or both. The interface is fully usable by a colour-blind user and in greyscale.

| Information conveyed by colour | The non-colour channel that always accompanies it |
|---|---|
| Verdict PASS / FAIL | The literal text `PASS` or `FAIL` plus a verdict glyph |
| Per-provider health (Providers table / Provider Edit) | A status-dot state plus a per-provider text label (`Live`, `Zero models`, `Down`, `Not tested`, `Checking` — the `ProviderTestStatus` set) |
| Aggregate app readiness (status-bar health dot) | A status-dot state plus the aggregate text label (`Ready`, `Degraded`, `Not ready`, `Checking` — the `ReadinessState` set); distinct from the per-provider labels above |
| Validation result (hard error, soft warning, soft info) | A validation message in text plus a severity glyph |
| Run stage and run state | A text stage label in the Progress Widget |
| A pending (not-yet-completed) result | The text status of the row; pending is never shown as a third verdict colour with no label |

This is a hard rule: a UI surface may not rely on hue alone to distinguish two states. The verdict and health palettes in 08-D §5 and §6 are always paired with their text label and glyph.

## 4. Mouse-only operation

The application is operated by mouse — through buttons, widgets, toolbar controls, menu entries, and context-menu items. The floor explicitly does **not** mandate full keyboard operability, a tab-order spec, accelerators, or shortcut consistency; the constraint in 00_Foundation/05_CONSTRAINTS.md rules them out as a product decision.

**This is a deliberately reduced accessibility target, stated honestly (DD-52):** this floor
adopts WCAG 2.1 AA for **colour contrast only** and does not claim WCAG 2.1 conformance
overall. Excluding supported keyboard operability excludes keyboard-dependent assistive
workflows (motor-impaired operation, screen-reader-driven navigation) — a known, accepted
consequence of the product decision, not an oversight.

**The toolkit's free keyboard behaviour is never suppressed (DD-52).** Mirroring the
Enter/Esc modal-default precedent (D-R-07), Qt's built-in `Tab`/`Shift+Tab` focus traversal
is **permitted and never actively suppressed**: interactive controls are not given a
`NoFocus` policy, and no code disables the toolkit's default traversal. It remains an
*unsupported, untested* path — no curated tab order is specified and no release check
exercises it; the mouse is the only supported and verified input path.

What the floor does mandate for pointer input:

- **Every action is visible.** Every operation the user can perform is exposed as a button, menu item, toolbar control, or context-menu item that the user can find by looking at the screen. There are no hidden affordances that only a keyboard user could discover.
- **Click-target size.** See §6.
- **Visible focus on click.** When a user clicks into an input control, the control acquires focus and shows the focus ring — see §5. This is the only path by which focus is reached.
- **No keyboard prerequisites.** A workflow may not rely on the user pressing a key to complete it. Where text entry is needed, the user clicks the input first; the toolkit's native text-entry behaviour is honoured by typing into the focused field, but the workflow itself is initiated and concluded with mouse clicks.
- **Toolkit-default modal keys are permitted (D-R-07).** A modal dialog may honour the host toolkit's built-in Enter (activate the default button) and Esc (Cancel/Close) behaviour. These are not custom shortcuts, require no registration, and are never the *only* way to do anything — the same actions are always available as visible buttons, so a mouse-only user is never dependent on them. No **custom** shortcut, accelerator, or mnemonic (`QShortcut`, a `QAction` accelerator, an `&`-mnemonic) is registered anywhere in the application.

## 5. Focus indication

When a control acquires focus — which, given the mouse-only model, happens when a user clicks into it — it shows a **visible focus indicator**. The indicator is the `focus.ring` token defined in 08_Cross_Cutting/08-D_color_palette_and_typography.md §11: a 1 px outer line in the focus colour plus a 2 px inner glow of the primary colour at 40 % opacity.

Focus-indication rules:

- **The ring is never suppressed — for focus-retaining input controls (DD-52).** For controls that hold focus after a click — text inputs, text areas, dropdowns/combos, spinners, lists, tables — the ring is rendered for the focused control at all times: never hidden for visual cleanliness, and never hidden because focus arrived by mouse (the application does not distinguish "mouse focus" from any other focus). Momentary action controls (push buttons, toolbar buttons) take click-focus platform-dependently; the ring requirement and its release check do **not** apply to them.
- **The ring meets the contrast floor.** The focus ring achieves at least 3 : 1 contrast against the adjacent surface in both themes; this is verified in the 08-D §14 matrix (`border.focus` on `bg.window`).
- **Every focus-retaining control shows it.** Inputs, dropdowns, text areas, table cells, list items — every control that holds focus renders the ring when it does, so a user who clicked into a control can see where their typing or selection will land.

A control that can receive focus but shows no focus ring is a release-blocking defect.

## 6. Click-target size

Every clickable control offers a hit area of at least **24 x 24 logical pixels** at the application's default scale, so a user can reliably aim with a mouse or trackpad. Tightly packed controls — for example icon buttons in a toolbar row — meet the same hit-area minimum.

This requirement applies to: every button (primary, secondary, destructive, side action, icon button), every checkbox and toggle, every dropdown chevron, every table-row selection checkbox, every chip-remove glyph, every title-bar close (X) glyph, and every menu item. Chart elements (bars, points, lines) that are independently clickable for drill-down also meet the minimum, by either intrinsic size or an enlarged invisible hit region.

A control that ships with a hit area below the minimum is a release-blocking defect.

## 7. Accessible names

Every interactive element exposes an **accessible name** — a programmatically queryable name — through the Qt accessibility interface, so an assistive technology can announce what the element is, and the application's own UI tests can address it by name.

| Element kind | Accessible name source |
|---|---|
| A button or menu item with a text label | Its visible text |
| An icon-only button (no visible text) | An explicitly set accessible name describing the action, for example "Detach chart" or "Open exports folder" |
| An input field | Its associated field label |
| A table | An accessible name describing the table's content; columns expose their header text |
| A status dot | An accessible name stating the health state in words |
| A tab in a tab strip | The tab's visible label |
| A dialog | An accessible name equal to its title |

Rule: an icon-only control must never ship with an empty or generic accessible name. An icon-only button with no accessible name is unidentifiable to assistive technology and is a release-blocking defect. Deeper screen-reader optimisation is out of scope per 00_Foundation/05_CONSTRAINTS.md, but a queryable name on every interactive element is not optional.

### 7.1 Test hook — stable objectName (D-R-07, MISS-30)

Separately from the accessible name, **every interactive control carries a stable, hand-authored Qt `objectName`** (for example `start_button`, `pause_button`, `run_selector`). The objectName is the **test handle**: the application's `pytest-qt` UI tests locate and drive controls by it (`widget.findChild(QPushButton, "start_button")`), simulating clicks and input. objectNames are author-assigned and stable across releases, and are **independent of the user-visible accessible name** — so renaming a label never breaks a test, and the test handle is never an auto-generated value. An architecture/AST test asserts that every interactive control sets a non-empty objectName. (The accessible name is the user-facing/assistive label; the objectName is the test id — the two serve different purposes and are both mandatory.)

### 7.2 Icon-only and ambiguous-control registry (canonical names)

The controls below have no visible text label (icon-only) or an otherwise ambiguous label, so their accessible name, test `objectName`, and hover tooltip are **pinned here** rather than left to the implementer. Implementers MUST use these exact values; the mockups' `title=` attributes carry the same tooltip text. Repeated controls (the rename pencil, the dialog close button) share one `objectName` pattern across every screen they appear on; per-field controls suffix the `objectName` with the field key.

| Screen | Control (glyph) | objectName | Accessible name | Tooltip (`title=`) |
|---|---|---|---|---|
| Main Window | Settings menu (gear) | `settings_menu_button` | "Settings" | Open the Settings dialog |
| Main Window | About menu (info) | `about_menu_button` | "About" | Application information: version, links, data folders |
| Main Window | Benchmark workspace tab | `workspace_benchmark_button` | "Benchmark workspace" | Benchmark workspace |
| Main Window | Task Editor workspace tab | `workspace_task_editor_button` | "Task Editor workspace" | Task Editor workspace |
| Main Window | Running pill | `running_pill_button` | "Run in progress — open Progress" | Switch to the Benchmark workspace and focus the Progress widget |
| Main Window | Provider-readiness indicator (dot) | `provider_readiness_indicator` | "Provider readiness status" | Provider readiness — click to open Settings / Providers |
| All widgets | Rename-run pencil (✎) | `rename_run_button` | "Rename run" | Rename run |
| All dialogs | Dialog close (✕) | `dialog_close_button` | "Close dialog" | Close |
| New Benchmark | Judge model refresh (↻) | `judge_model_refresh_button` | "Refresh judge model list" | Refresh the judge provider's model list |
| Result · Charts | Previous chart (◀) | `chart_prev_button` | "Previous chart" | Previous chart |
| Result · Charts | Next chart (▶) | `chart_next_button` | "Next chart" | Next chart |
| Result · Charts | Detach chart | `detach_chart_button` | "Detach chart" | Open the chart in its own window |
| About dialog | Open data folder | `open_data_folder_button` | "Open application data folder" | Open the application data folder |
| About dialog | Copy data-folder path | `copy_data_folder_path_button` | "Copy application data folder path" | Copy the application data folder path |
| Settings / dialogs | Gate-busy indicator (spinner) | `gate_busy_indicator` | "Inference in flight — controls temporarily disabled" | An inference is in flight; please wait. |
| Task Editor | Field-help icon (ⓘ) | `<field_key>_help_button` | "Help: \<field label\>" | About this field |
| Task Editor | Validation-summary pill | `validation_summary_button` | "Validation summary — focus first issue" | Click to focus the first task with a warning |

Rule restatement for the registry: the **tooltip** (`title=` / `QWidget.setToolTip`) is a pointer-hover affordance and MAY repeat the accessible name; the **accessible name** (`setAccessibleName`) is mandatory and queryable; the **objectName** is the stable test handle and is never shown to the user. All three are set for every row above. New icon-only controls added later MUST be appended to this registry in the same change that introduces them.

## 8. Reduced motion and high contrast

The application reads and respects two operating-system accessibility preferences through the OS adapter.

- **Reduced motion.** When the operating system reports a reduced-motion preference, every transition and the health-dot pulse animation are disabled; state changes apply instantly. No animation is essential to understanding a state — the application is fully usable with all motion off. The motion cap itself (no animation exceeds 200 ms) is in 08-D §12. No flicker or strobe is rendered at any rate; the application never emits content that could trigger photosensitive responses.
- **High contrast.** When the operating system reports a high-contrast preference, the theme module increases border-width emphasis and replaces the soft `*.fill` callout backgrounds with solid borders, so every component boundary stays distinct without relying on a subtle fill.

Both preferences are read at launch and re-applied live if the operating system preference changes while the application is running; neither requires a restart.

## 9. Text scaling and resizing

- The application honours the operating system's display-scaling setting: at a higher OS scale, the entire interface — text, controls, spacing — scales up, because all sizes derive from the design tokens in 08-D rather than from fixed pixel literals.
- A display-scale change while a run is in progress re-renders the UI at the new scale without interrupting the run (see EC-PLAT-2 in 08_Cross_Cutting/08-I_edge_cases.md).
- The main window and dialogs remain usable when resized: layouts reflow, scroll regions appear where content exceeds the available space, and no control becomes unreachable or clipped beyond a scrollable area.

The application does not provide an in-app font-size control independent of the operating-system scale; OS-level scaling is the supported mechanism, and it is honoured fully.

## 10. Verification method

Each floor requirement has a defined verification, so a release can be gated on it.

| Requirement | Verification |
|---|---|
| WCAG AA contrast, both themes | The 08-D §14 contrast matrix is re-checked with a contrast tool after any token change; every pair meets its stated minimum |
| Colour is never the sole channel | A manual greyscale review of every status-bearing surface confirms a text label or glyph accompanies the colour; covered by UI tests asserting the label text is present |
| Mouse-only operation | A traversal review confirms every workflow can be completed using a pointing device alone; an automated grep over the source asserts no **custom** shortcut, accelerator, or mnemonic is registered (`QShortcut`, `QAction` accelerators/mnemonics, `&`-mnemonics). The toolkit's built-in modal Enter/Esc defaults are exempt (D-R-07). |
| Stable test objectName | An architecture test asserts every interactive control sets a non-empty, author-assigned `objectName` (D-R-07, MISS-30) |
| Focus indication on click | An automated test asserts each **focus-retaining input control** (text inputs, combos, spinners, lists, tables — not momentary buttons, DD-52) reports a focus state and renders the ring after a click; a manual pass confirms no such control hides it |
| Click-target size | An automated test queries the bounding rect of every interactive control and asserts the minimum hit area; a manual pass spot-checks toolbars and tightly packed rows |
| Accessible names | An automated test walks the widget tree and asserts every interactive element, especially every icon-only button, has a non-empty accessible name |
| Reduced motion respected | A test sets the reduced-motion preference and asserts transitions and the health-dot pulse are disabled |
| High contrast respected | A test sets the high-contrast preference and asserts border emphasis increases and soft fills are replaced |
| Text scaling | A manual review at an elevated OS display scale confirms the interface scales and stays usable |

## 11. Accessibility floor summary

| Floor requirement | Minimum bar | Enforcement |
|---|---|---|
| Text contrast | WCAG 2.1 AA — 4.5 : 1 normal, 3 : 1 large, both themes | Blocks release |
| Component contrast | 3 : 1 for borders, focus rings, status dots, both themes | Blocks release |
| Colour never sole channel | Every colour-coded state also has a text label or glyph | Blocks release |
| Mouse-only operation | Every action is reachable as a button, menu entry, toolbar control, or context-menu item; no workflow depends on a key press | Blocks release |
| Focus indicator | Visible on every focusable control when it gains focus; meets 3 : 1 | Blocks release |
| Click-target size | Every clickable control has at least a 24 x 24 px hit area | Blocks release |
| Accessible names | Every interactive element, including every icon-only button, has a non-empty accessible name | Blocks release |
| Reduced motion | OS preference respected; all motion disablable; no flicker or strobe at any rate | Blocks release |
| High contrast | OS preference respected; borders strengthened, soft fills replaced | Blocks release |
| Text / display scaling | OS display scale honoured; UI scales and stays usable | Blocks release |
