"""Unit tests for EnvVarConversionDialog — resolved_configs logic and row defaults."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import ProviderConfig, ProviderType
from ollama_llm_bench.ui.widgets.settings.env_var_conversion_dialog import (
    _ENV_VAR_NAME_RE,
    _ROLE_CONVERT,
    _ROLE_SAVE_PLAIN,
    _ROLE_SKIP,
    EnvVarConversionDialog,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _make_cfg(
    provider_id: str = "test_provider",
    label: str = "Test Provider",
    api_key_raw: str = "sk-plainvalue",
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        label=label,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key=api_key_raw,
        api_key_raw=api_key_raw,
    )


def _make_dialog(configs: list[ProviderConfig], qapp: QApplication) -> EnvVarConversionDialog:
    return EnvVarConversionDialog(configs_needing_action=configs)


class TestResolvedConfigsDefaultBehavior:
    def test_save_plain_leaves_api_key_raw_unchanged(self, qapp: QApplication) -> None:
        cfg = _make_cfg(api_key_raw="sk-abc123")
        dlg = _make_dialog([cfg], qapp)

        resolved = dlg.resolved_configs

        assert resolved[0].api_key_raw == "sk-abc123"

    def test_skip_leaves_api_key_raw_unchanged(self, qapp: QApplication) -> None:
        cfg = _make_cfg(api_key_raw="sk-abc123")
        dlg = _make_dialog([cfg], qapp)
        dlg._rows[0].btn_group.button(_ROLE_SKIP).setChecked(True)  # type: ignore[union-attr]

        resolved = dlg.resolved_configs

        assert resolved[0].api_key_raw == "sk-abc123"

    def test_resolved_configs_count_matches_input(self, qapp: QApplication) -> None:
        configs = [_make_cfg(provider_id=f"p{i}") for i in range(3)]
        dlg = _make_dialog(configs, qapp)

        assert len(dlg.resolved_configs) == 3

    def test_all_rows_default_to_save_plain(self, qapp: QApplication) -> None:
        configs = [_make_cfg(provider_id=f"p{i}") for i in range(3)]
        dlg = _make_dialog(configs, qapp)

        for row in dlg._rows:
            assert row.btn_group.checkedId() == _ROLE_SAVE_PLAIN


class TestResolvedConfigsConvert:
    def test_convert_with_var_name_sets_env_var_reference(self, qapp: QApplication) -> None:
        cfg = _make_cfg()
        dlg = _make_dialog([cfg], qapp)
        dlg._rows[0].btn_group.button(_ROLE_CONVERT).setChecked(True)  # type: ignore[union-attr]
        dlg._rows[0].var_name_edit.setText("MY_KEY")

        resolved = dlg.resolved_configs

        assert resolved[0].api_key_raw == "${MY_KEY}"

    def test_convert_with_empty_var_name_falls_back_to_save_plain(self, qapp: QApplication) -> None:
        cfg = _make_cfg(api_key_raw="sk-orig")
        dlg = _make_dialog([cfg], qapp)
        dlg._rows[0].btn_group.button(_ROLE_CONVERT).setChecked(True)  # type: ignore[union-attr]
        dlg._rows[0].var_name_edit.setText("")

        resolved = dlg.resolved_configs

        assert resolved[0].api_key_raw == "sk-orig"

    def test_convert_sets_api_key_to_empty_string(self, qapp: QApplication) -> None:
        cfg = _make_cfg(api_key_raw="sk-secret")
        dlg = _make_dialog([cfg], qapp)
        dlg._rows[0].btn_group.button(_ROLE_CONVERT).setChecked(True)  # type: ignore[union-attr]
        dlg._rows[0].var_name_edit.setText("SOME_KEY")

        resolved = dlg.resolved_configs

        assert resolved[0].api_key == ""

    def test_convert_does_not_mutate_original_config(self, qapp: QApplication) -> None:
        cfg = _make_cfg(api_key_raw="sk-secret")
        dlg = _make_dialog([cfg], qapp)
        dlg._rows[0].btn_group.button(_ROLE_CONVERT).setChecked(True)  # type: ignore[union-attr]
        dlg._rows[0].var_name_edit.setText("SOME_KEY")

        _ = dlg.resolved_configs

        assert cfg.api_key_raw == "sk-secret"
        assert cfg.api_key == "sk-secret"


class TestDefaultVarNamePrefill:
    def test_default_var_name_is_provider_id_upper_api_key(self, qapp: QApplication) -> None:
        cfg = _make_cfg(provider_id="anthropic_prov")
        dlg = _make_dialog([cfg], qapp)

        assert dlg._rows[0].var_name_edit.text() == "ANTHROPIC_PROV_API_KEY"


class TestMultipleProviders:
    def test_multiple_providers_each_row_is_independent(self, qapp: QApplication) -> None:
        cfg0 = _make_cfg(provider_id="p0", api_key_raw="sk-p0")
        cfg1 = _make_cfg(provider_id="p1", api_key_raw="sk-p1")
        dlg = _make_dialog([cfg0, cfg1], qapp)

        # Row 0: Convert with key name KEY_A
        dlg._rows[0].btn_group.button(_ROLE_CONVERT).setChecked(True)  # type: ignore[union-attr]
        dlg._rows[0].var_name_edit.setText("KEY_A")
        # Row 1: Save plain (default)

        resolved = dlg.resolved_configs

        assert resolved[0].api_key_raw == "${KEY_A}"
        assert resolved[1].api_key_raw == "sk-p1"


class TestValidation:
    def test_lowercase_var_name_fails_validation(self) -> None:
        assert _ENV_VAR_NAME_RE.match("my_key") is None

    def test_uppercase_var_name_passes_validation(self) -> None:
        assert _ENV_VAR_NAME_RE.match("MY_KEY") is not None

    def test_mixed_case_var_name_fails_validation(self) -> None:
        assert _ENV_VAR_NAME_RE.match("My_Key") is None
