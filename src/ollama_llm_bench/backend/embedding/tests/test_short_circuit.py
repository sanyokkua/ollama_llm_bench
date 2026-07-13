"""Proves STORY-027-AC-4 — the consecutive-embedding-failure short-circuit (DD-70, §7)."""

from ollama_llm_bench.backend.embedding.api import make_embedding_service
from ollama_llm_bench.backend.embedding.tests.conftest import FakeLLMClient, make_snapshot
from ollama_llm_bench.backend.errors import HttpTimeoutError

_PROVIDER = "p1"
_MODEL = "embed-model"


def _always_fails(text: str) -> tuple[float, ...]:
    del text
    raise HttpTimeoutError(message="embedding call timed out")


def test_consecutive_failure_short_circuit_and_success_resets_counter() -> None:
    """Proves: STORY-027-AC-4

    K consecutive embedding failures with no intervening success trips the
    run-wide short-circuit and stops further provider calls; a success before
    the K-th failure resets the counter so no short-circuit occurs.
    """
    failures_to_skip = 3
    client = FakeLLMClient(embed_fn=_always_fails)
    service = make_embedding_service(
        client=client,
        provider_id=_PROVIDER,
        model_name=_MODEL,
        snapshot=make_snapshot(consecutive_failures_to_skip=failures_to_skip),
    )

    service.embed("text-a")
    service.embed("text-b")
    assert service.is_short_circuited() is False

    service.embed("text-c")
    assert service.is_short_circuited() is True

    calls_before_short_circuit = len(client.calls)
    service.embed("text-d")
    assert len(client.calls) == calls_before_short_circuit  # no further provider call


def test_success_before_kth_failure_resets_consecutive_counter() -> None:
    """Proves: STORY-027-AC-4

    A single successful embedding before the K-th failure resets the
    consecutive-failure counter, so K subsequent failures are required again
    before the short-circuit trips.
    """
    failures_to_skip = 2
    call_log: list[str] = []

    def _flaky(text: str) -> tuple[float, ...]:
        call_log.append(text)
        if text == "succeeds":
            return (1.0, 2.0, 3.0)
        raise HttpTimeoutError(message="embedding call timed out")

    client = FakeLLMClient(embed_fn=_flaky)
    service = make_embedding_service(
        client=client,
        provider_id=_PROVIDER,
        model_name=_MODEL,
        snapshot=make_snapshot(consecutive_failures_to_skip=failures_to_skip),
    )

    service.embed("fails-1")  # 1 consecutive failure
    service.embed("succeeds")  # resets the counter
    service.embed("fails-2")  # 1 consecutive failure (post-reset)
    assert service.is_short_circuited() is False

    service.embed("fails-3")  # 2 consecutive failures -> trips
    assert service.is_short_circuited() is True
