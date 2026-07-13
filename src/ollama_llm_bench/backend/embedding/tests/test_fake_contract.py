"""Shared contract-test suite proving FakeEmbeddingService is a faithful stand-in
for the concrete EmbeddingService (testing.md's per-Protocol contract-suite rule)."""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.embedding.api import make_embedding_service
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.embedding.testing import FakeEmbeddingService
from ollama_llm_bench.backend.embedding.tests.conftest import FakeLLMClient, make_snapshot

_CUSTOM_THRESHOLD = 0.5


def _make_real() -> EmbeddingService:
    return make_embedding_service(
        client=FakeLLMClient(),
        provider_id="p1",
        model_name="embed-model",
        snapshot=make_snapshot(),
    )


def _make_fake() -> EmbeddingService:
    return FakeEmbeddingService()


@pytest.mark.parametrize("make_service", [_make_real, _make_fake], ids=["real", "fake"])
def test_embed_returns_nonempty_vector_for_nonempty_text(
    make_service: Callable[[], EmbeddingService],
) -> None:
    """Both implementations return a non-empty vector for ordinary text."""
    service = make_service()

    vector = service.embed("hello world")

    assert len(vector) > 0


@pytest.mark.parametrize("make_service", [_make_real, _make_fake], ids=["real", "fake"])
def test_embed_is_deterministic_for_the_same_text(
    make_service: Callable[[], EmbeddingService],
) -> None:
    """Both implementations return the same vector for the same text twice."""
    service = make_service()

    first = service.embed("repeated text")
    second = service.embed("repeated text")

    assert first == second


@pytest.mark.parametrize("make_service", [_make_real, _make_fake], ids=["real", "fake"])
def test_cosine_of_identical_text_is_one(make_service: Callable[[], EmbeddingService]) -> None:
    """Both implementations score identical texts at cosine 1.0."""
    service = make_service()

    score = service.cosine("identical text", "identical text")

    assert score == pytest.approx(1.0)


@pytest.mark.parametrize("make_service", [_make_real, _make_fake], ids=["real", "fake"])
def test_cosine_threshold_default_matches_spec_default(
    make_service: Callable[[], EmbeddingService],
) -> None:
    """Both implementations default cosine_threshold() to the spec §7 default (0.85)."""
    service = make_service()

    assert service.cosine_threshold() == pytest.approx(0.85)


@pytest.mark.parametrize("make_service", [_make_real, _make_fake], ids=["real", "fake"])
def test_is_short_circuited_defaults_false(make_service: Callable[[], EmbeddingService]) -> None:
    """Both implementations start with the cosine dimension not short-circuited."""
    service = make_service()

    assert service.is_short_circuited() is False


def test_fake_set_cosine_threshold_overrides_the_lookup() -> None:
    """The fake's threshold-override test helper changes cosine_threshold()'s return."""
    fake = FakeEmbeddingService()

    fake.set_cosine_threshold(_CUSTOM_THRESHOLD)

    assert fake.cosine_threshold() == _CUSTOM_THRESHOLD


def test_fake_set_short_circuited_forces_embed_to_return_empty_vector() -> None:
    """The fake's short-circuit test helper degrades embed() to an empty vector."""
    fake = FakeEmbeddingService()

    fake.set_short_circuited(short_circuited=True)

    assert fake.is_short_circuited() is True
    assert fake.embed("anything") == ()


def test_fake_records_embed_and_cosine_calls_for_assertion() -> None:
    """The fake's call logs let a downstream test assert what it was asked to embed/compare."""
    fake = FakeEmbeddingService()

    fake.embed("solo text")
    fake.cosine("response", "golden")

    assert "solo text" in fake.embed_calls
    assert ("response", "golden") in fake.cosine_calls
