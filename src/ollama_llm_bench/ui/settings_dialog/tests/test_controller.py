"""Tests for ``SettingsController``/``ProvidersTabController`` and the dialog
shell factory (STORY-066-AC-6, AC-7, AC-8).
"""

from typing import cast

import msgspec
from PySide6.QtCore import QAbstractTableModel
from PySide6.QtWidgets import QLabel
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.adapters.qt_table_models.models import ProviderTableRow
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    InferenceTestOutcome,
    InferenceTestResult,
    ProviderTestStatus,
    ReadinessState,
)
from ollama_llm_bench.backend.events import SIGNAL_APP_READINESS_CHANGED, AppReadinessChangedEvent
from ollama_llm_bench.ui.settings_dialog._internal.controller import SettingsController
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.controller import (
    ProvidersTabController,
)
from ollama_llm_bench.ui.settings_dialog.api import (
    SettingsDialogCollaborators,
    make_settings_dialog,
)
from ollama_llm_bench.ui.settings_dialog.models import DialogChromeViewModel
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway
from ollama_llm_bench.ui.settings_dialog.tests.conftest import PROVIDER_A, FakeEventBus


class _RowsExposingModel:
    """Structural cast target for the table model's public ``rows`` property
    (see ``providers_tab/health_auth_delegate.py``'s equivalent)."""

    rows: tuple[ProviderTableRow, ...]


def _rows(model: QAbstractTableModel) -> tuple[ProviderTableRow, ...]:
    return cast("_RowsExposingModel", model).rows


class _FakeChromeApplier:
    """A minimal ``_ChromeApplier`` test double -- records every chrome push."""

    def __init__(self) -> None:
        self.applied: list[DialogChromeViewModel] = []

    def apply_chrome(self, chrome: DialogChromeViewModel) -> None:
        self.applied.append(chrome)


# ---------------------------------------------------------------------------
# STORY-066-AC-6
# ---------------------------------------------------------------------------


def test_test_connection_probes_working_copy() -> None:
    """Proves: STORY-066-AC-6

    Covers: EC-PROV-5

    Given the user clicks Test connection on a provider row, when the probe
    runs, then it calls ``SettingsGateway.test_provider`` against the row's
    in-memory working copy (never the persisted value) and paints the
    resulting status onto the row's health dot.
    """
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    controller = ProvidersTabController(
        gateway=gateway, event_bus=FakeEventBus(), notifications=FakeNotificationService()
    )
    controller.reload()
    gateway.set_test_provider_result(
        InferenceTestResult(
            outcome=InferenceTestOutcome.SUCCESS,
            provider_id=PROVIDER_A.provider_id,
            model_name="unknown",
            tested_at=0,
        )
    )
    # Act
    controller.on_test_clicked(0)
    # Assert: called against the working copy's provider_id, reachability-only (empty model)
    assert gateway.recorded_test_provider_calls == [(PROVIDER_A.provider_id, "")]
    assert _rows(controller.table_model)[0].health is ProviderTestStatus.READY


def test_test_connection_maps_auth_failure_to_missing_env() -> None:
    """Proves: STORY-066-AC-6

    An ``AUTH_FAILED`` outcome paints the row's health dot ``MISSING_ENV``.
    """
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    controller = ProvidersTabController(
        gateway=gateway, event_bus=FakeEventBus(), notifications=FakeNotificationService()
    )
    controller.reload()
    gateway.set_test_provider_result(
        InferenceTestResult(
            outcome=InferenceTestOutcome.AUTH_FAILED,
            provider_id=PROVIDER_A.provider_id,
            model_name="unknown",
            tested_at=0,
        )
    )
    # Act
    controller.on_test_clicked(0)
    # Assert
    assert _rows(controller.table_model)[0].health is ProviderTestStatus.MISSING_ENV


def test_test_connection_gate_busy_notifies_and_leaves_health_unchanged() -> None:
    """Proves: STORY-066-AC-6

    A ``GATE_BUSY`` outcome (the probe never ran) surfaces a warning toast and
    leaves the row's health dot at its previous value.
    """
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    notifications = FakeNotificationService()
    controller = ProvidersTabController(
        gateway=gateway, event_bus=FakeEventBus(), notifications=notifications
    )
    controller.reload()
    gateway.set_test_provider_result(
        InferenceTestResult(
            outcome=InferenceTestOutcome.GATE_BUSY,
            provider_id=PROVIDER_A.provider_id,
            model_name="unknown",
            tested_at=0,
        )
    )
    # Act
    controller.on_test_clicked(0)
    # Assert
    assert notifications.warning_calls
    assert _rows(controller.table_model)[0].health is PROVIDER_A.last_probe_status


