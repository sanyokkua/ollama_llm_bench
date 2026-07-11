"""Tests proving STORY-018-AC-10: populated Azure fields select the Azure
transport, and the call succeeds against the Azure-shaped endpoint using the
same call shape as plain OpenAI-compatible mode.

Source of truth: ``docs/stories/story-018-openai-compatible-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`` §6.9
(SPEC-114).
"""

from collections.abc import Callable
import json

from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.provider_openai_compatible._internal.azure_mode import is_azure_mode
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible.tests.conftest import (
    FakeClock,
    make_chat_request,
    make_provider_config,
)

_AZURE_API_VERSION = "2024-06-01"
_AZURE_DEPLOYMENT = "test-deployment"


def test_is_azure_mode_true_only_when_all_three_fields_populated() -> None:
    """Proves: STORY-018-AC-10

    Given a provider config whose ``azure_endpoint_raw``,
    ``azure_deployment_raw``, and ``azure_api_version_raw`` are all
    populated, when ``is_azure_mode`` inspects it, then it returns ``True``;
    given any one of the three is missing, then it returns ``False``.
    """
    # Arrange
    full = make_provider_config(azure_fields=("https://x.example/", _AZURE_DEPLOYMENT, "v1"))
    partial = make_provider_config(azure_fields=("https://x.example/", None, "v1"))
    none = make_provider_config(azure_fields=(None, None, None))

    # Act / Assert
    assert is_azure_mode(full) is True
    assert is_azure_mode(partial) is False
    assert is_azure_mode(none) is False


def test_azure_fields_select_azure_transport(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    make_client: Callable[..., OpenAICompatibleClient],
) -> None:
    """Proves: STORY-018-AC-10

    Given an ``OPENAI_COMPATIBLE`` provider whose ``azure_endpoint``,
    ``azure_deployment``, and ``azure_api_version`` are all populated, when
    a chat call is issued, then the client selects the Azure transport and
    the call succeeds against the Azure-shaped endpoint using the same call
    shape (streaming SSE, usage capture) as plain OpenAI-compatible mode.
    """
    # Arrange: the Azure SDK client posts to
    # ``{endpoint}/openai/deployments/{deployment}/chat/completions``.
    azure_path = f"/openai/deployments/{_AZURE_DEPLOYMENT}/chat/completions"
    chunk = {
        "id": "1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": _AZURE_DEPLOYMENT,
        "choices": [{"index": 0, "delta": {"content": "azure-ok"}, "finish_reason": None}],
    }
    body = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"
    httpserver.expect_request(azure_path, method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    config = make_provider_config(
        azure_fields=(httpserver.url_for("/"), _AZURE_DEPLOYMENT, _AZURE_API_VERSION)
    )
    client = make_client(config=config)
    request = make_chat_request(model=_AZURE_DEPLOYMENT)
    token = CancellationToken(clock=fake_clock)

    # Act
    response = client.chat(request, token=token)

    # Assert
    assert response.text == "azure-ok"
