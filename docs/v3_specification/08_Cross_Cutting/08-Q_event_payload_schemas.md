# Event Payload Schemas

**Status:** Draft
**Owner:** coder
**Audience:** coder
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-J_event_bus_catalog.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`

This document defines the payload of every event carried by the typed Event Bus. Each payload is a `msgspec.Struct` declared `frozen=True, kw_only=True, gc=False` — immutable, keyword-constructed, and opted out of cyclic garbage collection. The Event Bus routing map (emitters, subscribers, threading, coalescing) is in `08-J_event_bus_catalog.md`; this file is the binding field-level contract for what each event carries. Every event listed in `08-J` section 7 has exactly one struct here, in the same order.

---

## Table of Contents

1. Conventions
2. Run lifecycle payloads
3. Stage and progress payloads
4. Per-task payloads
5. Run name and run-list payloads
6. Table and chart data payloads
7. Settings and providers payloads
8. Global and app-readiness payloads
9. Workspace and task-file payloads

---

## 1. Conventions

- **Struct declaration.** Every payload is `class Name(msgspec.Struct, frozen=True, kw_only=True, gc=False)`. The payloads hold no reference cycles; `gc=False` is therefore safe and avoids GC tracking overhead on high-frequency events.
- **Imported types.** Payloads reference the enumerations and type aliases defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`: `RunMode`, `RunStatus`, `ResultStatus`, `Verdict`, `ErrorKind`, `RunId`, `ResultId`, `TaskId`, `TaskIdStr`, `ProviderId`, `ModelName`, `NonEmptyStr`, `CosineScore`, `Iso8601Utc`, `DurationMs`, `NonNegativeInt`, `PositiveInt`, `ReadinessState`, `InferenceActivity`, `InferenceActivityState`, `InferenceContext`, `AdaptiveTimeoutRole`, `InferenceTestOutcome`, `InferenceTestResult`, `InferenceProgressEvent`, `JudgeModelExcludedEvent`. They are reused verbatim — payloads never redefine a domain type.
- **Composite target identity.** A benchmark target is always the pair `(ProviderId, ModelName)`. Payloads that name a target carry both fields, or carry a `ModelDescriptor` (the `(provider_id, model_name)` struct from the DTO catalog). No payload identifies a target by model name alone.
- **Provider identifier vs display name (DD-33).** Every payload's `provider_id` field is the **internal UUID4** — the rename-stable linkage value. Payloads do NOT carry the user-visible `name`. Subscribers render the name at display time: historical surfaces resolve from the run-snapshot fields (`BenchmarkRun.judge_provider_name`, `BenchmarkRun.embedding_provider_name`, `BenchmarkRun.embedding_model_name`, `BenchmarkResult.provider_name`); live surfaces resolve from the `ProviderRegistry` / `ProvidersStore`. The same rule applies to `judge_provider_id`. See `08_Cross_Cutting/08-J_event_bus_catalog.md` §1 for the binding rendering rule.
- **Optionality.** A field typed `X | None` is optional and may be absent for the documented reason. A field without `| None` is always present.
- **No judge score.** The judge produces no numeric score. The only numeric quality value in any payload is `cosine_similarity` (the cosine-similarity check, range `0.0`–`1.0`). It is present only for a task that ran a cosine check and is `None` otherwise.
- **Binary verdict.** Every `Verdict` field is `PASS` or `FAIL`. A verdict field is `None` while a result is not yet `COMPLETED` and for any result that ended in a terminal-failure status.
- **Timestamps.** Human-facing and persisted timestamps cross the bus as ISO-8601 UTC strings (`Iso8601Utc`), consistent with the persistence layer. **Carve-out:** high-frequency or monotonic payload fields used for elapsed-time / liveness arithmetic rather than for display or persistence may instead be unix-millisecond UTC integers (`int`) recorded by the `Clock` — currently `excluded_at` (`JudgeModelExcludedEvent`, §3.6a) and `timestamp_ms` (`InferenceProgressEvent`, §3.7a). The `Iso8601Utc` rule applies to every other (human-facing or persisted) timestamp; these two numeric fields are the only exceptions.

The threading rule and coalescing rule cited per struct below restate the binding rule from `08-J`; the catalog file is the single source for routing.

---

## 2. Run lifecycle payloads

### 2.1 RunStartedEvent — `_run_started`

