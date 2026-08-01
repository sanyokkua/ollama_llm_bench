"""Tests for ``SettingsController``/``ProvidersTabController`` and the dialog
shell factory (STORY-066-AC-6, AC-7, AC-8; extended by STORY-067).
"""

from pathlib import Path
from typing import TYPE_CHECKING, cast
import uuid

import msgspec
from PySide6.QtCore import QAbstractTableModel
from PySide6.QtWidgets import QLabel, QPushButton, QTabWidget
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
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.events import SIGNAL_APP_READINESS_CHANGED, AppReadinessChangedEvent
from ollama_llm_bench.ui.settings_dialog._internal.controller import SettingsController
from ollama_llm_bench.ui.settings_dialog._internal.general_tab.controller import (
    GeneralTabController,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.controller import (
    ProvidersTabController,
)
from ollama_llm_bench.ui.settings_dialog.api import (
    SettingsDialogCollaborators,
    make_settings_dialog,
)
from ollama_llm_bench.ui.settings_dialog.models import (
    DialogChromeViewModel,
    GeneralFieldState,
    PreviewGroup,
    ProviderImportPreview,
    ProviderImportResult,
    SettingsImportPreview,
    SettingsImportPreviewRow,
    SettingsImportResult,
    Severity,
    ValidationFinding,
)
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway
from ollama_llm_bench.ui.settings_dialog.tests.conftest import PROVIDER_A, FakeEventBus

if TYPE_CHECKING:
    from ollama_llm_bench.ui.settings_dialog._internal.view import SettingsDialogView


class _RowsExposingModel:
    """Structural cast target for the table model's public ``rows`` property
    (see ``providers_tab/health_auth_delegate.py``'s equivalent)."""

    rows: tuple[ProviderTableRow, ...]


def _rows(model: QAbstractTableModel) -> tuple[ProviderTableRow, ...]:
    return cast("_RowsExposingModel", model).rows


def _controller_of(dialog: object) -> SettingsController:
    """STORY-067 test helper: reach the constructed ``SettingsController``
    behind a ``make_settings_dialog`` ``QDialog`` (its public return type
    carries no ``_controller`` attribute -- this cast is test-only)."""
    controller = cast("SettingsDialogView", dialog)._controller
    assert controller is not None
    return controller


class _FakeChromeApplier:
    """A minimal ``_ChromeApplier`` test double -- records every chrome push."""

    def __init__(self) -> None:
        self.applied: list[DialogChromeViewModel] = []
        self.pushed_field_states: list[tuple[GeneralFieldState, ...]] = []

    def apply_chrome(self, chrome: DialogChromeViewModel) -> None:
        self.applied.append(chrome)

    def push_general_field_states(self, states: tuple[GeneralFieldState, ...]) -> None:
        self.pushed_field_states.append(states)


def _make_collaborators(
    *,
    gateway: FakeSettingsGateway,
    event_bus: FakeEventBus | None = None,
    mocker: MockerFixture,
) -> SettingsDialogCollaborators:
    """Shared STORY-067 test helper: the full ``SettingsDialogCollaborators``
    bundle a fake ``SettingsGateway`` needs to drive ``make_settings_dialog``."""
    return SettingsDialogCollaborators(
        gateway=gateway,
        event_bus=event_bus if event_bus is not None else FakeEventBus(),
        native_pickers=FakeNativePickers(),
        clipboard=mocker.Mock(spec=Clipboard),
        file_system_actions=mocker.Mock(spec=FileSystemActions),
        notifications=FakeNotificationService(),
    )


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


def test_auto_check_on_open_requests_probe_all(mocker: MockerFixture) -> None:
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
        collaborators=_make_collaborators(gateway=gateway, mocker=mocker),
        providers_controller=providers_controller,
        general_tab_controller=GeneralTabController(gateway=gateway),
    )
    # Act
    controller.load()
    # Assert
    assert gateway.recorded_probe_all_calls == 1
    assert providers_controller.table_model.rowCount() == 1


def test_readiness_refresh_repaints_health_from_fresh_gateway_read(mocker: MockerFixture) -> None:
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
        collaborators=_make_collaborators(gateway=gateway, event_bus=bus, mocker=mocker),
        providers_controller=providers_controller,
        general_tab_controller=GeneralTabController(gateway=gateway),
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


# ---------------------------------------------------------------------------
# STORY-067
# ---------------------------------------------------------------------------


