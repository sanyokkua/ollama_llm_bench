"""Integration proof for the NOT_READY launch path (STORY-081-AC-2, EC-M-5).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-M_app_lifecycle.md`` section
5 -- when every operability check fails, the aggregate readiness resolves to
``NOT_READY``: "The status bar shows the not-ready state; run start is gated. The user
interface remains navigable." and "A problem that blocks the user is surfaced twice: in
the status bar, and through an explanatory modal dialog... The user must never reach an
enabled run-start affordance for an environment that cannot run a benchmark."

Earlier STORY-081 work proved the Start-button gate and the explanatory-modal trigger at
the unit level, against a harness that stands in for the real application. This module is
the integration-tier proof required by ``06_EDGE_CASE_TO_TEST_MAPPING.md``:267 -- it drives
the real, fully composed application (``compose.build_app``) through a genuinely
totally-failed readiness probe and asserts on the real Start button, the real status-bar
health dot, the real ``NotificationService.show_error`` call, and the real workspace
switcher, exactly as EC-M-1/2/3's ``test_launch_*.py`` and EC-M-4's
``test_launch_crash_recovery.py`` do for their own launch scenarios.

**How the total failure is forced.** ``build_app`` takes no readiness parameter, so
``ollama_llm_bench.compose.make_readiness_service`` is patched with a fake
``ReadinessService`` (structurally satisfying the Protocol -- ``backend/readiness/
protocols.py``) that starts ``CHECKING`` (matching the real service's own
construction-time invariant) and, on its one and only ``probe_all()`` call, transitions its
cached snapshot to ``NOT_READY`` and emits ``_app_readiness_changed`` on the real, shared
``EventBus`` handed to it by ``build_app`` -- the same bus the real application's widgets
subscribe to (``adapters/ui_gateways/_internal/main_window/gateway.py`` -- the UI learns
readiness only from the bus, never by polling). Starting ``CHECKING`` rather than
already-``NOT_READY`` is load-bearing, not cosmetic: ``MainWindowController.
_on_readiness_changed`` shows the explanatory modal only on the edge *into* ``NOT_READY``,
so a fake seeded already-``NOT_READY`` would silently suppress it (see
``_TotalFailureReadinessService``'s own docstring). The fake never performs a probe of its
own; that mechanic is already proven by ``backend/readiness``'s own contract-test suite.
This test module proves only the UI's reaction to a NOT_READY *result*.

**Two different provider types, matched exactly.** The fake's cached snapshot carries
``ProviderHealth`` (``backend/domain/models.py`` -- ``provider_id``, ``reachable``,
``discovery_supported``, ``model_count``, ``last_probe_ms``, ``probed_at``, optional
``last_error``); the event it emits carries ``ProviderHealthSummary``
(``backend/events/models.py`` -- no ``last_probe_ms``, no ``probed_at``) plus a required
``checked_at`` on the event itself. Both say ``reachable=False``, and the snapshot also
carries ``embedding_reachable=False`` -- omitting either would leave the real aggregation
this fake bypasses unable to resolve ``NOT_READY``.

**Why every test uses ``build_real_app_without_enabled_providers``.** That fixture's
app-data root has every builtin provider present but disabled, so nothing the real
application does on its own (e.g. the Settings dialog's embedding bootstrap search, not
exercised here) can reach a network socket -- see that fixture's own docstring in
``tests/integration/conftest.py``. This module's own NOT_READY result comes entirely from
the patched fake, not from the disabled providers; the fixture is chosen only to keep every
test in this suite offline-safe by construction, matching the existing menu-dialog suite's
precedent.

**Why ``NotificationService.show_error`` is mocked rather than driven for real.** A real
``QMessageBox.critical(...)`` call blocks the calling thread inside a nested Qt event loop
until dismissed. This suite's ``conftest.py`` installs an app-wide event filter that
auto-dismisses that modal for every test built through this fixture (so a real modal no
longer hangs the suite), but that filter exists precisely because letting the modal block
is not something a test should rely on to prove its own behaviour. Capturing the real
``NotificationService`` instance ``compose.py`` constructs (via the same
``mocker.patch(...); side_effect=<wraps the real factory>`` idiom
``test_compose_build_app.py`` uses for ``make_readiness_service``) and mocking its
``show_error`` method lets the modal-shown test assert on the exact call
(``blocking=True``) without ever entering ``QDialog.exec()``.
"""

from collections.abc import Callable
from typing import Final, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.notification_service import (
    NotificationService,
    make_notification_service,
)
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ProviderHealth,
    ProviderId,
    ReadinessState,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_READINESS_CHANGED,
    AppReadinessChangedEvent,
    EventBus,
    ProviderHealthSummary,
)
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.shared._internal.health_dot import HealthDotWidget

