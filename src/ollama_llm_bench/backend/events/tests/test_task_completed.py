"""Tests proving ``TaskCompletedEvent``'s verdict/no-numeric-score acceptance criterion.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-Q_event_payload_schemas.md``
§4.5 (``TaskCompletedEvent``) and §1 ("No judge score" convention).
"""

import typing

from ollama_llm_bench.backend.domain import ResultStatus, Verdict
from ollama_llm_bench.backend.events import TaskCompletedEvent, models as events_models

# Field names carrying a numeric quality/score value are forbidden anywhere in the module
# except `cosine_similarity` — the one documented numeric quality value (08-Q §1).
_FORBIDDEN_SCORE_FIELD_NAMES = frozenset(
    {"judge_score", "score", "quality_score", "grade", "rating"}
)


def test_task_completed_event_verdict_field_and_no_numeric_score() -> None:
    """Proves: STORY-003-AC-4

    Given the ``TaskCompletedEvent`` payload Struct,
    when its declared fields are inspected,
    then it declares ``result_status: ResultStatus`` and an optional
    ``verdict: Verdict | None`` field, constructing it with ``verdict`` set while
    ``result_status != ResultStatus.COMPLETED`` is representable (the Struct itself does
    not forbid it), and no payload Struct anywhere in ``backend.events`` declares a
    numeric judge-score field.
    """
    # Arrange
    declared_fields = typing.get_type_hints(TaskCompletedEvent)

    # Act — construct with a non-COMPLETED status but a verdict set; the pipeline (not the
    # Struct) is responsible for the invariant, so this must not raise.
    representable_instance = TaskCompletedEvent(
        run_id=1,
        result_id=1,
        task_id="task-1",
        provider_id="a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d",
        model_name="test-model",
        result_status=ResultStatus.FAILED_INFERENCE,
        verdict=Verdict.PASS,
    )

    # Assert
    assert declared_fields["result_status"] is ResultStatus
    assert declared_fields["verdict"] == (Verdict | None)
    assert representable_instance.result_status == ResultStatus.FAILED_INFERENCE
    assert representable_instance.verdict == Verdict.PASS
    for payload_type_name in events_models.__all__:
        payload_type = getattr(events_models, payload_type_name)
        if not (isinstance(payload_type, type) and hasattr(payload_type, "__struct_fields__")):
            continue
        assert _FORBIDDEN_SCORE_FIELD_NAMES.isdisjoint(payload_type.__struct_fields__)