def test_save_writes_providers_and_settings_atomically_then_emits_events_and_cleans(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-067-AC-3

    Given a dirty dialog with no hard error, when Save Changes is clicked, then
    both stores are written through the Gateway and, on commit,
    `_provider_registry_reloaded` and `_app_settings_changed` are emitted and
    the dialog becomes clean.
    """
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    gateway.set_setting_value("ui.theme", "system")
    bus = FakeEventBus()
    dialog = make_settings_dialog(
        collaborators=_make_collaborators(gateway=gateway, event_bus=bus, mocker=mocker)
    )
    qtbot.addWidget(dialog)
    dialog.show()
    controller = _controller_of(dialog)

    controller._general_tab_controller.set_value("ui.theme", "dark")
    controller.on_save_clicked()

    assert gateway.save_all_calls[-1][0] == (PROVIDER_A,)
    assert gateway.save_all_calls[-1][1]["ui.theme"] == "dark"
    assert bus.emitted_signal_names().count("_provider_registry_reloaded") == 1
    assert bus.emitted_signal_names().count("_app_settings_changed") == 1
    assert controller.is_dirty is False


def test_save_failure_leaves_dialog_dirty_and_shows_error(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-067 atomic-Save spec-conformance fix.

    A ``save_all`` failure surfaces an error notification, writes nothing
    (proven at the Fake level by ``test_fake_gateway.py``), and leaves the
    dialog dirty -- mirroring the error handling Reset now also carries.
    """
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    gateway.raise_on_next_save_all(PersistenceError(message="disk full"))
    notifications = FakeNotificationService()
    dialog = make_settings_dialog(
        collaborators=SettingsDialogCollaborators(
            gateway=gateway,
            event_bus=FakeEventBus(),
            native_pickers=FakeNativePickers(),
            clipboard=mocker.Mock(spec=Clipboard),
            file_system_actions=mocker.Mock(spec=FileSystemActions),
            notifications=notifications,
        )
    )
    qtbot.addWidget(dialog)
    controller = _controller_of(dialog)
    controller._general_tab_controller.set_value("ui.theme", "dark")
    # The dialog is left dirty by design (the assertion below); pytest-qt's
    # automatic teardown calls dialog.close() -> reject() -> on_close_requested(),
    # which would otherwise open a real, blocking QMessageBox with no user to
    # dismiss it. Discard silently so teardown does not hang.
    mocker.patch.object(controller, "_confirm_discard_changes", return_value=True)

    controller.on_save_clicked()

    assert notifications.error_calls
    assert controller.is_dirty is True


def test_save_writes_nothing_when_a_hard_error_is_present(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-067-AC-2

    A hard-error finding blocks Save entirely -- nothing is written.
    """
    gateway = FakeSettingsGateway()
    bus = FakeEventBus()
    dialog = make_settings_dialog(
        collaborators=_make_collaborators(gateway=gateway, event_bus=bus, mocker=mocker)
    )
    qtbot.addWidget(dialog)
    controller = _controller_of(dialog)
    # The field cleared below leaves the dialog dirty with a hard error;
    # pytest-qt's automatic teardown calls dialog.close() -> reject() ->
    # on_close_requested(), which would otherwise open a real, blocking
    # QMessageBox with no user to dismiss it. Discard silently so teardown
    # does not hang.
    mocker.patch.object(controller, "_confirm_discard_changes", return_value=True)

    controller._general_tab_controller.set_value("benchmark.min_timeout_seconds", "")
    controller.on_save_clicked()

    assert gateway.replace_providers_calls == []
    assert gateway.upsert_settings_calls == []


def test_reset_confirmed_wipes_and_reseeds_atomically(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-067-AC-5

    Confirming Reset to Defaults runs the wipe-and-reseed transaction,
    discarding unsaved edits, and emits both events.
    """
    gateway = FakeSettingsGateway()
    bus = FakeEventBus()
    dialog = make_settings_dialog(
        collaborators=_make_collaborators(gateway=gateway, event_bus=bus, mocker=mocker)
    )
    qtbot.addWidget(dialog)
    controller = _controller_of(dialog)
    controller._general_tab_controller.set_value("ui.theme", "dark")  # unsaved edit

    fake_confirmation_dialog = mocker.Mock(confirmed=True)
    mocker.patch(
        "ollama_llm_bench.ui.settings_dialog._internal.controller.make_reset_confirmation_dialog",
        return_value=fake_confirmation_dialog,
    )

    controller.on_reset_clicked()

    assert len(gateway.reset_to_defaults_calls) == 1
    # discarded, reset to default (the Fake clears settings; the General tab's
    # reload() falls through to its own known default for an absent key)
    assert controller._general_tab_controller.values_for_save()["ui.theme"] == "system"
    assert bus.emitted_signal_names().count("_provider_registry_reloaded") == 1
    assert bus.emitted_signal_names().count("_app_settings_changed") == 1


def test_reset_failure_leaves_dialog_dirty_and_shows_error(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-067 atomic-Reset spec-conformance fix.

    A ``reset_to_defaults`` failure surfaces an error notification instead of
    crashing (Reset previously had no error handling at all) and leaves the
    dialog's unsaved edits intact.
    """
    gateway = FakeSettingsGateway()
    gateway.raise_on_next_reset_to_defaults(PersistenceError(message="disk full"))
    notifications = FakeNotificationService()
    dialog = make_settings_dialog(
        collaborators=SettingsDialogCollaborators(
            gateway=gateway,
            event_bus=FakeEventBus(),
            native_pickers=FakeNativePickers(),
            clipboard=mocker.Mock(spec=Clipboard),
            file_system_actions=mocker.Mock(spec=FileSystemActions),
            notifications=notifications,
        )
    )
    qtbot.addWidget(dialog)
    controller = _controller_of(dialog)
    controller._general_tab_controller.set_value("ui.theme", "dark")
    fake_confirmation_dialog = mocker.Mock(confirmed=True)
    mocker.patch(
        "ollama_llm_bench.ui.settings_dialog._internal.controller.make_reset_confirmation_dialog",
        return_value=fake_confirmation_dialog,
    )
    # The dialog is left dirty by design (the assertion below); pytest-qt's
    # automatic teardown calls dialog.close() -> reject() -> on_close_requested(),
    # which would otherwise open a real, blocking QMessageBox with no user to
    # dismiss it. Discard silently so teardown does not hang.
    mocker.patch.object(controller, "_confirm_discard_changes", return_value=True)

    controller.on_reset_clicked()

    assert notifications.error_calls
    assert controller._general_tab_controller.values_for_save()["ui.theme"] == "dark"


def test_close_when_dirty_opens_discard_confirmation_and_cancel_keeps_dialog_open(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-067-AC-6

    A dirty dialog's Close opens the Discard-changes confirmation; Cancel
    keeps the dialog open with the working copy intact.
    """
    gateway = FakeSettingsGateway()
    dialog = make_settings_dialog(collaborators=_make_collaborators(gateway=gateway, mocker=mocker))
    qtbot.addWidget(dialog)
    controller = _controller_of(dialog)
    controller._general_tab_controller.set_value("ui.theme", "dark")

    mocker.patch.object(controller, "_confirm_discard_changes", return_value=False)  # Cancel

    should_close = controller.on_close_requested()

    assert should_close is False
    assert controller._general_tab_controller.values_for_save()["ui.theme"] == "dark"


def test_close_when_clean_closes_immediately(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-067-AC-6

    A clean dialog's Close dismisses it immediately, no confirmation shown.
    """
    gateway = FakeSettingsGateway()
    dialog = make_settings_dialog(collaborators=_make_collaborators(gateway=gateway, mocker=mocker))
    qtbot.addWidget(dialog)
    controller = _controller_of(dialog)

    should_close = controller.on_close_requested()

    assert should_close is True


def test_import_applies_known_keys_and_skips_unknown_keys_on_confirm(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-067-AC-4

    Covers: EC-SET-2

    Given an import file whose preview carries one recognised key (grouped
    Changed) and an "unrecognised key ignored" finding for an unknown key,
    when the user confirms the Import preview, then only the recognised
    key's resolved value reaches the Gateway's ``apply_settings_import`` call
    -- the unknown key never reaches persistence -- and
    `_app_settings_changed` is emitted exactly once.
    """
    gateway = FakeSettingsGateway()
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result(("settings.yaml",))
    bus = FakeEventBus()
    dialog = make_settings_dialog(
        collaborators=_make_collaborators(gateway=gateway, event_bus=bus, mocker=mocker)
    )
    qtbot.addWidget(dialog)
    controller = _controller_of(dialog)
    controller._native_pickers = native_pickers

    preview = SettingsImportPreview(
        rows=(
            SettingsImportPreviewRow(
                setting_key="benchmark.retry_count",
                current_value="3",
                imported_value="5",
                group=PreviewGroup.CHANGED,
            ),
        ),
        findings=(
            ValidationFinding(
                severity=Severity.SOFT_INFO,
                target="ui.old_theme",
                message="Unrecognised key — ignored",
            ),
        ),
        resolved_values={"benchmark.retry_count": "5"},
        backend_preview=object(),
    )
    gateway.set_settings_import_preview(preview)
    gateway.set_settings_import_result(SettingsImportResult(applied_count=1, skipped_count=1))
    fake_preview_dialog = mocker.Mock(confirmed=True)
    mocker.patch(
        "ollama_llm_bench.ui.settings_dialog._internal.controller.make_settings_import_preview_dialog",
        return_value=fake_preview_dialog,
    )

    controller.on_import_clicked()

    assert gateway.upsert_settings_calls[-1] == {"benchmark.retry_count": "5"}
    assert bus.emitted_signal_names().count("_app_settings_changed") == 1


def test_settings_dialog_shows_general_tab_and_all_footer_buttons(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-067-AC-1

    The dialog mounts a General tab and shows the five footer buttons in the
    spec's button-ordering (side cluster, then Close, then Save Changes).
    """
    gateway = FakeSettingsGateway()
    dialog = make_settings_dialog(collaborators=_make_collaborators(gateway=gateway, mocker=mocker))
    qtbot.addWidget(dialog)
    dialog.show()

    tab_widget = cast("QTabWidget", dialog.findChild(QTabWidget))
    tab_labels = [tab_widget.tabText(i) for i in range(tab_widget.count())]
    assert tab_labels[1].startswith("General")

    assert dialog.findChild(QPushButton, "settings_dialog.reset_to_defaults_button") is not None
    assert dialog.findChild(QPushButton, "settings_dialog.import_button") is not None
    assert dialog.findChild(QPushButton, "settings_dialog.export_button") is not None
    assert dialog.findChild(QPushButton, "settings_dialog.close_button") is not None
    assert dialog.findChild(QPushButton, "settings_dialog.save_changes_button") is not None


_EXPECTED_EXPORT_FILE_COUNT = 2


def test_export_writes_both_settings_and_provider_catalog(
    qtbot: QtBot, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Proves: STORY-067 export-completeness spec-conformance fix
    (``description.md`` §7: the export carries "the provider catalog, the
    embedding selection, and every user-saved setting key").

    Given the user clicks Export…, when the export runs, then both the
    settings payload and the provider-catalog payload reach
    ``FileSystemActions.write_text_file`` -- Export no longer omits the
    provider catalog.
    """
    gateway = FakeSettingsGateway()
    gateway.set_export_settings_bytes(b"schema_version: 1\nkind: settings\n")
    gateway.set_export_providers_bytes(b"schema_version: 1\nkind: provider_config\n")
    settings_path = tmp_path / "ollama_bench_settings_2026-07-21.yaml"
    providers_path = tmp_path / "ollama_bench_settings_2026-07-21_providers.yaml"
    native_pickers = FakeNativePickers()
    native_pickers.set_save_result(str(settings_path))
    file_system_actions = mocker.Mock(spec=FileSystemActions)
    dialog = make_settings_dialog(
        collaborators=SettingsDialogCollaborators(
            gateway=gateway,
            event_bus=FakeEventBus(),
            native_pickers=native_pickers,
            clipboard=mocker.Mock(spec=Clipboard),
            file_system_actions=file_system_actions,
            notifications=FakeNotificationService(),
        )
    )
    qtbot.addWidget(dialog)
    controller = _controller_of(dialog)

    controller.on_export_clicked()

    assert file_system_actions.write_text_file.call_count == _EXPECTED_EXPORT_FILE_COUNT
    written = {
        call.kwargs["path"]: call.kwargs["content"]
        for call in file_system_actions.write_text_file.call_args_list
    }
    assert written[str(settings_path)] == "schema_version: 1\nkind: settings\n"
    assert written[str(providers_path)] == "schema_version: 1\nkind: provider_config\n"


def test_import_button_routes_exported_provider_config_file_back_through_provider_import(
    qtbot: QtBot, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Proves: STORY-067-AC-4

    Round-trips the sibling provider-catalog file Export… writes
    (``kind: provider_config``) back through the single footer Import…
    entry point: both real Export… files are written to disk, then the exact
    provider-catalog path is fed back into ``on_import_clicked``. The
    controller's ``_detect_import_kind`` reads the real file's
    ``kind: provider_config`` key and routes to the provider-import preview
    flow, not the settings flow -- closing the gap the second
    spec-conformance review flagged (an Export… sibling file no exposed
    control could re-import).
    """
    gateway = FakeSettingsGateway()
    settings_export_bytes = b"schema_version: 1\nkind: settings\nsettings: {}\n"
    provider_export_bytes = (
        b"schema_version: 1\nkind: provider_config\n"
        b"embedding:\n  provider_name: Ollama (local)\n  model_name: bge-m3\n"
        b"providers:\n  - name: Ollama (local)\n    type: openai_compatible\n"
        b"    base_url: http://localhost:11434/v1\n    enabled: true\n"
    )
    gateway.set_export_settings_bytes(settings_export_bytes)
    gateway.set_export_providers_bytes(provider_export_bytes)
    settings_path = tmp_path / "ollama_bench_settings_2026-07-21.yaml"
    providers_path = tmp_path / "ollama_bench_settings_2026-07-21_providers.yaml"
    native_pickers = FakeNativePickers()
    native_pickers.set_save_result(str(settings_path))
    file_system_actions = mocker.Mock(spec=FileSystemActions)
    file_system_actions.write_text_file.side_effect = lambda *, path, content: Path(
        path
    ).write_text(content, encoding="utf-8")
    notifications = FakeNotificationService()
    bus = FakeEventBus()
    dialog = make_settings_dialog(
        collaborators=SettingsDialogCollaborators(
            gateway=gateway,
            event_bus=bus,
            native_pickers=native_pickers,
            clipboard=mocker.Mock(spec=Clipboard),
            file_system_actions=file_system_actions,
            notifications=notifications,
        )
    )
    qtbot.addWidget(dialog)
    controller = _controller_of(dialog)
    controller.on_export_clicked()
    assert providers_path.read_text(encoding="utf-8") == provider_export_bytes.decode("utf-8")

    provider_preview = ProviderImportPreview(
        rows=(),
        embedding_provider_name=None,
        embedding_model_name=None,
        findings=(),
        backend_preview=object(),
    )
    gateway.set_provider_import_preview(provider_preview)
    gateway.set_provider_import_result(ProviderImportResult(applied_count=1, skipped_count=0))
    native_pickers.set_open_file_result((str(providers_path),))
    fake_preview_dialog = mocker.Mock(confirmed=True)
    mocker.patch(
        "ollama_llm_bench.ui.settings_dialog._internal.controller.make_provider_import_preview_dialog",
        return_value=fake_preview_dialog,
    )

    controller.on_import_clicked()

    assert notifications.info_calls[-1][0] == "Provider configuration imported"
    assert bus.emitted_signal_names().count("_provider_registry_reloaded") == 1


def test_providers_tab_mutation_immediately_enables_save_without_general_tab_edit(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-067 Providers-tab chrome-notification spec-conformance fix.

    Given a clean dialog, when a Providers-tab-only mutation occurs (toggling
    a row's enabled flag), then the dialog chrome (Save Changes enablement)
    updates immediately -- no unrelated General-tab edit is required first.
    """
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A,))
    dialog = make_settings_dialog(collaborators=_make_collaborators(gateway=gateway, mocker=mocker))
    qtbot.addWidget(dialog)
    dialog.show()
    controller = _controller_of(dialog)
    # The mutation below leaves the dialog dirty; pytest-qt's automatic
    # teardown calls dialog.close() -> reject() -> on_close_requested(),
    # which would otherwise open a real, blocking QMessageBox with no user to
    # dismiss it. Discard silently so teardown does not hang.
    mocker.patch.object(controller, "_confirm_discard_changes", return_value=True)
    save_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.save_changes_button")
    )
    assert not save_button.isEnabled()  # clean dialog, nothing to save yet

    controller.providers_controller.on_enabled_toggled(0)

    assert save_button.isEnabled()


def test_providers_tab_duplicate_name_mutation_immediately_disables_save(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-067 Providers-tab chrome-notification spec-conformance fix.

    Given two persisted providers already sharing a Name (a hard-error
    finding), when a Providers-tab-only mutation occurs (toggling a row's
    enabled flag, with no General-tab edit), then the dialog chrome updates
    immediately: the save-state indicator flips to dirty and Save Changes
    stays disabled by the duplicate-name hard error.
    """
    duplicate = msgspec.structs.replace(PROVIDER_A, provider_id=str(uuid.uuid4()))
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A, duplicate))
    dialog = make_settings_dialog(collaborators=_make_collaborators(gateway=gateway, mocker=mocker))
    qtbot.addWidget(dialog)
    dialog.show()
    save_state_label = cast("QLabel", dialog.findChild(QLabel, "settings_dialog.save_state"))
    save_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.save_changes_button")
    )
    assert save_state_label.text() == "No changes"

    controller = _controller_of(dialog)
    # The mutation below leaves the dialog dirty; pytest-qt's automatic
    # teardown calls dialog.close() -> reject() -> on_close_requested(),
    # which would otherwise open a real, blocking QMessageBox with no user to
    # dismiss it. Discard silently so teardown does not hang.
    mocker.patch.object(controller, "_confirm_discard_changes", return_value=True)
    controller.providers_controller.on_enabled_toggled(0)

    assert save_state_label.text() == "Unsaved changes"
    assert not save_button.isEnabled()
