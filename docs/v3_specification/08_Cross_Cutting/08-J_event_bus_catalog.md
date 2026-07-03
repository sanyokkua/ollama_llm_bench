# Event Bus Catalog

**Status:** Draft
**Owner:** coder
**Audience:** coder, arch
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-Q_event_payload_schemas.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `08_Cross_Cutting/08-A_architecture_principles.md`

This document is the authoritative catalog of every one-shot domain event carried by the typed Event Bus. It lists every event name, its purpose, its payload type, the module(s) that emit it, the module(s) that subscribe to it, the threading rule that governs delivery, and any coalescing or debounce rule. It also defines the responsibility split between the Event Bus and the scoped reactive state stores: cross-widget *state* lives in state stores, while one-shot *domain events* travel on the Event Bus. The payload structs themselves are defined field-by-field in `08-Q_event_payload_schemas.md`; this file is the routing map and ownership contract.

---

## Table of Contents

1. Responsibility split — event bus versus state stores
2. Subscription ownership-binding rule
3. Threading model
4. Coalescing and debounce
5. Event catalog
   - 5.1 Run lifecycle
   - 5.2 Stage and progress
   - 5.3 Per-task events
   - 5.4 Run name and run-list changes
   - 5.5 Table and chart data changed
   - 5.6 Settings and providers changed
   - 5.7 Global and app-readiness
   - 5.8 Workspace and task-file events
6. When to add a new event
7. Event-to-payload index

---

## 1. Responsibility split — event bus versus state stores

The application separates two kinds of cross-component communication. Choosing the wrong channel produces either stale UI (state pushed as a fire-and-forget event) or event storms (state changes broadcast every tick). The split is binding.

**Scoped reactive state stores hold cross-widget STATE.** A state store owns a value that more than one widget must observe and that has a current, queryable value at any moment. A widget mounted after the value last changed must still read the correct value. Examples: the currently selected run id, the current run-list, the live provider registry, the current app-readiness snapshot, the current workspace. A widget subscribes to a store and is given the present value immediately on subscription, then every subsequent change. State stores are defined in `11_Services_and_Algorithms` and consumed per-widget as documented in each widget's `implementation_structure.md`.

**The Event Bus carries one-shot DOMAIN events.** An event is a fact that something *happened* at a moment in time. It has no current value; a widget that was not subscribed when it fired has missed it permanently and that is correct behaviour. Examples: a benchmark started, a task completed, an analysis was received, a toast message must be shown. Events are transient signals, never the source of truth for any displayed value.

**Practical rule.** If a widget mounted late would need the value, it is state — put it in a store. If a widget mounted late should not care that it missed the moment, it is an event — put it on the bus. Several concerns appear in both channels by design: the selected run id is *state* in the run-selection store and is also announced as the `_run_id_changed` *event* so transient listeners (a log line, a toast) can react to the change moment without subscribing to the store. The store is the source of truth; the event is the notification.

The event catalog in section 5 lists only Event Bus events. State stores are out of scope for this file.

**Provider identity on the bus (DD-33).** Every event payload that names a provider carries the internal `provider_id` (UUID4) for **linkage** — it is the stable, rename-proof handle the receiver uses to correlate the event with a benchmark row, a settings entry, or a registry client. The payload does NOT carry the user-visible `name`. Subscribers render the name on a payload as follows: a subscriber rendering an event that belongs to a completed run (a re-emitted historical event, a Result-widget refresh) resolves the name from the relevant run-snapshot field (`BenchmarkRun.judge_provider_name`, `BenchmarkRun.embedding_provider_name`, `BenchmarkRun.embedding_model_name`, or `BenchmarkResult.provider_name`); a subscriber rendering an event tied to a live activity (the in-flight Progress widget, the Settings provider table, the inference-test panel) resolves the name from the live registry (the `ProviderRegistry` / `ProvidersStore`). The same rule applies to the `judge_provider_id` payload field wherever it appears. This means a run-scoped subscriber that opens an old completed run sees the SNAPSHOT name; an in-flight subscriber on the same provider sees the CURRENT name. Renaming a provider mid-session never poisons the event payloads themselves, because the payloads carry only the rename-stable id.

---

## 2. Subscription ownership-binding rule

