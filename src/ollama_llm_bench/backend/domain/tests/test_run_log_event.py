"""Tests proving the ``RunLogEvent`` shape (§7.7, STORY-036's domain gap-fix).

Small and scoped: proves construction with only the two required fields defaults every
optional field to ``None``, and that a full field set round-trips through construction —
STORY-036's own ``log_formatting`` tests exercise ``RunLogEvent``'s actual use.
"""

from ollama_llm_bench.backend.domain.models import RunLogEvent, RunLogEventKind, Verdict

_PROVIDER_ID = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"
_TOTAL_TIME_MS = 2140
_TTFT_MS = 120
_TOKENS_PER_SECOND = 87.5
_PROMPT_TOKENS = 42
_COMPLETION_TOKENS = 188
_RETRY_ATTEMPT = 2


def test_run_log_event_required_fields_only_defaults_optional_fields_to_none() -> None:
    """Constructing with only ``kind`` and ``timestamp`` leaves every other field ``None``."""
    # Act
    event = RunLogEvent(kind=RunLogEventKind.STAGE, timestamp="2026-07-14T10:00:00Z")

    # Assert
    assert event.kind == RunLogEventKind.STAGE
    assert event.timestamp == "2026-07-14T10:00:00Z"
    assert event.provider_id is None
    assert event.model_name is None
    assert event.task_id is None
    assert event.stage is None
    assert event.started_at is None
    assert event.finished_at is None
    assert event.total_time_ms is None
    assert event.ttft_ms is None
    assert event.tokens_per_second is None
    assert event.prompt_tokens is None
    assert event.completion_tokens is None
    assert event.prompt_excerpt is None
    assert event.response_excerpt is None
    assert event.retry_attempt is None
    assert event.retry_reason is None
    assert event.error_text is None
    assert event.judge_verdict is None
    assert event.judge_reasoning is None


def test_run_log_event_full_field_set_round_trips() -> None:
    """Constructing with every field set makes each field readable back unchanged."""
    # Arrange / Act
    event = RunLogEvent(
        kind=RunLogEventKind.JUDGE,
        timestamp="2026-07-14T10:00:00Z",
        provider_id=_PROVIDER_ID,
        model_name="llama3.2:3b",
        task_id="coding_java_two_sum",
        stage="judging",
        started_at="2026-07-14T09:59:58Z",
        finished_at="2026-07-14T10:00:00Z",
        total_time_ms=_TOTAL_TIME_MS,
        ttft_ms=_TTFT_MS,
        tokens_per_second=_TOKENS_PER_SECOND,
        prompt_tokens=_PROMPT_TOKENS,
        completion_tokens=_COMPLETION_TOKENS,
        prompt_excerpt="Write a function that returns two sum indices.",
        response_excerpt="def two_sum(nums, target): ...",
        retry_attempt=_RETRY_ATTEMPT,
        retry_reason="Connection refused",
        error_text="timeout after 30s",
        judge_verdict=Verdict.PASS,
        judge_reasoning="The answer correctly solves the problem.",
    )

    # Assert
    assert event.kind == RunLogEventKind.JUDGE
    assert event.timestamp == "2026-07-14T10:00:00Z"
    assert event.provider_id == _PROVIDER_ID
    assert event.model_name == "llama3.2:3b"
    assert event.task_id == "coding_java_two_sum"
    assert event.stage == "judging"
    assert event.started_at == "2026-07-14T09:59:58Z"
    assert event.finished_at == "2026-07-14T10:00:00Z"
    assert event.total_time_ms == _TOTAL_TIME_MS
    assert event.ttft_ms == _TTFT_MS
    assert event.tokens_per_second == _TOKENS_PER_SECOND
    assert event.prompt_tokens == _PROMPT_TOKENS
    assert event.completion_tokens == _COMPLETION_TOKENS
    assert event.prompt_excerpt == "Write a function that returns two sum indices."
    assert event.response_excerpt == "def two_sum(nums, target): ..."
    assert event.retry_attempt == _RETRY_ATTEMPT
    assert event.retry_reason == "Connection refused"
    assert event.error_text == "timeout after 30s"
    assert event.judge_verdict == Verdict.PASS
    assert event.judge_reasoning == "The answer correctly solves the problem."
