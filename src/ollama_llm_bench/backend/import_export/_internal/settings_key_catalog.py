"""Hand-authored ``key -> (type, constraint)`` catalogue for settings-import validation.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-G_feature_flags.md``
§§3-9 — the exhaustive per-key type/default/range/enum registry. This module
duplicates that data the same way ``backend/settings/_internal/registry.py``'s
``DEFAULTS`` dict already duplicates the same spec section (this module is not a
declared dependency of ``backend/import_export/`` per
``14_Process_and_Traceability/01_MODULE_INVENTORY.md``, so it cannot import from
there) — same established pattern, extended with type/constraint information the
importer needs to validate a value, not merely default it.

``SettingSpec`` is a strictly private type living only inside this module's
``_internal/`` package and never crossing a module boundary, so a ``dataclass``
is used per the coding-style exception rather than a ``msgspec.Struct``.
"""

from dataclasses import dataclass
from enum import StrEnum

from ollama_llm_bench.backend.domain import SettingKey

__all__: list[str] = ["SETTINGS_CATALOG", "SettingSpec", "SettingValueType"]


class SettingValueType(StrEnum):
    """The logical value type a settings-import value is checked against."""

    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    ENUM = "enum"
    STRING = "string"


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """One registry entry's type and constraint, as needed for import validation."""

    value_type: SettingValueType
    enum_values: frozenset[str] | None = None
    min_value: float | None = None
    max_value: float | None = None
    allow_blank: bool = False


def _bool() -> SettingSpec:
    return SettingSpec(value_type=SettingValueType.BOOL)


def _int(*, minimum: float | None = None, maximum: float | None = None) -> SettingSpec:
    return SettingSpec(value_type=SettingValueType.INT, min_value=minimum, max_value=maximum)


def _float(
    *, minimum: float | None = None, maximum: float | None = None, allow_blank: bool = False
) -> SettingSpec:
    return SettingSpec(
        value_type=SettingValueType.FLOAT,
        min_value=minimum,
        max_value=maximum,
        allow_blank=allow_blank,
    )


def _enum(*values: str) -> SettingSpec:
    return SettingSpec(value_type=SettingValueType.ENUM, enum_values=frozenset(values))


def _string() -> SettingSpec:
    return SettingSpec(value_type=SettingValueType.STRING)


SETTINGS_CATALOG: dict[SettingKey, SettingSpec] = {
    # --- benchmark.* (`08-G` §3) — 12 keys ---
    "benchmark.warmup_enabled": _bool(),
    "benchmark.retry_count": _int(minimum=0, maximum=10),
    "benchmark.max_output_tokens": _int(minimum=256),
    "benchmark.temperature": _float(minimum=0.0, allow_blank=True),
    "benchmark.min_timeout_seconds": _int(minimum=1, maximum=3600),
    "benchmark.max_timeout_seconds": _int(minimum=1, maximum=3600),
    "benchmark.consecutive_max_timeouts_to_exclude": _int(minimum=1),
    "benchmark.pause_on_phase_switch": _bool(),
    "benchmark.pause_on_provider_switch": _bool(),
    "benchmark.pause_on_model_switch": _bool(),
    "benchmark.stop_on_provider_health_failure": _bool(),
    "benchmark.last_mode": _enum("synthetic", "tasks", "graded"),
    # --- feature.* / ui.stream_tokens_to_log (`08-G` §4) — 3 keys ---
    "ui.stream_tokens_to_log": _bool(),
    "feature.reasoning_effort_default": _enum("default", "low", "medium", "high"),
    "feature.judge_run_analysis_enabled": _bool(),
    # --- eval.* (`08-G` §5) — 14 keys ---
    "eval.phase_keyword_enabled": _bool(),
    "eval.phase_cosine_enabled": _bool(),
    "eval.phase_judge_enabled": _bool(),
    "eval.force_judge_on_prior_failure": _bool(),
    "eval.cosine_threshold": _float(minimum=0.0, maximum=1.0),
    "eval.judge_max_completion_tokens": _int(minimum=256),
    "eval.judge_timeout_min_seconds": _int(minimum=1, maximum=3600),
    "eval.judge_timeout_max_seconds": _int(minimum=1, maximum=3600),
    "eval.judge_timeout_escalation_steps": _int(minimum=0, maximum=10),
    "eval.judge_timeout_consecutive_threshold": _int(minimum=1),
    "eval.embedding_timeout_seconds": _int(minimum=1, maximum=3600),
    "eval.min_sample_size": _int(minimum=1),
    "eval.embedding_consecutive_failures_to_skip": _int(minimum=1),
    "eval.min_cosine_coverage": _float(minimum=0.0, maximum=1.0),
    # --- embedding.* (`08-G` §6) — 4 keys ---
    "embedding.selected_provider_name": _string(),
    "embedding.selected_model_name": _string(),
    "embedding.hide_from_test_models": _bool(),
    "embedding.additional_patterns": _string(),
    # --- ui.* (`08-G` §7) — 11 keys ---
    "ui.theme": _enum("system", "dark", "light"),
    "ui.score_display_format": _enum("decimal", "percent", "letter"),
    "ui.window_geometry": _string(),
    "ui.splitter_sizes": _string(),
    "ui.active_workspace": _enum("benchmark", "task_editor"),
    "ui.last_result_tab": _string(),
    "ui.task_editor_last_folder": _string(),
    "ui.export_save_directly": _bool(),
    "ui.run_log_verbosity": _enum("short", "normal", "verbose"),
    "ui.run_log_max_lines": _int(minimum=1000, maximum=500000),
    "ui.auto_scroll_run_log": _bool(),
    # --- logging.* (`08-G` §8) — 5 keys ---
    "logging.write_run_log_to_file": _bool(),
    "logging.write_app_log_to_file": _bool(),
    "logging.app_log_level": _enum("trace", "debug", "info", "warn", "error"),
    "logging.app_log_max_file_mb": _int(minimum=1, maximum=50),
    "logging.app_log_max_total_mb": _int(minimum=1, maximum=200),
    # --- task_editor.* (`08-G` §9) — 2 keys ---
    "task_editor.auto_format_on_save": _bool(),
    "task_editor.warn_on_empty_grading_criteria": _bool(),
}