Every `subscribe` call MUST pass an owner object whose lifetime bounds the subscription. The Event Bus binds the subscription to that owner and auto-cancels it when the owner is destroyed.

- A widget subscribes with itself (or its controller) as the owner. When the widget is destroyed, the bus drops the subscription before the next emit can reach a half-destroyed object.
- A controller or service subscribes with itself as the owner and is responsible for living at least as long as it needs the events.
- A subscription with no owner is a programming error and is rejected at subscribe time.

This rule eliminates zombie subscriptions — callbacks firing on objects whose Qt C++ half has already been deleted — which are otherwise the most common crash class in a long-lived desktop session that creates and destroys widgets repeatedly (for example, the Result widget rebuilt on every run switch).

Ownership binding is also why no event needs an explicit unsubscribe in normal code: destroying the owner is the unsubscribe.

---

## 3. Threading model

The benchmark pipeline and provider clients run on `QThreadPool` worker threads; the UI runs on the single Qt GUI thread. The Event Bus is the thread boundary — the adapter's Qt bridge re-emits each event onto the GUI thread via a queued signal/slot connection (per D-R-01).

- **Any thread may emit.** A worker thread or GUI code may call `emit`; the bus marshals delivery onto the GUI thread.
- **Delivery is always marshalled to the UI thread.** The bus queues every emission and delivers each subscriber callback on the UI thread. A subscriber callback therefore never needs its own locking and may touch widgets directly.
- **Emission is non-blocking.** `emit` returns immediately; the emitter never waits for subscribers.
- **Ordering is preserved per emitter.** Events emitted in sequence by one emitter are delivered in that sequence. No global ordering is guaranteed across emitters.
- **Dispatcher-emitted run-domain events are totally ordered (MISS-28).** Because the benchmark executes strictly serially on the single dedicated dispatcher thread (D-R-16, DD-38, `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` §6.1a/§6.2), the events the dispatcher emits — `_run_*` lifecycle, `_stage_changed`, `_task_completed`, `_judge_model_excluded`, and `_model_stability_changed` (the Adaptive Timeout Service and the Provider Circuit Breaker are consulted and updated only on the dispatcher, DD-38/DD-40) — are all emitted by that one thread in program order. Per-emitter ordering therefore gives a **total order** over this set, and the obvious happens-before holds: a `_judge_model_excluded` or `_model_stability_changed` that causes subsequent tasks to settle is always delivered before the `_task_completed` events of those tasks. Subscribers may rely on this ordering for these events.
- **`_inference_progress` is NOT part of that total order.** It is emitted by the **inference unit's worker thread** (the synchronous `emit_progress_during(...)` helper, `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9), not by the dispatcher, so it has no ordering relationship to the dispatcher-emitted set in general. It is a **best-effort, latest-wins** signal: subscribers must treat each snapshot idempotently and key only off the most recent one (the Progress widget already does — its sub-states read "the latest snapshot" and each sub-row is replaced on the next `_inference_started`, `04_Progress_Widget/description.md` §7.1). The one ordering guarantee that does hold and that subscribers may rely on: **a task's own `_inference_progress` emissions all precede that task's `_task_completed`.** This follows from the `Future` handoff barrier — the worker emits every snapshot, then returns the `ChatResponse`; the `Future` resolves; only then does the dispatcher read it, persist, and emit `_task_completed` — and Qt's `postEvent` preserves enqueue order across that synchronization point. So the widget never sees a task's progress arrive after that same task's completion.
- The "no cross-emitter ordering" caveat applies across genuinely independent emitters (e.g. a readiness probe vs. an unrelated UI action) and to `_inference_progress` relative to anything other than its own task's `_task_completed`.

Each event in section 5 declares one of three threading rules:

| Rule | Meaning |
|---|---|
| `worker → UI` | Emitted from a background worker (pipeline phase, provider client, probe); delivered on the UI thread. |
| `UI → UI` | Emitted from UI-thread code (a controller, a menu action); delivered on the UI thread. |
| `any → UI` | May be emitted from either; always delivered on the UI thread. |

---

## 4. Coalescing and debounce

High-frequency events would flood the UI thread and cause table and chart repaints faster than a human can perceive. Two mechanisms bound the rate.

