"""Ordered `(header, extractor)` column descriptors (`19_TABLE_SERIALIZATION.md` §6.6).

The CSV and Markdown paths of a given table iterate the **same** descriptor tuple,
which structurally guarantees the two formats never drift apart (the column-order
invariant, AC-1). Each extractor returns the *rendered* (not yet escaped) cell
string; format-specific escaping is applied afterward by the writer modules.
"""

from collections.abc import Callable

from ollama_llm_bench.backend.csv_export._internal.cell_rendering import (
    render_count,
    render_duration_ms_as_seconds,
    render_optional_str,
    render_ratio,
    render_seconds,
    render_tps,
)
from ollama_llm_bench.backend.csv_export._internal.verdict_rendering import render_verdict
from ollama_llm_bench.backend.csv_export.models import SummaryRow
from ollama_llm_bench.backend.domain import BenchmarkResult, BenchmarkTask

type SummaryColumnDescriptor = tuple[str, Callable[[SummaryRow], str]]
type DetailsColumnDescriptor = tuple[str, Callable[[BenchmarkResult, BenchmarkTask], str]]

SUMMARY_COLUMNS: tuple[SummaryColumnDescriptor, ...] = (
    ("Provider", lambda row: row.provider_name),
    ("Model", lambda row: row.model_name),
    ("Tasks", lambda row: render_count(row.task_count)),
    ("Completed", lambda row: render_count(row.completed_count)),
    ("Passed", lambda row: render_count(row.passed_count)),
    ("Failed", lambda row: render_count(row.failed_count)),
    ("Pass Rate", lambda row: render_ratio(row.pass_rate)),
    ("Avg Score", lambda row: render_ratio(row.avg_score)),
    ("Avg Cosine", lambda row: render_ratio(row.avg_cosine)),
    ("Avg TTFT (s)", lambda row: render_seconds(row.avg_ttft_s)),
    ("Avg Total Time (s)", lambda row: render_seconds(row.avg_total_time_s)),
    ("Avg TPS", lambda row: render_tps(row.avg_tps, estimated=False)),
    ("Errors", lambda row: render_count(row.error_count)),
)
"""The fixed 13-column Summary descriptor (`05_EXPORT_FORMATS.md` §4)."""


def _render_details_verdict(result: BenchmarkResult, _task: BenchmarkTask) -> str:
    return render_verdict(result)


def _render_resolution_layer(result: BenchmarkResult, _task: BenchmarkTask) -> str:
    return result.resolution_layer.value if result.resolution_layer is not None else ""


def _render_details_tps(result: BenchmarkResult, _task: BenchmarkTask) -> str:
    return render_tps(result.tokens_per_second, estimated=result.tokens_estimated)


DETAILS_COLUMNS: tuple[DetailsColumnDescriptor, ...] = (
    ("Task Id", lambda result, _task: result.task_id),
    ("Category", lambda _result, task: task.category),
    ("Sub Category", lambda _result, task: task.sub_category),
    ("Difficulty", lambda _result, task: task.difficulty.value),
    ("Provider", lambda result, _task: result.provider_name),
    ("Model", lambda result, _task: result.model_name),
    ("Verdict", _render_details_verdict),
    ("Score", lambda _result, _task: ""),
    ("Cosine", lambda result, _task: render_ratio(result.cosine_similarity)),
    ("Resolution Layer", _render_resolution_layer),
    ("TTFT (s)", lambda result, _task: render_duration_ms_as_seconds(result.ttft_ms)),
    (
        "Total Time (s)",
        lambda result, _task: render_duration_ms_as_seconds(result.total_time_ms),
    ),
    ("TPS", _render_details_tps),
    ("Prompt Tokens", lambda result, _task: render_count(result.prompt_tokens)),
    ("Response Tokens", lambda result, _task: render_count(result.completion_tokens)),
    ("Error", lambda result, _task: render_optional_str(result.error_message)),
    ("Response", lambda result, _task: render_optional_str(result.sanitized_response)),
)
"""The fixed 17-column Details descriptor (`05_EXPORT_FORMATS.md` §6).

Column 8 (``Score``) is always empty: this application's judge produces no
numeric score (reserved column, same contract as the Summary ``Avg Score``
column). Column 17 (``Response``) holds ``sanitized_response`` verbatim.
"""
