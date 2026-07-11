"""The canonical ``LLMClient`` Protocol, plus the ``ProviderRegistry`` contract.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§9 (Provider Registry) and §10 (LLM Client);
``docs/v3_specification/11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md``.

Per the resolution recorded in ``docs/stories/story-017-provider-registry-and-llm-client-
protocol.md`` ("Ambiguity #1"), the one authoritative Python declaration of ``LLMClient``
lives here. Each concrete provider adapter (``backend/provider_openai_compatible/``,
``backend/provider_anthropic/``, ``backend/provider_gemini/`` — later stories) re-exports
this same symbol from its own ``__init__.py`` rather than declaring a second copy; a
concrete client satisfies this Protocol structurally, with zero import-time coupling back
to this module.

``ChatStream`` is declared locally as a small structural Protocol (a synchronous iterator
of ``ChatChunk`` that also exposes ``trailing_response()``) because no such type exists
yet in ``backend/domain`` — see 08-E §10's ``chat_stream`` docstring.
"""

from collections.abc import Callable, Iterator
from typing import Protocol

from ollama_llm_bench.backend.domain import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    InferenceTestResult,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
)

__all__: list[str] = [
    "ChatStream",
    "ClientBuilder",
    "LLMClient",
    "ProviderRegistry",
]


class ChatStream(Protocol):
    """A synchronous iterator of ``ChatChunk`` yielding a trailing ``ChatResponse``.

    Returned by ``LLMClient.chat_stream`` (08-E §10). Iterating yields content
    chunks — plus >= 1 Hz empty-content heartbeat chunks during provider silence
    — until the stream is exhausted; ``trailing_response()`` is then callable to
    obtain the completed ``ChatResponse``. Declared locally because no
    ``backend.domain`` type currently names this shape.
    """

    def __iter__(self) -> Iterator[ChatChunk]:
        """Return the chunk iterator itself."""
        ...

    def __next__(self) -> ChatChunk:
        """Return the next chunk, raising ``StopIteration`` once exhausted."""
        ...

    def trailing_response(self) -> ChatResponse:
        """Return the completed response once the stream is exhausted.

        Raises:
            ProviderError: The provider rejected the request or returned an
                unusable response.
            TimeoutError: The call exceeded ``request.timeout_ms``.
        """
        ...


class LLMClient(Protocol):
    """A single provider's chat, embedding, and capability surface (08-E §10).

    The canonical declaration every concrete provider adapter satisfies
    structurally. ``list_models``, ``probe_health``, ``test_inference``,
    ``chat``, ``chat_stream``, and ``embed`` are *blocking* — invoked only on a
    ``TaskRunner`` worker thread. The three ``supports_*`` methods and
    ``close`` are fast-synchronous capability/lifecycle calls, callable from
    any context.
    """

    def list_models(self) -> tuple[ModelName, ...]:
        """Return the provider's available model names.

        May be empty for a reachable provider that exposes none.

        Raises:
            ProviderError: The listing call itself failed.
        """
        ...

    def probe_health(self) -> ProviderHealth:
        """Check reachability and, when supported, discover models.

        Never issues a chat or embedding inference call. Never raises —
        every failure mode is captured into the returned ``ProviderHealth``.
        """
        ...

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        """Run one small end-to-end chat call against ``model_name``.

        User-initiated only. Never raises — every provider-side failure is
        captured into the returned ``InferenceTestResult``.
        """
        ...

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Consume this client's own ``chat_stream`` to completion.

        Convenience wrapper (DD-51); not a second transport path. Error
        behaviour is identical to ``chat_stream``.

        Raises:
            ProviderError: The provider rejected the request or returned an
                unusable response.
            TimeoutError: The call exceeded ``request.timeout_ms``.
        """
        ...

    def chat_stream(self, request: ChatRequest) -> ChatStream:
        """Execute a chat call, returning a synchronous stream of chunks (DD-51).

        THE chat execution surface; invoked on a worker thread. The transport
        always opens in streaming mode; when the provider cannot stream the
        client falls back to a non-streaming request behind the same iterator
        contract.

        Raises:
            ProviderError: The provider rejected the request or returned an
                unusable response.
            TimeoutError: The call exceeded ``request.timeout_ms``.
        """
        ...

    def embed(self, text: str) -> tuple[float, ...]:
        """Return the embedding vector for ``text``.

        Implemented only by embedding-capable clients.

        Raises:
            ProviderError: The embedding call failed.
            TimeoutError: The call exceeded its time budget.
        """
        ...

    def supports_streaming(self) -> bool:
        """Whether the transport supports token streaming."""
        ...

    def supports_reasoning_effort(self) -> bool:
        """Whether the provider accepts a reasoning-effort parameter."""
        ...

    def supports_thinking(self) -> bool:
        """Whether the model emits a reasoning/thinking block."""
        ...

    def close(self) -> None:
        """Release this client's underlying transport resources.

        Best-effort: never raises to the caller. Not part of 08-E §10's
        printed signature block, but required by SPEC-045/STORY-017-AC-8 — the
        registry calls this on a superseded client once the single-inference
        gate is observed idle. The registry catches and logs any failure
        raised here; it never propagates.
        """
        ...


type ClientBuilder = Callable[[ProviderConfig, str], LLMClient]
"""Per-``ProviderType`` client constructor: ``(config, resolved_api_key) -> LLMClient``.

Never touches the environment itself — the registry has already resolved the
secret before calling this. Performs no network call; construction is pure
object assembly (§6.2 step 4).
"""


class ProviderRegistry(Protocol):
    """Owns the live ``LLMClient`` instances and routes targets to them (08-E §9).

    All three methods are synchronous; the network work happens later, in the
    client's own blocking methods, invoked on ``TaskRunner`` worker threads.
    """

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        """Return the enabled providers in display order.

        fast-synchronous; never raises.
        """
        ...

    def get_client(self, provider_id: ProviderId) -> LLMClient:
        """Return the live client for a provider.

        fast-synchronous.

        Raises:
            ConfigurationError: The provider is unknown, disabled, or its
                api-key env-var name does not resolve (the named variable is
                unset/empty).
        """
        ...

    def reload(self) -> None:
        """Rebuild every client from the current provider catalog.

        fast-synchronous. Emits ``_provider_registry_reloaded`` exactly once,
        after a successful rebuild.

        Raises:
            ConfigurationError: An enabled provider's configuration is
                structurally invalid. The previous catalog and client map are
                left untouched; no event is emitted.
            PersistenceError: The underlying ``ProvidersStore.list_providers()``
                read failed.
        """
        ...
