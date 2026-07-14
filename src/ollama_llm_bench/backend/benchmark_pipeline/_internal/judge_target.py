"""Resolves a run's one fixed judge stability target — pure, no I/O.

`AdaptiveTimeoutService`/`ProviderCircuitBreaker` role=JUDGE consultation must key on
the run's judge `(provider_id, model_name)`, resolved once from `run.models`
(`role=ModelRole.JUDGE`) — never from a per-row `result.provider_id`/`model_name`,
which names the row's TEST model, a different target (STORY-030).
"""

from ollama_llm_bench.backend.domain.models import BenchmarkRun, ModelName, ModelRole, ProviderId

__all__: list[str] = ["resolve_judge_target"]


def resolve_judge_target(run: BenchmarkRun) -> tuple[ProviderId, ModelName] | None:
    """Resolve the run's one fixed judge `(provider_id, model_name)`.

    Args:
        run: The active run, carrying its frozen `models` roster.

    Returns:
        The judge target pair, or `None` when the run has no `ModelRole.JUDGE`
        entry (the judge phase is not configured for this run).
    """
    judge_entry = next((m for m in run.models if m.role is ModelRole.JUDGE), None)
    if judge_entry is None:
        return None
    return judge_entry.provider_id, judge_entry.model_name
