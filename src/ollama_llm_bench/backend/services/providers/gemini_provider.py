"""Google Gemini provider implementing LLMProviderApi via the google-genai SDK."""

import logging
import time
from collections.abc import Generator

import google.genai
from google.genai import types as genai_types
from google.genai.types import HttpOptions

from ollama_llm_bench.backend.core.models import HealthProbeResult, InferenceResponse, ModelDescriptor, StreamChunk

_DEFAULT_MAX_TOKENS: int = 8192

_ROLE_MAP: dict[str, str] = {"user": "user", "assistant": "model"}

logger = logging.getLogger(__name__)


class GeminiProvider:
    """LLM provider for Google Gemini models using the google-genai SDK.

    Implements the LLMProviderApi Protocol structurally. Model list is static
    (sourced from providers.yaml default_models). Supports structured output
    via response_mime_type in GenerateContentConfig.
    """

    def __init__(
        self,
        *,
        provider_id: str,
        api_key: str,
        default_models: tuple[str, ...],
        base_url: str | None = None,
    ) -> None:
        """Initialize the Gemini provider with credentials and model list.

        Args:
            provider_id: Unique identifier for this provider instance.
            api_key: Google AI Studio API key.
            default_models: Tuple of model names available via this provider.
            base_url: Optional endpoint override for proxies or API gateways.
                Passed via HttpOptions(base_url=...) to the google-genai SDK.
                Defaults to the SDK default (generativelanguage.googleapis.com).
        """
        self._provider_id = provider_id
        self._default_models = default_models
        if base_url:
            self._client = google.genai.Client(
                api_key=api_key,
                http_options=HttpOptions(base_url=base_url),
            )
        else:
            self._client = google.genai.Client(api_key=api_key)

    @property
    def provider_id(self) -> str:
        """Return the unique provider identifier."""
        return self._provider_id

    @property
    def provider_type(self) -> str:
        """Return the provider type string."""
        return "gemini"

    def get_available_models(self) -> list[ModelDescriptor]:
        """Return static model list from config; no API call is made."""
        return [
            ModelDescriptor(
                provider_id=self._provider_id,
                provider_type="gemini",
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
        response_format: dict[str, str] | None = None,
    ) -> InferenceResponse:
        """Run synchronous inference against the Gemini generate_content API.

        Args:
            model: Model name to use for inference.
            messages: Conversation history in OpenAI-format role/content dicts.
            temperature: Sampling temperature; 0.0 for deterministic output.
            max_tokens: Maximum output tokens; defaults to _DEFAULT_MAX_TOKENS.

        Returns:
            InferenceResponse with generated text and timing metrics, or
            has_error=True with error_message on failure.
        """
        system_text, _ = self._extract_system_message(messages)
        contents = self._build_contents(messages)
        config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
            system_instruction=system_text or None,
        )
        start_ns = time.monotonic_ns()
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.exception("gemini_inference_sync_error")
            return InferenceResponse(has_error=True, error_message=str(e))
        end_ns = time.monotonic_ns()
        text = response.text or ""
        prompt_tokens: int | None = None
        completion_tokens = 0
        if response.usage_metadata:
            prompt_tokens = response.usage_metadata.prompt_token_count
            completion_tokens = response.usage_metadata.candidates_token_count or 0
        return InferenceResponse(
            llm_response=text,
            total_time_ms=(end_ns - start_ns) // 1_000_000,
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
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
            model: Model name to use for inference.
            messages: Conversation history in OpenAI-format role/content dicts.
            temperature: Sampling temperature; 0.0 for deterministic output.
            max_tokens: Maximum output tokens; defaults to _DEFAULT_MAX_TOKENS.

        Yields:
            StreamChunk containing the delta text for each token event.

        Returns:
            InferenceResponse with full accumulated text and timing metrics, or
            has_error=True with error_message on failure.
        """
        system_text, _ = self._extract_system_message(messages)
        contents = self._build_contents(messages)
        config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
            system_instruction=system_text or None,
        )
        start_ns = time.monotonic_ns()
        ttft_ns: int | None = None
        full_content = ""
        prompt_tokens: int | None = None
        completion_tokens = 0
        try:
            for chunk in self._client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    if ttft_ns is None:
                        ttft_ns = time.monotonic_ns()
                    full_content += chunk.text
                    yield StreamChunk(delta_content=chunk.text)
                if chunk.usage_metadata:
                    prompt_tokens = chunk.usage_metadata.prompt_token_count
                    completion_tokens = chunk.usage_metadata.candidates_token_count or 0
            end_ns = time.monotonic_ns()
            ttft_ms = (ttft_ns - start_ns) // 1_000_000 if ttft_ns is not None else None
            return InferenceResponse(
                llm_response=full_content,
                total_time_ms=(end_ns - start_ns) // 1_000_000,
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                ttft_ms=ttft_ms,
            )
        except Exception as e:
            logger.exception("gemini_stream_error")
            return InferenceResponse(has_error=True, error_message=str(e))

    def supports_structured_output(self) -> bool:
        """Return True; Gemini supports JSON-mode via response_mime_type."""
        return True

    def supports_streaming(self) -> bool:
        """Return True; Gemini supports streaming via generate_content_stream."""
        return True

    def warm_up(self, model: str) -> bool:
        """Send a minimal request to ensure the model is loaded; no retry.

        Args:
            model: Model name to warm up.

        Returns:
            True if the warm-up request succeeded, False on any error.
        """
        response = self.inference_sync(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        return not response.has_error

    def probe_health(self) -> HealthProbeResult:
        """Call client.models.list() to verify credentials and reachability.

        Consumes only the first item from the pager to avoid iterating the full
        public Gemini model catalog.

        Returns:
            HealthProbeResult with reachable=True on success, or reachable=False
            with error_message on any failure.
        """
        try:
            first = next(iter(self._client.models.list()), None)
            return HealthProbeResult(
                reachable=True,
                model_count_observed=1 if first is not None else 0,
            )
        except Exception as exc:
            logger.warning("gemini_probe_error", extra={"provider_id": self._provider_id, "error": str(exc)})
            return HealthProbeResult(reachable=False, error_message=str(exc))

    @staticmethod
    def _extract_system_message(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        """Split system prompt from conversation messages.

        Args:
            messages: Full message list including any system role entries.

        Returns:
            Tuple of (joined system text, non-system messages).
        """
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]
        return " ".join(system_parts), non_system

    @staticmethod
    def _build_contents(messages: list[dict[str, str]]) -> list[genai_types.Content]:
        """Convert OpenAI-format messages to Gemini Content objects.

        Maps 'assistant' role to 'model' (Gemini convention) and
        excludes system messages (handled separately via system_instruction).

        Args:
            messages: Full message list; system messages will be filtered out.

        Returns:
            List of genai_types.Content objects ready for the Gemini API.
        """
        return [
            genai_types.Content(
                role=_ROLE_MAP.get(m["role"], m["role"]),
                parts=[genai_types.Part(text=m["content"])],
            )
            for m in messages
            if m["role"] != "system"
        ]