- **Debounce.** The emitter (or a Status Listener sitting in front of subscribers) holds the most recent payload and emits at most once per debounce window, discarding intermediate payloads. Used for table-data and chart-data events, where only the latest snapshot matters.
- **Coalescing.** Multiple rapid emissions of the same logical change collapse into one delivery carrying the final state. Used for progress updates.

Each event in section 5 declares its coalescing/debounce rule explicitly. Events that fire at most a few times per run (lifecycle, analysis received, run renamed) declare `none` — every emission is delivered.

The default debounce window for table and chart data events is 250 ms; it is a tunable constant, not a magic number scattered across modules.

---

## 5. Event catalog

Every event name is prefixed with a leading underscore by convention, marking it as an Event Bus channel identifier rather than an ordinary attribute. Payload type names without the underscore are the `msgspec.Struct` types defined in `08-Q_event_payload_schemas.md`.

### 5.1 Run lifecycle

Fired once each at the boundaries of a run's execution. All declare coalescing `none`.

| Event | Purpose | Payload | Emitter | Subscribers | Thread | Coalescing |
|---|---|---|---|---|---|---|
| `_run_started` | A run's pipeline began executing; mark the UI as run-in-progress. | `RunStartedEvent` | benchmark pipeline | Progress widget, Main Window, Result widget | `worker → UI` | none |
| `_run_start_failed` | Run **creation** failed before the pipeline began (a snapshot-build or persistence write failed, or the single-inference gate could not be acquired); the creation transaction rolled back and no `benchmark_runs` row persists. | `RunStartFailedEvent` | run-creation use case | New Benchmark widget, Main Window | `worker → UI` | none |
| `_run_paused` | The pipeline finished the in-flight task and halted; the run is pausable-resumable. | `RunPausedEvent` | benchmark pipeline pause handler | Progress widget, Main Window | `worker → UI` | none |
| `_run_resumed` | A paused run resumed execution. | `RunResumedEvent` | benchmark pipeline resume handler | Progress widget, Main Window | `worker → UI` | none |
| `_run_stopped` | The user stopped the run before completion; the persisted `RunStatus` becomes `STOPPED`. | `RunStoppedEvent` | benchmark pipeline stop handler | Progress widget, Main Window, Result widget | `worker → UI` | none |
| `_run_finished` | Every result reached a terminal status and the run finished normally; persisted `RunStatus` becomes `COMPLETED`. | `RunFinishedEvent` | benchmark pipeline terminal handler | Progress widget, Result widget, Main Window | `worker → UI` | none |
| `_run_failed` | A fatal pipeline error halted the run; persisted `RunStatus` becomes `FAILED`. | `RunFailedEvent` | benchmark pipeline exception handler | Progress widget, Main Window, Result widget | `worker → UI` | none |

`Pause` finishes the in-flight task before `_run_paused` fires; the event therefore always arrives on a clean per-task boundary, never mid-inference. The persisted `RunStatus` enum has four members — `INCOMPLETE`, `COMPLETED`, `FAILED`, `STOPPED` — and the transient `RUNNING`/`PAUSED` distinction is in-memory only and is communicated through these lifecycle events, never persisted.

### 5.2 Stage and progress

The five-phase batched pipeline announces its stage transitions and its aggregate progress.

