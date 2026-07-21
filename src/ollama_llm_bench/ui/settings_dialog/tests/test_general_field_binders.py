"""Proves: STORY-067-AC-1

Confirms every General-tab control binds to exactly one registry key and
round-trips its value through that key's storage text form.
"""

import pytest

from ollama_llm_bench.ui.settings_dialog._internal.general_tab.field_binders import (
    FIELD_REGISTRY,
    ControlKind,
    FieldSpec,
    format_for_storage,
    parse_stored_value,
    validate_stored_text,
)
from ollama_llm_bench.ui.settings_dialog.models import Severity


def test_field_registry_has_no_duplicate_setting_keys() -> None:
    keys = [spec.setting_key for spec in FIELD_REGISTRY]
    assert len(keys) == len(set(keys))


def test_field_registry_covers_every_documented_general_tab_key() -> None:
    expected_keys = {
        "ui.stream_tokens_to_log",
        "feature.reasoning_effort_default",
        "benchmark.temperature",
        "benchmark.max_output_tokens",
        "eval.judge_max_completion_tokens",
        "benchmark.warmup_enabled",
        "benchmark.retry_count",
        "benchmark.min_timeout_seconds",
        "benchmark.max_timeout_seconds",
        "benchmark.consecutive_max_timeouts_to_exclude",
        "benchmark.pause_on_provider_switch",
        "benchmark.pause_on_model_switch",
        "benchmark.pause_on_phase_switch",
        "benchmark.stop_on_provider_health_failure",
        "eval.phase_keyword_enabled",
        "eval.phase_cosine_enabled",
        "eval.phase_judge_enabled",
        "eval.force_judge_on_prior_failure",
        "eval.cosine_threshold",
        "eval.judge_timeout_min_seconds",
        "eval.judge_timeout_max_seconds",
        "eval.judge_timeout_escalation_steps",
        "eval.judge_timeout_consecutive_threshold",
        "eval.embedding_timeout_seconds",
        "feature.judge_run_analysis_enabled",
        "embedding.hide_from_test_models",
        "embedding.additional_patterns",
        "ui.theme",
        "ui.score_display_format",
        "logging.write_run_log_to_file",
        "ui.run_log_verbosity",
        "ui.auto_scroll_run_log",
        "ui.run_log_max_lines",
        "logging.write_app_log_to_file",
        "logging.app_log_level",
        "logging.app_log_max_file_mb",
        "logging.app_log_max_total_mb",
        "ui.task_editor_last_folder",
        "task_editor.auto_format_on_save",
        "task_editor.warn_on_empty_grading_criteria",
    }
    actual_keys = {spec.setting_key for spec in FIELD_REGISTRY}
    assert actual_keys == expected_keys


@pytest.mark.parametrize("spec", FIELD_REGISTRY, ids=lambda spec: spec.setting_key)
def test_every_field_round_trips_a_representative_value(spec: FieldSpec) -> None:
    if spec.kind is ControlKind.BOOL:
        sample_text = "true"
    elif spec.kind is ControlKind.INT:
        sample_text = str(spec.int_min if spec.int_min is not None else 1)
    elif spec.kind is ControlKind.FLOAT_OR_BLANK:
        sample_text = ""
    elif spec.kind is ControlKind.FLOAT:
        sample_text = str(spec.float_min if spec.float_min is not None else 0.0)
    elif spec.kind is ControlKind.ENUM:
        sample_text = spec.enum_choices[0]
    else:
        sample_text = "sample"

    value = parse_stored_value(spec, sample_text)
    round_tripped = format_for_storage(spec, value=value)
    assert round_tripped == sample_text or (sample_text == "" and round_tripped == "")


def test_cleared_numeric_field_is_a_hard_error_never_zero() -> None:
    spec = next(
        spec for spec in FIELD_REGISTRY if spec.setting_key == "benchmark.min_timeout_seconds"
    )

    finding = validate_stored_text(spec, "")

    assert finding is not None
    assert finding.severity is Severity.HARD_ERROR
    assert "empty" in finding.message.lower() or "required" in finding.message.lower()


def test_out_of_range_int_is_a_hard_error() -> None:
    spec = next(
        spec for spec in FIELD_REGISTRY if spec.setting_key == "benchmark.min_timeout_seconds"
    )

    finding = validate_stored_text(spec, "9999")

    assert finding is not None
    assert finding.severity is Severity.HARD_ERROR


def test_cosine_threshold_out_of_0_to_1_is_a_hard_error() -> None:
    spec = next(spec for spec in FIELD_REGISTRY if spec.setting_key == "eval.cosine_threshold")

    finding = validate_stored_text(spec, "1.5")

    assert finding is not None
    assert finding.severity is Severity.HARD_ERROR


def test_blank_temperature_is_allowed_no_finding() -> None:
    spec = next(spec for spec in FIELD_REGISTRY if spec.setting_key == "benchmark.temperature")

    finding = validate_stored_text(spec, "")

    assert finding is None
