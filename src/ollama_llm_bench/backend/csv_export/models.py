"""Request DTOs for the Table Serialization Service (`19_TABLE_SERIALIZATION.md` §2.2)."""

from enum import StrEnum

import msgspec

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    Iso8601Utc,
    ModelNameStr,
    NonEmptyStr,
    NonNegativeInt,
    ProviderIdStr,
    RunId,
    RunMode,
    TaskIdStr,
)


class ExportKind(StrEnum):
    """The two table export kinds this module serializes (`05_EXPORT_FORMATS.md` §1).

    ``RunAnalysis`` and ``Chart_*`` kinds are out of scope for this module; they are
    owned by ``backend/run_analysis/`` and ``backend/charts/`` respectively.
    """

    SUMMARY = "Summary"
    DETAILS = "Details"


class RunExportContext(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Caller-resolved run identity carried into every serialized export (§2.2).

    The caller has already resolved the effective run name; this service never
    derives it from ``run_id``.
    """

    run_id: RunId
    effective_run_name: NonEmptyStr
    run_mode: RunMode
    exported_at: Iso8601Utc
    app_version: NonEmptyStr


class SummaryRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One aggregated ``(provider, model)`` row of the Summary table (§2.2, `05_EXPORT_FORMATS.md` §4).

    ``provider_name`` is the SNAPSHOT display name (DD-33) written to the ``Provider``
    column; the internal ``provider_id`` never appears in any export column.
    ``avg_score`` is reserved and always ``None`` — this application's judge produces
    no numeric score.
    """

    provider_id: ProviderIdStr
    provider_name: NonEmptyStr
    model_name: ModelNameStr
    task_count: NonNegativeInt
    completed_count: NonNegativeInt
    passed_count: NonNegativeInt
    failed_count: NonNegativeInt
    pass_rate: float | None
    avg_score: float | None
    avg_cosine: float | None
    avg_ttft_s: float | None
    avg_total_time_s: float | None
    avg_tps: float | None
    error_count: NonNegativeInt


class SummarySerializationRequest(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Request to serialize the Summary table (§2.2)."""

    context: RunExportContext
    rows: tuple[SummaryRow, ...]


class DetailsSerializationRequest(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Request to serialize the Details table (§2.2).

    ``tasks_by_id`` must carry an entry for every distinct ``task_id`` present in
    ``results`` — a missing entry is a programmer error (§8), surfaced as a raw
    ``KeyError`` from the lookup, not a taxonomy leaf.
    """

    context: RunExportContext
    results: tuple[BenchmarkResult, ...]
    tasks_by_id: dict[TaskIdStr, BenchmarkTask]
