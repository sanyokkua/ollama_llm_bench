"""Event Bus signal-name constants and payload ``msgspec.Struct`` catalogue.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-J_event_bus_catalog.md``
§7 (event-to-payload index, the closed 36-event set) and
``docs/v3_specification/08_Cross_Cutting/08-Q_event_payload_schemas.md`` (the
field-level contract for every payload Struct, table-driven per event).

Every payload is ``msgspec.Struct(frozen=True, kw_only=True, gc=False)`` per the
project's universal DTO rule. A payload naming a provider carries only
``provider_id`` (the internal, rename-stable UUID4) for linkage — never the
user-facing ``name`` (DD-33); a run-scoped display name is carried instead via the
run's own snapshot-name field (e.g. ``BenchmarkRun.judge_provider_name``,
``BenchmarkResult.provider_name``), never a live-registry name. The judge produces
no numeric score anywhere in this module — the only numeric quality value carried
by any payload is ``cosine_similarity``.

This module owns no logic: it defines the closed set of signal-name string
constants (so callers never hand-type a string literal) and the payload types
those signals carry. It imports nothing project-internal beyond
``backend.domain`` — standard library and ``msgspec`` otherwise.
"""

import msgspec

from ollama_llm_bench.backend.domain import (
    CosineScore,
    DurationMs,
    ErrorKind,
    InferenceActivityState,
    InferenceContext,
    InferenceTestResult,
    Iso8601Utc,
    ModelName,
    NonEmptyStr,
    NonNegativeInt,
    PositiveInt,
    ProviderId,
    ReadinessState,
    ResultId,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
    TaskId,
    TaskIdStr,
    Verdict,
)

__all__: list[str] = [
    "SIGNAL_APP_READINESS_CHANGED",
    "SIGNAL_APP_SETTINGS_CHANGED",
    "SIGNAL_CHART_DATA_CHANGED",
    "SIGNAL_DETAILED_DATA_CHANGED",
    "SIGNAL_GLOBAL_MESSAGE",
    "SIGNAL_INFERENCE_ACTIVITY_CHANGED",
    "SIGNAL_INFERENCE_COMPLETED",
    "SIGNAL_INFERENCE_PROGRESS",
    "SIGNAL_INFERENCE_STARTED",
    "SIGNAL_JUDGE_COMPLETED",
    "SIGNAL_JUDGE_MODEL_EXCLUDED",
    "SIGNAL_JUDGE_STARTED",
    "SIGNAL_LOG_CLEARED",
    "SIGNAL_MODEL_STABILITY_CHANGED",
    "SIGNAL_MODEL_SWITCHED",
    "SIGNAL_PROGRESS_UPDATED",
    "SIGNAL_PROVIDER_INFERENCE_TEST_COMPLETED",
    "SIGNAL_PROVIDER_REGISTRY_RELOADED",
    "SIGNAL_PROVIDER_SWITCHED",
    "SIGNAL_RUN_ANALYSIS_RECEIVED",
    "SIGNAL_RUN_FAILED",
    "SIGNAL_RUN_FINISHED",
    "SIGNAL_RUN_ID_CHANGED",
    "SIGNAL_RUN_LIST_CHANGED",
    "SIGNAL_RUN_PAUSED",
    "SIGNAL_RUN_RENAMED",
    "SIGNAL_RUN_RESUMED",
    "SIGNAL_RUN_STARTED",
    "SIGNAL_RUN_START_FAILED",
    "SIGNAL_RUN_STOPPED",
    "SIGNAL_STAGE_CHANGED",
    "SIGNAL_SUMMARY_DATA_CHANGED",
    "SIGNAL_TASK_COMPLETED",
    "SIGNAL_TASK_FILE_CHANGED",
    "SIGNAL_TASK_RETRY",
    "SIGNAL_WORKSPACE_CHANGED",
    "AppReadinessChangedEvent",
    "AppSettingsChangedEvent",
    "ChartDataChangedEvent",
    "DetailedDataChangedEvent",
    "GlobalMessageEvent",
    "InferenceActivityChangedEvent",
    "InferenceCompletedEvent",
    "InferenceProgressEvent",
    "InferenceStartedEvent",
    "InferenceTestCompletedEvent",
    "JudgeCompletedEvent",
    "JudgeModelExcludedEvent",
    "JudgeStartedEvent",
    "LogClearedEvent",
    "ModelStabilityChangedEvent",
    "ModelSwitchedEvent",
    "ProgressUpdatedEvent",
    "ProviderHealthSummary",
    "ProviderRegistryReloadedEvent",
    "ProviderSwitchedEvent",
    "RunAnalysisReceivedEvent",
    "RunFailedEvent",
    "RunFinishedEvent",
    "RunIdChangedEvent",
    "RunListChangedEvent",
    "RunListEntry",
    "RunPausedEvent",
    "RunRenamedEvent",
    "RunResumedEvent",
    "RunStartFailedEvent",
    "RunStartedEvent",
    "RunStoppedEvent",
    "StageChangedEvent",
    "SummaryDataChangedEvent",
    "TaskCompletedEvent",
    "TaskFileChangedEvent",
    "TaskRetryEvent",
    "WorkspaceChangedEvent",
]

