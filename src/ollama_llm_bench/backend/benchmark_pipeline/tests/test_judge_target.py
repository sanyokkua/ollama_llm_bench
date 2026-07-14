"""Proves: STORY-030-AC-3, STORY-030-AC-4 (`resolve_judge_target` unit)"""

from ollama_llm_bench.backend.benchmark_pipeline._internal.judge_target import (
    resolve_judge_target,
)
from ollama_llm_bench.backend.domain.models import (
    BenchmarkRun,
    BenchmarkRunModelEntry,
    ModelRole,
    RunMode,
    RunStatus,
)

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_TEST_MODEL_NAME = "llama3"
_JUDGE_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_JUDGE_MODEL_NAME = "judge-model"


def _make_run(*, models: tuple[BenchmarkRunModelEntry, ...]) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=1,
        run_name=None,
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.GRADED,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        models=models,
    )


def test_resolve_judge_target_with_judge_entry_returns_its_provider_and_model() -> None:
    """Proves: STORY-030-AC-3

    The judge target is resolved from the run's `ModelRole.JUDGE` roster entry,
    never from a row's own test-model identity.
    """
    run = _make_run(
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID, model_name=_TEST_MODEL_NAME
            ),
            BenchmarkRunModelEntry(
                role=ModelRole.JUDGE,
                provider_id=_JUDGE_PROVIDER_ID,
                model_name=_JUDGE_MODEL_NAME,
            ),
        )
    )

    result = resolve_judge_target(run)

    assert result == (_JUDGE_PROVIDER_ID, _JUDGE_MODEL_NAME)


def test_resolve_judge_target_with_no_judge_entry_returns_none() -> None:
    """Proves: STORY-030-AC-4

    A run with no `ModelRole.JUDGE` roster entry (the judge phase is not
    configured) resolves to `None` rather than raising or defaulting to the
    test model.
    """
    run = _make_run(
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID, model_name=_TEST_MODEL_NAME
            ),
        )
    )

    result = resolve_judge_target(run)

    assert result is None
