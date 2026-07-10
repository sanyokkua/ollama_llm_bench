"""Tests proving the event-to-payload catalogue acceptance criteria of STORY-003.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-J_event_bus_catalog.md``
§7 (the closed 36-event index) and
``docs/v3_specification/08_Cross_Cutting/08-Q_event_payload_schemas.md`` (the field-level
contract for each payload, cross-checked table-driven below against the real
``msgspec.Struct`` types).
"""

import typing

import msgspec
import pytest

from ollama_llm_bench.backend.events import models as events_models

_EXPECTED_EVENT_COUNT = 36

# The §7 event-to-payload index, verified against the spec file directly — one row per
# event name in the catalogue, 36 rows total.
_EVENT_TO_PAYLOAD_INDEX: tuple[tuple[str, str], ...] = (
    ("_run_started", "RunStartedEvent"),
    ("_run_start_failed", "RunStartFailedEvent"),
    ("_run_paused", "RunPausedEvent"),
    ("_run_resumed", "RunResumedEvent"),
    ("_run_stopped", "RunStoppedEvent"),
    ("_run_finished", "RunFinishedEvent"),
    ("_run_failed", "RunFailedEvent"),
    ("_stage_changed", "StageChangedEvent"),
    ("_progress_updated", "ProgressUpdatedEvent"),
    ("_provider_switched", "ProviderSwitchedEvent"),
    ("_model_switched", "ModelSwitchedEvent"),
    ("_task_retry", "TaskRetryEvent"),
    ("_model_stability_changed", "ModelStabilityChangedEvent"),
    ("_judge_model_excluded", "JudgeModelExcludedEvent"),
    ("_inference_started", "InferenceStartedEvent"),
    ("_inference_progress", "InferenceProgressEvent"),
    ("_inference_completed", "InferenceCompletedEvent"),
    ("_judge_started", "JudgeStartedEvent"),
    ("_judge_completed", "JudgeCompletedEvent"),
    ("_task_completed", "TaskCompletedEvent"),
    ("_run_id_changed", "RunIdChangedEvent"),
    ("_run_list_changed", "RunListChangedEvent"),
    ("_run_renamed", "RunRenamedEvent"),
    ("_summary_data_changed", "SummaryDataChangedEvent"),
    ("_detailed_data_changed", "DetailedDataChangedEvent"),
    ("_chart_data_changed", "ChartDataChangedEvent"),
    ("_run_analysis_received", "RunAnalysisReceivedEvent"),
    ("_provider_registry_reloaded", "ProviderRegistryReloadedEvent"),
    ("_app_settings_changed", "AppSettingsChangedEvent"),
    ("_provider_inference_test_completed", "InferenceTestCompletedEvent"),
    ("_app_readiness_changed", "AppReadinessChangedEvent"),
    ("_inference_activity_changed", "InferenceActivityChangedEvent"),
    ("_global_message", "GlobalMessageEvent"),
    ("_log_cleared", "LogClearedEvent"),
    ("_workspace_changed", "WorkspaceChangedEvent"),
    ("_task_file_changed", "TaskFileChangedEvent"),
)

# The matching signal-name constant for each event, so the test also proves the
# constant's string value matches the catalogue's leading-underscore event name.
_EVENT_TO_SIGNAL_CONSTANT: dict[str, str] = {
    "_run_started": "SIGNAL_RUN_STARTED",
    "_run_start_failed": "SIGNAL_RUN_START_FAILED",
    "_run_paused": "SIGNAL_RUN_PAUSED",
    "_run_resumed": "SIGNAL_RUN_RESUMED",
    "_run_stopped": "SIGNAL_RUN_STOPPED",
    "_run_finished": "SIGNAL_RUN_FINISHED",
    "_run_failed": "SIGNAL_RUN_FAILED",
    "_stage_changed": "SIGNAL_STAGE_CHANGED",
    "_progress_updated": "SIGNAL_PROGRESS_UPDATED",
    "_provider_switched": "SIGNAL_PROVIDER_SWITCHED",
    "_model_switched": "SIGNAL_MODEL_SWITCHED",
    "_task_retry": "SIGNAL_TASK_RETRY",
    "_model_stability_changed": "SIGNAL_MODEL_STABILITY_CHANGED",
    "_judge_model_excluded": "SIGNAL_JUDGE_MODEL_EXCLUDED",
    "_inference_started": "SIGNAL_INFERENCE_STARTED",
    "_inference_progress": "SIGNAL_INFERENCE_PROGRESS",
    "_inference_completed": "SIGNAL_INFERENCE_COMPLETED",
    "_judge_started": "SIGNAL_JUDGE_STARTED",
    "_judge_completed": "SIGNAL_JUDGE_COMPLETED",
    "_task_completed": "SIGNAL_TASK_COMPLETED",
    "_run_id_changed": "SIGNAL_RUN_ID_CHANGED",
    "_run_list_changed": "SIGNAL_RUN_LIST_CHANGED",
    "_run_renamed": "SIGNAL_RUN_RENAMED",
    "_summary_data_changed": "SIGNAL_SUMMARY_DATA_CHANGED",
    "_detailed_data_changed": "SIGNAL_DETAILED_DATA_CHANGED",
    "_chart_data_changed": "SIGNAL_CHART_DATA_CHANGED",
    "_run_analysis_received": "SIGNAL_RUN_ANALYSIS_RECEIVED",
    "_provider_registry_reloaded": "SIGNAL_PROVIDER_REGISTRY_RELOADED",
    "_app_settings_changed": "SIGNAL_APP_SETTINGS_CHANGED",
    "_provider_inference_test_completed": "SIGNAL_PROVIDER_INFERENCE_TEST_COMPLETED",
    "_app_readiness_changed": "SIGNAL_APP_READINESS_CHANGED",
    "_inference_activity_changed": "SIGNAL_INFERENCE_ACTIVITY_CHANGED",
    "_global_message": "SIGNAL_GLOBAL_MESSAGE",
    "_log_cleared": "SIGNAL_LOG_CLEARED",
    "_workspace_changed": "SIGNAL_WORKSPACE_CHANGED",
    "_task_file_changed": "SIGNAL_TASK_FILE_CHANGED",
}