```python
class RunStartedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    run_name: str
    run_mode: RunMode
    started_at: Iso8601Utc
    total_tasks: NonNegativeInt
    test_targets: tuple[tuple[ProviderId, ModelName], ...]
    judge_target: tuple[ProviderId, ModelName] | None = None
    embedding_target: tuple[ProviderId, ModelName] | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run that began executing. |
| `run_name` | `str` | no | The effective display name of the run. |
| `run_mode` | `RunMode` | no | One of `SYNTHETIC`, `TASKS`, `GRADED`. |
| `started_at` | `Iso8601Utc` | no | When the pipeline began. |
| `total_tasks` | `NonNegativeInt` | no | Count of `BenchmarkResult` rows the run will produce. |
| `test_targets` | `tuple[tuple[ProviderId, ModelName], ...]` | no | The benchmark targets, by composite identity. |
| `judge_target` | `tuple[ProviderId, ModelName] \| None` | yes | The judge target; `None` unless the run grades. |
| `embedding_target` | `tuple[ProviderId, ModelName] \| None` | yes | The embedding target; `None` unless the run runs a cosine check. |

**Emitter:** benchmark pipeline. **Subscribers:** Progress widget, Main Window, Result widget. **Thread:** `worker → UI`. **Coalescing:** none.

### 2.2 RunPausedEvent — `_run_paused`

```python
class RunPausedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    paused_at: Iso8601Utc
    completed_tasks: NonNegativeInt
    total_tasks: NonNegativeInt
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The paused run. |
| `paused_at` | `Iso8601Utc` | no | When the pipeline halted. |
| `completed_tasks` | `NonNegativeInt` | no | Tasks in a terminal status at the pause point. |
| `total_tasks` | `NonNegativeInt` | no | Total tasks in the run. |

Pause finishes the in-flight task before this event fires; `completed_tasks` therefore reflects a clean per-task boundary.

**Emitter:** benchmark pipeline pause handler. **Subscribers:** Progress widget, Main Window. **Thread:** `worker → UI`. **Coalescing:** none.

### 2.3 RunResumedEvent — `_run_resumed`

```python
class RunResumedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    resumed_at: Iso8601Utc
    completed_tasks: NonNegativeInt
    total_tasks: NonNegativeInt
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The resumed run. |
| `resumed_at` | `Iso8601Utc` | no | When execution resumed. |
| `completed_tasks` | `NonNegativeInt` | no | Tasks already terminal at resume. |
| `total_tasks` | `NonNegativeInt` | no | Total tasks in the run. |

**Emitter:** benchmark pipeline resume handler. **Subscribers:** Progress widget, Main Window. **Thread:** `worker → UI`. **Coalescing:** none.

### 2.4 RunStoppedEvent — `_run_stopped`

```python
class RunStoppedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    stopped_at: Iso8601Utc
    completed_tasks: NonNegativeInt
    total_tasks: NonNegativeInt
    reason: str | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The stopped run. |
| `stopped_at` | `Iso8601Utc` | no | When the run was stopped. |
| `completed_tasks` | `NonNegativeInt` | no | Tasks terminal at the stop point. |
| `total_tasks` | `NonNegativeInt` | no | Total tasks in the run. |
| `reason` | `str \| None` | yes | Human-readable stop reason; `None` for a plain user stop. |

The persisted `RunStatus` of the run becomes `STOPPED`.

**Emitter:** benchmark pipeline stop handler. **Subscribers:** Progress widget, Main Window, Result widget. **Thread:** `worker → UI`. **Coalescing:** none.

### 2.5 RunFinishedEvent — `_run_finished`

```python
class RunFinishedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    finished_at: Iso8601Utc
    run_status: RunStatus
    total_tasks: NonNegativeInt
    completed_tasks: NonNegativeInt
    counts_by_result_status: dict[ResultStatus, NonNegativeInt]
    total_elapsed_ms: DurationMs
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The finished run. |
| `finished_at` | `Iso8601Utc` | no | When the run reached its terminal status. |
| `run_status` | `RunStatus` | no | The persisted terminal status — `COMPLETED` for a normal finish. |
| `total_tasks` | `NonNegativeInt` | no | Total tasks in the run. |
| `completed_tasks` | `NonNegativeInt` | no | Tasks that reached a terminal `ResultStatus`. |
| `counts_by_result_status` | `dict[ResultStatus, NonNegativeInt]` | no | Per-`ResultStatus` tallies across the run's results. |
| `total_elapsed_ms` | `DurationMs` | no | Cumulative measured execution time, surviving stop/resume. |

`counts_by_result_status` is keyed by the eleven `ResultStatus` members; at run finish every counted result is in one of the six terminal states.

**Emitter:** benchmark pipeline terminal handler. **Subscribers:** Progress widget, Result widget, Main Window. **Thread:** `worker → UI`. **Coalescing:** none.

### 2.6 RunFailedEvent — `_run_failed`

```python
class RunFailedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    failed_at: Iso8601Utc
    error_kind: ErrorKind
    error_message: str
    completed_tasks: NonNegativeInt
    total_tasks: NonNegativeInt
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The failed run. |
| `failed_at` | `Iso8601Utc` | no | When the fatal error halted the run. |
| `error_kind` | `ErrorKind` | no | Failure classification. The `ErrorKind` enum is `LLM`, `PROVIDER`, `TIMEOUT`, `JUDGE_TIMEOUT`, `OTHER`; a run-level fatal failure uses `LLM`, `PROVIDER`, `TIMEOUT`, or `OTHER`. `JUDGE_TIMEOUT` is a per-task result classification only (it never halts a run) and never appears here. |
| `error_message` | `str` | no | Redacted, human-readable failure detail. |
| `completed_tasks` | `NonNegativeInt` | no | Tasks terminal before the failure. |
| `total_tasks` | `NonNegativeInt` | no | Total tasks in the run. |

The persisted `RunStatus` of the run becomes `FAILED`. `error_message` is redacted before emission; no secret value reaches the bus.

