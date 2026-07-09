"""Tests proving every in-scope symbol is importable from ``backend.domain`` directly.

STORY-001's in-scope list is: every ``StrEnum`` in §4 (23 members), every type alias in §2
(7 members), every constrained type in §3 (14 members), the §5-§7 records (including the
in-memory-only ``ProviderHealth``/``AppReadinessSnapshot`` and the runtime
``InferenceActivityContext``/``InferenceActivityState`` records), and the §8 patch records —
plus the locally-scoped enums those §5-§7 records reference (``ReadinessState``, ``ChatRole``,
``ReasoningEffort``, ``ResponseFormat``). The four EventBus payload structs/enums are excluded
(owned by STORY-003).
"""

import ollama_llm_bench.backend.domain as domain_package

# The full in-scope symbol set this story owns, independent of the module's own `__all__` —
# this is the traceability check: it must equal `__all__` exactly, with nothing missing and
# nothing extra smuggled in.
_EXPECTED_TYPE_ALIASES = {
    "RunId",
    "ResultId",
    "TaskId",
    "ProviderId",
    "ModelName",
    "SettingKey",
    "Iso8601Utc",
}

_EXPECTED_CONSTRAINED_TYPES = {
    "ProviderIdStr",
    "ModelNameStr",
    "TaskIdStr",
    "NonNegativeFloat",
    "PositiveFloat",
    "NonEmptyStr",
    "CosineScore",
    "CosineThreshold",
    "RetryCount",
    "TimeoutSeconds",
    "PositiveInt",
    "NonNegativeInt",
    "DurationMs",
    "RepeatCount",
}

_EXPECTED_SPEC_4_ENUMS = {
    "RunMode",
    "RunStatus",
    "ResultStatus",
    "Verdict",
    "ResolutionLayer",
    "Difficulty",
    "ProviderType",
    "ProviderTestStatus",
    "ModelRole",
    "AdaptiveTimeoutRole",
    "TaskOrigin",
    "TaskTermKind",
    "ResultTermKind",
    "ModelCapability",
    "CapabilitySource",
    "ErrorKind",
    "AttemptOutcome",
    "InferenceActivity",
    "ChartKind",
    "InferenceContext",
    "InferenceTestOutcome",
    "CancelLevel",
    "CancelReason",
}

_EXPECTED_RECORD_LOCAL_ENUMS = {
    "ReadinessState",
    "ChatRole",
    "ReasoningEffort",
    "ResponseFormat",
}

_EXPECTED_RECORDS = {
    # §5 — catalog records
    "ProviderConfig",
    "ProviderConfigDraft",
    "ModelCapabilityRecord",
    "AppSettingRecord",
    "AppMetaRecord",
    # §6 — run-data records
    "ModelDescriptor",
    "RequiredTerms",
    "BenchmarkTask",
    "BenchmarkRunModelEntry",
    "BenchmarkRunProviderEntry",
    "BenchmarkRunSettingEntry",
    "BenchmarkRun",
    "BenchmarkResultTerm",
    "BenchmarkResultAttempt",
    "BenchmarkResult",
    # §7 — runtime and service DTOs
    "ProviderHealth",
    "InferenceTestResult",
    "AppReadinessSnapshot",
    "PerformanceConfig",
    "RunStartRequest",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ChatChunk",
    "InferenceActivityContext",
    "InferenceActivityState",
    "GateLease",
    "ChartSeries",
    "ChartData",
    "HeatmapData",
    "ChartFilters",
    # §8 — patch records
    "ResultPatch",
    "RunStatusPatch",
}

_EXPECTED_PUBLIC_SYMBOLS = (
    _EXPECTED_TYPE_ALIASES
    | _EXPECTED_CONSTRAINED_TYPES
    | _EXPECTED_SPEC_4_ENUMS
    | _EXPECTED_RECORD_LOCAL_ENUMS
    | _EXPECTED_RECORDS
)


def test_domain_public_symbols_are_reexported() -> None:
    """Proves: STORY-001-AC-4

    Every enum, type alias, constrained type, and record named in the story's In-scope list
    is importable directly from the ``backend.domain`` package root, and the package's
    ``__all__`` contains exactly this set — no symbol missing, none extra.
    """
    # Act
    declared_all = set(domain_package.__all__)

    # Assert
    assert declared_all == _EXPECTED_PUBLIC_SYMBOLS
    for symbol_name in _EXPECTED_PUBLIC_SYMBOLS:
        assert hasattr(domain_package, symbol_name), (
            f"{symbol_name} not importable from package root"
        )
