"""The verdict-combination cascade (§6.6 of 04_EVALUATION_PIPELINE.md; §11 of
08-P_judge_protocol.md)."""

from ollama_llm_bench.backend.domain import ResolutionLayer, Verdict
from ollama_llm_bench.backend.evaluation.models import CombinedVerdict


def combine_verdict_impl(  # noqa: PLR0913  # each parameter disambiguates a distinct
    # combination-cascade input (sanity/keyword/cosine/judge phase outcomes plus the
    # force-judge flag); see the plan's ambiguity #6 — grouping into a Struct would
    # contradict the plan's explicit six-flat-keyword-only-parameter design
    *,
    sanity_check_passed: bool,
    keyword_verdict: Verdict | None,
    cosine_verdict: Verdict | None,
    judge_enabled: bool,
    judge_verdict: Verdict | None,
    force_judge_on_prior_failure: bool,
) -> CombinedVerdict:
    """Fold the enabled phases' outcomes into one binary verdict (§6.6, §11).

    Args:
        sanity_check_passed: The sanity pre-check's outcome; ``False`` is
            always a final ``FAIL`` (DD-62) — the judge is never consulted.
        keyword_verdict: The keyword phase's outcome, or ``None`` if the
            phase did not run.
        cosine_verdict: The cosine phase's outcome, or ``None`` if the
            phase did not run or was skipped for the task.
        judge_enabled: Whether the judge phase is enabled for this run —
            distinct from ``judge_verdict is None``, since a ``None``
            verdict from an *enabled* judge (transport failure) behaves
            differently under ``force_judge_on_prior_failure`` than a
            genuinely disabled judge phase.
        judge_verdict: The judge phase's outcome, or ``None`` when the
            phase is disabled or the call transport-failed. (An
            exhausted-parse-retries outcome never reaches this function —
            that result is ``ERRORED`` before combination runs, per §9.3.)
        force_judge_on_prior_failure: The run's force-judge setting.

    Returns:
        The combined binary verdict and the layer that decided it.
    """
    if not sanity_check_passed:
        return CombinedVerdict(verdict=Verdict.FAIL, resolution_layer=ResolutionLayer.KEYWORD)

    deterministic_fail = keyword_verdict is Verdict.FAIL
    skip_short_circuit = judge_enabled and force_judge_on_prior_failure

    if deterministic_fail and not skip_short_circuit:
        return CombinedVerdict(verdict=Verdict.FAIL, resolution_layer=ResolutionLayer.KEYWORD)

    if judge_verdict is not None:
        return CombinedVerdict(verdict=judge_verdict, resolution_layer=ResolutionLayer.JUDGE)

    if cosine_verdict is not None:
        return CombinedVerdict(verdict=cosine_verdict, resolution_layer=ResolutionLayer.COSINE)

    assert keyword_verdict is not None, (  # noqa: S101  # internal invariant, guaranteed by
        "keyword_verdict must be non-None here"  # the icontract precondition in api.py (Task 11)
    )
    return CombinedVerdict(verdict=keyword_verdict, resolution_layer=ResolutionLayer.KEYWORD)
