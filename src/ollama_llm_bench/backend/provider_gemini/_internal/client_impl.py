"""The concrete ``GEMINI`` ``LLMClient`` (§6.1-§6.10).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md``.
"""

import contextlib

from google.genai import types as genai_types
import httpx

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatRole,
    InferenceActivity,
    InferenceActivityContext,
    InferenceTestOutcome,
    InferenceTestResult,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ReasoningEffort,
    ResponseFormat,
)
from ollama_llm_bench.backend.errors import ErrorContext, ProviderBadRequestError, redact
from ollama_llm_bench.backend.provider_gemini._internal.chat_stream_impl import (
    ChatStreamCallInfo,
    GeminiChatStream,
)
from ollama_llm_bench.backend.provider_gemini._internal.collaborators import (
    GeminiClientCollaborators,
)
from ollama_llm_bench.backend.provider_gemini._internal.sdk_factory import build_sdk_client
from ollama_llm_bench.backend.provider_gemini._internal.translate_exception import (
    classify_test_inference_outcome,
    translate_chat_exception,
)
from ollama_llm_bench.backend.provider_gemini.models import GeminiClientSettings
from ollama_llm_bench.backend.provider_registry import ChatStream

__all__: list[str] = ["GeminiClient"]

_MODEL_ID_TRUNCATE_LEN = 64
_CANNED_PROMPT = "Reply with the single word: ok"
_RESPONSE_EXCERPT_LEN = 200
_GATE_BUSY_MESSAGE = "An inference activity is already in flight."


