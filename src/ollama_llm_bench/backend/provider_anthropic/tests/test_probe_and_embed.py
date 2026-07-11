"""Tests proving STORY-019-AC-6: ``probe_health``/``embed`` per the story's
three-scenario table, plus a plain unit test for ``list_models()`` (Protocol
completeness, no story AC id).

Source of truth: ``docs/stories/story-019-anthropic-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.8.1, §6.9.1.

Table-driven (Pattern B) for the reachable/unreachable ``probe_health``
scenarios (both integration-tier, real adapter + real ``anthropic`` SDK
against a local wire stub); a separate Given/When/Then test for ``embed``'s
immediate-raise, no-network-call contract, since that scenario is not a
variation on the same probe_health return-shape table.
"""

from collections.abc import Callable

import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.errors import AppError, ProviderBadRequestError
from ollama_llm_bench.backend.provider_anthropic._internal.client_impl import AnthropicClient

_EXPECTED_ZERO_REQUESTS = 0


def test_probe_health_reachable_reports_no_discovery_and_never_raises(
    httpserver: HTTPServer, make_client: Callable[..., AnthropicClient]
) -> None:
    """Proves: STORY-019-AC-6

    Given a reachable Anthropic provider, when ``probe_health`` is called,
    then it returns ``reachable=True, discovery_supported=False,
    model_count=None`` with no models-list call issued, and never raises.
    """
    # Arrange
    httpserver.expect_request("/", method="GET").respond_with_json({"ok": True})
    client = make_client()

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is True
    assert health.discovery_supported is False
    assert health.model_count is None
    assert len(httpserver.log) == 1  # exactly the reachability GET; no models-list call


def test_probe_health_unreachable_host_reports_unreachable_without_raising(
    make_client: Callable[..., AnthropicClient],
) -> None:
    """Proves: STORY-019-AC-6

    Given an unreachable host (connection refused), when ``probe_health`` is
    called, then it returns ``reachable=False, discovery_supported=False,
    model_count=None, last_error=<redacted>``, and never raises.
    """
    # Arrange: port 1 is a reserved, always-refused port on every OS.
    client = make_client(base_url="http://127.0.0.1:1/")

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is False
    assert health.discovery_supported is False
    assert health.model_count is None
    assert health.last_error is not None


def test_embed_raises_immediately_with_no_network_call(
    httpserver: HTTPServer, make_client: Callable[..., AnthropicClient]
) -> None:
    """Proves: STORY-019-AC-6

    Given the Anthropic client (which exposes no embeddings endpoint), when
    ``embed(text)`` is called, then it raises ``ProviderBadRequestError``
    immediately with no network call issued.
    """
    # Arrange
    client = make_client()

    # Act / Assert
    with pytest.raises(ProviderBadRequestError):
        client.embed("hello world")
    assert len(httpserver.log) == _EXPECTED_ZERO_REQUESTS


def test_list_models_raises_immediately_with_no_network_call(
    httpserver: HTTPServer, make_client: Callable[..., AnthropicClient]
) -> None:
    """Not tied to a story AC id — Protocol completeness/coverage.

    Given the Anthropic client (which exposes no models-list endpoint), when
    ``list_models()`` is called, then it raises immediately with no network
    call issued.
    """
    # Arrange
    client = make_client()

    # Act / Assert
    with pytest.raises(AppError):
        client.list_models()
    assert len(httpserver.log) == _EXPECTED_ZERO_REQUESTS