| Event | Purpose | Payload | Emitter | Subscribers | Thread | Coalescing |
|---|---|---|---|---|---|---|
| `_stage_changed` | The pipeline advanced to a new phase of the five-phase batched pipeline. | `StageChangedEvent` | benchmark pipeline stage controller | Progress widget | `worker → UI` | none |
| `_progress_updated` | Aggregate run progress changed — completed count, totals, current target, per-status counts. | `ProgressUpdatedEvent` | benchmark pipeline, after each per-task status transition | Progress widget | `worker → UI` | coalesced, ≤10/s |
| `_provider_switched` | The pipeline moved to a different provider for the next batch. | `ProviderSwitchedEvent` | benchmark pipeline | Progress widget (log line) | `worker → UI` | none |
| `_model_switched` | The pipeline moved to a different model for the next batch. | `ModelSwitchedEvent` | benchmark pipeline | Progress widget (log line) | `worker → UI` | none |
| `_task_retry` | A failed task is being retried; carries the attempt count and reason. | `TaskRetryEvent` | benchmark pipeline retry loop | Progress widget | `worker → UI` | none |
| `_model_stability_changed` | The adaptive-timeout state for a `(provider_id, model_name, role)` bucket or the provider circuit-breaker state changed. Emitted **per role** — a test model and a judge model are tracked separately and can each fire this event independently. | `ModelStabilityChangedEvent` | Adaptive Timeout Service, Provider Circuit Breaker | Progress widget (stability boxes) | `worker → UI` | none |
| `_judge_model_excluded` | The role=JUDGE bucket for the run's judge `(provider_id, model_name)` crossed the consecutive-max-timeout threshold (`eval.judge_timeout_consecutive_threshold`); every remaining task that would have entered the judge phase will settle to `FAILED_JUDGE_TIMEOUT`. Fires **at most once per `BENCHMARK_RUN` activity** (`RunAnalysisService` exhaustion uses the `RunAnalysisResult.outcome=FAILED` channel, NOT this event — see §6 below). | `JudgeModelExcludedEvent` | benchmark pipeline Phase 4 (judge), on the transition from `not excluded` to `excluded` in the role=JUDGE bucket | Progress widget Event Log (`04_Progress_Widget/description.md`), Result widget Status Listener | `worker → UI` | none |

`_progress_updated` is the only high-frequency event in this group; it is coalesced so the Progress widget repaints at most ten times per second regardless of how fast tasks resolve. The other events fire only on genuine transitions and are delivered every time.

`_judge_model_excluded` is the judge-role analogue of the test-role exclusion already carried by `_model_stability_changed` (whose `model_state` field can reach `EXCLUDED` for a role=INFERENCE target). It exists as a dedicated event because judge exclusion is a discrete one-shot user-facing fact — the Progress widget Event Log renders it as a single warning row "Judge model '<name>' excluded: <N> consecutive max-budget timeouts. Remaining tasks' judge phase will be skipped." — and the dedicated payload (`JudgeModelExcludedEvent`) carries the affected-task count that the test-role exclusion path does not. The two channels never overlap: a test-role exclusion fires `_model_stability_changed` (with `model_state = EXCLUDED`); a judge-role exclusion fires `_judge_model_excluded`. Both can be active in the same run when the same `(provider, model)` was selected as both a test model AND the judge model — the two role buckets are independent.

### 5.3 Per-task events

Fine-grained events consumed primarily by the Progress widget's log sub-controller. They report the lifecycle of a single `BenchmarkResult` as it moves through the pipeline.

| Event | Purpose | Payload | Emitter | Subscribers | Thread | Coalescing |
|---|---|---|---|---|---|---|
| `_inference_started` | An inference call for one task began. | `InferenceStartedEvent` | benchmark pipeline inference phase | Progress widget (log) | `worker → UI` | none |
| `_inference_progress` | A heartbeat snapshot of one in-flight LLM call from any of four user-visible surfaces (per-task main inference, per-task judge call, run-analysis generation, Provider Edit test inference): counters only — elapsed time, running `tokens_received`, and the `first_token_received` flag, plus an `InferenceContext` discriminator. **No model text crosses this boundary as a chunk event** — the response-text accumulator stays inside the emitter's scope. | `InferenceProgressEvent` | the shared `emit_progress_during(...)` helper (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9) invoked by four emitters: Benchmark Pipeline per-task main inference (`context=BENCHMARK_TASK`), Benchmark Pipeline per-task judge call (`context=BENCHMARK_JUDGE`), Run Analysis Service (`context=RUN_ANALYSIS`), Provider `LLMClient.test_inference` flow (`context=PROVIDER_TEST`). **Readiness probes (`probe_health()`) do NOT emit this event** — they are invisible background checks (`11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.2). | Three subscribers, each filtering by `context`: Progress widget Current-task controller (accepts `BENCHMARK_TASK` + `BENCHMARK_JUDGE`; `04_Progress_Widget/description.md` §7.1), Generate Analysis dialog (accepts `RUN_ANALYSIS` and matches `run_id`; `07_Common_Dialogs/generate_analysis_dialog.md` §8), Provider Edit inference-test panel (accepts `PROVIDER_TEST` and matches `provider_id`; `06_Settings_Dialog/sub_dialogs/provider_edit.md` §8.2). | `worker → UI` (marshalled to the Qt main thread via `adapters/qt_event_bus/`) | coalesced, ≥ 1 Hz per in-flight call |
| `_inference_completed` | An inference call for one task finished; carries timing and token counts. | `InferenceCompletedEvent` | benchmark pipeline inference phase | Progress widget (log) | `worker → UI` | none |
| `_judge_started` | The per-task judge phase began evaluating one task. Emitted only when the per-task judge phase runs — that is, only in `GRADED` with `eval.phase_judge_enabled` on. Never emitted in `TASKS` or `SYNTHETIC`. | `JudgeStartedEvent` | benchmark pipeline judge phase | Progress widget (log) | `worker → UI` | none |
| `_judge_completed` | The per-task judge phase finished one task; carries the binary judge verdict and the judge's reasoning. The judge produces no numeric score. Emitted only when the per-task judge phase runs — `GRADED` only. | `JudgeCompletedEvent` | benchmark pipeline judge phase | Progress widget (log) | `worker → UI` | none |
| `_task_completed` | One task reached a terminal `ResultStatus`; carries the final status and, when graded, the combined binary verdict. | `TaskCompletedEvent` | benchmark pipeline, after a task fully resolves | Progress widget (log), table-data Status Listener | `worker → UI` | none |

