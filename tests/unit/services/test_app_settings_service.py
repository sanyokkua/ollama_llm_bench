"""Unit tests for AppSettingsService — type conversion and DataApi delegation."""

from typing import cast
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import DataApi
from ollama_llm_bench.backend.core.models import AppSetting
from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_AUTO_SCROLL,
    SETTING_COSINE_ENABLED,
    SETTING_COSINE_THRESHOLD_CONTAINS,
    SETTING_COSINE_THRESHOLD_COVERS,
    SETTING_COSINE_THRESHOLD_EXACT,
    SETTING_KEYWORD_ENABLED,
    SETTING_LOG_MAX_LINES,
    SETTING_LOG_VERBOSITY,
    SETTING_PAUSE_ON_MODEL_SWITCH,
    SETTING_PAUSE_ON_PROVIDER_SWITCH,
    SETTING_PAUSE_ON_STAGE_SWITCH,
    SETTING_REASONING_EFFORT_DEFAULT,
    SETTING_RETRY_COUNT,
    SETTING_SCORE_DISPLAY_FORMAT,
    SETTING_STOP_ON_PROVIDER_ERROR,
    SETTING_STREAMING_ENABLED,
    SETTING_THEME,
    SETTING_WARMUP_ENABLED,
    AppSettingsService,
)

_UNKNOWN_KEY = "unknown.test.key"


@pytest.fixture
def mock_data_api(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=DataApi))


@pytest.fixture
def service(mock_data_api: MagicMock) -> AppSettingsService:
    return AppSettingsService(data_api=cast(DataApi, mock_data_api))


def _make_setting(key: str, value: str) -> AppSetting:
    return AppSetting(key=key, value=value, updated_at="2026-01-01T00:00:00")


