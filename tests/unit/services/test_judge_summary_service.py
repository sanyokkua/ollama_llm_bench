"""Unit tests for JudgeSummaryService and its prompt-builder helpers."""

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import LLMProviderApi, ProviderRegistryApi
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunStatus,
    InferenceResponse,
    RunMode,
)
from ollama_llm_bench.backend.services.judge_summary_service import (
    _SYSTEM_PROMPTS,
    JudgeSummaryService,
    _build_full_grading_prompt,
    _build_perf_prompt,
    _build_prompt_eval_prompt,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DEFAULT_RUN = BenchmarkRun(
    run_id=1,
    timestamp="2026-01-01T00:00:00",
    judge_model="judge:8b",
    judge_provider_id="ollama",
    status=BenchmarkRunStatus.NOT_COMPLETED,
    run_mode=RunMode.FULL_GRADING,
    models_json="[]",
    task_file_paths=(),
)

_PERF_RUN = BenchmarkRun(
    run_id=2,
    timestamp="2026-01-01T00:00:00",
    judge_model="judge:8b",
    judge_provider_id="ollama",
    status=BenchmarkRunStatus.NOT_COMPLETED,
    run_mode=RunMode.PERFORMANCE,
    models_json="[]",
    task_file_paths=(),
)

_PROMPT_EVAL_RUN = BenchmarkRun(
    run_id=3,
    timestamp="2026-01-01T00:00:00",
    judge_model="judge:8b",
    judge_provider_id="ollama",
    status=BenchmarkRunStatus.NOT_COMPLETED,
    run_mode=RunMode.PROMPT_EVAL,
    models_json="[]",
    task_file_paths=(),
)


def _make_perf_result(model: str, tps: float, ttft: int, total_ms: int) -> BenchmarkResult:
    return BenchmarkResult(
        run_id=1,
        task_id="t1",
        model_name=model,
        tokens_per_second=tps,
        ttft_ms=ttft,
        total_time_ms=total_ms,
    )


# ---------------------------------------------------------------------------
# Test 1 — happy path: provider returns a valid response
# ---------------------------------------------------------------------------


def test_generate_summary_returns_provider_response(mocker: MockerFixture) -> None:
    # Arrange
    mock_registry = mocker.Mock(spec=ProviderRegistryApi)
    mock_provider = mocker.Mock(spec=LLMProviderApi)
    mock_registry.get_provider.return_value = mock_provider
    mock_provider.inference_sync.return_value = InferenceResponse(
        llm_response="  analysis text  ",
        has_error=False,
    )
    service = JudgeSummaryService(provider_registry=mock_registry)

    # Act
    result = service.generate_summary(run=_DEFAULT_RUN, results=[])

    # Assert
    assert result == "analysis text"


# ---------------------------------------------------------------------------
# Test 2 — no judge_model → fallback without touching registry
# ---------------------------------------------------------------------------


def test_generate_summary_no_judge_model_returns_fallback(mocker: MockerFixture) -> None:
    # Arrange
    mock_registry = mocker.Mock(spec=ProviderRegistryApi)
    run = BenchmarkRun(
        run_id=1,
        timestamp="2026-01-01T00:00:00",
        judge_model="",
        judge_provider_id="ollama",
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=RunMode.FULL_GRADING,
        models_json="[]",
        task_file_paths=(),
    )
    service = JudgeSummaryService(provider_registry=mock_registry)

    # Act
    result = service.generate_summary(run=run, results=[])

    # Assert
    assert result == "No judge model configured — summary unavailable."
    mock_registry.get_provider.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3 — no judge_provider_id → fallback without touching registry
# ---------------------------------------------------------------------------


def test_generate_summary_no_judge_provider_returns_fallback(mocker: MockerFixture) -> None:
    # Arrange
    mock_registry = mocker.Mock(spec=ProviderRegistryApi)
    run = BenchmarkRun(
        run_id=1,
        timestamp="2026-01-01T00:00:00",
        judge_model="judge:8b",
        judge_provider_id="",
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=RunMode.FULL_GRADING,
        models_json="[]",
        task_file_paths=(),
    )
    service = JudgeSummaryService(provider_registry=mock_registry)

    # Act
    result = service.generate_summary(run=run, results=[])

    # Assert
    assert result == "No judge model configured — summary unavailable."
    mock_registry.get_provider.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — get_provider raises KeyError → "unavailable" fallback
# ---------------------------------------------------------------------------


def test_generate_summary_provider_not_found_returns_fallback(mocker: MockerFixture) -> None:
    # Arrange
    mock_registry = mocker.Mock(spec=ProviderRegistryApi)
    mock_registry.get_provider.side_effect = KeyError("ollama")
    service = JudgeSummaryService(provider_registry=mock_registry)

    # Act
    result = service.generate_summary(run=_DEFAULT_RUN, results=[])

    # Assert
    assert result == "Judge model unavailable — summary could not be generated."


# ---------------------------------------------------------------------------
# Test 5 — inference_sync raises RuntimeError → "call failed" fallback
# ---------------------------------------------------------------------------


def test_generate_summary_inference_fails_returns_fallback(mocker: MockerFixture) -> None:
    # Arrange
    mock_registry = mocker.Mock(spec=ProviderRegistryApi)
    mock_provider = mocker.Mock(spec=LLMProviderApi)
    mock_registry.get_provider.return_value = mock_provider
    mock_provider.inference_sync.side_effect = RuntimeError("timeout")
    service = JudgeSummaryService(provider_registry=mock_registry)

    # Act
    result = service.generate_summary(run=_DEFAULT_RUN, results=[])

    # Assert
    assert result == "Judge model call failed — summary could not be generated."


# ---------------------------------------------------------------------------
# Test 6 — response.has_error = True → "returned an error" fallback
# ---------------------------------------------------------------------------


def test_generate_summary_response_has_error_returns_fallback(mocker: MockerFixture) -> None:
    # Arrange
    mock_registry = mocker.Mock(spec=ProviderRegistryApi)
    mock_provider = mocker.Mock(spec=LLMProviderApi)
    mock_registry.get_provider.return_value = mock_provider
    mock_provider.inference_sync.return_value = InferenceResponse(
        has_error=True,
        error_message="upstream error",
    )
    service = JudgeSummaryService(provider_registry=mock_registry)

    # Act
    result = service.generate_summary(run=_DEFAULT_RUN, results=[])

    # Assert
    assert result == "Judge model returned an error — summary could not be generated."


# ---------------------------------------------------------------------------
# Test 7 — system prompt matches _SYSTEM_PROMPTS[run_mode] for each mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode",
    [RunMode.FULL_GRADING, RunMode.PERFORMANCE, RunMode.SPEED, RunMode.PROMPT_EVAL],
    ids=["full_grading", "performance", "speed", "prompt_eval"],
)
def test_generate_summary_uses_correct_system_prompt_per_mode(
    mocker: MockerFixture,
    mode: RunMode,
) -> None:
    # Arrange
    mock_registry = mocker.Mock(spec=ProviderRegistryApi)
    mock_provider = mocker.Mock(spec=LLMProviderApi)
    mock_registry.get_provider.return_value = mock_provider
    mock_provider.inference_sync.return_value = InferenceResponse(
        llm_response="ok",
        has_error=False,
    )
    run = BenchmarkRun(
        run_id=1,
        timestamp="2026-01-01T00:00:00",
        judge_model="judge:8b",
        judge_provider_id="ollama",
        status=BenchmarkRunStatus.NOT_COMPLETED,
        run_mode=mode,
        models_json="[]",
        task_file_paths=(),
    )
    service = JudgeSummaryService(provider_registry=mock_registry)

    # Act
    service.generate_summary(run=run, results=[])

    # Assert
    call_kwargs = mock_provider.inference_sync.call_args.kwargs
    messages: list[dict[str, str]] = call_kwargs["messages"]
    assert messages[0]["content"] == _SYSTEM_PROMPTS[mode]


