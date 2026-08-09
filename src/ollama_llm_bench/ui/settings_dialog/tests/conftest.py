"""Shared fixtures for ``ui/settings_dialog/tests/`` (STORY-066, extended by
STORY-067).

Mirrors ``ui/common_dialogs/tests/test_generate_analysis_dialog.py``'s locally-
declared, in-process synchronous ``EventBus`` test double.
"""

from collections.abc import Callable
import uuid

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
        self._emitted_signal_names: list[str] = []

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        # Mirrors QtEventBusDeliverer's icontract precondition (08-J §2) so this tier can
        # never again accept what the real bus crashes on -- see STORY-118.
        if owner is None:
            message = "owner is required — a subscription with no owner is a programming error"
            raise AssertionError(message)
        self._handlers.setdefault(signal_name, []).append(handler)

        def _cancel() -> None:
            self._handlers[signal_name].remove(handler)

        return FakeSubscription(_cancel)

    def emit(self, signal_name: str, payload: object) -> None:
        self._emitted_signal_names.append(signal_name)
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)

    def emitted_signal_names(self) -> list[str]:
        """Test helper (STORY-067): every signal name passed to ``emit``, in order."""
        return list(self._emitted_signal_names)


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def provider_config_factory() -> Callable[..., ProviderConfig]:
    """Build a ``ProviderConfig`` with sane defaults, overridable per test
    (STORY-067) -- a lighter-weight alternative to hand-writing a full
    ``ProviderConfig`` when a test only cares about one or two fields (e.g.
    ``name``, ``api_key_raw``)."""

    def _make(**overrides: object) -> ProviderConfig:
        defaults: dict[str, object] = {
            "provider_id": str(uuid.uuid4()),
            "name": "Test Provider",
            "provider_type": ProviderType.OPENAI_COMPATIBLE,
            "base_url": "http://localhost:11434/v1",
            "enabled": True,
        }
        defaults.update(overrides)
        return ProviderConfig(**defaults)  # type: ignore[arg-type]  # kwargs assembled dynamically from a typed-default dict

    return _make
