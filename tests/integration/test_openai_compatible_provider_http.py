"""Integration tests for OpenAICompatibleProvider using a real localhost HTTP server."""

import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.core.models import ModelDescriptor, ProviderType, StreamChunk
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser
from ollama_llm_bench.backend.services.providers.openai_compatible_provider import OpenAICompatibleProvider

_MODEL = "llama3.2:3b"
_MESSAGES = [{"role": "user", "content": "What is 2+2?"}]

_SYNC_RESPONSE = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
}

_MODELS_RESPONSE = {
    "object": "list",
    "data": [
        {"id": "llama3.2:3b", "object": "model", "owned_by": "library"},
        {"id": "qwen2.5:7b", "object": "model", "owned_by": "library"},
    ],
}

_SSE_BODY = (
    'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}],"usage":null}\n\n'
    'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" world"},"finish_reason":null}],"usage":null}\n\n'
    'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":"stop"}],"usage":null}\n\n'
    'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","choices":[],"usage":{"prompt_tokens":5,"completion_tokens":3,"total_tokens":8}}\n\n'
    "data: [DONE]\n\n"
)


@pytest.fixture
def name_parser() -> ModelNameParser:
    return ModelNameParser()


@pytest.fixture
def provider(httpserver: HTTPServer, name_parser: ModelNameParser) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_id="test",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        base_url=httpserver.url_for("/v1"),
        api_key="test-key",
        name_parser=name_parser,
    )


def test_sync_inference_success(httpserver: HTTPServer, provider: OpenAICompatibleProvider) -> None:
    httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_json(_SYNC_RESPONSE)

    result = provider.inference_sync(model=_MODEL, messages=_MESSAGES)

    assert result.has_error is False
    assert result.llm_response == "Hello"
    assert result.total_time_ms >= 0


def test_sync_inference_api_error(httpserver: HTTPServer, provider: OpenAICompatibleProvider) -> None:
    httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_data(
        '{"error":{"message":"bad request","type":"invalid_request_error"}}',
        status=400,
        content_type="application/json",
    )

    result = provider.inference_sync(model=_MODEL, messages=_MESSAGES)

    assert result.has_error is True
    assert result.error_message


def test_stream_inference_yields_chunks(httpserver: HTTPServer, provider: OpenAICompatibleProvider) -> None:
    httpserver.expect_request("/v1/chat/completions", method="POST").respond_with_data(
        _SSE_BODY,
        content_type="text/event-stream",
    )

    chunks = list(provider.inference_stream(model=_MODEL, messages=_MESSAGES))

    assert len(chunks) == 3
    assert all(isinstance(c, StreamChunk) for c in chunks)
    assert all(c.delta_content for c in chunks)


def test_get_available_models_success(httpserver: HTTPServer, provider: OpenAICompatibleProvider) -> None:
    httpserver.expect_request("/v1/models").respond_with_json(_MODELS_RESPONSE)

    models = provider.get_available_models()

    assert len(models) == 2
    assert all(isinstance(m, ModelDescriptor) for m in models)


def test_get_available_models_error(httpserver: HTTPServer, provider: OpenAICompatibleProvider) -> None:
    httpserver.expect_request("/v1/models").respond_with_data("Internal Server Error", status=500)

    models = provider.get_available_models()

    assert models == []
