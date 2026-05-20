"""Unit tests for ProviderTableModel."""

import dataclasses

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import ProviderConfig, ProviderType
from ollama_llm_bench.backend.services.provider_health_checker import HealthCheckResult
from ollama_llm_bench.ui.models.provider_table_model import (
    COL_ACTIONS,
    COL_BASE_URL,
    COL_ENABLED,
    COL_HEALTH,
    COL_LABEL,
    COL_TYPE,
    ProviderTableModel,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _cfg(
    provider_id: str = "p1",
    *,
    enabled: bool = True,
    base_url: str = "http://localhost:11434/v1",
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        label=f"Provider {provider_id}",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key="key",
        api_key_raw="key",
        enabled=enabled,
        base_url=base_url,
    )


def _healthy(provider_id: str = "p1", *, model_count: int = 3) -> HealthCheckResult:
    return HealthCheckResult(
        provider_id=provider_id,
        is_healthy=True,
        model_count=model_count,
        error_message="",
        latency_ms=50,
    )


def _down(provider_id: str = "p1") -> HealthCheckResult:
    return HealthCheckResult(
        provider_id=provider_id,
        is_healthy=False,
        model_count=0,
        error_message="Connection refused",
        latency_ms=0,
    )


# ---------------------------------------------------------------------------
# Row / column counts
# ---------------------------------------------------------------------------


class TestShapeContract:
    def test_row_count_matches_configs(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1"), _cfg("p2")])
        assert model.rowCount() == 2

    def test_row_count_zero_for_valid_parent(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        parent = model.index(0, 0)
        assert model.rowCount(parent) == 0

    def test_column_count_is_six(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        assert model.columnCount() == 6

    def test_column_count_zero_for_valid_parent(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        parent = model.index(0, 0)
        assert model.columnCount(parent) == 0


# ---------------------------------------------------------------------------
# DisplayRole
# ---------------------------------------------------------------------------


class TestDisplayRole:
    def test_label_column(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        idx = model.index(0, COL_LABEL)
        assert model.data(idx) == "Provider p1"

    def test_type_column(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        idx = model.index(0, COL_TYPE)
        assert model.data(idx) == ProviderType.OPENAI_COMPATIBLE.value

    def test_base_url_column(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        idx = model.index(0, COL_BASE_URL)
        assert model.data(idx) == "http://localhost:11434/v1"

    def test_base_url_none_returns_empty_string(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1", base_url="")])
        # ProviderConfig base_url is str | None; passing "" tests empty string path
        idx = model.index(0, COL_BASE_URL)
        assert model.data(idx) == ""

    def test_health_column_display_is_dot(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        idx = model.index(0, COL_HEALTH)
        assert model.data(idx) == "●"

    def test_invalid_index_returns_none(self, qapp: QApplication) -> None:
        from PySide6.QtCore import QModelIndex

        model = ProviderTableModel([_cfg()])
        assert model.data(QModelIndex()) is None


# ---------------------------------------------------------------------------
# CheckStateRole (COL_ENABLED)
# ---------------------------------------------------------------------------


class TestCheckStateRole:
    def test_enabled_returns_checked(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg(enabled=True)])
        idx = model.index(0, COL_ENABLED)
        assert model.data(idx, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked

    def test_disabled_returns_unchecked(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg(enabled=False)])
        idx = model.index(0, COL_ENABLED)
        assert model.data(idx, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked

    def test_other_columns_return_none_for_check_role(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        idx = model.index(0, COL_LABEL)
        assert model.data(idx, Qt.ItemDataRole.CheckStateRole) is None


# ---------------------------------------------------------------------------
# UserRole
# ---------------------------------------------------------------------------


class TestUserRole:
    def test_health_user_role_returns_health_state(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        idx = model.index(0, COL_HEALTH)
        assert model.data(idx, Qt.ItemDataRole.UserRole) == "unknown"

    def test_label_user_role_returns_provider_id(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        idx = model.index(0, COL_LABEL)
        assert model.data(idx, Qt.ItemDataRole.UserRole) == "p1"


# ---------------------------------------------------------------------------
# setData
# ---------------------------------------------------------------------------


class TestSetData:
    def test_toggle_to_unchecked_updates_config(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg(enabled=True)])
        idx = model.index(0, COL_ENABLED)
        model.setData(idx, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        assert not model.get_config(0).enabled

    def test_toggle_to_checked_updates_config(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg(enabled=False)])
        idx = model.index(0, COL_ENABLED)
        model.setData(idx, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        assert model.get_config(0).enabled

    def test_toggle_emits_provider_user_edited(self, qapp: QApplication, qtbot: pytest.FixtureRequest) -> None:
        model = ProviderTableModel([_cfg("p1", enabled=True)])
        idx = model.index(0, COL_ENABLED)
        received: list[str] = []
        model.provider_user_edited.connect(received.append)
        model.setData(idx, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        assert received == ["p1"]

    def test_invalid_index_returns_false(self, qapp: QApplication) -> None:
        from PySide6.QtCore import QModelIndex

        model = ProviderTableModel([_cfg()])
        assert model.setData(QModelIndex(), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole) is False

    def test_non_enabled_column_returns_false(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        idx = model.index(0, COL_LABEL)
        assert model.setData(idx, "value", Qt.ItemDataRole.CheckStateRole) is False


# ---------------------------------------------------------------------------
# set_enable (programmatic, no signal)
# ---------------------------------------------------------------------------


class TestSetEnable:
    def test_set_enable_true_updates_is_enabled(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg(enabled=False)])
        model.set_enable("p1", True)
        assert model.is_enabled("p1") is True

    def test_set_enable_false_updates_is_enabled(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg(enabled=True)])
        model.set_enable("p1", False)
        assert model.is_enabled("p1") is False

    def test_set_enable_does_not_emit_user_edited(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg(enabled=False)])
        received: list[str] = []
        model.provider_user_edited.connect(received.append)
        model.set_enable("p1", True)
        assert received == []

    def test_set_enable_unknown_id_is_noop(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        model.set_enable("nonexistent", True)  # must not raise
        assert model.rowCount() == 1


# ---------------------------------------------------------------------------
# apply_health_result
# ---------------------------------------------------------------------------


class TestApplyHealthResult:
    def test_initial_state_is_unknown(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        assert model.get_health_state("p1") == "unknown"

    def test_healthy_with_models_sets_live(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        model.apply_health_result(_healthy(model_count=3))
        assert model.get_health_state("p1") == "live"

    def test_healthy_zero_models_sets_warning(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        model.apply_health_result(_healthy(model_count=0))
        assert model.get_health_state("p1") == "warning"

    def test_unhealthy_sets_down(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        model.apply_health_result(_down())
        assert model.get_health_state("p1") == "down"

    def test_stores_last_health_result(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        result = _healthy()
        model.apply_health_result(result)
        assert model.get_health_result("p1") is result

    def test_unknown_provider_id_is_noop(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        model.apply_health_result(_healthy(provider_id="missing"))
        assert model.get_health_state("p1") == "unknown"

    def test_second_result_overwrites_first(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        model.apply_health_result(_healthy(model_count=5))
        model.apply_health_result(_down())
        assert model.get_health_state("p1") == "down"


# ---------------------------------------------------------------------------
# set_health (direct state setter)
# ---------------------------------------------------------------------------


class TestSetHealth:
    def test_set_health_updates_state(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        model.set_health("p1", "down", "Provider unreachable.")
        assert model.get_health_state("p1") == "down"

    def test_set_health_unknown_id_is_noop(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        model.set_health("missing", "down", "")  # must not raise


# ---------------------------------------------------------------------------
# Mutations (append, remove, update)
# ---------------------------------------------------------------------------


class TestMutations:
    def test_append_increases_row_count(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        model.append_config(_cfg("p2"))
        assert model.rowCount() == 2

    def test_append_returns_new_row_index(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        row = model.append_config(_cfg("p2"))
        assert row == 1

    def test_find_row_returns_correct_index(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1"), _cfg("p2")])
        assert model.find_row("p2") == 1

    def test_find_row_returns_minus_one_for_missing(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        assert model.find_row("missing") == -1

    def test_remove_row_decreases_count(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1"), _cfg("p2")])
        model.remove_row_for_provider("p1")
        assert model.rowCount() == 1

    def test_remove_row_makes_provider_unfindable(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1"), _cfg("p2")])
        model.remove_row_for_provider("p1")
        assert model.find_row("p1") == -1

    def test_remove_unknown_provider_is_noop(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        model.remove_row_for_provider("missing")  # must not raise
        assert model.rowCount() == 1

    def test_update_config_changes_label(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        new_cfg = dataclasses.replace(_cfg("p1"), label="Updated")
        model.update_config(0, new_cfg)
        assert model.get_config(0).label == "Updated"

    def test_update_config_out_of_range_is_noop(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1")])
        model.update_config(99, _cfg("p2"))  # must not raise

    def test_all_configs_returns_all_in_order(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg("p1"), _cfg("p2")])
        ids = [c.provider_id for c in model.all_configs()]
        assert ids == ["p1", "p2"]


# ---------------------------------------------------------------------------
# Header ToolTipRole
# ---------------------------------------------------------------------------


class TestHeaderTooltipRole:
    def test_header_tooltip_health_column_returns_text(self, qapp: QApplication) -> None:
        """Health column header must have a non-empty tooltip explaining the dot colours."""
        model = ProviderTableModel([_cfg()])
        tooltip = model.headerData(COL_HEALTH, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        assert isinstance(tooltip, str) and tooltip

    def test_header_tooltip_label_column_returns_text(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        tooltip = model.headerData(COL_LABEL, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        assert isinstance(tooltip, str) and tooltip

    def test_header_tooltip_type_column_returns_text(self, qapp: QApplication) -> None:
        model = ProviderTableModel([_cfg()])
        tooltip = model.headerData(COL_TYPE, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        assert isinstance(tooltip, str) and tooltip

    def test_header_tooltip_actions_column_returns_none(self, qapp: QApplication) -> None:
        """Actions column has no tooltip — headerData must return None."""
        model = ProviderTableModel([_cfg()])
        tooltip = model.headerData(COL_ACTIONS, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        assert tooltip is None

    def test_header_display_role_still_works(self, qapp: QApplication) -> None:
        """Adding ToolTipRole must not break the existing DisplayRole branch."""
        model = ProviderTableModel([_cfg()])
        label = model.headerData(COL_LABEL, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        assert label == "Label"

    def test_header_tooltip_vertical_returns_none(self, qapp: QApplication) -> None:
        """Vertical headers have no tooltip."""
        model = ProviderTableModel([_cfg()])
        tooltip = model.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.ToolTipRole)
        assert tooltip is None
