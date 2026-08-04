"""Integration tests for the runtime theme re-apply driven by a settings change
(STORY-083-AC-1, STORY-083-AC-2).

All three tests build the real composed application and capture its theme manager and settings
service by patching their `compose` factories with a forwarding `side_effect` -- the real
factories still run, so nothing about the production wiring is stubbed out. This crosses the
compose/QApplication boundary, so it belongs in `tests/integration/`, not a colocated `tests/`.

**Two different Save emitters, deliberately covered separately.** The two lower tests drive
`SettingsService.set()`, which both writes the value and emits an `_app_settings_changed`
event. The real Settings dialog does *not* go through that method: clicking **Save Changes**
writes through `SqliteSettingsAtomicWriter.save_all()`, which emits nothing, and the
announcement comes from the dialog controller's own separate `_emit_settings_changed(...)`
(`06_Settings_Dialog` §6 step 5, `08-Q` §7.2). The first test therefore drives the real
menu-bar Settings action, the real Theme combo, and the real Save Changes button, so that the
production announcement is covered too rather than only the service-level one.

**`_flush_pending_widget_deletions` is load-bearing, not defensive padding.** Every test below
performs a *live*, in-place `QApplication.setStyleSheet()` re-apply from inside a nested
`QEventLoop` (`qtbot.waitSignal`/`qtbot.waitUntil`, or the Settings dialog's own `.exec()` --
a nested loop is required either way, because `QtEventBusDeliverer` always delivers on
`Qt.ConnectionType.QueuedConnection`, so nothing runs the subscriber until an event loop actually
ticks). Empirically, if an *earlier* `tests/integration/` test also built a real `build_app()`
window via `build_real_app` + `qtbot.addWidget` (true of most of this directory), that window's
`deleteLater()`-scheduled destruction is still pending when this test starts, and processing it
concurrently with this test's own live style re-apply segfaults deep in Qt's style engine
(reproduced deterministically, independent of test order, isolated down to this exact
interaction). The helper does not wait a fixed duration -- it loops `gc.collect()` plus a short
event-loop tick, tracking `len(QApplication.allWidgets())`, until that count stops changing
between passes. Direct instrumentation showed why a single pass is not enough: right after an
earlier test's teardown, `QApplication.allWidgets()` still held 545 widgets from the torn-down
app. Those widget wrapper objects only became collectible once a reference cycle involving them
was broken by a `gc.collect()` pass, and the underlying C++ objects were only actually
destroyed -- and so removed from `allWidgets()` -- once a *subsequent* pass's event-loop tick
processed the resulting deferred-delete events; the count reached 0 only after the second pass.
The wait *duration* between passes was not the load-bearing part: `qtbot.wait(10)` proved just
as effective as `qtbot.wait(200)`, so the helper uses the shorter one.
"""

from collections.abc import Callable
import gc
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QPushButton
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.settings import SettingsService, make_settings_service
from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.settings_dialog import make_settings_dialog as _real_make_settings_dialog
from ollama_llm_bench.ui.theme import ActiveThemeKind, PlatformKind, ThemeManager
from ollama_llm_bench.ui.theme.api import make_light_theme_tokens, make_theme_manager

_MAX_FLUSH_PASSES = 10
_SAVE_INTERACTION_DELAY_MS = 50
_THEME_REAPPLY_TIMEOUT_MS = 5000


def _flush_pending_widget_deletions(qtbot: QtBot) -> None:
    """See the module docstring -- clears any earlier test's still-pending `build_app()`
    window teardown before this test's own live, in-nested-loop theme re-apply runs.

    Loops `gc.collect()` followed by a short `qtbot.wait(...)` event-loop tick, reading
    `len(QApplication.allWidgets())` after each pass, until two consecutive passes report the
    same count -- i.e. the widget count has genuinely stopped changing, not merely "enough time
    has passed". This is condition-based rather than a fixed sleep because the load-bearing
    factor is the *number* of `gc.collect()` + event-loop-tick passes (a previous test's widget
    wrapper objects need one pass to become collectible via a broken reference cycle, and a
    second pass's event-loop tick to actually process the resulting deferred deletes), not how
    long any single pass waits.

    Raises `AssertionError` if the count has not stabilized within `_MAX_FLUSH_PASSES` passes,
    so a regression in the underlying Qt/GC behaviour this helper depends on fails loudly
    instead of silently letting the segfault-inducing race back in.
    """
    previous_count: int | None = None
    for _ in range(_MAX_FLUSH_PASSES):
        gc.collect()
        qtbot.wait(10)
        current_count = len(QApplication.allWidgets())
        if current_count == previous_count:
            return
        previous_count = current_count
    raise AssertionError(
        f"_flush_pending_widget_deletions: widget count did not stabilize after "
        f"{_MAX_FLUSH_PASSES} passes (last count={previous_count}); the segfault-avoidance "
        "guard this helper exists for may no longer be effective"
    )


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


