"""Integration tests for the runtime theme re-apply driven by a settings change
(STORY-083-AC-1, STORY-083-AC-2).

Builds the real composed application and drives the real `SettingsService`, whose `set` both
writes the value and emits the genuine `_app_settings_changed` event the Settings dialog emits
on Save (`06_Settings_Dialog` §6 step 5, `08-Q` §7.2). The theme manager and settings service
are captured by patching their `compose` factories with a forwarding `side_effect` -- the real
factories still run, so nothing about the production wiring is stubbed out. This crosses the
compose/QApplication boundary, so it belongs in `tests/integration/`, not a colocated `tests/`.

**`_flush_pending_widget_deletions` is load-bearing, not defensive padding.** Both tests below
perform a *live*, in-place `QApplication.setStyleSheet()` re-apply from inside a nested
`QEventLoop` (`qtbot.waitSignal` -- required because `QtEventBusDeliverer` always delivers on
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

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.settings import SettingsService, make_settings_service
from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.theme import ActiveThemeKind, PlatformKind, ThemeManager
from ollama_llm_bench.ui.theme.api import make_light_theme_tokens, make_theme_manager

_MAX_FLUSH_PASSES = 10


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
