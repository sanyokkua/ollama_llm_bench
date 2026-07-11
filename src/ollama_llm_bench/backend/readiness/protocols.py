"""The ``ReadinessService`` contract, plus the narrow collaborator Protocols it needs.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§12 (Readiness Service); ``docs/v3_specification/11_Services_and_Algorithms/
09_READINESS_PROBE.md`` §6.1-§6.6, §9.

``ReadinessProviderRegistry``, ``ReadinessLLMClient``, and ``ReadinessEmbeddingSelector``
are declared here as narrow, structurally-typed Protocols carrying only the members this
module's algorithm needs. The real ``ProviderRegistry`` (`backend/provider_registry/`),
the real ``LLMClient`` (owned by the provider adapters), and the real embedding
selection resolver (`backend/embedding/`) are owned by their own, later stories; each
satisfies its narrow Protocol here structurally, with zero import-time coupling, because
``typing.Protocol`` matching is structural, not nominal (the same pattern
``backend/infra/protocols.py`` uses for the future ``PlatformDetector``).
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
)

__all__: list[str] = [
    "ReadinessEmbeddingSelection",
    "ReadinessEmbeddingSelector",
    "ReadinessLLMClient",
    "ReadinessProviderRegistry",
    "ReadinessService",
]


class ReadinessLLMClient(Protocol):
    """The slice of ``LLMClient`` the readiness probe needs (`02_LLM_CLIENT_PROTOCOL.md`).

    Satisfied structurally by the real per-provider ``LLMClient`` implementations.
    """

    def probe_health(self) -> ProviderHealth:
        """Reachability + conditional model discovery; never an inference call.

        Blocking; invoked on a ``TaskRunner`` worker thread. Never raises —
        every failure mode is captured into the returned ``ProviderHealth``.
        """
        ...

    def supports_embedding(self) -> bool:
        """Whether this client exposes an embedding surface (DD-48 handshake).

        fast-synchronous capability lookup; callable from any context.
        """
        ...

    def supports_discovery(self) -> bool:
        """Whether this client's ``probe_health`` performs model discovery.

        fast-synchronous capability lookup; callable from any context.
        """
        ...

    def list_models(self) -> tuple[ModelName, ...]:
        """Return the provider's discovered model names for the embedding handshake.

        Blocking; invoked on a ``TaskRunner`` worker thread. Never raises for
        an empty catalog.
        """
        ...


class ReadinessProviderRegistry(Protocol):
    """The slice of ``ProviderRegistry`` the readiness probe needs (`03_PROVIDER_REGISTRY.md`).

    Satisfied structurally by the real ``backend/provider_registry`` implementation.
    """

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        """Return the enabled providers in display order.

        fast-synchronous; never raises.
        """
        ...

    def get_client(self, provider_id: ProviderId) -> ReadinessLLMClient:
        """Return the live client for a provider.

        fast-synchronous.

        Raises:
            ConfigurationError: The provider is unknown, disabled, or its
                api-key env-var name does not resolve (the named variable is
                unset/empty).
        """
        ...


class ReadinessEmbeddingSelection(Protocol):
    """The resolved ``(provider, embedding model)`` pair (`09_READINESS_PROBE.md` §2).

    Satisfied structurally by the real embedding-selection value owned by
    ``backend/embedding``.
    """

    @property
    def provider(self) -> ProviderConfig:
        """The provider hosting the selected embedding model."""
        ...

    @property
    def model_name(self) -> ModelName:
        """The selected embedding model's name."""
        ...


class ReadinessEmbeddingSelector(Protocol):
    """Resolves the live embedding selection for the handshake-only probe (DD-48).

    Satisfied structurally by the real ``backend/embedding`` resolver (or, until
    that module exists, any collaborator exposing this single method — e.g. a
    thin adapter over ``SettingsService`` + ``ReadinessProviderRegistry``).
    """

    def resolve_embedding_selection(self) -> ReadinessEmbeddingSelection | None:
        """Resolve the currently selected ``(provider, embedding model)`` pair.

        fast-synchronous.

        Returns:
            The resolved selection, or ``None`` when no embedding model is
            selected.

        Raises:
            PersistenceError: The underlying settings read failed. The
                Readiness Service treats this as an unreachable embedding
                result and proceeds (`09_READINESS_PROBE.md` §8, RP-14) —
                the exception is caught inside this module, never
                propagated further by ``ReadinessService``.
        """
        ...


class ReadinessService(Protocol):
    """Aggregates provider and embedding health into an application-readiness view.

    Source of truth: `08-E` §12; `09_READINESS_PROBE.md`.
    """

    def snapshot(self) -> AppReadinessSnapshot:
        """Return the most recent readiness snapshot.

        fast-synchronous; never raises; never probes. Returns a ``CHECKING``
        snapshot before the first probe completes.
        """
        ...

    def probe_all(self) -> AppReadinessSnapshot:
        """Probe every enabled provider and the embedding model, and recompute.

        Blocking; orchestrated on the dispatcher thread (DD-38/DD-40): the
        per-provider reachability handshakes fan out concurrently onto the
        shared ``TaskRunner`` and this method joins their ``Future``s; the
        single embedding probe then runs once, serially. Overlapping calls
        coalesce onto one shared in-flight batch (`09_READINESS_PROBE.md`
        §6.6). Emits ``_app_readiness_changed`` only when the recomputed
        snapshot differs from the cached one. Never raises: an unreachable
        provider is reported as such.
        """
        ...

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        """Probe one provider and return its health.

        Blocking; a single leaf unit invoked on a ``TaskRunner`` worker
        thread. Never submits work to the ``TaskRunner`` itself and never
        blocks on a ``Future``. Never raises.
        """
        ...
