"""Shared fixtures and local test doubles for ``backend/provider_registry/`` tests.

``FakeProvidersStore`` implements the real ``ProvidersStore`` Protocol
(``backend/persistence/providers/protocols.py``) structurally, with only
``list_providers`` behaving for real — every other method is unused by this
module's own tests and raises ``NotImplementedError`` if a test ever exercises
it by mistake. ``FakeLLMClient`` implements the canonical ``LLMClient``
Protocol declared by this module. The ``EventBus`` double follows the same
in-memory ``subscribe``/``emit`` convention used by
``backend/readiness/tests/conftest.py`` and
``backend/stores/inference_activity/tests/conftest.py``, except that
``subscribe`` here genuinely records handlers so a test can drive the
registry's ``_inference_activity_changed`` subscription — the deferred-close
mechanism under test in ``test_deferred_close.py`` depends on that dispatch
actually happening.

``FakeInferenceActivityStore`` is imported, not reinvented, from
``ollama_llm_bench.backend.stores.inference_activity.testing`` per the story's
instruction; it is driven with its real ``try_acquire``/``release`` semantics
against the local ``FakeClock``.
"""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    ChatRequest,
    ChatResponse,
    InferenceActivity,
    InferenceActivityContext,
    InferenceTestResult,
    Iso8601Utc,
    ModelName,
    ProviderConfig,
    ProviderConfigDraft,
    ProviderHealth,
    ProviderId,
    ProviderType,
)
from ollama_llm_bench.backend.events.protocols import Subscription
from ollama_llm_bench.backend.provider_registry.protocols import ChatStream, ClientBuilder
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

__all__: list[str] = [
    "FakeClock",
    "FakeEventBus",
    "FakeLLMClient",
    "FakeProvidersStore",
    "make_provider_config",
]


class FakeClock:
    """A fully controllable ``Clock`` double, matching sibling modules' fixture shape."""

    def __init__(self, *, start_monotonic_ms: int = 0) -> None:
        self._monotonic_ms = start_monotonic_ms

    def now_utc(self) -> Iso8601Utc:
        """Return a fixed ISO-8601 UTC instant; wall-clock value is irrelevant here."""
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        """Return the fake's current monotonic millisecond counter."""
        return self._monotonic_ms

    def advance_monotonic_ms(self, delta_ms: int) -> None:
        """Move the monotonic counter forward by ``delta_ms``."""
        self._monotonic_ms += delta_ms


class FakeEventBus:
    """An in-memory ``EventBus`` double that genuinely dispatches ``emit`` to subscribers.

    Unlike the read-only spies in ``readiness``/``inference_activity`` tests,
    this module's own tests need ``subscribe`` to actually register a handler
    — the registry subscribes to ``_inference_activity_changed`` at
    construction time, and ``test_deferred_close.py`` drives that
    subscription by acquiring/releasing the real
    ``FakeInferenceActivityStore``, which emits on this same bus.
    """

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []
        self._handlers: dict[str, list[Callable[[object], None]]] = {}

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        """Register ``handler`` for ``signal_name`` and return a cancellable handle."""
        self._handlers.setdefault(signal_name, []).append(handler)

        class _Subscription:
            def __init__(self, bus: FakeEventBus, name: str, fn: Callable[[object], None]) -> None:
                self._bus = bus
                self._name = name
                self._fn = fn

            def cancel(self) -> None:
                handlers = self._bus._handlers.get(self._name, [])
                if self._fn in handlers:
                    handlers.remove(self._fn)

        return _Subscription(self, signal_name, handler)

    def emit(self, signal_name: str, payload: object) -> None:
        """Record the emission, then synchronously call every subscribed handler."""
        self.emitted.append((signal_name, payload))
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)

    def emitted_count(self, signal_name: str) -> int:
        """Return how many times ``signal_name`` was emitted."""
        return sum(1 for name, _ in self.emitted if name == signal_name)


