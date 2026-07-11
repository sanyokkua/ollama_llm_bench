"""Shared fixtures and local test doubles for ``backend/readiness/`` tests.

These fakes implement this module's own narrow collaborator Protocols
(``ReadinessProviderRegistry``, ``ReadinessLLMClient``, ``ReadinessEmbeddingSelector``)
— no suitable fake exists elsewhere because those Protocols are declared locally in
``backend/readiness/protocols.py`` (the real ``backend/provider_registry`` and
``backend/embedding`` modules are owned by later stories; see that module's docstring).
"""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    Iso8601Utc,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ProviderType,
)
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.events.protocols import Subscription
from ollama_llm_bench.backend.readiness.protocols import ReadinessEmbeddingSelection


class FakeClock:
    """A fully controllable ``Clock`` double."""

    def __init__(self, *, start_monotonic_ms: int = 0) -> None:
        self._monotonic_ms = start_monotonic_ms
        self._now = datetime(2026, 1, 1, tzinfo=UTC)

    def now_utc(self) -> Iso8601Utc:
        """Return the fake's current wall-clock instant as an ISO-8601 UTC string."""
        return self._now.isoformat()

    def monotonic_ms(self) -> int:
        """Return the fake's current monotonic millisecond counter."""
        return self._monotonic_ms

    def advance_monotonic_ms(self, delta_ms: int) -> None:
        """Move the monotonic counter forward by ``delta_ms``."""
        self._monotonic_ms += delta_ms


class SpyEventBus:
    """A minimal in-memory ``EventBus`` double recording every ``emit`` call, in order."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        """Unused by these tests; present only to satisfy the Protocol shape."""
        raise NotImplementedError("subscribe is not exercised by backend/readiness tests")

    def emit(self, signal_name: str, payload: object) -> None:
        """Record the emitted ``(signal_name, payload)`` pair, in call order."""
        self.emitted.append((signal_name, payload))


class FakeReadinessLLMClient:
    """A controllable ``ReadinessLLMClient`` double. Never calls a real network."""

    def __init__(
        self,
        *,
        health: ProviderHealth,
        supports_embedding: bool = False,
        supports_discovery: bool = False,
        models: tuple[ModelName, ...] = (),
    ) -> None:
        self._health = health
        self._supports_embedding = supports_embedding
        self._supports_discovery = supports_discovery
        self._models = models
        self.probe_health_calls = 0
        self.embed_calls = 0
        self.chat_calls = 0

    def probe_health(self) -> ProviderHealth:
        """Return the canned health without any network call."""
        self.probe_health_calls += 1
        return self._health

    def supports_embedding(self) -> bool:
        """Return the canned embedding-surface capability."""
        return self._supports_embedding

    def supports_discovery(self) -> bool:
        """Return the canned discovery capability."""
        return self._supports_discovery

    def list_models(self) -> tuple[ModelName, ...]:
        """Return the canned discovered model list."""
        return self._models

    def embed(self, text: str) -> tuple[float, ...]:
        """Fail the test loudly if the automatic path ever calls this (DD-48)."""
        self.embed_calls += 1
        raise AssertionError("embed() must never be called by the automatic readiness path")

    def chat(self, request: object) -> object:
        """Fail the test loudly if the automatic path ever calls this (DD-48)."""
        self.chat_calls += 1
        raise AssertionError("chat() must never be called by the automatic readiness path")


class FakeReadinessProviderRegistry:
    """A controllable ``ReadinessProviderRegistry`` double."""

    def __init__(
        self,
        *,
        enabled: tuple[ProviderConfig, ...] = (),
        clients: dict[ProviderId, FakeReadinessLLMClient] | None = None,
    ) -> None:
        self._enabled = enabled
        self._clients = clients or {}

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        """Return the canned enabled-provider tuple."""
        return self._enabled

    def get_client(self, provider_id: ProviderId) -> FakeReadinessLLMClient:
        """Return the canned client, or raise ``ConfigurationError`` when absent."""
        client = self._clients.get(provider_id)
        if client is None:
            raise ConfigurationError(message="missing environment variable", context=None)
        return client


class FakeReadinessEmbeddingSelection:
    """A concrete value structurally satisfying ``ReadinessEmbeddingSelection``."""

    def __init__(self, *, provider: ProviderConfig, model_name: ModelName) -> None:
        self._provider = provider
        self._model_name = model_name

    @property
    def provider(self) -> ProviderConfig:
        """The provider hosting the selected embedding model."""
        return self._provider

    @property
    def model_name(self) -> ModelName:
        """The selected embedding model's name."""
        return self._model_name


class FakeReadinessEmbeddingSelector:
    """A controllable ``ReadinessEmbeddingSelector`` double."""

    def __init__(self, *, selection: ReadinessEmbeddingSelection | None = None) -> None:
        self._selection = selection

    def resolve_embedding_selection(self) -> ReadinessEmbeddingSelection | None:
        """Return the canned selection (or ``None``)."""
        return self._selection


def make_provider_config(
    *, provider_id: ProviderId, name: str = "provider", enabled: bool = True
) -> ProviderConfig:
    """Build a minimal, otherwise-arbitrary ``ProviderConfig``."""
    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=enabled,
    )


class ThreadPoolTaskRunner[T]:
    """A real, bounded ``concurrent.futures.ThreadPoolExecutor``-backed ``TaskRunner`` double.

    Unlike ``InlineTaskRunner``, this genuinely runs submitted units on
    background threads — needed to prove coalescing (STORY-016-AC-5/AC-6),
    gate-deferral concurrency (STORY-016-AC-7), and saturated-pool
    orchestration (STORY-016-AC-8) instead of merely asserting them against
    single-threaded, already-resolved ``Future``s.
    """

    def __init__(self, *, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self.submit_count = 0

    def submit(self, fn: Callable[[], T], *, token: CancellationToken) -> Future[T]:
        """Schedule ``fn`` on the bounded thread pool and return its ``Future``."""
        self.submit_count += 1
        return self._executor.submit(fn)

    def shutdown(self) -> None:
        """Release the pool's worker threads; call once the test is done with it."""
        self._executor.shutdown(wait=True)


@pytest.fixture
def fake_clock() -> FakeClock:
    """A fresh ``FakeClock`` starting at monotonic 0."""
    return FakeClock()


@pytest.fixture
def spy_event_bus() -> SpyEventBus:
    """A fresh ``SpyEventBus`` with no recorded emissions."""
    return SpyEventBus()
