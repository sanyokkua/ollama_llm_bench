"""Shared fixtures for ``ui/settings_dialog/tests/`` (STORY-066).

Mirrors ``ui/common_dialogs/tests/test_generate_analysis_dialog.py``'s locally-
declared, in-process synchronous ``EventBus`` test double.
"""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.events import Subscription

PROVIDER_A = ProviderConfig(
    provider_id="aaaaaaaa-1111-4111-8111-111111111111",
    name="Ollama Local",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    base_url="http://localhost:11434/v1",
    enabled=True,
)
PROVIDER_B = ProviderConfig(
    provider_id="bbbbbbbb-2222-4222-8222-222222222222",
    name="Anthropic",
    provider_type=ProviderType.ANTHROPIC,
    api_key_raw="ANTHROPIC_API_KEY",
    enabled=True,
)


class FakeSubscription:
    """A cancellable ``Subscription`` test double."""

    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn

    def cancel(self) -> None:
        self._cancel_fn()


class FakeEventBus:
    """A synchronous, in-process ``EventBus`` test double (immediate delivery)."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[object], None]]] = {}

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        self._handlers.setdefault(signal_name, []).append(handler)

        def _cancel() -> None:
            self._handlers[signal_name].remove(handler)

        return FakeSubscription(_cancel)

    def emit(self, signal_name: str, payload: object) -> None:
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    return FakeEventBus()
