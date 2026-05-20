"""HTML renderer for BenchmarkResult task detail views."""

import html
import logging

from ollama_llm_bench.backend.core.models import BenchmarkResult
from ollama_llm_bench.backend.utils.html_utils import markdown_to_html
from ollama_llm_bench.backend.utils.text_utils import parse_json_string_list

logger = logging.getLogger(__name__)


def build_result_html(result: BenchmarkResult, tokens: dict[str, str]) -> str:
    """Build the full HTML representation of a BenchmarkResult.

    Args:
        result: Source data for the HTML document.
        tokens: Theme token dict (from ``ui.style.tokens.get_tokens``).

    Returns:
        Complete HTML string with inline styles derived from design tokens.
    """
    t = tokens
    sections: list[str] = []

    sections.append(_header_section(result, t))

    if result.user_prompt_sent:
        sections.append(_prompt_section(result, t))

    sections.append(_response_section(result, t))
    sections.append(_performance_section(result, t))
    sections.append(_evaluation_section(result, t))

    error_html = _error_section(result, t)
    if error_html:
        sections.append(error_html)

    keyword_html = _keyword_section(result, t)
    if keyword_html:
        sections.append(keyword_html)

    if result.cosine_similarity is not None:
        sections.append(_cosine_section(result, t))

    if result.judge_score is not None:
        sections.append(_judge_section(result, t))

    body = f'<hr style="border: 1px solid {t["border"]}; margin: 8px 0;">'.join(sections)

    return (
        f'<html><body style="background: {t["bg_primary"]}; '
        f'font-family: {t["font_sans"]}; padding: 8px;">'
        f"{body}"
        f"</body></html>"
    )


def _header_section(result: BenchmarkResult, t: dict[str, str]) -> str:
    s = f"color: {t['text_muted']}; font-size: 12px; margin-bottom: 8px; line-height: 1.7;"
    return (
        f'<div style="{s}">'
        f"<b>Provider:</b> {html.escape(result.provider_id)}<br>"
        f"<b>Type:</b> {html.escape(result.task_type or '—')}<br>"
        f"<b>Model:</b> {html.escape(result.model_name)}<br>"
        f"<b>Difficulty:</b> {html.escape(result.task_difficulty or '—')}<br>"
        f"<b>Task:</b> {html.escape(result.task_id)}"
        f"</div>"
    )


def _prompt_section(result: BenchmarkResult, t: dict[str, str]) -> str:
    return (
        f'<div style="color: {t["primary"]}; font-weight: bold; margin-top: 8px;">PROMPT</div>'
        f'<pre style="color: {t["text_secondary"]}; '
        f"font-family: {t['font_mono']}; font-size: 12px; margin: 4px 0 8px 0; "
        f"padding: 8px; background: {t['bg_secondary']}; border-radius: 4px; "
        f'white-space: pre-wrap; word-wrap: break-word;">'
        f"{html.escape(result.user_prompt_sent)}"
        f"</pre>"
    )


def _response_section(result: BenchmarkResult, t: dict[str, str]) -> str:
    sanitized = result.sanitized_response
    raw = result.raw_response
    response_text: str | None = sanitized if sanitized else raw

    if response_text:
        content = (
            f'<div style="color: {t["text_primary"]}; font-size: 12px; '
            f"margin: 4px 0 8px 0; padding: 8px; background: {t['bg_secondary']}; "
            f'border-radius: 4px;">'
            f"{markdown_to_html(response_text)}"
            f"</div>"
        )
    else:
        content = f'<i style="color: {t["text_muted"]};">(no response)</i>'

    return f'<div style="color: {t["primary"]}; font-weight: bold; margin-top: 8px;">RESPONSE</div>{content}'