class TestGet:
    def test_returns_value_when_setting_exists(self, service: AppSettingsService, mock_data_api: MagicMock) -> None:
        mock_data_api.get_app_setting.return_value = _make_setting(SETTING_STREAMING_ENABLED, "true")
        result = service.get(SETTING_STREAMING_ENABLED)

        assert result == "true"

    def test_returns_none_when_setting_absent_and_no_default(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        result = service.get(_UNKNOWN_KEY)

        assert result is None

    def test_returns_default_when_setting_absent(self, service: AppSettingsService, mock_data_api: MagicMock) -> None:
        mock_data_api.get_app_setting.return_value = None
        result = service.get(_UNKNOWN_KEY, default="fallback")

        assert result == "fallback"

    def test_delegates_to_data_api_with_correct_key(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        mock_data_api.get_app_setting.reset_mock()
        service.get(SETTING_WARMUP_ENABLED)

        mock_data_api.get_app_setting.assert_called_once_with(SETTING_WARMUP_ENABLED)


class TestSet:
    def test_calls_data_api_with_keyword_args(self, service: AppSettingsService, mock_data_api: MagicMock) -> None:
        service.set(SETTING_STREAMING_ENABLED, "false")

        mock_data_api.set_app_setting.assert_called_once_with(key=SETTING_STREAMING_ENABLED, value="false")

    def test_passes_arbitrary_key_and_value(self, service: AppSettingsService, mock_data_api: MagicMock) -> None:
        service.set(SETTING_STOP_ON_PROVIDER_ERROR, "true")

        mock_data_api.set_app_setting.assert_called_once_with(key=SETTING_STOP_ON_PROVIDER_ERROR, value="true")


class TestGetBool:
    @pytest.mark.parametrize(
        "stored_value",
        ["true", "True", "TRUE", "tRuE"],
        ids=["lowercase", "capitalized", "uppercase", "mixed_case"],
    )
    def test_returns_true_for_true_variants(
        self, service: AppSettingsService, mock_data_api: MagicMock, stored_value: str
    ) -> None:
        mock_data_api.get_app_setting.return_value = _make_setting(SETTING_STREAMING_ENABLED, stored_value)
        assert service.get_bool(SETTING_STREAMING_ENABLED) is True

    @pytest.mark.parametrize(
        "stored_value",
        ["false", "False", "0", "1", "yes", "no", ""],
        ids=["false_lower", "false_cap", "zero", "one", "yes", "no", "empty"],
    )
    def test_returns_false_for_non_true_values(
        self, service: AppSettingsService, mock_data_api: MagicMock, stored_value: str
    ) -> None:
        mock_data_api.get_app_setting.return_value = _make_setting(SETTING_STREAMING_ENABLED, stored_value)
        assert service.get_bool(SETTING_STREAMING_ENABLED) is False

    def test_returns_default_false_when_setting_absent(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        assert service.get_bool(_UNKNOWN_KEY) is False

    def test_returns_custom_default_true_when_setting_absent(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        assert service.get_bool(_UNKNOWN_KEY, default=True) is True


class TestGetInt:
    def test_returns_parsed_int_for_valid_string(self, service: AppSettingsService, mock_data_api: MagicMock) -> None:
        mock_data_api.get_app_setting.return_value = _make_setting(SETTING_LOG_MAX_LINES, "10000")
        assert service.get_int(SETTING_LOG_MAX_LINES) == 10000

    def test_returns_default_zero_when_setting_absent(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        assert service.get_int(_UNKNOWN_KEY) == 0

    def test_returns_custom_default_when_setting_absent(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        assert service.get_int(_UNKNOWN_KEY, default=500) == 500

    def test_returns_default_and_logs_warning_for_non_numeric_value(
        self, service: AppSettingsService, mock_data_api: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_data_api.get_app_setting.return_value = _make_setting(SETTING_LOG_MAX_LINES, "abc")
        result = service.get_int(SETTING_LOG_MAX_LINES, default=100)

        assert result == 100
        assert "invalid_int_setting" in caplog.text

    def test_returns_default_for_empty_string_value(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = _make_setting(SETTING_LOG_MAX_LINES, "")
        assert service.get_int(SETTING_LOG_MAX_LINES, default=42) == 42


class TestProtocolConformance:
    def test_isinstance_check_passes(self, mock_data_api: MagicMock) -> None:
        from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi

        svc = AppSettingsService(data_api=cast(DataApi, mock_data_api))
        assert isinstance(svc, AppSettingsServiceApi)

    def test_all_setting_constants_are_strings(self) -> None:
        assert isinstance(SETTING_PAUSE_ON_PROVIDER_SWITCH, str)
        assert isinstance(SETTING_STREAMING_ENABLED, str)
        assert isinstance(SETTING_LOG_MAX_LINES, str)
        assert isinstance(SETTING_WARMUP_ENABLED, str)

    def test_new_setting_constants_are_strings(self) -> None:
        assert isinstance(SETTING_THEME, str)
        assert isinstance(SETTING_SCORE_DISPLAY_FORMAT, str)
        assert isinstance(SETTING_COSINE_ENABLED, str)
        assert isinstance(SETTING_KEYWORD_ENABLED, str)
        assert isinstance(SETTING_COSINE_THRESHOLD_EXACT, str)
        assert isinstance(SETTING_COSINE_THRESHOLD_CONTAINS, str)
        assert isinstance(SETTING_COSINE_THRESHOLD_COVERS, str)
        assert isinstance(SETTING_REASONING_EFFORT_DEFAULT, str)
        assert isinstance(SETTING_AUTO_SCROLL, str)

    def test_new_setting_constant_keys_have_expected_prefixes(self) -> None:
        ui_constants = [
            SETTING_THEME,
            SETTING_SCORE_DISPLAY_FORMAT,
            SETTING_AUTO_SCROLL,
            SETTING_LOG_VERBOSITY,
            SETTING_LOG_MAX_LINES,
        ]
        for key in ui_constants:
            assert key.startswith("ui."), f"{key!r} should start with 'ui.'"

        feature_constants = [
            SETTING_COSINE_ENABLED,
            SETTING_KEYWORD_ENABLED,
            SETTING_REASONING_EFFORT_DEFAULT,
            SETTING_STREAMING_ENABLED,
        ]
        for key in feature_constants:
            assert key.startswith("feature."), f"{key!r} should start with 'feature.'"

        eval_constants = [
            SETTING_COSINE_THRESHOLD_EXACT,
            SETTING_COSINE_THRESHOLD_CONTAINS,
            SETTING_COSINE_THRESHOLD_COVERS,
        ]
        for key in eval_constants:
            assert key.startswith("eval."), f"{key!r} should start with 'eval.'"

        benchmark_constants = [
            SETTING_PAUSE_ON_PROVIDER_SWITCH,
            SETTING_PAUSE_ON_MODEL_SWITCH,
            SETTING_PAUSE_ON_STAGE_SWITCH,
            SETTING_STOP_ON_PROVIDER_ERROR,
            SETTING_WARMUP_ENABLED,
        ]
        for key in benchmark_constants:
            assert key.startswith("benchmark."), f"{key!r} should start with 'benchmark.'"

    def test_default_theme_is_system(self) -> None:
        from ollama_llm_bench.backend.services.app_settings_service import _DEFAULTS

        assert _DEFAULTS[SETTING_THEME] == "system"

    def test_default_reasoning_effort_is_default(self) -> None:
        from ollama_llm_bench.backend.services.app_settings_service import _DEFAULTS

        assert _DEFAULTS[SETTING_REASONING_EFFORT_DEFAULT] == "default"

    def test_default_score_format_is_decimal(self) -> None:
        from ollama_llm_bench.backend.services.app_settings_service import _DEFAULTS

        assert _DEFAULTS[SETTING_SCORE_DISPLAY_FORMAT] == "decimal"

    def test_default_log_verbosity_is_verbose(self) -> None:
        from ollama_llm_bench.backend.services.app_settings_service import _DEFAULTS

        assert _DEFAULTS[SETTING_LOG_VERBOSITY] == "verbose"


class TestDefaultsFallback:
    def test_get_bool_returns_defaults_dict_value_when_row_absent(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        assert service.get_bool(SETTING_WARMUP_ENABLED) is True

    def test_get_bool_db_row_overrides_defaults_dict(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = _make_setting(SETTING_WARMUP_ENABLED, "false")
        assert service.get_bool(SETTING_WARMUP_ENABLED) is False

    def test_get_int_returns_defaults_dict_value_when_row_absent(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        assert service.get_int(SETTING_RETRY_COUNT) == 3

    def test_caller_default_used_only_for_unknown_keys(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        assert service.get(_UNKNOWN_KEY, default="fallback") == "fallback"

    def test_get_returns_defaults_dict_string_value_when_row_absent(
        self, service: AppSettingsService, mock_data_api: MagicMock
    ) -> None:
        mock_data_api.get_app_setting.return_value = None
        assert service.get(SETTING_STREAMING_ENABLED) == "true"
