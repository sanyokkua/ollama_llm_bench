# STORY-083 Implementation Plan — Runtime theme re-apply + Settings/About menu actions

**Goal:** Make a saved theme change repaint the running app immediately, and prove the menu-bar
Settings and About items actually open their real modal dialogs.

**Architecture:** The theme module already owns the entire switch sequence — `ThemeManager`
has a public `set_theme_setting(...)` lever, applies the stylesheet and `QPalette` to the
`QApplication`, and emits a `theme_changed` Qt signal. Nothing calls it in production. This
story adds the missing **trigger**: a subscriber in the composition root that listens for the
app-settings-changed bus event, and when `ui.theme` is among the changed keys, re-reads the
value and hands it to the theme manager. No new module, no new Protocol, no styling code
outside `ui/theme/`.

**Tech Stack:** Python 3.13, PySide6 6.8, `pytest-qt`, `msgspec`, `structlog`, `icontract`.

## Context — why this work exists

Two user-facing behaviours are wired but dead:

1. **The theme setting does nothing until restart.** A user opens Settings → General → Display,
   switches Theme from `dark` to `light`, clicks Save Changes. The value is persisted correctly
   and the dialog announces the change on the event bus — but nobody is listening for it. The
   app keeps its dark palette until the process restarts. `08-D` §13 is explicit that switching
   "never requires an application restart".