def _performance_section(result: BenchmarkResult, t: dict[str, str]) -> str:
    total_time: str | float | int | None = result.total_time_ms if result.total_time_ms is not None else "N/A"
    ttft: str | float | int | None = result.ttft_ms if result.ttft_ms is not None else "N/A"
    tps = f"{result.tokens_per_second:.1f}" if result.tokens_per_second is not None else "N/A"
    prompt_tok: str | int | None = result.prompt_tokens if result.prompt_tokens is not None else "N/A"
    completion_tok: str | int | None = result.completion_tokens if result.completion_tokens is not None else "N/A"
    return (
        f'<div style="color: {t["text_muted"]}; font-size: 11px; margin: 4px 0;">'
        f"Time: {total_time} ms &nbsp;|&nbsp; "
        f"TTFT: {ttft} ms &nbsp;|&nbsp; "
        f"Tokens/s: {tps} &nbsp;|&nbsp; "
        f"Prompt tokens: {prompt_tok} &nbsp;|&nbsp; "
        f"Completion tokens: {completion_tok}"
        f"</div>"
    )


def _evaluation_section(result: BenchmarkResult, t: dict[str, str]) -> str:
    verdict = result.final_verdict
    if verdict == "pass":
        verdict_color = t["success_text"]
    elif verdict == "fail":
        verdict_color = t["failure_text"]
    else:
        verdict_color = t["text_muted"]

    verdict_display = html.escape(verdict) if verdict else "—"
    resolution = html.escape(result.resolution_layer) if result.resolution_layer else "—"

    return (
        f'<div style="color: {t["primary"]}; font-weight: bold; margin-top: 8px;">EVALUATION</div>'
        f'<div style="color: {t["text_muted"]}; font-size: 12px;">'
        f'Verdict: <b style="color: {verdict_color};">{verdict_display}</b> &nbsp;|&nbsp; '
        f"Resolution Layer: {resolution}"
        f"</div>"
    )


def _error_section(result: BenchmarkResult, t: dict[str, str]) -> str:
    if not result.has_inference_error:
        return ""
    error_msg = html.escape(result.inference_error_message or "")
    return (
        f'<div style="color: {t["failure_text"]}; margin-top: 6px;">&#10060; <b>Inference Error:</b> {error_msg}</div>'
    )


def _keyword_section(result: BenchmarkResult, t: dict[str, str]) -> str:
    parts: list[str] = []

    missing = parse_json_string_list(result.missing_exact_terms)
    if missing:
        terms = html.escape(", ".join(missing))
        parts.append(
            f'<div style="color: {t["warning"]}; margin-top: 6px;">&#9888; <b>Missing required terms:</b> {terms}</div>'
        )

    forbidden = parse_json_string_list(result.found_forbidden_terms)
    if forbidden:
        terms = html.escape(", ".join(forbidden))
        parts.append(
            f'<div style="color: {t["failure_text"]}; margin-top: 4px;">'
            f"&#128683; <b>Forbidden terms found:</b> {terms}"
            f"</div>"
        )

    return "".join(parts)


def _cosine_section(result: BenchmarkResult, t: dict[str, str]) -> str:
    similarity = result.cosine_similarity
    if similarity is None:
        return ""
    strategy = html.escape(result.cosine_strategy or "—")
    return (
        f'<div style="color: {t["text_muted"]}; margin-top: 4px;">'
        f"&#128208; Cosine similarity: <b>{similarity:.4f}</b> "
        f"(strategy: {strategy}, "
        f"auto_pass: {result.cosine_auto_pass}, resolved: {result.cosine_resolved})"
        f"</div>"
    )


def _judge_section(result: BenchmarkResult, t: dict[str, str]) -> str:
    score = result.judge_score
    if score is None:
        return ""

    if score >= 0.7:
        judge_color = t["success_text"]
    elif score >= 0.4:
        judge_color = t["warning"]
    else:
        judge_color = t["failure_text"]

    parts: list[str] = [
        f'<div style="color: {t["text_muted"]}; margin-top: 4px;">'
        f'&#9878; Judge score: <b style="color: {judge_color};">{score:.2f}</b>'
        f"</div>"
    ]

    if result.judge_reasoning:
        parts.append(
            f'<div style="color: {t["text_secondary"]}; margin-top: 4px; padding: 6px; '
            f'background: {t["bg_secondary"]}; border-radius: 4px; font-size: 11px;">'
            f"{markdown_to_html(result.judge_reasoning)}"
            f"</div>"
        )

    return "".join(parts)
