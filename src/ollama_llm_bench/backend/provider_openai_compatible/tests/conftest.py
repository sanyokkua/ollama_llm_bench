"""Shared fixtures for ``backend/provider_openai_compatible/`` tests.

``FakeClock`` and ``FakeEventBus`` follow the same shape as
``backend/provider_registry/tests/conftest.py`` so a reader familiar with one
module's tests recognises the other's doubles immediately.
``FakeInferenceActivityStore`` is imported, not reinvented, from
``ollama_llm_bench.backend.stores.inference_activity.testing`` per the
project's established convention (see that module's own docstring and
``provider_registry/tests/conftest.py``).

``make_client`` is the one helper every test file in this module uses to
build a real ``OpenAICompatibleClient`` wired against a local
``pytest_httpserver`` fixture — the wire-stub-backed integration pattern the
story's Test Plan and the ``testing-standard-pyqt`` skill mandate for
provider adapters. No test in this module monkeypatches or mocks the
``openai`` SDK's internals; every "integration" test in this package makes a
genuine HTTP call to the local stub server.

This module overrides ``pytest_httpserver``'s session-scoped ``make_httpserver``
fixture to construct its underlying ``HTTPServer`` with ``threaded=True``.
Several tests in this package (AC-4's deadline stall, AC-9's inference-test
timeout) deliberately hold one HTTP request open for seconds past the
client's own timeout budget to exercise the finite-deadline invariant. The
upstream default (``threaded=False``) serves one request at a time on a
single worker thread; a still-sleeping stalled-request handler from one test
then blocks the *next* test's unrelated request against the same
session-scoped server, producing cross-test flakiness having nothing to do
with the behaviour under test. ``threaded=True`` gives each request its own
daemon thread so a slow handler in one test can never stall an unrelated
request in the next.
"""

from collections.abc import Callable, Generator
from ssl import SSLContext

import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.domain import (
    ChatMessage,
    ChatRequest,
    ChatRole,
    Iso8601Utc,
    ProviderConfig,
    ProviderType,
    ReasoningEffort,
    ResponseFormat,
)
from ollama_llm_bench.backend.events.protocols import Subscription
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.collaborators import (
    OpenAICompatibleClientCollaborators,
)
from ollama_llm_bench.backend.provider_openai_compatible.models import (
    OpenAICompatibleClientSettings,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore


@pytest.fixture(scope="session")
def make_httpserver(
    httpserver_listen_address: tuple[str | None, int | None],
    httpserver_ssl_context: SSLContext | None,
) -> Generator[HTTPServer]:
    """Override ``pytest_httpserver``'s fixture to run the server ``threaded=True``.

    See the module docstring for why: a slow-handler test in this package
    must never stall an unrelated request from a different test sharing this
    session-scoped server.
    """
    host, port = httpserver_listen_address
    server = HTTPServer(
        host=host or HTTPServer.DEFAULT_LISTEN_HOST,
        port=port or HTTPServer.DEFAULT_LISTEN_PORT,
        ssl_context=httpserver_ssl_context,
        threaded=True,
    )
    server.start()
    yield server
    server.clear()
    if server.is_running():
        server.stop()


__all__: list[str] = [
    "FakeClock",
    "FakeEventBus",
    "make_chat_request",
    "make_client",
    "make_provider_config",
]


class FakeClock:
    """A fully controllable ``Clock`` double; matches sibling modules' fixture shape."""

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
    """An in-memory ``EventBus`` double; unused by this module's own surface but
    required by ``OpenAICompatibleClientCollaborators``' constructor shape."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        """Unused by these tests; returns a no-op cancellable handle."""
        del signal_name, handler, owner

        class _Subscription:
            def cancel(self) -> None:
                return None

        return _Subscription()

    def emit(self, signal_name: str, payload: object) -> None:
        """Record the emission; no subscriber dispatch needed by these tests."""
        self.emitted.append((signal_name, payload))


def make_provider_config(
    *,
    base_url: str | None = None,
    api_key_raw: str | None = "",
    azure_fields: tuple[str | None, str | None, str | None] = (None, None, None),
) -> ProviderConfig:
    """Build a minimal, otherwise-arbitrary ``OPENAI_COMPATIBLE`` ``ProviderConfig``.

    Args:
        base_url: The transport base URL; typically the ``httpserver`` fixture's
            own URL for a wire-stub-backed test.
        api_key_raw: The raw (pre-resolution) API-key field; unused by this
            client's construction directly (``resolved_api_key`` is what the
            client actually receives), included for shape completeness.
        azure_fields: ``(azure_endpoint_raw, azure_deployment_raw,
            azure_api_version_raw)`` — all three populated selects Azure mode.
    """
    azure_endpoint_raw, azure_deployment_raw, azure_api_version_raw = azure_fields
    return ProviderConfig(
        provider_id="11111111-1111-4111-8111-111111111111",
        name="provider",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
        base_url=base_url,
        api_key_raw=api_key_raw,
        azure_endpoint_raw=azure_endpoint_raw,
        azure_deployment_raw=azure_deployment_raw,
        azure_api_version_raw=azure_api_version_raw,
    )


def make_chat_request(
    *,
    model: str = "test-model",
    timeout_ms: int = 5000,
    prompt: str = "hello",
) -> ChatRequest:
    """Build a minimal ``ChatRequest`` for a wire-stub-backed call."""
    return ChatRequest(
        model=model,
        messages=(ChatMessage(role=ChatRole.USER, content=prompt),),
        timeout_ms=timeout_ms,
        reasoning_effort=ReasoningEffort.DEFAULT,
        response_format=ResponseFormat.TEXT,
        echo_tokens_to_log=False,
    )


@pytest.fixture
def fake_clock() -> FakeClock:
    """A fresh ``FakeClock`` starting at monotonic 0."""
    return FakeClock()


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    """A fresh ``FakeEventBus`` with no recorded emissions."""
    return FakeEventBus()


@pytest.fixture
def gate(fake_clock: FakeClock, fake_event_bus: FakeEventBus) -> FakeInferenceActivityStore:
    """A real ``FakeInferenceActivityStore`` sharing this test's clock and event bus."""
    return FakeInferenceActivityStore(clock=fake_clock, event_bus=fake_event_bus)


@pytest.fixture
def make_client(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    fake_event_bus: FakeEventBus,
    gate: FakeInferenceActivityStore,
) -> Callable[..., OpenAICompatibleClient]:
    """Build a real ``OpenAICompatibleClient`` wired against ``httpserver``.

    Returns a factory (not a single instance) so a test can override the
    ``settings``/``base_url``/collaborators shape per case, matching the
    established factory-fixture convention (`testing.md` Fixtures section).
    """

    def _make(
        *,
        base_url: str | None = None,
        settings: OpenAICompatibleClientSettings | None = None,
        config: ProviderConfig | None = None,
        resolved_api_key: str = "",
    ) -> OpenAICompatibleClient:
        effective_config = config or make_provider_config(
            base_url=base_url or httpserver.url_for("/")
        )
        collaborators = OpenAICompatibleClientCollaborators(
            clock=fake_clock, event_bus=fake_event_bus, inference_activity_store=gate
        )
        return OpenAICompatibleClient(
            config=effective_config,
            resolved_api_key=resolved_api_key,
            collaborators=collaborators,
            settings=settings if settings is not None else OpenAICompatibleClientSettings(),
        )

    return _make
