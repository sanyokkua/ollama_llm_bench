"""Proves: STORY-067-AC-1

Confirms the General tab's working copy loads from the Gateway, tracks dirty
state per-key, and assembles the full value map for Save.
"""

from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.settings_dialog._internal.general_tab.controller import (
    GeneralTabController,
)
from ollama_llm_bench.ui.settings_dialog._internal.general_tab.field_binders import FIELD_REGISTRY
from ollama_llm_bench.ui.settings_dialog._internal.general_tab.view import GeneralTabView
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway


def test_reload_seeds_working_copy_from_gateway_list_settings() -> None:
    gateway = FakeSettingsGateway()
    gateway.set_setting_value("ui.theme", "dark")
    controller = GeneralTabController(gateway=gateway)

    controller.reload()

    assert controller.is_dirty is False
    assert controller.values_for_save()["ui.theme"] == "dark"


def test_set_value_marks_dirty_only_when_value_differs_from_loaded() -> None:
    gateway = FakeSettingsGateway()
    gateway.set_setting_value("ui.theme", "dark")
    controller = GeneralTabController(gateway=gateway)
    controller.reload()

    controller.set_value("ui.theme", "dark")
    assert controller.is_dirty is False

    controller.set_value("ui.theme", "light")
    assert controller.is_dirty is True


def test_values_for_reset_defaults_covers_every_registry_key() -> None:
    gateway = FakeSettingsGateway()
    controller = GeneralTabController(gateway=gateway)

    defaults = controller.values_for_reset_defaults()

    assert defaults["ui.theme"] == "system"
    assert defaults["benchmark.retry_count"] == "3"
    assert defaults["benchmark.temperature"] == "0.0"


def test_general_tab_view_constructs_one_control_per_registry_key(qtbot: QtBot) -> None:
    view = GeneralTabView()
    qtbot.addWidget(view)

    for spec in FIELD_REGISTRY:
        assert view.findChild(object, spec.setting_key) is not None
