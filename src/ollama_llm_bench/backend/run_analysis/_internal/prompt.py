"""The mode-aware analysis prompt (§6.3)."""

from typing import Final

from ollama_llm_bench.backend.domain import (
    ChatMessage,
    ChatRequest,
    ChatRole,
    ModelName,
    ResponseFormat,
    RunMode,
)
from ollama_llm_bench.backend.run_analysis._internal.aggregation import RunDigest

__all__: list[str] = ["build_analysis_request"]

_SYSTEM_PROMPT: Final[str] = (
    "You are a benchmark analyst. Write concise, factual prose summarizing the "
    "benchmark run digest provided by the user. Produce Markdown using exactly "
    "this section structure: `## Overview`, `## Per-model observations` (one "
    "`### <provider>/<model>` sub-heading per test model), and `## Notable tasks`. "
    "Omit a section entirely when there is nothing to report for it. Invent no "
    "data beyond what the digest provides. Produce no numeric judge score — the "
    "Cosine Score already present in the digest is the only numeric quality "
    "value that may appear."
)

_FRAMING_LINES: Final[dict[RunMode, str]] = {
    RunMode.GRADED: (
        "Emphasize quality outcomes: pass rates, Cosine Scores, where and why "
        "models failed, and any layer disagreements."
    ),
    RunMode.TASKS: (
        "Emphasize throughput and latency comparison across models; there are "
        "no verdicts to discuss."
    ),
    RunMode.SYNTHETIC: (
        "Emphasize how latency and throughput scale across the input/output "
        "size grid; there are no real tasks, verdicts, or categories."
    ),
}


def build_analysis_request(
    digest: RunDigest, *, run_mode: RunMode, model_name: ModelName, timeout_ms: int
) -> ChatRequest:
    """Build the single chat request for the analysis model call (§6.3).

    Args:
        digest: The run's bounded digest.
        run_mode: Selects the framing line appended to the user message.
        model_name: The chosen analysis model.
        timeout_ms: The per-attempt time budget.

    Returns:
        A ``ChatRequest`` with ``response_format=TEXT`` and exactly one system
        and one user message.
    """
    return ChatRequest(
        model=model_name,
        messages=(
            ChatMessage(role=ChatRole.SYSTEM, content=_SYSTEM_PROMPT),
            ChatMessage(role=ChatRole.USER, content=_render_user_message(digest, run_mode)),
        ),
        timeout_ms=timeout_ms,
        response_format=ResponseFormat.TEXT,
    )


def _render_user_message(digest: RunDigest, run_mode: RunMode) -> str:
    sections = [
        _render_facts(digest),
        _render_per_model(digest),
        _render_per_category(digest),
        _render_notable_results(digest),
        _FRAMING_LINES[run_mode],
    ]
    return "\n\n".join(section for section in sections if section)


def _render_facts(digest: RunDigest) -> str:
    facts = digest.facts
    lines = [
        "Run facts:",
        f"- mode: {facts.run_mode.value}",
        f"- test models: {', '.join(facts.test_model_labels) or 'none'}",
        f"- judge model: {facts.judge_model_label}",
        f"- embedding model: {facts.embedding_model_label}",
        f"- started_at: {facts.started_at or 'unknown'}",
        f"- finished_at: {facts.finished_at or 'unknown'}",
        f"- total_elapsed_ms: {facts.total_elapsed_ms}",
        f"- total_tasks: {facts.total_tasks}",
        f"- completed_tasks: {facts.completed_tasks}",
    ]
    return "\n".join(lines)


def _render_per_model(digest: RunDigest) -> str:
    if not digest.per_model:
        return ""
    lines = ["Per-model:"]
    for row in digest.per_model:
        lines.append(
            f"- {row.label}: tasks={row.task_count} completed={row.completed_count} "
            f"errors={row.error_count} mean_ttft_ms={row.mean_ttft_ms} "
            f"mean_total_time_ms={row.mean_total_time_ms} "
            f"mean_tokens_per_second={row.mean_tokens_per_second} "
            f"pass_count={row.pass_count} fail_count={row.fail_count} "
            f"pass_rate={row.pass_rate} mean_cosine_similarity={row.mean_cosine_similarity} "
            f"resolution_layer_counts={row.resolution_layer_counts}"
        )
    return "\n".join(lines)


def _render_per_category(digest: RunDigest) -> str:
    if not digest.per_category:
        return ""
    lines = ["Per-category:"]
    for row in digest.per_category:
        lines.append(f"- {row.category}: pass_rate={row.pass_rate} result_count={row.result_count}")
    return "\n".join(lines)


def _render_notable_results(digest: RunDigest) -> str:
    if not digest.notable_results:
        return ""
    lines = ["Notable results:"]
    for entry in digest.notable_results:
        lines.append(
            f"- task={entry.task_id} model={entry.provider_id}/{entry.model_name} "
            f"verdict={entry.verdict} note={entry.note}"
        )
    return "\n".join(lines)
