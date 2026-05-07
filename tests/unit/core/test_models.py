"""Unit tests for InferenceResponse, ModelDescriptor, and StreamChunk dataclasses."""

from dataclasses import FrozenInstanceError

import pytest

from ollama_llm_bench.backend.core.models import InferenceResponse, ModelDescriptor, StreamChunk


class TestInferenceResponse:
    def test_inference_response_defaults(self) -> None:
        response = InferenceResponse()

        assert response.llm_response == ""
        assert response.total_time_ms == 0
        assert response.completion_tokens == 0
        assert response.prompt_tokens is None
        assert response.ttft_ms is None
        assert response.has_error is False
        assert response.error_message is None

    def test_inference_response_with_all_fields(self) -> None:
        response = InferenceResponse(
            llm_response="Hello world",
            total_time_ms=1234,
            completion_tokens=42,
            prompt_tokens=10,
            ttft_ms=87,
            has_error=False,
            error_message=None,
        )

        assert response.llm_response == "Hello world"
        assert response.total_time_ms == 1234
        assert response.completion_tokens == 42
        assert response.prompt_tokens == 10
        assert response.ttft_ms == 87
        assert response.has_error is False
        assert response.error_message is None

    def test_inference_response_error_state(self) -> None:
        response = InferenceResponse(has_error=True, error_message="Connection refused")

        assert response.has_error is True
        assert response.error_message == "Connection refused"
        assert response.llm_response == ""

    def test_inference_response_is_frozen(self) -> None:
        response = InferenceResponse(total_time_ms=100)

        with pytest.raises(FrozenInstanceError):
            response.total_time_ms = 999  # type: ignore[misc]


class TestModelDescriptor:
    def test_model_descriptor_with_required_fields_only(self) -> None:
        descriptor = ModelDescriptor(
            provider_id="ollama_local",
            provider_type="openai_compatible",
            model_name="llama3.1:8b",
            display_label="ollama_local / llama3.1:8b",
        )

        assert descriptor.provider_id == "ollama_local"
        assert descriptor.provider_type == "openai_compatible"
        assert descriptor.model_name == "llama3.1:8b"
        assert descriptor.display_label == "ollama_local / llama3.1:8b"
        assert descriptor.model_family is None
        assert descriptor.model_size_b is None
        assert descriptor.quantization_label is None

    def test_model_descriptor_with_all_fields(self) -> None:
        descriptor = ModelDescriptor(
            provider_id="ollama_local",
            provider_type="openai_compatible",
            model_name="llama3.1:8b-instruct-q4_K_M",
            display_label="ollama_local / llama3.1:8b-instruct-q4_K_M",
            model_family="llama",
            model_size_b=8.0,
            quantization_label="Q4_K_M",
        )

        assert descriptor.model_family == "llama"
        assert descriptor.model_size_b == 8.0
        assert descriptor.quantization_label == "Q4_K_M"

    def test_model_descriptor_is_frozen(self) -> None:
        descriptor = ModelDescriptor(
            provider_id="p",
            provider_type="openai_compatible",
            model_name="m",
            display_label="p / m",
        )

        with pytest.raises(FrozenInstanceError):
            descriptor.model_name = "other"  # type: ignore[misc]


class TestStreamChunk:
    def test_stream_chunk_with_content_only(self) -> None:
        chunk = StreamChunk(delta_content="Hello")

        assert chunk.delta_content == "Hello"
        assert chunk.is_final is False
        assert chunk.finish_reason is None

    def test_stream_chunk_final_with_reason(self) -> None:
        chunk = StreamChunk(delta_content="", is_final=True, finish_reason="stop")

        assert chunk.delta_content == ""
        assert chunk.is_final is True
        assert chunk.finish_reason == "stop"

    def test_stream_chunk_is_frozen(self) -> None:
        chunk = StreamChunk(delta_content="token")

        with pytest.raises(FrozenInstanceError):
            chunk.delta_content = "other"  # type: ignore[misc]