1. **Nothing proves the menu items open their dialogs.** `grep settings_requested tests/`
   returns zero hits. The one adjacent test (STORY-077's) replaces both dialogs with mocks, so
   it proves the callback is reachable but never that a real dialog opens.

## Global Constraints

- `docs/v3_specification/` is read-only. Never edit it.
- Only `src/ollama_llm_bench/ui/theme/` may call `setStyleSheet()` — architecture-test enforced
  (`tests/architecture/test_ui_theme_style_authority.py`).
- **`compose.py` must stay within 50–520 lines.** It is at **508** today.
  `tests/architecture/test_compose_line_budget.py` is a standing invariant whose docstring
  names STORY-083 by name. This plan's compose changes add **6 lines → 514**. Do not exceed.
- `EventBus.subscribe(...)` **requires a non-`None` `owner`** — the concrete Qt deliverer calls
  `weakref.finalize(owner, ...)` for a non-`QObject` owner, which raises on `None`.
- Never `git commit --no-verify`. Never delete a failing test to make the suite pass.
- Tests: fully annotated, `-> None`, Arrange/Act/Assert comments, no `if`/`for` in a test body,
  one logical assertion each. First docstring line is exactly `Proves: STORY-083-AC-N`.
- `qtbot.mouseClick(...)` needs `# type: ignore[no-untyped-call]  # pytest-qt provides no type stubs`.
- `findChild` results are wrapped in `cast("QPushButton", ...)` followed by an `assert ... is not None`.
- Do **not** add `@pytest.mark.integration` — tier is determined by directory in this repo.
- Magic-number comparisons need a named local or `# noqa: PLR2004  # <reason>` (`PLR2004` is
  not ignored for tests).

______________________________________________________________________

## Spec grounding

| Source                         | What it fixes                                                                                                                                                                                                                                                  |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `08-D` §13                     | The switch sequence: replace container → rebuild stylesheet + `QPalette`, re-apply to `QApplication` → **emit the theme-changed notification** → never restart, never discard unsaved input.                                                                   |
| `08-D` §16                     | `ui/theme/` is the sole styling authority and the only code allowed to call `setStyleSheet()`.                                                                                                                                                                 |
| `06_Settings_Dialog` §4.6      | The Theme control persists `ui.theme` as `system` / `dark` / `light`.                                                                                                                                                                                          |
| `06_Settings_Dialog` §6 step 5 | On commit the dialog emits `_app_settings_changed`. §18 confirms Import and Reset emit it too.                                                                                                                                                                 |
| `08-Q` §7.2                    | `AppSettingsChangedEvent(changed_keys: tuple[str, ...])` — **key names only, never values**. "A consumer reads the new value from the settings service."                                                                                                       |
| **`08-J` line 181**            | Names the subscriber this story builds: *"the application theme controller (re-reads `ui.theme` to re-apply the palette)"*. Thread `UI → UI`, no coalescing. **This is why the trigger is a bus subscription and not a direct call from the Settings dialog.** |
| `01_Main_Window` §3.1 / §3.2   | Settings action opens the Settings modal (disabled while a run is non-terminal); About action opens the Application Information modal and is always available.                                                                                                 |

## Two behaviours of the existing code you must not fight

1. **`_reapply_if_changed()` early-returns when the resolved `ActiveThemeKind` is unchanged** —
   no re-apply, no signal. `system → system` on an already-dark OS is a deliberate silent
   no-op. AC-2 says "a saved theme change that **switches the active theme**", which matches
   exactly. Seed `dark` and switch to `light` so the kind provably flips regardless of the
   host OS colour scheme.

1. **`changed_keys` always contains `ui.theme` on a Save.** The dialog's `values_for_save()`
   returns the whole General-tab map, not a diff. So the `"ui.theme" in changed_keys` guard
   fires on *every* save — harmless only because of behaviour 1. Never write an assertion that
   treats presence in `changed_keys` as proof the theme changed.

______________________________________________________________________

## File structure

| File                                                                 | Responsibility                                                                                                                |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Create** `tests/integration/conftest.py`                           | The composed-app test rig, moved out of `test_compose_build_app.py` so three files share one copy instead of triplicating it. |
| **Modify** `src/ollama_llm_bench/compose.py`                         | Line 87 import; ~6 new lines after line 443 wiring the settings-change subscriber to the theme manager.                       |
| **Create** `tests/integration/test_theme_reapply_on_save.py`         | AC-1, AC-2.                                                                                                                   |
| **Create** `tests/integration/test_menu_opens_dialogs.py`            | AC-3, AC-4.                                                                                                                   |
| **Modify** `tests/integration/test_compose_build_app.py`             | Delete the five fixtures/helpers now living in `conftest.py`.                                                                 |
| **Modify** `docs/stories/story-083-app-level-theme-dialog-wiring.md` | `status: draft` → `in-progress` → `done`.                                                                                     |
| **Modify** `CHANGELOG.md`                                            | One `Fixed` entry under `[Unreleased]`.                                                                                       |
| **Regenerate** `traceability.yaml`                                   | Via `just trace`. Never hand-edited.                                                                                          |

______________________________________________________________________

## Task 1: Extract the composed-app test rig into `tests/integration/conftest.py`

Both new test files need the same six pieces that are currently private to
`test_compose_build_app.py`. Copying them twice would triplicate the rig — the exact debt
already flagged once in this repo. Move them first, prove nothing broke, then build on them.

**Files:**

- Create: `tests/integration/conftest.py`
- Modify: `tests/integration/test_compose_build_app.py` (delete lines ~68–172: the constant,
  `_disconnect_os_color_scheme_signal`, `isolated_home`, `seeded_app_data_root`,
  `_seed_setting`, `_shutdown`, `build_real_app`)

**Interfaces produced** (later tasks rely on these exact names):

- `build_real_app: Callable[[], AppHandle]` — fixture; builds a real app against a seeded,
  isolated app-data root and tears every handle down afterwards.

- `seeded_app_data_root: Path` — fixture; the app-data directory `build_app` will resolve.

- `_seed_setting(app_data_root: Path, *, key: str, value: str) -> None` — module-level helper.

- `_disconnect_os_color_scheme_signal` — autouse fixture; required because every `build_app`
  attaches a `ThemeManager` to the session-scoped `qapp.styleHints().colorSchemeChanged`.

- [ ] **Step 1: Create the conftest by moving the rig verbatim**

Copy the constant, the four fixtures, and the two helpers out of `test_compose_build_app.py`
into a new `tests/integration/conftest.py` **without changing their bodies**. Keep the
docstrings. The file's imports are whatever those bodies already reference (`functools`,
`Path`, `Generator`, `Callable`, `pytest`, `QApplication`, `QEventLoop`, plus the
`ollama_llm_bench` symbols they use: `AppHandle`, `build_app`, `DB_FILENAME`,
`open_write_connection`, `open_read_connection`, `create_app_settings_store`,
`make_system_clock`, `make_platform_detector`, `create_app_data_dir`, `ensure_schema`,
`seed_builtin_providers`).

