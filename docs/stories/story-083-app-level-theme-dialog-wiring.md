---
id: STORY-083
title: Re-apply the theme at runtime on save and open the Settings and About dialogs from the menu
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#13-theme-switching
  - 06_Settings_Dialog/description.md#46-display
  - 06_Settings_Dialog/description.md#6-save-flow-atomic
  - 01_Main_Window/description.md#31-settings-action
  - 01_Main_Window/description.md#32-about-action
modules:
  - ui/theme/
  - ui/settings_dialog/
  - ui/main_window/
acceptance_criteria:
  - STORY-083-AC-1
  - STORY-083-AC-2
  - STORY-083-AC-3
  - STORY-083-AC-4
edge_cases: []
depends_on:
  - STORY-077
adrs: []
owner: coder
estimate: M
---

# STORY-083 — Re-apply the theme at runtime on save and open the Settings and About dialogs from the menu

## Goal

Make two half-wired user-facing behaviours actually work end to end. First, when the user changes the
theme in Settings and saves, the whole application repaints in the new theme immediately, with no
restart — today the setting is persisted but nothing re-applies it. Second, the Settings and About
menu-bar actions actually open their modal dialogs — today the main-window controller's dialog-open
callbacks were only injected at composition time (STORY-077); this story proves they open the dialogs
when the user activates the menu items.

## In scope

- Wiring the Settings save path so that a changed `ui.theme` value drives the theme module to
  re-apply the theme to the running `QApplication` immediately (the runtime theme switch of
  `08-D` §13), with no restart.
- Proving the theme-changed notification is emitted on that re-apply so custom-painted surfaces
  re-read their colours.
- Proving that activating the menu-bar Settings action opens the Settings modal dialog end to end.
- Proving that activating the menu-bar About action opens the About modal dialog end to end.

## Out of scope

- Constructing the theme manager and applying the theme once at startup, and injecting the
  Settings/About callbacks into the main-window controller — owned by STORY-077 (this story's
  prerequisite; here the wiring is exercised through the UI, not created).
- The `system` OS-colour-scheme live re-apply path — already delivered by the theme module's OS
  colour-scheme subscription; this story covers the user-driven `ui.theme` change on save.
- The Settings dialog's own content, validation, and atomic save transaction — already delivered;
  this story only ensures the saved theme value re-applies at runtime.

## Spec inputs

- `08_Cross_Cutting/08-D_color_palette_and_typography.md#13-theme-switching` — the theme module
  replaces the active token container, rebuilds and re-applies the stylesheet/`QPalette` (repainting
  every standard widget), emits a theme-changed notification, and never requires an application
  restart or discards unsaved input.
- `06_Settings_Dialog/description.md#46-display` — the Theme control persists `ui.theme` as
  `system`, `dark`, or `light`.
- `06_Settings_Dialog/description.md#6-save-flow-atomic` — Save Changes commits the general-tab
  values (including `ui.theme`) atomically and emits the settings-changed event; the runtime
  re-apply is driven off that saved change.
- `01_Main_Window/description.md#31-settings-action` — the menu-bar Settings action opens the
  Settings modal dialog (gated only while a run is non-terminal).
- `01_Main_Window/description.md#32-about-action` — the menu-bar About action opens the Application
  Information modal dialog and is always available.

## Design constraints

- Only `ui/theme/` may build or apply a stylesheet; the Settings save path requests the re-apply
  through the theme module's public surface, it does not assemble styling itself.
- A UI controller holds only its per-widget adapter gateway, never a backend Store/Service Protocol
  directly (D-R-06).
- No `setStyleSheet` call exists outside `ui/theme/` (architecture-test enforced).

## Acceptance criteria

### STORY-083-AC-1

Given the Settings General tab with the theme changed to a different value,
when the user saves the change,
then the theme module re-applies the theme to the running `QApplication` immediately and the active
theme container reflects the new value, with no application restart.

### STORY-083-AC-2

Given a saved theme change that switches the active theme,
when the theme is re-applied,
then the theme module emits its theme-changed notification exactly once so custom-painted surfaces
re-read their colours.

### STORY-083-AC-3

Given the main window is shown,
when the user activates the menu-bar Settings action,
then the Settings modal dialog opens.

### STORY-083-AC-4

Given the main window is shown,
when the user activates the menu-bar About action,
then the About modal dialog opens.

## Test plan

- STORY-083-AC-1 — integration (`pytest-qt`), `tests/integration/test_theme_reapply_on_save.py`,
  `test_saving_theme_change_reapplies_theme_without_restart`.
- STORY-083-AC-2 — integration (`pytest-qt`), same file,
  `test_theme_reapply_emits_theme_changed_notification_once`.
- STORY-083-AC-3 — integration (`pytest-qt`), `tests/integration/test_menu_opens_dialogs.py`,
  `test_settings_action_opens_settings_dialog`.
- STORY-083-AC-4 — integration (`pytest-qt`), same file,
  `test_about_action_opens_about_dialog`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-083.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