class GeminiClient:
    """The ``GEMINI`` ``LLMClient``, wrapping the ``google-genai`` SDK.

    Holds no per-call mutable state: every ``chat``/``chat_stream``/``embed``/
    ``list_models``/``probe_health``/``test_inference`` call builds its own
    accumulator, timing, and deadline (§9). Unlike ``AnthropicClient``,
    ``embed`` and ``list_models`` are implemented for real — Gemini exposes
    both an embeddings endpoint and a ``models.list()`` discovery call
    (§6.9).
    """

    def __init__(
        self,
        *,
        config: ProviderConfig,
        resolved_api_key: str,
        collaborators: GeminiClientCollaborators,
        settings: GeminiClientSettings,
    ) -> None:
        """Construct the client for one provider configuration.

        Never issues a network call.

        Args:
            config: The provider catalog entry this client serves.
            resolved_api_key: The already-resolved secret value.
            collaborators: The injected ``Clock``/``EventBus``/
                ``InferenceActivityStore`` this client depends on.
            settings: The timeout/bound configuration bundle.
        """
        self._config = config
        self._clock = collaborators.clock
        self._event_bus = collaborators.event_bus
        self._inference_activity_store = collaborators.inference_activity_store
        self._settings = settings
        self._sdk_client = build_sdk_client(
            config, resolved_api_key, connect_timeout_ms=settings.connect_timeout_ms
        )

    def _error_context(self, *, model: str = "") -> ErrorContext:
        return ErrorContext(
            provider_id=self._config.provider_id,
            model_id_truncated=model[:_MODEL_ID_TRUNCATE_LEN] or None,
        )

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        """Consume this client's own ``chat_stream`` to completion (DD-51)."""
        stream = self.chat_stream(request, token=token)
        for _ in stream:
            pass
        return stream.trailing_response()

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        """Execute a chat call, returning a synchronous stream of chunks (DD-51)."""
        t0 = self._clock.monotonic_ms()
        context = self._error_context(model=request.model)
        system_instruction, contents = _split_system_and_messages(request.messages)
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=request.max_output_tokens,
            temperature=request.temperature,
            http_options=genai_types.HttpOptions(timeout=request.timeout_ms),
        )
        try:
            raw_stream = self._sdk_client.models.generate_content_stream(
                model=request.model, contents=contents, config=config
            )
        except Exception as exc:  # boundary translation catch-all; re-raised as a taxonomy leaf
            raise translate_chat_exception(exc, context=context) from exc
        call = ChatStreamCallInfo(
            raw_stream=raw_stream,
            t0=t0,
            deadline_ms=t0 + request.timeout_ms,
            provider_id=self._config.provider_id,
            model=request.model,
        )
        stream = GeminiChatStream(call=call, clock=self._clock, token=token)
        token.add_hard_cancel_hook(raw_stream.close)  # type: ignore[attr-defined]  # generator protocol, not SDK-declared
        return stream

    def embed(self, text: str) -> tuple[float, ...]:
        """Return the embedding vector for ``text`` (§6.7)."""
        model = self._settings.embedding_model
        if model is None:
            raise ProviderBadRequestError(
                message="this client has no configured embedding model",
                context=self._error_context(),
            )
        try:
            response = self._sdk_client.models.embed_content(
                model=model,
                contents=text,
                config=genai_types.EmbedContentConfig(
                    http_options=genai_types.HttpOptions(
                        timeout=self._settings.embedding_timeout_ms
                    )
                ),
            )
        except Exception as exc:  # boundary translation catch-all; re-raised as a taxonomy leaf
            raise translate_chat_exception(exc, context=self._error_context(model=model)) from exc
        if not response.embeddings or response.embeddings[0].values is None:
            raise ProviderBadRequestError(
                message="embeddings response carried no vector",
                context=self._error_context(model=model),
            )
        return tuple(response.embeddings[0].values)

    def list_models(self) -> tuple[ModelName, ...]:
        """Return the provider's advertised model catalog (§6.8.1, §6.9.1)."""
        try:
            models = self._sdk_client.models.list(
                config=genai_types.ListModelsConfig(
                    http_options=genai_types.HttpOptions(timeout=self._settings.probe_timeout_ms)
                )
            )
        except Exception as exc:  # boundary translation catch-all; re-raised as a taxonomy leaf
            raise translate_chat_exception(exc, context=self._error_context()) from exc
        return tuple(model.name for model in models if model.name)

    def probe_health(self) -> ProviderHealth:
        """Check reachability then, if supported, discover models (§6.8.1, §6.9.1).

        Falls back to ``discovery_supported=False``, ``model_count=None``
        when the installed SDK build's ``client.models`` object lacks
        ``list`` at all (``AttributeError``) — the SDK-absent branch of
        §6.9.1's discovery matrix. This never happens against the pinned
        SDK version (it always exposes ``models.list()``); the branch exists
        for forward SDK-build compatibility per the spec's own framing.
        """
        t0 = self._clock.monotonic_ms()
        if not self._probe_reachable():
            return ProviderHealth(
                provider_id=self._config.provider_id,
                reachable=False,
                discovery_supported=True,
                model_count=None,
                last_probe_ms=self._clock.monotonic_ms() - t0,
                last_error="endpoint unreachable",
                probed_at=self._clock.monotonic_ms(),
            )
        if not hasattr(self._sdk_client.models, "list"):
            return ProviderHealth(
                provider_id=self._config.provider_id,
                reachable=True,
                discovery_supported=False,
                model_count=None,
                last_probe_ms=self._clock.monotonic_ms() - t0,
                last_error=None,
                probed_at=self._clock.monotonic_ms(),
            )
        try:
            model_count = len(self.list_models())
            last_error = None
        except Exception as exc:  # noqa: BLE001  # probe_health never raises (§6.8.1)
            model_count = None
            last_error = redact(str(exc))
        return ProviderHealth(
            provider_id=self._config.provider_id,
            reachable=True,
            discovery_supported=True,
            model_count=model_count,
            last_probe_ms=self._clock.monotonic_ms() - t0,
            last_error=last_error,
            probed_at=self._clock.monotonic_ms(),
        )

    def _probe_reachable(self) -> bool:
        """Confirm the configured endpoint is reachable (DNS + TCP connect).

        Never issues a chat or models-list call — a bare HTTP request
        against the base URL is enough to confirm the endpoint answers at
        all. A 4xx/5xx response still proves reachability; only a
        connection-level failure means unreachable.
        """
        base_url = self._config.base_url or "https://generativelanguage.googleapis.com"
        timeout = httpx.Timeout(self._settings.probe_timeout_ms / 1000)
        try:
            with httpx.Client(timeout=timeout) as http_client:
                http_client.get(base_url)
        except httpx.HTTPError:
            return False
        return True

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        """Run one canned-prompt chat call against ``model_name`` (§6.8.2)."""
        t0 = self._clock.monotonic_ms()
        context = InferenceActivityContext(
            activity=InferenceActivity.PROVIDER_TEST,
            started_at=t0,
            provider_id=self._config.provider_id,
            model_name=model_name,
        )
        lease = self._inference_activity_store.try_acquire(InferenceActivity.PROVIDER_TEST, context)
        if lease is None:
            return InferenceTestResult(
                outcome=InferenceTestOutcome.GATE_BUSY,
                provider_id=self._config.provider_id,
                model_name=model_name,
                latency_ms=None,
                response_excerpt=None,
                last_error=_GATE_BUSY_MESSAGE,
                tested_at=self._clock.monotonic_ms(),
            )
        try:
            return self._run_inference_test(model_name, t0=t0)
        finally:
            self._inference_activity_store.release(lease)

    def _run_inference_test(self, model_name: ModelName, *, t0: int) -> InferenceTestResult:
        request = ChatRequest(
            model=model_name,
            messages=(ChatMessage(role=ChatRole.USER, content=_CANNED_PROMPT),),
            timeout_ms=self._settings.inference_test_timeout_ms,
            reasoning_effort=ReasoningEffort.DEFAULT,
            response_format=ResponseFormat.TEXT,
            echo_tokens_to_log=False,
        )
        token = CancellationToken(clock=self._clock)
        try:
            response = self.chat(request, token=token)
        except Exception as exc:  # noqa: BLE001  # test_inference never raises (§6.8.2)
            return InferenceTestResult(
                outcome=classify_test_inference_outcome(exc),
                provider_id=self._config.provider_id,
                model_name=model_name,
                latency_ms=self._clock.monotonic_ms() - t0,
                response_excerpt=None,
                last_error=redact(str(exc)),
                tested_at=self._clock.monotonic_ms(),
            )
        return self._classify_response(response, model_name=model_name, t0=t0)

    def _classify_response(
        self, response: ChatResponse, *, model_name: ModelName, t0: int
    ) -> InferenceTestResult:
        latency_ms = self._clock.monotonic_ms() - t0
        if response.text and response.error is None:
            return InferenceTestResult(
                outcome=InferenceTestOutcome.SUCCESS,
                provider_id=self._config.provider_id,
                model_name=model_name,
                latency_ms=latency_ms,
                response_excerpt=response.text[:_RESPONSE_EXCERPT_LEN],
                last_error=None,
                tested_at=self._clock.monotonic_ms(),
            )
        return InferenceTestResult(
            outcome=InferenceTestOutcome.PROVIDER_ERROR,
            provider_id=self._config.provider_id,
            model_name=model_name,
            latency_ms=latency_ms,
            response_excerpt=None,
            last_error=response.error or "empty response",
            tested_at=self._clock.monotonic_ms(),
        )

    def supports_streaming(self) -> bool:
        """Whether the transport supports token streaming."""
        return True

    def supports_reasoning_effort(self) -> bool:
        """Whether the provider accepts a reasoning-effort parameter.

        Per-model capability discovery is layered on by a later story; this
        client reports the conservative default.
        """
        return False

    def supports_thinking(self) -> bool:
        """Whether the model emits a reasoning/thinking block.

        Per-model capability discovery is layered on by a later story; this
        client reports the conservative default. A single response actually
        containing a reasoning part still surfaces it in
        ``ChatResponse.text`` (§6.9) regardless of this capability flag.
        """
        return False

    def close(self) -> None:
        """Release this client's underlying transport resources (best-effort)."""
        with contextlib.suppress(Exception):
            self._sdk_client.close()


