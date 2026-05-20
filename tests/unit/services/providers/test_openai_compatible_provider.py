"""Unit tests for OpenAICompatibleProvider."""

from unittest.mock import MagicMock

import openai
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import HealthProbeResult, InferenceResponse, ModelDescriptor, StreamChunk
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser
from ollama_llm_bench.backend.services.providers.openai_compatible_provider import OpenAICompatibleProvider

_PROVIDER_ID = "ollama_local"
_PROVIDER_TYPE = "openai_compatible"
_BASE_URL = "http://localhost:11434/v1"
_API_KEY = "test-key"


def _make_provider(
    mocker: MockerFixture,
    *,
    provider_id: str = _PROVIDER_ID,
    provider_type: str = _PROVIDER_TYPE,
    base_url: str = _BASE_URL,
    api_key: str = _API_KEY,
) -> tuple[OpenAICompatibleProvider, MagicMock]:
    """Create an OpenAICompatibleProvider with a patched openai.OpenAI client.

    Returns:
        Tuple of (provider instance, mock client instance).
    """
    mock_cls = mocker.patch("ollama_llm_bench.backend.services.providers.openai_compatible_provider.openai.OpenAI")
    mock_client = mock_cls.return_value
    provider = OpenAICompatibleProvider(
        provider_id=provider_id,
        provider_type=provider_type,
        base_url=base_url,
        api_key=api_key,
        name_parser=ModelNameParser(),
    )
    return provider, mock_client


def _make_sync_response(
    mocker: MockerFixture,
    *,
    content: str = "response text",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
) -> object:
    """Create a mock ChatCompletion response.

    Args:
        mocker: pytest-mock fixture.
        content: Text returned in choices[0].message.content.
        prompt_tokens: Prompt token count in usage.
        completion_tokens: Completion token count in usage.

    Returns:
        Mock object representing a ChatCompletion.
    """
    mock_response = mocker.Mock()
    mock_choice = mocker.Mock()
    mock_choice.message.content = content
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = prompt_tokens
    mock_response.usage.completion_tokens = completion_tokens
    return mock_response


