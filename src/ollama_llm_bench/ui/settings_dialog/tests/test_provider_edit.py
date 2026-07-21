"""Tests for the Provider Edit sub-dialog (STORY-066-AC-2, AC-3, AC-4, AC-5)."""

from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QPushButton
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import (
    InferenceActivity,
    InferenceActivityState,
    ProviderConfig,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    InferenceActivityChangedEvent,
)
from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.provider_edit_view import (
    ProviderEditDialog,
    make_provider_edit_dialog,
)
from ollama_llm_bench.ui.settings_dialog.models import ProviderEditCollaborators
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway
from ollama_llm_bench.ui.settings_dialog.tests.conftest import PROVIDER_A, PROVIDER_B, FakeEventBus

_GATE_BUSY_TOOLTIP = "Another inference activity is in flight — please wait."


def _make_dialog(
    *,
    gateway: FakeSettingsGateway | None = None,
    bus: FakeEventBus | None = None,
    config: ProviderConfig | None = None,
    existing_names: tuple[str, ...] = (),
) -> ProviderEditDialog:
    collaborators = ProviderEditCollaborators(
        gateway=gateway or FakeSettingsGateway(), event_bus=bus or FakeEventBus()
    )
    return make_provider_edit_dialog(
        collaborators=collaborators, config=config, existing_names=existing_names
    )


# ---------------------------------------------------------------------------
# STORY-066-AC-2
# ---------------------------------------------------------------------------


def test_api_key_field_rejects_non_env_var_name(qtbot: QtBot) -> None:
    """Proves: STORY-066-AC-2

    Covers: EC-PROV-7

    Given the Provider Edit API-key field, when the user types a value that
    is not a valid environment-variable name and is non-empty, then the field
    shows the inline error and Save is blocked; and when the value is a
    valid name, then the field is accepted and Save is no longer blocked by
    this rule.
    """
    # Arrange
    dialog = _make_dialog(config=PROVIDER_A)
    qtbot.addWidget(dialog)
    api_key_edit = cast(
        "QLineEdit", dialog.findChild(QLineEdit, "settings_dialog.provider_edit.api_key")
    )
    api_key_error = cast(
        "QLabel", dialog.findChild(QLabel, "settings_dialog.provider_edit.api_key_error")
    )
    save_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.provider_edit.save")
    )
    # Act: type an invalid value (looks like an actual key, not a name)
    api_key_edit.clear()
    qtbot.keyClicks(api_key_edit, "sk-proj-AbCdEf1234567890")  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    # Assert
    assert api_key_error.text() != ""
    assert save_button.isEnabled() is False
    # Act: replace it with a valid environment-variable name
    api_key_edit.clear()
    qtbot.keyClicks(api_key_edit, "OPENAI_API_KEY")  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    # Assert
    assert api_key_error.text() == ""
    assert save_button.isEnabled() is True


# ---------------------------------------------------------------------------
# STORY-066-AC-3
# ---------------------------------------------------------------------------


def test_duplicate_name_blocks_save(qtbot: QtBot) -> None:
    """Proves: STORY-066-AC-3

    Covers: EC-PROV-10, EC-PROV-11

    Given the Provider Edit dialog, when the user types a Name that
    duplicates another working row's Name, then the Name field shows the
    duplicate-name error and Save is disabled.
    """
    # Arrange
    dialog = _make_dialog(existing_names=("Existing Provider",))
    qtbot.addWidget(dialog)
    name_edit = cast("QLineEdit", dialog.findChild(QLineEdit, "settings_dialog.provider_edit.name"))
    name_error = cast(
        "QLabel", dialog.findChild(QLabel, "settings_dialog.provider_edit.name_error")
    )
    save_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.provider_edit.save")
    )
    # Act
    qtbot.keyClicks(name_edit, "Existing Provider")  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    # Assert
    assert name_error.text() == "A provider with this name already exists."
    assert save_button.isEnabled() is False