`_task_completed` carries the terminal `ResultStatus` (one of the eleven `ResultStatus` members — five pipeline-position states never appear here; only the six terminal states `COMPLETED`, `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, `ERRORED` do) and an optional `Verdict`. The verdict is `PASS` or `FAIL` only when `status == COMPLETED` for a graded run; it is absent otherwise. No event in this group carries a judge score; the only numeric quality value anywhere in the system is the cosine similarity, carried as `cosine_similarity` on per-task and detail payloads and absent for tasks with no cosine check.

### 5.4 Run name and run-list changes

Run identity and the run-list catalog change through dedicated events. The *current* run-list and the *current* selected run id are also held as state in the run-selection store (see section 1); these events announce the change moment.

| Event | Purpose | Payload | Emitter | Subscribers | Thread | Coalescing |
|---|---|---|---|---|---|---|
| `_run_id_changed` | The currently selected run changed (selection, or auto-select on start). | `RunIdChangedEvent` | run-selection controller | Result widget, Progress widget, Resume Benchmark widget | `UI → UI` | none |
| `_run_list_changed` | The set of runs changed — a run was created, deleted, or renamed. | `RunListChangedEvent` | run-registry controller | Result widget run dropdown, Resume Benchmark widget run table | `UI → UI` | none |
| `_run_renamed` | A run's display name changed. | `RunRenamedEvent` | rename use case | every widget that displays the run name | `UI → UI` | none |

`_run_renamed` fires in addition to `_run_list_changed` on a rename: `_run_list_changed` lets list widgets rebuild their rows, while `_run_renamed` lets a widget showing a single name (a title bar, a tab label) update without rebuilding a list.

### 5.5 Table and chart data changed

The Result widget's tables and charts are repainted when the underlying result data changes. These events are debounced because a running benchmark mutates result rows continuously.

| Event | Purpose | Payload | Emitter | Subscribers | Thread | Coalescing |
|---|---|---|---|---|---|---|
| `_summary_data_changed` | The summary-table dataset for a run changed. | `SummaryDataChangedEvent` | table-data Status Listener | Result widget Summary tab | `worker → UI` | debounced, 250 ms |
| `_detailed_data_changed` | The detailed-table dataset for a run changed. | `DetailedDataChangedEvent` | table-data Status Listener | Result widget Details tab | `worker → UI` | debounced, 250 ms |
| `_chart_data_changed` | A chart's aggregated dataset for a run changed. | `ChartDataChangedEvent` | chart-aggregation Status Listener | Result widget Charts tab | `worker → UI` | debounced, 250 ms |
| `_run_analysis_received` | The consolidated run-level analysis narrative for a run is available. | `RunAnalysisReceivedEvent` | run-analysis use case | Result widget Run Analysis tab | `worker → UI` | none |

There is exactly **one** analysis event: `_run_analysis_received`. It carries the single consolidated run-level analysis narrative for every run mode — `SYNTHETIC`, `TASKS`, and `GRADED`. There are no separate performance-analysis and judge-summary events; the consolidated event and the single `BenchmarkRun.run_analysis` field replace both. It fires once when the analysis completes, and again after each regeneration.

### 5.6 Settings and providers changed

| Event | Purpose | Payload | Emitter | Subscribers | Thread | Coalescing |
|---|---|---|---|---|---|---|
| `_provider_registry_reloaded` | The provider registry was rebuilt — after a save, import, reset, or reload. | `ProviderRegistryReloadedEvent` | provider-registry service | every widget that lists providers or models | `UI → UI` | none |
| `_app_settings_changed` | One or more application settings were written. | `AppSettingsChangedEvent` | settings service | Result widget `FooterController` (re-reads `ui.export_save_directly` to show/hide the Open Exports Folder button on every footer); the application theme controller (re-reads `ui.theme` to re-apply the palette). No other live subscriber exists today — every other setting is snapshotted at run-creation time, so any future live consumer must be named here when added. | `UI → UI` | none |
| `_provider_inference_test_completed` | A user-initiated end-to-end inference test (Provider Edit dialog's Test inference action) returned its `InferenceTestResult`. | `InferenceTestCompletedEvent` | the controller that ran the test (Provider Edit sub-dialog) | Provider Edit sub-dialog (to update its inline display), Settings dialog Providers tab (to refresh the row summary in the providers table) | `UI → UI` | none |

`_provider_registry_reloaded` announces that the registry *state* was replaced; the current registry value itself lives in the provider-registry state store, and most widgets read it from there. The event exists for transient reactions (refreshing a dropdown, clearing a stale selection). `_app_settings_changed` carries only the set of changed keys; consumers read the new values from the settings service. Most settings are read at run-creation time and snapshotted into the run, so live-update subscribers to `_app_settings_changed` are rare.

`_provider_inference_test_completed` is fired exactly once per Test inference action (success, failure, or gate-busy refusal). The reachability probe (`LLMClient.probe_health()`) has no dedicated event: the Settings dialog reads the result synchronously from the call and updates its UI directly, and the broader app already observes provider-reachability changes via `_app_readiness_changed`.

### 5.7 Global and app-readiness

| Event | Purpose | Payload | Emitter | Subscribers | Thread | Coalescing |
|---|---|---|---|---|---|---|
| `_app_readiness_changed` | The aggregate app-readiness snapshot changed (provider/embedding reachability). | `AppReadinessChangedEvent` | Readiness Service | Main Window status bar, Settings dialog readiness section, New Benchmark widget gating | `worker → UI` | coalesced, ≤2/s |
| `_inference_activity_changed` | The application-wide single-inference gate changed: an activity acquired the gate or released it. | `InferenceActivityChangedEvent` | the `InferenceActivityStore` concrete store, on every acquire/release (Protocol is method-only; the adapter's `qt_event_bus` bridge marshals to the GUI thread) | New Benchmark Start button, Settings dialog Test connection button, Result widget Run Analysis tab (Generate/Regenerate button), Generate Analysis dialog Confirm button, status-bar diagnostic when present | `any → UI` | none |
| `_global_message` | A transient user-facing message must be shown as a status-bar toast. | `GlobalMessageEvent` | any module | Main Window status-bar toast region | `any → UI` | none |
| `_log_cleared` | The Progress widget log must be cleared (fired at run start). | `LogClearedEvent` | benchmark pipeline, at run start | Progress widget (log) | `worker → UI` | none |

The current readiness *snapshot* is also state, held in the readiness state store and consulted directly by the New Benchmark widget when it decides whether a mode may start. `_app_readiness_changed` is the change notification; it is coalesced because background probes can resolve in quick succession.

### 5.8 Workspace and task-file events

The application has two workspaces — the Benchmark workspace and the Task Editor workspace. Workspace and task-file changes are announced as events; the *current* workspace is also held as state in the workspace store.

| Event | Purpose | Payload | Emitter | Subscribers | Thread | Coalescing |
|---|---|---|---|---|---|---|
| `_workspace_changed` | The active workspace switched between the Benchmark workspace and the Task Editor workspace. | `WorkspaceChangedEvent` | Workspace Controller | Main Window (menu and status visibility), Task Editor (resume), New Benchmark task-files panel (refresh dirty markers) | `UI → UI` | none |
| `_task_file_changed` | A YAML task file was saved to disk. | `TaskFileChangedEvent` | Task Editor controller, on Save | New Benchmark task-files panel (recount tasks), Resume Benchmark widget (refresh runs that used the file) | `UI → UI` | none |

`_task_file_changed` lets the Benchmark workspace stay consistent with edits made in the Task Editor workspace without polling the filesystem: the New Benchmark task-files panel recounts the tasks in the changed file, and the Resume Benchmark widget refreshes its row for any listed run whose snapshot referenced that file path.

---

## 6. When to add a new event

Apply this decision tree before adding a channel to the Event Bus.

1. **Is the data a current value a late-mounted widget would need?** Then it is state — put it in a scoped reactive state store, not on the bus. (Section 1.)
2. **Is the data needed by exactly one widget and never crosses a widget boundary?** Then keep it inside that widget's own local signal mechanism; do not add a bus channel.
3. **Is the data a one-shot fact shared by two or more widgets or controllers?** Then add a bus event: define its payload struct in `08-Q_event_payload_schemas.md`, add a row to the matching catalog table in section 5, and declare its emitter, subscribers, threading rule, and coalescing rule.
4. **Will the event fire faster than roughly 100 times per second?** Then it MUST declare a coalescing or debounce rule and route through a Status Listener; an un-throttled high-frequency event is rejected in review.

Removing or merging a channel follows the same discipline in reverse: update both this file and `08-Q_event_payload_schemas.md` in the same change so the catalog and the schemas never diverge.

---

## 7. Event-to-payload index

Every event maps one-to-one to a payload struct. The struct field definitions are in `08-Q_event_payload_schemas.md`.

| Event | Payload struct |
|---|---|
| `_run_started` | `RunStartedEvent` |
| `_run_start_failed` | `RunStartFailedEvent` |
| `_run_paused` | `RunPausedEvent` |
| `_run_resumed` | `RunResumedEvent` |
| `_run_stopped` | `RunStoppedEvent` |
| `_run_finished` | `RunFinishedEvent` |
| `_run_failed` | `RunFailedEvent` |
| `_stage_changed` | `StageChangedEvent` |
| `_progress_updated` | `ProgressUpdatedEvent` |
| `_provider_switched` | `ProviderSwitchedEvent` |
| `_model_switched` | `ModelSwitchedEvent` |
| `_task_retry` | `TaskRetryEvent` |
| `_model_stability_changed` | `ModelStabilityChangedEvent` |
| `_judge_model_excluded` | `JudgeModelExcludedEvent` |
| `_inference_started` | `InferenceStartedEvent` |
| `_inference_progress` | `InferenceProgressEvent` |
| `_inference_completed` | `InferenceCompletedEvent` |
| `_judge_started` | `JudgeStartedEvent` |
| `_judge_completed` | `JudgeCompletedEvent` |
| `_task_completed` | `TaskCompletedEvent` |
| `_run_id_changed` | `RunIdChangedEvent` |
| `_run_list_changed` | `RunListChangedEvent` |
| `_run_renamed` | `RunRenamedEvent` |
| `_summary_data_changed` | `SummaryDataChangedEvent` |
| `_detailed_data_changed` | `DetailedDataChangedEvent` |
| `_chart_data_changed` | `ChartDataChangedEvent` |
| `_run_analysis_received` | `RunAnalysisReceivedEvent` |
| `_provider_registry_reloaded` | `ProviderRegistryReloadedEvent` |
| `_app_settings_changed` | `AppSettingsChangedEvent` |
| `_provider_inference_test_completed` | `InferenceTestCompletedEvent` |
| `_app_readiness_changed` | `AppReadinessChangedEvent` |
| `_inference_activity_changed` | `InferenceActivityChangedEvent` |
| `_global_message` | `GlobalMessageEvent` |
| `_log_cleared` | `LogClearedEvent` |
| `_workspace_changed` | `WorkspaceChangedEvent` |
| `_task_file_changed` | `TaskFileChangedEvent` |
