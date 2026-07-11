"""Tests proving STORY-018-AC-7: ``probe_health``/``list_models`` per the story's
four-scenario table, plus the distinction between the zero-models-is-healthy case
and a genuine ``list_models()`` failure.

Source of truth: ``docs/stories/story-018-openai-compatible-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.8.1, §6.9.1.

Table-driven (Pattern B): the story's AC-7 table enumerates a finite scenario set,
each an integration-tier wire-stub case (real adapter, real ``openai`` SDK, real
local HTTP server) — no monkeypatching.
"""

from collections.abc import Callable

import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.errors import AppError
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)

_EXPECTED_ZERO_MODELS = 0


def test_unreachable_host_reports_unreachable_without_raising(
    make_client: Callable[..., OpenAICompatibleClient],
) -> None:
    """Proves: STORY-018-AC-7

    Given an unreachable host (connection refused), when ``probe_health`` is
    called, then it returns ``reachable=False, discovery_supported=True,
    model_count=None, last_error=<redacted>`` — discovery is not attempted —
    and never raises.
    """
    # Arrange: port 1 is a reserved, always-refused port on every OS.
    client = make_client(base_url="http://127.0.0.1:1/")

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is False
    assert health.discovery_supported is True
    assert health.model_count is None
    assert health.last_error is not None


def test_reachable_with_zero_models_is_healthy(
    httpserver: HTTPServer, make_client: Callable[..., OpenAICompatibleClient]
) -> None:
    """Proves: STORY-018-AC-7

    Given a reachable endpoint whose ``GET /v1/models`` lists zero models,
    when ``probe_health`` is called, then it returns ``reachable=True,
    discovery_supported=True, model_count=0, last_error=None`` — zero
    models is a healthy result, not a failure.
    """
    # Arrange
    httpserver.expect_request("/", method="GET").respond_with_json({"ok": True})
    httpserver.expect_request("/models", method="GET").respond_with_json(
        {"object": "list", "data": []}
    )
    client = make_client()

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is True
    assert health.discovery_supported is True
    assert health.model_count == _EXPECTED_ZERO_MODELS
    assert health.last_error is None


def test_reachable_with_listing_5xx_still_reports_reachable(
    httpserver: HTTPServer, make_client: Callable[..., OpenAICompatibleClient]
) -> None:
    """Proves: STORY-018-AC-7

    Given a reachable endpoint whose listing call returns a 5xx, when
    ``probe_health`` is called, then it returns ``reachable=True,
    discovery_supported=True, model_count=None, last_error=<redacted>`` —
    distinct from the unreachable-host case: the reachability handshake
    succeeded even though discovery itself failed.
    """
    # Arrange
    httpserver.expect_request("/", method="GET").respond_with_json({"ok": True})
    httpserver.expect_request("/models", method="GET").respond_with_json(
        {"error": {"message": "internal error"}}, status=500
    )
    client = make_client()

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is True
    assert health.discovery_supported is True
    assert health.model_count is None
    assert health.last_error is not None


def test_list_models_raises_when_listing_call_fails(
    httpserver: HTTPServer, make_client: Callable[..., OpenAICompatibleClient]
) -> None:
    """Proves: STORY-018-AC-7

    Given the listing call fails, when ``list_models()`` is called directly
    (not ``probe_health``), then it raises ``ProviderError`` — distinct from
    ``probe_health``'s never-raising, zero-models-is-healthy contract.
    """
    # Arrange
    httpserver.expect_request("/models", method="GET").respond_with_json(
        {"error": {"message": "internal error"}}, status=500
    )
    client = make_client()

    # Act / Assert
    with pytest.raises(AppError):
        client.list_models()