# ---------------------------------------------------------------------------------
# Signal-name constants (`08-J_event_bus_catalog.md` §5, §7) — the closed 36-event
# set. Every constant's string value is the catalog's leading-underscore event name.
# ---------------------------------------------------------------------------------

# 5.1 Run lifecycle
SIGNAL_RUN_STARTED = "_run_started"
SIGNAL_RUN_START_FAILED = "_run_start_failed"
SIGNAL_RUN_PAUSED = "_run_paused"
SIGNAL_RUN_RESUMED = "_run_resumed"
SIGNAL_RUN_STOPPED = "_run_stopped"
SIGNAL_RUN_FINISHED = "_run_finished"
SIGNAL_RUN_FAILED = "_run_failed"

# 5.2 Stage and progress
SIGNAL_STAGE_CHANGED = "_stage_changed"
SIGNAL_PROGRESS_UPDATED = "_progress_updated"
SIGNAL_PROVIDER_SWITCHED = "_provider_switched"
SIGNAL_MODEL_SWITCHED = "_model_switched"
SIGNAL_TASK_RETRY = "_task_retry"
SIGNAL_MODEL_STABILITY_CHANGED = "_model_stability_changed"
SIGNAL_JUDGE_MODEL_EXCLUDED = "_judge_model_excluded"

# 5.3 Per-task events
SIGNAL_INFERENCE_STARTED = "_inference_started"
SIGNAL_INFERENCE_PROGRESS = "_inference_progress"
SIGNAL_INFERENCE_COMPLETED = "_inference_completed"
SIGNAL_JUDGE_STARTED = "_judge_started"
SIGNAL_JUDGE_COMPLETED = "_judge_completed"
SIGNAL_TASK_COMPLETED = "_task_completed"

# 5.4 Run name and run-list changes
SIGNAL_RUN_ID_CHANGED = "_run_id_changed"
SIGNAL_RUN_LIST_CHANGED = "_run_list_changed"
SIGNAL_RUN_RENAMED = "_run_renamed"

# 5.5 Table and chart data changed
SIGNAL_SUMMARY_DATA_CHANGED = "_summary_data_changed"
SIGNAL_DETAILED_DATA_CHANGED = "_detailed_data_changed"
SIGNAL_CHART_DATA_CHANGED = "_chart_data_changed"
SIGNAL_RUN_ANALYSIS_RECEIVED = "_run_analysis_received"

# 5.6 Settings and providers changed
SIGNAL_PROVIDER_REGISTRY_RELOADED = "_provider_registry_reloaded"
SIGNAL_APP_SETTINGS_CHANGED = "_app_settings_changed"
SIGNAL_PROVIDER_INFERENCE_TEST_COMPLETED = "_provider_inference_test_completed"

# 5.7 Global and app-readiness
SIGNAL_APP_READINESS_CHANGED = "_app_readiness_changed"
SIGNAL_INFERENCE_ACTIVITY_CHANGED = "_inference_activity_changed"
SIGNAL_GLOBAL_MESSAGE = "_global_message"
SIGNAL_LOG_CLEARED = "_log_cleared"

# 5.8 Workspace and task-file events
SIGNAL_WORKSPACE_CHANGED = "_workspace_changed"
SIGNAL_TASK_FILE_CHANGED = "_task_file_changed"


# ---------------------------------------------------------------------------------
# 2. Run lifecycle payloads (`08-Q_event_payload_schemas.md` §2)
# ---------------------------------------------------------------------------------


class RunStartedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_started`` (§2.1): a run's pipeline began executing."""

    run_id: RunId
    run_name: str
    run_mode: RunMode
    started_at: Iso8601Utc
    total_tasks: NonNegativeInt
    test_targets: tuple[tuple[ProviderId, ModelName], ...]
    judge_target: tuple[ProviderId, ModelName] | None = None
    embedding_target: tuple[ProviderId, ModelName] | None = None


class RunStartFailedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_start_failed`` (§2, catalog row 5.1): run creation failed
    before the pipeline began; no ``benchmark_runs`` row persists."""

    run_mode: RunMode
    error_kind: ErrorKind
    error_message: str
    attempted_at: Iso8601Utc


class RunPausedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_paused`` (§2.2): the pipeline finished the in-flight task
    and halted at a clean per-task boundary."""

    run_id: RunId
    paused_at: Iso8601Utc
    completed_tasks: NonNegativeInt
    total_tasks: NonNegativeInt


class RunResumedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_resumed`` (§2.3): a paused run resumed execution."""

    run_id: RunId
    resumed_at: Iso8601Utc
    completed_tasks: NonNegativeInt
    total_tasks: NonNegativeInt


class RunStoppedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_stopped`` (§2.4): the user stopped the run before
    completion; the persisted ``RunStatus`` becomes ``STOPPED``."""

    run_id: RunId
    stopped_at: Iso8601Utc
    completed_tasks: NonNegativeInt
    total_tasks: NonNegativeInt
    reason: str | None = None


class RunFinishedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_finished`` (§2.5): every result reached a terminal
    status and the run finished normally."""

    run_id: RunId
    finished_at: Iso8601Utc
    run_status: RunStatus
    total_tasks: NonNegativeInt
    completed_tasks: NonNegativeInt
    counts_by_result_status: dict[ResultStatus, NonNegativeInt]
    total_elapsed_ms: DurationMs


class RunFailedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_failed`` (§2.6): a fatal pipeline error halted the run;
    the persisted ``RunStatus`` becomes ``FAILED``. ``error_message`` is redacted
    before emission."""

    run_id: RunId
    failed_at: Iso8601Utc
    error_kind: ErrorKind
    error_message: str
    completed_tasks: NonNegativeInt
    total_tasks: NonNegativeInt


# ---------------------------------------------------------------------------------
# 3. Stage and progress payloads (`08-Q_event_payload_schemas.md` §3)
# ---------------------------------------------------------------------------------


class StageChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_stage_changed`` (§3.1): the pipeline advanced to a new phase
    of the five-phase batched pipeline."""

    run_id: RunId
    stage: str
    previous_stage: str | None = None
    stage_index: PositiveInt
    stage_count: PositiveInt


class ProgressUpdatedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_progress_updated`` (§3.2): aggregate run progress changed."""

    run_id: RunId
    completed_count: NonNegativeInt
    total_count: NonNegativeInt
    counts_by_result_status: dict[ResultStatus, NonNegativeInt]
    current_provider_id: ProviderId | None = None
    current_model_name: ModelName | None = None
    current_task_id: TaskId | None = None


class ProviderSwitchedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_provider_switched`` (§3.3): the pipeline moved to a
    different provider for the next batch."""

    run_id: RunId
    from_provider_id: ProviderId | None = None
    to_provider_id: ProviderId


class ModelSwitchedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_model_switched`` (§3.4): the pipeline moved to a different
    model for the next batch."""

    run_id: RunId
    provider_id: ProviderId
    from_model_name: ModelName | None = None
    to_model_name: ModelName


class TaskRetryEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_task_retry`` (§3.5): a failed task is being retried."""

    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    provider_id: ProviderId
    model_name: ModelName
    attempt: PositiveInt
    total_attempts: PositiveInt
    reason: str
    error_kind: ErrorKind


class ModelStabilityChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_model_stability_changed`` (§3.6): the adaptive-timeout state
    for a ``(provider_id, model_name, role)`` bucket, or the provider
    circuit-breaker state, changed. Emitted per role — a test model and a judge
    model are tracked independently."""

    run_id: RunId
    provider_id: ProviderId
    model_name: ModelName
    model_state: str
    model_consecutive_successes: NonNegativeInt
    model_promotion_threshold: PositiveInt
    provider_state: str
    provider_consecutive_failures: NonNegativeInt
    provider_cooldown_remaining_ms: DurationMs
    last_probe_ok_at: Iso8601Utc | None = None
    last_probe_failed_at: Iso8601Utc | None = None


class JudgeModelExcludedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_judge_model_excluded`` (§3.6a): the role=JUDGE bucket for the
    run's judge ``(provider_id, model_name)`` crossed the
    consecutive-max-timeout threshold. Fires at most once per ``BENCHMARK_RUN``
    activity.

    ``excluded_at`` is a unix-millisecond UTC integer (the one documented
    carve-out from the ``Iso8601Utc`` timestamp convention, §1) because it feeds
    elapsed-time arithmetic rather than display or persistence.
    """

    run_id: RunId
    provider_id: ProviderId
    model_name: ModelName
    consecutive_timeouts: PositiveInt
    exclusion_reason: NonEmptyStr
    excluded_at: int
    remaining_tasks_affected: NonNegativeInt


# ---------------------------------------------------------------------------------
# 4. Per-task payloads (`08-Q_event_payload_schemas.md` §4)
# ---------------------------------------------------------------------------------


class InferenceStartedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_inference_started`` (§4.1): an inference call for one task
    began."""

    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    provider_id: ProviderId
    model_name: ModelName
    stage: str
    user_prompt: str
    system_prompt: str | None = None


class InferenceProgressEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_inference_progress`` (§4.1a): a heartbeat snapshot of one
    in-flight LLM call. Carries counters only — elapsed time, running
    ``tokens_received``, and the ``first_token_received`` flag, plus an
    ``InferenceContext`` discriminator. No model-response text crosses this
    boundary as a chunk event.

    ``timestamp_ms`` is a unix-millisecond UTC integer (the other documented
    carve-out from the ``Iso8601Utc`` convention, §1) because it is a
    high-frequency liveness field, not a display/persistence timestamp.

    ``tokens_estimated`` is an additive field (STORY-059): ``True`` when the
    call's running ``tokens_received`` count for this snapshot came from the
    4-character heuristic rather than a provider-reported per-chunk/running
    count (``11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`` §6.5a).
    Named to match the existing ``BenchmarkResult.tokens_estimated`` field.
    """

    context: InferenceContext
    run_id: RunId | None
    result_id: ResultId | None
    task_id: TaskIdStr | None
    provider_id: ProviderId
    model_name: ModelName
    elapsed_ms: int
    tokens_received: int | None = None
    first_token_received: bool
    timestamp_ms: int
    tokens_estimated: bool = False


class InferenceCompletedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_inference_completed`` (§4.2): an inference call for one task
    finished; carries timing and token counts."""

    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    provider_id: ProviderId
    model_name: ModelName
    total_time_ms: DurationMs
    ttft_ms: DurationMs | None = None
    prompt_tokens: NonNegativeInt | None = None
    completion_tokens: NonNegativeInt | None = None
    tokens_per_second: float | None = None


class JudgeStartedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_judge_started`` (§4.3): the per-task judge phase began
    evaluating one task. Emitted only in ``GRADED`` runs."""

    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    judge_provider_id: ProviderId
    judge_model_name: ModelName


class JudgeCompletedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_judge_completed`` (§4.4): the per-task judge phase finished
    one task; carries the binary judge verdict and reasoning. The judge produces
    no numeric score — this payload carries no score field of any kind."""

    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    judge_verdict: Verdict
    judge_reasoning: str
    judge_time_ms: DurationMs
    judge_completion_tokens: NonNegativeInt | None = None


class TaskCompletedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_task_completed`` (§4.5): one task reached a terminal
    ``ResultStatus``.

    ``verdict`` is ``PASS``/``FAIL`` only when ``result_status == COMPLETED``
    for a graded run, and ``None`` otherwise; ``cosine_similarity`` is the only
    numeric quality value carried anywhere on this payload — there is no judge
    score field.
    """

    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    provider_id: ProviderId
    model_name: ModelName
    result_status: ResultStatus
    verdict: Verdict | None = None
    cosine_similarity: CosineScore | None = None
    total_time_ms: DurationMs | None = None
    error_kind: ErrorKind | None = None


# ---------------------------------------------------------------------------------
# 5. Run name and run-list payloads (`08-Q_event_payload_schemas.md` §5)
# ---------------------------------------------------------------------------------


class RunIdChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_id_changed`` (§5.1): the currently selected run
    changed."""

    run_id: RunId | None
    previous_run_id: RunId | None = None


