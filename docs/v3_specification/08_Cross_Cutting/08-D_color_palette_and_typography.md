# Color Palette and Typography

**Status:** Draft
**Owner:** architect
**Audience:** arch, coder, tester
**Last Updated:** 2026-05-22
**Cross-references:** 08_Cross_Cutting/08-L_ui_standardization.md; 00_Foundation/02_GLOSSARY.md; 10_Domain_and_Data/01_DOMAIN_MODEL.md; 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md; 16_Engineering_Standards

This document defines the design-token system for Ollama LLM Bench: every colour, font, size, spacing, radius, and border value the user interface is permitted to use. The application is built with programmatic Qt Widgets (no QML and no `.qss` stylesheet files on disk). Tokens are typed Python objects held in a single theme module; that module is the only place styling is generated and applied. Every widget, dialog, chart, and custom-painted surface resolves its appearance from these tokens by role name. No widget ever embeds a literal colour, and no code outside the theme module ever calls `setStyleSheet()`. This document specifies the full Dark and Light token sets, the verdict and health palettes, the theme-switching contract, and the WCAG AA contrast matrix that both themes must satisfy.

---

## Table of Contents

1. [Token System and Non-Negotiable Rules](#1-token-system-and-non-negotiable-rules)
2. [Token Naming Convention](#2-token-naming-convention)
3. [Dark Theme Colour Tokens](#3-dark-theme-colour-tokens)
4. [Light Theme Colour Tokens](#4-light-theme-colour-tokens)
5. [Verdict Palette](#5-verdict-palette)
6. [Health Palette](#6-health-palette)
7. [Font Chains](#7-font-chains)
8. [Font-Size Tokens](#8-font-size-tokens)
9. [Spacing Tokens](#9-spacing-tokens)
10. [Radius Tokens](#10-radius-tokens)
11. [Border and Focus Tokens](#11-border-and-focus-tokens)
12. [Shadow and Motion Tokens](#12-shadow-and-motion-tokens)
13. [Theme Switching](#13-theme-switching)
14. [WCAG AA Contrast Matrix](#14-wcag-aa-contrast-matrix)
15. [Accessibility Rules](#15-accessibility-rules)
16. [The Theme Module Contract](#16-the-theme-module-contract)

---

## 1. Token System and Non-Negotiable Rules

Apply these rules without exception:

- **Tokens are typed Python objects.** Define them as immutable `msgspec.Struct(frozen=True, kw_only=True)` token containers (or equivalent frozen dataclasses) — one container per theme. There are no `.qss` files anywhere in the source tree.
- **One theme module owns all styling.** A single module (`src/ollama_llm_bench/ui/theme/`) holds the token containers, builds the Qt stylesheet strings and `QPalette` objects from them, and applies styling to the `QApplication`. No other module imports the raw token containers for direct stylesheet construction.
- **`setStyleSheet()` is forbidden outside the theme module.** The architecture-enforcement stack (import-linter + a `pytest-archon` rule) must fail the build if any module outside `src/ollama_llm_bench/ui/theme/` references `setStyleSheet`. Widgets receive their appearance because the theme module applies an application-level stylesheet and palette; per-widget styling is achieved through Qt dynamic properties (for example `role="primary-button"`) that the application stylesheet targets.
- **Widgets reference roles, never literals.** A widget that needs a colour names the role (for example "surface layer 2", "primary", "error"). The theme module resolves the role to a concrete value for the active theme.
- **Both themes are mandatory.** The Dark and Light token sets in §3 and §4 are both complete and both must be implemented. Neither is a partial or "best effort" theme.
- **Custom-painted surfaces use the same tokens.** Charts, status dots, badges, and any `QPainter`-based widget read their colours from the active theme's token container — they never hold their own palette.

## 2. Token Naming Convention

Every colour token is a **role name**, not a hex value. A role describes *what the colour is for*, so the same widget code produces a correct result in either theme. Tokens are grouped into families:

| Family | Prefix | Purpose |
|---|---|---|
| Background layers | `bg.*` | Stacked surface elevations, from the window backdrop to the most-raised surface |
| Borders | `border.*` | Separators, outlines, focus rings |
| Text | `text.*` | Foreground text at each emphasis level |
| Primary (brand) | `primary.*` | The brand teal and its interaction states |
| Semantic | `success.*`, `warning.*`, `error.*`, `info.*` | Status colours and their soft fill backgrounds |
| Muted / neutral | `muted.*` | Unknown, untested, neutral, disabled-adjacent states |
| Effect | `shadow`, `overlay` | Drop shadows and modal scrims |

The theme module exposes one accessor per token (for example `theme.color("bg.surface")` or an attribute `theme.colors.bg_surface`). The naming in the tables below is the canonical role identifier; the exact attribute spelling is an implementation detail of the theme module, but the role identity and its resolved value are binding.

## 3. Dark Theme Colour Tokens

The Dark theme is the default appearance when the OS reports a dark colour scheme.

| Token role | Value | Used for |
|---|---|---|
| `bg.window` | `#0a0f1a` | Application outer background; main-window backdrop |
| `bg.surface` | `#111827` | Panel surface; status bar; menu bar; input fill |
| `bg.raised` | `#1f2937` | Group-box surface; card surface; hover surface |
| `bg.selected` | `#263044` | Selected table row; active hover; segmented-control active segment |
| `bg.input` | `#1f2937` | Text-input, dropdown, and spin-box field background |
| `bg.context-strip` | `#1f2937` | Workspace context strip background (see 08-L §1.3) |
| `border.default` | `#374151` | Default 1 px border on panels, inputs, tables |
| `border.strong` | `#4b5563` | Pressed-state and hover-state border emphasis |
| `border.focus` | `#14b8a6` | Focus ring shown when a control gains focus (equals `primary.base`) |
| `text.primary` | `#f9fafb` | Primary body text, input text, headings |
| `text.secondary` | `#9ca3af` | Helper text, field labels, secondary table cells |
| `text.disabled` | `#4b5563` | Disabled-control text |
| `text.on-primary` | `#ffffff` | Text on a `primary.base` fill (primary button label) |
| `text.on-error` | `#ffffff` | Text on an `error.base` fill (destructive button label) |
| `primary.base` | `#14b8a6` | Brand teal; primary button fill; active tab underline; selected accents |
| `primary.hover` | `#2dd4bf` | Primary button hover fill |
| `primary.pressed` | `#0d9488` | Primary button pressed fill |
| `primary.disabled` | `#2d5a54` | Primary button disabled fill |
| `success.base` | `#34d399` | Pass verdict; healthy provider; valid validation state |
| `success.fill` | `rgba(52, 211, 153, 0.18)` | Pass badge / success callout background |
| `warning.base` | `#fbbf24` | Soft validation warning; degraded readiness; dirty-buffer marker |
| `warning.fill` | `rgba(251, 191, 36, 0.18)` | Warning badge / callout background |
| `error.base` | `#f87171` | Fail verdict; hard validation error; destructive action |
| `error.fill` | `rgba(248, 113, 113, 0.18)` | Error badge / callout background |
| `info.base` | `#60a5fa` | Informational tags; in-pane informational callouts |
| `info.fill` | `rgba(96, 165, 250, 0.18)` | Info badge / callout background |
| `muted.base` | `#9ca3af` | Unknown / untested / pending / neutral state |
| `muted.fill` | `rgba(156, 163, 175, 0.16)` | Neutral badge / callout background |
| `shadow` | `rgba(0, 0, 0, 0.65)` | Modal-dialog and popover drop shadow |
| `overlay` | `rgba(0, 0, 0, 0.55)` | Modal scrim behind a dialog |

## 4. Light Theme Colour Tokens

The Light theme is the appearance when the OS reports a light colour scheme. Values are tuned independently — they are not algorithmic inversions of the Dark theme — so that every contrast pair in §14 still meets WCAG AA.

| Token role | Value | Used for |
|---|---|---|
| `bg.window` | `#ffffff` | Application outer background; main-window backdrop |
| `bg.surface` | `#f3f4f6` | Panel surface; status bar; menu bar; input fill |
| `bg.raised` | `#e5e7eb` | Group-box surface; card surface; hover surface |
| `bg.selected` | `#d1d5db` | Selected table row; active hover; segmented-control active segment |
| `bg.input` | `#ffffff` | Text-input, dropdown, and spin-box field background |
| `bg.context-strip` | `#e5e7eb` | Workspace context strip background (see 08-L §1.3) |
| `border.default` | `#d1d5db` | Default 1 px border on panels, inputs, tables |
| `border.strong` | `#9ca3af` | Pressed-state and hover-state border emphasis |
| `border.focus` | `#0d9488` | Focus ring shown when a control gains focus (equals `primary.base`) |
| `text.primary` | `#111827` | Primary body text, input text, headings |
| `text.secondary` | `#4b5563` | Helper text, field labels, secondary table cells |
| `text.disabled` | `#9ca3af` | Disabled-control text |
| `text.on-primary` | `#ffffff` | Text on a `primary.base` fill (primary button label) |
| `text.on-error` | `#ffffff` | Text on an `error.base` fill (destructive button label) |
| `primary.base` | `#0d9488` | Brand teal, deepened for white-background contrast; primary button fill |
| `primary.hover` | `#0f766e` | Primary button hover fill |
| `primary.pressed` | `#115e59` | Primary button pressed fill |
| `primary.disabled` | `#99f6e4` | Primary button disabled fill |
| `success.base` | `#047857` | Pass verdict; healthy provider; valid validation state |
| `success.fill` | `rgba(4, 120, 87, 0.12)` | Pass badge / success callout background |
| `warning.base` | `#b45309` | Soft validation warning; degraded readiness; dirty-buffer marker |
| `warning.fill` | `rgba(180, 83, 9, 0.12)` | Warning badge / callout background |
| `error.base` | `#dc2626` | Fail verdict; hard validation error; destructive action |
| `error.fill` | `rgba(220, 38, 38, 0.12)` | Error badge / callout background |
| `info.base` | `#2563eb` | Informational tags; in-pane informational callouts |
| `info.fill` | `rgba(37, 99, 235, 0.10)` | Info badge / callout background |
| `muted.base` | `#4b5563` | Unknown / untested / pending / neutral state |
| `muted.fill` | `rgba(75, 85, 99, 0.10)` | Neutral badge / callout background |
| `shadow` | `rgba(15, 23, 42, 0.20)` | Modal-dialog and popover drop shadow |
| `overlay` | `rgba(15, 23, 42, 0.32)` | Modal scrim behind a dialog |

## 5. Verdict Palette

The final benchmark verdict is **binary: PASS or FAIL** (see 10_Domain_and_Data/01_DOMAIN_MODEL.md and 08_Cross_Cutting/08-L_ui_standardization.md §6). A result that has not yet completed has no verdict; it is *pending*, not a third verdict. Pending and per-task non-terminal states render with the muted/warning palette below, but they are never presented to the user as a verdict value.

| Display state | Token role | Dark value | Light value |
|---|---|---|---|
| Verdict PASS | `success.base` | `#34d399` | `#047857` |
| Verdict FAIL | `error.base` | `#f87171` | `#dc2626` |
| Pending (result not yet completed) | `muted.base` | `#9ca3af` | `#4b5563` |
| Failed-state result (retryable failure, not a verdict) | `warning.base` | `#fbbf24` | `#b45309` |

Verdict colour is always accompanied by the verdict text label (`PASS` / `FAIL`) and a glyph (see 08-L §5) so the verdict is legible without colour perception.

## 6. Health Palette

Provider and embedding-endpoint health is rendered as a status dot plus a text label.

| Health state | Token role | Dark value | Light value |
|---|---|---|---|
| Live — endpoint reachable and at least one model available | `success.base` | `#34d399` | `#047857` |
| Reachable but zero models available | `warning.base` | `#fbbf24` | `#b45309` |
| Down — endpoint unreachable | `error.base` | `#f87171` | `#dc2626` |
| Not tested / probe disabled | `muted.base` | `#9ca3af` | `#4b5563` |
| Checking — probe in flight (dot pulses) | `muted.base` | `#9ca3af` | `#4b5563` |

The "checking" pulse is a pure opacity animation; its duration obeys the reduced-motion cap in §12.

## 7. Font Chains

The application ships no bundled fonts. Each chain is an ordered preference list resolved by Qt's font system to the first available family.

### 7.1 Platform-aware selection rule

Font selection is **platform-aware**. At startup the theme module reads the current platform from the Platform Detector (see 08-K §2) — a `PlatformKind` value (`MACOS`, `WINDOWS`, `LINUX`, or `UNKNOWN`) — and applies the sans + mono chain prescribed for that platform from §7.2. The theme module **never enumerates installed fonts**: platform-based branching (using `sys.platform`, `QSysInfo`, or the Platform Detector's `PlatformKind`) is the only branching permitted, and per-family probing through `QFontDatabase` is forbidden (see §7.5). Once the platform-specific chain is set on the application, Qt's font system resolves the chain to the first available family without further intervention.

The full eight-family cross-platform chain (§7.2 row "Unknown") is retained **only** as a defensive fallback for `PlatformKind.UNKNOWN` — it is not what the runtime app applies on macOS, Windows, or Linux.

### 7.2 Per-platform font chains

| Platform (`PlatformKind`) | `font.sans` | `font.mono` |
|---|---|---|
| `MACOS` | `"Helvetica Neue", "Arial", sans-serif` | `"Menlo", "Monaco", "Courier New", monospace` |
| `WINDOWS` | `"Segoe UI", "Arial", sans-serif` | `"Consolas", "Cascadia Mono", "Courier New", monospace` |
| `LINUX` | `"Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans", sans-serif` | `"DejaVu Sans Mono", "Ubuntu Mono", "Noto Sans Mono", "Liberation Mono", monospace` |
| `UNKNOWN` (defensive fallback) | `"Segoe UI", "Helvetica Neue", "Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans", "Arial", sans-serif` | `"Consolas", "Menlo", "Cascadia Mono", "DejaVu Sans Mono", "Ubuntu Mono", "Monaco", "Courier New", monospace` |

### 7.3 Per-platform ordering rationale

- **macOS sans** begins with **Helvetica Neue** because it is the reliable macOS UI face resolvable through Qt; **Arial** is the absolute cross-platform safety net before the generic `sans-serif` keyword.
- **macOS mono** begins with **Menlo** (the modern macOS terminal/code face); **Monaco** covers legacy macOS environments; **Courier New** is the absolute fallback before the generic `monospace` keyword.
- **Windows sans** begins with **Segoe UI** because it is the primary UI font on every supported Windows release; **Arial** is the absolute cross-platform safety net before the generic `sans-serif` keyword.
- **Windows mono** begins with **Consolas** because it has been guaranteed-present on Windows since Vista; **Cascadia Mono** follows but is intentionally not first — it ships only with newer Windows setups (Windows Terminal, recent Visual Studio installs) and is **not** guaranteed even on Windows 11, which is why Consolas precedes it; **Courier New** is the absolute fallback before the generic `monospace` keyword.
- **Linux sans** is ordered GNOME default first — **Cantarell** — then the Ubuntu-family **Ubuntu**, then the modern Linux default **Noto Sans** (the default on many current Linux desktops), and finally **DejaVu Sans** as the universal Linux fallback before the generic `sans-serif` keyword.
- **Linux mono** begins with **DejaVu Sans Mono** because it is almost universally installed on desktop Linux and Qt resolves it reliably; **Ubuntu Mono** covers Ubuntu-family systems; **Noto Sans Mono** is the modern Linux default; **Liberation Mono** is the universal Linux fallback before the generic `monospace` keyword.
- **Unknown** carries the full eight-family cross-platform list as a defensive safety net when the Platform Detector cannot classify the host.

### 7.4 Usage rules

- `font.sans` is the default family for every UI surface — labels, buttons, table cells, headings, dialog text.
- `font.mono` is used only where character alignment matters: the run log, YAML editor content in the Task Editor, raw model output, file paths, and numeric columns where digit alignment aids scanning.

### 7.5 No `QFontDatabase` probing

The application **never probes `QFontDatabase`** for family availability to drive any logic. Platform-based branching is allowed and required — the theme module switches on the Platform Detector's `PlatformKind` (or, equivalently, `sys.platform` / `QSysInfo`) to pick the correct chain at startup — but per-family availability probing is forbidden. The chain is declared and Qt's font system resolves it to the first available family. Qt may report substituted or aliased family names rather than the requested family, so any logic built on per-family probing would be unreliable.

### 7.6 Avoided families

Do **not** add these to any chain:

- `"SF Pro Text"`, `"SF Pro Display"`, `"SF Mono"`, `"San Francisco"` — hidden/private system fonts on macOS; not reliably resolvable through Qt's font APIs and may trigger toolkit warnings; cross-platform licensing is ambiguous.
- `"Roboto"`, `"Inter"` — not preinstalled on desktop Linux; do not assume their availability.
- `system-ui`, `BlinkMacSystemFont`, `-apple-system` — browser-only CSS concepts with inconsistent behaviour in Qt stylesheets; do not use them.

### 7.7 Note on HTML mockup files in this specification

The HTML mockup files distributed in this specification (the `mockup.html` documents under the per-widget folders) use the full cross-platform CSS font chain — equivalent to the `UNKNOWN` row of §7.2 — and not a single platform-specific chain. This is deliberate: those mockups are **static documentation** rendered in a web browser on whichever operating system the reviewer happens to use, and the chain must resolve correctly regardless of the reviewer's OS. The cross-platform chain in the mockups is **documentation-only** and is **not** how the runtime application selects fonts. The runtime application reads `PlatformKind` from the Platform Detector at startup and applies the matching platform-specific chain from §7.2.

## 8. Font-Size Tokens

All font sizes are tokens. No widget sets an inline pixel size; the theme module assigns sizes through the application stylesheet and the dynamic-property roles it targets.

| Token | Size | Used for |
|---|---|---|
| `font.size.xs` | 11 px | Captions, badge text, validation-strip text, context-strip text |
| `font.size.sm` | 12 px | Secondary labels, table cells, status-bar text |
| `font.size.base` | 13 px | Body text, input text, button labels, list items |
| `font.size.md` | 14 px | Group-box and section titles |
| `font.size.lg` | 16 px | Panel headings |
| `font.size.xl` | 20 px | Dialog titles |

Font weights are limited to two values: `regular` (400) for body and `semibold` (600) for headings, section titles, primary button labels, and active-tab labels. No other weights are used.

## 9. Spacing Tokens

Every margin, padding, and gap is one of these tokens. Layout code passes token values into Qt layout `setSpacing` / `setContentsMargins` calls; arbitrary pixel literals are not permitted in layout code.

| Token | Size | Typical use |
|---|---|---|
| `space.xs` | 2 px | Hairline gaps; badge inner padding |
| `space.sm` | 4 px | Label-to-input gap; tight icon padding |
| `space.md` | 8 px | Default control padding; gap between related controls |
| `space.lg` | 12 px | Gap between sections; panel inner padding |
| `space.xl` | 16 px | Gap between major regions; dialog inner padding |
| `space.2xl` | 24 px | Dialog outer margins; large vertical separation |

## 10. Radius Tokens

| Token | Radius | Used for |
|---|---|---|
| `radius.sm` | 3 px | Pill badges, chips, status-dot containers |
| `radius.md` | 5 px | Buttons, inputs, dropdowns, segmented-control segments |
| `radius.lg` | 8 px | Dialog frames, panels, group-box surfaces, cards |

## 11. Border and Focus Tokens

| Token | Value | Used for |
|---|---|---|
| `border.width` | 1 px | All neutral borders (panels, inputs, tables, group boxes) |
| `border.width.active` | 1 px `primary.base` | Border of an active/selected input or control |
| `focus.ring` | 1 px `border.focus` outer line + 2 px inner glow of `primary.base` at 40 % opacity | Focus indication on every focusable control (shown when a control gains focus, for example after a click into an input) |

Focus rules:

- Every focusable control renders the `focus.ring` when it holds focus. The ring is always visible — it is never suppressed for visual cleanliness.
- The focus ring meets at least a 3:1 contrast ratio against the adjacent surface in both themes (see §14).
- The application does not hide the focus indicator when an input is reached by clicking.

## 12. Shadow and Motion Tokens

| Token | Value | Used for |
|---|---|---|
| `shadow.modal` | drop shadow using the `shadow` colour, 24 px blur, 8 px y-offset | Modal dialogs and detached chart windows |
| `shadow.popover` | drop shadow using the `shadow` colour, 12 px blur, 4 px y-offset | Tooltips, help popovers, dropdown menus |
| `motion.fast` | 120 ms | Hover and pressed transitions |
| `motion.standard` | 200 ms | Theme repaint cross-fade; pulse cycle; panel show/hide |

Motion rules:

- No animation exceeds `motion.standard` (200 ms).
- When the platform reports a reduced-motion preference, all transitions and the health-dot pulse are disabled; state changes apply instantly. The reduced-motion preference is read through the OS adapter.

## 13. Theme Switching

The theme is controlled by the setting `ui.theme` with three values: `system`, `dark`, `light`. The default is `system`.

- **`system`** — the application reads the OS colour-scheme preference at launch through the OS adapter and selects the matching token container. It also subscribes to the OS colour-scheme change signal and re-applies the theme live when the OS preference changes.
- **`dark`** — the Dark token container is always used, regardless of the OS preference.
- **`light`** — the Light token container is always used, regardless of the OS preference.

Switching behaviour:

1. The theme module replaces the active token container.
2. It rebuilds the application stylesheet and `QPalette` from the new container and re-applies them to the `QApplication`. This repaints every standard widget.
3. It emits a theme-changed notification so that custom-painted surfaces (charts, status dots, badges) re-read their colours and repaint.
4. Theme-tinted icons (those whose tint derives from `text.*` or `muted.*`) are re-rendered for the new theme.
5. The switch never requires an application restart and never discards unsaved user input.
6. The repaint cross-fades over `motion.standard`, or applies instantly under reduced motion.

## 14. WCAG AA Contrast Matrix

The application targets at least **WCAG 2.1 AA**: a contrast ratio of 4.5:1 for normal text, and 3:1 for large text (≥ 18.66 px regular or ≥ 14 px semibold) and for non-text UI components such as borders, focus rings, and status dots. Both themes must satisfy every pair below. Implementers must re-verify these ratios with a contrast tool after any token value change.

| Foreground / background pair | Dark ratio | Light ratio | Minimum required |
|---|---|---|---|
| `text.primary` on `bg.window` | 18.7 : 1 | 17.4 : 1 | 4.5 : 1 (normal text) |
| `text.primary` on `bg.surface` | 16.1 : 1 | 14.2 : 1 | 4.5 : 1 (normal text) |
| `text.primary` on `bg.raised` | 13.2 : 1 | 11.6 : 1 | 4.5 : 1 (normal text) |
| `text.secondary` on `bg.surface` | 5.0 : 1 | 7.1 : 1 | 4.5 : 1 (normal text) |
| `text.secondary` on `bg.raised` | 4.6 : 1 | 5.8 : 1 | 4.5 : 1 (normal text) |
| `text.on-primary` (white) on `primary.base` | 4.6 : 1 | 5.0 : 1 | 4.5 : 1 (normal text) |
| `text.on-error` (white) on `error.base` | 4.7 : 1 | 4.9 : 1 | 4.5 : 1 (normal text) |
| `success.base` on `bg.surface` | 5.3 : 1 | 4.6 : 1 | 3 : 1 (UI component) |
| `warning.base` on `bg.surface` | 7.5 : 1 | 4.5 : 1 | 3 : 1 (UI component) |
| `error.base` on `bg.surface` | 4.8 : 1 | 5.7 : 1 | 3 : 1 (UI component) |
| `info.base` on `bg.surface` | 5.6 : 1 | 5.2 : 1 | 3 : 1 (UI component) |
| `muted.base` on `bg.surface` | 5.0 : 1 | 7.1 : 1 | 3 : 1 (UI component) |
| `border.focus` on `bg.window` | 5.1 : 1 | 4.9 : 1 | 3 : 1 (UI component) |
| `border.default` on `bg.surface` | 3.1 : 1 | 3.0 : 1 | 3 : 1 (UI component) |

Verdict and health text labels always pair their colour with a background from this matrix, so verdict and health information meets the contrast floor on every surface where it appears.

## 15. Accessibility Rules

- **Contrast.** Every text-on-background and component-on-background pair the UI produces satisfies the matrix in §14 in both themes. A palette change is not accepted until the matrix is re-verified.
- **Colour is never the sole channel.** Every state communicated by colour — verdict, health, validation result, run stage — is also communicated by a text label and/or a glyph (see 08-L §4 and §5). The interface remains fully usable for colour-blind users and in greyscale.
- **Reduced motion.** When the OS reports a reduced-motion preference, all transitions and the health-dot pulse are disabled (see §12).
- **High contrast.** When the OS reports a high-contrast preference, the theme module increases `border.width` emphasis and removes soft `*.fill` backgrounds in favour of solid borders, so component boundaries remain distinct.
- **Focus visibility.** The `focus.ring` is always rendered for the focused control and meets the 3:1 component-contrast floor (see §11 and §14).

The numeric accessibility floor and its verification method are owned by 12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md; this document supplies the colour and contrast values that floor depends on.

## 16. The Theme Module Contract

The theme module (`src/ollama_llm_bench/ui/theme/`) is the single styling authority. Its public surface and obligations:

- **Holds the token containers.** Two frozen token containers — one Dark, one Light — each carrying the full set from §3–§12.
- **Resolves roles.** Exposes the active container and a role-resolution accessor used by custom-painted surfaces.
- **Builds and applies styling.** Constructs the application-level Qt stylesheet string and `QPalette` from the active container and applies them to the `QApplication`. This is the only code permitted to call `setStyleSheet()`.
- **Targets dynamic-property roles.** Per-widget appearance variants (primary button, destructive button, icon button, badge variants, context strip) are expressed as Qt dynamic properties on widgets; the application stylesheet selects on those properties. Widget code sets the property; it never sets style.
- **Switches themes.** Implements the §13 switching sequence and emits the theme-changed notification.
- **Reports the active theme.** Other modules may query which theme is active (for example to choose an export chart background) but may not construct styling themselves.

Enforcement: the architecture-test suite fails the build if any module outside `src/ollama_llm_bench/ui/theme/` references `setStyleSheet`, embeds a colour literal in a widget, or imports a token container for direct stylesheet assembly. This keeps the design-token system the single source of truth for the application's appearance.
