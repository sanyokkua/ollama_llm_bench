"""Proves: STORY-029-AC-1"""

import pytest

from ollama_llm_bench.backend.benchmark_pipeline._internal.grouping import (
    eligible_for_phase,
    group_by_provider_and_model,
    phase_applies,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.units import (
    _complete_or_advance,
    _next_status_after_phase,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import PHASE_ORDER, Phase
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.domain.models import ResolutionLayer, ResultStatus, RunMode, Verdict


def test_phase_order_is_the_five_phases_in_spec_order() -> None:
    """Proves: STORY-029-AC-1

    The pipeline never reorders phases; Init precedes Inference precedes
    Keyword precedes Cosine precedes Judge.
    """
    assert PHASE_ORDER == (
        Phase.INITIALIZATION,
        Phase.INFERENCE,
        Phase.KEYWORD_CHECK,
        Phase.COSINE_CHECK,
        Phase.JUDGE_CHECK,
    )


@pytest.mark.parametrize(
    ("phase", "run_mode", "keyword_enabled", "cosine_enabled", "judge_enabled", "expected"),
    [
        (Phase.INFERENCE, RunMode.SYNTHETIC, False, False, False, True),
        (Phase.KEYWORD_CHECK, RunMode.SYNTHETIC, True, True, True, False),
        (Phase.KEYWORD_CHECK, RunMode.TASKS, True, True, True, False),
        (Phase.KEYWORD_CHECK, RunMode.GRADED, False, True, True, False),
        (Phase.KEYWORD_CHECK, RunMode.GRADED, True, True, True, True),
        (Phase.JUDGE_CHECK, RunMode.GRADED, True, True, False, False),
    ],
)
def test_phase_applies_matches_the_mode_applicability_table(  # noqa: PLR0913  # one
    # parametrize column per phase-applicability input plus the expected output; 08-B
    # §3.3's table is inherently this wide and splitting it would obscure the mapping
    *,
    phase: Phase,
    run_mode: RunMode,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
    expected: bool,
) -> None:
    """Proves: STORY-029-AC-1

    Table-driven over 08-B §3.3: SYNTHETIC/TASKS never grade; GRADED grades
    per the per-dimension toggle.
    """
    result = phase_applies(
        phase=phase,
        run_mode=run_mode,
        keyword_enabled=keyword_enabled,
        cosine_enabled=cosine_enabled,
        judge_enabled=judge_enabled,
    )
    assert result == expected


def test_eligible_for_phase_excludes_rows_already_past_or_failed() -> None:
    """Proves: STORY-029-AC-1

    A row already COMPLETED or terminally failed in an earlier phase never
    enters a later phase's eligible set.
    """
    pending = make_benchmark_result(status=ResultStatus.PENDING)
    awaiting_keyword = make_benchmark_result(status=ResultStatus.AWAITING_KEYWORD_CHECK)
    failed = make_benchmark_result(status=ResultStatus.FAILED_INFERENCE)
    completed = make_benchmark_result(status=ResultStatus.COMPLETED)

    result = eligible_for_phase(
        (pending, awaiting_keyword, failed, completed), phase=Phase.KEYWORD_CHECK
    )

    assert result == (awaiting_keyword,)


def test_group_by_provider_and_model_preserves_first_seen_order() -> None:
    """Proves: STORY-029-AC-1

    Grouping never alphabetizes — group order follows first appearance in
    the run's own task/result order, and no provider switch occurs
    mid-group.
    """
    row_a = make_benchmark_result(
        provider_id="11111111-1111-4111-8111-111111111111", model_name="llama3"
    )
    row_b = make_benchmark_result(
        provider_id="22222222-2222-4222-8222-222222222222", model_name="mistral"
    )
    row_c = make_benchmark_result(
        provider_id="11111111-1111-4111-8111-111111111111", model_name="llama3"
    )

    groups = group_by_provider_and_model((row_a, row_b, row_c))

    assert [group[:2] for group in groups] == [
        ("11111111-1111-4111-8111-111111111111", "llama3"),
        ("22222222-2222-4222-8222-222222222222", "mistral"),
    ]
    assert groups[0][2] == (row_a, row_c)


@pytest.mark.parametrize(
    (
        "completed_phase",
        "run_mode",
        "keyword_enabled",
        "cosine_enabled",
        "judge_enabled",
        "expected",
    ),
    [
        (
            Phase.KEYWORD_CHECK,
            RunMode.GRADED,
            True,
            True,
            True,
            ResultStatus.AWAITING_COSINE_CHECK,
        ),
        (
            Phase.KEYWORD_CHECK,
            RunMode.GRADED,
            True,
            False,
            True,
            ResultStatus.AWAITING_JUDGE_CHECK,
        ),
        (
            Phase.KEYWORD_CHECK,
            RunMode.GRADED,
            True,
            False,
            False,
            None,
        ),
        (
            Phase.JUDGE_CHECK,
            RunMode.GRADED,
            True,
            True,
            True,
            None,
        ),
        (
            Phase.INFERENCE,
            RunMode.GRADED,
            False,
            False,
            False,
            None,
        ),
        (
            # A non-GRADED run never routes into a grading phase, even when
            # every per-dimension toggle is enabled — the mode gate (08-B
            # §5.1) is checked before the toggles are even consulted.
            Phase.INFERENCE,
            RunMode.TASKS,
            True,
            True,
            True,
            None,
        ),
    ],
)
def test_next_status_after_phase_routes_per_08b_state_machine(  # noqa: PLR0913  # one
    # parameter per parametrize column; 08-B §5.1's state machine is inherently
    # this wide and splitting it would obscure the mapping
    *,
    completed_phase: Phase,
    run_mode: RunMode,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
    expected: ResultStatus | None,
) -> None:
    """Proves: STORY-029-AC-1

    08-B §5.1's state machine: a completed phase advances to the next
    *enabled* grading phase's AWAITING_* status, skipping any disabled
    phase, or returns None (route to COMPLETED) when no later grading
    phase is enabled or the run mode does not grade at all.
    """
    result = _next_status_after_phase(
        run_mode=run_mode,
        completed_phase=completed_phase,
        keyword_enabled=keyword_enabled,
        cosine_enabled=cosine_enabled,
        judge_enabled=judge_enabled,
    )

    assert result is expected


def test_complete_or_advance_returns_next_awaiting_status_with_no_verdict() -> None:
    """Proves: STORY-029-AC-1

    When a later grading phase is enabled, the row advances without a
    combined verdict — combine_verdict runs only on the terminal phase.
    """
    status, verdict, resolution_layer = _complete_or_advance(
        run_mode=RunMode.GRADED,
        completed_phase=Phase.KEYWORD_CHECK,
        keyword_enabled=True,
        cosine_enabled=True,
        judge_enabled=True,
        sanity_check_passed=True,
        keyword_verdict=Verdict.PASS,
        cosine_verdict=None,
        judge_verdict=None,
        force_judge_on_prior_failure=False,
    )

    assert status is ResultStatus.AWAITING_COSINE_CHECK
    assert verdict is None
    assert resolution_layer is None


def test_complete_or_advance_combines_verdict_on_terminal_grading_phase() -> None:
    """Proves: STORY-029-AC-1

    On the row's actual terminal grading phase, combine_verdict runs
    exactly once and its result is threaded onto the COMPLETED patch.
    """
    status, verdict, resolution_layer = _complete_or_advance(
        run_mode=RunMode.GRADED,
        completed_phase=Phase.KEYWORD_CHECK,
        keyword_enabled=True,
        cosine_enabled=False,
        judge_enabled=False,
        sanity_check_passed=True,
        keyword_verdict=Verdict.PASS,
        cosine_verdict=None,
        judge_verdict=None,
        force_judge_on_prior_failure=False,
    )

    assert status is ResultStatus.COMPLETED
    assert verdict is Verdict.PASS
    assert resolution_layer is ResolutionLayer.KEYWORD


def test_complete_or_advance_skips_combine_verdict_when_all_grading_disabled() -> None:
    """Proves: STORY-029-AC-1

    A non-grading run (or an all-phases-disabled GRADED run) routes
    straight to COMPLETED with verdict=None and resolution_layer=SKIP,
    never calling combine_verdict (which would violate its own
    icontract precondition on an all-None-verdict input).
    """
    status, verdict, resolution_layer = _complete_or_advance(
        run_mode=RunMode.GRADED,
        completed_phase=Phase.INFERENCE,
        keyword_enabled=False,
        cosine_enabled=False,
        judge_enabled=False,
        sanity_check_passed=True,
        keyword_verdict=None,
        cosine_verdict=None,
        judge_verdict=None,
        force_judge_on_prior_failure=False,
    )

    assert status is ResultStatus.COMPLETED
    assert verdict is None
    assert resolution_layer is ResolutionLayer.SKIP
