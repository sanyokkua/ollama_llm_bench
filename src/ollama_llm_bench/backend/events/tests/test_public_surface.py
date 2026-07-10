"""Tests proving every in-scope symbol is importable from ``backend.events`` directly.

STORY-003's in-scope list is: the ``EventBus`` Protocol, the ``Subscription`` Protocol,
every payload ``msgspec.Struct`` named in the §7 event-to-payload index (36 event
payloads) plus the two auxiliary structs referenced by the payload schemas
(``RunListEntry``, ``ProviderHealthSummary`` — 38 exported struct types total), and the
closed set of 36 signal-name constants matching the §7 index exactly.
"""

import ollama_llm_bench.backend.events as events_package

_EXPECTED_SIGNAL_CONSTANTS = {
    "SIGNAL_RUN_STARTED",
    "SIGNAL_RUN_START_FAILED",
    "SIGNAL_RUN_PAUSED",
    "SIGNAL_RUN_RESUMED",
    "SIGNAL_RUN_STOPPED",
    "SIGNAL_RUN_FINISHED",
    "SIGNAL_RUN_FAILED",
    "SIGNAL_STAGE_CHANGED",
    "SIGNAL_PROGRESS_UPDATED",
    "SIGNAL_PROVIDER_SWITCHED",
    "SIGNAL_MODEL_SWITCHED",
    "SIGNAL_TASK_RETRY",
    "SIGNAL_MODEL_STABILITY_CHANGED",
    "SIGNAL_JUDGE_MODEL_EXCLUDED",
    "SIGNAL_INFERENCE_STARTED",
    "SIGNAL_INFERENCE_PROGRESS",
    "SIGNAL_INFERENCE_COMPLETED",
    "SIGNAL_JUDGE_STARTED",
    "SIGNAL_JUDGE_COMPLETED",
    "SIGNAL_TASK_COMPLETED",
    "SIGNAL_RUN_ID_CHANGED",
    "SIGNAL_RUN_LIST_CHANGED",
    "SIGNAL_RUN_RENAMED",
    "SIGNAL_SUMMARY_DATA_CHANGED",
    "SIGNAL_DETAILED_DATA_CHANGED",
    "SIGNAL_CHART_DATA_CHANGED",
    "SIGNAL_RUN_ANALYSIS_RECEIVED",
    "SIGNAL_PROVIDER_REGISTRY_RELOADED",
    "SIGNAL_APP_SETTINGS_CHANGED",
    "SIGNAL_PROVIDER_INFERENCE_TEST_COMPLETED",
    "SIGNAL_APP_READINESS_CHANGED",
    "SIGNAL_INFERENCE_ACTIVITY_CHANGED",
    "SIGNAL_GLOBAL_MESSAGE",
    "SIGNAL_LOG_CLEARED",
    "SIGNAL_WORKSPACE_CHANGED",
    "SIGNAL_TASK_FILE_CHANGED",
}

_EXPECTED_PAYLOAD_STRUCTS = {
    "RunStartedEvent",
    "RunStartFailedEvent",
    "RunPausedEvent",
    "RunResumedEvent",
    "RunStoppedEvent",
    "RunFinishedEvent",
    "RunFailedEvent",
    "StageChangedEvent",
    "ProgressUpdatedEvent",
    "ProviderSwitchedEvent",
    "ModelSwitchedEvent",
    "TaskRetryEvent",
    "ModelStabilityChangedEvent",
    "JudgeModelExcludedEvent",
    "InferenceStartedEvent",
    "InferenceProgressEvent",
    "InferenceCompletedEvent",
    "JudgeStartedEvent",
    "JudgeCompletedEvent",
    "TaskCompletedEvent",
    "RunIdChangedEvent",
    "RunListChangedEvent",
    "RunRenamedEvent",
    "SummaryDataChangedEvent",
    "DetailedDataChangedEvent",
    "ChartDataChangedEvent",
    "RunAnalysisReceivedEvent",
    "ProviderRegistryReloadedEvent",
    "AppSettingsChangedEvent",
    "InferenceTestCompletedEvent",
    "AppReadinessChangedEvent",
    "InferenceActivityChangedEvent",
    "GlobalMessageEvent",
    "LogClearedEvent",
    "WorkspaceChangedEvent",
    "TaskFileChangedEvent",
}

# Auxiliary structs referenced by the payload schemas but not themselves a §7 event payload
# (`RunListEntry` is the element type of `RunListChangedEvent.runs`; `ProviderHealthSummary`
# is the element type of `AppReadinessChangedEvent.per_provider`).
_EXPECTED_AUXILIARY_STRUCTS = {
    "RunListEntry",
    "ProviderHealthSummary",
}

_EXPECTED_PROTOCOLS = {
    "EventBus",
    "Subscription",
}

_EXPECTED_PUBLIC_SYMBOLS = (
    _EXPECTED_SIGNAL_CONSTANTS
    | _EXPECTED_PAYLOAD_STRUCTS
    | _EXPECTED_AUXILIARY_STRUCTS
    | _EXPECTED_PROTOCOLS
)


def test_events_public_symbols_and_signal_names_are_reexported_and_total() -> None:
    """Proves: STORY-003-AC-5

    Every signal-name constant, the ``EventBus`` Protocol, the ``Subscription`` Protocol,
    and every payload Struct named in the story's In-scope list is importable directly
    from the ``backend.events`` package root, the package's ``__all__`` contains exactly
    this set, and the set of exported signal-name constants has no member absent from,
    and no member beyond, the §7 index (36 event-name constants exactly).
    """
    # Act
    declared_all = set(events_package.__all__)
    declared_signal_constants = {name for name in declared_all if name.startswith("SIGNAL_")}

    # Assert
    assert declared_all == _EXPECTED_PUBLIC_SYMBOLS
    assert declared_signal_constants == _EXPECTED_SIGNAL_CONSTANTS
    for symbol_name in _EXPECTED_PUBLIC_SYMBOLS:
        assert hasattr(events_package, symbol_name), (
            f"{symbol_name} not importable from package root"
        )