# ---------------------------------------------------------------------------
# Test 8 — _build_perf_prompt includes model stats for known results
# ---------------------------------------------------------------------------


def test_build_perf_prompt_includes_model_stats() -> None:
    # Arrange
    results = [
        _make_perf_result("llama3:8b", tps=50.0, ttft=100, total_ms=2000),
        _make_perf_result("llama3:8b", tps=50.0, ttft=100, total_ms=2000),
    ]

    # Act
    output = _build_perf_prompt(_PERF_RUN, results)

    # Assert
    assert "llama3:8b" in output
    assert "50.0" in output
    assert "100" in output


# ---------------------------------------------------------------------------
# Test 9 — _build_full_grading_prompt includes per-model AND per-category data
# ---------------------------------------------------------------------------


def test_build_full_grading_prompt_includes_per_model_and_per_category() -> None:
    # Arrange — 2 models x 2 categories = 4 results, all with final_verdict set
    results = [
        BenchmarkResult(
            run_id=1,
            task_id="t1",
            model_name="model_alpha",
            task_category="cat_math",
            final_verdict="pass",
        ),
        BenchmarkResult(
            run_id=1,
            task_id="t2",
            model_name="model_alpha",
            task_category="cat_code",
            final_verdict="pass",
        ),
        BenchmarkResult(
            run_id=1,
            task_id="t3",
            model_name="model_beta",
            task_category="cat_math",
            final_verdict="pass",
        ),
        BenchmarkResult(
            run_id=1,
            task_id="t4",
            model_name="model_beta",
            task_category="cat_code",
            final_verdict="pass",
        ),
    ]

    # Act
    output = _build_full_grading_prompt(_DEFAULT_RUN, results)

    # Assert — model names appear in per-model section
    assert "model_alpha" in output
    assert "model_beta" in output
    # Assert — category names appear in per-category section
    assert "cat_math" in output
    assert "cat_code" in output


# ---------------------------------------------------------------------------
# Test 10 — _build_prompt_eval_prompt includes per-variant stats
# ---------------------------------------------------------------------------


def test_build_prompt_eval_prompt_includes_variant_stats() -> None:
    # Arrange
    results = [
        BenchmarkResult(
            run_id=1,
            task_id="t1",
            model_name="llama3",
            prompt_version="v1",
            final_verdict="pass",
            judge_score=0.9,
        ),
        BenchmarkResult(
            run_id=1,
            task_id="t2",
            model_name="llama3",
            prompt_version="v2",
            final_verdict="fail",
            judge_score=0.4,
        ),
    ]

    # Act
    output = _build_prompt_eval_prompt(_PROMPT_EVAL_RUN, results)

    # Assert
    assert "v1" in output
    assert "v2" in output


# ---------------------------------------------------------------------------
# Test 11 — _build_perf_prompt with empty results does not crash
# ---------------------------------------------------------------------------


def test_build_perf_prompt_empty_results_does_not_crash() -> None:
    # Arrange
    results: list[BenchmarkResult] = []

    # Act
    output = _build_perf_prompt(_PERF_RUN, results)

    # Assert
    assert isinstance(output, str)
    assert "Total results: 0" in output
