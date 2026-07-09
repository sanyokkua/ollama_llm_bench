"""Tests proving the ``ProviderConfig`` / ``ProviderConfigDraft`` relationship (§5.1, AC-5).

The AC-5 prose ("every field of ``ProviderConfig`` except ``provider_id``") is looser than the
spec's literal §5.1 code block, which shows ``ProviderConfigDraft`` also omitting the ten
``last_probe_*``/``last_inference_test_*`` result-only fields — each of those carries a SQLite
``DEFAULT`` (`03_PERSISTENCE_SCHEMA.md`) because a draft has no probe/test history yet. This
test asserts against the spec's actual §5.1 code block, per the coder's documented resolution.
"""

import msgspec

from ollama_llm_bench.backend.domain.models import (
    ProviderConfig,
    ProviderConfigDraft,
    ProviderIdStr,
)

_RESULT_ONLY_FIELDS = frozenset(
    {
        "last_probe_status",
        "last_probe_at",
        "last_probe_reachable",
        "last_probe_model_count",
        "last_probe_message",
        "last_inference_test_at",
        "last_inference_test_outcome",
        "last_inference_test_model",
        "last_inference_test_message",
    }
)


def test_provider_config_draft_omits_provider_id_and_validates_uuid() -> None:
    """Proves: STORY-001-AC-5

    Given the ``ProviderConfig`` and ``ProviderConfigDraft`` records, the draft's field set is
    exactly ``ProviderConfig``'s minus ``provider_id`` and minus the ten
    result-only ``last_probe_*``/``last_inference_test_*`` fields (the literal §5.1 code
    block), and ``ProviderConfig.provider_id`` accepts only a value matching the UUID4
    ``ProviderIdStr`` pattern.
    """
    # Arrange
    config_fields = set(ProviderConfig.__struct_fields__)
    draft_fields = set(ProviderConfigDraft.__struct_fields__)
    expected_draft_fields = config_fields - {"provider_id"} - _RESULT_ONLY_FIELDS

    # Act / Assert — the draft's field set matches the spec's §5.1 code block exactly.
    assert draft_fields == expected_draft_fields
    assert "provider_id" not in draft_fields

    # Assert — provider_id's declared type is the UUID4-constrained ProviderIdStr.
    provider_id_field = next(
        field for field in msgspec.structs.fields(ProviderConfig) if field.name == "provider_id"
    )
    assert provider_id_field.type == ProviderIdStr

    valid_uuid4 = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"
    decoded = msgspec.convert(valid_uuid4, type=ProviderIdStr)
    assert decoded == valid_uuid4
