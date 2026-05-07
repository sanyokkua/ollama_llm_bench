"""JudgeSummaryService — generates a structured comparative analysis of a full_grading benchmark run."""

import logging
from collections import defaultdict

from ollama_llm_bench.backend.core.interfaces import ProviderRegistryApi
from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkRun

logger = logging.getLogger(__name__)

_MAX_TOKENS: int = 2048
_TEMPERATURE: float = 0.3

_SYSTEM_PROMPT: str = (
    "You are an expert AI evaluator producing a structured benchmark analysis report. "
    "Write a plain-text report with the following sections in order:\n"
    "1. PER-MODEL SUMMARY — for each model: overall pass rate, average score, average speed (tokens/s), "
    "average total time, failure layer breakdown (how many tasks stopped at L1/L2/L3/L4).\n"
    "2. CATEGORY BREAKDOWN — for each task category, state which model performed better and by how much.\n"
    "3. HEAD-TO-HEAD RECOMMENDATION — for each task category, one sentence recommending which model to use.\n"
    "4. FAILURE ANALYSIS — the most common failure patterns and what they reveal about model weaknesses.\n"
    "Rules: always name specific models by their exact names. "
    "Always cite specific numbers (percentages, seconds, tokens/s). "
    "Do not use markdown. Do not use bullet points. Use section headers in ALL CAPS."
)


class JudgeSummaryService:
    """Generates a structured comparative benchmark analysis by calling the judge model."""

    def __init__(self, *, provider_registry: ProviderRegistryApi) -> None:
        """Initialize with a provider registry for judge model access.

        Args:
            provider_registry: registry used to look up the configured judge provider.
        """
        self._provider_registry = provider_registry

    def generate_summary(self, *, run: BenchmarkRun, results: list[BenchmarkResult]) -> str:
        """Build a rich structured prompt and call the judge model for a comparative analysis.

        Args:
            run: the completed benchmark run metadata.
            results: all benchmark results for this run.

        Returns:
            Structured analysis text from the judge model, or a fallback message on error.
        """
        if not run.judge_provider_id or not run.judge_model:
            return "No judge model configured — summary unavailable."

        try:
            provider = self._provider_registry.get_provider(run.judge_provider_id)
        except (KeyError, RuntimeError) as exc:
            logger.warning("judge_summary_provider_unavailable", extra={"error": str(exc)})
            return "Judge model unavailable — summary could not be generated."

        prompt = _build_summary_prompt(run, results)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = provider.inference_sync(
                model=run.judge_model,
                messages=messages,
                temperature=_TEMPERATURE,
                max_tokens=_MAX_TOKENS,
            )
        except Exception as exc:
            logger.warning("judge_summary_inference_failed", extra={"error": str(exc)})
            return "Judge model call failed — summary could not be generated."

        if response.has_error:
            return "Judge model returned an error — summary could not be generated."

        return response.llm_response.strip()


def _build_summary_prompt(run: BenchmarkRun, results: list[BenchmarkResult]) -> str:
    """Build a structured plain-text prompt with per-model and per-category statistics.

    Args:
        run: the completed benchmark run metadata.
        results: all benchmark results for this run.

    Returns:
        Plain-text prompt string with rich context for comparative analysis.
    """
    completed = [r for r in results if r.final_verdict is not None]

    lines: list[str] = [
        f"Benchmark run ID: {run.run_id}",
        f"Run mode: {run.run_mode}",
        f"Total results: {len(completed)}",
        "",
    ]

    by_model: dict[str, list[BenchmarkResult]] = defaultdict(list)
    for r in completed:
        by_model[r.model_name].append(r)

    lines.append("=== PER-MODEL STATISTICS ===")
    for model_name, model_results in sorted(by_model.items()):
        pass_count = sum(1 for r in model_results if str(r.final_verdict).lower() == "pass")
        total = len(model_results)
        pass_pct = pass_count / total * 100 if total else 0.0

        judge_scores: list[float] = [r.judge_score for r in model_results if r.judge_score is not None]
        avg_score = sum(judge_scores) / len(judge_scores) if judge_scores else 0.0

        time_values: list[int] = [r.total_time_ms for r in model_results if r.total_time_ms is not None]
        avg_time_s = sum(time_values) / len(time_values) / 1000.0 if time_values else 0.0

        tps_list: list[float] = [r.tokens_per_second for r in model_results if r.tokens_per_second is not None]
        avg_tps = sum(tps_list) / len(tps_list) if tps_list else 0.0

        ttft_values: list[int] = [r.ttft_ms for r in model_results if r.ttft_ms is not None]
        avg_ttft_ms: float | None = sum(ttft_values) / len(ttft_values) if ttft_values else None

        layer_counts: dict[str, int] = defaultdict(int)
        for r in model_results:
            if r.resolution_layer:
                layer_counts[str(r.resolution_layer)] += 1

        lines.append(f"Model: {model_name}")
        lines.append(f"  Pass rate: {pass_pct:.1f}% ({pass_count}/{total})")
        lines.append(f"  Avg score (judged tasks): {avg_score:.3f}")
        lines.append(f"  Avg total time: {avg_time_s:.1f}s")
        lines.append(f"  Avg tokens/s: {avg_tps:.1f}")
        if avg_ttft_ms is not None:
            lines.append(f"  Avg TTFT: {avg_ttft_ms / 1000.0:.1f}s")
        lines.append(f"  Resolution layer breakdown: {dict(layer_counts)}")
        lines.append("")

    by_category: dict[str, dict[str, list[BenchmarkResult]]] = defaultdict(lambda: defaultdict(list))
    for r in completed:
        by_category[r.task_category][r.model_name].append(r)

    lines.append("=== PER-CATEGORY STATISTICS ===")
    for category, cat_by_model in sorted(by_category.items()):
        lines.append(f"Category: {category}")
        for model_name, cat_results in sorted(cat_by_model.items()):
            pass_count = sum(1 for r in cat_results if str(r.final_verdict).lower() == "pass")
            total = len(cat_results)
            pass_pct = pass_count / total * 100 if total else 0.0
            cat_scores: list[float] = [r.judge_score for r in cat_results if r.judge_score is not None]
            avg_score = sum(cat_scores) / len(cat_scores) if cat_scores else 0.0
            cat_times: list[int] = [r.total_time_ms for r in cat_results if r.total_time_ms is not None]
            avg_time_s = sum(cat_times) / len(cat_times) / 1000.0 if cat_times else 0.0
            lines.append(
                f"  {model_name}: pass={pass_pct:.0f}% ({pass_count}/{total}), "
                f"avg_score={avg_score:.2f}, avg_time={avg_time_s:.1f}s"
            )
        lines.append("")

    lines.append("=== TOP/BOTTOM TASKS BY SCORE ===")
    scored_all = sorted(
        [r for r in completed if r.judge_score is not None],
        key=lambda r: r.judge_score or 0.0,
    )
    lines.append("Lowest 5 scoring tasks:")
    for r in scored_all[:5]:
        lines.append(f"  {r.task_id} [{r.model_name}]: score={r.judge_score:.2f}, verdict={r.final_verdict}")
    lines.append("Highest 5 scoring tasks:")
    for r in reversed(scored_all[-5:]):
        lines.append(f"  {r.task_id} [{r.model_name}]: score={r.judge_score:.2f}, verdict={r.final_verdict}")

    return "\n".join(lines)
