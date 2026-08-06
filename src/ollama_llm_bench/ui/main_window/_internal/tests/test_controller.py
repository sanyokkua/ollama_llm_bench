"""Unit tests for ``_internal/controller.py`` (STORY-053-AC-1, STORY-053-AC-2,
STORY-053-AC-3, EC-SET-1).
"""

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.workspace_controller.models import WorkspaceHint
from ollama_llm_bench.backend.domain import ErrorKind, ReadinessState, RunMode, RunStatus
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_READINESS_CHANGED,
    SIGNAL_GLOBAL_MESSAGE,
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_PAUSED,
    SIGNAL_RUN_RENAMED,
    SIGNAL_RUN_RESUMED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_WORKSPACE_CHANGED,
    AppReadinessChangedEvent,
    GlobalMessageEvent,
    ProviderHealthSummary,
    RunFailedEvent,
    RunFinishedEvent,
    RunPausedEvent,
    RunRenamedEvent,
    RunResumedEvent,
    RunStartedEvent,
    RunStoppedEvent,
    WorkspaceChangedEvent,
)
from ollama_llm_bench.ui.main_window._internal import controller as controller_module
from ollama_llm_bench.ui.main_window._internal.tests.conftest import MainWindowHarness
from ollama_llm_bench.ui.main_window.models import MainWindowViewModel

_DISABLED_SETTINGS_TOOLTIP = "Disabled - a benchmark is in progress."


def _make_run_started_event(*, run_id: int = 1, run_name: str = "my-run") -> RunStartedEvent:
    return RunStartedEvent(
        run_id=run_id,
        run_name=run_name,
        run_mode=RunMode.TASKS,
        started_at="2026-01-01T00:00:00Z",
        total_tasks=10,
        test_targets=(("provider-1", "model-1"),),
    )


def _make_run_paused_event(*, run_id: int = 1) -> RunPausedEvent:
    return RunPausedEvent(
        run_id=run_id, paused_at="2026-01-01T00:01:00Z", completed_tasks=1, total_tasks=10
    )


def _make_run_stopped_event(*, run_id: int = 1) -> RunStoppedEvent:
    return RunStoppedEvent(
        run_id=run_id, stopped_at="2026-01-01T00:02:00Z", completed_tasks=1, total_tasks=10
    )


def _make_run_finished_event(*, run_id: int = 1) -> RunFinishedEvent:
    return RunFinishedEvent(
        run_id=run_id,
        finished_at="2026-01-01T00:02:00Z",
        run_status=RunStatus.COMPLETED,
        total_tasks=10,
        completed_tasks=10,
        counts_by_result_status={},
        total_elapsed_ms=1000,
    )


def _not_ready_event() -> AppReadinessChangedEvent:
    """Build a readiness event where every operability check failed."""
    return AppReadinessChangedEvent(
        overall=ReadinessState.NOT_READY,
        per_provider=(
            ProviderHealthSummary(
                provider_id="provider-1",
                reachable=False,
                discovery_supported=True,
                model_count=None,
            ),
        ),
        embedding_reachable=False,
        checked_at="2026-01-01T00:00:00Z",
    )


def _make_run_failed_event(*, run_id: int = 1) -> RunFailedEvent:
    return RunFailedEvent(
        run_id=run_id,
        failed_at="2026-01-01T00:02:00Z",
        error_kind=ErrorKind.OTHER,
        error_message="boom",
        completed_tasks=1,
        total_tasks=10,
    )


def _settings_action(harness: MainWindowHarness) -> QPushButton:
    return cast(
        "QPushButton", harness.shell.menu_bar.findChild(QPushButton, "settings_menu_button")
    )


def _running_pill(harness: MainWindowHarness) -> QPushButton:
    return cast("QPushButton", harness.shell.menu_bar.findChild(QPushButton, "running_pill_button"))


def _click_health_dot(harness: MainWindowHarness) -> None:
    harness.shell.status_bar.health_dot_clicked.emit()


