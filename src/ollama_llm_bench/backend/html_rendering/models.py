"""DTOs for the HTML Rendering Service (`20_HTML_RENDERING.md` §2.2)."""

from enum import StrEnum

import msgspec

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    Iso8601Utc,
    ModelNameStr,
    NonEmptyStr,
    ProviderIdStr,
    RunMode,
    TaskIdStr,
)


class UiTheme(StrEnum):
    """The two application themes (§2.2)."""

    LIGHT = "light"
    DARK = "dark"


class LogSeverity(StrEnum):
    """The five event-log line severities (§2.2)."""

    DEBUG = "debug"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class LogEntry(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One event-log line to render (§2.2). Fed one at a time; never accumulated."""

    timestamp: Iso8601Utc
    severity: LogSeverity
    message: NonEmptyStr
    provider_id: ProviderIdStr | None = None
    model_name: ModelNameStr | None = None
    task_id: TaskIdStr | None = None


class ResultDetailRenderRequest(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The pairing of a result and its executed task to render as the detail
    fragment (§2.2).

    `run_mode` lets the renderer omit sections that are meaningless for the mode
    (for example, the grading sections for a `SYNTHETIC` run).
    """

    result: BenchmarkResult
    task: BenchmarkTask
    run_mode: RunMode