**Emitter:** benchmark pipeline exception handler. **Subscribers:** Progress widget, Main Window, Result widget. **Thread:** `worker → UI`. **Coalescing:** none.

---

## 3. Stage and progress payloads

### 3.1 StageChangedEvent — `_stage_changed`

```python
class StageChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    stage: str
    previous_stage: str | None = None
    stage_index: PositiveInt
    stage_count: PositiveInt
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run whose stage changed. |
| `stage` | `str` | no | The phase the pipeline entered, within the five-phase batched pipeline. |
| `previous_stage` | `str \| None` | yes | The phase just left; `None` for the first stage. |
| `stage_index` | `PositiveInt` | no | 1-based index of the current phase. |
| `stage_count` | `PositiveInt` | no | Total phases for this run mode. |

**Emitter:** benchmark pipeline stage controller. **Subscribers:** Progress widget. **Thread:** `worker → UI`. **Coalescing:** none.

### 3.2 ProgressUpdatedEvent — `_progress_updated`

```python
class ProgressUpdatedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    completed_count: NonNegativeInt
    total_count: NonNegativeInt
    counts_by_result_status: dict[ResultStatus, NonNegativeInt]
    current_provider_id: ProviderId | None = None
    current_model_name: ModelName | None = None
    current_task_id: TaskId | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run reporting progress. |
| `completed_count` | `NonNegativeInt` | no | Tasks in a terminal `ResultStatus`. |
| `total_count` | `NonNegativeInt` | no | Total tasks in the run. |
| `counts_by_result_status` | `dict[ResultStatus, NonNegativeInt]` | no | Per-`ResultStatus` tallies, covering all eleven members. |
| `current_provider_id` | `ProviderId \| None` | yes | Provider of the task in flight; `None` between batches. |
| `current_model_name` | `ModelName \| None` | yes | Model of the task in flight; `None` between batches. |
| `current_task_id` | `TaskId \| None` | yes | Id of the task in flight; `None` between batches. |

**Emitter:** benchmark pipeline, after each per-task status transition. **Subscribers:** Progress widget. **Thread:** `worker → UI`. **Coalescing:** coalesced; delivered at most ten times per second, carrying the latest counts.

### 3.3 ProviderSwitchedEvent — `_provider_switched`

```python
class ProviderSwitchedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    from_provider_id: ProviderId | None = None
    to_provider_id: ProviderId
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run whose pipeline switched provider. |
| `from_provider_id` | `ProviderId \| None` | yes | The provider left; `None` on the first batch. |
| `to_provider_id` | `ProviderId` | no | The provider the pipeline moved to. |

**Emitter:** benchmark pipeline. **Subscribers:** Progress widget log. **Thread:** `worker → UI`. **Coalescing:** none.

### 3.4 ModelSwitchedEvent — `_model_switched`

```python
class ModelSwitchedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    provider_id: ProviderId
    from_model_name: ModelName | None = None
    to_model_name: ModelName
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run whose pipeline switched model. |
| `provider_id` | `ProviderId` | no | Provider of the new model. |
| `from_model_name` | `ModelName \| None` | yes | The model left; `None` on the first batch. |
| `to_model_name` | `ModelName` | no | The model the pipeline moved to. |

**Emitter:** benchmark pipeline. **Subscribers:** Progress widget log. **Thread:** `worker → UI`. **Coalescing:** none.

### 3.5 TaskRetryEvent — `_task_retry`

```python
class TaskRetryEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    provider_id: ProviderId
    model_name: ModelName
    attempt: PositiveInt
    total_attempts: PositiveInt
    reason: str
    error_kind: ErrorKind
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run the task belongs to. |
| `result_id` | `ResultId` | no | The result row being retried. |
| `task_id` | `TaskId` | no | The task being retried. |
| `provider_id` | `ProviderId` | no | Provider of the target. |
| `model_name` | `ModelName` | no | Model of the target. |
| `attempt` | `PositiveInt` | no | 1-based number of the attempt about to start. |
| `total_attempts` | `PositiveInt` | no | Maximum attempts permitted. |
| `reason` | `str` | no | Redacted, human-readable retry reason. |
| `error_kind` | `ErrorKind` | no | Classification of the failure that triggered the retry. |

**Emitter:** benchmark pipeline retry loop. **Subscribers:** Progress widget. **Thread:** `worker → UI`. **Coalescing:** none.

### 3.6 ModelStabilityChangedEvent — `_model_stability_changed`

```python
class ModelStabilityChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
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
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run whose stability state changed. |
| `provider_id` | `ProviderId` | no | Provider of the affected target. |
| `model_name` | `ModelName` | no | Model of the affected target. |
| `model_state` | `str` | no | Adaptive-timeout state of the `(provider, model)` pair. |
| `model_consecutive_successes` | `NonNegativeInt` | no | Consecutive successes counted toward promotion. |
| `model_promotion_threshold` | `PositiveInt` | no | Successes required to promote the model's timeout band. |
| `provider_state` | `str` | no | Circuit-breaker state for the provider. |
| `provider_consecutive_failures` | `NonNegativeInt` | no | Consecutive failures counted by the breaker. |
| `provider_cooldown_remaining_ms` | `DurationMs` | no | Remaining cooldown before the next probe; `0` when not cooling down. |
| `last_probe_ok_at` | `Iso8601Utc \| None` | yes | Time of the last successful probe; `None` if none yet. |
| `last_probe_failed_at` | `Iso8601Utc \| None` | yes | Time of the last failed probe; `None` if none yet. |

