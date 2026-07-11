"""Shared fixtures for ``backend/provider_gemini/`` tests.

``FakeClock`` and ``FakeEventBus`` mirror ``provider_anthropic/tests/conftest.py``
and ``provider_openai_compatible/tests/conftest.py`` exactly, so a reader
familiar with one provider adapter's tests recognises the other's doubles
immediately. ``FakeInferenceActivityStore`` is imported, not reinvented, from
``ollama_llm_bench.backend.stores.inference_activity.testing`` per the
project's established convention.

``make_client`` is the one helper every test file in this module uses to
build a real ``GeminiClient`` wired against a local ``pytest_httpserver``
fixture — the wire-stub-backed integration pattern the story's Test Plan and
the ``testing-standard-pyqt`` skill mandate for provider adapters. No test in
this module monkeypatches or mocks the ``google-genai`` SDK's internals
(except the one deliberate ``AttributeError``-fallback case in
``test_probe_health.py``, which patches ``client.models`` itself, not SDK
internals); every "integration" test in this package makes a genuine HTTP
call to the local stub server, reached via ``genai.Client(http_options=
types.HttpOptions(base_url=...))`` — confirmed to work in plain API-key mode
by reading the installed SDK's ``_base_url.py`` directly.

This module overrides ``pytest_httpserver``'s session-scoped ``make_httpserver``
fixture to construct its underlying ``HTTPServer`` with ``threaded=True`` —
mirrors the two sibling adapters' own override and rationale: a test
deliberately stalling a handler past a client timeout must never block an
unrelated request from a different test sharing this session-scoped server.

The wire-format helpers assemble Gemini's actual streaming wire shape:
``data: {...}\\n\\n`` lines (SSE-shaped, no ``[DONE]`` sentinel — the stream
simply ends when the connection closes, like Anthropic's, unlike OpenAI's),
each line a JSON object shaped like one ``GenerateContentResponse`` with
**camelCase** field names (``candidates``, ``content``, ``parts``, ``text``,
``thought``, ``usageMetadata``, ``promptTokenCount``, ``candidatesTokenCount``)
— confirmed against the installed SDK's ``_common.BaseModel``, which uses
``alias_generator=alias_generators.to_camel``.
"""

from collections.abc import Callable, Generator
import json
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
from ollama_llm_bench.backend.provider_gemini._internal.client_impl import GeminiClient
from ollama_llm_bench.backend.provider_gemini._internal.collaborators import (
    GeminiClientCollaborators,
)
from ollama_llm_bench.backend.provider_gemini.models import GeminiClientSettings
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
    "gemini_reasoning_and_text_stream_body",
    "gemini_success_stream_body",
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
    required by ``GeminiClientCollaborators``' constructor shape."""

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
    """Build a minimal, otherwise-arbitrary ``GEMINI`` ``ProviderConfig``.

    Args:
        base_url: The transport base URL; typically the ``httpserver``
            fixture's own URL for a wire-stub-backed test.
        api_key_raw: The raw (pre-resolution) API-key field; unused by this
            client's construction directly (``resolved_api_key`` is what the
            client actually receives), included for shape completeness.
    """
    return ProviderConfig(
        provider_id="33333333-3333-4333-8333-333333333333",
        name="gemini-provider",
        provider_type=ProviderType.GEMINI,
        enabled=True,
        base_url=base_url,
        api_key_raw=api_key_raw,
    )


def make_chat_request(
    *,
    model: str = "gemini-test-model",
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


def _sse_chunk(payload: dict[str, object]) -> str:
    """Assemble one Gemini-shaped ``data: <json>\\n\\n`` SSE frame."""
    return f"data: {json.dumps(payload)}\n\n"


def gemini_success_stream_body(
    *, text: str = "hi", prompt_tokens: int = 10, candidates_tokens: int = 3
) -> str:
    """Assemble a canned success SSE stream: one text-carrying chunk with usage.

    Mirrors real Gemini streaming shape: ``usageMetadata`` on the same
    (here, only) chunk carries both ``promptTokenCount`` and
    ``candidatesTokenCount`` — confirmed against the installed SDK's
    camelCase field aliasing.
    """
    return _sse_chunk(
        {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": text}]},
                    "index": 0,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": prompt_tokens,
                "candidatesTokenCount": candidates_tokens,
            },
        }
    )


def gemini_reasoning_and_text_stream_body(
    *, reasoning: str = "let me think", text: str = "the answer"
) -> str:
    """Assemble a canned SSE stream carrying a reasoning part then a text part.

    Mirrors real Gemini thinking-model output ordering: a part with
    ``thought: true`` streams first, then the plain text part (§6.9) — see
    STORY-020-AC-3.
    """
    return _sse_chunk(
        {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": reasoning, "thought": True},
                            {"text": text},
                        ],
                    },
                    "index": 0,
                }
            ],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 4},
        }
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
) -> Callable[..., GeminiClient]:
    """Build a real ``GeminiClient`` wired against ``httpserver``.

    Returns a factory (not a single instance) so a test can override the
    ``settings``/``base_url``/collaborators shape per case, matching the
    established factory-fixture convention (`testing.md` Fixtures section).
    """

    def _make(
        *,
        base_url: str | None = None,
        settings: GeminiClientSettings | None = None,
        config: ProviderConfig | None = None,
        resolved_api_key: str = "gemini-test-key",
    ) -> GeminiClient:
        effective_config = config or make_provider_config(
            base_url=base_url or httpserver.url_for("/")
        )
        collaborators = GeminiClientCollaborators(
            clock=fake_clock, event_bus=fake_event_bus, inference_activity_store=gate
        )
        return GeminiClient(
            config=effective_config,
            resolved_api_key=resolved_api_key,
            collaborators=collaborators,
            settings=settings if settings is not None else GeminiClientSettings(),
        )

    return _make
