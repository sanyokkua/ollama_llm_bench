"""Tests proving STORY-020-AC-6: reachability + conditional discovery, and the
SDK-absent fallback, per the story's probe-scenario table.

Source of truth: ``docs/stories/story-020-gemini-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.8.1, §6.9.1.
"""

from collections.abc import Callable

from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.provider_gemini._internal.client_impl import GeminiClient

_LIST_MODELS_PATH = "/v1beta/models"
_EXPECTED_MODEL_COUNT = 2


def test_probe_health_reachable_with_models(
    httpserver: HTTPServer, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-6

    Given the endpoint is reachable and the SDK's ``models.list()`` returns
    two models, when ``probe_health`` is called, then it returns
    ``ProviderHealth(reachable=True, discovery_supported=True,
    model_count=2)``.
    """
    # Arrange
    httpserver.expect_request(_LIST_MODELS_PATH, method="GET").respond_with_json(
        {"models": [{"name": "models/gemini-test-a"}, {"name": "models/gemini-test-b"}]}
    )
    client = make_client()

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is True
    assert health.discovery_supported is True
    assert health.model_count == _EXPECTED_MODEL_COUNT


def test_probe_health_reachable_with_zero_models_is_healthy(
    httpserver: HTTPServer, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-6

    Given the endpoint is reachable and the SDK's ``models.list()`` returns
    zero models, when ``probe_health`` is called, then it returns
    ``ProviderHealth(reachable=True, discovery_supported=True,
    model_count=0)`` — zero discovered models is never an unhealthy signal.
    """
    # Arrange
    httpserver.expect_request(_LIST_MODELS_PATH, method="GET").respond_with_json({"models": []})
    client = make_client()

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is True
    assert health.model_count == 0


class _ModelsWithoutList:
    """Strictly private, colocated-test-only double simulating an SDK build
    whose ``client.models`` object exposes no ``list`` attribute at all —
    ``google.genai.models.Models.list`` is a class-level method, so it
    cannot be removed from one instance with ``del``; substituting the
    ``Client``'s private ``_models`` backing attribute (its public
    ``models`` property is read-only) with an object that genuinely lacks
    ``list`` is the instance-scoped equivalent."""


def test_probe_health_sdk_build_lacks_models_list_falls_back(
    httpserver: HTTPServer, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-6

    Given the endpoint is reachable but the installed SDK build's
    ``client.models`` object exposes no ``list`` attribute at all, when
    ``probe_health`` is called, then it returns
    ``ProviderHealth(reachable=True, discovery_supported=False,
    model_count=None)`` — the SDK-absent fallback (§6.9.1), never a
    monkeypatch of SDK internals, only of the attribute presence itself to
    simulate an older SDK build the real pinned SDK does not currently ship.
    """
    # Arrange: any reachable response satisfies the reachability handshake.
    httpserver.expect_request("/", method="GET").respond_with_json({"ok": True})
    client = make_client()
    client._sdk_client._models = _ModelsWithoutList()  # type: ignore[assignment]  # simulate an SDK build without discovery support

    # Act
    health = client.probe_health()

    # Assert
    assert health.reachable is True
    assert health.discovery_supported is False
    assert health.model_count is None


def test_probe_health_unreachable_host_never_raises(
    make_client: Callable[..., GeminiClient],
) -> None:
    """Proves: STORY-020-AC-6

    Given the configured endpoint is unreachable, when ``probe_health`` is
    called, then it returns ``ProviderHealth(reachable=False,
    discovery_supported=True, model_count=None, last_error=<set>)`` and
    never raises; discovery is not attempted.
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
