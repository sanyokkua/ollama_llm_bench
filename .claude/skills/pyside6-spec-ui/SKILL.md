---
name: pyside6-spec-ui
description: Use when writing or reviewing any PySide6 widget, dialog, or theming code in this project — covers the theme-module styling authority, design tokens, the no-placeholder-UI rule, dialog button ordering, the MVC-family widget layout, and the accessibility floor.
---

# PySide6 UI Standards (Project-Specific)

Source of truth: `docs/v3_specification/08_Cross_Cutting/08-D_color_palette_and_typography.md` (design tokens) and `docs/v3_specification/08_Cross_Cutting/08-L_ui_standardization.md` (interaction patterns). This skill is project-specific UI law layered on top of general PySide6 practice — where it conflicts with general Qt habits, this skill wins for this codebase.

## The single theme-module styling authority

The application is built with **programmatic Qt Widgets** — no QML, no `.qss` files on disk anywhere in the source tree. Exactly one module, `src/ollama_llm_bench/ui/theme/`, owns all styling:

- It holds two frozen token containers — one Dark, one Light — each an immutable `msgspec.Struct(frozen=True, kw_only=True)` (or equivalent frozen dataclass).
- It builds the application-level Qt stylesheet string and `QPalette` objects from the active container and applies them to the `QApplication`.
- **`setStyleSheet()` is forbidden everywhere outside this one module.** The architecture-enforcement stack (`import-linter` + a `pytest-archon` rule) fails the build if any module outside `src/ollama_llm_bench/ui/theme/` calls `setStyleSheet`, embeds a color literal in a widget, or imports a token container for direct stylesheet assembly.

Widget code never sets style directly. Instead it sets a **Qt dynamic property** (e.g. `role="primary-button"`) that the single application-level stylesheet targets:

```python
# RIGHT — widget code names a role, never a literal color
save_button = QPushButton("Save Changes")
save_button.setProperty("role", "primary-button")

# WRONG — never call setStyleSheet outside ui/theme/, never embed a hex literal
save_button.setStyleSheet("background-color: #14b8a6; color: white;")
```

Custom-painted surfaces (`QPainter`-based charts, status dots, badges) read their colors from the active theme's token container by **role name** — they never hold their own palette and never hardcode a hex value.

### Design tokens — reference by role, never by literal

Tokens are grouped into families and referenced by role name so the same widget code is correct in either theme:

| Family | Prefix | Example roles |
|---|---|---|
| Background layers | `bg.*` | `bg.window`, `bg.surface`, `bg.raised`, `bg.selected`, `bg.input` |
| Borders | `border.*` | `border.default`, `border.strong`, `border.focus` |
| Text | `text.*` | `text.primary`, `text.secondary`, `text.disabled`, `text.on-primary` |
| Primary (brand) | `primary.*` | `primary.base`, `primary.hover`, `primary.pressed`, `primary.disabled` |
| Semantic | `success.*`, `warning.*`, `error.*`, `info.*` | `.base` (the solid color) and `.fill` (a soft translucent background) |
| Muted / neutral | `muted.*` | `muted.base`, `muted.fill` — unknown/untested/pending/neutral states |
| Effect | `shadow`, `overlay` | Drop shadows, modal scrims |

Spacing, radius, and font sizes are tokens too — `space.xs` through `space.2xl` (2px–24px), `radius.sm/md/lg` (3/5/8px), `font.size.xs` through `font.size.xl` (11px–20px). Layout code passes these into `setSpacing`/`setContentsMargins`; arbitrary pixel literals are not permitted in layout code. Both Dark and Light token sets are mandatory and complete — neither is ever a partial or "best effort" theme.

## The "no placeholder UI" rule

This is a hard rule, stated in one line: **hide what does not apply; disable (with a reason) what is about to apply; never ship a control wired to nothing.**

- **A control inapplicable to the current state is removed from the layout entirely — never shown greyed out.** The canonical project example: the Benchmark workspace's left configuration panel is hidden entirely while a run is active, not disabled in place. When applicability changes, the control appears or disappears and the surrounding layout reflows cleanly with no leftover gap.
- **Legitimate transient disabling is still permitted** — a control that is momentarily not actionable but *will* become actionable shortly may be shown disabled, but it **must** carry a tooltip explaining why. Canonical examples: a dialog's Save button while the form is invalid; the menu bar's Settings action while a benchmark run is in a non-terminal stage. A transiently disabled control with no explanatory tooltip is a defect, not a minor omission.
- No "coming soon" tiles, no empty tabs that do nothing, no buttons wired to nothing. Every tab has content; every button has behavior. An empty state (e.g. the Results tab before any run exists) is deliberate, designed content with explanatory text — never a blank stubbed area.

```python
# RIGHT — the control is removed from the layout when it doesn't apply
def _on_run_state_changed(self, *, is_active: bool) -> None:
    self._left_config_panel.setVisible(not is_active)   # hidden, not disabled

# RIGHT — transient disabling with a mandatory tooltip
self._settings_action.setEnabled(not run_in_progress)
self._settings_action.setToolTip(
    "Disabled while a benchmark run is in progress." if run_in_progress else ""
)

# WRONG — permanently disabled with no explanation, or disabled with no tooltip at all
self._unused_feature_button.setEnabled(False)   # no tooltip, no future re-enable path
```

## Dialog button ordering

**The right-most button is always the primary/default action.** The escape/back-out action (Cancel, Discard, Close, Back) sits immediately to its left. Lower-priority side actions (Reset, Import, Export) cluster on the far left, in their own cluster, separate from the back-out/primary pair.

```
[Reset to Defaults] [Import...] [Export...]          [Close]  [Save Changes]
 <------- side-action cluster ------->        <-- back-out --> <-- primary -->
```