_WAIT_TIMEOUT_MS: Final[int] = 3000
_NOT_READY_HEALTH_LABEL: Final[str] = "Not ready"
_FAILED_PROVIDER_ID: Final[ProviderId] = "provider-1"
_CHECKED_AT: Final = "2026-01-01T00:00:00Z"

_FAILED_PROVIDER_HEALTH: Final[ProviderHealth] = ProviderHealth(
    provider_id=_FAILED_PROVIDER_ID,
    reachable=False,
    discovery_supported=True,
    model_count=None,
    last_probe_ms=0,
    probed_at=0,
)

_CHECKING_SNAPSHOT: Final[AppReadinessSnapshot] = AppReadinessSnapshot(
    overall=ReadinessState.CHECKING,
    per_provider=(),
    embedding_reachable=False,
)

_NOT_READY_SNAPSHOT: Final[AppReadinessSnapshot] = AppReadinessSnapshot(
    overall=ReadinessState.NOT_READY,
    per_provider=(_FAILED_PROVIDER_HEALTH,),
    embedding_reachable=False,
)

_NOT_READY_EVENT: Final[AppReadinessChangedEvent] = AppReadinessChangedEvent(
    overall=ReadinessState.NOT_READY,
    per_provider=(
        ProviderHealthSummary(
            provider_id=_FAILED_PROVIDER_ID,
            reachable=False,
            discovery_supported=True,
            model_count=None,
        ),
    ),
    embedding_reachable=False,
    checked_at=_CHECKED_AT,
)


