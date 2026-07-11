"""The concrete ``ANTHROPIC`` ``LLMClient`` (§6.1-§6.10).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md``.
"""

import contextlib

import anthropic
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
from ollama_llm_bench.backend.provider_anthropic._internal.chat_stream_impl import (
    AnthropicChatStream,
    ChatStreamCallInfo,
)
from ollama_llm_bench.backend.provider_anthropic._internal.collaborators import (
    AnthropicClientCollaborators,
)
from ollama_llm_bench.backend.provider_anthropic._internal.sdk_factory import build_sdk_client
from ollama_llm_bench.backend.provider_anthropic._internal.translate_exception import (
    classify_test_inference_outcome,
    translate_chat_exception,
)
from ollama_llm_bench.backend.provider_anthropic.models import AnthropicClientSettings
from ollama_llm_bench.backend.provider_registry import ChatStream

__all__: list[str] = ["AnthropicClient"]

_MODEL_ID_TRUNCATE_LEN = 64
_CANNED_PROMPT = "Reply with the single word: ok"
_RESPONSE_EXCERPT_LEN = 200
_STREAM_READ_TIMEOUT_S = 0.5
_STREAM_WRITE_TIMEOUT_S = 5.0
_STREAM_POOL_TIMEOUT_S = 5.0
_GATE_BUSY_MESSAGE = "An inference activity is already in flight."


class AnthropicClient:
    """The ``ANTHROPIC`` ``LLMClient``, wrapping the ``anthropic`` SDK's Messages API.

    Holds no per-call mutable state: every ``chat``/``chat_stream``/``embed``/
    ``list_models``/``probe_health``/``test_inference`` call builds its own
    accumulator, timing, and deadline (§9). ``discovery_supported`` is always
    ``False`` (§6.9.1) — Anthropic exposes no models-list endpoint — and
    ``embed`` always raises immediately — Anthropic exposes no embeddings
    endpoint at all.
    """

    def __init__(
        self,
        *,
        config: ProviderConfig,
        resolved_api_key: str,
        collaborators: AnthropicClientCollaborators,
        settings: AnthropicClientSettings,
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
        system, sdk_messages = _split_system_and_messages(request.messages)
        stream_timeout = httpx.Timeout(
            connect=self._settings.connect_timeout_ms / 1000,
            read=_STREAM_READ_TIMEOUT_S,
            write=_STREAM_WRITE_TIMEOUT_S,
            pool=_STREAM_POOL_TIMEOUT_S,
        )
        try:
            raw_stream = self._sdk_client.messages.create(
                model=request.model,
                max_tokens=request.max_output_tokens,
                messages=sdk_messages,
                stream=True,
                system=system if system is not None else anthropic.omit,
                temperature=request.temperature
                if request.temperature is not None
                else anthropic.omit,
                timeout=stream_timeout,
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
        stream = AnthropicChatStream(call=call, clock=self._clock, token=token)
        token.add_hard_cancel_hook(raw_stream.close)
        return stream

    def embed(self, text: str) -> tuple[float, ...]:
        """Always raise — Anthropic exposes no embeddings endpoint at all (§6.9)."""
        del text
        raise ProviderBadRequestError(
            message="ANTHROPIC has no embeddings endpoint", context=self._error_context()
        )

    def list_models(self) -> tuple[ModelName, ...]:
        """Always raise — Anthropic exposes no models-list endpoint (§6.9.1)."""
        raise ProviderBadRequestError(
            message=(
                "ANTHROPIC exposes no models-list endpoint; the catalog is "
                "provider-configured (default_models)"
            ),
            context=self._error_context(),
        )

    def probe_health(self) -> ProviderHealth:
        """Check reachability only — no discovery step ever (§6.8.1, §6.9.1).

        ``discovery_supported`` is always ``False`` and ``model_count`` is
        always ``None``: the Anthropic API exposes no models-list endpoint, so
        a reachable provider is healthy without any second network call.
        """
        t0 = self._clock.monotonic_ms()
        reachable = self._probe_reachable()
        return ProviderHealth(
            provider_id=self._config.provider_id,
            reachable=reachable,
            discovery_supported=False,
            model_count=None,
            last_probe_ms=self._clock.monotonic_ms() - t0,
            last_error=None if reachable else "endpoint unreachable",
            probed_at=self._clock.monotonic_ms(),
        )

    def _probe_reachable(self) -> bool:
        """Confirm the configured endpoint is reachable (DNS + TCP connect).

        Never issues a chat or models-list call — a bare HTTP request against
        the base URL is enough to confirm the endpoint answers at all. A
        4xx/5xx response still proves reachability; only a connection-level
        failure means unreachable.
        """
        base_url = str(self._sdk_client.base_url)
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
        containing a ``thinking`` block still surfaces it in
        ``ChatResponse.text`` (§6.9) regardless of this capability flag.
        """
        return False

    def close(self) -> None:
        """Release this client's underlying transport resources (best-effort)."""
        with contextlib.suppress(Exception):
            self._sdk_client.close()


def _split_system_and_messages(
    messages: tuple[ChatMessage, ...],
) -> tuple[str | None, list[anthropic.types.MessageParam]]:
    """Split domain ``ChatMessage``s into Anthropic's ``system=`` + ``messages=`` shape.

    ``ChatRequest.messages`` is an optional leading ``SYSTEM`` message, then
    alternating ``USER``/``ASSISTANT`` (§4). Anthropic's Messages API takes the
    system prompt as a separate top-level ``system=`` string, not a
    role-tagged message, so the leading ``SYSTEM`` message (if any) is popped
    off and the rest translated 1:1.

    Args:
        messages: The well-ordered domain message sequence.

    Returns:
        A ``(system, sdk_messages)`` pair; ``system`` is ``None`` when
        ``messages`` carries no leading ``SYSTEM`` message.
    """
    if messages and messages[0].role is ChatRole.SYSTEM:
        system: str | None = messages[0].content
        rest = messages[1:]
    else:
        system = None
        rest = messages
    sdk_messages: list[anthropic.types.MessageParam] = [
        {
            "role": "assistant" if message.role is ChatRole.ASSISTANT else "user",
            "content": message.content,
        }
        for message in rest
    ]
    return system, sdk_messages
