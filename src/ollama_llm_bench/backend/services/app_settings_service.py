"""AppSettingsService — typed key-value store backed by the app_settings SQLite table."""

import logging

from ollama_llm_bench.backend.core.interfaces import DataApi

logger = logging.getLogger(__name__)

SETTING_PAUSE_ON_PROVIDER_SWITCH: str = "benchmark.pause_on_provider_switch"
SETTING_PAUSE_ON_MODEL_SWITCH: str = "benchmark.pause_on_model_switch"
SETTING_PAUSE_ON_STAGE_SWITCH: str = "benchmark.pause_on_stage_switch"
SETTING_STOP_ON_PROVIDER_ERROR: str = "benchmark.stop_on_provider_error"
SETTING_STREAMING_ENABLED: str = "feature.streaming_enabled"
SETTING_LOG_TO_FILE: str = "feature.log_to_file"
SETTING_LOG_VERBOSITY: str = "ui.log_verbosity"
SETTING_LOG_MAX_LINES: str = "ui.log_max_lines"
SETTING_WARMUP_ENABLED: str = "benchmark.warmup_enabled"
SETTING_THEME: str = "ui.theme"  # "system" / "dark" / "light"; default "system"
SETTING_SCORE_DISPLAY_FORMAT: str = "ui.score_display_format"  # "decimal"/"percent"/"both"; default "decimal"
SETTING_COSINE_ENABLED: str = "feature.cosine_enabled"  # "true"/"false"; default "true"
SETTING_KEYWORD_ENABLED: str = "feature.keyword_enabled"  # "true"/"false"; default "true"
SETTING_COSINE_THRESHOLD_EXACT: str = "eval.cosine_threshold_exact"  # float as str; default "0.9"
SETTING_COSINE_THRESHOLD_CONTAINS: str = "eval.cosine_threshold_contains"  # float as str; default "0.7"
SETTING_COSINE_THRESHOLD_COVERS: str = "eval.cosine_threshold_covers"  # float as str; default "0.6"
SETTING_REASONING_EFFORT_DEFAULT: str = (
    "feature.reasoning_effort_default"  # "default"/"low"/"medium"/"high"; default "default"
)
SETTING_AUTO_SCROLL: str = "ui.auto_scroll"  # "true"/"false"; default "true"
SETTING_EMBEDDING_FILTER_ENABLED: str = "embedding.filter_enabled"  # "true"/"false"; default "false"
SETTING_EMBEDDING_CUSTOM_PATTERNS: str = "embedding.custom_patterns"  # comma-separated; default ""
SETTING_TASK_TIMEOUT_S: str = (
    "benchmark.task_timeout_s"  # int seconds; kept for backward compat, no longer used by engine
)
SETTING_RETRY_COUNT: str = "benchmark.retry_count"  # int; default 3
SETTING_RETRY_TIMEOUT_MIN_S: str = "benchmark.retry_timeout_min_s"  # int seconds; default 300 (5 min)
SETTING_RETRY_TIMEOUT_MAX_S: str = "benchmark.retry_timeout_max_s"  # int seconds; default 900 (15 min)
SETTING_RETRY_MAX_FAILURES_TO_EXCLUDE: str = "benchmark.retry_max_failures_to_exclude"
SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL: str = "feature.judge_override_keyword_fail"
SETTING_JUDGE_OVERRIDE_COSINE_LOW: str = "feature.judge_override_cosine_low"
SETTING_JUDGE_RUN_ANALYSIS_ENABLED: str = "feature.judge_run_analysis_enabled"
SETTING_PROVIDER_TRIP_THRESHOLD: str = "benchmark.provider_trip_threshold"
SETTING_PROVIDER_TRIP_WINDOW_S: str = "benchmark.provider_trip_window_s"
SETTING_PROVIDER_TRIP_PROBE_INTERVAL_S: str = "benchmark.provider_trip_probe_s"
SETTING_PROVIDER_STOP_ON_TRIP: str = "benchmark.provider_stop_on_trip"

