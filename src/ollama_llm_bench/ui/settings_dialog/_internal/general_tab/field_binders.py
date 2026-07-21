"""The single place the registry-to-control mapping is declared
(``06_Settings_Dialog/description.md`` §4, ``08_Cross_Cutting/08-G_feature_flags.md``).

Every General-tab control binds to exactly one entry in ``FIELD_REGISTRY``; a
control never exists outside this registry (STORY-067-AC-1).
"""

from dataclasses import dataclass
from enum import StrEnum

from ollama_llm_bench.backend.domain import SettingKey
from ollama_llm_bench.ui.settings_dialog.models import Severity, ValidationFinding

__all__: list[str] = [
    "FIELD_REGISTRY",
    "ControlKind",
    "FieldSpec",
    "GeneralSection",
    "format_for_storage",
    "parse_stored_value",
    "validate_stored_text",
]


class ControlKind(StrEnum):
    """The Qt control family one ``FieldSpec`` binds to."""

    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    FLOAT_OR_BLANK = "float_or_blank"
    ENUM = "enum"
    STRING = "string"
    COMMA_LIST = "comma_list"


class GeneralSection(StrEnum):
    """The General tab's section groupings, top to bottom (``description.md`` §4)."""

    INFERENCE = "inference"
    BENCHMARK_EVENTS = "benchmark_events"
    EVALUATION = "evaluation"
    JUDGE_AND_EMBEDDING_TIMEOUTS = "judge_and_embedding_timeouts"
    RUN_LEVEL_ANALYSIS = "run_level_analysis"
    EMBEDDING_MODELS = "embedding_models"
    DISPLAY = "display"
    LOGGING_RUN = "logging_run"
    LOGGING_APP = "logging_app"
    TASK_EDITOR = "task_editor"


@dataclass(slots=True, frozen=True)
class FieldSpec:
    """A single General-tab control's binding to one registry key.

    Private to ``_internal/general_tab/``; never crosses the settings_dialog
    module boundary, so ``@dataclass`` (not ``msgspec.Struct``) is the correct
    exception per the msgspec-domain-modeling skill.

    Attributes:
        setting_key: The one ``08-G`` registry key this control binds to.
        section: The General-tab section this control renders in.
        label: The control's display label.
        kind: Which Qt control family renders this field.
        int_min: The inclusive lower bound for ``ControlKind.INT``.
        int_max: The inclusive upper bound for ``ControlKind.INT``.
        float_min: The inclusive lower bound for ``ControlKind.FLOAT``/
            ``ControlKind.FLOAT_OR_BLANK``.
        float_max: The inclusive upper bound for ``ControlKind.FLOAT``/
            ``ControlKind.FLOAT_OR_BLANK``.
        enum_choices: The ordered choice list for ``ControlKind.ENUM``.
    """

    setting_key: SettingKey
    section: GeneralSection
    label: str
    kind: ControlKind
    int_min: int | None = None
    int_max: int | None = None
    float_min: float | None = None
    float_max: float | None = None
    enum_choices: tuple[str, ...] = ()