**Emitter:** Adaptive Timeout Service and Provider Circuit Breaker, on any state change. **Subscribers:** Progress widget stability boxes. **Thread:** `worker → UI`. **Coalescing:** none.

`model_state` reflects the **per-role** state of the bucket the change concerns (`role=INFERENCE` for a test-model state change; `role=JUDGE` for a judge-model state change). The dedicated `_judge_model_excluded` event (§3.6a) carries the final-exclusion transition for role=JUDGE separately, with a payload that includes the affected-task count — a piece of information not present on `ModelStabilityChangedEvent`.

### 3.6a JudgeModelExcludedEvent — `_judge_model_excluded`

```python
class JudgeModelExcludedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    provider_id: ProviderId
    model_name: ModelName
    consecutive_timeouts: PositiveInt
    exclusion_reason: NonEmptyStr
    excluded_at: int                       # unix milliseconds, UTC
    remaining_tasks_affected: NonNegativeInt
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run whose judge model was excluded. |
| `provider_id` | `ProviderId` | no | The judge model's provider; internal UUID4 (DD-33). The Event Log resolves the provider's display name from the live registry while the run is in flight, and from `BenchmarkRun.judge_provider_name` once the run completes. |
| `model_name` | `ModelName` | no | The judge model that was excluded. |
| `consecutive_timeouts` | `PositiveInt` | no | The count of consecutive max-budget judge timeouts that triggered exclusion. Always equals `eval.judge_timeout_consecutive_threshold` at emission time. |
| `exclusion_reason` | `NonEmptyStr` | no | Canonical text `"<N> consecutive max-budget judge timeouts"`. Subscribers may render verbatim or wrap. |
| `excluded_at` | `int` | no | Unix-millisecond UTC timestamp recorded by the `Clock` when the threshold was crossed. |
| `remaining_tasks_affected` | `NonNegativeInt` | no | Count of still-pending tasks in the run that would have entered the judge phase and will now settle to `FAILED_JUDGE_TIMEOUT` without the judge call being attempted. |

**Emitter:** benchmark pipeline Phase 4 (judge), exactly once per `BENCHMARK_RUN` activity, on the transition from `not excluded` to `excluded` in the role=JUDGE bucket for the run's judge `(provider, model)` pair. The Run Analysis Service does NOT emit this event — analysis-call exhaustion is signalled through `RunAnalysisResult.outcome = FAILED` with `reason = "judge_timeout_exhausted"` (`11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md` §6) and rendered inline by the Generate Analysis dialog. **Subscribers:** Progress widget Event Log (renders the "Judge model '<name>' excluded: <N> consecutive max-budget timeouts. Remaining tasks' judge phase will be skipped." entry), Result widget Status Listener (for filter-chip count refresh on the new `FAILED_JUDGE_TIMEOUT` status). **Thread:** `worker → UI`. **Coalescing:** none.

---

## 4. Per-task payloads

### 4.1 InferenceStartedEvent — `_inference_started`

```python
class InferenceStartedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    provider_id: ProviderId
    model_name: ModelName
    stage: str
    user_prompt: str
    system_prompt: str | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run the task belongs to. |
| `result_id` | `ResultId` | no | The result row for this task. |
| `task_id` | `TaskId` | no | The task being inferred. |
| `provider_id` | `ProviderId` | no | Provider of the target. |
| `model_name` | `ModelName` | no | Model of the target. |
| `stage` | `str` | no | The pipeline phase issuing the inference. |
| `user_prompt` | `str` | no | The user message sent. |
| `system_prompt` | `str \| None` | yes | The system message sent; `None` when none was sent. |

**Emitter:** benchmark pipeline inference phase. **Subscribers:** Progress widget log. **Thread:** `worker → UI`. **Coalescing:** none.

### 4.1a InferenceProgressEvent — `_inference_progress`