def test_rename_to_persisted_name_blocks_save(qtbot: QtBot) -> None:
    """Proves: STORY-066-AC-3

    Covers: EC-PROV-11

    Given the user edits an existing provider and types a Name matching a
    *persisted* row (returned by ``SettingsGateway.get_provider_by_name``)
    other than the row being edited, then Save is disabled.
    """
    # Arrange
    gateway = FakeSettingsGateway()
    gateway.set_providers((PROVIDER_A, PROVIDER_B))
    dialog = _make_dialog(gateway=gateway, config=PROVIDER_A)
    qtbot.addWidget(dialog)
    name_edit = cast("QLineEdit", dialog.findChild(QLineEdit, "settings_dialog.provider_edit.name"))
    save_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.provider_edit.save")
    )
    # Act: rename PROVIDER_A's working copy to PROVIDER_B's persisted name
    name_edit.clear()
    qtbot.keyClicks(name_edit, PROVIDER_B.name)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    # Assert
    assert save_button.isEnabled() is False


# ---------------------------------------------------------------------------
# STORY-066-AC-4
# ---------------------------------------------------------------------------


def test_run_inference_disabled_until_model_named(qtbot: QtBot) -> None:
    """Proves: STORY-066-AC-4

    Covers: EC-PROV-5c

    Given the Test inference panel, when no model is selected and manual
    entry is off, then Run inference test is disabled; and when the manual
    entry toggle is on and a model name is typed, then it is enabled.
    """
    # Arrange
    dialog = _make_dialog(config=PROVIDER_A)
    qtbot.addWidget(dialog)
    test_inference_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.provider_edit.test_inference")
    )
    run_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.provider_edit.run_inference")
    )
    manual_toggle = cast(
        "QCheckBox",
        dialog.findChild(QCheckBox, "settings_dialog.provider_edit.manual_entry_toggle"),
    )
    manual_model_edit = cast(
        "QLineEdit", dialog.findChild(QLineEdit, "settings_dialog.provider_edit.manual_model")
    )
    # Act: open the inference panel
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        test_inference_button, Qt.MouseButton.LeftButton
    )
    # Assert: no model named yet
    assert run_button.isEnabled() is False
    # Act: toggle manual entry and type a model name
    manual_toggle.setChecked(True)
    qtbot.keyClicks(manual_model_edit, "llama3")  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    # Assert
    assert run_button.isEnabled() is True
    # Act: clear the manual text
    manual_model_edit.clear()
    # Assert: disabled again
    assert run_button.isEnabled() is False


# ---------------------------------------------------------------------------
# STORY-066-AC-5
# ---------------------------------------------------------------------------


def test_test_buttons_gated_on_inference_activity(qtbot: QtBot) -> None:
    """Proves: STORY-066-AC-5

    Covers: EC-PROV-5b

    Given the single-inference gate is held by an activity other than
    ``PROVIDER_TEST``, when the Test reachability and Test inference buttons
    render, then both are disabled with the in-flight tooltip; and when
    ``_inference_activity_changed`` reports the gate ``IDLE``, then they
    re-enable.
    """
    # Arrange
    bus = FakeEventBus()
    dialog = _make_dialog(bus=bus, config=PROVIDER_A)
    qtbot.addWidget(dialog)
    test_reachability_button = cast(
        "QPushButton",
        dialog.findChild(QPushButton, "settings_dialog.provider_edit.test_reachability"),
    )
    test_inference_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.provider_edit.test_inference")
    )
    # Act: another activity holds the gate
    bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(
            state=InferenceActivityState(current=InferenceActivity.BENCHMARK_RUN)
        ),
    )
    # Assert
    assert test_reachability_button.isEnabled() is False
    assert test_reachability_button.toolTip() == _GATE_BUSY_TOOLTIP
    assert test_inference_button.isEnabled() is False
    assert test_inference_button.toolTip() == _GATE_BUSY_TOOLTIP
    # Act: the gate returns to IDLE
    bus.emit(
        SIGNAL_INFERENCE_ACTIVITY_CHANGED,
        InferenceActivityChangedEvent(state=InferenceActivityState(current=InferenceActivity.IDLE)),
    )
    # Assert
    assert test_reachability_button.isEnabled() is True
    assert test_inference_button.isEnabled() is True
