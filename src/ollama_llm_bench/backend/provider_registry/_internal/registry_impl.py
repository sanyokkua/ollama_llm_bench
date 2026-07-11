"""The concrete ``ProviderRegistry`` implementation.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md``
§6.4-§6.6, §9 (composite-key routing, enable/disable, atomic rebuild, SPEC-045 deferred
close).

Lock discipline (load-bearing, do not change without re-reading the concurrency
standard): ``self._lock`` guards only the three pieces of mutable state this registry
owns — the catalog, the client map, and the pending-close list. It is never held while
calling out to the providers store, a client's ``close()``, or the event bus, so a
synchronous event-bus subscriber calling back into this registry can never re-enter the
lock. ``reload`` performs the whole rebuild-and-validate sequence *before* taking the
lock for the swap, so the previous catalog/client map are visible to every other thread
for the entire duration of a reload that ultimately fails.
"""

from collections.abc import Mapping
import threading

import structlog

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderId, ProviderType
from ollama_llm_bench.backend.errors import ConfigurationError, redact
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    SIGNAL_PROVIDER_REGISTRY_RELOADED,
    EventBus,
    ProviderRegistryReloadedEvent,
)
from ollama_llm_bench.backend.persistence.providers import ProvidersStore
from ollama_llm_bench.backend.provider_registry._internal.client_builder import build_one
from ollama_llm_bench.backend.provider_registry.protocols import ClientBuilder, LLMClient
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = [
    "ProviderRegistryCollaborators",
    "ProviderRegistryImpl",
]

_logger = structlog.get_logger("app.provider_registry")

_CAUSE_RELOAD = "reload"


class ProviderRegistryCollaborators:
    """Groups the concrete registry's constructor dependencies (<=4-parameter rule).

    A plain, private-implementation-detail bundle — not a cross-boundary DTO,
    so it is an ordinary class rather than a ``msgspec.Struct``; it never
    leaves this ``_internal`` package.
    """

    def __init__(
        self,
        *,
        providers_store: ProvidersStore,
        client_builders: Mapping[ProviderType, ClientBuilder],
        gate: InferenceActivityStore,
        event_bus: EventBus,
    ) -> None:
        self.providers_store = providers_store
        self.client_builders = client_builders
        self.gate = gate
        self.event_bus = event_bus


