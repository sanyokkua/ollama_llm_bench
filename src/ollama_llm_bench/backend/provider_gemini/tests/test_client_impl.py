"""Tests proving STORY-077-AC-9 and STORY-077-AC-10 for `GeminiClient`.

Source of truth: `docs/stories/story-077-composition-root-and-app-handle.md`;
`docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.9.

Given/When/Then (Pattern A) for both: each proves one concrete, single-scenario behaviour
(the reachability probe reuses the injected client; the two capability flags resolve to
their documented values) -- neither varies across an enumerable case set nor claims a
universal property over an open input domain.
"""

from collections.abc import Callable

import httpx
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.provider_gemini._internal.client_impl import GeminiClient


def test_probe_reachable_uses_injected_http_client_not_a_new_one(
    make_client: Callable[..., GeminiClient],
    http_client: httpx.Client,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-077-AC-9

    Given a provider's reachability probe is invoked after construction (mirroring
    `build_app`'s injected shared HTTP client), when the probe makes its HTTP request,
    then it issues that request on the single shared `httpx.Client` instance injected
    at construction -- no new `httpx.Client` is constructed for the probe.
    """
    # Arrange
    client = make_client()
    get_spy = mocker.spy(http_client, "get")
    new_client_spy = mocker.patch(
        "ollama_llm_bench.backend.provider_gemini._internal.client_impl.httpx.Client"
    )

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is True
    get_spy.assert_called_once()
    new_client_spy.assert_not_called()


def test_supports_embedding_and_supports_discovery(
    make_client: Callable[..., GeminiClient],
) -> None:
    """Proves: STORY-077-AC-10

    Given the Gemini `LLMClient`, when `supports_embedding()` and
    `supports_discovery()` are called, then `supports_embedding()` returns `True`
    unconditionally (Gemini always exposes an embeddings endpoint, §6.9) and
    `supports_discovery()` returns `True` because the installed, pinned SDK build's
    `client.models` object exposes `list` (the same `hasattr` check `probe_health`
    itself branches on, §6.9.1) -- not a guessed or unconditional placeholder.
    """
    # Arrange
    client = make_client()

    # Act
    supports_embedding = client.supports_embedding()
    supports_discovery = client.supports_discovery()

    # Assert
    assert supports_embedding is True
    assert supports_discovery is True
