"""Pure derivation helpers for the Generate Analysis dialog (STORY-065).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/generate_analysis_dialog.md``
§3 (title/button label), §5 (default selection rule).
"""

from ollama_llm_bench.backend.domain import BenchmarkRun, ProviderId

__all__: list[str] = ["default_provider_id", "resolve_title_and_button_label"]


def resolve_title_and_button_label(*, run: BenchmarkRun) -> tuple[str, str]:
    """Return the dialog's ``(title, primary-button label)`` pair (§3)."""
    if run.run_analysis is not None:
        return "Regenerate Analysis", "Regenerate"
    return "Generate Analysis", "Generate"


def default_provider_id(
    *, run: BenchmarkRun, enabled_provider_ids: tuple[ProviderId, ...]
) -> ProviderId | None:
    """Return the run's snapshot judge provider when still enabled, else the first
    enabled provider, else ``None`` (§5; EC-GA-1 when no provider is enabled).

    Args:
        run: The run under analysis; ``run.judge_provider_id`` is the snapshot
            judge provider recorded at run start, if any.
        enabled_provider_ids: Every currently-enabled provider's id, in the
            Provider dropdown's own display order.

    Returns:
        The default provider id to pre-select, or ``None`` when no provider is
        enabled at all.
    """
    if run.judge_provider_id is not None and run.judge_provider_id in enabled_provider_ids:
        return run.judge_provider_id
    return enabled_provider_ids[0] if enabled_provider_ids else None