Give the new file this module docstring:

```python
"""Shared rig for `tests/integration/` tests that build the real composed application.

Moved here from `test_compose_build_app.py` so the theme-reapply and menu-dialog suites
(STORY-083) share one copy instead of triplicating it. The autouse
`_disconnect_os_color_scheme_signal` fixture is load-bearing: every `build_app` constructs a
`ThemeManager` that connects to the session-scoped `qapp.styleHints().colorSchemeChanged`,
and `pytest-randomly` reorders tests, so a leaked connection corrupts a later test.
"""
```

- [ ] **Step 2: Delete the moved definitions from `test_compose_build_app.py`**

Remove them and drop any import that is now unused. Leave every test function untouched — they
pick the fixtures up from the conftest automatically.

- [ ] **Step 3: Verify the move changed no behaviour**

```bash
uv run pytest tests/integration/test_compose_build_app.py -q
```

Expected: the same pass count as before the move, zero failures.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/conftest.py tests/integration/test_compose_build_app.py
git commit -m "test(story-083): extract the composed-app integration rig into a shared conftest"
```

______________________________________________________________________

## Task 2: Wire the application theme controller (AC-1, AC-2)

**Files:**

- Modify: `src/ollama_llm_bench/compose.py:87` (import) and after `:443` (the wiring)
- Create: `tests/integration/test_theme_reapply_on_save.py`

**Interfaces:**

- Consumes: `build_real_app`, `seeded_app_data_root`, `_seed_setting` from Task 1.

- Produces: nothing new on any public surface. `compose.py` gains one private closure.

- [ ] **Step 1: Write the two failing tests**

Create `tests/integration/test_theme_reapply_on_save.py`:

```python
"""Integration tests for the runtime theme re-apply driven by a settings change
(STORY-083-AC-1, STORY-083-AC-2).

Builds the real composed application and drives the real `SettingsService`, whose `set` both
writes the value and emits the genuine `_app_settings_changed` event the Settings dialog emits
on Save (`06_Settings_Dialog` §6 step 5, `08-Q` §7.2). The theme manager and settings service
are captured by patching their `compose` factories with a forwarding `side_effect` -- the real
factories still run, so nothing about the production wiring is stubbed out. This crosses the
compose/QApplication boundary, so it belongs in `tests/integration/`, not a colocated `tests/`.
"""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.settings import SettingsService, make_settings_service
from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.theme import ActiveThemeKind, PlatformKind, ThemeManager
from ollama_llm_bench.ui.theme.api import make_light_theme_tokens, make_theme_manager


def _capture_collaborators(
    mocker: MockerFixture,
) -> tuple[list[ThemeManager], list[SettingsService]]:
    """Patch compose's theme-manager and settings-service factories to record what they build.

    Both `side_effect`s forward to the real factory, so the application is composed exactly as
    it is in production -- the patch only takes a typed reference to the real objects.
    """
    managers: list[ThemeManager] = []
    services: list[SettingsService] = []

    def _capture_manager(**kwargs: object) -> ThemeManager:
        manager = make_theme_manager(**kwargs)  # type: ignore[arg-type]  # forwarding real build_app kwargs
        managers.append(manager)
        return manager

    def _capture_service(**kwargs: object) -> SettingsService:
        service = make_settings_service(**kwargs)  # type: ignore[arg-type]  # forwarding real build_app kwargs
        services.append(service)
        return service

    mocker.patch("ollama_llm_bench.compose.make_theme_manager", side_effect=_capture_manager)
    mocker.patch("ollama_llm_bench.compose.make_settings_service", side_effect=_capture_service)
    return managers, services


