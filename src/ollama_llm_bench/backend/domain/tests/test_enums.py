"""Tests proving every ``StrEnum`` in §4 has exactly the members and values it declares.

Table-driven across all 29 enums this story owns (the two EventBus-local enums —
``DriftSeverity``, ``DriftKind`` — are owned by STORY-003 and excluded here).
``RunLogVerbosity`` and ``RunLogEventKind`` (§7.7) are added by STORY-036, which folded the
missing run-log DTOs into ``backend/domain/`` as an approved gap-fix ahead of its own
``log_formatting`` scope. Each row asserts the member count and the exact ordered
``(name, value)`` pairs, verbatim against ``02_DTOS_AND_ENUMS.md`` §4 / §7.7.
"""

from enum import StrEnum
from typing import Any

import pytest

from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    AttemptOutcome,
    CancelLevel,
    CancelReason,
    CapabilitySource,
    ChartKind,
    ChatRole,
    Difficulty,
    ErrorKind,
    InferenceActivity,
    InferenceContext,
    InferenceTestOutcome,
    ModelCapability,
    ModelRole,
    ProviderTestStatus,
    ProviderType,
    ReadinessState,
    ReasoningEffort,
    ResolutionLayer,
    ResponseFormat,
    ResultStatus,
    ResultTermKind,
    RunLogEventKind,
    RunLogVerbosity,
    RunMode,
    RunStatus,
    TaskOrigin,
    TaskTermKind,
    Verdict,
)

