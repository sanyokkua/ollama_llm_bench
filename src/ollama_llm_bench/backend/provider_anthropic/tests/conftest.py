"""Shared fixtures for ``backend/provider_anthropic/`` tests.

``FakeClock`` and ``FakeEventBus`` mirror
``provider_openai_compatible/tests/conftest.py`` exactly, so a reader familiar
with one provider adapter's tests recognises the other's doubles immediately.
``FakeInferenceActivityStore`` is imported, not reinvented, from
``ollama_llm_bench.backend.stores.inference_activity.testing`` per the
project's established convention.

``make_client`` is the one helper every test file in this module uses to
build a real ``AnthropicClient`` wired against a local ``pytest_httpserver``
fixture — the wire-stub-backed integration pattern the story's Test Plan and
the ``testing-standard-pyqt`` skill mandate for provider adapters. No test in
this module monkeypatches or mocks the ``anthropic`` SDK's internals; every
"integration" test in this package makes a genuine HTTP call to the local
stub server, which answers at the real ``anthropic`` SDK's ``/v1/messages``
path.

This module overrides ``pytest_httpserver``'s session-scoped ``make_httpserver``
fixture to construct its underlying ``HTTPServer`` with ``threaded=True`` —
mirrors ``provider_openai_compatible/tests/conftest.py``'s own override and
rationale: a test deliberately stalling a handler past a client timeout must
never block an unrelated request from a different test sharing this
session-scoped server.

The SSE helpers (``sse_event``, ``anthropic_success_stream_body``,
``anthropic_thinking_and_text_stream_body``) assemble Anthropic's
``event: <type>\\ndata: <json>\\n\\n`` wire format, distinct from OpenAI's
bare ``data: <json>\\n\\n`` lines with a ``[DONE]`` sentinel — the Anthropic
stream simply ends when the connection closes after ``message_stop``.
"""

from collections.abc import Callable, Generator
import json
from ssl import SSLContext

import httpx
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
from ollama_llm_bench.backend.provider_anthropic._internal.client_impl import AnthropicClient
from ollama_llm_bench.backend.provider_anthropic._internal.collaborators import (
    AnthropicClientCollaborators,
)
from ollama_llm_bench.backend.provider_anthropic.models import AnthropicClientSettings
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
    "anthropic_success_stream_body",
    "anthropic_thinking_and_text_stream_body",
    "make_chat_request",
    "make_client",
    "make_provider_config",
    "sse_event",
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
    required by ``AnthropicClientCollaborators``' constructor shape."""

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
    *, base_url: str | None = None, api_key_raw: str | None = ""
) -> ProviderConfig:
    """Build a minimal, otherwise-arbitrary ``ANTHROPIC`` ``ProviderConfig``.

    Args:
        base_url: The transport base URL; typically the ``httpserver``
            fixture's own URL for a wire-stub-backed test.
        api_key_raw: The raw (pre-resolution) API-key field; unused by this
            client's construction directly (``resolved_api_key`` is what the
            client actually receives), included for shape completeness.
    """
    return ProviderConfig(
        provider_id="22222222-2222-4222-8222-222222222222",
        name="anthropic-provider",
        provider_type=ProviderType.ANTHROPIC,
        enabled=True,
        base_url=base_url,
        api_key_raw=api_key_raw,
    )


def make_chat_request(
    *,
    model: str = "claude-test-model",
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


def sse_event(event_type: str, data: dict[str, object]) -> str:
    """Assemble one Anthropic-shaped ``event: <type>\\ndata: <json>\\n\\n`` frame."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def anthropic_success_stream_body(
    *, text: str = "hi", input_tokens: int = 10, output_tokens: int = 3
) -> str:
    """Assemble a canned success SSE stream: usage + one text delta + terminal events."""
    return "".join(
        [
            sse_event(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-test-model",
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": input_tokens, "output_tokens": 0},
                    },
                },
            ),
            sse_event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text},
                },
            ),
            sse_event("content_block_stop", {"type": "content_block_stop", "index": 0}),
            sse_event(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": output_tokens},
                },
            ),
            sse_event("message_stop", {"type": "message_stop"}),
        ]
    )


def anthropic_thinking_and_text_stream_body(
    *, thinking: str = "let me think", text: str = "the answer"
) -> str:
    """Assemble a canned SSE stream carrying a ``thinking`` block then a ``text`` block.

    Mirrors real Anthropic extended-thinking output ordering: the
    ``thinking`` content block (index 0) streams first, then the ``text``
    content block (index 1) — see AC-2.
    """
    return "".join(
        [
            sse_event(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-test-model",
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 5, "output_tokens": 0},
                    },
                },
            ),
            sse_event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "thinking", "thinking": ""},
                },
            ),
            sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "thinking_delta", "thinking": thinking},
                },
            ),
            sse_event("content_block_stop", {"type": "content_block_stop", "index": 0}),
            sse_event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "text_delta", "text": text},
                },
            ),
            sse_event("content_block_stop", {"type": "content_block_stop", "index": 1}),
            sse_event(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 4},
                },
            ),
            sse_event("message_stop", {"type": "message_stop"}),
        ]
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
def http_client() -> Generator[httpx.Client]:
    """A real ``httpx.Client``, mirroring the one shared instance ``compose.py``
    constructs in production (STORY-077, Gap 1)."""
    with httpx.Client() as client:
        yield client


@pytest.fixture
def make_client(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    fake_event_bus: FakeEventBus,
    gate: FakeInferenceActivityStore,
    http_client: httpx.Client,
) -> Callable[..., AnthropicClient]:
    """Build a real ``AnthropicClient`` wired against ``httpserver``.

    Returns a factory (not a single instance) so a test can override the
    ``settings``/``base_url``/collaborators shape per case, matching the
    established factory-fixture convention (`testing.md` Fixtures section).
    """

    def _make(
        *,
        base_url: str | None = None,
        settings: AnthropicClientSettings | None = None,
        config: ProviderConfig | None = None,
        resolved_api_key: str = "sk-ant-test-key",
    ) -> AnthropicClient:
        effective_config = config or make_provider_config(
            base_url=base_url or httpserver.url_for("/")
        )
        collaborators = AnthropicClientCollaborators(
            clock=fake_clock,
            event_bus=fake_event_bus,
            inference_activity_store=gate,
            http_client=http_client,
        )
        return AnthropicClient(
            config=effective_config,
            resolved_api_key=resolved_api_key,
            collaborators=collaborators,
            settings=settings if settings is not None else AnthropicClientSettings(),
        )

    return _make