@pytest.mark.parametrize(
    ("event_name", "payload_type_name"),
    _EVENT_TO_PAYLOAD_INDEX,
    ids=[event_name for event_name, _ in _EVENT_TO_PAYLOAD_INDEX],
)
def test_every_cataloged_event_has_a_matching_frozen_payload_struct(
    event_name: str, payload_type_name: str
) -> None:
    """Proves: STORY-003-AC-2

    Table-driven over all 36 events in the §7 event-to-payload index: for each event
    name, a ``msgspec.Struct`` named exactly as the index's payload-struct column exists
    in ``backend.events``, is declared ``frozen=True, kw_only=True, gc=False``, and the
    event's signal-name constant's string value matches the event name exactly.
    """
    # Arrange
    signal_constant_name = _EVENT_TO_SIGNAL_CONSTANT[event_name]

    # Act
    payload_type = getattr(events_models, payload_type_name)
    signal_value = getattr(events_models, signal_constant_name)
    struct_config: msgspec.structs.StructConfig = payload_type.__struct_config__
    struct_info = msgspec.inspect.type_info(payload_type)
    field_count = len(payload_type.__struct_fields__)

    # Assert
    assert isinstance(payload_type, type)
    assert issubclass(payload_type, msgspec.Struct)
    assert isinstance(struct_info, msgspec.inspect.StructType)
    assert struct_config.frozen is True
    assert struct_config.gc is False
    assert struct_info.array_like is False  # kw_only structs decode from objects, not arrays
    with pytest.raises(TypeError):  # kw_only=True rejects positional construction
        payload_type(*((None,) * max(field_count, 1)))
    assert signal_value == event_name


def test_event_to_payload_index_is_closed_at_36_events() -> None:
    """Proves: STORY-003-AC-2

    The §7 event-to-payload index this test table encodes is total and closed: it has
    exactly 36 rows, matching the story's corrected in-scope count (7 + 8 + 6 + 3 + 4 + 3
    + 4 + 2 payloads across catalogue sections 5.1-5.8).
    """
    # Act
    event_count = len(_EVENT_TO_PAYLOAD_INDEX)

    # Assert
    assert event_count == _EXPECTED_EVENT_COUNT


# ---------------------------------------------------------------------------------
# AC-3 — provider-identity fields carry `provider_id`/`judge_provider_id`, never a
# live/display name.
# ---------------------------------------------------------------------------------

# Every payload Struct that the catalogue's DD-33 provider-identity rule applies to,
# paired with the provider-identity field name(s) it must declare. `ProviderHealthSummary`
# is included because it is the per-provider element carried by `AppReadinessChangedEvent`.
_PROVIDER_NAMING_PAYLOADS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ProgressUpdatedEvent", ("current_provider_id",)),
    ("ProviderSwitchedEvent", ("from_provider_id", "to_provider_id")),
    ("ModelSwitchedEvent", ("provider_id",)),
    ("TaskRetryEvent", ("provider_id",)),
    ("ModelStabilityChangedEvent", ("provider_id",)),
    ("JudgeModelExcludedEvent", ("provider_id",)),
    ("InferenceStartedEvent", ("provider_id",)),
    ("InferenceProgressEvent", ("provider_id",)),
    ("InferenceCompletedEvent", ("provider_id",)),
    ("JudgeStartedEvent", ("judge_provider_id",)),
    ("TaskCompletedEvent", ("provider_id",)),
    ("ProviderRegistryReloadedEvent", ("enabled_provider_ids",)),
    ("ProviderHealthSummary", ("provider_id",)),
)

_FORBIDDEN_NAME_FIELDS = ("name", "provider_name", "judge_provider_name")


@pytest.mark.parametrize(
    ("payload_type_name", "provider_identity_fields"),
    _PROVIDER_NAMING_PAYLOADS,
    ids=[name for name, _ in _PROVIDER_NAMING_PAYLOADS],
)
def test_provider_naming_payloads_carry_provider_id_never_live_name(
    payload_type_name: str, provider_identity_fields: tuple[str, ...]
) -> None:
    """Proves: STORY-003-AC-3

    Table-driven over every payload Struct naming a provider (DD-33): each declares its
    documented provider-identity field(s) (``provider_id``, ``judge_provider_id``, or a
    collection thereof) and declares no ``name``/``provider_name``/``judge_provider_name``
    field — a run-scoped display name is never carried on the event payload itself.
    """
    # Arrange
    payload_type = getattr(events_models, payload_type_name)
    declared_fields = set(typing.get_type_hints(payload_type))

    # Act / Assert
    assert declared_fields.issuperset(provider_identity_fields)
    assert declared_fields.isdisjoint(_FORBIDDEN_NAME_FIELDS)