A destructive primary action (e.g. `[Cancel] [Delete]`) is still right-most and still primary, but rendered with the destructive style (`error.base` fill) instead of the default primary style, so the danger is visually distinct from an ordinary confirm.

One footer-specific wrinkle worth remembering: **when Close is the footer's only or right-most action** (no separate confirm button beside it — e.g. an error dialog or the About dialog), Close itself **becomes the primary/default action** and takes the filled `primary.base` style, not the outlined-muted "back-out" style. The outlined-muted Close style applies only when Close is sitting to the left of a distinct primary confirm, e.g. Settings' `[Close] [Save Changes]`.

```python
# RIGHT — Close is the only footer action, so it is styled as primary
close_button = QPushButton("Close")
close_button.setProperty("role", "primary-button")   # filled, not outlined

# RIGHT — Close sits beside a distinct primary confirm, so it's the outlined back-out
close_button.setProperty("role", "outlined-muted-button")
save_button.setProperty("role", "primary-button")
```

## The MVC-family per-widget module layout

Every UI feature module follows the same internal shape, with a factory function in `api.py` returning the mountable widget, a frozen ViewModel `msgspec.Struct` in `models.py`, and the rendering/controller split inside `_internal/`:

```
src/ollama_llm_bench/ui/new_benchmark/
    __init__.py
    api.py                       # make_new_benchmark_widget(...) -> QWidget
    models.py                    # frozen ViewModel Struct + UI event types
    _internal/
        view.py                  # QWidget subclass: rendering only
        controller.py             # store subscriptions + signal handlers
        view_model_select.py      # pure functions: store state -> ViewModel
    tests/
```

- `view.py` renders. It never calls a Gateway method directly and never contains business logic — it only reflects whatever ViewModel it's given.
- `controller.py` wires signals/slots and calls the widget's Gateway (see the `protocol-first-interfaces` skill for what a Gateway is and is not).
- `view_model_select.py` holds pure functions that turn raw store/gateway state into the frozen ViewModel struct the view renders — no Qt imports here at all, which makes these functions trivially unit-testable with no `QApplication`.

`api.py`'s factory function is the only public entry point a parent module calls:

```python
# api.py
def make_new_benchmark_widget(*, gateway: NewBenchmarkGateway, bus: EventBus) -> QWidget:
    """Construct the mountable New Benchmark widget.

    Returns:
        The fully wired QWidget, ready to be added to a parent layout.
    """
    view = _View()
    controller = _Controller(view=view, gateway=gateway, bus=bus)
    controller.bind()
    return view
```

## The accessibility floor — what this app actually targets

This app targets **WCAG 2.1 AA for color/contrast only** — it is explicitly **mouse-only by design**, not a full WCAG-conformant application. Don't over-engineer keyboard navigation paths that the spec deliberately excludes; but never skip the contrast and color-independence rules, which are mandatory.

- **Contrast.** Every text-on-background and component-on-background pair meets at least 4.5:1 (normal text) or 3:1 (large text ≥18.66px regular / ≥14px semibold, and non-text UI components like borders/focus rings/status dots) — in **both** themes. A token-value change is not accepted until the full contrast matrix is re-verified with a contrast tool.
- **Colour is never the sole channel.** Every state communicated by color — verdict, health, validation result, run stage — is also communicated by a text label and/or a glyph. The interface must remain fully usable for colorblind users and in greyscale. A verdict badge, for instance, always pairs its `success.base`/`error.base` fill with the literal text `PASS`/`FAIL` plus a check-mark/cross-mark glyph — never color alone.
- **Mouse-only operation.** No **custom** keyboard shortcuts, accelerators, F-keys, mnemonics, or required keyboard-navigation paths. Dialogs are always dismissible by clicking close (X) or Cancel. (The host toolkit's incidental Enter/Esc behavior on a modal's default/cancel button is permitted but is never the *only* way to perform an action.)
- **Click-target size.** Every clickable control offers a hit area of at least **24x24 logical pixels**, so the user can reliably aim with a mouse or trackpad — this includes icon-only buttons, which are otherwise sized 28x28px per the button-style table.
- **Visible focus.** Every focusable control renders the `focus.ring` token when it holds focus; the ring is never suppressed, including when focus is reached by a mouse click into an input.
- **Reduced motion.** When the OS reports a reduced-motion preference, all transitions and the health-dot pulse animation are disabled; state changes apply instantly instead.

```python
# RIGHT — a verdict is never color-only
verdict_label = QLabel("PASS")
verdict_label.setProperty("role", "success-badge")   # success.fill background, success.base text
verdict_icon.setPixmap(check_mark_glyph)              # glyph reinforces the same state
```

## Quick checklist before committing new/changed UI code

- [ ] No `setStyleSheet()` call outside `src/ollama_llm_bench/ui/theme/`.
- [ ] No literal hex color, no raw pixel size, anywhere in widget/layout code — only token roles and dynamic properties.
- [ ] Any control inapplicable to the current state is hidden (`setVisible(False)`), not just disabled.
- [ ] Any transiently disabled control carries a tooltip explaining why.
- [ ] Dialog footer follows the ordering rule: side actions left, back-out then primary on the right, primary right-most; Close-only footers use the primary (filled) style.
- [ ] New UI feature module follows the `api.py` / `models.py` / `_internal/{view,controller,view_model_select}.py` split.
- [ ] Every color-coded state also carries a text label or glyph.
- [ ] Every clickable control (including icon-only buttons) has at least a 24x24px hit area and a hover tooltip.
- [ ] The surface is checked against both Dark and Light themes for WCAG AA contrast.
