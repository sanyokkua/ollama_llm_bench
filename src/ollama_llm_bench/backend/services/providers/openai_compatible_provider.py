"""OpenAI-compatible LLM provider supporting Ollama, LM Studio, llama.cpp, OpenAI, and Azure."""

import logging
import time
from collections.abc import Generator
from typing import cast

import httpx
import openai
from openai.types.chat import ChatCompletionMessageParam

from ollama_llm_bench.backend.core.interfaces import ModelCapabilityServiceApi
from ollama_llm_bench.backend.core.models import HealthProbeResult, InferenceResponse, ModelDescriptor, StreamChunk
from ollama_llm_bench.backend.services.llm_error_classifier import LlmErrorClassifier
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser

_WARM_UP_RETRIES: int = 3
_WARM_UP_SLEEP_S: int = 10
_HTTP_CONNECT_TIMEOUT_S: float = 10.0
_HTTP_READ_TIMEOUT_S: float = 120.0  # safety net; per-task timer fires first

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    """LLM provider for any OpenAI-compatible endpoint.

    Wraps the openai SDK to support Ollama, LM Studio, llama.cpp, OpenAI,
    and Azure OpenAI Service. Provider identity is supplied at construction
    time; model name parsing is delegated to an injected ModelNameParser.

    Both synchronous and streaming inference are supported. The streaming
    implementation requests usage metadata via ``stream_options`` so that
    token counts are available in the final usage chunk.
    """

    def __init__(
        self,
        *,
        provider_id: str,
        provider_type: str,
        base_url: str,
        api_key: str,
        name_parser: ModelNameParser,
        capability_service: ModelCapabilityServiceApi | None = None,
        classifier: LlmErrorClassifier | None = None,
    ) -> None:
        """Initialize the provider and construct the underlying openai client.

        Args:
            provider_id: Unique identifier for this provider instance.
            provider_type: Discriminator string (e.g. ``"openai_compatible"``).
            base_url: Base URL of the OpenAI-compatible endpoint (e.g. ``"http://localhost:11434/v1"``).
            api_key: API key; use any non-empty string for local servers that ignore it.
            name_parser: Parser used to extract family, size, and quantization from model names.
            capability_service: Optional service for reading/writing per-model capability flags.
                When provided, warm_up() skips ``reasoning_effort`` for models known not to
                support it and persists new discoveries.
            classifier: Optional error classifier; a default instance is created when omitted.
        """
        self._provider_id = provider_id
        self._provider_type = provider_type
        self._name_parser = name_parser
        self._capability_service = capability_service
        self._classifier = classifier if classifier is not None else LlmErrorClassifier()
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(
                connect=_HTTP_CONNECT_TIMEOUT_S,
                read=_HTTP_READ_TIMEOUT_S,
                write=_HTTP_CONNECT_TIMEOUT_S,
                pool=5.0,
            ),
        )

    @property
    def provider_id(self) -> str:
        """Return the provider's unique identifier."""
        return self._provider_id

    @property
    def provider_type(self) -> str:
        """Return the provider type discriminator string."""
        return self._provider_type

    def get_available_models(self) -> list[ModelDescriptor]:
        """Retrieve available models from the endpoint and parse their names.

        Returns:
            List of ModelDescriptor instances sorted by model_name; empty list
            when the endpoint is unreachable or returns an error.
        """
        try:
            response = self._client.models.list()
        except openai.APIConnectionError:
            logger.warning("openai_compatible_models_unreachable", extra={"provider_id": self._provider_id})
            return []
        except openai.OpenAIError:
            logger.warning("openai_compatible_models_error", extra={"provider_id": self._provider_id})
            return []

        descriptors: list[ModelDescriptor] = []
        for model in response.data:
            parsed = self._name_parser.parse(model.id)
            descriptors.append(
                ModelDescriptor(
                    provider_id=self._provider_id,
                    provider_type=self._provider_type,
                    model_name=model.id,
                    display_label=f"{self._provider_id} / {model.id}",
                    model_family=parsed.model_family,
                    model_size_b=parsed.model_size_b,
                    quantization_label=parsed.quantization_label,
                )
            )
        return sorted(descriptors, key=lambda d: d.model_name)

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
        """Run synchronous (non-streaming) inference against the endpoint.

        Args:
            model: Model identifier to use for inference.
            messages: Conversation messages in OpenAI role/content format.
            temperature: Sampling temperature; defaults to 0.0 for deterministic output.
            max_tokens: Maximum tokens to generate; None leaves the limit to the server.
            reasoning_effort: Reasoning effort level for o-series models; ignored by others.
            response_format: Optional format hint passed to the API, e.g.
                ``{"type": "json_object"}`` for providers that support structured output.

        Returns:
            Populated InferenceResponse on success, or an error response with
            has_error=True and error_message set when an OpenAIError is raised.
        """
        extra: dict[str, str] = {}
        if reasoning_effort != "default":
            extra["reasoning_effort"] = reasoning_effort
        start_ns = time.monotonic_ns()
        fmt: dict[str, object] = {"response_format": response_format} if response_format is not None else {}
        try:
            response = self._client.chat.completions.create(  # type: ignore[call-overload]
                model=model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra or None,
                **fmt,
            )
        except openai.OpenAIError as exc:
            logger.error("openai_compatible_sync_error", exc_info=exc)
            return InferenceResponse(has_error=True, error_message=str(exc))
        end_ns = time.monotonic_ns()

        content = response.choices[0].message.content or "" if response.choices else ""
        prompt_tokens: int | None = response.usage.prompt_tokens if response.usage else None
        completion_tokens: int = response.usage.completion_tokens if response.usage else 0
        total_time_ms = (end_ns - start_ns) // 1_000_000

        return InferenceResponse(
            llm_response=content,
            total_time_ms=total_time_ms,
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            ttft_ms=None,
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

        With ``stream_options={"include_usage": True}``, the final chunk contains
        usage statistics; content chunks precede it. TTFT is recorded on the
        first chunk that carries a non-empty delta.

        Args:
            model: Model identifier to use for inference.
            messages: Conversation messages in OpenAI role/content format.
            temperature: Sampling temperature; defaults to 0.0.
            max_tokens: Maximum tokens to generate; None leaves the limit to the server.
            reasoning_effort: Reasoning effort level for o-series models; ignored by others.

        Yields:
            StreamChunk for each non-empty delta received from the stream.

        Returns:
            InferenceResponse with full metrics on success, or an error response
            with has_error=True and error_message set when an OpenAIError is raised.
        """
        extra: dict[str, str] = {}
        if reasoning_effort != "default":
            extra["reasoning_effort"] = reasoning_effort
        start_ns = time.monotonic_ns()
        ttft_ns: int | None = None
        full_content = ""
        prompt_tokens: int | None = None
        completion_tokens: int | None = None

        try:
            raw_stream = self._client.chat.completions.create(
                model=model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                stream=True,
                stream_options={"include_usage": True},
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra or None,
            )
            stream = raw_stream
            for chunk in stream:
                if chunk.usage is not None:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens

                if not chunk.choices:
                    continue

                delta_content = chunk.choices[0].delta.content or ""
                if delta_content:
                    if ttft_ns is None:
                        ttft_ns = time.monotonic_ns()
                    full_content += delta_content
                    yield StreamChunk(delta_content=delta_content)

        except openai.OpenAIError as exc:
            logger.error("openai_compatible_stream_error", exc_info=exc)
            return InferenceResponse(has_error=True, error_message=str(exc))

        end_ns = time.monotonic_ns()
        ttft_ms = (ttft_ns - start_ns) // 1_000_000 if ttft_ns is not None else None
        return InferenceResponse(
            llm_response=full_content,
            total_time_ms=(end_ns - start_ns) // 1_000_000,
            completion_tokens=completion_tokens or 0,
            prompt_tokens=prompt_tokens,
            ttft_ms=ttft_ms,
        )

    def supports_structured_output(self) -> bool:
        """Return True; OpenAI-compatible endpoints support JSON structured output."""
        return True

    def supports_streaming(self) -> bool:
        """Return True; OpenAI-compatible endpoints support server-sent event streaming."""
        return True

    def abort(self) -> None:
        """Close the underlying HTTP client to cancel any in-flight request."""
        try:
            self._client.close()
        except Exception:
            logger.debug("openai_compatible_abort_error")

    def warm_up(self, model: str) -> bool:
        """Send minimal requests to ensure the model is loaded and responsive.

        Consults the capability service to skip ``reasoning_effort`` for models
        known not to support extended thinking.  On a 400 "does not support
        thinking" response, persists the discovery and immediately retries
        without the parameter.  Other non-retryable errors abort without
        sleeping; transient errors sleep and retry up to _WARM_UP_RETRIES times.

        Args:
            model: Model identifier to warm up.

        Returns:
            True when any attempt succeeds, False when all retries are exhausted
            or a non-retryable non-capability error is received.
        """
        use_reasoning: bool | None = (
            self._capability_service.supports_thinking(self._provider_id, model)
            if self._capability_service is not None
            else None
        )

        for attempt in range(_WARM_UP_RETRIES):
            effort = "default" if use_reasoning is False else "medium"
            response = self.inference_sync(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
                reasoning_effort=effort,
            )
            if not response.has_error:
                return True

            classification = self._classifier.classify_from_message(response.error_message or "")

            if classification.is_capability_signal and classification.capability_unsupported == "thinking":
                logger.debug(
                    "warm_up_thinking_unsupported",
                    extra={"model": model, "provider_id": self._provider_id},
                )
                if self._capability_service is not None:
                    self._capability_service.remember(
                        self._provider_id,
                        model,
                        "thinking",
                        supported=False,
                        observed_via="warm_up_400",
                        detail=response.error_message,
                    )
                use_reasoning = False
                continue  # immediate retry without sleep

            if not classification.is_retryable:
                logger.debug(
                    "warm_up_non_retryable",
                    extra={"model": model, "reason": classification.classification_reason},
                )
                return False

            logger.warning("warm_up_retry", extra={"attempt": attempt + 1, "model": model})
            if attempt < _WARM_UP_RETRIES - 1:
                time.sleep(_WARM_UP_SLEEP_S)

        return False

    def probe_health(self) -> HealthProbeResult:
        """Call models.list() and return a probe result; re-raises no exception.

        Returns:
            HealthProbeResult with reachable=True and model_count_observed set
            on success, or reachable=False with error_message on any failure.
        """
        try:
            response = self._client.models.list()
            return HealthProbeResult(
                reachable=True,
                model_count_observed=len(list(response.data)),
            )
        except openai.APIConnectionError as exc:
            logger.warning("openai_compatible_probe_unreachable", extra={"provider_id": self._provider_id})
            return HealthProbeResult(reachable=False, error_message=str(exc))
        except openai.AuthenticationError:
            logger.warning("openai_compatible_probe_auth_error", extra={"provider_id": self._provider_id})
            return HealthProbeResult(reachable=False, error_message="Authentication failed — check API key.")
        except openai.OpenAIError as exc:
            logger.warning("openai_compatible_probe_error", extra={"provider_id": self._provider_id})
            return HealthProbeResult(reachable=False, error_message=str(exc))