def _split_system_and_messages(
    messages: tuple[ChatMessage, ...],
) -> tuple[str | None, list[genai_types.Content]]:
    """Split domain ``ChatMessage``s into Gemini's ``system_instruction`` + ``contents`` shape.

    ``ChatRequest.messages`` is an optional leading ``SYSTEM`` message, then
    alternating ``USER``/``ASSISTANT`` (§4). Gemini's ``GenerateContentConfig``
    takes the system prompt as a separate ``system_instruction`` field, not a
    role-tagged message — mirrors ``AnthropicClient``'s ``system=`` split.
    Gemini's ``Content.role`` must be ``"user"`` or ``"model"`` (never
    ``"assistant"``).

    Args:
        messages: The well-ordered domain message sequence.

    Returns:
        A ``(system_instruction, contents)`` pair; ``system_instruction`` is
        ``None`` when ``messages`` carries no leading ``SYSTEM`` message.
    """
    if messages and messages[0].role is ChatRole.SYSTEM:
        system_instruction: str | None = messages[0].content
        rest = messages[1:]
    else:
        system_instruction = None
        rest = messages
    contents = [
        genai_types.Content(
            role="model" if message.role is ChatRole.ASSISTANT else "user",
            parts=[genai_types.Part(text=message.content)],
        )
        for message in rest
    ]
    return system_instruction, contents
