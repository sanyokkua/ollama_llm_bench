"""Tests for STORY-110-AC-9 -- the three Settings-dialog test actions apply no
outcome until the gateway's ``on_complete`` callback fires.

Uses ``FakeSettingsGateway(defer_callbacks=True)`` (STORY-110): unlike the
default synchronous-fire fake every pre-existing colocated test in this module
relies on, the deferred variant captures ``on_complete`` without invoking it,
so this file drives completion itself via ``fire_test_provider_callback`` --
the only way to observe the "nothing changes until the callback fires" half of
this acceptance criterion.
"""

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QPushButton
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.adapters.qt_table_models.models import ProviderTableRow
from ollama_llm_bench.backend.domain import (
    InferenceTestOutcome,
    InferenceTestResult,
    ProviderTestStatus,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.controller import (
    ProvidersTabController,
)
from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.provider_edit_view import (
    ProviderEditDialog,
    make_provider_edit_dialog,
)
from ollama_llm_bench.ui.settings_dialog.models import ProviderEditCollaborators
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway
from ollama_llm_bench.ui.settings_dialog.tests.conftest import PROVIDER_A, FakeEventBus


class _RowsExposingModel:
    """Structural cast target for the table model's public ``rows`` property
    (mirrors ``test_controller.py``'s equivalent)."""

    rows: tuple[ProviderTableRow, ...]


def _make_result(
    *, outcome: InferenceTestOutcome = InferenceTestOutcome.SUCCESS, model_name: str = "unknown"
) -> InferenceTestResult:
    return InferenceTestResult(
        outcome=outcome, provider_id=PROVIDER_A.provider_id, model_name=model_name, tested_at=0
    )


def _make_provider_edit_dialog_under_test(
    *, gateway: FakeSettingsGateway, event_bus: FakeEventBus, qtbot: QtBot
) -> ProviderEditDialog:
    dialog = make_provider_edit_dialog(
        collaborators=ProviderEditCollaborators(gateway=gateway, event_bus=event_bus),
        config=PROVIDER_A,
        existing_names=(),
    )
    qtbot.addWidget(dialog)
    return dialog


def _result_label(dialog: ProviderEditDialog) -> QLabel:
    return cast("QLabel", dialog.findChild(QLabel, "settings_dialog.provider_edit.result"))


def _case_providers_tab_row_test_connection(qtbot: QtBot) -> None:
    del qtbot  # this click target needs no real widget -- the controller owns the paint
    # Arrange
    gateway = FakeSettingsGateway(defer_callbacks=True)
    gateway.set_providers((PROVIDER_A,))
    controller = ProvidersTabController(
        gateway=gateway, event_bus=FakeEventBus(), notifications=FakeNotificationService()
    )
    controller.reload()

    # Act: click Test connection
    controller.on_test_clicked(0)

    # Assert: immediately after the click, the row shows TESTING -- the outcome has not
    # been applied because the fake captured (not invoked) on_complete.
    rows = cast("_RowsExposingModel", controller.table_model).rows
    assert rows[0].health is ProviderTestStatus.TESTING

    # Act: the gateway's completion callback fires
    gateway.fire_test_provider_callback(_make_result(outcome=InferenceTestOutcome.SUCCESS))

    # Assert: only now does the real outcome apply.
    rows = cast("_RowsExposingModel", controller.table_model).rows
    assert rows[0].health is ProviderTestStatus.READY


def _case_provider_edit_test_reachability(qtbot: QtBot) -> None:
    # Arrange
    gateway = FakeSettingsGateway(defer_callbacks=True)
    dialog = _make_provider_edit_dialog_under_test(
        gateway=gateway, event_bus=FakeEventBus(), qtbot=qtbot
    )
    reachability_button = cast(
        "QPushButton",
        dialog.findChild(QPushButton, "settings_dialog.provider_edit.test_reachability"),
    )
    result_label = _result_label(dialog)
    assert result_label.text() == ""

    # Act: click Test reachability
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        reachability_button, Qt.MouseButton.LeftButton
    )

    # Assert: the strip is unchanged immediately after the click
    assert result_label.text() == ""

    # Act: the gateway's completion callback fires
    gateway.fire_test_provider_callback(_make_result(outcome=InferenceTestOutcome.SUCCESS))

    # Assert: only now does the strip read the outcome
    assert result_label.text() == "Test reachability — success"


def _case_provider_edit_run_inference_test(qtbot: QtBot) -> None:
    # Arrange
    gateway = FakeSettingsGateway(defer_callbacks=True)
    dialog = _make_provider_edit_dialog_under_test(
        gateway=gateway, event_bus=FakeEventBus(), qtbot=qtbot
    )
    test_inference_toggle = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.provider_edit.test_inference")
    )
    manual_entry_checkbox = cast(
        "QCheckBox",
        dialog.findChild(QCheckBox, "settings_dialog.provider_edit.manual_entry_toggle"),
    )
    manual_model_edit = cast(
        "QLineEdit", dialog.findChild(QLineEdit, "settings_dialog.provider_edit.manual_model")
    )
    run_inference_button = cast(
        "QPushButton", dialog.findChild(QPushButton, "settings_dialog.provider_edit.run_inference")
    )
    result_label = _result_label(dialog)
    # Act: open the inference panel, switch to manual entry, and name a model
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        test_inference_toggle, Qt.MouseButton.LeftButton
    )
    manual_entry_checkbox.setChecked(True)
    qtbot.keyClicks(manual_model_edit, "llama3")  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    assert run_inference_button.isEnabled() is True
    assert result_label.text() == ""

    # Act: click Run inference test
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        run_inference_button, Qt.MouseButton.LeftButton
    )

    # Assert: the strip is unchanged immediately after the click
    assert result_label.text() == ""

    # Act: the gateway's completion callback fires
    gateway.fire_test_provider_callback(
        _make_result(outcome=InferenceTestOutcome.SUCCESS, model_name="llama3")
    )

    # Assert: only now does the strip read the outcome and the model
    assert result_label.text() == "Test inference — success — llama3"


_AC9_CASES: tuple[tuple[str, Callable[[QtBot], None]], ...] = (
    ("providers_tab_row_test_connection", _case_providers_tab_row_test_connection),
    ("provider_edit_test_reachability", _case_provider_edit_test_reachability),
    ("provider_edit_run_inference_test", _case_provider_edit_run_inference_test),
)
_AC9_CASE_IDS = [case[0] for case in _AC9_CASES]


@pytest.mark.parametrize("case", _AC9_CASES, ids=_AC9_CASE_IDS)
def test_each_test_action_applies_its_outcome_only_from_the_callback(
    case: tuple[str, Callable[[QtBot], None]], qtbot: QtBot
) -> None:
    """Proves: STORY-110-AC-9

    For each Settings-dialog test action (the Providers-tab row's ``Test
    connection``, Provider Edit's ``Test reachability``, and Provider Edit's
    ``Run inference test``), clicking it applies no outcome to the widget
    until the gateway's completion callback runs -- the row's health dot (or
    the inline result strip) is unchanged, or reads an in-flight ``TESTING``
    state, immediately after the click, and reads the real outcome only once
    ``FakeSettingsGateway.fire_test_provider_callback`` is called. Table-driven
    -- one row per click target -- because the variation across all three rows
    is a finite enumerable set and is the point of the criterion.
    """
    _name, run_case = case
    run_case(qtbot)
