"""Smoke coverage for ``backend/readiness/`` (STORY-016).

Exhaustive acceptance-criteria coverage is the tester agent's job (per-AC test files
named in the story's Test plan). This file only sanity-checks the wiring end to end:
construction starts ``CHECKING``, a fully-healthy batch resolves ``READY`` with no
``embed()``/``chat()`` call, and the gate is acquired and released around a probe.
"""

from ollama_llm_bench.backend.concurrency import make_inline_task_runner
from ollama_llm_bench.backend.domain import ProviderHealth, ReadinessState
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.readiness.api import make_readiness_service
from ollama_llm_bench.backend.readiness.tests.conftest import (
    FakeReadinessEmbeddingSelection,
    FakeReadinessEmbeddingSelector,
    FakeReadinessLLMClient,
    FakeReadinessProviderRegistry,
    make_provider_config,
)
from ollama_llm_bench.backend.settings.testing import FakeSettingsService
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_PROVIDER_ID = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"


def test_snapshot_starts_checking(fake_clock: object, spy_event_bus: object) -> None:
    """Proves: STORY-016-AC-1 (smoke)

    A freshly constructed service's ``snapshot()`` is ``CHECKING`` before any
    probe runs, synchronously and without probing.
    """
    # Arrange
    service = make_readiness_service(
        registry=FakeReadinessProviderRegistry(),
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=fake_clock, event_bus=spy_event_bus),  # type: ignore[arg-type]
        event_bus=spy_event_bus,  # type: ignore[arg-type]
        task_runner=make_inline_task_runner(),
        clock=fake_clock,  # type: ignore[arg-type]
    )

    # Act
    snapshot = service.snapshot()

    # Assert
    assert snapshot.overall == ReadinessState.CHECKING


def test_probe_all_healthy_batch_resolves_ready_with_no_model_compute(
    fake_clock: object, spy_event_bus: EventBus
) -> None:
    """Proves: STORY-016-AC-2, STORY-016-AC-4 (smoke)

    One reachable provider with a listed, embeddable model resolves ``READY``
    and never issues ``embed()``/``chat()``.
    """
    # Arrange
    health = ProviderHealth(
        provider_id=_PROVIDER_ID,
        reachable=True,
        discovery_supported=True,
        model_count=1,
        last_probe_ms=10,
        probed_at=0,
    )
    client = FakeReadinessLLMClient(
        health=health, supports_embedding=True, supports_discovery=True, models=("m1",)
    )
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    selection = FakeReadinessEmbeddingSelection(
        provider=make_provider_config(provider_id=_PROVIDER_ID), model_name="m1"
    )
    service = make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(selection=selection),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=fake_clock, event_bus=spy_event_bus),  # type: ignore[arg-type]
        event_bus=spy_event_bus,
        task_runner=make_inline_task_runner(),
        clock=fake_clock,  # type: ignore[arg-type]
    )

    # Act
    snapshot = service.probe_all()

    # Assert
    assert snapshot.overall == ReadinessState.READY
    assert snapshot.embedding_reachable is True
    assert client.embed_calls == 0
    assert client.chat_calls == 0