def test_saving_theme_change_reapplies_theme_without_restart(
    build_real_app: Callable[[], AppHandle],
    seeded_app_data_root: Path,
    qapp: QApplication,
    qtbot: QtBot,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-083-AC-1

    Given the running application started under the dark theme, when a settings write changes
    `ui.theme` to light and announces it on the event bus exactly as the Settings dialog's Save
    does, then the theme module re-applies the theme to the live QApplication and the active
    theme container reflects the new value -- with no application restart.
    """
    # Arrange
    _seed_setting(seeded_app_data_root, key="ui.theme", value="dark")
    managers, services = _capture_collaborators(mocker)
    handle = build_real_app()
    qtbot.addWidget(handle.window)
    manager = managers[0]
    settings = services[0]
    assert manager.active_theme_kind is ActiveThemeKind.DARK
    stylesheet_before = qapp.styleSheet()
    assert stylesheet_before != ""

    # Act -- the same write + announcement the Settings dialog performs on Save
    settings.set("ui.theme", "light")

    # Assert -- the container flipped and the live QApplication carries the light palette
    assert manager.active_theme_kind is ActiveThemeKind.LIGHT
    assert qapp.styleSheet() != stylesheet_before
    expected_window_color = make_light_theme_tokens(
        platform_kind=PlatformKind.LINUX
    ).colors.bg_window
    assert qapp.palette().color(QPalette.ColorRole.Window).name() == expected_window_color


def test_theme_reapply_emits_theme_changed_notification_once(
    build_real_app: Callable[[], AppHandle],
    seeded_app_data_root: Path,
    qapp: QApplication,
    qtbot: QtBot,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-083-AC-2

    Given a saved theme change that switches the active theme, when the theme is re-applied,
    then the theme module emits its theme-changed notification exactly once, so custom-painted
    surfaces (charts, status dots, badges) re-read their colours and repaint (08-D §13 step 3).
    """
    # Arrange
    _seed_setting(seeded_app_data_root, key="ui.theme", value="dark")
    managers, services = _capture_collaborators(mocker)
    handle = build_real_app()
    qtbot.addWidget(handle.window)
    manager = managers[0]
    settings = services[0]
    notifications: list[bool] = []
    manager.theme_changed.connect(lambda: notifications.append(True))

    # Act
    with qtbot.waitSignal(manager.theme_changed, timeout=2000):
        settings.set("ui.theme", "light")

    # Assert
    assert notifications == [True]
```

Both patched factories forward to the real ones imported at module scope
(`make_theme_manager`, `make_settings_service`), so the application is composed exactly as it
is in production -- `mocker.patch` replaces only the name `compose` looks up, never the
factory the test calls.

- [ ] **Step 2: Run the tests and confirm they fail for the right reason**

```bash
uv run pytest tests/integration/test_theme_reapply_on_save.py -q
```

Expected: both FAIL. AC-1 fails on `assert manager.active_theme_kind is ActiveThemeKind.LIGHT`
(it is still `DARK`); AC-2 fails with a `qtbot.waitSignal` timeout. A failure with a different
message means the rig is wrong, not the production gap — fix the rig before continuing.

- [ ] **Step 3: Widen the compose import (still one line)**

`src/ollama_llm_bench/compose.py:87`, replace:

```python
from ollama_llm_bench.backend.events import EventBus
```

with:

```python
from ollama_llm_bench.backend.events import SIGNAL_APP_SETTINGS_CHANGED, AppSettingsChangedEvent, EventBus  # fmt: skip
```

The `# fmt: skip` keeps it one physical line — this is the same technique `compose.py` already
uses throughout, and it is what keeps the line budget intact. Net new lines: **0**.

- [ ] **Step 4: Add the subscriber immediately after the theme manager is built**

Insert directly after `src/ollama_llm_bench/compose.py:443` (the `theme_manager = ...` line):

```python

    def _reapply_theme_on_settings_change(payload: object) -> None:
        """Re-read `ui.theme` and re-apply it live when a settings write changed it (08-J, 08-D §13)."""
        if isinstance(payload, AppSettingsChangedEvent) and "ui.theme" in payload.changed_keys:
            theme_manager.set_theme_setting(ThemeSetting(settings.get_str("ui.theme") or "system"))

    bus.subscribe(SIGNAL_APP_SETTINGS_CHANGED, _reapply_theme_on_settings_change, owner=theme_manager)
```

Three things are load-bearing here:

- **`owner=theme_manager`** is required, not optional. The Qt deliverer calls
  `weakref.finalize(owner, ...)` for a non-`QObject` owner and would raise on `None`;
  `ThemeManager` is a `QObject`, so the subscription auto-cancels on its `destroyed` signal.
- **The `isinstance` guard** is not defensive padding — `subscribe` types the handler as
  `Callable[[object], None]`, so `payload.changed_keys` does not type-check without it.
- **Re-reading through `settings.get_str`** is what `08-Q` §7.2 mandates: the event carries key
  names only, never values. `SettingsService` does not cache, so this reads the just-written
  value.

Net new lines: **6** (one blank + five code). `compose.py` goes 508 → 514, inside the 520 ceiling.

- [ ] **Step 5: Run the tests and the line-budget guard**

```bash
uv run pytest tests/integration/test_theme_reapply_on_save.py tests/architecture/test_compose_line_budget.py -q
wc -l src/ollama_llm_bench/compose.py
```

Expected: 3 passed. `wc -l` reports **514**.

- [ ] **Step 6: Confirm no styling authority was violated**

```bash
uv run pytest tests/architecture -q
```

Expected: all pass — in particular `test_setstylesheet_confined_to_ui_theme`. Nothing in this
task builds or applies a stylesheet outside `ui/theme/`; it only calls the theme module's
public lever.

- [ ] **Step 7: Commit**

```bash
git add src/ollama_llm_bench/compose.py tests/integration/test_theme_reapply_on_save.py
git commit -m "feat(story-083): re-apply the theme live when a settings change writes ui.theme"
```

______________________________________________________________________

## Task 3: Prove the menu actions open the real dialogs (AC-3, AC-4)

The existing `test_build_app_injects_settings_and_about_callbacks` (STORY-077-AC-8) already
clicks both buttons — but with both dialogs replaced by mocks, so it cannot fail if a dialog
stops opening. These tests let the **real** dialogs construct and run their blocking `.exec()`,
and dismiss them on a timer. That is the pattern
`tests/integration/test_launch_abort_modal_quits.py` established, and its own docstring explains
why it matters: with a real `.exec()`, a regression **hangs the test** instead of passing.

**Files:**

- Create: `tests/integration/test_menu_opens_dialogs.py`

**Interfaces:**

- Consumes: `build_real_app` from Task 1.

- Produces: nothing.

- [ ] **Step 1: Write the two tests**

Create `tests/integration/test_menu_opens_dialogs.py`:

```python
"""Integration tests proving the menu-bar Settings and About actions open their real modal
dialogs (STORY-083-AC-3, STORY-083-AC-4).

Neither dialog is stubbed to a `.exec()`-returns-instantly double -- that is the whole point.
`ollama_llm_bench.compose.make_settings_dialog` / `make_about_dialog` are patched only to take a
typed reference to the dialog the *real* factory builds; the call is forwarded unchanged. A
`QTimer.singleShot` inspects the live modal and closes it so the nested `.exec()` returns. If
the wiring regresses, these tests hang instead of quietly passing -- which is exactly the
failure mode the existing STORY-077-AC-8 test (both dialogs mocked) cannot detect.
"""

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QPushButton
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

import ollama_llm_bench.compose as compose
from ollama_llm_bench.compose import AppHandle

_DISMISS_DELAY_MS = 50


def test_settings_action_opens_settings_dialog(
    build_real_app: Callable[[], AppHandle], qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-083-AC-3

    Given the main window is shown, when the user activates the menu-bar Settings action, then
    the real Settings modal dialog opens (`01_Main_Window` §3.1).
    """
    # Arrange
    real_factory = compose.make_settings_dialog
    captured: list[QDialog] = []
    observed: dict[str, bool] = {}

    def _capture(**kwargs: object) -> QDialog:
        dialog = cast("QDialog", real_factory(**kwargs))  # type: ignore[arg-type]  # forwarding real compose kwargs
        captured.append(dialog)
        return dialog

    mocker.patch("ollama_llm_bench.compose.make_settings_dialog", side_effect=_capture)
    handle = build_real_app()
    qtbot.addWidget(handle.window)
    settings_button = cast("QPushButton", handle.window.findChild(QPushButton, "settings_action"))
    assert settings_button is not None
    assert settings_button.isEnabled()

    def _inspect_and_dismiss() -> None:
        dialog = captured[0]
        observed["visible"] = dialog.isVisible()
        observed["modal"] = dialog.isModal()
        dialog.close()

    # Act -- blocks inside the dialog's nested exec() until the timer dismisses it
    QTimer.singleShot(_DISMISS_DELAY_MS, _inspect_and_dismiss)
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        settings_button, Qt.MouseButton.LeftButton
    )

    # Assert
    assert observed == {"visible": True, "modal": True}


def test_about_action_opens_about_dialog(
    build_real_app: Callable[[], AppHandle], qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-083-AC-4

    Given the main window is shown, when the user activates the menu-bar About action, then the
    real Application Information modal dialog opens (`01_Main_Window` §3.2).
    """
    # Arrange
    real_factory = compose.make_about_dialog
    captured: list[QDialog] = []
    observed: dict[str, bool] = {}

    def _capture(**kwargs: object) -> QDialog:
        dialog = cast("QDialog", real_factory(**kwargs))  # type: ignore[arg-type]  # forwarding real compose kwargs
        captured.append(dialog)
        return dialog

    mocker.patch("ollama_llm_bench.compose.make_about_dialog", side_effect=_capture)
    handle = build_real_app()
    qtbot.addWidget(handle.window)
    about_button = cast("QPushButton", handle.window.findChild(QPushButton, "about_action"))
    assert about_button is not None

    def _inspect_and_dismiss() -> None:
        dialog = captured[0]
        observed["visible"] = dialog.isVisible()
        observed["modal"] = dialog.isModal()
        dialog.close()

    # Act -- blocks inside the dialog's nested exec() until the timer dismisses it
    QTimer.singleShot(_DISMISS_DELAY_MS, _inspect_and_dismiss)
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        about_button, Qt.MouseButton.LeftButton
    )

    # Assert
    assert observed == {"visible": True, "modal": True}
```

Two notes for whoever runs this:

- **Take `real_factory = compose.make_settings_dialog` before `mocker.patch`.** Reading it
  afterwards captures the mock and recurses forever.

- **A freshly opened Settings dialog is clean**, so `close()` takes the plain reject path and
  does not raise a discard-confirmation `QMessageBox`. Do not mutate any field before closing.

- [ ] **Step 2: Run them**

```bash
uv run pytest tests/integration/test_menu_opens_dialogs.py -q
```

Expected: 2 passed. **If either hangs**, the dialog never opened or the capture list was empty
when the timer fired — that is a real failure signal, not flakiness. Interrupt, and check that
the patch target is `ollama_llm_bench.compose.<factory>` (the consumer module, never the
source module).

- [ ] **Step 3: Confirm they hold under the offscreen platform CI uses**

Locally these run against the native macOS window server; CI sets `QT_QPA_PLATFORM=offscreen`.
Verify both:

```bash
QT_QPA_PLATFORM=offscreen uv run pytest tests/integration/test_menu_opens_dialogs.py -q
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_menu_opens_dialogs.py
git commit -m "test(story-083): prove the menu-bar Settings and About actions open real modals"
```

______________________________________________________________________

## Task 4: Close out traceability and documentation

**Files:**

- Modify: `docs/stories/story-083-app-level-theme-dialog-wiring.md`

- Modify: `CHANGELOG.md`

- Regenerate: `traceability.yaml`

- [ ] **Step 1: Add the CHANGELOG entry**

Under `[Unreleased]` → `Fixed` in `CHANGELOG.md`:

```markdown
- Changing the theme in Settings now repaints the whole application immediately on save,
  instead of only taking effect after a restart.
```

Nothing goes under `Added` — no public API changed. The theme module's surface is untouched.

- [ ] **Step 2: Set the story status to `done`**

In the front-matter of `docs/stories/story-083-app-level-theme-dialog-wiring.md`, change
`status: draft` to `status: done`, and tick the four Definition-of-done checkboxes.

> Use `Bash`/Python for this edit, not the `Edit` tool, if the markdown formatter hook would
> reflow the whole file.

- [ ] **Step 3: Regenerate and validate the traceability record**

```bash
just trace
just trace-check
```

Expected: `trace-check` reports **zero** failures. Every one of STORY-083-AC-1..AC-4 must map to
the test that names it. If `trace-check` reports pre-existing failures unrelated to STORY-083,
capture the list and report it rather than absorbing it into this story.

- [ ] **Step 4: Run the full local CI mirror**

```bash
just check
```

Expected: lint, format-check, `mypy --strict`, import-check, arch-test, and the test suite all
pass. Fix every `ruff`/`mypy` finding in the files this story touched — "pre-existing" is not a
valid reason to skip one here, because all four touched files are new or modified by this story.

- [ ] **Step 5: Commit**

```bash
git add docs/stories/story-083-app-level-theme-dialog-wiring.md CHANGELOG.md traceability.yaml
git commit -m "chore(story-083): mark STORY-083 done and regenerate the traceability record"
```

______________________________________________________________________

## Verification — end to end

Beyond the suite, confirm the behaviour in the real application:

```bash
uv run python -m ollama_llm_bench
```

1. Click **Settings** in the menu bar → the Settings dialog opens (AC-3).
1. Go to **General → Display**, change **Theme** from its current value to the other explicit
   value (`dark` ⇄ `light`), click **Save Changes** → **the entire window repaints immediately**,
   including the still-open Settings dialog. No restart (AC-1). Confirm the dialog's own
   contents are not discarded by the repaint (`08-D` §13 step 5).
1. Confirm the custom-painted surfaces re-coloured too — the status-bar health dot and any
   verdict badges (AC-2, the `theme_changed` consumers).
1. Close Settings, click **About** → the About dialog opens with the version and the
   application-data-folder row (AC-4).
1. Start a benchmark run, then check the menu bar: **Settings** is disabled with the tooltip
   `Disabled - a benchmark is in progress.` while **About** stays clickable (`01_Main_Window`
   §3.1/§3.2 — existing behaviour, confirm this story did not disturb it).

## Risks

| Risk                                                                                | Mitigation                                                                                                                                                  |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `compose.py` line budget: 514/520 after this story, 6 lines of headroom left        | The budget test runs on every suite run. If a later edit pushes past 520, that needs a fourth owner-approved widening — do not silently raise the constant. |
| The AC-3/AC-4 tests block in a real `.exec()`                                       | Deliberate: a hang is the regression signal. The `QTimer.singleShot` dismissal is the project's established pattern (`test_launch_abort_modal_quits.py`).   |
| Test-order randomisation leaking a `ThemeManager` ↔ `colorSchemeChanged` connection | The autouse `_disconnect_os_color_scheme_signal` fixture from Task 1 covers every file in `tests/integration/`.                                             |
| Overlap with STORY-077-AC-8                                                         | Accepted and deliberate: that test proves the callbacks are reachable with mocked dialogs; these prove a real dialog opens. Both stay.                      |
