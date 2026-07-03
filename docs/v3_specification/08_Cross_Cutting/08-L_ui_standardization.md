# UI Standardization

**Status:** Draft
**Owner:** architect
**Audience:** arch, coder, tester, human
**Last Updated:** 2026-06-06
**Cross-references:** 08_Cross_Cutting/08-D_color_palette_and_typography.md; 00_Foundation/02_GLOSSARY.md; 01_Main_Window; 06_Settings_Dialog; 07_Common_Dialogs; 09_Task_Editor; 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md

This document collects the non-negotiable visual and interaction patterns that every screen, dialog, and widget of Ollama LLM Bench must follow. It exists to keep the interface consistent: anything that is UI-shaped — a menu bar, a dialog footer, a verdict colour, a button order, a form field — has its single canonical form defined here. Where any other specification document, HTML mockup, or implementation appears to conflict with this document, **this document wins**, and the conflicting surface must be corrected to match it. The application is built with programmatic Qt Widgets; this document defines rules and patterns, not pixel-perfect mockups (UI mockups live in the individual widget folders as HTML files).

---

## Table of Contents

1. [No Placeholder UI — Hard Rule](#1-no-placeholder-ui--hard-rule)
2. [Window Chrome](#2-window-chrome)
3. [Workspace Context Strip](#3-workspace-context-strip)
4. [Status Bar](#4-status-bar)
5. [Dialog Button Ordering](#5-dialog-button-ordering)
6. [Button Styles](#6-button-styles)
7. [Form Layout](#7-form-layout)
8. [Verdict and Status Colours](#8-verdict-and-status-colours)
9. [Iconography](#9-iconography)
10. [Tooltips](#10-tooltips)
11. [Theme Handling](#11-theme-handling)
12. [Responsive Behaviour](#12-responsive-behaviour)
13. [Accessibility Floor](#13-accessibility-floor)
14. [Standardization Review Checklist](#14-standardization-review-checklist)

---

## 1. No Placeholder UI — Hard Rule

The interface must not contain inactive, stub, dead, or placeholder elements. Every visible control is either functional in the current application state or is **hidden** until it becomes applicable.

- **A control that does not apply to the current state is removed from the layout — not shown greyed out.** The canonical example: the Benchmark workspace's left configuration panel is hidden entirely while a benchmark run is active, not disabled in place. When a control's applicability changes, it appears or disappears; the surrounding layout reflows.
- **Legitimate transient disabling is still permitted.** A control that is momentarily not actionable but *will* become actionable shortly may be shown disabled, and must carry a tooltip explaining why (see §11). The clearest examples: a dialog's Save button while a form is invalid, or the Settings action in the menu bar while a benchmark run is in a non-terminal stage. The rule forbids *permanent* stubs and *dead* placeholders — it does not forbid honest, short-lived disabled states tied to a condition the user can resolve.
- **No "coming soon" tiles, no empty tabs that do nothing, no buttons wired to nothing.** Every tab has content; every button has behaviour.
- **Empty states are content, not placeholders.** A region with no data yet (for example a Results tab before any run exists) shows a deliberate, designed empty state with explanatory text — it is not a blank or stubbed area.

The distinction in one line: **hide what does not apply; disable (with a reason) what is about to apply; never ship a control wired to nothing.**

## 2. Window Chrome

### 2.1 Built-in menu bar — cross-platform contract

The Main Window uses a **built-in, in-window menu bar** on every platform, including macOS where a global menu bar is available natively.

- On macOS the implementation opts out of the global menu bar (or duplicates the menu inside the window) so the menu is always visible at the top of the application window.
- On Windows and Linux the in-window menu bar is the default and requires no special handling.

Rationale: every user sees the same control surface in the same place; help text and screenshots refer to "the menu bar at the top of the application window" unambiguously across operating systems.

### 2.2 Menu bar layout — canonical

The menu bar is **minimal**. It has **no File, Edit, View, or Help dropdown menus**. It contains exactly the items below, in this left-to-right order:

```
+----------------------------------------------------------------------------+
|  Settings   About      [ Benchmark | Task Editor ]    Running...      v1.0  |
+----------------------------------------------------------------------------+
|  <-- actions -->        <--- workspace switcher --->   <----- status ---->  |
```

1. **Settings action** — a single clickable item that opens the Settings dialog. Disabled (with a tooltip) while a benchmark run is in a non-terminal stage.
2. **About action** — a single clickable item that opens the Application Information (About) dialog.
3. **Workspace switcher** — a segmented control with two segments, `Benchmark` and `Task Editor`. Always visible. Switches the active workspace.
4. **Running pill** — appears *only* while at least one benchmark run is in a non-terminal stage. Clickable: it switches to the Benchmark workspace and focuses the Progress widget. It is absent (not greyed out) when no run is active — consistent with §1.
5. **Right cluster** — the application version string. No clickable affordances by default.

Operations that a conventional File/Edit/View/Help menu would hold instead live at their functional home: Task Editor file and task operations on the Task Editor toolbar; folder-open actions inside the About dialog; workspace switching on the segmented control; application quit on the window close control.

Menu bar metrics: height 32 px; background `bg.surface`; 1 px bottom border in `border.default` (token roles defined in 08-D).

## 3. Workspace Context Strip

A specification or mockup that shows a single widget in isolation (rather than the whole Main Window) must display a slim **workspace context strip** at the top, identifying which workspace and region the widget belongs to. This prevents a single-widget surface from being mistaken for a complete window.

```
[ Benchmark workspace > Left panel > New Benchmark ]      <- context strip
```

Context-strip metrics: height 22 px; background `bg.context-strip`; italic text in `muted.base`. The context strip is informational only — it contains no controls.

## 4. Status Bar

The status bar at the bottom of the Main Window is **always present**. It has three regions:

```
+----------------------------------------------------------------------------+
|  * <health or editor status>      <toast / transient message>       v1.0.0  |
+----------------------------------------------------------------------------+
|  <-- left: status dot + label -->  <-- centre: toasts -->   <-- right: ver --|
```

- **Left region** — a status dot plus a short label. In the Benchmark workspace it reflects provider/embedding health (colours per §8 and the health palette in 08-D §6). In the Task Editor workspace it reflects editor status (for example clean vs unsaved changes).
- **Centre region** — the transient toast / message area. Toast messages auto-dismiss; this region is empty in steady state.
- **Right region** — the application version string.

Status-bar metrics: height 22 px; background `bg.surface`.

## 5. Dialog Button Ordering

### 5.1 The single ordering rule

**The right-most button is the primary / default action.** Lower-priority actions sit to its left. The escape / back-out action (Cancel, Discard, Close, Back) sits **immediately to the left of the primary confirm**.

Two-button dialog:

```
                                          [ Cancel ]  [ Confirm ]
                                                       ^ primary, right-most
```

Three-button dialog with one back-out and two confirms:

```
                          [ Cancel ]  [ Save Draft ]  [ Save & Publish ]
                                                        ^ default, right-most
```

Destructive prompt — the destructive action is primary and uses the destructive style (see §6):

```
                                          [ Cancel ]  [ Delete ]
                                                       ^ destructive primary
```

### 5.2 Multi-action dialog footers

When a dialog has **side actions** — actions that do not fit the cancel/confirm pattern, such as Reset, Import, Export — split the footer into two clusters:

```
+----------------------------------------------------------------------------+
| [Reset to Defaults] [Import...] [Export...]          [Close]  [Save Changes]|
+----------------------------------------------------------------------------+
|  <------- side-action cluster ------->        <-- back-out --> <-- primary --|
```

- **Left cluster** — side actions only. Never place Cancel/Close here.
- **Right cluster** — the back-out action (Cancel/Close) on the left of the cluster, the primary action on the right of the cluster, following §5.1.

The Settings dialog uses this two-cluster footer.

### 5.3 Standardized footers for current dialogs

| Dialog | Left cluster (side actions) | Right cluster (back-out, then primary) |
|---|---|---|
| Settings | Reset to Defaults / Import... / Export... | Close / Save Changes |
| Provider Edit | Test connection | Cancel / Save |
| Environment-variable conversion | — | Cancel / Apply |
| Reset confirmation | — | Cancel / Reset (destructive) |
| Settings import preview | — | Cancel / Replace Settings |
| Discard-changes confirmation | — | Cancel / Discard (destructive) |
| Rename Run | — | Cancel / Rename |
| Run Summary (pre-start review) | — | Back / Start Benchmark |
| Resume Summary | — | Cancel / Resume Run |
| Retry Selection | — | Cancel / Retry Selected |
| Error dialog | — | Copy Details / Close (Close is primary) |
| About dialog | — | Close (the Copy-path / Open-folder actions are row-level icon buttons on the data-folder row, §10 — not footer buttons) |
| Task Editor — unsaved-changes prompt | — | Cancel / Discard All / Save All |

## 6. Button Styles

Every button uses one of the styles below. Colour token roles are defined in 08-D. Every button is activated by clicking it; there are no **custom** keyboard shortcuts, accelerators, or mnemonics. (A modal dialog's default/cancel buttons may still respond to the toolkit's built-in Enter/Esc — D-R-07.)

| Role | Style |
|---|---|
| Primary confirm | Filled — `primary.base` fill, `text.on-primary` label |
| Destructive primary | Filled — `error.base` fill, `text.on-error` label |
| Secondary confirm | Outlined — `border.default` outline, `text.primary` label |
| Cancel / Discard / Close / Back (beside a primary confirm) | Outlined muted — `border.default` outline, `muted.base` label |
| Side action | Outlined muted — same as Cancel style |
| Icon button | 28x28 px, transparent fill and border, `muted.base` glyph; on hover `bg.raised` fill, `border.default` outline, `text.primary` glyph |

Rules:

- A destructive primary always uses the destructive style so a dangerous action is visually distinct from an ordinary confirm.
- **Close as primary.** When **Close is the footer's only or right-most action** (no separate confirm beside it), it is the primary/default action (§5.1) and takes the **Primary confirm** style (filled) — as in the Error dialog (recoverable / action-available patterns) and the About dialog. The outlined-muted Close style applies only when Close is a back-out action sitting to the left of a distinct primary confirm (for example Settings' `[Close] [Save Changes]`).
- An icon-only button is never shipped without a hover tooltip (see §9 and §10).

## 7. Form Layout

### 7.1 Field-row anatomy

Every input in a form is presented as a **field row** with this fixed vertical structure:

```
+--------------------------------------------------------------+
| Label  (required marker or "(optional)" if applicable)   (i)  |
| Format hint (muted, font.size.xs)                             |
| +----------------------------------------------------------+ |
| | Input control                                            | |
| +----------------------------------------------------------+ |
| Validation strip:  valid  |  warning  |  error                |
+--------------------------------------------------------------+
```

- **Label** — the field name, with a required/optional marker per §7.3, and an optional info icon `(i)` opening a help popover.
- **Format hint** — a short muted hint at `font.size.xs` describing the expected format. Always present in the layout; may be empty for self-explanatory fields.
- **Input control** — the editable control.
- **Validation strip** — a single line below the input that shows the current validation state with glyph and text (see §8 and §9). It occupies layout space even when empty, so the row height does not jump when validation appears.

Spacing within and between rows uses the spacing tokens from 08-D: `space.sm` between label and input, `space.xs` between input and validation strip, `space.lg` between consecutive field rows.

### 7.2 Section layout

Field rows are grouped into **sections** (group boxes). A section has:

- A title in uppercase, `muted.base`, `font.size.xs`, with slightly increased letter spacing.
- An optional one-line muted helper text below the title.
- A vertical stack of field rows.
- Optional section-level action button(s) aligned to the right edge of the title row.

Sections are padded `space.lg` inside, with a `space.lg` gap to the next section.

### 7.3 Required vs optional markers

| Marker | Meaning |
|---|---|
| Red `*` immediately after the label | Required field. |
| `(optional)` after the label, in `muted.base` | Optional field, used when the surrounding layout would otherwise imply the field is required. |
| No marker | Optional field where the absence of a marker is unambiguous. |

A form uses one consistent convention throughout: either every required field is starred, or every optional field is marked `(optional)` — never a mix that leaves a field's status ambiguous.

## 8. Verdict and Status Colours

Wherever a verdict, status, health state, or validation result is rendered, it uses the semantic role below. Concrete colour values for both themes are defined in 08-D §3–§6.

| Semantic meaning | Token role | Example surfaces |
|---|---|---|
| Pass / ready / valid | `success.base` | Verdict PASS, healthy provider dot, valid validation strip |
| Warning / degraded / soft issue | `warning.base` | Unsaved-changes marker, degraded readiness, soft validation warning, retryable failed-state result |
| Fail / not-ready / hard error | `error.base` | Verdict FAIL, down provider dot, hard validation error, destructive action |
| Unknown / pending / neutral | `muted.base` | Result not yet completed, untested provider, neutral state |
| Informational | `info.base` | Informational tags, in-pane informational callouts |
| Primary / active / selected | `primary.base` | Active tab underline, primary button fill, selected table row |

The final benchmark verdict is **binary — PASS or FAIL**. A result that has not finished evaluation has *no verdict*; it is rendered as pending with `muted.base` and a "pending" label. Pending is a transient display state, never presented as a verdict value. Per-task failure states (a retryable failed inference, provider failure, timeout, or error) render with `warning.base` and an explicit failure label — they are failures of the attempt, not a FAIL verdict.

## 9. Iconography

The application uses a small, fixed glyph set with consistent meaning:

| Glyph | Meaning |
|---|---|
| check mark | Success / valid |
| cross mark | Failure / error / blocked |
| warning triangle | Warning / soft issue |
| info circle | Information / help popover |
| circular arrow | Reset / refresh / reload |
| lightning bolt | Test connection / health probe |
| pencil | Edit / rename |
| trash can | Delete |
| open folder | Open folder |
| document | File |
| overlapping squares | Duplicate |
| clipboard | Copy to clipboard |
| plus | Add |
| chevron down / right | Expand / collapse |
| triangle left / right | Previous / next |
| filled / hollow circle | Active / inactive segment |

Rules:

- Every icon-bearing control has a hover tooltip stating the action (see §10). No glyph-only control ships without one.
- A glyph that conveys status (check, cross, warning, info) is always paired with a text label where the status is decision-relevant — colour and glyph alone are never the sole channel (see §13).
- Icons whose tint derives from theme text/muted roles are re-rendered on a theme change (see 08-D §13).

## 10. Tooltips

- A tooltip appears after a 600 ms hover and hides when the pointer leaves the control.
- Tooltip text includes an action verb where the control performs an action ("Test connection", not "Test").
- **A disabled control must show a tooltip explaining why it is disabled** — for example, "Disabled while a benchmark run is in progress." This is mandatory: a transiently disabled control without an explanatory tooltip is a defect (see §1).
- Tooltips are plain text, short, and do not repeat the visible label verbatim; they add information.

## 11. Theme Handling

The application supports three themes: **System** (auto-detect), **Dark**, and **Light**, controlled by the setting `ui.theme` with default `system`.

- On launch, when `ui.theme` is `system`, the OS adapter reads the operating system's colour-scheme preference and the matching theme is applied.
- When `ui.theme` is `system`, the application also tracks live OS colour-scheme changes and re-applies the theme without restarting.
- A runtime theme change re-applies all tokens and repaints every surface without an application restart and without discarding unsaved input.
- All colour, font, spacing, radius, and border values come from the design tokens in 08-D. Both Dark and Light themes must satisfy the WCAG AA contrast matrix in 08-D §14.
- Styling is generated and applied exclusively by the theme module; `setStyleSheet()` is forbidden elsewhere (see 08-D §1 and §16).

## 12. Responsive Behaviour

- **Main Window size.** Minimum 1280 x 720; default 1440 x 900. The window is resizable above the minimum.
- **Splitters.** Each splitter child has a defined minimum width or height; collapse-to-zero is disabled, so no panel can be dragged out of existence.
- **Modal dialogs.** Modal dialogs are not resizable unless a specific dialog's own specification states otherwise.
- **Text overflow.** Labels and table cells that cannot fit their text truncate with an ellipsis and expose the full text in a hover tooltip.
- **Reflow on state change.** When a control is hidden or shown per §1, the surrounding layout reflows cleanly with no leftover gap.

## 13. Accessibility Floor

This is the minimum accessibility bar; it is mandatory, not aspirational. The numeric floor and its verification method are owned by 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md.

- **Mouse-only operation.** The application is operated entirely by mouse — buttons, widgets, toolbar controls, and menu entries. There are no **custom** keyboard shortcuts, accelerators, F-keys, mnemonics, or required keyboard-navigation paths; dialogs can always be dismissed by clicking the close (X) or the cancel button. The host toolkit's built-in modal defaults — Enter activating a dialog's default button and Esc triggering Cancel/Close — are permitted as incidental behaviour (D-R-07) and are never the only way to perform an action; likewise any incidental focus behaviour when a user clicks into an input is honoured visually (see "Visible focus" below) but never relied on as the primary means of operation.
- **Contrast.** Every text-on-background and component-on-background pairing meets at least WCAG 2.1 AA in *both* themes (4.5:1 normal text, 3:1 large text and UI components). The contrast matrix is in 08-D §14.
- **Visible focus.** When a user clicks into an input the control acquires focus and shows the focus ring (08-D §11); the focus indicator is never suppressed, including for mouse users.
- **Click-target size.** Every clickable control offers a hit area of at least 24 x 24 px so the user can reliably aim with a mouse or trackpad.
- **Accessible names.** Every interactive control has an accessible name and a tooltip, so assistive technology and hover both identify it.
- **Colour is never the only channel.** Every state conveyed by colour — verdict, health, validation, run stage — is also conveyed by a text label and/or glyph, so the interface is usable for colour-blind users and in greyscale.
- **Reduced motion.** When the OS reports a reduced-motion preference, all animation is disabled and state changes apply instantly (see 08-D §12).

## 14. Standardization Review Checklist

Apply this checklist when reviewing any new or changed UI surface, mockup, or widget specification:

- [ ] No placeholder, stub, or dead control; non-applicable controls are hidden, not greyed out (§1).
- [ ] Any disabled control is genuinely transient and carries a tooltip explaining why (§1, §11).
- [ ] Main-window-scope surfaces show the minimal built-in menu bar; single-widget surfaces show the workspace context strip (§2, §3).
- [ ] The menu bar has no File/Edit/View/Help menus — only Settings, About, the workspace switcher, the running pill, and the version string (§2).
- [ ] The running pill is present only while a run is in a non-terminal stage (§1, §2).
- [ ] The status bar is present with the version string on the right (§4).
- [ ] Dialog footers follow §5 ordering: side actions left, back-out then primary on the right; the primary is right-most.
- [ ] The primary button uses the `primary.base` filled style; a destructive primary uses the `error.base` destructive style (§6).
- [ ] Every field row has a label with the correct required/optional marker, a format-hint line, and a validation strip (§7).
- [ ] No glyph-only control without a hover tooltip; every control has an accessible name (§9, §10, §13).
- [ ] All colours, fonts, spacing, radii, and borders use design-token roles from 08-D — no literals.
- [ ] Every state shown by colour is also shown by text and/or glyph (§8, §13).
- [ ] The surface renders correctly and meets WCAG AA contrast in both Dark and Light themes (§11, §13).