def _switch_theme_to_light_and_save(dialog: QDialog, qtbot: QtBot) -> None:
    """Drive the real Settings dialog to light and click its real **Save Changes** button.

    Runs from a `QTimer` callback *inside* the dialog's own blocking `.exec()` nested event
    loop, which is the only place the dialog's widgets are reachable while production is
    sitting in `compose.py`'s `.exec()` call.

    The dismissal at the end calls `QDialog.reject` **unbound** on purpose. `SettingsDialogView`
    overrides `reject()` to re-route Esc/title-bar-close through its own `close_requested`
    signal, which asks the controller whether it is safe to close and can open a second, nested
    "discard unsaved changes?" `QMessageBox.exec()`. A Save that worked leaves the dialog clean,
    so that path would not fire -- but a Save that *regressed* would leave it dirty, and the
    confirmation box would then block this callback forever and hang the suite instead of
    failing it. Calling the base-class `reject()` directly closes the dialog unconditionally, so
    a regression in what this test asserts shows up as a failed assertion, never as a hang.
    Dismissal is plumbing here; nothing is asserted from it.
    """
    theme_combo = cast("QComboBox", dialog.findChild(QComboBox, "ui.theme"))
    assert theme_combo is not None
    theme_combo.setCurrentText("light")
    save_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.save_changes_button")
    )
    assert save_button is not None
    assert save_button.isEnabled()
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        save_button, Qt.MouseButton.LeftButton
    )
    QDialog.reject(dialog)