FIELD_REGISTRY: tuple[FieldSpec, ...] = (
    # 4.1 Inference
    FieldSpec(
        "ui.stream_tokens_to_log",
        GeneralSection.INFERENCE,
        "Stream tokens to Log panel",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "feature.reasoning_effort_default",
        GeneralSection.INFERENCE,
        "Default reasoning effort",
        ControlKind.ENUM,
        enum_choices=("default", "low", "medium", "high"),
    ),
    FieldSpec(
        "benchmark.temperature",
        GeneralSection.INFERENCE,
        "Sampling temperature (model under test)",
        ControlKind.FLOAT_OR_BLANK,
        float_min=0.0,
    ),
    FieldSpec(
        "benchmark.max_output_tokens",
        GeneralSection.INFERENCE,
        "Max output tokens (model under test)",
        ControlKind.INT,
        int_min=256,
    ),
    FieldSpec(
        "eval.judge_max_completion_tokens",
        GeneralSection.INFERENCE,
        "Judge max completion tokens",
        ControlKind.INT,
        int_min=256,
    ),
    FieldSpec(
        "benchmark.warmup_enabled",
        GeneralSection.INFERENCE,
        "Enable model warmup",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "benchmark.retry_count",
        GeneralSection.INFERENCE,
        "Retry count (recoverable failures)",
        ControlKind.INT,
        int_min=0,
        int_max=10,
    ),
    FieldSpec(
        "benchmark.min_timeout_seconds",
        GeneralSection.INFERENCE,
        "Inference timeout — minimum (seconds)",
        ControlKind.INT,
        int_min=1,
        int_max=3600,
    ),
    FieldSpec(
        "benchmark.max_timeout_seconds",
        GeneralSection.INFERENCE,
        "Inference timeout — maximum (seconds)",
        ControlKind.INT,
        int_min=1,
        int_max=3600,
    ),
    FieldSpec(
        "benchmark.consecutive_max_timeouts_to_exclude",
        GeneralSection.INFERENCE,
        "Max max-timeout failures before exclusion",
        ControlKind.INT,
        int_min=1,
    ),
    # 4.2 Benchmark Events
    FieldSpec(
        "benchmark.pause_on_provider_switch",
        GeneralSection.BENCHMARK_EVENTS,
        "Pause when moving to the next provider",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "benchmark.pause_on_model_switch",
        GeneralSection.BENCHMARK_EVENTS,
        "Pause when moving to the next model",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "benchmark.pause_on_phase_switch",
        GeneralSection.BENCHMARK_EVENTS,
        "Pause between pipeline stages",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "benchmark.stop_on_provider_health_failure",
        GeneralSection.BENCHMARK_EVENTS,
        "Stop the run if a provider's health check fails",
        ControlKind.BOOL,
    ),
    # 4.3 Evaluation
    FieldSpec(
        "eval.phase_keyword_enabled",
        GeneralSection.EVALUATION,
        "Enable keyword validation",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "eval.phase_cosine_enabled",
        GeneralSection.EVALUATION,
        "Enable cosine similarity validation",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "eval.phase_judge_enabled",
        GeneralSection.EVALUATION,
        "Enable judge validation",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "eval.force_judge_on_prior_failure",
        GeneralSection.EVALUATION,
        "Run the judge even after an earlier phase failed",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "eval.cosine_threshold",
        GeneralSection.EVALUATION,
        "Cosine threshold",
        ControlKind.FLOAT,
        float_min=0.0,
        float_max=1.0,
    ),
    # 4.3a Judge timeouts and embedding timeout
    FieldSpec(
        "eval.judge_timeout_min_seconds",
        GeneralSection.JUDGE_AND_EMBEDDING_TIMEOUTS,
        "Judge timeout — minimum (seconds)",
        ControlKind.INT,
        int_min=1,
        int_max=3600,
    ),
    FieldSpec(
        "eval.judge_timeout_max_seconds",
        GeneralSection.JUDGE_AND_EMBEDDING_TIMEOUTS,
        "Judge timeout — maximum (seconds)",
        ControlKind.INT,
        int_min=1,
        int_max=3600,
    ),
    FieldSpec(
        "eval.judge_timeout_escalation_steps",
        GeneralSection.JUDGE_AND_EMBEDDING_TIMEOUTS,
        "Judge timeout — escalation steps",
        ControlKind.INT,
        int_min=0,
        int_max=10,
    ),
    FieldSpec(
        "eval.judge_timeout_consecutive_threshold",
        GeneralSection.JUDGE_AND_EMBEDDING_TIMEOUTS,
        "Judge timeout — max max-timeout failures before exclusion",
        ControlKind.INT,
        int_min=1,
    ),
    FieldSpec(
        "eval.embedding_timeout_seconds",
        GeneralSection.JUDGE_AND_EMBEDDING_TIMEOUTS,
        "Embedding timeout (fixed, seconds)",
        ControlKind.INT,
        int_min=1,
        int_max=3600,
    ),
    # 4.4 Run-level analysis
    FieldSpec(
        "feature.judge_run_analysis_enabled",
        GeneralSection.RUN_LEVEL_ANALYSIS,
        "Generate run-level analysis with the judge model",
        ControlKind.BOOL,
    ),
    # 4.5 Embedding Models
    FieldSpec(
        "embedding.hide_from_test_models",
        GeneralSection.EMBEDDING_MODELS,
        "Hide embedding-like models from selection lists",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "embedding.additional_patterns",
        GeneralSection.EMBEDDING_MODELS,
        "Additional patterns (comma-separated)",
        ControlKind.COMMA_LIST,
    ),
    # 4.6 Display
    FieldSpec(
        "ui.theme",
        GeneralSection.DISPLAY,
        "Theme",
        ControlKind.ENUM,
        enum_choices=("system", "dark", "light"),
    ),
    FieldSpec(
        "ui.score_display_format",
        GeneralSection.DISPLAY,
        "Score display format",
        ControlKind.ENUM,
        enum_choices=("decimal", "percent", "letter"),
    ),
    # 4.7 Logging — Run Logs
    FieldSpec(
        "logging.write_run_log_to_file",
        GeneralSection.LOGGING_RUN,
        "Write run log to file",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "ui.run_log_verbosity",
        GeneralSection.LOGGING_RUN,
        "Default run-log verbosity",
        ControlKind.ENUM,
        enum_choices=("short", "normal", "verbose"),
    ),
    FieldSpec(
        "ui.auto_scroll_run_log",
        GeneralSection.LOGGING_RUN,
        "Auto-scroll log panel",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "ui.run_log_max_lines",
        GeneralSection.LOGGING_RUN,
        "Run-log buffer (lines)",
        ControlKind.INT,
        int_min=1000,
        int_max=500000,
    ),
    # 4.8 Logging — App Logs
    FieldSpec(
        "logging.write_app_log_to_file",
        GeneralSection.LOGGING_APP,
        "Write app log to file",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "logging.app_log_level",
        GeneralSection.LOGGING_APP,
        "App-log level",
        ControlKind.ENUM,
        enum_choices=("trace", "debug", "info", "warn", "error"),
    ),
    FieldSpec(
        "logging.app_log_max_file_mb",
        GeneralSection.LOGGING_APP,
        "Rotation — max file size (MB)",
        ControlKind.INT,
        int_min=1,
        int_max=50,
    ),
    FieldSpec(
        "logging.app_log_max_total_mb",
        GeneralSection.LOGGING_APP,
        "Rotation — total log budget (MB)",
        ControlKind.INT,
        int_min=1,
        int_max=200,
    ),
    # 4.10 Task Editor
    FieldSpec(
        "ui.task_editor_last_folder",
        GeneralSection.TASK_EDITOR,
        "Default Task Editor folder",
        ControlKind.STRING,
    ),
    FieldSpec(
        "task_editor.auto_format_on_save",
        GeneralSection.TASK_EDITOR,
        "Auto-format YAML on save",
        ControlKind.BOOL,
    ),
    FieldSpec(
        "task_editor.warn_on_empty_grading_criteria",
        GeneralSection.TASK_EDITOR,
        "Warn on empty grading criteria",
        ControlKind.BOOL,
    ),
)


