"""Proves STORY-026-AC-4 and STORY-026-AC-5 — the model capability service (§4.8)."""

import pytest

from ollama_llm_bench.backend.domain import (
    CapabilitySource,
    ModelCapability,
    ModelCapabilityRecord,
)
from ollama_llm_bench.backend.model_helpers import (
    CapabilityObservation,
    make_model_capability_service,
)
from ollama_llm_bench.backend.persistence.model_capabilities.testing import (
    FakeModelCapabilitiesStore,
)

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "qwen3:8b"


class _FakeClock:
    """A fixed-time double satisfying the Clock Protocol for this test module."""

    def __init__(self, *, fixed_now: str = "2026-01-01T00:00:00Z") -> None:
        self._fixed_now = fixed_now

    def now_utc(self) -> str:
        """Return the fixed instant every call in this test module observes."""
        return self._fixed_now

    def monotonic_ms(self) -> int:
        """Return a constant monotonic counter; unused by this service."""
        return 0


class _UpsertCountingStore(FakeModelCapabilitiesStore):
    """A thin spy wrapper counting ``upsert_model_capability`` calls."""

    def __init__(self) -> None:
        super().__init__()
        self.upsert_calls: list[ModelCapabilityRecord] = []

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        """Record the call, then delegate to the real fake-store behaviour."""
        self.upsert_calls.append(record)
        super().upsert_model_capability(record)


def test_get_capabilities_and_streaming_reflect_store() -> None:
    """Proves: STORY-026-AC-4

    get_capabilities returns exactly the records the injected
    ModelCapabilitiesStore reports for a (provider_id, model_name) pair, and
    is_streaming_supported returns True exactly when the streaming record's
    supported value is 1.
    """
    streaming_supported = ModelCapabilityRecord(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        capability=ModelCapability.STREAMING,
        supported=1,
        last_observed_at="2026-01-01T00:00:00Z",
        observed_via=CapabilitySource.PROBE,
    )
    store = FakeModelCapabilitiesStore(records=(streaming_supported,))
    service = make_model_capability_service(store=store, clock=_FakeClock())

    records = service.get_capabilities(_PROVIDER_ID, _MODEL_NAME)

    assert records == (streaming_supported,)
    assert service.is_streaming_supported(_PROVIDER_ID, _MODEL_NAME) is True


@pytest.mark.parametrize(
    "supported_value",
    [0, -1],
    ids=["not_supported", "unknown"],
)
def test_is_streaming_supported_false_for_non_supported_values(supported_value: int) -> None:
    """Proves: STORY-026-AC-4

    is_streaming_supported returns False when the streaming record's supported
    value is 0 (not supported) or -1 (unknown).
    """
    record = ModelCapabilityRecord(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        capability=ModelCapability.STREAMING,
        supported=supported_value,
        last_observed_at="2026-01-01T00:00:00Z",
        observed_via=CapabilitySource.PROBE,
    )
    store = FakeModelCapabilitiesStore(records=(record,))
    service = make_model_capability_service(store=store, clock=_FakeClock())

    assert service.is_streaming_supported(_PROVIDER_ID, _MODEL_NAME) is False


def test_is_streaming_supported_ignores_non_streaming_records() -> None:
    """Proves: STORY-026-AC-4

    is_streaming_supported inspects only the STREAMING capability record for the
    pair and ignores other cached capabilities (e.g. THINKING), even when the
    non-streaming record's supported value is 1.
    """
    thinking_supported = ModelCapabilityRecord(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        capability=ModelCapability.THINKING,
        supported=1,
        last_observed_at="2026-01-01T00:00:00Z",
        observed_via=CapabilitySource.PROBE,
    )
    streaming_not_supported = ModelCapabilityRecord(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        capability=ModelCapability.STREAMING,
        supported=0,
        last_observed_at="2026-01-01T00:00:00Z",
        observed_via=CapabilitySource.PROBE,
    )
    store = FakeModelCapabilitiesStore(records=(thinking_supported, streaming_not_supported))
    service = make_model_capability_service(store=store, clock=_FakeClock())

    assert service.is_streaming_supported(_PROVIDER_ID, _MODEL_NAME) is False


def test_is_streaming_supported_false_when_no_record_exists() -> None:
    """Proves: STORY-026-AC-4

    is_streaming_supported returns False when no streaming capability record
    exists at all for the (provider_id, model_name) pair.
    """
    store = FakeModelCapabilitiesStore()
    service = make_model_capability_service(store=store, clock=_FakeClock())

    assert service.is_streaming_supported(_PROVIDER_ID, "unknown-model") is False


def test_record_capability_writes_one_upsert_through_store() -> None:
    """Proves: STORY-026-AC-5

    record_capability writes exactly one upsert through the ModelCapabilitiesStore
    for the (provider_id, model_name, capability) triple carrying the given
    CapabilitySource, and a subsequent get_capabilities for the pair reflects the
    recorded value.
    """
    store = _UpsertCountingStore()
    service = make_model_capability_service(store=store, clock=_FakeClock())

    service.record_capability(
        _PROVIDER_ID,
        _MODEL_NAME,
        CapabilityObservation(
            capability=ModelCapability.STREAMING,
            supported=1,
            source=CapabilitySource.INFERENCE,
            detail="observed mid-run",
        ),
    )

    assert len(store.upsert_calls) == 1
    assert store.upsert_calls[0].provider_id == _PROVIDER_ID
    assert store.upsert_calls[0].model_name == _MODEL_NAME
    assert store.upsert_calls[0].capability is ModelCapability.STREAMING
    assert store.upsert_calls[0].observed_via is CapabilitySource.INFERENCE

    records = service.get_capabilities(_PROVIDER_ID, _MODEL_NAME)
    assert len(records) == 1
    assert records[0].supported == 1
    assert records[0].detail == "observed mid-run"
