"""Shared fixtures for backend/evaluation's colocated tests."""

from collections.abc import Iterable
from datetime import UTC, datetime

import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    ChatRequest,
    ChatResponse,
    Difficulty,
    RequiredTerms,
    TaskOrigin,
)
from ollama_llm_bench.backend.domain.models import Iso8601Utc

_DEFAULT_SETTING_VALUES: dict[str, str] = {
    "eval.sanity_min_chars": "2",
    "eval.sanity_error_markers": "ERROR:,EXCEPTION:,[ERROR]",
    "eval.keyword_semantic_pass_threshold": "0.70",
    "eval.judge_max_completion_tokens": "4096",
    "eval.judge_max_parse_retries": "2",
    "eval.force_judge_on_prior_failure": "false",
}


def make_task(  # noqa: PLR0913  # test builder must expose every evaluator-relevant field
    *,
    task_id: str = "task-1",
    question: str = "What is the capital of France?",
    category: str = "geography",
    sub_category: str = "capitals",
    golden_answer: str | None = "Paris",
    pass_criteria: str = "",
    fail_criteria: str = "",
    cosine_enabled: bool = True,
    required_terms: RequiredTerms | None = None,
    source_material: str | None = None,
    fail_example: str | None = None,
    task_origin: TaskOrigin = TaskOrigin.FILE,
) -> BenchmarkTask:
    """Build a minimal, valid ``BenchmarkTask`` for a test case."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=task_origin,
        cosine_enabled=cosine_enabled,
        question=question,
        category=category,
        sub_category=sub_category,
        golden_answer=golden_answer,
        pass_criteria=pass_criteria,
        fail_criteria=fail_criteria,
        difficulty=Difficulty.MEDIUM,
        required_terms=required_terms if required_terms is not None else RequiredTerms(),
        source_material=source_material,
        fail_example=fail_example,
    )


def make_snapshot(
    overrides: dict[str, str] | None = None,
) -> tuple[BenchmarkRunSettingEntry, ...]:
    """Build a settings snapshot carrying every key this module reads."""
    values = {**_DEFAULT_SETTING_VALUES, **(overrides or {})}
    return tuple(
        BenchmarkRunSettingEntry(setting_key=key, setting_value=value)
        for key, value in values.items()
    )


class FakeLLMClient:
    """A canned ``LLMClient`` stand-in for judge-evaluator tests.

    Not a full ``LLMClient`` fake (no ``list_models``/``probe_health``/etc.) —
    scoped to exactly what ``JudgeEvaluator`` calls: ``chat``.
    """

    def __init__(self, *, responses: Iterable[ChatResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        self.requests.append(request)
        return self._responses.pop(0)


class FakeClock:
    """A minimal, fully controllable ``Clock`` double (matches the project-wide
    per-module convention already used by ``backend/circuit_breaker/tests/conftest.py``
    and every provider adapter's own ``tests/conftest.py``).

    ``CancellationToken`` requires a real ``clock=`` keyword argument — it has no
    no-arg constructor — so every ``CancellationToken()`` construction in this
    module's tests must go through ``make_cancellation_token()`` below, never
    ``CancellationToken()`` directly.
    """

    def __init__(self, *, start_monotonic_ms: int = 0) -> None:
        self._monotonic_ms = start_monotonic_ms
        self._now = datetime(2026, 1, 1, tzinfo=UTC)

    def now_utc(self) -> Iso8601Utc:
        return self._now.isoformat()

    def monotonic_ms(self) -> int:
        return self._monotonic_ms


def make_cancellation_token() -> CancellationToken:
    """Build a fresh, uncancelled ``CancellationToken`` backed by a ``FakeClock``."""
    return CancellationToken(clock=FakeClock())


@pytest.fixture
def cancellation_token() -> CancellationToken:
    return make_cancellation_token()
