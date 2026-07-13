"""Proves: STORY-029-AC-1"""

import pytest

from ollama_llm_bench.backend.benchmark_pipeline._internal.grouping import (
    eligible_for_phase,
    group_by_provider_and_model,
    phase_applies,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import PHASE_ORDER, Phase
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.domain.models import ResultStatus, RunMode


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