class RunListEntry(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One row of the run list carried by ``RunListChangedEvent`` (§5.2) — the
    minimum a list widget needs to render a row without a further query."""

    run_id: RunId
    run_name: str
    run_mode: RunMode
    run_status: RunStatus
    created_at: Iso8601Utc


class RunListChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_list_changed`` (§5.2): the set of runs changed — a run
    was created, deleted, or renamed."""

    runs: tuple[RunListEntry, ...]
    change_kind: str
    affected_run_id: RunId | None = None


class RunRenamedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_renamed`` (§5.3): a run's display name changed."""

    run_id: RunId
    new_name: str
    previous_name: str | None = None


# ---------------------------------------------------------------------------------
# 6. Table and chart data payloads (`08-Q_event_payload_schemas.md` §6)
# ---------------------------------------------------------------------------------


class SummaryDataChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_summary_data_changed`` (§6.1): the summary-table dataset for
    a run changed. ``revision`` lets a subscriber discard an out-of-order
    delivery."""

    run_id: RunId
    row_count: NonNegativeInt
    revision: PositiveInt


class DetailedDataChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_detailed_data_changed`` (§6.2): the detailed-table dataset
    for a run changed."""

    run_id: RunId
    row_count: NonNegativeInt
    revision: PositiveInt


class ChartDataChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_chart_data_changed`` (§6.3): a chart's aggregated dataset
    for a run changed."""

    run_id: RunId
    chart_kind: str
    revision: PositiveInt


class RunAnalysisReceivedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_run_analysis_received`` (§6.4): the single consolidated
    run-level analysis narrative is available. There is exactly one analysis
    event for all three run modes — no separate performance/judge-summary
    events exist."""

    run_id: RunId
    run_mode: RunMode
    analysis_markdown: str
    generated_at: Iso8601Utc
    is_regeneration: bool = False


# ---------------------------------------------------------------------------------
# 7. Settings and providers payloads (`08-Q_event_payload_schemas.md` §7)
# ---------------------------------------------------------------------------------


class ProviderRegistryReloadedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_provider_registry_reloaded`` (§7.1): the provider registry
    was rebuilt. Carries no secret material."""

    provider_count: NonNegativeInt
    enabled_provider_ids: tuple[ProviderId, ...]
    reload_cause: str


class AppSettingsChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_app_settings_changed`` (§7.2): one or more application
    settings were written. Carries only the changed keys, never the values, so
    no setting value — and no secret — reaches the bus."""

    changed_keys: tuple[str, ...]


class InferenceTestCompletedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_provider_inference_test_completed`` (§7.3): a user-initiated
    end-to-end inference test returned its result. Fires once per Test
    inference action (success, failure, or ``GATE_BUSY`` refusal)."""

    result: InferenceTestResult


# ---------------------------------------------------------------------------------
# 8. Global and app-readiness payloads (`08-Q_event_payload_schemas.md` §8)
# ---------------------------------------------------------------------------------


class ProviderHealthSummary(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One provider's reachability summary carried by ``AppReadinessChangedEvent``
    (§8.1). ``last_error`` is redacted before emission."""

    provider_id: ProviderId
    reachable: bool
    discovery_supported: bool
    model_count: int | None
    last_error: str | None = None


class AppReadinessChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_app_readiness_changed`` (§8.1): the aggregate
    app-readiness snapshot changed."""

    overall: ReadinessState
    per_provider: tuple[ProviderHealthSummary, ...]
    embedding_reachable: bool
    checked_at: Iso8601Utc


class InferenceActivityChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_inference_activity_changed`` (§8.2): the application-wide
    single-inference gate changed — an activity acquired the gate or released
    it. Every acquire and every release emits one event; no coalescing
    applies."""

    state: InferenceActivityState


class GlobalMessageEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_global_message`` (§8.3): a transient user-facing message
    must be shown as a status-bar toast. ``text`` must be redacted by the
    emitter before construction; no secret value reaches the toast."""

    text: str
    severity: str = "info"
    duration_ms: DurationMs | None = None


class LogClearedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_log_cleared`` (§8.4): the Progress widget log must be
    cleared, fired at run start."""

    run_id: RunId


# ---------------------------------------------------------------------------------
# 9. Workspace and task-file payloads (`08-Q_event_payload_schemas.md` §9)
# ---------------------------------------------------------------------------------


class WorkspaceChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_workspace_changed`` (§9.1): the active workspace switched
    between the Benchmark workspace and the Task Editor workspace."""

    workspace: str
    previous_workspace: str | None = None


class TaskFileChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Payload of ``_task_file_changed`` (§9.2): a YAML task file was saved to
    disk."""

    path: str
    task_count: NonNegativeInt
    change_kind: str
