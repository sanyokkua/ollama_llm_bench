"""Fakes and fixture factories for downstream consumers of this module."""

from ollama_llm_bench.backend.domain.models import BenchmarkResult, ResultStatus

__all__: list[str] = ["make_benchmark_result"]


def make_benchmark_result(  # noqa: PLR0913  # test builder must expose every
    # BenchmarkResult field this module's phase-eligibility/grouping tests vary independently
    *,
    result_id: int = 1,
    run_id: int = 1,
    task_id: str = "task-1",
    provider_id: str = "11111111-1111-4111-8111-111111111111",
    provider_name: str = "Test Provider",
    model_name: str = "llama3",
    status: ResultStatus = ResultStatus.PENDING,
    created_at: str = "2026-01-01T00:00:00Z",
) -> BenchmarkResult:
    """Build a minimal valid `BenchmarkResult` for pipeline unit tests.

    Args:
        result_id: The result row's primary key.
        run_id: The owning run's primary key.
        task_id: The task identifier the result answers.
        provider_id: The internal UUID4 provider identifier.
        provider_name: The provider's display-name snapshot at result creation.
        model_name: The provider-defined model string under test.
        status: The result row's current lifecycle status.
        created_at: The ISO-8601 UTC timestamp the row was created.

    Returns:
        A fully populated `BenchmarkResult` with every optional field left at its
        default, suitable for phase-eligibility and grouping tests.
    """
    return BenchmarkResult(
        result_id=result_id,
        run_id=run_id,
        task_id=task_id,
        provider_id=provider_id,
        provider_name=provider_name,
        model_name=model_name,
        status=status,
        created_at=created_at,
    )
