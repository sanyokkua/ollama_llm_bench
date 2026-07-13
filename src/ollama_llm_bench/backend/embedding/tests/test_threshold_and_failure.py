"""Proves STORY-027-AC-5 — the threshold lookup and the never-raises failure
degradation (§6.4, §8)."""

from ollama_llm_bench.backend.embedding.api import make_embedding_service
from ollama_llm_bench.backend.embedding.tests.conftest import FakeLLMClient, make_snapshot
from ollama_llm_bench.backend.errors import HttpTimeoutError

_PROVIDER = "p1"
_MODEL = "embed-model"
_CUSTOM_COSINE_THRESHOLD = 0.72


def test_threshold_lookup_returns_snapshot_value() -> None:
    """Proves: STORY-027-AC-5

    cosine_threshold() returns the eval.cosine_threshold value carried by the
    run snapshot, typed as CosineThreshold.
    """
    client = FakeLLMClient()
    service = make_embedding_service(
        client=client,
        provider_id=_PROVIDER,
        model_name=_MODEL,
        snapshot=make_snapshot(cosine_threshold=_CUSTOM_COSINE_THRESHOLD),
    )

    assert service.cosine_threshold() == _CUSTOM_COSINE_THRESHOLD


def test_single_failed_embedding_degrades_without_raising() -> None:
    """Proves: STORY-027-AC-5

    A single embedding call that fails surfaces as a degraded outcome — no
    exception propagates to the caller, and no Cosine Score is produced for
    the affected comparison.
    """

    def _fails_once(text: str) -> tuple[float, ...]:
        del text
        raise HttpTimeoutError(message="embedding call timed out")

    client = FakeLLMClient(embed_fn=_fails_once)
    service = make_embedding_service(
        client=client, provider_id=_PROVIDER, model_name=_MODEL, snapshot=make_snapshot()
    )

    vector = service.embed("some response text")

    assert vector == ()


def test_single_failed_embedding_in_cosine_yields_zero_score_without_raising() -> None:
    """Proves: STORY-027-AC-5

    A failing embedding call inside cosine() degrades to a Cosine Score of
    0.0 (the zero-norm rule) rather than raising to the caller.
    """

    def _fails_once(text: str) -> tuple[float, ...]:
        del text
        raise HttpTimeoutError(message="embedding call timed out")

    client = FakeLLMClient(embed_fn=_fails_once)
    service = make_embedding_service(
        client=client, provider_id=_PROVIDER, model_name=_MODEL, snapshot=make_snapshot()
    )

    score = service.cosine("response text", "golden answer text")

    assert score == 0.0