```python
class InferenceProgressEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
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
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `context` | `InferenceContext` | no | Which user-visible LLM-call surface produced this event — `BENCHMARK_TASK`, `BENCHMARK_JUDGE`, `RUN_ANALYSIS`, or `PROVIDER_TEST` (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.19a). Subscribers filter on this field. There is intentionally no `READINESS_PROBE` member; readiness probes never emit this event. |
| `run_id` | `RunId \| None` | yes | The run the call belongs to. Required for `BENCHMARK_TASK`, `BENCHMARK_JUDGE`, and `RUN_ANALYSIS`; `None` for `PROVIDER_TEST` (the Provider Edit test is not run-scoped). |
| `result_id` | `ResultId \| None` | yes | The result row for the call. Required for `BENCHMARK_TASK` and `BENCHMARK_JUDGE`; `None` for `RUN_ANALYSIS` and `PROVIDER_TEST` (no per-task semantics). |
| `task_id` | `TaskIdStr \| None` | yes | The task being inferred or judged. Required for `BENCHMARK_TASK` and `BENCHMARK_JUDGE`; `None` for `RUN_ANALYSIS` and `PROVIDER_TEST`. |
| `provider_id` | `ProviderId` | no | Provider of the call's target. Always present. |
| `model_name` | `ModelName` | no | Model of the call's target. Always present. |
| `elapsed_ms` | `int` | no | Milliseconds since the `chat_stream` call started. |
| `tokens_received` | `int \| None` | yes | Running completion-token count for this in-flight call; `None` until `first_token_received` is `True`. The source preference (provider per-chunk `delta_tokens` → provider running count → 4-char heuristic) is documented in `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.5 and `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §"Live inference-progress emission". |
| `first_token_received` | `bool` | no | `True` once the first content-bearing chunk has arrived. |
| `timestamp_ms` | `int` | no | Unix-millisecond UTC timestamp recorded by the `Clock` when this snapshot was taken. |

The payload carries **counters only** — no portion of the assembled response text crosses the bus. Each emitter keeps the response-text accumulator internally and never broadcasts chunks; the full formatted model response (where one exists, e.g. for benchmark contexts) still appears at task completion via the existing log-formatting and verbosity rules. The struct definition (and the canonical field-level contract) lives in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.7a; this entry restates it for the event bus catalog.

**Emitters:** four user-visible surfaces, each invoking the shared `emit_progress_during(...)` helper (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9) with the appropriate `context`:
- Benchmark Pipeline per-task main inference → `context=BENCHMARK_TASK`.
- Benchmark Pipeline per-task judge call (GRADED only) → `context=BENCHMARK_JUDGE`.
- Run Analysis Service `generate()` (`11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`) → `context=RUN_ANALYSIS`.
- `LLMClient.test_inference(...)` flow (`11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.8.2) → `context=PROVIDER_TEST`.

Readiness probes (`probe_health()`, `11_Services_and_Algorithms/09_READINESS_PROBE.md`) are NOT emitters — they are invisible background checks.

**Subscribers:** three consumers, each filtering by `context`:
- Progress widget Current-task controller — accepts `BENCHMARK_TASK` and `BENCHMARK_JUDGE`; renders them as two distinct sub-rows ("Inference progress" and "Judge progress" — see `04_Progress_Widget/description.md` §7.1).
- Generate Analysis dialog — accepts `RUN_ANALYSIS` and matches `run_id` against the run being analyzed; renders the live progress line in place of the static "Generating…" spinner (`07_Common_Dialogs/generate_analysis_dialog.md` §8).
- Provider Edit inference-test panel — accepts `PROVIDER_TEST` and matches `provider_id`; renders the live "Testing — …" indicator in place of the Run button area (`06_Settings_Dialog/sub_dialogs/provider_edit.md` §8.2).

