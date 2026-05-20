"""Unit tests for AnthropicProvider."""

from unittest.mock import MagicMock

import anthropic
import httpx
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import HealthProbeResult, InferenceResponse, ModelDescriptor, StreamChunk
from ollama_llm_bench.backend.services.providers.anthropic_provider import AnthropicProvider

_PROVIDER_ID = "anthropic_cloud"
_API_KEY = "test-api-key"
_DEFAULT_MODELS: tuple[str, ...] = ("claude-opus-4-6", "claude-haiku-4-5")


def _make_provider(
    mocker: MockerFixture,
    *,
    provider_id: str = _PROVIDER_ID,
    api_key: str = _API_KEY,
    default_models: tuple[str, ...] = _DEFAULT_MODELS,
) -> tuple[AnthropicProvider, MagicMock]:
    """Create an AnthropicProvider with a patched anthropic.Anthropic client.

    Returns:
        Tuple of (provider instance, mock client instance).
    """
    mock_patch = mocker.patch("ollama_llm_bench.backend.services.providers.anthropic_provider.anthropic.Anthropic")
    mock_client = mock_patch.return_value
    provider = AnthropicProvider(
        provider_id=provider_id,
        api_key=api_key,
        default_models=default_models,
    )
    return provider, mock_client


def _make_sync_response(
    mocker: MockerFixture,
    *,
    text: str = "response text",
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> object:
    """Create a mock synchronous Anthropic Messages API response.

    Args:
        mocker: pytest-mock fixture.
        text: Text content returned in the first content block.
        input_tokens: Prompt token count.
        output_tokens: Completion token count.

    Returns:
        Mock object representing a Message response.
    """
    mock_response = mocker.Mock()
    mock_block = mocker.Mock()
    mock_block.type = "text"
    mock_block.text = text
    mock_response.content = [mock_block]
    mock_response.usage.input_tokens = input_tokens
    mock_response.usage.output_tokens = output_tokens
    return mock_response


def _make_stream_ctx(
    mocker: MockerFixture,
    *,
    text_deltas: list[str],
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> object:
    """Create a mock MessageStreamManager context manager.

    Args:
        mocker: pytest-mock fixture.
        text_deltas: List of text delta strings the stream will yield.
        input_tokens: Prompt token count on the final message.
        output_tokens: Completion token count on the final message.

    Returns:
        Mock context manager whose __enter__ yields a mock MessageStream.
    """
    mock_final_msg = mocker.Mock()
    mock_final_msg.usage.input_tokens = input_tokens
    mock_final_msg.usage.output_tokens = output_tokens

    mock_stream_ctx = mocker.MagicMock()
    mock_stream_ctx.__enter__.return_value = mock_stream_ctx
    mock_stream_ctx.__exit__.return_value = False
    mock_stream_ctx.text_stream = text_deltas
    mock_stream_ctx.get_final_message.return_value = mock_final_msg
    return mock_stream_ctx


def _drain_stream(
    provider: AnthropicProvider,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> tuple[list[StreamChunk], InferenceResponse]:
    """Exhaust a streaming generator and collect chunks plus the return value.

    Args:
        provider: AnthropicProvider under test.
        model: Model name passed to inference_stream.
        messages: Messages list passed to inference_stream.
        temperature: Sampling temperature.
        max_tokens: Max output token count.

    Returns:
        Tuple of (list of yielded StreamChunk objects, final InferenceResponse).
    """
    gen = provider.inference_stream(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    chunks: list[StreamChunk] = []
    final_response: InferenceResponse | None = None
    try:
        while True:
            chunks.append(next(gen))
    except StopIteration as exc:
        final_response = exc.value
    assert final_response is not None
    return chunks, final_response


class TestAnthropicProviderProperties:
    """Tests for provider identity properties."""

    def test_provider_id_returns_injected_value(self, mocker: MockerFixture) -> None:
        # Arrange / Act
        provider, _ = _make_provider(mocker, provider_id="my_anthropic")

        # Assert
        assert provider.provider_id == "my_anthropic"

    def test_provider_type_returns_anthropic(self, mocker: MockerFixture) -> None:
        # Arrange / Act
        provider, _ = _make_provider(mocker)

        # Assert
        assert provider.provider_type == "anthropic"


class TestAnthropicProviderGetAvailableModels:
    """Tests for get_available_models."""

    def test_get_available_models_returns_correct_count(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker, default_models=("claude-opus-4-6", "claude-haiku-4-5"))

        # Act
        models = provider.get_available_models()

        # Assert
        assert len(models) == 2

    def test_get_available_models_display_label_includes_provider_id(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(
            mocker,
            provider_id="anthropic_cloud",
            default_models=("claude-opus-4-6",),
        )

        # Act
        models = provider.get_available_models()

        # Assert
        assert models[0].display_label == "anthropic_cloud / claude-opus-4-6"

    def test_get_available_models_parsed_fields_are_none(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker, default_models=("claude-opus-4-6",))

        # Act
        models = provider.get_available_models()

        # Assert
        descriptor = models[0]
        assert descriptor.model_family is None
        assert descriptor.model_size_b is None
        assert descriptor.quantization_label is None

    def test_get_available_models_empty_default_models_returns_empty_list(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker, default_models=())

        # Act
        models = provider.get_available_models()

        # Assert
        assert models == []

    def test_get_available_models_returns_model_descriptor_instances(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker, default_models=("claude-opus-4-6",))

        # Act
        models = provider.get_available_models()

        # Assert
        assert all(isinstance(m, ModelDescriptor) for m in models)


class TestAnthropicProviderInferenceSync:
    """Tests for inference_sync."""

    def test_inference_sync_success_returns_populated_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, text="The answer is 42.", input_tokens=15, output_tokens=8)
        mock_client.messages.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "What is 6 * 7?"}],
        )

        # Assert
        assert result.llm_response == "The answer is 42."
        assert result.prompt_tokens == 15
        assert result.completion_tokens == 8
        assert result.has_error is False
        assert result.total_time_ms >= 0

    def test_inference_sync_extracts_system_message(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, text="ok")
        mock_client.messages.create.return_value = mock_response
        # Act
        provider.inference_sync(
            model="claude-opus-4-6",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"},
            ],
        )

        # Assert — system content extracted, system message excluded from messages kwarg
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "You are a helpful assistant."
        assert all(m["role"] != "system" for m in call_kwargs["messages"])

    def test_inference_sync_api_error_returns_error_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        dummy_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        api_error = anthropic.APIError("API request failed", dummy_request, body=None)
        mock_client.messages.create.side_effect = api_error
        # Act
        result = provider.inference_sync(
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert result.has_error is True
        assert result.error_message == "API request failed"

    def test_inference_sync_empty_content_returns_empty_llm_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_response.content = []
        mock_response.usage.input_tokens = 5
        mock_response.usage.output_tokens = 0
        mock_client.messages.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert result.llm_response == ""
        assert result.has_error is False

    def test_inference_sync_non_text_block_excluded_from_response(self, mocker: MockerFixture) -> None:
        # Arrange — content block is a tool_use block (not text)
        provider, mock_client = _make_provider(mocker)
        mock_tool_block = mocker.Mock()
        mock_tool_block.type = "tool_use"
        mock_response = mocker.Mock()
        mock_response.content = [mock_tool_block]
        mock_response.usage.input_tokens = 5
        mock_response.usage.output_tokens = 0
        mock_client.messages.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert — no text block found, response falls back to empty string
        assert result.llm_response == ""
        assert result.has_error is False


class TestAnthropicProviderInferenceStream:
    """Tests for inference_stream."""

    def test_inference_stream_yields_chunks_and_returns_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        stream_ctx = _make_stream_ctx(mocker, text_deltas=["Hello", " world"], input_tokens=10, output_tokens=5)
        mock_client.messages.stream.return_value = stream_ctx
        # Act
        chunks, final_response = _drain_stream(
            provider,
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert len(chunks) == 2
        assert chunks[0].delta_content == "Hello"
        assert chunks[1].delta_content == " world"
        assert final_response.llm_response == "Hello world"
        assert final_response.completion_tokens == 5
        assert final_response.prompt_tokens == 10
        assert final_response.has_error is False

    def test_inference_stream_yields_stream_chunk_instances(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        stream_ctx = _make_stream_ctx(mocker, text_deltas=["Hi"])
        mock_client.messages.stream.return_value = stream_ctx
        # Act
        chunks, _ = _drain_stream(
            provider,
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert all(isinstance(c, StreamChunk) for c in chunks)

    def test_inference_stream_ttft_ms_set_on_first_content_chunk(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        stream_ctx = _make_stream_ctx(mocker, text_deltas=["token1", "token2"])
        mock_client.messages.stream.return_value = stream_ctx
        # Act
        _, final_response = _drain_stream(
            provider,
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert final_response.ttft_ms is not None
        assert final_response.ttft_ms >= 0

    def test_inference_stream_empty_deltas_sets_ttft_ms_none(self, mocker: MockerFixture) -> None:
        # Arrange — all deltas are empty strings, so ttft is never set
        provider, mock_client = _make_provider(mocker)
        stream_ctx = _make_stream_ctx(mocker, text_deltas=["", ""])
        mock_client.messages.stream.return_value = stream_ctx
        # Act
        chunks, final_response = _drain_stream(
            provider,
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert chunks == []
        assert final_response.ttft_ms is None

    def test_inference_stream_api_error_returns_error_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        dummy_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        api_error = anthropic.APIError("stream connection failed", dummy_request, body=None)
        mock_client.messages.stream.side_effect = api_error
        # Act
        chunks, final_response = _drain_stream(
            provider,
            model="claude-opus-4-6",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert chunks == []
        assert final_response.has_error is True
        assert final_response.error_message == "stream connection failed"


class TestAnthropicProviderCapabilities:
    """Tests for capability flag methods."""

    def test_supports_structured_output_returns_false(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker)

        # Act / Assert
        assert provider.supports_structured_output() is False

    def test_supports_streaming_returns_true(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker)

        # Act / Assert
        assert provider.supports_streaming() is True


class TestAnthropicProviderWarmUp:
    """Tests for warm_up."""

    def test_warm_up_success_returns_true(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, text="hi")
        mock_client.messages.create.return_value = mock_response
        # Act
        result = provider.warm_up("claude-opus-4-6")

        # Assert
        assert result is True

    def test_warm_up_failure_returns_false(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        dummy_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        api_error = anthropic.APIError("connection refused", dummy_request, body=None)
        mock_client.messages.create.side_effect = api_error
        # Act
        result = provider.warm_up("claude-opus-4-6")

        # Assert
        assert result is False

    def test_warm_up_sends_minimal_request(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, text="ok")
        mock_client.messages.create.return_value = mock_response
        # Act
        provider.warm_up("claude-opus-4-6")

        # Assert — model name and minimal max_tokens passed
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-6"
        assert call_kwargs["max_tokens"] == 1


class TestAnthropicProviderExtractSystemMessage:
    """Tests for _extract_system_message static method."""

    def test_extract_system_message_single_system_entry(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]

        # Act
        system_text, non_system = AnthropicProvider._extract_system_message(messages)

        # Assert
        assert system_text == "You are helpful."
        assert len(non_system) == 1

    def test_extract_system_message_joins_multiple_system_entries(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "Part one."},
            {"role": "system", "content": "Part two."},
            {"role": "user", "content": "Hello"},
        ]

        # Act
        system_text, non_system = AnthropicProvider._extract_system_message(messages)

        # Assert
        assert system_text == "Part one. Part two."
        assert len(non_system) == 1

    def test_extract_system_message_no_system_returns_empty_string(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = [
            {"role": "user", "content": "Hello"},
        ]

        # Act
        system_text, non_system = AnthropicProvider._extract_system_message(messages)

        # Assert
        assert system_text == ""
        assert len(non_system) == 1

    def test_extract_system_message_non_system_messages_preserved(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "System."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]

        # Act
        _, non_system = AnthropicProvider._extract_system_message(messages)

        # Assert
        assert len(non_system) == 2
        assert all(m["role"] != "system" for m in non_system)

    def test_extract_system_message_empty_messages_returns_empty(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = []

        # Act
        system_text, non_system = AnthropicProvider._extract_system_message(messages)

        # Assert
        assert system_text == ""
        assert non_system == []


# ---------------------------------------------------------------------------
# Constructor — base_url forwarding
# ---------------------------------------------------------------------------


def test_constructor_without_base_url_uses_default_endpoint(mocker: MockerFixture) -> None:
    # Arrange
    mock_cls = mocker.patch("ollama_llm_bench.backend.services.providers.anthropic_provider.anthropic.Anthropic")

    # Act
    AnthropicProvider(
        provider_id=_PROVIDER_ID,
        api_key=_API_KEY,
        default_models=_DEFAULT_MODELS,
    )

    # Assert — base_url must NOT be passed to the SDK constructor
    call_kwargs = mock_cls.call_args.kwargs
    assert "base_url" not in call_kwargs


def test_constructor_with_base_url_passes_it_to_sdk(mocker: MockerFixture) -> None:
    # Arrange
    mock_cls = mocker.patch("ollama_llm_bench.backend.services.providers.anthropic_provider.anthropic.Anthropic")
    proxy_url = "https://proxy.example.com"

    # Act
    AnthropicProvider(
        provider_id=_PROVIDER_ID,
        api_key=_API_KEY,
        default_models=_DEFAULT_MODELS,
        base_url=proxy_url,
    )

    # Assert
    call_kwargs = mock_cls.call_args.kwargs
    assert call_kwargs.get("base_url") == proxy_url


class TestAnthropicProviderProbeHealth:
    """Tests for probe_health."""

    def test_probe_health_reachable_returns_model_count(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        model_item = mocker.Mock()
        mock_client.models.list.return_value.data = [model_item]

        # Act
        result = provider.probe_health()

        # Assert
        assert isinstance(result, HealthProbeResult)
        assert result.reachable is True
        assert result.model_count_observed == 1

    def test_probe_health_auth_error_returns_not_reachable(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.list.side_effect = anthropic.AuthenticationError(
            message="Invalid API key",
            response=mocker.Mock(),
            body=None,
        )

        # Act
        result = provider.probe_health()

        # Assert
        assert result.reachable is False
        assert result.error_message == "Authentication failed — check API key."

    def test_probe_health_connection_error_returns_not_reachable(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.list.side_effect = anthropic.APIConnectionError(request=mocker.Mock())

        # Act
        result = provider.probe_health()

        # Assert
        assert result.reachable is False
        assert result.error_message is not None