@pytest.mark.allow_qt_warnings  # offscreen-only: opening the real Settings dialog resizes a
# widget before the offscreen platform plugin has a native window to hint, which logs
# "This plugin does not support propagateSizeHints()" -- pre-existing offscreen-plugin
# behaviour (identical to the marker on `test_menu_opens_dialogs.py`'s two tests), not a
# defect in this test or the production dialog wiring.
def test_clicking_save_changes_in_the_real_settings_dialog_reapplies_theme(  # noqa: PLR0913  # the real app-composition rig needs seed_setting and the dialog-capture fixtures alongside build_real_app_without_enabled_providers/app_data_root_all_providers_disabled/qapp/qtbot/mocker
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    app_data_root_all_providers_disabled: Path,
    seed_setting: Callable[..., None],
    qapp: QApplication,
    qtbot: QtBot,
    mocker: MockerFixture,
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-083-AC-1

    Given the running application started under the dark theme and the real Settings dialog
    opened from the real menu-bar Settings action with its Theme control switched to light,
    when the user clicks the dialog's real **Save Changes** button, then the theme module
    re-applies the theme to the live QApplication -- with no application restart.

    This drives the production Save path end to end, which the sibling test above does not:
    Save goes through the settings gateway's `save_all()` to `SqliteSettingsAtomicWriter`,
    which persists the values but emits *nothing*, and the announcement the whole feature
    hangs off comes from the dialog controller's own separate `_emit_settings_changed(...)`
    (`06_Settings_Dialog` §6 step 5, `08-Q` §7.2). Driving `SettingsService.set()` instead --
    as the sibling test does -- exercises a different emitter, so it would keep passing if that
    announcement were removed while the theme silently stopped re-applying on Save.

    Every provider is disabled so the dialog's embedding-section bootstrap search touches no
    socket; see `build_real_app_without_enabled_providers` in `tests/integration/conftest.py`.
    """
    # Arrange
    _flush_pending_widget_deletions(qtbot)
    seed_setting(app_data_root_all_providers_disabled, key="ui.theme", value="dark")
    managers, _services = _capture_collaborators(mocker)
    captured_dialogs: list[QDialog] = []

    def _capture_dialog(**kwargs: object) -> QDialog:
        dialog = _real_make_settings_dialog(**kwargs)  # type: ignore[arg-type]  # forwarding real compose kwargs
        captured_dialogs.append(dialog)
        return dialog

    mocker.patch("ollama_llm_bench.compose.make_settings_dialog", side_effect=_capture_dialog)
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    manager = managers[0]
    assert manager.active_theme_kind is ActiveThemeKind.DARK
    stylesheet_before = qapp.styleSheet()
    settings_button = cast("QPushButton", handle.window.findChild(QPushButton, "settings_action"))
    assert settings_button is not None

    # Act -- the menu-bar click blocks inside the real dialog's `.exec()`, so the theme switch
    # and the Save click are driven from a timer callback running inside that nested loop.
    QTimer.singleShot(
        _SAVE_INTERACTION_DELAY_MS,
        lambda: _switch_theme_to_light_and_save(captured_dialogs[0], qtbot),
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        settings_button, Qt.MouseButton.LeftButton
    )

    # Assert -- the container flipped and the live QApplication carries the light palette. The
    # bus delivers `AppSettingsChangedEvent` on a queued connection, so the flip lands on a
    # later event-loop turn than the Save click; `waitUntil` turns the loop until it does
    # (a real condition, not a fixed sleep) and returns at once if it already has.
    qtbot.waitUntil(
        lambda: manager.active_theme_kind is ActiveThemeKind.LIGHT,
        timeout=_THEME_REAPPLY_TIMEOUT_MS,
    )
    assert qapp.styleSheet() != stylesheet_before
    expected_window_color = make_light_theme_tokens(
        platform_kind=PlatformKind.LINUX
    ).colors.bg_window
    assert qapp.palette().color(QPalette.ColorRole.Window).name() == expected_window_color

    # Cleanup -- see `drain_task_runner_deliveries`/`_drain_pending_task_runner_deliveries` in
    # `tests/integration/conftest.py` for why this must run in the test body, not a fixture.
    drain_task_runner_deliveries(handle)


def test_saving_theme_change_reapplies_theme_without_restart(  # noqa: PLR0913  # the real app-composition rig needs seed_setting alongside build_real_app/seeded_app_data_root/qapp/qtbot/mocker
    build_real_app: Callable[[], AppHandle],
    seeded_app_data_root: Path,
    seed_setting: Callable[..., None],
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
    _flush_pending_widget_deletions(qtbot)
    seed_setting(seeded_app_data_root, key="ui.theme", value="dark")
    managers, services = _capture_collaborators(mocker)
    handle = build_real_app()
    qtbot.addWidget(handle.window)
    manager = managers[0]
    settings = services[0]
    active_theme_kind_before = manager.active_theme_kind
    assert active_theme_kind_before is ActiveThemeKind.DARK
    stylesheet_before = qapp.styleSheet()
    assert stylesheet_before != ""

    # Act -- the same write + announcement the Settings dialog performs on Save; the bus
    # delivers on a queued connection (adapters/qt_event_bus), so waiting for the resulting
    # `theme_changed` notification is what lets the queued dispatch actually run before assert.
    with qtbot.waitSignal(manager.theme_changed, timeout=2000):
        settings.set("ui.theme", "light")

    # Assert -- the container flipped and the live QApplication carries the light palette
    active_theme_kind_after = manager.active_theme_kind
    assert active_theme_kind_after is ActiveThemeKind.LIGHT
    assert qapp.styleSheet() != stylesheet_before
    expected_window_color = make_light_theme_tokens(
        platform_kind=PlatformKind.LINUX
    ).colors.bg_window
    assert qapp.palette().color(QPalette.ColorRole.Window).name() == expected_window_color


def test_theme_reapply_emits_theme_changed_notification_once(  # noqa: PLR0913  # the real app-composition rig needs seed_setting alongside build_real_app/seeded_app_data_root/qapp/qtbot/mocker
    build_real_app: Callable[[], AppHandle],
    seeded_app_data_root: Path,
    seed_setting: Callable[..., None],
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
    _flush_pending_widget_deletions(qtbot)
    seed_setting(seeded_app_data_root, key="ui.theme", value="dark")
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

    # `waitSignal` quits its nested loop on the *first* emission, so it cannot by itself prove
    # there wasn't a second one queued for a later event-loop turn. Let the loop turn again
    # before asserting, so a duplicate emission would still land in `notifications` in time.
    qtbot.wait(50)

    # Assert
    assert notifications == [True]