**Thread:** `worker → UI` — marshalled to the Qt main thread via the existing `adapters/qt_event_bus/` bridge. **Coalescing:** coalesced at ≥ 1 Hz per in-flight call (chunk-driven by the synchronous `emit_progress_during(...)` helper — heartbeat chunks from the sub-second per-read socket timeout, one emission per ≥1000 ms window; no ticker thread, `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9).

### 4.2 InferenceCompletedEvent — `_inference_completed`

```python
class InferenceCompletedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
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
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run the task belongs to. |
| `result_id` | `ResultId` | no | The result row for this task. |
| `task_id` | `TaskId` | no | The task that finished inference. |
| `provider_id` | `ProviderId` | no | Provider of the target. |
| `model_name` | `ModelName` | no | Model of the target. |
| `total_time_ms` | `DurationMs` | no | End-to-end inference duration. |
| `ttft_ms` | `DurationMs \| None` | yes | Time to first token; `None` when transport streaming is unsupported. |
| `prompt_tokens` | `NonNegativeInt \| None` | yes | Prompt token count reported by the provider; `None` if unreported. |
| `completion_tokens` | `NonNegativeInt \| None` | yes | Completion token count; `None` if unreported. |
| `tokens_per_second` | `float \| None` | yes | Generation throughput; `None` when not derivable. |

**Emitter:** benchmark pipeline inference phase. **Subscribers:** Progress widget log. **Thread:** `worker → UI`. **Coalescing:** none.

### 4.3 JudgeStartedEvent — `_judge_started`

```python
class JudgeStartedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    judge_provider_id: ProviderId
    judge_model_name: ModelName
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run the task belongs to. |
| `result_id` | `ResultId` | no | The result row being judged. |
| `task_id` | `TaskId` | no | The task being judged. |
| `judge_provider_id` | `ProviderId` | no | Provider of the judge model. |
| `judge_model_name` | `ModelName` | no | The judge model. |

**Emitter:** benchmark pipeline judge phase. **Subscribers:** Progress widget log. **Thread:** `worker → UI`. **Coalescing:** none.

### 4.4 JudgeCompletedEvent — `_judge_completed`

```python
class JudgeCompletedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    result_id: ResultId
    task_id: TaskId
    judge_verdict: Verdict
    judge_reasoning: str
    judge_time_ms: DurationMs
    judge_completion_tokens: NonNegativeInt | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run the task belongs to. |
| `result_id` | `ResultId` | no | The result row that was judged. |
| `task_id` | `TaskId` | no | The task that was judged. |
| `judge_verdict` | `Verdict` | no | The judge phase's binary outcome — `PASS` or `FAIL`. |
| `judge_reasoning` | `str` | no | The judge's one-sentence explanation. |
| `judge_time_ms` | `DurationMs` | no | Judge call duration. |
| `judge_completion_tokens` | `NonNegativeInt \| None` | yes | Judge call completion tokens; `None` if unreported. |

The judge produces no numeric score; this payload carries only a binary verdict and the reasoning text. There is no score field of any kind.

**Emitter:** benchmark pipeline judge phase. **Subscribers:** Progress widget log. **Thread:** `worker → UI`. **Coalescing:** none.

### 4.5 TaskCompletedEvent — `_task_completed`

```python
class TaskCompletedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
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
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run the task belongs to. |
| `result_id` | `ResultId` | no | The result row that resolved. |
| `task_id` | `TaskId` | no | The task that resolved. |
| `provider_id` | `ProviderId` | no | Provider of the target. |
| `model_name` | `ModelName` | no | Model of the target. |
| `result_status` | `ResultStatus` | no | The terminal status — one of `COMPLETED`, `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, `ERRORED`. |
| `verdict` | `Verdict \| None` | yes | The combined binary verdict; present only when `result_status == COMPLETED` for a graded run, `None` otherwise. |
| `cosine_similarity` | `CosineScore \| None` | yes | The cosine-similarity score (`0.0`–`1.0`); present only for a task that ran a cosine check, `None` otherwise. |
| `total_time_ms` | `DurationMs \| None` | yes | End-to-end inference duration; `None` if inference did not complete. |
| `error_kind` | `ErrorKind \| None` | yes | Failure classification; set only on a terminal-failure status, `None` on `COMPLETED`. |

`result_status` is always one of the six terminal `ResultStatus` members — the five pipeline-position states (`PENDING`, `RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`, `AWAITING_COSINE_CHECK`, `AWAITING_JUDGE_CHECK`) never appear in a `_task_completed` payload. `cosine_similarity` is the only numeric quality value carried; no judge score exists.

**Emitter:** benchmark pipeline, after a task fully resolves. **Subscribers:** Progress widget log, table-data Status Listener. **Thread:** `worker → UI`. **Coalescing:** none.

---

## 5. Run name and run-list payloads

### 5.1 RunIdChangedEvent — `_run_id_changed`

```python
class RunIdChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId | None
    previous_run_id: RunId | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId \| None` | no | The newly selected run; `None` when the selection is cleared. |
| `previous_run_id` | `RunId \| None` | yes | The previously selected run; `None` if there was none. |

The selected run id is also held as state in the run-selection store; this event announces the change moment for transient listeners.

**Emitter:** run-selection controller. **Subscribers:** Result widget, Progress widget, Resume Benchmark widget. **Thread:** `UI → UI`. **Coalescing:** none.

### 5.2 RunListChangedEvent — `_run_list_changed`

```python
class RunListEntry(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    run_name: str
    run_mode: RunMode
    run_status: RunStatus
    created_at: Iso8601Utc

class RunListChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    runs: tuple[RunListEntry, ...]
    change_kind: str
    affected_run_id: RunId | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `runs` | `tuple[RunListEntry, ...]` | no | The full run list after the change, newest-first. |
| `change_kind` | `str` | no | What changed — `created`, `deleted`, or `renamed`. |
| `affected_run_id` | `RunId \| None` | yes | The run created, deleted, or renamed; `None` only for a bulk rebuild. |

`RunListEntry` carries the minimum a list widget needs to render a row without a further query.

**Emitter:** run-registry controller. **Subscribers:** Result widget run dropdown, Resume Benchmark widget run table. **Thread:** `UI → UI`. **Coalescing:** none.

### 5.3 RunRenamedEvent — `_run_renamed`

```python
class RunRenamedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    new_name: str
    previous_name: str | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The renamed run. |
| `new_name` | `str` | no | The new effective display name. |
| `previous_name` | `str \| None` | yes | The prior display name; `None` if the run had no override before. |

**Emitter:** rename use case. **Subscribers:** every widget that displays the run name. **Thread:** `UI → UI`. **Coalescing:** none.

---

## 6. Table and chart data payloads

### 6.1 SummaryDataChangedEvent — `_summary_data_changed`

```python
class SummaryDataChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    row_count: NonNegativeInt
    revision: PositiveInt
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run whose summary dataset changed. |
| `row_count` | `NonNegativeInt` | no | Number of rows in the recomputed summary dataset. |
| `revision` | `PositiveInt` | no | Monotonic revision number; lets a subscriber discard an out-of-order delivery. |

The event signals that the dataset changed; the Summary tab reads the rows themselves from the table-data store keyed by `run_id`. The payload stays small so debouncing is cheap.

**Emitter:** table-data Status Listener. **Subscribers:** Result widget Summary tab. **Thread:** `worker → UI`. **Coalescing:** debounced, 250 ms — only the latest revision is delivered.

### 6.2 DetailedDataChangedEvent — `_detailed_data_changed`

```python
class DetailedDataChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    row_count: NonNegativeInt
    revision: PositiveInt
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run whose detailed dataset changed. |
| `row_count` | `NonNegativeInt` | no | Number of rows in the recomputed detailed dataset. |
| `revision` | `PositiveInt` | no | Monotonic revision number for out-of-order discard. |

**Emitter:** table-data Status Listener. **Subscribers:** Result widget Details tab. **Thread:** `worker → UI`. **Coalescing:** debounced, 250 ms.

### 6.3 ChartDataChangedEvent — `_chart_data_changed`

```python
class ChartDataChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    chart_kind: str
    revision: PositiveInt
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run whose chart dataset changed. |
| `chart_kind` | `str` | no | The `ChartKind` whose aggregation changed. |
| `revision` | `PositiveInt` | no | Monotonic revision number for out-of-order discard. |

The Charts tab reads the recomputed aggregate from the chart-aggregation store keyed by `(run_id, chart_kind)`.

**Emitter:** chart-aggregation Status Listener. **Subscribers:** Result widget Charts tab. **Thread:** `worker → UI`. **Coalescing:** debounced, 250 ms per `(run_id, chart_kind)`.

### 6.4 RunAnalysisReceivedEvent — `_run_analysis_received`

```python
class RunAnalysisReceivedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
    run_mode: RunMode
    analysis_markdown: str
    generated_at: Iso8601Utc
    is_regeneration: bool = False
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run the analysis belongs to. |
| `run_mode` | `RunMode` | no | The run mode; the analysis is consolidated and applies to all three modes. |
| `analysis_markdown` | `str` | no | The single consolidated run-level analysis narrative, as Markdown. |
| `generated_at` | `Iso8601Utc` | no | When the analysis was produced. |
| `is_regeneration` | `bool` | yes | `True` when the analysis replaces an earlier one; `False` on first generation. |

This is the **single** analysis event. It carries the one consolidated run-level analysis narrative for `SYNTHETIC`, `TASKS`, and `GRADED` alike, and corresponds to the single `BenchmarkRun.run_analysis` field. There are no separate performance-analysis or judge-summary events or fields.

**Emitter:** run-analysis use case. **Subscribers:** Result widget Run Analysis tab. **Thread:** `worker → UI`. **Coalescing:** none.

---

## 7. Settings and providers payloads

### 7.1 ProviderRegistryReloadedEvent — `_provider_registry_reloaded`

```python
class ProviderRegistryReloadedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    provider_count: NonNegativeInt
    enabled_provider_ids: tuple[ProviderId, ...]
    reload_cause: str
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `provider_count` | `NonNegativeInt` | no | Total providers in the rebuilt registry. |
| `enabled_provider_ids` | `tuple[ProviderId, ...]` | no | Ids of the providers currently enabled. |
| `reload_cause` | `str` | no | What triggered the reload — `save`, `import`, `reset`, or `reload`. |

The registry itself is held as state in the provider-registry store; this event announces that the state was replaced and why. The payload carries no secret material.

**Emitter:** provider-registry service. **Subscribers:** every widget that lists providers or models. **Thread:** `UI → UI`. **Coalescing:** none.

### 7.2 AppSettingsChangedEvent — `_app_settings_changed`

```python
class AppSettingsChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    changed_keys: tuple[str, ...]
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `changed_keys` | `tuple[str, ...]` | no | The dotted setting keys written in this save. |

The payload carries only the changed keys, never the values; a consumer reads the new value from the settings service. No setting value reaches the bus, so no secret can leak through this event.

**Emitter:** settings service. **Subscribers:** settings consumers that opt into live updates. **Thread:** `UI → UI`. **Coalescing:** none.

### 7.3 InferenceTestCompletedEvent — `_provider_inference_test_completed`

```python
class InferenceTestCompletedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    result: InferenceTestResult
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `result` | `InferenceTestResult` | no | The full result of one user-initiated inference test (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.1a). Carries the classified `outcome`, the `provider_id`, the tested `model_name`, optional `latency_ms`, the redacted `response_excerpt` (on `SUCCESS`), the redacted `last_error` (on failure), and `tested_at`. |

The struct's `response_excerpt` is the first ~200 characters of the model's reply, displayed as-is (the user is reading their own machine's response to a canned prompt). The `last_error`, when present, is the SDK exception text that has already passed through `redact(text)` at the `LLMClient` adapter boundary before the result was constructed (`11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.8.2; `10_Domain_and_Data/08_REDACTION_PATTERNS.md` surface 2). The event fires once per Test inference action (success, failure, or `GATE_BUSY` refusal).