def _make_stream_chunk(
    mocker: MockerFixture,
    *,
    delta_content: str | None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> object:
    """Create a mock ChatCompletionChunk.

    Args:
        mocker: pytest-mock fixture.
        delta_content: Text delta for this chunk, or None for a usage-only chunk.
        prompt_tokens: Prompt tokens in usage field, or None for content chunks.
        completion_tokens: Completion tokens in usage field, or None for content chunks.

    Returns:
        Mock object representing a single streaming chunk.
    """
    chunk = mocker.Mock()
    if prompt_tokens is not None:
        chunk.usage.prompt_tokens = prompt_tokens
        chunk.usage.completion_tokens = completion_tokens
    else:
        chunk.usage = None

    if delta_content is not None:
        mock_choice = mocker.Mock()
        mock_choice.delta.content = delta_content
        chunk.choices = [mock_choice]
    else:
        chunk.choices = []

    return chunk


def _drain_stream(
    provider: OpenAICompatibleProvider,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> tuple[list[StreamChunk], InferenceResponse]:
    """Exhaust a streaming generator and collect chunks plus the return value.

    Args:
        provider: OpenAICompatibleProvider under test.
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


class TestOpenAICompatibleProviderProperties:
    """Tests for provider identity properties."""

    def test_provider_id_returns_injected_value(self, mocker: MockerFixture) -> None:
        # Arrange / Act
        provider, _ = _make_provider(mocker, provider_id="my_ollama")

        # Assert
        assert provider.provider_id == "my_ollama"

    def test_provider_type_returns_injected_value(self, mocker: MockerFixture) -> None:
        # Arrange / Act
        provider, _ = _make_provider(mocker, provider_type="openai_compatible")

        # Assert
        assert provider.provider_type == "openai_compatible"


class TestOpenAICompatibleProviderGetAvailableModels:
    """Tests for get_available_models."""

    def test_get_available_models_returns_sorted_list(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        model_b = mocker.Mock()
        model_b.id = "zephyr:7b"
        model_a = mocker.Mock()
        model_a.id = "llama3:8b"
        mock_client.models.list.return_value.data = [model_b, model_a]
        # Act
        models = provider.get_available_models()

        # Assert — sorted by model_name ascending
        assert len(models) == 2
        assert models[0].model_name == "llama3:8b"
        assert models[1].model_name == "zephyr:7b"

    def test_get_available_models_display_label_includes_provider_id(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker, provider_id="ollama_local")
        model = mocker.Mock()
        model.id = "llama3:8b"
        mock_client.models.list.return_value.data = [model]
        # Act
        models = provider.get_available_models()

        # Assert
        assert models[0].display_label == "ollama_local / llama3:8b"

    def test_get_available_models_parses_model_family(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        model = mocker.Mock()
        model.id = "llama3:8b-instruct-q4_K_M"
        mock_client.models.list.return_value.data = [model]
        # Act
        models = provider.get_available_models()

        # Assert — ModelNameParser extracts "llama3" family
        assert models[0].model_family == "llama3"

    def test_get_available_models_parses_model_size(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        model = mocker.Mock()
        model.id = "llama3:8b-instruct-q4_K_M"
        mock_client.models.list.return_value.data = [model]
        # Act
        models = provider.get_available_models()

        # Assert
        assert models[0].model_size_b == 8.0

    def test_get_available_models_parses_quantization_label(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        model = mocker.Mock()
        model.id = "llama3:8b-instruct-q4_K_M"
        mock_client.models.list.return_value.data = [model]
        # Act
        models = provider.get_available_models()

        # Assert
        assert models[0].quantization_label == "q4_K_M"

    def test_get_available_models_opaque_name_yields_none_parsed_fields(self, mocker: MockerFixture) -> None:
        # Arrange — model id has no ':' so parser returns all-None ParsedModelName
        provider, mock_client = _make_provider(mocker)
        model = mocker.Mock()
        model.id = "gpt-4o"
        mock_client.models.list.return_value.data = [model]
        # Act
        models = provider.get_available_models()

        # Assert
        assert models[0].model_family is None
        assert models[0].model_size_b is None
        assert models[0].quantization_label is None

    def test_get_available_models_empty_data_returns_empty_list(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.list.return_value.data = []
        # Act
        models = provider.get_available_models()

        # Assert
        assert models == []

    def test_get_available_models_returns_model_descriptor_instances(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        model = mocker.Mock()
        model.id = "llama3:8b"
        mock_client.models.list.return_value.data = [model]
        # Act
        models = provider.get_available_models()

        # Assert
        assert all(isinstance(m, ModelDescriptor) for m in models)

    def test_get_available_models_on_api_connection_error_returns_empty_list(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.list.side_effect = openai.APIConnectionError(request=mocker.Mock())

        # Act
        models = provider.get_available_models()

        # Assert
        assert models == []

    def test_get_available_models_on_openai_error_returns_empty_list(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.list.side_effect = openai.OpenAIError("server error")
        # Act
        models = provider.get_available_models()

        # Assert
        assert models == []


class TestOpenAICompatibleProviderInferenceSync:
    """Tests for inference_sync."""

    def test_inference_sync_success_populates_llm_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, content="The answer is 42.")
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "What is 6 * 7?"}],
        )

        # Assert
        assert result.llm_response == "The answer is 42."

    def test_inference_sync_success_sets_total_time_ms_positive(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker)
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.total_time_ms >= 0

    def test_inference_sync_success_populates_completion_tokens(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, completion_tokens=42)
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.completion_tokens == 42

    def test_inference_sync_success_populates_prompt_tokens(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, prompt_tokens=15)
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.prompt_tokens == 15

    def test_inference_sync_success_sets_ttft_ms_none(self, mocker: MockerFixture) -> None:
        # Arrange — sync inference does not capture TTFT
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker)
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.ttft_ms is None

    def test_inference_sync_success_sets_has_error_false(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker)
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.has_error is False

    def test_inference_sync_null_usage_sets_none_prompt_tokens(self, mocker: MockerFixture) -> None:
        # Arrange — server returns no usage object
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_choice = mocker.Mock()
        mock_choice.message.content = "ok"
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.prompt_tokens is None
        assert result.completion_tokens == 0

    def test_inference_sync_empty_choices_returns_empty_llm_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_response.choices = []
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 0
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.llm_response == ""
        assert result.has_error is False

    def test_inference_sync_null_message_content_returns_empty_string(self, mocker: MockerFixture) -> None:
        # Arrange — content field is None (e.g. tool-call response)
        provider, mock_client = _make_provider(mocker)
        mock_response = mocker.Mock()
        mock_choice = mocker.Mock()
        mock_choice.message.content = None
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 0
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.llm_response == ""

    def test_inference_sync_on_api_connection_error_returns_has_error_true(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.chat.completions.create.side_effect = openai.APIConnectionError(request=mocker.Mock())

        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.has_error is True
        assert result.error_message is not None

    def test_inference_sync_on_openai_error_returns_has_error_true(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("server error")

        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.has_error is True

    def test_inference_sync_on_openai_error_sets_error_message(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("server unavailable")

        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert
        assert result.error_message == "server unavailable"

    def test_inference_sync_on_error_returns_inference_response_instance(self, mocker: MockerFixture) -> None:
        # Arrange — verify no-throw contract: error is captured in fields, not raised
        provider, mock_client = _make_provider(mocker)
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("boom")

        # Act
        result = provider.inference_sync(
            model="llama3:8b",
            messages=[{"role": "user", "content": "hi"}],
        )

        # Assert — returned an InferenceResponse, not raised
        assert isinstance(result, InferenceResponse)


class TestOpenAICompatibleProviderInferenceStream:
    """Tests for inference_stream."""

    def test_inference_stream_yields_stream_chunk_instances(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        chunks_data = [
            _make_stream_chunk(mocker, delta_content="Hello"),
            _make_stream_chunk(mocker, delta_content=" world"),
            _make_stream_chunk(mocker, delta_content=None, prompt_tokens=10, completion_tokens=5),
        ]
        mock_client.chat.completions.create.return_value = iter(chunks_data)
        # Act
        chunks, _ = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert all(isinstance(c, StreamChunk) for c in chunks)

    def test_inference_stream_yields_correct_delta_contents(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        chunks_data = [
            _make_stream_chunk(mocker, delta_content="Hello"),
            _make_stream_chunk(mocker, delta_content=" world"),
            _make_stream_chunk(mocker, delta_content=None, prompt_tokens=10, completion_tokens=5),
        ]
        mock_client.chat.completions.create.return_value = iter(chunks_data)
        # Act
        chunks, _ = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert chunks[0].delta_content == "Hello"
        assert chunks[1].delta_content == " world"

    def test_inference_stream_assembles_full_response_content(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        chunks_data = [
            _make_stream_chunk(mocker, delta_content="Hello"),
            _make_stream_chunk(mocker, delta_content=" world"),
            _make_stream_chunk(mocker, delta_content=None, prompt_tokens=10, completion_tokens=5),
        ]
        mock_client.chat.completions.create.return_value = iter(chunks_data)
        # Act
        _, final_response = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert final_response.llm_response == "Hello world"

    def test_inference_stream_populates_token_counts_from_usage_chunk(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        chunks_data = [
            _make_stream_chunk(mocker, delta_content="Hello"),
            _make_stream_chunk(mocker, delta_content=None, prompt_tokens=12, completion_tokens=7),
        ]
        mock_client.chat.completions.create.return_value = iter(chunks_data)
        # Act
        _, final_response = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert final_response.completion_tokens == 7
        assert final_response.prompt_tokens == 12

    def test_inference_stream_sets_ttft_ms_on_first_content_chunk(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        chunks_data = [
            _make_stream_chunk(mocker, delta_content="first"),
            _make_stream_chunk(mocker, delta_content="second"),
            _make_stream_chunk(mocker, delta_content=None, prompt_tokens=5, completion_tokens=2),
        ]
        mock_client.chat.completions.create.return_value = iter(chunks_data)
        # Act
        _, final_response = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert final_response.ttft_ms is not None
        assert final_response.ttft_ms >= 0

    def test_inference_stream_no_content_chunks_sets_ttft_ms_none(self, mocker: MockerFixture) -> None:
        # Arrange — all chunks have empty delta; ttft should remain None
        provider, mock_client = _make_provider(mocker)
        chunks_data = [
            _make_stream_chunk(mocker, delta_content=""),
            _make_stream_chunk(mocker, delta_content=None, prompt_tokens=5, completion_tokens=0),
        ]
        mock_client.chat.completions.create.return_value = iter(chunks_data)
        # Act
        chunks, final_response = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert chunks == []
        assert final_response.ttft_ms is None

    def test_inference_stream_usage_only_chunk_not_yielded_as_stream_chunk(self, mocker: MockerFixture) -> None:
        # Arrange — final chunk has no choices, only usage; should not produce a StreamChunk
        provider, mock_client = _make_provider(mocker)
        chunks_data = [
            _make_stream_chunk(mocker, delta_content="text"),
            _make_stream_chunk(mocker, delta_content=None, prompt_tokens=5, completion_tokens=1),
        ]
        mock_client.chat.completions.create.return_value = iter(chunks_data)
        # Act
        chunks, _ = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert — only the content chunk is yielded
        assert len(chunks) == 1

    def test_inference_stream_sets_has_error_false_on_success(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        chunks_data = [
            _make_stream_chunk(mocker, delta_content="hi"),
            _make_stream_chunk(mocker, delta_content=None, prompt_tokens=3, completion_tokens=1),
        ]
        mock_client.chat.completions.create.return_value = iter(chunks_data)
        # Act
        _, final_response = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert final_response.has_error is False

    def test_inference_stream_on_openai_error_returns_error_response(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("stream connection dropped")

        # Act
        chunks, final_response = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert
        assert chunks == []
        assert final_response.has_error is True
        assert final_response.error_message == "stream connection dropped"

    def test_inference_stream_returns_inference_response_instance(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("err")
        # Act
        _, final_response = _drain_stream(
            provider,
            model="llama3:8b",
            messages=[{"role": "user", "content": "test"}],
        )

        # Assert — no-throw contract: result is InferenceResponse, not an exception
        assert isinstance(final_response, InferenceResponse)


class TestOpenAICompatibleProviderCapabilities:
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


class TestOpenAICompatibleProviderWarmUp:
    """Tests for warm_up."""

    def test_warm_up_success_returns_true(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, content="hi")
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        result = provider.warm_up("llama3:8b")

        # Assert
        assert result is True

    def test_warm_up_success_on_first_attempt_makes_one_call(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, content="hi")
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        provider.warm_up("llama3:8b")

        # Assert — succeeded on first attempt, no retries needed
        assert mock_client.chat.completions.create.call_count == 1

    def test_warm_up_all_retries_exhausted_returns_false(self, mocker: MockerFixture) -> None:
        # Arrange — all three attempts fail
        provider, mock_client = _make_provider(mocker)
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("connection refused")
        mocker.patch("ollama_llm_bench.backend.services.providers.openai_compatible_provider.time.sleep")

        # Act
        result = provider.warm_up("llama3:8b")

        # Assert
        assert result is False

    def test_warm_up_retries_three_times_before_failing(self, mocker: MockerFixture) -> None:
        # Arrange — use a 503 error so the classifier marks it as retryable
        provider, mock_client = _make_provider(mocker)
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("Error code: 503 - Server Error")
        mocker.patch("ollama_llm_bench.backend.services.providers.openai_compatible_provider.time.sleep")

        # Act
        provider.warm_up("llama3:8b")

        # Assert — exactly 3 attempts (_WARM_UP_RETRIES = 3)
        assert mock_client.chat.completions.create.call_count == 3

    def test_warm_up_sleeps_between_failed_attempts(self, mocker: MockerFixture) -> None:
        # Arrange — use a 503 error so the classifier marks it as retryable
        provider, mock_client = _make_provider(mocker)
        mock_client.chat.completions.create.side_effect = openai.OpenAIError("Error code: 503 - Server Error")
        mock_sleep = mocker.patch("ollama_llm_bench.backend.services.providers.openai_compatible_provider.time.sleep")

        # Act
        provider.warm_up("llama3:8b")

        # Assert — sleep called between retries (3 attempts → 2 sleeps)
        assert mock_sleep.call_count == 2

    def test_warm_up_succeeds_on_second_attempt_returns_true(self, mocker: MockerFixture) -> None:
        # Arrange — first attempt raises a retryable 503, second succeeds
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, content="hi")
        mock_client.chat.completions.create.side_effect = [
            openai.OpenAIError("Error code: 503 - Server Error"),
            mock_response,
        ]
        mocker.patch("ollama_llm_bench.backend.services.providers.openai_compatible_provider.time.sleep")

        # Act
        result = provider.warm_up("llama3:8b")

        # Assert
        assert result is True

    def test_warm_up_sends_minimal_max_tokens(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, content="ok")
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        provider.warm_up("llama3:8b")

        # Assert — max_tokens=1 used to minimise overhead
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 1

    def test_warm_up_sends_correct_model_name(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_response = _make_sync_response(mocker, content="ok")
        mock_client.chat.completions.create.return_value = mock_response
        # Act
        provider.warm_up("mistral:7b")

        # Assert
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "mistral:7b"


class TestOpenAICompatibleProviderProbeHealth:
    """Tests for probe_health."""

    def test_probe_health_reachable_returns_model_count(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        model_a = mocker.Mock()
        model_b = mocker.Mock()
        mock_client.models.list.return_value.data = [model_a, model_b]

        # Act
        result = provider.probe_health()

        # Assert
        assert isinstance(result, HealthProbeResult)
        assert result.reachable is True
        assert result.model_count_observed == 2

    def test_probe_health_connection_refused_returns_not_reachable(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.list.side_effect = openai.APIConnectionError(request=mocker.Mock())

        # Act
        result = provider.probe_health()

        # Assert
        assert result.reachable is False
        assert result.error_message is not None

    def test_probe_health_auth_error_returns_not_reachable(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.list.side_effect = openai.AuthenticationError(
            message="Unauthorized",
            response=mocker.Mock(),
            body=None,
        )

        # Act
        result = provider.probe_health()

        # Assert
        assert result.reachable is False
        assert result.error_message == "Authentication failed — check API key."

    def test_probe_health_other_openai_error_returns_not_reachable(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.models.list.side_effect = openai.RateLimitError(
            message="Rate limited",
            response=mocker.Mock(),
            body=None,
        )

        # Act
        result = provider.probe_health()

        # Assert
        assert result.reachable is False
        assert result.error_message is not None
