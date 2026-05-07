"""Unit tests for GeminiProvider."""

from unittest.mock import MagicMock

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import InferenceResponse, ModelDescriptor, StreamChunk
from ollama_llm_bench.backend.services.providers.gemini_provider import GeminiProvider

_PROVIDER_ID = "gemini_cloud"
_API_KEY = "test-api-key"
_DEFAULT_MODELS: tuple[str, ...] = ("gemini-2.0-flash",)


def _make_provider(
    mocker: MockerFixture,
    *,
    provider_id: str = _PROVIDER_ID,
    api_key: str = _API_KEY,
    default_models: tuple[str, ...] = _DEFAULT_MODELS,
    base_url: str | None = None,
) -> tuple[GeminiProvider, MagicMock]:
    """Create a GeminiProvider with a patched google.genai.Client.

    Returns:
        Tuple of (provider instance, mock client instance).
    """
    mock_patch = mocker.patch("ollama_llm_bench.backend.services.providers.gemini_provider.google.genai.Client")
    mock_client = mock_patch.return_value
    provider = GeminiProvider(
        provider_id=provider_id,
        api_key=api_key,
        default_models=default_models,
        base_url=base_url,
    )
    return provider, mock_client


def _make_chunk(
    mocker: MockerFixture,
    text: str,
    *,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> object:
    """Create a mock Gemini streaming chunk.

    Args:
        mocker: pytest-mock fixture.
        text: Delta text content for this chunk.
        prompt_tokens: Prompt token count, or None if usage_metadata absent.
        completion_tokens: Completion token count, or None if usage_metadata absent.

    Returns:
        Mock object representing a single stream chunk.
    """
    chunk = mocker.Mock()
    chunk.text = text
    if prompt_tokens is not None:
        chunk.usage_metadata.prompt_token_count = prompt_tokens
        chunk.usage_metadata.candidates_token_count = completion_tokens
    else:
        chunk.usage_metadata = None
    return chunk


def _drain_stream(
    provider: GeminiProvider,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> tuple[list[StreamChunk], InferenceResponse]:
    """Exhaust a streaming generator and collect chunks plus the return value.

    Args:
        provider: GeminiProvider under test.
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


class TestGeminiProviderProperties:
    """Tests for provider identity properties."""

    def test_provider_id_returns_injected_value(self, mocker: MockerFixture) -> None:
        # Arrange / Act
        provider, _ = _make_provider(mocker, provider_id="my_gemini")

        # Assert
        assert provider.provider_id == "my_gemini"

    def test_provider_type_returns_gemini(self, mocker: MockerFixture) -> None:
        # Arrange / Act
        provider, _ = _make_provider(mocker)

        # Assert
        assert provider.provider_type == "gemini"


class TestGeminiProviderGetAvailableModels:
    """Tests for get_available_models."""

    def test_get_available_models_returns_correct_count(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker, default_models=("gemini-2.0-flash",))

        # Act
        models = provider.get_available_models()

        # Assert
        assert len(models) == 1

    def test_get_available_models_display_label_format(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(
            mocker,
            provider_id="gemini_cloud",
            default_models=("gemini-2.0-flash",),
        )

        # Act
        models = provider.get_available_models()

        # Assert
        assert models[0].display_label == "gemini_cloud / gemini-2.0-flash"

    def test_get_available_models_parsed_fields_are_none(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker, default_models=("gemini-2.0-flash",))

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
        provider, _ = _make_provider(mocker, default_models=("gemini-2.0-flash",))

        # Act
        models = provider.get_available_models()

        # Assert
        assert all(isinstance(m, ModelDescriptor) for m in models)


class TestGeminiProviderInferenceSync:
    """Tests for inference_sync."""

    def test_inference_sync_success_returns_populated_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_response.text = "The answer is 42."
        mock_response.usage_metadata.prompt_token_count = 15
        mock_response.usage_metadata.candidates_token_count = 8
        mock_client.models.generate_content.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "What is 6 * 7?"}],
        )

        # Assert
        assert result.llm_response == "The answer is 42."
        assert result.prompt_tokens == 15
        assert result.completion_tokens == 8
        assert result.has_error is False
        assert result.total_time_ms >= 0

    def test_inference_sync_system_message_passed_as_system_instruction(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_response.text = "ok"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response
        # Act
        provider.inference_sync(
            model="gemini-2.0-flash",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"},
            ],
        )

        # Assert
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config = call_kwargs["config"]
        assert config.system_instruction == "You are a helpful assistant."

    def test_inference_sync_assistant_role_converted_to_model(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_response.text = "Sure"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ]

        # Act
        provider.inference_sync(model="gemini-2.0-flash", messages=messages)

        # Assert
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        contents = call_kwargs["contents"]
        roles = [c.role for c in contents]
        assert "assistant" not in roles
        assert "model" in roles

    def test_inference_sync_no_system_message_sets_system_instruction_none(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_response.text = "hi"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response
        # Act
        provider.inference_sync(
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "Hello"}],
        )

        # Assert
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config = call_kwargs["config"]
        assert config.system_instruction is None

    def test_inference_sync_exception_returns_error_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.generate_content.side_effect = Exception("API error")
        # Act
        result = provider.inference_sync(
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert result.has_error is True
        assert result.error_message == "API error"

    def test_inference_sync_null_usage_metadata_sets_none_prompt_tokens(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_response.text = "response text"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert result.prompt_tokens is None
        assert result.completion_tokens == 0


class TestGeminiProviderInferenceStream:
    """Tests for inference_stream."""

    def test_inference_stream_yields_chunks_and_returns_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.generate_content_stream.return_value = iter(
            [
                _make_chunk(mocker, "Hello"),
                _make_chunk(mocker, " world", prompt_tokens=10, completion_tokens=5),
            ]
        )

        # Act
        chunks, final_response = _drain_stream(
            provider,
            model="gemini-2.0-flash",
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
        mock_client.models.generate_content_stream.return_value = iter([_make_chunk(mocker, "Hi")])

        # Act
        chunks, _ = _drain_stream(
            provider,
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert all(isinstance(c, StreamChunk) for c in chunks)

    def test_inference_stream_ttft_ms_set_on_first_content_chunk(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.generate_content_stream.return_value = iter(
            [
                _make_chunk(mocker, "token1"),
                _make_chunk(mocker, "token2", prompt_tokens=5, completion_tokens=2),
            ]
        )

        # Act
        _, final_response = _drain_stream(
            provider,
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert final_response.ttft_ms is not None
        assert final_response.ttft_ms >= 0

    def test_inference_stream_empty_chunks_sets_ttft_ms_none(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        # A chunk with empty text does not set ttft
        empty_chunk = mocker.Mock()
        empty_chunk.text = ""
        empty_chunk.usage_metadata = None
        mock_client.models.generate_content_stream.return_value = iter([empty_chunk])
        # Act
        chunks, final_response = _drain_stream(
            provider,
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert chunks == []
        assert final_response.ttft_ms is None

    def test_inference_stream_exception_returns_error_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.generate_content_stream.side_effect = Exception("stream error")

        # Act
        chunks, final_response = _drain_stream(
            provider,
            model="gemini-2.0-flash",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert chunks == []
        assert final_response.has_error is True
        assert final_response.error_message == "stream error"


class TestGeminiProviderCapabilities:
    """Tests for capability flag methods."""

    def test_supports_structured_output_returns_true(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker)

        # Act / Assert
        assert provider.supports_structured_output() is True

    def test_supports_streaming_returns_true(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker)

        # Act / Assert
        assert provider.supports_streaming() is True


class TestGeminiProviderWarmUp:
    """Tests for warm_up."""

    def test_warm_up_success_returns_true(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_response.text = "hi"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response
        # Act
        result = provider.warm_up("gemini-2.0-flash")

        # Assert
        assert result is True

    def test_warm_up_failure_returns_false(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.generate_content.side_effect = Exception("connection refused")
        # Act
        result = provider.warm_up("gemini-2.0-flash")

        # Assert
        assert result is False

    def test_warm_up_sends_minimal_request(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_response.text = "ok"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response
        # Act
        provider.warm_up("gemini-2.0-flash")

        # Assert — verify model name passed through
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.0-flash"
        config = call_kwargs["config"]
        assert config.max_output_tokens == 1


class TestGeminiProviderBuildContents:
    """Tests for _build_contents static method."""

    def test_build_contents_filters_system_messages(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]

        # Act
        contents = GeminiProvider._build_contents(messages)

        # Assert
        roles = [c.role for c in contents]
        assert "system" not in roles
        assert len(contents) == 1

    def test_build_contents_maps_assistant_to_model_role(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = [
            {"role": "assistant", "content": "I can help."},
        ]

        # Act
        contents = GeminiProvider._build_contents(messages)

        # Assert
        assert contents[0].role == "model"

    def test_build_contents_preserves_user_role(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = [
            {"role": "user", "content": "Hi"},
        ]

        # Act
        contents = GeminiProvider._build_contents(messages)

        # Assert
        assert contents[0].role == "user"

    def test_build_contents_empty_messages_returns_empty_list(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = []

        # Act
        contents = GeminiProvider._build_contents(messages)

        # Assert
        assert contents == []


class TestGeminiProviderExtractSystemMessage:
    """Tests for _extract_system_message static method."""

    def test_extract_system_message_joins_multiple_system_entries(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "Part one."},
            {"role": "system", "content": "Part two."},
            {"role": "user", "content": "Hello"},
        ]

        # Act
        system_text, non_system = GeminiProvider._extract_system_message(messages)

        # Assert
        assert system_text == "Part one. Part two."
        assert len(non_system) == 1

    def test_extract_system_message_no_system_returns_empty_string(self) -> None:
        # Arrange
        messages: list[dict[str, str]] = [
            {"role": "user", "content": "Hello"},
        ]

        # Act
        system_text, non_system = GeminiProvider._extract_system_message(messages)

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
        _, non_system = GeminiProvider._extract_system_message(messages)

        # Assert
        assert len(non_system) == 2
        assert all(m["role"] != "system" for m in non_system)


# ---------------------------------------------------------------------------
# Constructor — base_url forwarding
# ---------------------------------------------------------------------------


def test_constructor_without_base_url_uses_default_endpoint(mocker: MockerFixture) -> None:
    # Arrange
    mock_cls = mocker.patch("ollama_llm_bench.backend.services.providers.gemini_provider.google.genai.Client")

    # Act
    GeminiProvider(
        provider_id=_PROVIDER_ID,
        api_key=_API_KEY,
        default_models=_DEFAULT_MODELS,
    )

    # Assert — http_options must NOT be passed to the SDK constructor
    call_kwargs = mock_cls.call_args.kwargs
    assert "http_options" not in call_kwargs


def test_constructor_with_base_url_passes_http_options(mocker: MockerFixture) -> None:
    # Arrange
    mock_cls = mocker.patch("ollama_llm_bench.backend.services.providers.gemini_provider.google.genai.Client")
    proxy_url = "https://proxy.example.com"

    # Act
    GeminiProvider(
        provider_id=_PROVIDER_ID,
        api_key=_API_KEY,
        default_models=_DEFAULT_MODELS,
        base_url=proxy_url,
    )

    # Assert
    call_kwargs = mock_cls.call_args.kwargs
    assert "http_options" in call_kwargs
    assert call_kwargs["http_options"].base_url == proxy_url