**Emitter:** the controller that ran the test — typically the Provider Edit sub-dialog (`06_Settings_Dialog/sub_dialogs/provider_edit.md` §8.2). **Subscribers:** the Provider Edit sub-dialog (to update its inline display), the Settings dialog Providers tab (to refresh the row summary). **Thread:** `UI → UI`. **Coalescing:** none.

---

## 8. Global and app-readiness payloads

### 8.1 AppReadinessChangedEvent — `_app_readiness_changed`

```python
class ProviderHealthSummary(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    provider_id: ProviderId
    reachable: bool
    discovery_supported: bool
    model_count: int | None
    last_error: str | None = None

class AppReadinessChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    overall: ReadinessState
    per_provider: tuple[ProviderHealthSummary, ...]
    embedding_reachable: bool
    checked_at: Iso8601Utc
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `overall` | `ReadinessState` | no | Aggregate readiness — `READY`, `DEGRADED`, `NOT_READY`, or `CHECKING`. |
| `per_provider` | `tuple[ProviderHealthSummary, ...]` | no | Per-provider reachability summary. Each summary mirrors the new `ProviderHealth` shape (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.1): `discovery_supported` explicitly signals whether the per-provider implementation supports model discovery, and `model_count` is `None` when discovery was not attempted (either because `discovery_supported` is `False`, or the reachability step failed first). |
| `embedding_reachable` | `bool` | no | Whether the configured embedding model is reachable. |
| `checked_at` | `Iso8601Utc` | no | When the snapshot was computed. |

`ProviderHealthSummary.last_error` is redacted before emission. The current snapshot is also held in the readiness state store; this event announces the change. Consumers MUST treat `discovery_supported=False` as healthy (informational), per `11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.5.