# (enum type, expected ordered (name, value) pairs)
_CASES: tuple[tuple[type[StrEnum], tuple[tuple[str, str], ...]], ...] = (
    (RunMode, (("SYNTHETIC", "synthetic"), ("TASKS", "tasks"), ("GRADED", "graded"))),
    (
        RunStatus,
        (
            ("INCOMPLETE", "incomplete"),
            ("COMPLETED", "completed"),
            ("FAILED", "failed"),
            ("STOPPED", "stopped"),
        ),
    ),
    (
        ResultStatus,
        (
            ("PENDING", "pending"),
            ("RUNNING_INFERENCE", "running_inference"),
            ("AWAITING_KEYWORD_CHECK", "awaiting_keyword_check"),
            ("AWAITING_COSINE_CHECK", "awaiting_cosine_check"),
            ("AWAITING_JUDGE_CHECK", "awaiting_judge_check"),
            ("COMPLETED", "completed"),
            ("FAILED_INFERENCE", "failed_inference"),
            ("FAILED_PROVIDER", "failed_provider"),
            ("FAILED_TIMEOUT", "failed_timeout"),
            ("FAILED_JUDGE_TIMEOUT", "failed_judge_timeout"),
            ("ERRORED", "errored"),
        ),
    ),
    (Verdict, (("PASS", "pass"), ("FAIL", "fail"))),
    (
        ResolutionLayer,
        (
            ("KEYWORD", "keyword"),
            ("COSINE", "cosine"),
            ("JUDGE", "judge"),
            ("SKIP", "skip"),
        ),
    ),
    (Difficulty, (("EASY", "easy"), ("MEDIUM", "medium"), ("HARD", "hard"))),
    (
        ProviderType,
        (
            ("OPENAI_COMPATIBLE", "openai_compatible"),
            ("ANTHROPIC", "anthropic"),
            ("GEMINI", "gemini"),
        ),
    ),
    (
        ProviderTestStatus,
        (
            ("UNTESTED", "untested"),
            ("READY", "ready"),
            ("ZERO_MODELS", "zero_models"),
            ("UNREACHABLE", "unreachable"),
            ("MISSING_ENV", "missing_env"),
            ("TESTING", "testing"),
        ),
    ),
    (
        ModelRole,
        (("TEST", "test"), ("JUDGE", "judge"), ("EMBEDDING", "embedding")),
    ),
    (
        AdaptiveTimeoutRole,
        (("INFERENCE", "inference"), ("JUDGE", "judge"), ("RUN_ANALYSIS", "run_analysis")),
    ),
    (TaskOrigin, (("FILE", "file"), ("SYNTHETIC", "synthetic"))),
    (
        TaskTermKind,
        (("EXACT", "exact"), ("SEMANTIC", "semantic"), ("FORBIDDEN", "forbidden")),
    ),
    (
        ResultTermKind,
        (
            ("EXACT_MISSING", "exact_missing"),
            ("FORBIDDEN_FOUND", "forbidden_found"),
            ("SEMANTIC", "semantic"),
        ),
    ),
    (
        ModelCapability,
        (
            ("STREAMING", "streaming"),
            ("REASONING_EFFORT", "reasoning_effort"),
            ("THINKING", "thinking"),
        ),
    ),
    (
        CapabilitySource,
        (("PROBE", "probe"), ("INFERENCE", "inference"), ("MANUAL", "manual")),
    ),
    (
        ErrorKind,
        (
            ("LLM", "llm"),
            ("PROVIDER", "provider"),
            ("TIMEOUT", "timeout"),
            ("JUDGE_TIMEOUT", "judge_timeout"),
            ("OTHER", "other"),
        ),
    ),
    (
        AttemptOutcome,
        (("SUCCESS", "success"), ("TIMEOUT", "timeout"), ("ERROR", "error")),
    ),
    (
        InferenceActivity,
        (
            ("IDLE", "idle"),
            ("BENCHMARK_RUN", "benchmark_run"),
            ("JUDGE_ANALYSIS", "judge_analysis"),
            ("PROVIDER_TEST", "provider_test"),
            ("READINESS_PROBE", "readiness_probe"),
        ),
    ),
    (
        ChartKind,
        (
            ("AVG_TTFT_PER_MODEL", "avg_ttft_per_model"),
            ("AVG_TPS_PER_MODEL", "avg_tps_per_model"),
            ("AVG_TIME_PER_MODEL", "avg_time_per_model"),
            ("SUCCESS_FAILED_INCOMPLETE_STACKED", "success_failed_incomplete_stacked"),
            ("PASS_RATE_BY_MODEL", "pass_rate_by_model"),
            ("AVG_COSINE_BY_MODEL", "avg_cosine_by_model"),
            ("VERDICT_COUNTS_STACKED", "verdict_counts_stacked"),
            ("TIME_VS_TOKENS_SCATTER", "time_vs_tokens_scatter"),
            ("HEATMAP_TASK_BY_MODEL", "heatmap_task_by_model"),
            ("PER_CATEGORY_BAR", "per_category_bar"),
            ("SPEED_VS_QUALITY_SCATTER", "speed_vs_quality_scatter"),
            ("TOKENS_PER_TASK_BOX", "tokens_per_task_box"),
        ),
    ),
    (
        InferenceContext,
        (
            ("BENCHMARK_TASK", "benchmark_task"),
            ("BENCHMARK_JUDGE", "benchmark_judge"),
            ("RUN_ANALYSIS", "run_analysis"),
            ("PROVIDER_TEST", "provider_test"),
        ),
    ),
    (
        InferenceTestOutcome,
        (
            ("SUCCESS", "success"),
            ("REACHABILITY_FAILED", "reachability_failed"),
            ("AUTH_FAILED", "auth_failed"),
            ("MODEL_NOT_FOUND", "model_not_found"),
            ("TIMEOUT", "timeout"),
            ("PROVIDER_ERROR", "provider_error"),
            ("GATE_BUSY", "gate_busy"),
        ),
    ),
    (CancelLevel, (("NONE", "none"), ("SOFT", "soft"), ("HARD", "hard"))),
    (
        CancelReason,
        (
            ("USER_PAUSE", "user_pause"),
            ("AUTO_PAUSE", "auto_pause"),
            ("USER_STOP", "user_stop"),
            ("APP_SHUTDOWN", "app_shutdown"),
        ),
    ),
    (
        ReadinessState,
        (
            ("READY", "ready"),
            ("DEGRADED", "degraded"),
            ("NOT_READY", "not_ready"),
            ("CHECKING", "checking"),
        ),
    ),
    (ChatRole, (("SYSTEM", "system"), ("USER", "user"), ("ASSISTANT", "assistant"))),
    (
        ReasoningEffort,
        (
            ("DEFAULT", "default"),
            ("LOW", "low"),
            ("MEDIUM", "medium"),
            ("HIGH", "high"),
        ),
    ),
    (ResponseFormat, (("TEXT", "text"), ("JSON", "json"))),
    (
        RunLogVerbosity,
        (("SHORT", "short"), ("NORMAL", "normal"), ("VERBOSE", "verbose")),
    ),
    (
        RunLogEventKind,
        (
            ("STAGE", "stage"),
            ("SYSTEM", "system"),
            ("TASK_START", "task_start"),
            ("DONE", "done"),
            ("JUDGE", "judge"),
            ("RETRY", "retry"),
            ("PROVIDER_SWITCH", "provider_switch"),
            ("MODEL_SWITCH", "model_switch"),
            ("STOPPED", "stopped"),
            ("FINISHED", "finished"),
            ("FAILED", "failed"),
        ),
    ),
)

_IDS = [enum_type.__name__ for enum_type, _ in _CASES]


@pytest.mark.parametrize(("enum_type", "expected_pairs"), _CASES, ids=_IDS)
def test_enum_members_and_values_are_total(
    enum_type: type[StrEnum], expected_pairs: tuple[tuple[str, str], ...]
) -> None:
    """Proves: STORY-001-AC-2

    Each ``StrEnum`` in §4 has exactly the members and string values declared for it —
    no member missing, none added, and no value drift.
    """
    # Act
    actual_pairs: tuple[tuple[str, Any], ...] = tuple(
        (member.name, member.value) for member in enum_type
    )

    # Assert
    assert actual_pairs == expected_pairs