class ProviderRegistryImpl:
    """Owns the live ``LLMClient`` instances and routes targets to them.

    Constructed once by ``make_provider_registry``, which performs the first
    build silently (no event emission — construction is not a reload; see
    ``08-Q_event_payload_schemas.md``'s ``reload_cause`` enum and
    ``09_READINESS_PROBE.md`` §"startup, an explicit refresh, or a
    ``_provider_registry_reloaded`` event" treating construction and the
    reload event as distinct triggers). ``reload()`` repeats the same rebuild
    and additionally emits ``_provider_registry_reloaded`` on success.
    """

    def __init__(self, *, collaborators: ProviderRegistryCollaborators) -> None:
        self._providers_store = collaborators.providers_store
        self._client_builders = collaborators.client_builders
        self._gate = collaborators.gate
        self._event_bus = collaborators.event_bus
        self._lock = threading.Lock()
        self._catalog: tuple[ProviderConfig, ...] = ()
        self._client_map: dict[ProviderId, LLMClient] = {}
        self._pending_close: list[LLMClient] = []
        self._event_bus.subscribe(
            SIGNAL_INFERENCE_ACTIVITY_CHANGED, self._on_activity_changed, owner=self
        )
        self._rebuild(emit=False)

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        """Return the enabled providers in display order. Never raises."""
        with self._lock:
            return tuple(provider for provider in self._catalog if provider.enabled)

    def get_client(self, provider_id: ProviderId) -> LLMClient:
        """Return the live client for a provider (§6.4).

        Raises:
            ConfigurationError: The provider is unknown, disabled, or has no
                built client (unresolved secret / invalid config).
        """
        with self._lock:
            provider = self._find(provider_id)
            if provider is None:
                raise ConfigurationError(message="unknown provider")
            if not provider.enabled:
                raise ConfigurationError(message="provider disabled")
            client = self._client_map.get(provider_id)
            if client is None:
                raise ConfigurationError(message="provider unusable")
            return client

    def reload(self) -> None:
        """Rebuild every client from the current provider catalog (§6.6).

        Emits ``_provider_registry_reloaded`` exactly once, after a
        successful rebuild — never on construction (see the class
        docstring).

        Raises:
            ConfigurationError: An enabled provider's configuration is
                structurally invalid. The previous catalog and client map are
                left untouched; no event is emitted.
            PersistenceError: The underlying ``ProvidersStore.list_providers()``
                read failed.
        """
        self._rebuild(emit=True)

    def _find(self, provider_id: ProviderId) -> ProviderConfig | None:
        for provider in self._catalog:
            if provider.provider_id == provider_id:
                return provider
        return None

    def _rebuild(self, *, emit: bool) -> None:
        """The atomic commit-or-rollback rebuild body (§6.6, §9).

        Args:
            emit: Whether to publish ``_provider_registry_reloaded`` after a
                successful swap. ``False`` only for the initial build
                performed by ``__init__``; ``reload()`` always passes
                ``True``.
        """
        new_catalog = self._providers_store.list_providers()
        new_map = self._build_new_client_map(new_catalog)
        to_close_now = self._swap_in(new_catalog, new_map)
        for client in to_close_now:
            _close_quietly(client)
        if emit:
            self._emit_reloaded(new_catalog)

    def _build_new_client_map(
        self, new_catalog: tuple[ProviderConfig, ...]
    ) -> dict[ProviderId, LLMClient]:
        """Build a complete new client map; raises on the first structural failure."""
        new_map: dict[ProviderId, LLMClient] = {}
        for provider in new_catalog:
            if not provider.enabled:
                continue
            client = build_one(provider, client_builders=self._client_builders)
            if client is not None:
                new_map[provider.provider_id] = client
        return new_map

    def _swap_in(
        self,
        new_catalog: tuple[ProviderConfig, ...],
        new_map: dict[ProviderId, LLMClient],
    ) -> list[LLMClient]:
        """Swap the catalog/client map in atomically; return clients to close now."""
        with self._lock:
            old_client_map = self._client_map
            self._catalog = new_catalog
            self._client_map = new_map
            if self._gate.is_busy():
                self._pending_close.extend(old_client_map.values())
                return []
            return list(old_client_map.values())

    def _emit_reloaded(self, new_catalog: tuple[ProviderConfig, ...]) -> None:
        """Publish ``_provider_registry_reloaded`` after a successful ``reload()`` swap.

        ``reload_cause`` is always ``"reload"`` here: construction never
        calls this method (per ``08-Q_event_payload_schemas.md``'s
        ``reload_cause`` enum, which does not include a "startup" value).
        """
        enabled_ids = tuple(provider.provider_id for provider in new_catalog if provider.enabled)
        self._event_bus.emit(
            SIGNAL_PROVIDER_REGISTRY_RELOADED,
            ProviderRegistryReloadedEvent(
                provider_count=len(new_catalog),
                enabled_provider_ids=enabled_ids,
                reload_cause=_CAUSE_RELOAD,
            ),
        )

    def _on_activity_changed(self, _event: object) -> None:
        """Drain the pending-close list once the gate is observed idle (SPEC-045)."""
        if self._gate.is_busy():
            return
        with self._lock:
            to_close = self._pending_close
            self._pending_close = []
        for client in to_close:
            _close_quietly(client)


def _close_quietly(client: LLMClient) -> None:
    """Close ``client`` best-effort; log and swallow any failure (SPEC-045)."""
    try:
        client.close()
    except Exception as exc:  # noqa: BLE001  # best-effort close; never raises to the caller
        _logger.warning("provider_registry_client_close_failed", error=redact(str(exc)))
