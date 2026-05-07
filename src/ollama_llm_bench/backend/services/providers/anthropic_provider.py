"""Anthropic Claude provider implementing LLMProviderApi via the anthropic SDK."""

import logging
import time
from collections.abc import Generator
from typing import cast

import anthropic
from anthropic.types import MessageParam, ThinkingConfigParam

from ollama_llm_bench.backend.core.models import InferenceResponse, ModelDescriptor, StreamChunk

_DEFAULT_MAX_TOKENS: int = 4096
_THINKING_BUDGET_MAP: dict[str, int] = {
    "low": 1_024,
    "medium": 4_096,
    "high": 16_384,
}

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """LLM provider for Anthropic Claude models using the anthropic SDK.

    Implements the LLMProviderApi Protocol structurally. Model list is static
    (sourced from providers.yaml default_models) because the Anthropic API
    has no public /models listing endpoint.
    """

    def __init__(
        self,
        *,
        provider_id: str,
        api_key: str,
        default_models: tuple[str, ...],
        base_url: str | None = None,
    ) -> None:
        """Initialize the provider with identity and a pre-constructed Anthropic client.

        Args:
            provider_id: Unique identifier for this provider instance.
            api_key: Anthropic API key used to authenticate requests.
            default_models: Static tuple of model name strings from providers.yaml.
            base_url: Optional endpoint override for proxies or API gateways.
                Defaults to the Anthropic SDK default (api.anthropic.com).
        """
        self._provider_id = provider_id
        self._default_models = default_models
        if base_url:
            self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        else:
            self._client = anthropic.Anthropic(api_key=api_key)

    @property
    def provider_id(self) -> str:
        """Return the provider's unique identifier."""
        return self._provider_id

    @property
    def provider_type(self) -> str:
        """Return the provider type discriminator string."""
        return "anthropic"

    def get_available_models(self) -> list[ModelDescriptor]:
        """Return static model list from config; no API call is made.

        Returns:
            List of ModelDescriptor instances, one per entry in default_models.
            Empty list when default_models is empty.
        """
        return [
            ModelDescriptor(
                provider_id=self._provider_id,
                provider_type="anthropic",
                model_name=model_name,
                display_label=f"{self._provider_id} / {model_name}",
            )
            for model_name in self._default_models
        ]

    def inference_sync(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        reasoning_effort: str = "medium",
    ) -> InferenceResponse:
        """Run synchronous inference against the Anthropic Messages API.

        Args:
            model: Anthropic model identifier (e.g. ``"claude-opus-4-6"``).
            messages: Conversation messages in OpenAI-style role/content format.
            temperature: Sampling temperature; defaults to 0.0 for deterministic output.
            max_tokens: Maximum tokens to generate; defaults to _DEFAULT_MAX_TOKENS.
            reasoning_effort: Maps to extended thinking budget_tokens ("low"/"medium"/"high").

        Returns:
            Populated InferenceResponse on success, or an error response with
            has_error=True and error_message set when an APIError is raised.
        """
        system_text, non_system = self._extract_system_message(messages)
        thinking = self._build_thinking_param(reasoning_effort)
        start_ns = time.monotonic_ns()
        try:
            if thinking is not None:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
                    system=system_text,
                    messages=cast(list[MessageParam], non_system),
                    temperature=temperature,
                    thinking=thinking,
                )
            else:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
                    system=system_text,
                    messages=cast(list[MessageParam], non_system),
                    temperature=temperature,
                )
        except anthropic.APIError as exc:
            logger.exception("anthropic_inference_sync_error")
            return InferenceResponse(has_error=True, error_message=str(exc))
        end_ns = time.monotonic_ns()
        text_blocks = [block.text for block in response.content if block.type == "text"]
        text = text_blocks[0] if text_blocks else ""
        return InferenceResponse(
            llm_response=text,
            total_time_ms=(end_ns - start_ns) // 1_000_000,
            completion_tokens=response.usage.output_tokens,
            prompt_tokens=response.usage.input_tokens,
        )

    def inference_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        reasoning_effort: str = "medium",
    ) -> Generator[StreamChunk, None, InferenceResponse]:
        """Run streaming inference; yields StreamChunk deltas, returns InferenceResponse.

        Args:
            model: Anthropic model identifier.
            messages: Conversation messages in OpenAI-style role/content format.
            temperature: Sampling temperature; defaults to 0.0.
            max_tokens: Maximum tokens to generate; defaults to _DEFAULT_MAX_TOKENS.
            reasoning_effort: Maps to extended thinking budget_tokens ("low"/"medium"/"high").

        Yields:
            StreamChunk for each non-empty text delta received from the stream.

        Returns:
            InferenceResponse with full metrics on success, or an error response
            with has_error=True and error_message set when an APIError is raised.
        """
        system_text, non_system = self._extract_system_message(messages)
        thinking = self._build_thinking_param(reasoning_effort)
        start_ns = time.monotonic_ns()
        ttft_ns: int | None = None
        full_content = ""
        try:
            stream_ctx = (
                self._client.messages.stream(
                    model=model,
                    max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
                    system=system_text,
                    messages=cast(list[MessageParam], non_system),
                    temperature=temperature,
                    thinking=thinking,
                )
                if thinking is not None
                else self._client.messages.stream(
                    model=model,
                    max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
                    system=system_text,
                    messages=cast(list[MessageParam], non_system),
                    temperature=temperature,
                )
            )
            with stream_ctx as stream:
                for text_delta in stream.text_stream:
                    if text_delta:
                        if ttft_ns is None:
                            ttft_ns = time.monotonic_ns()
                        full_content += text_delta
                        yield StreamChunk(delta_content=text_delta)
                final_msg = stream.get_final_message()
            end_ns = time.monotonic_ns()
            ttft_ms = (ttft_ns - start_ns) // 1_000_000 if ttft_ns is not None else None
            return InferenceResponse(
                llm_response=full_content,
                total_time_ms=(end_ns - start_ns) // 1_000_000,
                completion_tokens=final_msg.usage.output_tokens,
                prompt_tokens=final_msg.usage.input_tokens,
                ttft_ms=ttft_ms,
            )
        except anthropic.APIError as exc:
            logger.exception("anthropic_stream_error")
            return InferenceResponse(has_error=True, error_message=str(exc))

    def supports_structured_output(self) -> bool:
        """Return False; Anthropic structured output requires beta tools, not yet supported."""
        return False

    def supports_streaming(self) -> bool:
        """Return True; Anthropic Messages API supports server-sent event streaming."""
        return True

    def warm_up(self, model: str) -> bool:
        """Send a minimal request to ensure the model is loaded; no retry.

        Args:
            model: Anthropic model identifier to warm up.

        Returns:
            True when the warm-up request succeeds, False on any error.
        """
        response = self.inference_sync(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        return not response.has_error

    @staticmethod
    def _build_thinking_param(reasoning_effort: str) -> ThinkingConfigParam | None:
        """Return the Anthropic extended-thinking config, or None for default effort.

        Args:
            reasoning_effort: "low", "medium", "high", or "default".

        Returns:
            ThinkingConfigParam dict for the ``thinking`` kwarg, or None when effort is "default".
        """
        if reasoning_effort == "default":
            return None
        budget = _THINKING_BUDGET_MAP.get(reasoning_effort, _THINKING_BUDGET_MAP["medium"])
        return {"type": "enabled", "budget_tokens": budget}

    @staticmethod
    def _extract_system_message(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        """Split system prompt from conversation messages.

        Args:
            messages: Full message list potentially containing a system-role entry.

        Returns:
            Tuple of (system_text, non_system_messages). system_text is an empty
            string when no system message is present.
        """
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]
        return " ".join(system_parts), non_system