def _append_and_call(
    sequence: list[str], label: str, original: Callable[..., None]
) -> Callable[..., None]:
    """Build a patch side effect recording ``label`` then delegating to ``original``.

    Used to pin the relative order of two independently-faked collaborator calls
    (the shell's ``apply_view_model`` and the notification service's ``show_error``)
    against a single shared list, rather than asserting on two disconnected mocks.
    """

    def _side_effect(*args: object, **kwargs: object) -> None:
        sequence.append(label)
        original(*args, **kwargs)

    return _side_effect


def test_run_started_shows_pill_disables_settings(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: STORY-053-AC-1

    Given the shell is in the ``Idle`` state,
    when a ``_run_started`` event is delivered,
    then the running pill becomes visible, the Settings action becomes disabled, the health
    dot becomes non-clickable, and the window title switches to the running title.
    """
    # Arrange
    harness = make_harness()

    # Act
    harness.event_bus.emit(SIGNAL_RUN_STARTED, _make_run_started_event(run_name="my-run"))

    # Assert
    assert _running_pill(harness).isVisible()
    assert not _settings_action(harness).isEnabled()
    assert _settings_action(harness).toolTip() == _DISABLED_SETTINGS_TOOLTIP
    assert "Running:" in harness.shell.windowTitle()
    _click_health_dot(harness)
    assert harness.gateway.reprobe_calls == 0
    assert len(harness.notifications.info_calls) == 1


def _reach_idle(harness: MainWindowHarness) -> None:
    return None


def _reach_running(harness: MainWindowHarness) -> None:
    harness.event_bus.emit(SIGNAL_RUN_STARTED, _make_run_started_event())


def _reach_paused(harness: MainWindowHarness) -> None:
    harness.event_bus.emit(SIGNAL_RUN_STARTED, _make_run_started_event())
    harness.event_bus.emit(SIGNAL_RUN_PAUSED, _make_run_paused_event())


def _reach_stopping(harness: MainWindowHarness) -> None:
    harness.shell.apply_view_model(_view_model_for(settings_enabled=False, pill_visible=True))


def _reach_finishing(harness: MainWindowHarness) -> None:
    harness.shell.apply_view_model(_view_model_for(settings_enabled=False, pill_visible=True))


def _view_model_for(*, settings_enabled: bool, pill_visible: bool) -> MainWindowViewModel:
    return MainWindowViewModel(
        window_title="Ollama LLM Bench v9.9.9",
        active_workspace="benchmark",
        settings_action_enabled=settings_enabled,
        running_pill_visible=pill_visible,
        running_pill_label="my-run" if pill_visible else "",
        health_state=ReadinessState.READY,
        health_tooltip="",
        health_dot_clickable=not pill_visible,
        toast_text="",
    )


def _assert_dot_reprobes_on_click(harness: MainWindowHarness) -> None:
    _click_health_dot(harness)
    assert harness.gateway.reprobe_calls == 1
    assert len(harness.notifications.info_calls) == 0


def _assert_dot_blocked_on_click(harness: MainWindowHarness) -> None:
    _click_health_dot(harness)
    assert harness.gateway.reprobe_calls == 0
    assert len(harness.notifications.info_calls) == 1


def _assert_dot_state_only(harness: MainWindowHarness) -> None:
    """``Stopping``/``Finishing`` are reached via a direct ``shell.apply_view_model`` call,
    bypassing ``MainWindowController`` entirely (per its own docstring/state coverage: no
    ``_run_*`` event models the ``RunStarting``/``Stopping``/``Finishing`` transitional shell
    states -- ``Stopping`` is entered by "user clicked Stop", owned by the Progress widget of a
    later story, and this controller's ``_run_finished``/``_run_failed`` handlers collapse
    straight to the terminal ``Idle`` render with no observable ``Finishing`` interval).
    Dot-click routing (``reprobe`` vs. the blocked-click toast) is controller-internal state
    (``_run_non_terminal``), so it cannot be exercised through a click here; the
    ``health_dot_clickable=False`` field on the constructed ``MainWindowViewModel`` itself is
    this row's total-table proof instead.
    """
    del harness


@pytest.mark.parametrize(
    ("reach_state", "settings_enabled", "pill_visible", "assert_dot_behaviour"),
    [
        (_reach_idle, True, False, _assert_dot_reprobes_on_click),
        (_reach_running, False, True, _assert_dot_blocked_on_click),
        (_reach_paused, False, True, _assert_dot_blocked_on_click),
        (_reach_stopping, False, True, _assert_dot_state_only),
        (_reach_finishing, False, True, _assert_dot_state_only),
    ],
    ids=["idle", "running", "paused", "stopping", "finishing"],
)
def test_shell_affordances_per_run_state(
    reach_state: Callable[[MainWindowHarness], None],
    settings_enabled: bool,  # noqa: FBT001  # parametrize tuple element
    pill_visible: bool,  # noqa: FBT001  # parametrize tuple element
    assert_dot_behaviour: Callable[[MainWindowHarness], None],
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: STORY-053-AC-2

    For each window-level run state, the shell imposes the affordances the specification
    assigns it: Settings action enablement, running-pill visibility, and health-dot
    clickability (proven, where the controller can reach the state, by whether a click routes
    to ``gateway.reprobe`` or is blocked into a ``notifications.show_info`` toast).
    """
    # Arrange
    harness = make_harness()

    # Act
    reach_state(harness)

    # Assert
    assert _settings_action(harness).isEnabled() is settings_enabled
    assert _running_pill(harness).isVisible() is pill_visible
    assert_dot_behaviour(harness)


@pytest.mark.parametrize(
    ("signal_name", "make_event"),
    [
        (SIGNAL_RUN_STOPPED, _make_run_stopped_event),
        (SIGNAL_RUN_FINISHED, _make_run_finished_event),
        (SIGNAL_RUN_FAILED, _make_run_failed_event),
    ],
    ids=["run_stopped", "run_finished", "run_failed"],
)
def test_terminal_event_restores_idle_affordances(
    signal_name: str,
    make_event: Callable[[], object],
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: STORY-053-AC-3

    Given a run is non-terminal,
    when a ``_run_finished``, ``_run_stopped``, or ``_run_failed`` event is delivered,
    then the running pill is hidden, the Settings action is re-enabled, and the window title
    returns to the default ``Ollama LLM Bench v{version}`` form.
    """
    # Arrange
    harness = make_harness()
    harness.event_bus.emit(SIGNAL_RUN_STARTED, _make_run_started_event())

    # Act
    harness.event_bus.emit(signal_name, make_event())

    # Assert
    assert not _running_pill(harness).isVisible()
    assert _settings_action(harness).isEnabled()
    assert harness.shell.windowTitle() == "Ollama LLM Bench v9.9.9"


def test_settings_action_disabled_while_run_non_terminal(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: EC-SET-1

    Given a run is non-terminal,
    when the Settings action's enabled state is inspected,
    then it is disabled and carries the explanatory tooltip -- the same affordance rule
    STORY-053-AC-2's ``Running`` row asserts, verified here as its own edge-case-cited test.
    """
    # Arrange
    harness = make_harness()

    # Act
    harness.event_bus.emit(SIGNAL_RUN_STARTED, _make_run_started_event())

    # Assert
    assert not _settings_action(harness).isEnabled()
    assert _settings_action(harness).toolTip() == _DISABLED_SETTINGS_TOOLTIP


def _make_run_resumed_event(*, run_id: int = 1) -> RunResumedEvent:
    return RunResumedEvent(
        run_id=run_id, resumed_at="2026-01-01T00:01:30Z", completed_tasks=2, total_tasks=10
    )


def test_run_resumed_restores_running_title_from_paused(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Given a run is ``Paused``, when a ``_run_resumed`` event is delivered, then the window
    title switches back from the ``Paused:`` form to the ``Running:`` form and the run stays
    non-terminal (pill still visible, Settings still disabled).

    Given/When/Then: closes a `just coverage-layers` gap on ``_on_run_resumed``, which no
    existing STORY-053 acceptance criterion separately numbers.
    """
    # Arrange
    harness = make_harness()
    harness.event_bus.emit(SIGNAL_RUN_STARTED, _make_run_started_event(run_name="my-run"))
    harness.event_bus.emit(SIGNAL_RUN_PAUSED, _make_run_paused_event())
    assert "Paused:" in harness.shell.windowTitle()

    # Act
    harness.event_bus.emit(SIGNAL_RUN_RESUMED, _make_run_resumed_event())

    # Assert
    assert "Running: my-run" in harness.shell.windowTitle()
    assert _running_pill(harness).isVisible()
    assert not _settings_action(harness).isEnabled()


def test_run_renamed_updates_title_for_the_current_run(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Given the running-pill's run id matches a ``_run_renamed`` event's run id, when the
    event is delivered, then the window title reflects the new run name.

    Given/When/Then: closes a `just coverage-layers` gap on ``_on_run_renamed``.
    """
    # Arrange
    harness = make_harness()
    harness.event_bus.emit(SIGNAL_RUN_STARTED, _make_run_started_event(run_id=1, run_name="old"))

    # Act
    harness.event_bus.emit(SIGNAL_RUN_RENAMED, RunRenamedEvent(run_id=1, new_name="renamed-run"))

    # Assert
    assert "Running: renamed-run" in harness.shell.windowTitle()


def test_run_renamed_for_a_different_run_id_is_ignored(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Given the current run's id does not match a ``_run_renamed`` event's run id, when the
    event is delivered, then the window title is left unchanged -- proves the guard clause
    branch of ``_on_run_renamed`` that discards a rename for a run other than the reflected one.

    Given/When/Then: closes a `just coverage-layers` gap on ``_on_run_renamed``'s early-return
    branch.
    """
    # Arrange
    harness = make_harness()
    harness.event_bus.emit(SIGNAL_RUN_STARTED, _make_run_started_event(run_id=1, run_name="my-run"))

    # Act
    harness.event_bus.emit(
        SIGNAL_RUN_RENAMED, RunRenamedEvent(run_id=999, new_name="unrelated-run")
    )

    # Assert
    assert "Running: my-run" in harness.shell.windowTitle()


def _health_dot(harness: MainWindowHarness) -> QWidget:
    health_region = cast("QWidget", harness.shell.status_bar.findChild(QWidget, "health_region"))
    layout = health_region.layout()
    assert layout is not None
    item = layout.itemAt(0)
    assert item is not None
    dot = item.widget()
    assert dot is not None
    return dot


def test_readiness_changed_updates_health_dot_tooltip(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Given an ``_app_readiness_changed`` event reporting an unreachable provider and an
    unreachable embedding endpoint, when the event is delivered, then the health dot's tooltip
    is rebuilt from that event's per-provider and embedding fields.

    Given/When/Then: closes a `just coverage-layers` gap on ``_on_readiness_changed``.
    """
    # Arrange
    harness = make_harness()

    # Act
    harness.event_bus.emit(
        SIGNAL_APP_READINESS_CHANGED,
        AppReadinessChangedEvent(
            overall=ReadinessState.NOT_READY,
            per_provider=(
                ProviderHealthSummary(
                    provider_id="provider-1",
                    reachable=False,
                    discovery_supported=True,
                    model_count=None,
                ),
            ),
            embedding_reachable=False,
            checked_at="2026-01-01T00:00:00Z",
        ),
    )

    # Assert
    tooltip = _health_dot(harness).toolTip()
    assert "provider-1: unreachable" in tooltip
    assert "embedding: unreachable" in tooltip


def test_entering_not_ready_shows_blocking_explanatory_modal(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: STORY-081-AC-2

    A totally-failed health check is surfaced twice -- the status bar dot and a
    blocking explanatory modal (EC-M-5, 08-M_app_lifecycle.md section 5).
    """
    # Arrange
    harness = make_harness()

    # Act
    harness.event_bus.emit(SIGNAL_APP_READINESS_CHANGED, _not_ready_event())

    # Assert
    assert [blocking for _text, blocking in harness.notifications.error_calls] == [True]


def test_repeated_not_ready_results_show_the_modal_once(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: STORY-081-AC-2

    The probe re-runs on demand and after settings changes; the modal is
    edge-triggered so a still-broken environment does not re-prompt.
    """
    # Arrange
    harness = make_harness()

    # Act
    harness.event_bus.emit(SIGNAL_APP_READINESS_CHANGED, _not_ready_event())
    harness.event_bus.emit(SIGNAL_APP_READINESS_CHANGED, _not_ready_event())

    # Assert
    assert len(harness.notifications.error_calls) == 1


def test_modal_text_names_the_unreachable_providers_and_the_remedy(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Proves: STORY-081-AC-2

    The modal states what is wrong and how to correct it, not merely that
    something failed (08-M_app_lifecycle.md section 5).
    """
    # Arrange
    harness = make_harness()

    # Act
    harness.event_bus.emit(SIGNAL_APP_READINESS_CHANGED, _not_ready_event())

    # Assert
    text = harness.notifications.error_calls[0][0]
    assert "provider-1" in text and "Settings" in text


def test_readiness_not_ready_renders_before_the_blocking_modal(
    make_harness: Callable[..., MainWindowHarness],
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-081-AC-2

    The two surfacings of a totally-failed health check must appear concurrently,
    not with the status bar catching up once the user dismisses the dialog:
    ``show_error(..., blocking=True)`` opens a nested ``QMessageBox.critical(...).exec()``
    loop that blocks the GUI thread until the user dismisses it, so the shell's
    view-model -- and with it the health dot's repaint to NOT_READY -- must already be
    applied before that call, never after (08-M_app_lifecycle.md section 5: "surfaced
    twice: in the status bar, and through an explanatory modal dialog").
    """
    # Arrange
    harness = make_harness()
    sequence: list[str] = []
    render_original = harness.shell.apply_view_model
    show_error_original = harness.notifications.show_error
    mocker.patch.object(
        harness.shell,
        "apply_view_model",
        side_effect=_append_and_call(sequence, "render", render_original),
    )
    mocker.patch.object(
        harness.notifications,
        "show_error",
        side_effect=_append_and_call(sequence, "show_error", show_error_original),
    )

    # Act
    harness.event_bus.emit(SIGNAL_APP_READINESS_CHANGED, _not_ready_event())

    # Assert
    assert sequence == ["render", "show_error"]


def test_global_message_shows_toast_then_auto_clears(
    make_harness: Callable[..., MainWindowHarness],
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    """Given a ``_global_message`` event, when it is delivered, then the toast label shows its
    text immediately and clears itself once the debounce timer elapses.

    Given/When/Then: closes a `just coverage-layers` gap on ``_on_global_message`` and
    ``_clear_toast``; the clear-debounce interval is monkeypatched short so the test stays
    within the unit-test time budget instead of waiting on the real 5-second interval.
    """
    # Arrange
    harness = make_harness()
    monkeypatch.setattr(controller_module, "_TOAST_CLEAR_MS", 20)
    toast_label = cast("QLabel", harness.shell.status_bar.findChild(QLabel, "toast_label"))

    # Act
    harness.event_bus.emit(SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text="Saved settings"))

    # Assert
    assert toast_label.text() == "Saved settings"
    qtbot.waitUntil(lambda: toast_label.text() == "", timeout=1000)


def _workspace_switcher_task_editor_button(harness: MainWindowHarness) -> QPushButton:
    return cast(
        "QPushButton",
        harness.shell.menu_bar.findChild(QPushButton, "workspace_task_editor_button"),
    )


def test_workspace_changed_event_checks_the_matching_switcher_segment(
    make_harness: Callable[..., MainWindowHarness],
) -> None:
    """Given a ``_workspace_changed`` event naming the ``task_editor`` workspace, when the
    event is delivered, then the menu bar's workspace switcher reflects it as the checked
    segment.

    Given/When/Then: closes a `just coverage-layers` gap on ``_on_workspace_changed``; relates
    to STORY-053's declared in-scope subscription to ``_workspace_changed``
    (`01_Main_Window/description.md#5-workspace-switcher-and-the-workspace-region`), though no
    single numbered acceptance criterion isolates this reflection on its own.
    """
    # Arrange
    harness = make_harness()

    # Act
    harness.event_bus.emit(SIGNAL_WORKSPACE_CHANGED, WorkspaceChangedEvent(workspace="task_editor"))

    # Assert
    assert _workspace_switcher_task_editor_button(harness).isChecked()


def test_workspace_switch_requested_routes_to_workspace_controller(
    make_harness: Callable[..., MainWindowHarness], qtbot: QtBot
) -> None:
    """Given the user clicks the Task Editor segment of the menu bar's workspace switcher, when
    the click is processed, then the controller routes it to
    ``WorkspaceController.switch_to("task_editor")``.

    Given/When/Then: closes a `just coverage-layers` gap on
    ``_on_workspace_switch_requested``; relates to STORY-053's declared in-scope workspace
    switcher wiring.
    """
    # Arrange
    harness = make_harness()

    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        _workspace_switcher_task_editor_button(harness), Qt.MouseButton.LeftButton
    )

    # Assert
    assert harness.workspace.switch_calls == [("task_editor", None)]


def test_running_pill_click_switches_to_benchmark_progress(
    make_harness: Callable[..., MainWindowHarness], qtbot: QtBot
) -> None:
    """Given a run is non-terminal so the running pill is visible, when the user clicks it,
    then the controller switches to the Benchmark workspace with a ``progress``-focus hint.

    Given/When/Then: closes a `just coverage-layers` gap on ``_on_running_pill_clicked``.
    """
    # Arrange
    harness = make_harness()
    harness.event_bus.emit(SIGNAL_RUN_STARTED, _make_run_started_event())

    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        _running_pill(harness), Qt.MouseButton.LeftButton
    )

    # Assert
    assert harness.workspace.switch_calls == [("benchmark", WorkspaceHint(focus_widget="progress"))]


def test_settings_action_click_invokes_the_optional_callback(
    make_harness: Callable[..., MainWindowHarness], qtbot: QtBot
) -> None:
    """Given the shell was constructed with a ``settings_requested`` callback, when the user
    clicks the Settings action, then that callback is invoked exactly once.

    Given/When/Then: closes a `just coverage-layers` gap on ``_on_settings_requested``; a
    plain incidental-handler test (not a separately numbered STORY-053 acceptance criterion --
    the Settings dialog itself is a later story's scope per STORY-053's "Out of scope").
    """
    # Arrange
    harness = make_harness()

    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        _settings_action(harness), Qt.MouseButton.LeftButton
    )

    # Assert
    assert harness.settings_requested_calls == [None]


def test_about_action_click_invokes_the_optional_callback(
    make_harness: Callable[..., MainWindowHarness], qtbot: QtBot
) -> None:
    """Given the shell was constructed with an ``about_requested`` callback, when the user
    clicks the About action, then that callback is invoked exactly once.

    Given/When/Then: closes a `just coverage-layers` gap on ``_on_about_requested``; a plain
    incidental-handler test (not a separately numbered STORY-053 acceptance criterion -- the
    About dialog itself is owned by STORY-070 per STORY-053's "Out of scope").
    """
    # Arrange
    harness = make_harness()
    about_action = cast(
        "QPushButton", harness.shell.menu_bar.findChild(QPushButton, "about_menu_button")
    )

    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        about_action, Qt.MouseButton.LeftButton
    )

    # Assert
    assert harness.about_requested_calls == [None]
