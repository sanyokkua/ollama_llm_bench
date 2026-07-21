"""Working-copy + dirty tracking for the General tab, mirroring the dirty-diff
shape already established by ``_internal/providers_tab/controller.py``
(``ProvidersTabController.is_dirty``).
"""

import structlog

from ollama_llm_bench.backend.domain import SettingKey
from ollama_llm_bench.ui.settings_dialog._internal.general_tab.field_binders import FIELD_REGISTRY
from ollama_llm_bench.ui.settings_dialog.models import GeneralFieldState
from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway

__all__: list[str] = ["GeneralTabController"]

_log = structlog.get_logger(__name__)

_DEFAULT_STORAGE_TEXT: dict[SettingKey, str] = {
    "ui.stream_tokens_to_log": "true",
    "feature.reasoning_effort_default": "default",
    "benchmark.temperature": "0.0",
    "benchmark.max_output_tokens": "4096",
    "eval.judge_max_completion_tokens": "4096",
    "benchmark.warmup_enabled": "true",
    "benchmark.retry_count": "3",
    "benchmark.min_timeout_seconds": "300",
    "benchmark.max_timeout_seconds": "900",
    "benchmark.consecutive_max_timeouts_to_exclude": "3",
    "benchmark.pause_on_provider_switch": "false",
    "benchmark.pause_on_model_switch": "false",
    "benchmark.pause_on_phase_switch": "false",
    "benchmark.stop_on_provider_health_failure": "false",
    "eval.phase_keyword_enabled": "true",
    "eval.phase_cosine_enabled": "true",
    "eval.phase_judge_enabled": "true",
    "eval.force_judge_on_prior_failure": "false",
    "eval.cosine_threshold": "0.85",
    "eval.judge_timeout_min_seconds": "20",
    "eval.judge_timeout_max_seconds": "120",
    "eval.judge_timeout_escalation_steps": "2",
    "eval.judge_timeout_consecutive_threshold": "3",
    "eval.embedding_timeout_seconds": "30",
    "feature.judge_run_analysis_enabled": "true",
    "embedding.hide_from_test_models": "true",
    "embedding.additional_patterns": "",
    "ui.theme": "system",
    "ui.score_display_format": "decimal",
    "logging.write_run_log_to_file": "true",
    "ui.run_log_verbosity": "normal",
    "ui.auto_scroll_run_log": "true",
    "ui.run_log_max_lines": "100000",
    "logging.write_app_log_to_file": "true",
    "logging.app_log_level": "info",
    "logging.app_log_max_file_mb": "10",
    "logging.app_log_max_total_mb": "60",
    "ui.task_editor_last_folder": "",
    "task_editor.auto_format_on_save": "true",
    "task_editor.warn_on_empty_grading_criteria": "true",
}


class GeneralTabController:
    """Owns the General tab's in-memory working copy of every registry key."""

    def __init__(self, *, gateway: SettingsGateway) -> None:
        self._gateway = gateway
        self._values: dict[SettingKey, str] = {}
        self._original: dict[SettingKey, str] = {}
        _log.debug("general_tab_controller_constructed")

    def reload(self) -> None:
        """Seed the working copy from the Gateway's resolved current values."""
        stored = self._gateway.list_settings()
        self._original = {
            spec.setting_key: stored.get(spec.setting_key, _DEFAULT_STORAGE_TEXT[spec.setting_key])
            for spec in FIELD_REGISTRY
        }
        self._values = dict(self._original)
        _log.debug("general_tab_reloaded", key_count=len(self._values))

    @property
    def is_dirty(self) -> bool:
        """Whether any working-copy value differs from what was last loaded."""
        return self._values != self._original

    def set_value(self, setting_key: SettingKey, text: str) -> None:
        """Update one key's working-copy text (a user edit on the General tab)."""
        self._values[setting_key] = text
        _log.debug("general_tab_field_edited", setting_key=setting_key)

    def field_states(self) -> tuple[GeneralFieldState, ...]:
        """The current working copy as the view's render-ready field states.

        ``has_error`` stays ``False`` here -- the parent
        ``SettingsController`` merges cross-tab validation findings (from
        ``_internal.validation.validate_all``) back into the pushed
        ``GeneralFieldState`` tuple before handing it to the view; this
        controller does not depend on ``validation.py`` (keeps the two
        concerns separable and each independently testable).
        """
        return tuple(
            GeneralFieldState(setting_key=key, value=value, has_error=False)
            for key, value in self._values.items()
        )

    def values_for_save(self) -> dict[SettingKey, str]:
        """The full working-copy value map, ready for
        ``SettingsGateway.upsert_settings``."""
        return dict(self._values)

    def values_for_reset_defaults(self) -> dict[SettingKey, str]:
        """The full in-code defaults map, for the footer Reset-to-Defaults
        transaction (``sub_dialogs/reset_confirmation.md`` §4)."""
        return dict(_DEFAULT_STORAGE_TEXT)