def parse_stored_value(spec: FieldSpec, text: str) -> bool | int | float | str:
    """Convert a key's storage text form into the value its control renders.

    Args:
        spec: The field's registry entry.
        text: The key's current storage text form.

    Returns:
        The typed value the bound Qt control should display.
    """
    if spec.kind is ControlKind.BOOL:
        return text.strip().lower() == "true"
    if spec.kind is ControlKind.INT:
        return int(text) if text.strip() else 0
    if spec.kind is ControlKind.FLOAT:
        return float(text) if text.strip() else 0.0
    # FLOAT_OR_BLANK renders as a QLineEdit (text-native) -- returning the raw
    # text (rather than coercing to a float) preserves blank verbatim instead
    # of collapsing it to 0.0, so format_for_storage can round-trip it exactly.
    return text


def format_for_storage(spec: FieldSpec, *, value: bool | int | float | str) -> str:
    """Convert a control's current value into the key's storage text form.

    Args:
        spec: The field's registry entry.
        value: The control's current typed value.

    Returns:
        The text form persisted via ``SettingsGateway.upsert_settings``.
    """
    if spec.kind is ControlKind.BOOL:
        return "true" if value else "false"
    return str(value)


def validate_stored_text(spec: FieldSpec, text: str) -> ValidationFinding | None:
    """Validate one field's raw stored text against its ``FieldSpec`` constraints
    (``description.md`` §15.1, §15.3 -- EC-SET-3).

    Args:
        spec: The field's registry entry.
        text: The key's current storage text form.

    Returns:
        ``None`` when the text is valid for this field; a ``HARD_ERROR``
        finding otherwise. Blank is valid only for ``FLOAT_OR_BLANK``; every
        other numeric kind treats blank as a hard error (EC-SET-3 -- never
        coerced to zero).
    """
    stripped = text.strip()
    if spec.kind is ControlKind.FLOAT_OR_BLANK and stripped == "":
        return None
    if spec.kind not in (ControlKind.INT, ControlKind.FLOAT, ControlKind.FLOAT_OR_BLANK):
        return None
    if stripped == "":
        return ValidationFinding(
            severity=Severity.HARD_ERROR,
            target=spec.setting_key,
            message=f"{spec.label} is required and cannot be empty.",
        )
    try:
        numeric_value = int(stripped) if spec.kind is ControlKind.INT else float(stripped)
    except ValueError:
        return ValidationFinding(
            severity=Severity.HARD_ERROR,
            target=spec.setting_key,
            message=f"{spec.label} must be a valid number.",
        )
    lower = spec.int_min if spec.kind is ControlKind.INT else spec.float_min
    upper = spec.int_max if spec.kind is ControlKind.INT else spec.float_max
    if (lower is not None and numeric_value < lower) or (
        upper is not None and numeric_value > upper
    ):
        return ValidationFinding(
            severity=Severity.HARD_ERROR,
            target=spec.setting_key,
            message=f"{spec.label} must be between {lower} and {upper}.",
        )
    return None
