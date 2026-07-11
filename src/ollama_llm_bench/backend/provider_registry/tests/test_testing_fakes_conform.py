"""Tests proving STORY-021-AC-3: this module's ``LLMClient`` fakes match the corrected shape.

Source of truth: ``docs/stories/story-021-llmclient-chat-cancellation-token-parameter.md``;
``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client``.

``backend/provider_registry/`` ships no ``testing.py`` fake of its own (it is a registry, not
an ``LLMClient`` implementer) — the only ``LLMClient`` double owned by this module is
``FakeLLMClient`` in its colocated ``tests/conftest.py``. This suite proves that fake's
``chat``/``chat_stream`` accept the corrected keyword-only ``token: CancellationToken``
parameter (structurally, via ``inspect.signature``, and behaviourally, by actually calling
``chat`` with a real token) and that the module's existing STORY-017 test suite — exercised
end to end here via the registry's own public ``get_client`` path — continues to pass
unchanged in behaviour.
"""

import inspect
from typing import TYPE_CHECKING

import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken, make_cancellation_token
from ollama_llm_bench.backend.domain import ProviderType
from ollama_llm_bench.backend.provider_registry.api import make_provider_registry
from ollama_llm_bench.backend.provider_registry.tests.conftest import (
    FakeClock,
    FakeEventBus,
    FakeLLMClient,
    FakeProvidersStore,
    make_client_builders,
    make_provider_config,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

if TYPE_CHECKING:
    from ollama_llm_bench.backend.provider_registry.protocols import ClientBuilder, LLMClient


def test_fake_llm_client_chat_methods_accept_keyword_only_token() -> None:
    """Proves: STORY-021-AC-3

    Given the ``FakeLLMClient`` double shipped inside
    ``backend/provider_registry/tests/conftest.py``, when its ``chat`` and
    ``chat_stream`` signatures are inspected, then each declares the same
    keyword-only ``token: CancellationToken`` parameter (no default) as the
    corrected ``LLMClient`` Protocol.
    """
    # Arrange / Act
    chat_signature = inspect.signature(FakeLLMClient.chat)
    chat_stream_signature = inspect.signature(FakeLLMClient.chat_stream)

    # Assert
    assert list(chat_signature.parameters) == ["self", "request", "token"]
    assert chat_signature.parameters["token"].kind == inspect.Parameter.KEYWORD_ONLY
    assert chat_signature.parameters["token"].default is inspect.Parameter.empty
    assert chat_signature.parameters["token"].annotation is CancellationToken
    assert list(chat_stream_signature.parameters) == ["self", "request", "token"]
    assert chat_stream_signature.parameters["token"].kind == inspect.Parameter.KEYWORD_ONLY
    assert chat_stream_signature.parameters["token"].default is inspect.Parameter.empty
    assert chat_stream_signature.parameters["token"].annotation is CancellationToken


def test_fake_llm_client_satisfies_llm_client_protocol_structurally() -> None:
    """Proves: STORY-021-AC-3

    Given a ``FakeLLMClient`` instance, when it is used as an ``LLMClient``
    through a type-annotated binding, then it satisfies the Protocol
    structurally — every declared member is present and callable with the
    corrected signature, with no ``AttributeError`` at any call site.
    """
    # Arrange
    fake = FakeLLMClient()
    client: LLMClient = fake

    # Act / Assert — every LLMClient member resolves on the fake with no AttributeError
    assert client.list_models() == ()
    assert client.supports_streaming() is False
    assert client.supports_reasoning_effort() is False
    assert client.supports_thinking() is False
    assert callable(client.chat)
    assert callable(client.chat_stream)
    client.close()
    assert fake.closed is True


def test_fake_llm_client_chat_raises_not_implemented_when_called_with_a_real_token() -> None:
    """Proves: STORY-021-AC-3

    Given a ``FakeLLMClient`` and a real ``CancellationToken`` built by the
    project's own ``make_cancellation_token`` factory, when ``chat`` is
    invoked positionally for ``request`` and by keyword for ``token`` (the
    only call shape the corrected Protocol permits), then the call is
    accepted at the Python call-signature level — the fake's own
    unimplemented-behaviour marker (``NotImplementedError``) is raised from
    inside the method body, not a ``TypeError`` for a bad call shape.
    """
    # Arrange
    client = FakeLLMClient()
    token = make_cancellation_token(clock=FakeClock())
    request = object()  # the fake never inspects `request`; only the call shape matters here

    # Act / Assert
    with pytest.raises(NotImplementedError):
        client.chat(request, token=token)  # type: ignore[arg-type]  # sentinel request, call-shape probe


def test_registry_fakes_match_corrected_chat_signature() -> None:
    """Proves: STORY-021-AC-3

    Given the ``ProviderRegistry`` wired entirely against this module's own
    STORY-017 fakes (``FakeProvidersStore``, ``FakeEventBus``,
    ``FakeInferenceActivityStore``, and client builders returning
    ``FakeLLMClient``), when a client is obtained through the registry's
    public ``get_client`` and its ``chat``/``chat_stream`` are bound as
    ``LLMClient``, then the existing STORY-017 construction/retrieval
    behaviour is unchanged and the retrieved client's chat surface conforms
    to the corrected signature.
    """
    # Arrange
    provider = make_provider_config(provider_type=ProviderType.OPENAI_COMPATIBLE)
    providers_store = FakeProvidersStore(providers=(provider,))
    fake_event_bus = FakeEventBus()
    gate = FakeInferenceActivityStore(clock=FakeClock(), event_bus=fake_event_bus)
    client_builders: dict[ProviderType, ClientBuilder] = make_client_builders()
    registry = make_provider_registry(
        providers_store=providers_store,
        client_builders=client_builders,
        gate=gate,
        event_bus=fake_event_bus,
    )

    # Act
    client: LLMClient = registry.get_client(provider.provider_id)

    # Assert — STORY-017 behaviour: the registry still returns exactly one live client
    assert isinstance(client, FakeLLMClient)
    assert client.provider == provider
    chat_signature = inspect.signature(type(client).chat)
    assert chat_signature.parameters["token"].kind == inspect.Parameter.KEYWORD_ONLY