class FakeProvidersStore:
    """A structural ``ProvidersStore`` fake; only ``list_providers`` behaves for real.

    Every other method is unused by ``backend/provider_registry`` tests and
    raises ``NotImplementedError`` if a test accidentally calls it.
    """

    def __init__(self, *, providers: tuple[ProviderConfig, ...] = ()) -> None:
        self._providers = providers

    def set_providers(self, providers: tuple[ProviderConfig, ...]) -> None:
        """Replace the catalog ``list_providers`` will return on the next call."""
        self._providers = providers

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        """Return the canned catalog, in the order it was set."""
        return self._providers

    def get_by_name(self, name: str) -> ProviderConfig | None:
        """Unused by these tests."""
        raise NotImplementedError("get_by_name is not exercised by provider_registry tests")

    def add(self, draft: ProviderConfigDraft) -> ProviderId:
        """Unused by these tests."""
        raise NotImplementedError("add is not exercised by provider_registry tests")

    def update(self, provider_id: ProviderId, config: ProviderConfig) -> None:
        """Unused by these tests."""
        raise NotImplementedError("update is not exercised by provider_registry tests")

    def delete(self, provider_id: ProviderId) -> None:
        """Unused by these tests."""
        raise NotImplementedError("delete is not exercised by provider_registry tests")

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Unused by these tests."""
        raise NotImplementedError("replace_providers is not exercised by provider_registry tests")

    def replace_providers_in_open_transaction(self, configs: tuple[ProviderConfig, ...]) -> None:
        """Unused by these tests."""
        raise NotImplementedError(
            "replace_providers_in_open_transaction is not exercised by provider_registry tests"
        )


class FakeLLMClient:
    """A controllable ``LLMClient`` double. Never touches the network.

    Records the resolved api-key value and ``ProviderConfig`` it was built
    with, and exposes ``close_calls``/``closed`` so a test can spy on
    ``close()``.
    """

    def __init__(
        self, *, provider: ProviderConfig | None = None, resolved_api_key: str | None = None
    ) -> None:
        self.provider = provider
        self.resolved_api_key = resolved_api_key
        self.close_calls = 0

    @property
    def closed(self) -> bool:
        """Whether ``close()`` has been called at least once."""
        return self.close_calls > 0

    def list_models(self) -> tuple[ModelName, ...]:
        """Return an empty model list; unused by these tests."""
        return ()

    def probe_health(self) -> ProviderHealth:
        """Unused by these tests."""
        raise NotImplementedError("probe_health is not exercised by provider_registry tests")

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        """Unused by these tests."""
        raise NotImplementedError("test_inference is not exercised by provider_registry tests")

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        """Unused by these tests."""
        raise NotImplementedError("chat is not exercised by provider_registry tests")

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        """Unused by these tests."""
        raise NotImplementedError("chat_stream is not exercised by provider_registry tests")

    def embed(self, text: str) -> tuple[float, ...]:
        """Unused by these tests."""
        raise NotImplementedError("embed is not exercised by provider_registry tests")

    def supports_streaming(self) -> bool:
        """Fixed capability answer; unused by these tests' assertions."""
        return False

    def supports_reasoning_effort(self) -> bool:
        """Fixed capability answer; unused by these tests' assertions."""
        return False

    def supports_thinking(self) -> bool:
        """Fixed capability answer; unused by these tests' assertions."""
        return False

    def close(self) -> None:
        """Record that this client was closed."""
        self.close_calls += 1


def make_provider_config(  # noqa: PLR0913  # test builder must expose every AC-3/AC-4 field
    *,
    provider_id: str = "11111111-1111-4111-8111-111111111111",
    name: str = "provider",
    provider_type: ProviderType = ProviderType.OPENAI_COMPATIBLE,
    enabled: bool = True,
    base_url: str | None = "http://localhost:11434/v1",
    api_key_raw: str | None = "",
    azure_fields: tuple[str | None, str | None, str | None] = (None, None, None),
    provider_order: int = 0,
) -> ProviderConfig:
    """Build a minimal, otherwise-arbitrary ``ProviderConfig``.

    Defaults describe a valid, keyless, local ``OPENAI_COMPATIBLE`` provider;
    every keyword is overridable to express any row of AC-3/AC-4's tables.

    Args:
        azure_fields: ``(azure_endpoint_raw, azure_deployment_raw,
            azure_api_version_raw)``, grouped to keep this factory's
            parameter count within the project's limit.
    """
    azure_endpoint_raw, azure_deployment_raw, azure_api_version_raw = azure_fields
    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        provider_type=provider_type,
        enabled=enabled,
        base_url=base_url,
        api_key_raw=api_key_raw,
        azure_endpoint_raw=azure_endpoint_raw,
        azure_deployment_raw=azure_deployment_raw,
        azure_api_version_raw=azure_api_version_raw,
        provider_order=provider_order,
    )


def make_client_builders(
    *, factory: Callable[[ProviderConfig, str], FakeLLMClient] | None = None
) -> dict[ProviderType, ClientBuilder]:
    """Build a ``{ProviderType: ClientBuilder}`` map, one fake-returning builder per type."""

    def _default_factory(provider: ProviderConfig, resolved_api_key: str) -> FakeLLMClient:
        return FakeLLMClient(provider=provider, resolved_api_key=resolved_api_key)

    build = factory or _default_factory
    return dict.fromkeys(ProviderType, build)


@pytest.fixture
def fake_clock() -> FakeClock:
    """A fresh ``FakeClock`` starting at monotonic 0."""
    return FakeClock()


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    """A fresh ``FakeEventBus`` with no recorded emissions and no subscribers."""
    return FakeEventBus()


@pytest.fixture
def fake_providers_store() -> FakeProvidersStore:
    """A fresh ``FakeProvidersStore`` with an empty catalog."""
    return FakeProvidersStore()


@pytest.fixture
def client_builders() -> dict[ProviderType, ClientBuilder]:
    """A ``{ProviderType: ClientBuilder}`` map covering every ``ProviderType``, each
    returning a fresh ``FakeLLMClient`` recording its build arguments."""
    return make_client_builders()


@pytest.fixture
def gate(fake_clock: FakeClock, fake_event_bus: FakeEventBus) -> FakeInferenceActivityStore:
    """A real ``FakeInferenceActivityStore`` sharing this test's clock and event bus."""
    return FakeInferenceActivityStore(clock=fake_clock, event_bus=fake_event_bus)


def make_activity_context(
    *, activity: InferenceActivity = InferenceActivity.PROVIDER_TEST
) -> InferenceActivityContext:
    """Build a minimal ``InferenceActivityContext`` for driving the gate in tests."""
    return InferenceActivityContext(activity=activity, started_at=0)