_DEFAULTS: dict[str, str] = {
    SETTING_PAUSE_ON_PROVIDER_SWITCH: "false",
    SETTING_PAUSE_ON_MODEL_SWITCH: "false",
    SETTING_PAUSE_ON_STAGE_SWITCH: "false",
    SETTING_STOP_ON_PROVIDER_ERROR: "false",
    SETTING_STREAMING_ENABLED: "true",
    SETTING_LOG_TO_FILE: "false",
    SETTING_LOG_VERBOSITY: "verbose",
    SETTING_LOG_MAX_LINES: "10000",
    SETTING_WARMUP_ENABLED: "true",
    SETTING_THEME: "system",
    SETTING_SCORE_DISPLAY_FORMAT: "decimal",
    SETTING_COSINE_ENABLED: "true",
    SETTING_KEYWORD_ENABLED: "true",
    SETTING_COSINE_THRESHOLD_EXACT: "0.90",
    SETTING_COSINE_THRESHOLD_CONTAINS: "0.70",
    SETTING_COSINE_THRESHOLD_COVERS: "0.60",
    SETTING_REASONING_EFFORT_DEFAULT: "default",
    SETTING_AUTO_SCROLL: "true",
    SETTING_EMBEDDING_FILTER_ENABLED: "false",
    SETTING_EMBEDDING_CUSTOM_PATTERNS: "",
    SETTING_RETRY_COUNT: "3",
    SETTING_RETRY_TIMEOUT_MIN_S: "300",
    SETTING_RETRY_TIMEOUT_MAX_S: "900",
    SETTING_RETRY_MAX_FAILURES_TO_EXCLUDE: "3",
    SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL: "false",
    SETTING_JUDGE_OVERRIDE_COSINE_LOW: "false",
    SETTING_JUDGE_RUN_ANALYSIS_ENABLED: "false",
    SETTING_PROVIDER_TRIP_THRESHOLD: "3",
    SETTING_PROVIDER_TRIP_WINDOW_S: "600",
    SETTING_PROVIDER_TRIP_PROBE_INTERVAL_S: "60",
    SETTING_PROVIDER_STOP_ON_TRIP: "true",
}


class AppSettingsService:
    """Typed key-value store wrapping the app_settings table.

    Delegates raw persistence to DataApi and adds type-conversion helpers
    for boolean and integer settings consumed by the benchmark pipeline.
    """

    def __init__(self, *, data_api: DataApi) -> None:
        self._data_api = data_api
        self._migrate_legacy_force_judge_keys()

    def _migrate_legacy_force_judge_keys(self) -> None:
        _LEGACY_MAP: dict[str, str] = {
            "eval.force_judge_on_keyword_fail": SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL,
            "eval.force_judge_on_cosine": SETTING_JUDGE_OVERRIDE_COSINE_LOW,
            "eval.force_judge_on_run_analysis": SETTING_JUDGE_RUN_ANALYSIS_ENABLED,
        }
        for old_key, new_key in _LEGACY_MAP.items():
            old_setting = self._data_api.get_app_setting(old_key)
            if old_setting is None:
                continue
            new_setting = self._data_api.get_app_setting(new_key)
            if new_setting is None:
                self._data_api.set_app_setting(key=new_key, value=old_setting.value)

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the stored string value for key, or default if not found."""
        setting = self._data_api.get_app_setting(key)
        if setting is not None:
            return setting.value
        if key in _DEFAULTS:
            return _DEFAULTS[key]
        return default

    def set(self, key: str, value: str) -> None:
        """Persist a string value for key, creating or updating the row."""
        self._data_api.set_app_setting(key=key, value=value)

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Return True only when the stored value (case-insensitive) equals "true"."""
        raw = self.get(key)
        if raw is None:
            return default
        return raw.lower() == "true"

    def get_int(self, key: str, default: int = 0) -> int:
        """Return the stored value parsed as int, or default on absence or parse failure."""
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            logger.warning("invalid_int_setting", extra={"key": key, "value": raw})
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Return the stored value parsed as float, or default on absence or parse failure."""
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            logger.warning("invalid_float_setting", extra={"key": key, "value": raw})
            return default

    def reset_to_defaults(self) -> None:
        """Reset all settings to their default values."""
        for key, value in _DEFAULTS.items():
            self.set(key, value)