**Emitter:** Readiness Service. **Subscribers:** Main Window status bar, Settings dialog readiness section, New Benchmark widget gating. **Thread:** `worker → UI`. **Coalescing:** coalesced; delivered at most twice per second.

### 8.2 InferenceActivityChangedEvent — `_inference_activity_changed`

```python
class InferenceActivityChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    state: InferenceActivityState
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `state` | `InferenceActivityState` | no | The new state of the application-wide single-inference gate. Carries the held `InferenceActivity` and the optional `InferenceActivityContext`. |

The event carries the `InferenceActivityState` the store moved to (see `08_Cross_Cutting/08-E_interfaces_contracts.md` §13 and `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.8). The concrete store publishes it on every acquire/release; the adapter's `qt_event_bus` bridge marshals it onto the Qt main thread. The `InferenceActivityStore` Protocol is method-only (no `psygnal.Signal`); widgets observe this event through the adapter, never the store directly. Every acquire and every release emits one event; no coalescing applies.

**Emitter:** `adapters/qt_inference_activity_bridge/`. **Subscribers:** New Benchmark Start button, Settings dialog Test connection button, Result widget Run Analysis tab (Generate/Regenerate button), Generate Analysis dialog Confirm button. **Thread:** `any → UI`. **Coalescing:** none.

### 8.3 GlobalMessageEvent — `_global_message`

```python
class GlobalMessageEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    text: str
    severity: str = "info"
    duration_ms: DurationMs | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `text` | `str` | no | The redacted message to show in the status-bar toast. |
| `severity` | `str` | yes | `info`, `success`, `warning`, or `error`; selects the toast styling. Default `info`. |
| `duration_ms` | `DurationMs \| None` | yes | How long the toast stays visible; `None` uses the default dwell time. |

`text` must be redacted by the emitter; no secret value reaches the toast.

**Emitter:** any module. **Subscribers:** Main Window status-bar toast region. **Thread:** `any → UI`. **Coalescing:** none.

### 8.4 LogClearedEvent — `_log_cleared`

```python
class LogClearedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    run_id: RunId
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `run_id` | `RunId` | no | The run whose log view is being cleared, at run start. |

**Emitter:** benchmark pipeline, at run start. **Subscribers:** Progress widget log. **Thread:** `worker → UI`. **Coalescing:** none.

---

## 9. Workspace and task-file payloads

### 9.1 WorkspaceChangedEvent — `_workspace_changed`

```python
class WorkspaceChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    workspace: str
    previous_workspace: str | None = None
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `workspace` | `str` | no | The activated workspace — `benchmark` or `task_editor`. |
| `previous_workspace` | `str \| None` | yes | The workspace left; `None` on the first activation. |

The current workspace is also held as state in the workspace store; this event announces the switch.

**Emitter:** Workspace Controller. **Subscribers:** Main Window (menu and status visibility), Task Editor, New Benchmark task-files panel. **Thread:** `UI → UI`. **Coalescing:** none.

### 9.2 TaskFileChangedEvent — `_task_file_changed`

```python
class TaskFileChangedEvent(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    path: str
    task_count: NonNegativeInt
    change_kind: str
```

| Field | Type | Optional | Meaning |
|---|---|:--:|---|
| `path` | `str` | no | The absolute path of the YAML task file that changed. |
| `task_count` | `NonNegativeInt` | no | Number of valid tasks in the file after the save. |
| `change_kind` | `str` | no | What happened — `saved` or `created`. |

**Emitter:** Task Editor controller, on Save. **Subscribers:** New Benchmark task-files panel (recount tasks), Resume Benchmark widget (refresh runs whose snapshot used the file). **Thread:** `UI → UI`. **Coalescing:** none.
