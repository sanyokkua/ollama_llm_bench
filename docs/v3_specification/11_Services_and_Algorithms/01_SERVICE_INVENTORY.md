# Service Inventory

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` through `11_Services_and_Algorithms/18_RETRY_POLICY.md` (every algorithm spec in this folder), `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`

This document is the master index of every backend service, helper, and module in
Ollama LLM Bench. It is the single place an engineer or the implementation agent looks
to answer the question "what services exist, what does each do, how is it threaded, and
where is its algorithm specified". Every service contract named here is defined
authoritatively as a `typing.Protocol` (or a function group) in
`08_Cross_Cutting/08-E_interfaces_contracts.md`; every DTO and enum named here is defined
authoritatively in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`. This inventory references
those names and never redefines them.

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [How to Read This Inventory](#2-how-to-read-this-inventory)
3. [Master Service Table](#3-master-service-table)
4. [Service Notes](#4-service-notes)
5. [Module Ownership and Construction](#5-module-ownership-and-construction)
6. [Test-Double Convention](#6-test-double-convention)

---

## 1. Purpose and Scope

The backend of Ollama LLM Bench is a set of replaceable, headless-runnable services. Each
service has exactly one responsibility, a single `Protocol` contract, one concrete
implementation, and one test double. Every service is constructed once at startup by the
composition root and is handed to consumers by constructor injection through the
`ApplicationContext`; no widget ever instantiates a concrete service.

This inventory covers three kinds of backend component:

- **Contract services** — components with a `typing.Protocol` in
  `08_Cross_Cutting/08-E_interfaces_contracts.md` and a handle on `ApplicationContext`.
- **Internal services** — components with no `ApplicationContext` handle that are owned
  and used by a contract service (for example the synthetic-task generator, owned by the
  run-creation use case). They have a stated public surface but no top-level Protocol.
- **Pure modules** — stateless function groups (for example the redaction module, the
  model-name parser). They have a function-signature contract, not a Protocol.

The pipeline phases (initialisation, inference, keyword, cosine, judge) and the five-phase
batched scheduler are not themselves separate services; they are stages inside the
Benchmark Pipeline. Their algorithms are specified in
`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` and
`11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`.

---

## 2. How to Read This Inventory

The master table columns mean:

| Column | Meaning |
|---|---|
| **Service** | The component name used throughout the specification. |
| **Kind** | `contract` (has a Protocol + `ApplicationContext` handle), `internal` (owned by a contract service), or `module` (pure function group). |
| **Protocol / module path** | The Python import path of the Protocol or module. Concrete implementations live under the same package's `_internal/` and are never imported directly. |
| **Purpose** | One sentence: the single responsibility. |
| **Key methods** | The principal method names. The full typed contract is in `08-E`. |
| **Threading** | `fast-sync` (returns quickly, callable from the GUI thread) or `blocking` (network/CPU work invoked on a `TaskRunner` worker thread). All backend methods are synchronous `def` — there is no event loop (D-R-01). |
| **Faked in tests by** | The module path of the deterministic test double. |
| **Algorithm spec** | The `11_Services_and_Algorithms/` file that specifies the non-trivial algorithm, or `—` when the behaviour is fully captured by the contract in `08-E`. |

The threading rule is binding: it is the rule restated per service in `08-E` Section 4
and enforced by the architecture tests in `12_Quality_and_NFRs/`.

---

## 3. Master Service Table

| Service | Kind | Protocol / module path | Purpose | Key methods | Threading | Faked in tests by | Algorithm spec |
|---|---|---|---|---|---|---|---|
| Clock | contract | `backend.infra.protocols.Clock` | Provide an injectable UTC time source and a monotonic millisecond counter. | `now_utc`, `monotonic_ms` | fast-sync | `backend/infra/testing.py` | — |
| EventBus | contract | `backend.events.protocols.EventBus` | Cross-component publish/subscribe channel; the only cross-thread delivery path. | `subscribe`, `emit` | fast-sync (`emit` callable from any thread) | `backend/events/testing.py` | — |
| RunsStore | contract | `backend.persistence.runs.protocols.RunsStore` | Durable-state gateway for `BenchmarkRun` aggregate rows. | `create_run`, `get_run`, `list_runs`, `update_run_status`, `rename_run`, `delete_run` | fast-sync | `backend/persistence/runs/testing.py` | — |
| TasksStore | contract | `backend.persistence.tasks.protocols.TasksStore` | Durable-state gateway for `BenchmarkTask` aggregate rows. | `create_tasks`, `list_tasks` | fast-sync | `backend/persistence/tasks/testing.py` | — |
| ResultsStore | contract | `backend.persistence.results.protocols.ResultsStore` | Durable-state gateway for `BenchmarkResult` aggregate rows, including the crash-recovery sweep. | `create_results`, `update_result`, `list_results`, `list_resumable_results`, `reset_results`, `recover_in_flight_results` | fast-sync | `backend/persistence/results/testing.py` | — |
| ProvidersStore | contract | `backend.persistence.providers.protocols.ProvidersStore` | Durable-state gateway for the provider catalog. **Owns `provider_id` generation** — `add(draft) -> ProviderId` returns the freshly-generated UUID4 (DD-33). Enforces `UNIQUE (name)`; `get_by_name` is the friendly duplicate-name lookup used by the dialog and the importer. | `list_providers`, `get_by_name`, `add(draft) -> ProviderId`, `update(provider_id, config)`, `delete(provider_id)`, `replace_providers(configs)` | fast-sync | `backend/persistence/providers/testing.py` | — |
| ModelCapabilitiesStore | contract | `backend.persistence.model_capabilities.protocols.ModelCapabilitiesStore` | Durable-state gateway for the per-`(provider, model)` capability observation cache. | `list_model_capabilities`, `upsert_model_capability` | fast-sync | `backend/persistence/model_capabilities/testing.py` | — |
| AppSettingsStore | contract | `backend.persistence.app_settings.protocols.AppSettingsStore` | Durable-state gateway for the typed user-saved settings layer and the `app_meta` schema-version row. | `get_setting`, `upsert_settings`, `list_settings`, `get_schema_version` | fast-sync | `backend/persistence/app_settings/testing.py` | — |
| SettingsService | contract | `backend.settings.protocols.SettingsService` | Typed access to the user-saved + default layers of the settings hierarchy. | `get_str`, `get_bool`, `get_int`, `get_float`, `set`, `upsert` | fast-sync | `backend/settings/testing.py` | — |
| RunSnapshotBuilder | contract | `backend.settings.protocols.RunSnapshotBuilder` | Capture the per-run-overridable settings keys into the frozen `BenchmarkRunSettingEntry` tuple at run start, so a run reads a stable settings view for its whole lifetime. | `build_snapshot` | fast-sync | `backend/settings/testing.py` | — |
| ProviderRegistry | contract | `backend.provider_registry.protocols.ProviderRegistry` | Own one `LLMClient` per provider; route a `(provider_id, model_name)` target to its client. | `list_enabled`, `get_client`, `reload` | fast-sync | `backend/provider_registry/testing.py` | `03_PROVIDER_REGISTRY.md` |
| LLMClient | contract (per-provider) | `backend.provider_registry.protocols.LLMClient` | Unified provider-facing chat, embedding, and capability surface; wraps the provider SDK and translates its exceptions. `probe_health` is a reachability + conditional-discovery probe (no inference); `test_inference` is a user-initiated end-to-end chat call against one named model. | `list_models`, `probe_health`, `test_inference`, `chat`, `embed`, `supports_streaming`, `supports_reasoning_effort`, `supports_thinking` | mixed (`chat`/`embed`/`list_models`/`probe_health`/`test_inference` blocking; `supports_*` fast-sync) | `backend/provider_registry/testing.py` | `02_LLM_CLIENT_PROTOCOL.md` |
| BenchmarkFlowApi | contract | `backend.benchmark_pipeline.protocols.BenchmarkFlowApi` | Single backend entry point that drives a run to a terminal status; never raises to its caller. | `start`, `resume`, `pause`, `resume_paused`, `stop`, `shutdown`, `is_running`, `current_run` | mixed (`start`/`resume`/`shutdown` blocking; control and query methods fast-sync) | `backend/benchmark_pipeline/testing.py` | `04_EVALUATION_PIPELINE.md`, `16_CONCURRENCY_MODEL.md` |
| ReadinessService | contract | `backend.readiness.protocols.ReadinessService` | Aggregate per-provider and embedding health into one application-readiness snapshot. | `snapshot`, `probe_all`, `probe` | mixed (`snapshot` fast-sync; `probe_all`/`probe` blocking) | `backend/readiness/testing.py` | `09_READINESS_PROBE.md` |
| InferenceActivityStore | contract | `backend.stores.inference_activity.protocols.InferenceActivityStore` | Enforce the application-wide single-inference invariant: at most one inference-using activity (benchmark run, judge analysis, provider test, readiness probe) is in flight at any moment. | `try_acquire`, `release`, `state`, `is_busy` (method-only Protocol; NO `psygnal.Signal` on the contract — D-R-06) | fast-sync (all four callable from any thread under one `threading.Lock`); state changes are published as the `_inference_activity_changed` bus event and marshalled to the UI thread by the adapter | `backend/stores/inference_activity/testing.py` | — |
| TaskFileLoader | contract | `backend.task_files.protocols.TaskFileLoader` | Loader-tolerant reader of YAML task files for run creation; skips malformed tasks. | `scan_directory`, `load_tasks` | blocking | `backend/task_files/testing.py` | `12_YAML_FORMATTER.md` |
| TaskFileValidator | contract | `backend.task_files.protocols.TaskFileValidator` | Editor-strict validator producing per-row diagnostics for the Task Editor. | `validate_file` | blocking | `backend/task_files/testing.py` | `14_VALIDATION_CASCADE.md` |
| YamlFormatter | contract | `backend.yaml_formatter.protocols.YamlFormatter` | Comment-preserving serialiser and parser for task files in canonical field order. | `serialize`, `parse` | fast-sync | `backend/yaml_formatter/testing.py` | `12_YAML_FORMATTER.md` |
| AdaptiveTimeoutService | contract | `backend.adaptive_timeout.protocols.AdaptiveTimeoutService` | Compute the per-attempt timeout per `(provider, model, role)` and track exclusion-triggering instability **per role** — INFERENCE (Phase 2 inference) and JUDGE (Phase 4 per-task judge + Run Analysis generation). NOT consulted by Embedding (fixed `eval.embedding_timeout_seconds`), `LLMClient.test_inference` (fixed 60 s), or `LLMClient.probe_health` (fixed short). See DD-34. | `next_budget`, `record_success`, `record_timeout`, `is_excluded`, `model_state` | fast-sync | `backend/adaptive_timeout/testing.py` | `07_ADAPTIVE_TIMEOUT.md` |
| ProviderCircuitBreaker | contract | `backend.circuit_breaker.protocols.ProviderCircuitBreaker` | Trip a consistently-failing provider out of the run for a cooldown window, then probe before closing. | `state`, `record_failure`, `record_success`, `should_skip`, `cooldown_remaining_seconds` | fast-sync | `backend/circuit_breaker/testing.py` | `08_CIRCUIT_BREAKER.md` |
| WorkspaceController | contract | `adapters.workspace_controller.protocols.WorkspaceController` | Switch the main window between the benchmark and task-editor workspaces. | `active`, `switch_to` | fast-sync | `adapters/workspace_controller/testing.py` | — |
| NotificationService | contract | `adapters.notification_service.protocols.NotificationService` | Surface transient toasts and modal error dialogs to the user. | `show_info`, `show_warning`, `show_error` | fast-sync | `adapters/notification_service/testing.py` | — |
| NativePickers | contract | `adapters.native_pickers.protocols.NativePickers` | Isolate the native save / open-file / open-folder pickers behind one contract. | `open_file`, `open_folder`, `save_file` | fast-sync | `adapters/native_pickers/testing.py` | — |
| Clipboard | contract | `adapters.clipboard.protocols.Clipboard` | Isolate clipboard copy behind one contract. | `copy_text` | fast-sync | `adapters/clipboard/testing.py` | — |
| FileSystemActions | contract | `adapters.file_system_actions.protocols.FileSystemActions` | Isolate the "open in file manager" OS surface action behind one contract. | `open_in_file_manager` | fast-sync | `adapters/file_system_actions/testing.py` | — |
| Redaction module | module | `backend.errors.redaction` | Masks secret-shaped text at the two surfaces named in `10_Domain_and_Data/08_REDACTION_PATTERNS.md` — app-log records and provider SDK error-message wrapping at the adapter boundary. | `redact(text)`, `redact_for_log` (structlog processor) | fast-sync (pure; callable from any thread) | not faked — pure functions used as-is | `10_Domain_and_Data/08_REDACTION_PATTERNS.md` |
| EmbeddingService | internal | `backend.embedding.protocols.EmbeddingService` | LRU-cached cosine-similarity and embedding facade over the embedding-capable `LLMClient`. Uses the **fixed** `eval.embedding_timeout_seconds` budget per call — does NOT consult the Adaptive Timeout Service; no exclusion on consecutive timeouts (DD-34). | `embed`, `cosine_similarity`, `clear_cache` | blocking (`embed` runs on a `TaskRunner` worker; CPU math on a `TaskRunner` worker) | `backend/embedding/testing.py` | `06_EMBEDDING_SERVICE.md` |
| JudgePromptService | internal | `backend.evaluation.protocols.JudgePromptService` | Build the inference prompt and the task-type-aware judge prompt for one task. | `build_inference_prompt`, `build_judge_prompt` | fast-sync | `backend/evaluation/testing.py` | `05_JUDGE_PROTOCOL.md` |
| JudgeEvaluator | internal | `backend.evaluation.protocols.JudgeEvaluator` | Run the judge phase: call the judge model and parse a binary `PASS`/`FAIL` verdict with reasoning. | `evaluate` | blocking | `backend/evaluation/testing.py` | `05_JUDGE_PROTOCOL.md` |
| RunAnalysisService | internal | `backend.run_analysis.protocols.RunAnalysisService` | Generate the single consolidated, mode-aware prose run analysis via a user-chosen `(provider, model)` pair (defaulting to the run's judge model from the snapshot). | `generate(run_id, provider_id, model_name)` | blocking (acquires `JUDGE_ANALYSIS` on `InferenceActivityStore` for the call's duration) | `backend/run_analysis/testing.py` | `22_RUN_ANALYSIS_SERVICE.md` |
| KeywordEvaluator | internal | `backend.evaluation.protocols.KeywordEvaluator` | Run the keyword phase: exact, semantic, and forbidden term matching from `required_terms`. | `evaluate` | blocking (semantic terms use the embedding service) | `backend/evaluation/testing.py` | `04_EVALUATION_PIPELINE.md` |
| CosineEvaluator | internal | `backend.evaluation.protocols.CosineEvaluator` | Run the cosine phase: compute the Cosine Score of the response against the golden answer and grade it against the scope band. | `evaluate` | blocking | `backend/evaluation/testing.py` | `04_EVALUATION_PIPELINE.md`, `06_EMBEDDING_SERVICE.md` |
| SanityChecker | internal | `backend.evaluation.protocols.SanityChecker` | Deterministic post-inference pre-check (empty, echoed, too short, error marker) that can short-circuit grading to `FAIL`. | `check` | fast-sync | `backend/evaluation/testing.py` | `04_EVALUATION_PIPELINE.md` |
| PerformanceTaskGenerator | internal | `backend.performance_task_generator.protocols.PerformanceTaskGenerator` | Expand a `PerformanceConfig` input/output size matrix into synthetic `BenchmarkTask` rows for `SYNTHETIC` mode. | `generate` | fast-sync | `backend/performance_task_generator/testing.py` | — |
| ModelNameParser | module | `backend.model_helpers.model_name` | Parse a provider model string into family, parameter count, and quantization. | `parse_model_name` | fast-sync (pure) | not faked — pure function used as-is | — |
| ModelCapabilityService | internal | `backend.model_helpers.protocols.ModelCapabilityService` | Query and persist observed per-`(provider, model)` capability flags (streaming, reasoning effort, thinking). | `get_capabilities`, `record_capability`, `is_streaming_supported` | fast-sync | `backend/model_helpers/testing.py` | — |
| EmbeddingModelClassifier | module | `backend.model_helpers.classifier` | Decide whether a model name denotes an embedding-only model so it is excluded from inference selection. | `is_embedding_model` | fast-sync (pure) | not faked — pure function used as-is | — |
| TableSerializer | internal | `backend.csv_export.protocols.TableSerializer` | Serialise the summary and detailed result tables to CSV and Markdown. | `summary_to_csv`, `detailed_to_csv`, `summary_to_markdown`, `detailed_to_markdown` | fast-sync (large exports dispatched to a `TaskRunner` worker by the caller) | `backend/csv_export/testing.py` | — |
| ResultHtmlRenderer | internal | `backend.html_rendering.protocols.ResultHtmlRenderer` | Render a `BenchmarkResult` into the HTML task-detail view shown in the Result widget. | `render_result`, `render_task_detail` | fast-sync | `backend/html_rendering/testing.py` | `15_LOG_FORMATTING.md` |
| ChartAggregator | internal | `backend.charts.protocols.ChartAggregator` | Compute the twelve `ChartKind` aggregations from a run's results for the Result widget charts tab. | `aggregate` | blocking (pure aggregation dispatched to a `TaskRunner` worker) | `backend/charts/testing.py` | `13_CHART_AGGREGATORS.md` |
| ModeVisibilityPolicy | module | `backend.mode_visibility.visibility` | Data-driven lookup of which left-panel sections are visible for a given `RunMode`. | `is_visible`, `visible_sections` | fast-sync (pure) | not faked — pure function used as-is | `10_MODE_VISIBILITY_POLICY.md` |
| LogFormatter | internal | `backend.log_formatting.protocols.LogFormatter` | Render a pipeline event into the HTML log line at the configured verbosity. | `format_event` | fast-sync | `backend/log_formatting/testing.py` | `15_LOG_FORMATTING.md` |

### 3.1 UI shared dropdown widgets

Two reusable Qt widgets live under `ui/shared/`. They are listed here because their `(provider_id, model_name)` selection is the same composite identity the backend services route on, and they are consumed by the New Benchmark widget's Judge section, the Settings dialog's Embedding section, the Provider Edit Test Connection inference test, and the new Generate Analysis dialog (`07_Common_Dialogs/generate_analysis_dialog.md`). The two widgets are independent: the consumer wires them together (typically: on `provider_changed` set the model dropdown's provider).

| Widget | Module path | Purpose | Public API entry point | Signals | Implementer notes |
|---|---|---|---|---|---|
| Provider dropdown | `ui/shared/provider_dropdown/` | A `QComboBox`-backed Dropdown whose items are the enabled providers. Accepts an optional `filter` callable so consumers can restrict the displayed providers (for example, "providers that expose a judge-capable model"). | `make_provider_dropdown(...) -> QWidget` | `provider_changed(provider_id: str)` | Reads providers from `ProviderRegistry`. Refreshes on `_provider_registry_reloaded`. Holds no domain logic; pure presentation. |
| Model dropdown | `ui/shared/model_dropdown/` | A `QComboBox`-backed Dropdown whose items are the models of a given provider. Configurable by `provider_id` (set imperatively by the consumer in response to a sibling provider dropdown). Accepts an optional `filter` callable (for example, "chat-capable models only", "embedding models only"). | `make_model_dropdown(...) -> QWidget` | `model_changed(model_name: str)` | Re-fetches the model list when its `provider_id` changes or the user clicks a Refresh affordance. Holds no domain logic; pure presentation. |

---

## 4. Service Notes

This section gives a fuller inventory entry for each service whose behaviour is not
already obvious from its one-sentence purpose, with attention to the services that have
no dedicated algorithm file.

### 4.1 Clock

The Clock makes time injectable. `now_utc` returns an `Iso8601Utc` string used for every
persisted timestamp; `monotonic_ms` returns a monotonic counter whose differences measure
durations such as `total_time_ms` and `ttft_ms`. It is synchronous, callable from any
thread, and never raises. In tests it is faked by a frozen clock so timestamps and
durations are deterministic.

### 4.2 EventBus

The EventBus is the application-wide publish/subscribe channel and the **only** sanctioned
cross-thread channel. `emit` is callable from any thread; delivery is queued onto the main
thread, and every subscription handler runs on the main thread. `subscribe` returns a
`Subscription` and, when given an `owner`, auto-cancels when that owner is destroyed so
widgets never leak handlers. The bus never raises to the emitter; an exception inside one
handler is caught, redacted, logged, and isolated. The signal names and payload Structs
are catalogued in `08_Cross_Cutting/08-J_event_bus_catalog.md`.

### 4.3 The six persistence Stores

The durable-state gateway is split into six focused Protocols, one per aggregate root, so
each store has one responsibility and one owner: `RunsStore` (runs), `TasksStore` (frozen
task rows), `ResultsStore` (result rows and the crash-recovery sweep), `ProvidersStore`
(provider catalog and embedding-config row), `ModelCapabilitiesStore` (per-`(provider,
model)` capability cache), and `AppSettingsStore` (typed user-saved settings and the
schema-version row). Every store owns the SQLite tables of its aggregate under the WAL
configuration and raises `PersistenceError` on a storage failure. `ResultsStore` owns the
crash-recovery sweep (`recover_in_flight_results`), which resets every result left in a
non-terminal in-flight status back to `PENDING` at startup. Each store's methods are
synchronous because SQLite under WAL is fast enough to return quickly; the pipeline calls
them from its worker units, and all writes are funnelled through the single DB writer. Each is faked by
an in-memory test double in its own package's `testing.py` that honours the same contract
and transactional semantics.

### 4.4 SettingsService and RunSnapshotBuilder

The SettingsService resolves the user-saved + default layers for typed reads against the
`AppSettingsStore`. Only the user-saved layer is mutable through `set` and `upsert`; a
write emits the settings-changed signal. It raises `ConfigurationError` for an unknown key
or a value that cannot be coerced to the requested type.

The companion `RunSnapshotBuilder` Protocol (a sibling in `backend/settings/`) owns the
per-run-snapshot half of the three-layer hierarchy: its `build_snapshot()` method captures
the resolved value of every per-run-overridable key as the frozen `BenchmarkRunSettingEntry`
tuple at run start, so a run reads a stable settings view for its whole lifetime. The
SettingsService and the RunSnapshotBuilder are deliberately separate Protocols so a widget
that only reads settings does not depend on the snapshot-building surface and the
benchmark pipeline's run-creation use case does not depend on the live-settings mutation
surface.

### 4.5 PerformanceTaskGenerator

The PerformanceTaskGenerator is an internal service owned by the run-creation use case. It
expands a `PerformanceConfig` (`input_sizes` x `output_sizes` x `repeats`) into a tuple of
synthetic `BenchmarkTask` values with `task_origin = SYNTHETIC`, each carrying
`input_size_label`, `output_size_label`, and `repeat_index`. Synthetic tasks have no
`golden_answer` and no `required_terms`, so `SYNTHETIC` runs never grade. It is
synchronous and pure, and is faked by a deterministic generator that produces a fixed
matrix for tests.

### 4.6 RunAnalysisService

The RunAnalysisService generates the single consolidated `run_analysis` narrative stored
on `BenchmarkRun.run_analysis`. Its `generate(run_id, provider_id, model_name)` entry
point takes the analysis model as an explicit `(provider_id, model_name)` pair — supplied
either by the run's snapshot for the automatic post-run generation, or by the user via
the Generate Analysis dialog (`07_Common_Dialogs/generate_analysis_dialog.md`) for an
on-demand generation or regeneration. It adapts its prompt to the run mode (a
throughput-oriented narrative for `SYNTHETIC` and `TASKS`, a quality-oriented
narrative for `GRADED`). It calls the chosen model through the `LLMClient` and is
`blocking`. The service acquires the application-wide single-inference gate
(`InferenceActivityStore.try_acquire(JUDGE_ANALYSIS, ctx)`) at entry and releases it in
`finally`; a failed acquire returns a `FAILED` outcome with an `InferenceBusy`-classified
reason. A failure to generate the analysis is non-fatal: the run still completes and
`run_analysis` is preserved unchanged.

### 4.7 ModelNameParser

The ModelNameParser is a pure module. `parse_model_name` parses a provider model string
(for example `qwen3:8b-q4_K_M`) into `model_family`, `model_params_b`, and `quantization`,
which populate the parsed fields of `BenchmarkRunModelEntry`. It never raises: an
unparseable component is returned as `None`. Being pure, it is used directly in tests with
no double.

### 4.8 ModelCapabilityService

The ModelCapabilityService queries and persists `ModelCapabilityRecord` rows describing
the streaming, reasoning-effort, and thinking capabilities of a `(provider, model)` pair.
It records observations sourced from a dedicated probe, a normal inference call, or a
manual setting (`CapabilitySource`). The pipeline consults it before inference to decide
whether time-to-first-token can be measured. It is synchronous and reads/writes through
the `ModelCapabilitiesStore`.

### 4.9 EmbeddingModelClassifier

The EmbeddingModelClassifier is a pure module. `is_embedding_model` decides, from a model
name, whether the model is an embedding-only model that must not be offered as an
inference or judge target. It never raises and is used directly in tests.

### 4.10 NotificationService

The NotificationService is the only sanctioned path for a controller to raise a
user-visible message; UI primitives never throw to the user. `show_info` and `show_warning`
show transient toasts; `show_error` shows a toast when `blocking` is `False` and a modal
dialog when `True`. It must be called on the main thread; a background worker that needs
to notify the user emits an EventBus signal that the adapter layer marshals into a
notification call. The error-to-UX dispatch that decides which surface an error reaches is
specified in `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`.

### 4.11 TaskFileLoader

The TaskFileLoader reads YAML task files for run creation. It is **loader-tolerant**: a
malformed individual task is skipped with a logged warning, and tasks are de-duplicated by
`task_id` (first occurrence wins). It raises `TaskFileError` only when a folder or a file
is wholly unreadable or not valid YAML. It is the loader half of the loader/validator
pair; the validator half is editor-strict.

### 4.12 TaskFileValidator

The TaskFileValidator validates a task file for the Task Editor. It is **editor-strict**:
it re-reads the raw YAML and produces a `ValidationReport` of per-row `Diagnostic` records
rather than skipping content, so the user can see and fix every problem. It raises
`TaskFileError` only for a file that cannot be opened; unparseable YAML is reported as a
file-level hard-error diagnostic inside the report. The validation cascade and debounce
timing are specified in `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`.

### 4.13 SettingsService, RunSnapshotBuilder, WorkspaceController, NativePickers, Clipboard, FileSystemActions, and the six persistence Stores — the no-algorithm services

These contract services have no dedicated `11_Services_and_Algorithms/` algorithm file
because their full behaviour is captured by their typed contract in `08-E`: each is a
straightforward gateway or query surface with no non-trivial algorithm. The
WorkspaceController switches the main window between two named workspaces and carries an
optional `WorkspaceHint`; the three OS-adapter Protocols (`NativePickers`, `Clipboard`,
`FileSystemActions`) each wrap one OS integration behind one substitutable contract; the
six persistence Stores (`RunsStore`, `TasksStore`, `ResultsStore`, `ProvidersStore`,
`ModelCapabilitiesStore`, `AppSettingsStore`) are per-aggregate CRUD gateways, with
`ResultsStore` also owning the crash-recovery sweep; `SettingsService` is a typed
user-saved-plus-default resolver, and `RunSnapshotBuilder` is a one-method snapshot
capturer. Where a behaviour rule is non-obvious (the crash-recovery sweep, the settings
resolution order, the snapshot-capture rule) it is stated in `08-E` and in the
cross-referenced cross-cutting documents, not in a separate algorithm file.

### 4.14 InferenceActivityStore

The InferenceActivityStore is a backend reactive store (lives in `backend/stores/inference_activity/`) that owns the application-wide single-inference gate. It exposes a **method-only** Protocol — `try_acquire(activity, context) -> GateLease | None`, `release(lease)`, `state() -> InferenceActivityState`, `is_busy() -> bool` — with NO `psygnal.Signal` on the contract (D-R-06). The methods are safe to call from any thread (one `threading.Lock`) and never raise: a failed acquire returns `None`; ownership is the `GateLease`, so a stale release no-ops (DD-50). The store's coarse states are the five `InferenceActivity` members (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.18). Watchdog auto-release timeouts (per `08_Cross_Cutting/08-I_edge_cases.md`) prevent a crashed acquirer from locking the gate forever; `BENCHMARK_RUN` has no watchdog and is reconciled by the orphan-run sweep. On every acquire/release the concrete store publishes the `_inference_activity_changed` event (`08-J`, `08-Q`); the adapter's `qt_event_bus` bridge marshals it to the Qt main thread. (How the concrete store detects the change internally — e.g. psygnal — never crosses the Protocol.) It is faked in tests by `backend/stores/inference_activity/testing.py`, an in-memory deterministic double honouring the same `try_acquire` / `release` contract.

### 4.15 TableSerializer, ResultHtmlRenderer, ChartAggregator, LogFormatter — the presentation services

These four internal services turn `BenchmarkResult` data into a presentation form.
TableSerializer produces CSV and Markdown exports; ResultHtmlRenderer produces the HTML
task-detail view; ChartAggregator computes the twelve `ChartKind` aggregations; LogFormatter
renders pipeline events into HTML log lines. All of them are pure transforms over
already-loaded data — they never touch the network and never mutate state. The two that
can process large inputs (TableSerializer for a big detailed export, ChartAggregator for a
large run) are CPU-bound and are dispatched to a `TaskRunner` worker by their caller, per
`16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`; the contract surface remains as
shown in the table.

---

## 5. Module Ownership and Construction

Every contract service is constructed exactly once by the composition root and assembled
into the `ApplicationContext` (`08-E` Section 22). Internal services are constructed by
the composition root too, but they are injected into their owning contract service rather
than placed on `ApplicationContext` directly:

| Internal service | Owned and used by |
|---|---|
| EmbeddingService | CosineEvaluator, KeywordEvaluator (semantic terms), ReadinessService (embedding probe) |
| JudgePromptService | JudgeEvaluator, RunAnalysisService, Benchmark Pipeline (inference prompt) |
| JudgeEvaluator | Benchmark Pipeline (judge phase) |
| RunAnalysisService | Benchmark Pipeline (run-end analysis) |
| KeywordEvaluator, CosineEvaluator, SanityChecker | Benchmark Pipeline (grading phases) |
| PerformanceTaskGenerator | run-creation use case (`SYNTHETIC` mode) |
| ModelCapabilityService | Benchmark Pipeline (inference phase), Provider Registry |
| TableSerializer, ResultHtmlRenderer, ChartAggregator | Result widget controller (export and charts) |
| LogFormatter | Log widget controller |

Pure modules (Redaction, ModelNameParser, EmbeddingModelClassifier, ModeVisibilityPolicy)
are imported wherever they are needed; they hold no state and need no construction.

The dependency direction is strict and one-way: the UI layer depends on the adapter layer,
the adapter layer depends on these service Protocols, and services depend only on other
service Protocols and on domain models. No service imports a UI primitive. The full rule
is stated in `08-E` Section 2.

---

## 6. Test-Double Convention

Every contract service and every internal service has exactly one deterministic test
double, placed in a `testing.py` module inside the owning package (for example
`backend/persistence/testing.py`). The convention:

- The double satisfies the same `Protocol` structurally and honours the same contract,
  including the same error categories.
- The double is deterministic: no network, no real clock, no real filesystem unless a
  test explicitly provides a temp path.
- A test composes an `ApplicationContext` from doubles, overriding only the services
  relevant to the test under examination.
- Pure modules (Redaction, ModelNameParser, EmbeddingModelClassifier, ModeVisibilityPolicy)
  have **no** double: they are deterministic by construction and are used as-is in tests.

The faking module for each service is listed in the master table in Section 3. The full
testing strategy is specified in the `12_Quality_and_NFRs/` and `16_Engineering_Standards/`
documents.