# ---------------------------------------------------------------------------
# STORY-066-AC-7
# ---------------------------------------------------------------------------


def test_auto_check_on_open_requests_probe_all() -> None:
    """Proves: STORY-066-AC-7

    Given the Settings dialog opens, when it enters its Opening state, then
    it issues a ``SettingsGateway.probe_all()`` request.
    """
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    providers_controller = ProvidersTabController(
        gateway=gateway, event_bus=FakeEventBus(), notifications=FakeNotificationService()
    )
    controller = SettingsController(
        gateway=gateway, event_bus=FakeEventBus(), providers_controller=providers_controller
    )
    # Act
    controller.load()
    # Assert
    assert gateway.recorded_probe_all_calls == 1
    assert providers_controller.table_model.rowCount() == 1


def test_readiness_refresh_repaints_health_from_fresh_gateway_read() -> None:
    """Proves: STORY-066-AC-7

    Given a readiness probe resolves, when ``_app_readiness_changed`` fires,
    then the row's health dot repaints from a fresh
    ``SettingsGateway.list_providers()`` read.
    """
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    bus = FakeEventBus()
    providers_controller = ProvidersTabController(
        gateway=gateway, event_bus=bus, notifications=FakeNotificationService()
    )
    controller = SettingsController(
        gateway=gateway, event_bus=bus, providers_controller=providers_controller
    )
    controller.bind_view(_FakeChromeApplier())
    controller.load()
    assert _rows(providers_controller.table_model)[0].health is ProviderTestStatus.UNTESTED
    # Act: the provider now reports READY in the persisted catalog
    ready_provider = msgspec.structs.replace(PROVIDER_A, last_probe_status=ProviderTestStatus.READY)
    gateway.set_providers((ready_provider,))
    bus.emit(
        SIGNAL_APP_READINESS_CHANGED,
        AppReadinessChangedEvent(
            overall=ReadinessState.READY,
            per_provider=(),
            embedding_reachable=True,
            checked_at="2026-07-21T00:00:00Z",
        ),
    )
    # Assert
    assert _rows(providers_controller.table_model)[0].health is ProviderTestStatus.READY


def test_readiness_refresh_repaints_embedding_diagnostic(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-066-AC-7

    Given a readiness probe resolves, when ``_app_readiness_changed`` fires,
    then the embedding section's diagnostic repaints from the snapshot's
    ``embedding_reachable`` flag.
    """
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    bus = FakeEventBus()
    collaborators = SettingsDialogCollaborators(
        gateway=gateway,
        event_bus=bus,
        native_pickers=FakeNativePickers(),
        clipboard=mocker.Mock(spec=Clipboard),
        file_system_actions=mocker.Mock(spec=FileSystemActions),
        notifications=FakeNotificationService(),
    )
    dialog = make_settings_dialog(collaborators=collaborators)
    qtbot.addWidget(dialog)
    diagnostic_label = cast(
        "QLabel",
        dialog.findChild(QLabel, "settings_dialog.embedding_section.diagnostic"),
    )
    # Act
    bus.emit(
        SIGNAL_APP_READINESS_CHANGED,
        AppReadinessChangedEvent(
            overall=ReadinessState.READY,
            per_provider=(),
            embedding_reachable=False,
            checked_at="2026-07-21T00:00:00Z",
        ),
    )
    # Assert
    assert diagnostic_label.text() == "✗ embedding unreachable"


# ---------------------------------------------------------------------------
# STORY-066-AC-8
# ---------------------------------------------------------------------------


def test_settings_dialog_constructs_and_shows_with_no_error_logs(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-066-AC-8

    Given the dialog is constructed via its own factory function with a fake
    ``SettingsGateway`` (and fakes for the declared collaborators) and
    mounted under ``qtbot``, when it is shown, then no exception is raised,
    the dialog reports ``isVisible()``, and no ``error``/``critical``-level
    ``structlog`` record is captured.
    """
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    gateway.set_readiness(
        AppReadinessSnapshot(
            overall=ReadinessState.READY, per_provider=(), embedding_reachable=True
        )
    )
    collaborators = SettingsDialogCollaborators(
        gateway=gateway,
        event_bus=FakeEventBus(),
        native_pickers=FakeNativePickers(),
        clipboard=mocker.Mock(spec=Clipboard),
        file_system_actions=mocker.Mock(spec=FileSystemActions),
        notifications=FakeNotificationService(),
    )
    # Act
    with structlog.testing.capture_logs() as logs:
        dialog = make_settings_dialog(collaborators=collaborators)
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)
    # Assert
    assert dialog.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)