class _TotalFailureReadinessService:
    """Fake ``ReadinessService`` whose first probe reports a totally-failed batch (EC-M-5).

    Satisfies ``backend.readiness.ReadinessService`` structurally. Starts ``CHECKING`` --
    matching the real service's own construction-time invariant
    (``make_readiness_service``'s ``@icontract.ensure``) -- so the one and only
    ``probe_all()`` call genuinely *transitions* the cached snapshot into ``NOT_READY``
    rather than starting there. That transition matters beyond realism: the real
    ``MainWindowController._on_readiness_changed`` shows the explanatory modal only on
    the edge into ``NOT_READY`` (``was_not_ready`` guard), so a fake that started
    already-``NOT_READY`` would silently suppress the very modal this module proves --
    confirmed by reproducing that exact false pass while developing this fake. ``probe_all``
    emits ``_app_readiness_changed`` on the real, injected ``EventBus`` -- the only channel
    the real UI ever learns readiness from.
    """

    def __init__(self, *, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._snapshot = _CHECKING_SNAPSHOT

    def snapshot(self) -> AppReadinessSnapshot:
        """Return the most recently recomputed snapshot (``CHECKING`` until the first probe)."""
        return self._snapshot

    def probe_all(self) -> AppReadinessSnapshot:
        """Transition the cached snapshot to NOT_READY and emit the matching event."""
        self._snapshot = _NOT_READY_SNAPSHOT
        self._event_bus.emit(SIGNAL_APP_READINESS_CHANGED, _NOT_READY_EVENT)
        return self._snapshot

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        """Return the fixed failed-provider health, regardless of which provider is asked."""
        return _FAILED_PROVIDER_HEALTH

    def record_embedding_capability_result(self, *, reachable: bool) -> None:
        """No-op: this scenario has no embedding-capability check to record."""


def _install_total_failure_readiness(mocker: MockerFixture) -> None:
    """Patch ``compose.make_readiness_service`` so the next ``build_app`` call wires
    ``_TotalFailureReadinessService`` in place of the real service, forwarding the real
    factory's ``event_bus`` kwarg so the fake emits on the same bus the built application's
    widgets subscribe to."""

    def _factory(**kwargs: object) -> ReadinessService:
        event_bus = cast("EventBus", kwargs["event_bus"])
        return _TotalFailureReadinessService(event_bus=event_bus)

    mocker.patch("ollama_llm_bench.compose.make_readiness_service", side_effect=_factory)


def _health_dot(handle: AppHandle) -> HealthDotWidget:
    """Locate the status bar's health dot -- copied from ``ui/main_window/_internal/tests/
    test_controller.py``'s identical helper (no importable shared home exists). The dot is
    rebuilt on every render (``StatusBarWidget._rebuild_health_dot``), so callers must
    re-locate it after a state change rather than caching the returned widget."""
    health_region = cast("QWidget", handle.window.findChild(QWidget, "health_region"))
    layout = health_region.layout()
    assert layout is not None
    item = layout.itemAt(0)
    assert item is not None
    dot = cast("HealthDotWidget", item.widget())
    assert dot is not None
    return dot


def _wait_for_not_ready_health_dot(handle: AppHandle, qtbot: QtBot) -> None:
    """Block until the status-bar health dot reflects the delivered NOT_READY event."""
    qtbot.waitUntil(
        lambda: _health_dot(handle).text_label == _NOT_READY_HEALTH_LABEL,
        timeout=_WAIT_TIMEOUT_MS,
    )


@pytest.mark.allow_qt_warnings  # offscreen-only: the real NOT_READY QMessageBox this test
# lets fire (auto-dismissed by this directory's conftest event filter) resizes a widget
# before the offscreen platform plugin has a native window to hint, which logs "This plugin
# does not support propagateSizeHints()" -- the identical pre-existing offscreen-plugin
# behaviour test_menu_opens_dialogs.py and test_launch_abort_modal_quits.py already carry
# this same marker for, not a defect in this test or the production dialog wiring.
def test_readiness_probe_total_failure_resolves_not_ready_and_gates_run_start(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    mocker: MockerFixture,
    qtbot: QtBot,
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-2

    Covers EC-M-5. When every operability check fails, readiness resolves to
    NOT_READY and the Start button is disabled, so the user never reaches an
    enabled run-start affordance for an environment that cannot run a benchmark.
    """
    # Arrange
    _install_total_failure_readiness(mocker)

    # Act
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    handle.window.show()
    start_button = cast(
        "QPushButton", handle.window.findChild(QPushButton, "new_benchmark.start_button")
    )
    qtbot.waitUntil(lambda: start_button.isEnabled() is False, timeout=_WAIT_TIMEOUT_MS)

    # Assert
    assert start_button.isEnabled() is False

    # Cleanup
    drain_task_runner_deliveries(handle)


@pytest.mark.allow_qt_warnings  # offscreen-only: see the identical marker on
# test_readiness_probe_total_failure_resolves_not_ready_and_gates_run_start above.
def test_readiness_probe_total_failure_shows_not_ready_in_the_status_bar(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    mocker: MockerFixture,
    qtbot: QtBot,
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-2

    Covers EC-M-5. The failure is surfaced in the status bar.
    """
    # Arrange
    _install_total_failure_readiness(mocker)

    # Act
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    handle.window.show()
    _wait_for_not_ready_health_dot(handle, qtbot)

    # Assert
    assert _health_dot(handle).text_label == _NOT_READY_HEALTH_LABEL

    # Cleanup
    drain_task_runner_deliveries(handle)


def test_readiness_probe_total_failure_shows_an_explanatory_modal(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    mocker: MockerFixture,
    qtbot: QtBot,
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-2

    Covers EC-M-5. The failure is surfaced through an explanatory modal as well
    as the status bar.
    """
    # Arrange
    _install_total_failure_readiness(mocker)
    captured_notifications: list[NotificationService] = []

    def _capture_notification_service(**kwargs: object) -> NotificationService:
        service = make_notification_service(**kwargs)  # type: ignore[arg-type]  # forwarding real build_app kwargs
        captured_notifications.append(service)
        return service

    mocker.patch(
        "ollama_llm_bench.compose.make_notification_service",
        side_effect=_capture_notification_service,
    )

    # Act
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    show_error_spy = mocker.patch.object(captured_notifications[0], "show_error")
    handle.window.show()
    qtbot.waitUntil(lambda: show_error_spy.call_count >= 1, timeout=_WAIT_TIMEOUT_MS)

    # Assert
    show_error_spy.assert_called_once()
    assert show_error_spy.call_args.kwargs["blocking"] is True

    # Cleanup
    drain_task_runner_deliveries(handle)


@pytest.mark.allow_qt_warnings  # offscreen-only: see the identical marker on
# test_readiness_probe_total_failure_resolves_not_ready_and_gates_run_start above.
def test_user_interface_stays_navigable_when_not_ready(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    mocker: MockerFixture,
    qtbot: QtBot,
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-2

    Covers EC-M-5. A not-ready environment gates run start but never blocks
    navigation -- the window stays visible and the workspace switch still works.
    """
    # Arrange
    _install_total_failure_readiness(mocker)

    # Act
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    handle.window.show()
    _wait_for_not_ready_health_dot(handle, qtbot)
    task_editor_button = cast(
        "QPushButton", handle.window.findChild(QPushButton, "workspace_task_editor_button")
    )
    qtbot.mouseClick(task_editor_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs

    # Assert
    assert handle.window.isVisible() is True
    assert task_editor_button.isChecked() is True

    # Cleanup
    drain_task_runner_deliveries(handle)
