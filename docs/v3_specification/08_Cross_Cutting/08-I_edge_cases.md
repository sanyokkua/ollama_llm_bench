# Edge Case Catalog

**Status:** Draft
**Owner:** architect
**Audience:** tester, coder, arch
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-B_benchmark_state_machine.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`, `09_Task_Editor/description.md`, `06_Settings_Dialog/description.md`, `05_Result_Widget/description.md`, `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`

This document is the exhaustive catalog of non-obvious behaviours the implementation must handle. Each entry names a precise trigger, the expected behaviour, and the failure mode to avoid. Edge-case identifiers are stable: a test, a story, or a code comment may cite an identifier, and the identifier must not be reassigned. New edge cases discovered during implementation are appended to the owning catalog rather than scattered across widget descriptions.

### Edge-case identifier governance (D-R-08)

Every edge-case identifier is **scoped**: `EC-<SCOPE>-<N>`, where `<SCOPE>` is a short uppercase area tag owned by **exactly one** catalog document, and `<N>` is a number unique within that scope. **No number is ever reused across scopes**, so an identifier is globally unique and a citation is never ambiguous. The scope tags and their owning catalogs:

| Scope     | Owner catalog                                 | Area                        |
| --------- | --------------------------------------------- | --------------------------- |
| `RUN`     | `08-I` §1                                     | Run lifecycle               |
| `TASK`    | `08-I` §2                                     | Task files                  |
| `PROV`    | `08-I` §3                                     | Providers and clients       |
| `SET`     | `08-I` §4                                     | Settings                    |
| `RES`     | `08-I` §5                                     | Results, charts, exports    |
| `LOG`     | `08-I` §6                                     | Logging                     |
| `WS`      | `08-I` §7                                     | Workspace and Task Editor   |
| `PERF`    | `08-I` §8                                     | Performance and concurrency |
| `PERSIST` | `08-I` §9                                     | Persistence                 |
| `PLAT`    | `08-I` §10                                    | Platform                    |
| `IMP`     | `10_Domain_and_Data/06_IMPORT_FORMATS.md`     | Import validation           |
| `EXP`     | `10_Domain_and_Data/05_EXPORT_FORMATS.md`     | Export formatting           |
| `FL`      | `10_Domain_and_Data/07_FILE_LAYOUT.md`        | File layout / disk          |
| `RD`      | `10_Domain_and_Data/08_REDACTION_PATTERNS.md` | Redaction                   |
| `M`       | `08_Cross_Cutting/08-M_app_lifecycle.md`      | App lifecycle               |

The colliding domain-doc identifiers have been re-scoped accordingly (`EC-IMP-*`, `EC-EXP-*`, `EC-FL-*`). **Migration complete (D-R-08):** this catalog's entries have been rewritten from the historical `EC-<group>.<N>` form to the scoped `EC-<SCOPE>-<N>` form per the table above — §1 → `RUN`, §2 → `TASK`, §3 → `PROV`, §4 → `SET`, §5 → `RES`, §6 → `LOG`, §7 → `WS`, §8 → `PERF`, §9 → `PERSIST`, §10 → `PLAT` — preserving each case number (and any sub-letter, e.g. `EC-PROV-4a`) so citations stay stable. All citations across the spec were updated in the same pass. New cases use the scoped form.

______________________________________________________________________

## Table of Contents

1. Run lifecycle
1. Task files
1. Providers and clients
1. Settings
1. Results, charts, and exports
1. Logging
1. Workspace and Task Editor
1. Performance and concurrency
1. Persistence
1. Platform

______________________________________________________________________

## 1. Run lifecycle

### EC-RUN-1 — Start clicked while a run is already running

- **Trigger:** a run is in the in-memory `RUNNING` state and the user clicks Start.
- **Expected:** Start is disabled while a run is active; the click is a no-op. As the safety net, `start` acquires the `BENCHMARK_RUN` gate synchronously as its first step (SPEC-036); a click that slips past the disabled affordance hits a held gate, writes nothing, and is recorded only as a rejected `FAILED` attempt. The running run remains reachable through the Running pill.
- **Avoid:** spawning a second pipeline or a second run record.

### EC-RUN-1a — Rapid double-admission (double-click Start/Resume; Resume-Summary Confirm raced)

- **Trigger:** two admission calls (`start` or `resume`) fire before the first has flipped the activity state — a double-click, or a Resume-Summary Confirm racing another resume path.
- **Expected:** admission is gate-first and synchronous on the GUI thread (SPEC-036, DD-50): the first call's `try_acquire(BENCHMARK_RUN)` succeeds and proceeds; the second hits `None` and is a complete no-op — **no second run, no second row reset, no second pipeline**. For `resume`, the retry-row reset happens only after the gate is held, and is idempotent.
- **Avoid:** a second command resetting rows or partially starting before losing the gate.

### EC-RUN-2 — Pause requested between phases

- **Trigger:** the user requests a pause while the pipeline is at a phase boundary — for example between the inference phase and the keyword phase.
- **Expected:** the pipeline finishes the in-flight task, persists its result row, then halts cleanly before the next task. The run becomes `PAUSED` in memory; the persisted status stays `INCOMPLETE`. The Progress Widget stays visible; the idle three-panel layout is not restored.
- **Avoid:** corrupting the in-flight task's row to a failure status by cancelling it prematurely.

### EC-RUN-3 — Run starts with no reachable test models

- **Trigger:** every selected test model's provider is unreachable at run start.
- **Expected:** the pipeline marks the run `FAILED` with an error message stating that no provider for the selected models is reachable. The Result Widget shows the failure cleanly; every chart shows its empty-data state.
- **Avoid:** a long-running silent retry loop with no user feedback.

### EC-RUN-4 — Window closed while a run is in progress

- **Trigger:** a window close or application quit while a run is in the `RUNNING` state.
- **Expected:** a modal asks whether to stop the benchmark and quit. On confirm, shutdown issues a stop with a bounded timeout. If the graceful stop completes within the timeout, the run is marked `STOPPED` normally (a deliberate user stop). If the stop does not complete and the application force-quits, the run is left `INCOMPLETE`; on the next launch the orphan-run sweep records a recovery note and resets any non-terminal result row to `PENDING`.
- **Avoid:** data corruption from a half-written result row.

### EC-RUN-5 — Resume of a stopped run

- **Trigger:** the user selects a `STOPPED` run in the Resume Widget and resumes it.
- **Expected:** the run's persisted status is set to `INCOMPLETE`. The pipeline re-reads the result rows, selecting all rows in a non-terminal status (`PENDING`, `RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`, `AWAITING_COSINE_CHECK`, `AWAITING_JUDGE_CHECK`) plus any retryable failure rows (`FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, `ERRORED`) the user elects to retry. Any row left in `RUNNING_INFERENCE` is reset to `PENDING`. Execution continues from there. The original run's settings snapshot is reused.
- **Avoid:** re-running `COMPLETED` rows; automatically retrying `COMPLETED` rows that carry a `FAIL` verdict — a `FAIL` verdict is a validation result, not an error.

### EC-RUN-6 — Resume of a failed run

- **Trigger:** the user resumes a run whose persisted status is `FAILED` after a fatal pipeline error.
- **Expected:** the resume is allowed. The original settings snapshot is reused. If the underlying cause — for example a missing embedding configuration — is still present, the run re-fails immediately with the same class of error.
- **Avoid:** blocking a failed run from being resumed once its cause is fixed.

### EC-RUN-7 — Resume on a different machine or app version

- **Trigger:** the run's settings snapshot references a setting key that the current app version has removed, or omits a key the current version has added.
- **Expected:** unknown snapshot keys are ignored; missing keys fall back to current defaults. A soft warning naming the affected keys is recorded to the run log.
- **Avoid:** a crash while reading the snapshot.

### EC-RUN-8 — Stop versus pause and the idle layout

- **Trigger:** the user stops a run, versus the user pauses a run.
- **Expected:** a stop restores the idle three-panel layout so the user can start or resume another run; the run becomes `STOPPED`. A pause does not restore the layout; the Progress Widget stays visible and the run stays `INCOMPLETE`.
- **Avoid:** treating pause and stop identically with respect to layout.

### EC-RUN-9 — Automatic pause at a model, provider, or phase switch

- **Trigger:** the user has enabled automatic pauses, and the pipeline reaches a model switch, a provider switch, or a phase switch.
- **Expected:** the pipeline finishes and persists the in-flight task, then halts at the boundary and waits for an explicit resume, exactly as for a user-requested pause. The run becomes `PAUSED`.
- **Avoid:** halting mid-task; leaving a worker thread running after the pause is reported.

### EC-RUN-10 — Stop requested during phase-1 initialization

- **Trigger:** the user requests a stop before phase 1 has finished creating all result rows.
- **Expected:** the pipeline completes the creation of result rows so the run record is internally consistent, then honours the stop and marks the run `STOPPED`. The run remains resumable.
- **Avoid:** a run with a partial set of result rows that cannot be resumed.

### EC-RUN-11 — A run is resumed after its provider configuration changed

- **Trigger:** the user resumes a `STOPPED` run, but a provider used by the run has had its credentials, base URL, or enabled flag changed since the run was created.
- **Expected:** the run uses the provider snapshot frozen on the run record, not the current provider catalog. Re-validation at resume warns the user if the snapshotted provider is now unreachable, but the snapshot values are still what the pipeline uses.
- **Avoid:** silently switching the run to current provider configuration.

### EC-RUN-12 — Generate Analysis clicked while another inference activity is in flight

- **Trigger:** the user clicks **Generate analysis** or **Regenerate analysis** on the Run Analysis tab at the moment a benchmark run starts elsewhere, or a Provider Test or readiness probe is in flight.
- **Expected:** the Generate / Regenerate button is bound to the `InferenceActivityStore` state; when the gate is held by an activity other than `JUDGE_ANALYSIS` for the same run, the button is disabled and carries the tooltip `Another inference activity is in flight; analysis can be generated when it finishes.` When the gate is held because a benchmark run is non-terminal, the tooltip reads `A benchmark run is in progress; analysis can be generated when it finishes.` If the user reached the Generate Analysis dialog (`07_Common_Dialogs/generate_analysis_dialog.md`) before the gate flipped, the dialog's Confirm button is disabled with the same tooltip. The store's `try_acquire(JUDGE_ANALYSIS)` would in any case return `None` (DD-50), so the inline "An inference is currently in flight — please wait" message would appear instead of a generation start.
- **Avoid:** allowing two inference activities to overlap; surfacing a service-layer `InferenceBusyError` to the user when the UI already prevents the click.

### EC-RUN-13 — Readiness probe requested mid-benchmark

- **Trigger:** the user triggers a readiness probe — for example by clicking the health dot or by saving the Settings dialog — while a benchmark run is executing.
- **Expected:** the probe `try_acquire(READINESS_PROBE)` fails because the gate is held by `BENCHMARK_RUN`. The probe is **deferred, not queued** for the remainder of the run: the Readiness Service records the request, the readiness widget shows `Checking deferred — run in progress`, and the probe is re-attempted once the run reaches a terminal status. A health-dot click during a run shows the same deferred status rather than initiating a probe. The coalescing rule in `11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.6 still applies — overlapping deferred requests collapse into one.
- **Avoid:** running a readiness probe concurrently with a benchmark run and risking provider-side rate-limit collisions.

### EC-RUN-14 — Watchdog auto-release of the inference-activity gate

- **Trigger:** a non-pipeline acquirer of the `InferenceActivityStore` (a `JUDGE_ANALYSIS`, `PROVIDER_TEST`, or `READINESS_PROBE` activity) crashes or hangs without releasing the gate.
- **Expected:** the store applies a per-activity auto-release timeout — a watchdog — so the gate cannot be locked forever. The timeouts are:
  - `BENCHMARK_RUN` — **no auto-release**. The pipeline owns its own lifecycle and the orphan-run sweep (EC-PERSIST-2) handles a process death; auto-releasing mid-run would risk a second activity starting against an in-flight pipeline.
  - `JUDGE_ANALYSIS` — 10 minutes from `started_at`. Generous because a long analysis call against a slow local model can legitimately take minutes.
  - `PROVIDER_TEST` — 60 seconds. The Provider Edit Test probe issues one short request; a longer absence is a hang.
  - `READINESS_PROBE` — 30 seconds. A probe is `LLMClient.probe_health` with a short timeout; anything longer indicates a hung call.
- When the watchdog fires, it calls `release(lease)` with the `GateLease` it observed when arming (DD-50): the store transitions to `IDLE`, publishes the `_inference_activity_changed` event, and logs a warning naming the abandoned activity and its `started_at`. A subsequent acquire then succeeds normally — and if the abandoned holder's `finally` runs later, its stale lease no-ops and never steals the successor's gate.
- **Avoid:** a permanently locked gate that prevents the user from running a benchmark or test connection ever again.

### EC-RUN-15 — `GRADED` run started with `feature.judge_run_analysis_enabled = OFF`

- **Trigger:** the user starts a `GRADED` run after disabling the "Generate run analysis" toggle on the New Benchmark widget (the toggle defaults ON in `GRADED`; the user opted out to skip the extra inference cost).
- **Expected:** the pipeline runs all five phases normally — initialization, inference, and every enabled grading phase — and completes with `BenchmarkRun.run_analysis = null`. The pipeline's finalization step consults the run's snapshot value of `feature.judge_run_analysis_enabled`, sees `false`, and does not invoke the Run Analysis Service. The Run Analysis tab shows the **Generate analysis** empty state — `Run-level analysis was not requested for this run. Click Generate analysis to produce it now.` — and the user can post-run generate via the existing Generate Analysis dialog (D-037).
- **Avoid:** treating `GRADED` as always requiring the post-run analysis; forcing the toggle on at run snapshot time; failing the run because `run_analysis` is null.

### EC-RUN-16 — `GRADED` run with the per-task judge phase OFF and the run-analysis toggle OFF — no judge required

- **Trigger:** the user starts a `GRADED` run after disabling **both** the per-task judge phase (Settings → Evaluation) **and** the run-analysis toggle on the New Benchmark widget. The configured grading phases are limited to keyword and/or cosine.
- **Expected:** no judge model is required. The Judge picker on the New Benchmark widget may be left empty; the Start button accepts the configuration without raising the "judge model required" hard error. The pipeline runs init → inference → keyword/cosine grading → finalize, never calls a judge model, and finalizes with `BenchmarkRun.run_analysis = null`. The user can still post-run generate the analysis through the Generate Analysis dialog by picking any enabled chat-capable provider/model.
- **Avoid:** raising a "judge required" hard error in this configuration; refusing the Start; requiring a judge picker entry when neither toggle that consumes a judge is on.

### EC-RUN-17 — Provider does not expose `delta_tokens` for the in-flight `chat_stream` call

- **Trigger:** the active provider/model pair does not expose per-chunk `delta_tokens` on `ChatChunk` and does not expose a per-chunk running count either — for example, a streaming OpenAI-compatible endpoint that delivers usage only at end-of-stream (see `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.5a). The benchmark pipeline's live inference-progress emitter therefore falls back to the 4-character heuristic (`ceil(char_count / 4)`).
- **Expected:** `_inference_progress` events still emit at ≥ 1 Hz; their `tokens_received` field carries the heuristic estimate; the Progress widget's Current-task "Inference progress" row renders the value with a leading `~` (for example `Generating — ~184 tokens · 4.6 s elapsed`) to surface that the count is an approximation (`04_Progress_Widget/description.md` §7.1). At task completion the `_inference_completed` event and `BenchmarkResult.completion_tokens` still carry the provider's authoritative end-of-stream count, unaffected by the heuristic.
- **Avoid:** suppressing the row entirely when no per-chunk count is available; displaying the heuristic estimate as if it were exact; reusing the heuristic estimate as `BenchmarkResult.completion_tokens`.

### EC-RUN-18 — Inference completes before the first `_inference_progress` emission

- **Trigger:** an inference call returns within ~1000 ms — the `chat_stream` iterator completes before the first ≥ 1 Hz heartbeat emission, so no `_inference_progress` event ever fires for that task.
- **Expected:** the Progress widget's Current-task section briefly shows the "Inference progress" row in sub-state A (waiting), seeded with `0.0 s` from the `_inference_started` reset, and is then immediately replaced by the task's `_task_completed` close-line and the next task's `_inference_started`. No event is missed; the row simply never reached sub-state B for that task. The progress loop ends cleanly when the stream ends (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9 "Live inference-progress emission"); there is no ticker task or thread to tear down.
- **Avoid:** leaving a stale "Generating — 0 tokens" line after the task completes; emitting an `_inference_progress` event for a `chat_stream` that has already ended.

### EC-RUN-19 — Very slow first-token (sub-state A persists for many seconds)

- **Trigger:** the provider is reachable but the model is slow to begin streaming — for example, a cold local model load — so the first content-bearing chunk does not arrive for many seconds (or longer). No `_inference_progress` event yet carries `first_token_received == True`.
- **Expected:** the Progress widget's Current-task "Inference progress" row stays in sub-state A and the seconds counter (`Waiting for first token — N.N s`) keeps increasing on every heartbeat emission (the client's sub-second read timeout yields a heartbeat chunk during provider silence). The row stays in sub-state A indefinitely until either the first token arrives (transitioning to sub-state B) or the adaptive-timeout budget aborts the `chat_stream` call (at which point the row is replaced by the retry/failure flow per `04_Progress_Widget/state_machine.md` §3). The user sees the model is alive — the seconds counter is monotonically increasing — even though no token has been produced yet.
- **Avoid:** hiding the row while the adaptive timeout is still active; rendering a stale or frozen seconds value; emitting a `_inference_progress` event whose `first_token_received` flips from `True` back to `False` (the flag is monotonic per call).

### EC-RUN-20 — Judge call completes before the first progress emission

- **Trigger:** a per-task judge call (`context=BENCHMARK_JUDGE`) in `GRADED` returns within ~1000 ms — the judge's `chat_stream` iterator completes before the first ≥ 1 Hz heartbeat emission, so no `_inference_progress` event with `context=BENCHMARK_JUDGE` ever fires for that result.
- **Expected:** the Progress widget's Current-task section briefly shows the "Judge progress" sub-row in sub-state A (judge waiting), seeded with `0.0 s` from the `_judge_started` reset, and is then immediately replaced by the result's `_judge_completed` / `_task_completed` close-line and the next task's `_inference_started`. No event is missed; the sub-row simply never reached sub-state B for that result. The progress loop in the shared helper ends cleanly when the stream ends (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9); there is no ticker task or thread to tear down.
- **Avoid:** leaving a stale "Judge: receiving — 0 tokens" line after the judge call completes; emitting a `_inference_progress` event with `context=BENCHMARK_JUDGE` for a judge `chat_stream` that has already ended.

### EC-RUN-21 — RUN_ANALYSIS call cancelled by the user

- **Trigger:** while the Generate Analysis dialog is in its `Generating` sub-state (the analysis `chat_stream` is in flight, emitting `_inference_progress` events with `context=RUN_ANALYSIS`), the user clicks Cancel on the dialog.
- **Expected:** the dialog closes and the `chat_stream` is cancelled cooperatively — the LLM client closes the streaming connection per `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.6, the shared progress-emitter helper's loop ends as the cancelled stream closes (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9), and no further `_inference_progress` events fire for that `run_id`. The partial analysis is NOT saved — the Run Analysis Service never reaches its `RunAnalysisResult(outcome=GENERATED, ...)` return path. The Run Analysis tab continues showing the previously stored `run_analysis` (or its empty state if none was stored). The `JUDGE_ANALYSIS` activity is released in the service's `finally` block.
- **Avoid:** persisting a half-streamed analysis body; leaking the `JUDGE_ANALYSIS` activity gate; emitting `_inference_progress` events after the dialog has closed.

### EC-RUN-22 — PROVIDER_TEST call times out (live indicator transition)

- **Trigger:** a Test inference call from the Provider Edit dialog hangs and reaches `provider.inference_test_timeout_ms` (default 30 s). The live indicator was showing either sub-state A (testing waiting) or sub-state B (testing receiving) at the moment of the timeout.
- **Expected:** the LLM client returns `InferenceTestResult(outcome=TIMEOUT, latency_ms≈<deadline>, ...)` per EC-PROV-5e and `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.8.2. The Provider Edit inference-test panel **replaces the live indicator with the TIMEOUT outcome row** (the existing rendering per §8.2 — outcome chip in error tone, the elapsed `latency_ms`, the redacted `last_error`). The `_inference_progress` loop in the helper ends as the stream closes; no further progress events fire. The `PROVIDER_TEST` activity is released. The watchdog (60 s) acts as the final safety net if the deadline itself hangs.
- **Avoid:** leaving the live "Testing — …" indicator visible after the call has returned; emitting a stale `_inference_progress` event after the TIMEOUT outcome has been recorded.

### EC-RUN-23 — Defensive: BENCHMARK_JUDGE progress event arrives before its result's BENCHMARK_TASK has completed

- **Trigger:** an `_inference_progress` event with `context=InferenceContext.BENCHMARK_JUDGE` is observed for a `result_id` whose main inference (`context=BENCHMARK_TASK`) has not yet emitted `_task_completed` or `_inference_completed`. This is a programmer error: by construction the per-task judge call cannot start until the main inference completes (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.1, §6.5).
- **Expected:** the Progress widget's Current-task controller **ignores** the out-of-order `BENCHMARK_JUDGE` progress event (it does not transition the Judge progress sub-row to visible). The controller logs an assertion-style warning naming the offending `result_id`. The fix lives in the pipeline, not in the widget; the widget's defensive ignore guarantees the user sees a coherent Current-task section even if the pipeline misbehaves.
- **Avoid:** rendering the Judge progress sub-row before `_judge_started` for the active result has been observed; trusting the order of `_inference_progress` events as a correctness signal (the assertion is informational).

______________________________________________________________________

## 2. Task files

### EC-TASK-1 — Malformed YAML task file

- **Trigger:** a YAML parse error while loading a task file.
- **Expected:** at run-load time the file is skipped and the error is recorded to the app log, so one bad file never blocks a run. In the Task Editor the file surfaces as a parse-error state on its buffer with a banner stating that the file cannot be parsed, the reason, and that it must be fixed externally and reloaded.
- **Avoid:** blocking the entire Task Editor on a single bad file.

### EC-TASK-2 — Two tasks share the same `task_id`

- **Trigger:** the same `task_id` appears in more than one task entry, within one file or across two files loaded together.
- **Expected:** within one file, the Task File Validator flags both rows as hard errors and Save is disabled. Across two files, the loader keeps the first occurrence and skips the second with a warning; the Task Editor flags both rows in a cross-file diagnostic banner.
- **Avoid:** silent data loss from one task overwriting another.

### EC-TASK-3 — Task missing a required field

- **Trigger:** any of the required fields — `task_id`, `question`, `golden_answer` — is empty after trimming whitespace.
- **Expected:** at load time the task is skipped and the omission is logged, so a corrupted file does not block a run. In the Task Editor the task row carries a hard error and Save is disabled for that file until the user fixes it.
- **Avoid:** admitting an incomplete task into a run.

### EC-TASK-4 — Task opts out of cosine (`cosine_enabled: false`)

- **Trigger:** a task sets `cosine_enabled: false` (DD-46), or a legacy file contains the retired `task_type` key.
- **Expected:** `cosine_enabled: false` is valid — the cosine phase records `cosine_similarity = None` / `cosine_verdict = None` and the keyword and judge phases still grade the task. A retired `task_type` key is ignored with a soft warning and dropped on the next save.
- **Avoid:** treating the opt-out as an error, or letting a legacy key block a load.

### EC-TASK-5 — Invalid `difficulty` value

- **Trigger:** a value not in the `Difficulty` enum.
- **Expected:** at load time the field falls back to its default (`MEDIUM`) with a warning. In the Task Editor a soft warning is shown with a dropdown of valid choices. (A `response_scope` key in a legacy file is a retired key — ignored with a soft warning, DD-45.)
- **Avoid:** silently admitting an out-of-range value into a run.

### EC-TASK-6 — File modified on disk while open in the Task Editor

- **Trigger:** the file-system watcher reports that an open file changed on disk.
- **Expected:** a banner on that file row offers to reload the file or keep the in-editor edits. If the user keeps the edits, the next Save overwrites the on-disk file with the editor's form values.
- **Avoid:** silently discarding either the on-disk change or the user's edits.

### EC-TASK-7 — Saving a file that a running benchmark is using

- **Trigger:** the user saves a file in the Task Editor whose path is also among the task paths of the currently running run.
- **Expected:** a confirmation modal warns that a run is using this file. On confirm the save proceeds, but the pipeline does not re-read the file — the run cached its tasks into the database at phase 1. On cancel the edits remain unsaved.
- **Avoid:** the false expectation that saving changes the in-flight run's tasks.

### EC-TASK-8 — Folder picker selects a folder with no YAML files

- **Trigger:** the chosen folder contains no `.yaml` or `.yml` file.
- **Expected:** a toast states that no YAML files were found in the folder. No buffer is added.
- **Avoid:** adding an empty buffer or showing a misleading success state.

______________________________________________________________________

## 3. Providers and clients

### EC-PROV-1 — A listed model returns 404 during inference

- **Trigger:** the model the pipeline calls was not actually present at the provider — it was removed between selection and the run, or the pre-flight model listing was stale.
- **Expected:** the failure is classified as non-retryable. The result row is marked `FAILED_INFERENCE` with an error message naming the unavailable model. The pipeline advances.
- **Avoid:** retrying a non-retryable model-availability error.

### EC-PROV-1a — An advertised model cannot load (READY is not a load guarantee, SPEC-048)

- **Trigger:** a model that the endpoint advertised (so it passed readiness and drift checks) cannot actually load at run time — out of memory, not resident, or the backend lists more than it can serve. The application is backend-agnostic and cannot know this in advance from the listing.
- **Expected:** the failure surfaces at the model's **first use**, not silently mid-run. When `benchmark.warmup_enabled` is on, the warmup at the model-switch boundary hits it first: a warmup **timeout** is recorded as a provider failure (breaker, `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`), and a warmup that fails with a non-timeout error follows the `FAILED_PROVIDER` / `FAILED_INFERENCE` rules. With warmup off, the first task's inference produces the same `FAILED_*` outcome. `READY` only ever meant reachable + advertised, never loadable (`11_Services_and_Algorithms/09_READINESS_PROBE.md`).
- **Avoid:** treating a `READY` snapshot as a promise that every advertised model will load; blocking on a load test during readiness (no automatic load probe runs — DD-48).

### EC-PROV-2 — All retries exhausted for one task

- **Trigger:** every attempt for a task fails — a timeout or a retryable error — up to `benchmark.retry_count`.
- **Expected:** the row receives the terminal failure status matching the last error: `FAILED_PROVIDER` for a provider or connection failure, `FAILED_TIMEOUT` for a timeout, `FAILED_INFERENCE` for a model error. The last error message is recorded. The row carries no verdict. The pipeline advances. The row is retryable and remains eligible for a later manual retry.
- **Avoid:** halting the whole run because one task exhausted its retries.

### EC-PROV-3 — A provider trips the circuit breaker mid-run

- **Trigger:** provider-attributable failures exceed the breaker threshold across two or more distinct models — hard `FAILED_PROVIDER` errors and/or **warmup timeouts** on model switches. Per-task `FAILED_TIMEOUT` does **not** count (a slow model is excluded by adaptive timeout, not blamed on the provider — MISS-25).
- **Expected:** the provider's breaker state becomes tripped; the pipeline stops dispatching to that provider until the breaker probes and recovers. If `benchmark.stop_on_provider_health_failure` is true, the whole run is stopped with an error message naming the provider.
- **Avoid:** continuing to dispatch tasks to a provider known to be failing.

### EC-PROV-4 — A test (inference-role) model is excluded after repeated max-timeout failures

- **Trigger:** a `(provider, model, role=INFERENCE)` bucket accumulates `benchmark.consecutive_max_timeouts_to_exclude` consecutive failures at the maximum role=INFERENCE timeout (`benchmark.max_timeout_seconds`).
- **Expected:** the target is excluded from the run **for role=INFERENCE only**. Its remaining un-run tasks are marked `FAILED_TIMEOUT` with the reason that they did not fit the allotted time. The pipeline moves on to the next target. The same `(provider, model)` pair is **not** excluded for role=JUDGE — the two role buckets are independent.
- **Avoid:** one hopeless test model stalling the entire run; cross-contaminating role=JUDGE exclusion state from a role=INFERENCE exclusion.

### EC-PROV-4a — Per-task judge call exhausts its adaptive-timeout budget

- **Trigger:** the Phase 4 per-task judge call for a single task exhausts the role=JUDGE escalation ladder for that task — every attempt timed out, with the final attempt at `eval.judge_timeout_max_seconds`.
- **Expected:** the result settles to `status = FAILED_JUDGE_TIMEOUT`, `error_kind = JUDGE_TIMEOUT`, `error_message = "Judge call exhausted adaptive budget for this task."`, `verdict = None` (NOT `COMPLETED`; the binary verdict cascade is NOT applied because the judge phase produced no value AND the FAILED_JUDGE_TIMEOUT status is its own terminal class). The judge model is NOT excluded yet — only this task's judge phase is terminated. The pipeline continues to the next task. The result is **retryable** (the row joins `FAILED_INFERENCE` / `FAILED_PROVIDER` / `FAILED_TIMEOUT` / `ERRORED` in the retryable-terminal-state set; a retry re-runs the WHOLE task — re-inference + re-grade — uniform with the other `FAILED_*` states).
- **Avoid:** marking the task `COMPLETED` with a fabricated verdict; preserving the original attempt's inference text across a retry (the retry rebuilds the task end-to-end).

### EC-PROV-4b — Judge model excluded mid-run after consecutive max-budget judge timeouts

- **Trigger:** the role=JUDGE bucket for `(judge_provider, judge_model)` accumulates `eval.judge_timeout_consecutive_threshold` consecutive max-budget judge timeouts across multiple tasks during a `GRADED` run.
- **Expected:** the pipeline emits the `_judge_model_excluded` event exactly once (payload `JudgeModelExcludedEvent` — `08-J §5.2`, `08-Q §3.6a`), sets a local "judge_excluded" flag for the rest of the run, and **every remaining task that would have entered the judge phase settles to `FAILED_JUDGE_TIMEOUT`** directly — the judge call is NOT attempted for those tasks. The run does NOT abort; it finishes the remaining Phase 2 (inference), Phase 3 (cosine), and Phase 1 (sanity) work for each remaining task, then settles the judge phase for each as `FAILED_JUDGE_TIMEOUT`. The same judge `(provider, model)` pair remains usable at role=INFERENCE if it also happens to be selected as a test model. The Progress widget Event Log renders the exclusion with `"Judge model '<name>' excluded: <N> consecutive max-budget timeouts. Remaining tasks' judge phase will be skipped."`
- **Avoid:** aborting the whole run because the judge model failed; emitting the `_judge_model_excluded` event more than once per run; skipping inference/cosine phases on the remaining tasks just because the judge phase will be skipped for them.

### EC-PROV-4c — Embedding call times out (fixed budget, no exclusion)

- **Trigger:** an embedding call inside the cosine phase (or the keyword-phase semantic-term check) exceeds the **fixed** `eval.embedding_timeout_seconds` budget for one task.
- **Expected:** the task's cosine phase fails for that task: `cosine_similarity = None`, `cosine_verdict = None`. The binary verdict cascade (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.6, D-012) settles per the cosine-not-run handling — when cosine is the deciding phase and cannot produce a value, the cascade falls back to keyword or judge per the rules already documented in the pipeline. There is **NO exclusion** of the embedding model — the very next task tries the embedding call afresh with the same fixed budget. Embedding has no adaptive escalation and no consecutive-max threshold; a chronically stalled embedding model keeps producing per-task cosine failures task after task, but never aborts the run.
- **Avoid:** treating an embedding timeout as a judge or inference timeout; introducing an adaptive ladder for embedding (it is deliberately fixed); excluding the embedding model after consecutive timeouts.

### EC-PROV-4d — Retry of a FAILED_JUDGE_TIMEOUT row

- **Trigger:** the user retries a `BenchmarkResult` row whose status is `FAILED_JUDGE_TIMEOUT` from the Result widget's Retry action menu (`07_Common_Dialogs/retry_selection_dialog.md`).
- **Expected (DD-66, stage-preserving retry):** the row is reset to `AWAITING_JUDGE_CHECK`, **not** `PENDING` — only the judge outputs and combined verdict are cleared; the inference response, timing/token metrics, `keyword_verdict`, and `cosine_similarity`/`cosine_verdict` are **preserved**. The resume re-runs **only the judge** against the preserved `sanitized_response`, so it grades the exact response the earlier keyword/cosine stages saw (no wasted re-inference, no stale-text mismatch). The persistent role=JUDGE last-known-good budget may carry escalated state from the original attempt; the in-run consecutive-timeout count begins at zero for the retry session. (A crash before the re-judge falls back to a whole-task re-run via the startup sweep, which resets `AWAITING_*` rows to `PENDING`.)
- **Avoid:** re-running inference for a judge-only failure; clearing the preserved inference/keyword/cosine outputs; resetting the persistent role=JUDGE last-known-good budget on retry.

### EC-PROV-4e — Run-analysis generation exhausts its adaptive budget

- **Trigger:** the user clicks Generate / Regenerate in the Result widget Run Analysis tab (the Generate Analysis dialog dispatches the call); the user-initiated run-analysis generation call exhausts its role=RUN_ANALYSIS escalation ladder (DD-65) — every attempt timed out at the budgeted max.
- **Expected:** `RunAnalysisService.generate(...)` returns `RunAnalysisResult` with `outcome = FAILED` and `reason = "judge_timeout_exhausted"`. The Generate Analysis dialog renders `"The judge model failed to respond within the time budget after N attempts. Pick a different model and retry."`. No `_judge_model_excluded` event is emitted from this path — analysis is a one-shot user activity and the dialog's failure message is the user's exit ramp. The in-run consecutive-timeout count for role=JUDGE that was used during this invocation is discarded when the activity ends; a subsequent click starts a fresh count. The persistent last-known-good role=JUDGE budget DOES carry forward (it may already be at the ceiling from the failed attempt).
- **Avoid:** emitting `_judge_model_excluded` from the analysis path (that event is for the BENCHMARK_RUN activity only); preserving the in-run consecutive-timeout count across separate user clicks.

### EC-PROV-4f — GRADED run excludes the judge model mid-run; user immediately tries to regenerate analysis with the same model

- **Trigger:** a `GRADED` run causes the judge model to be excluded (per EC-PROV-4b); the run completes (most tasks have `FAILED_JUDGE_TIMEOUT`). The user then clicks Generate Analysis in the Result widget Run Analysis tab with the same judge `(provider, model)` selected.
- **Expected:** the analysis call's in-run consecutive-timeout count starts fresh — the BENCHMARK_RUN activity's count is not carried into the JUDGE_ANALYSIS activity. Per SPEC-032 the run-analysis call runs at the **configured maximum** budget (`eval.judge_timeout_max_seconds`) directly — it does not inherit the per-task judge last-known-good. Since the model just proved it cannot answer within that maximum during the run, the analysis call is likely to time out on the first attempt; after `eval.judge_timeout_consecutive_threshold` consecutive attempts (all at the maximum) the analysis surfaces the `judge_timeout_exhausted` failure (EC-PROV-4e). The clear user remedy is to pick a different judge model from the dialog's provider/model dropdown and retry — and because the analysis budget is decoupled, that failed BENCHMARK_RUN never altered any per-task budget.
- **Avoid:** carrying the BENCHMARK_RUN's exclusion flag into the analysis path (the analysis is independent and the user may genuinely succeed with a fresh attempt); resetting the persistent last-known-good budget at activity boundaries (it must carry over to avoid re-learning the same value every click).

### EC-PROV-5 — Provider Health Test uses unsaved form values

- **Trigger:** the user edits the Provider Edit dialog and clicks Test reachability or Run inference test without saving.
- **Expected:** the action runs against the current form state. The result is shown inline. The saved provider record in the database is untouched until the dialog is saved.
- **Avoid:** testing the saved values when the user expects the form values to be tested.

### EC-PROV-5a — Provider reports `discovery_supported=False` (e.g. Anthropic)

- **Trigger:** the user runs Test reachability against a provider whose per-provider `LLMClient` implementation does not support a models-list call (notably Anthropic, which historically exposes no models-list endpoint), or against a Gemini build whose SDK does not expose `models.list()`.
- **Expected:** the `ProviderHealth` returned by `LLMClient.probe_health()` carries `reachable=True, discovery_supported=False, model_count=None`. The Settings dialog renders the reachability outcome as `reachable · discovery not supported by this provider`. The Readiness Service treats this provider as **READY** when reachable — the missing discovery endpoint is informational metadata, never a health-gating criterion (`11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.5). The Settings dialog's Test inference panel exposes the manual-entry toggle so the user can type a model name to test.
- **Avoid:** treating zero discovered models or a missing discovery endpoint as unhealthy; refusing to render the row READY in the readiness section.

### EC-PROV-5b — Inference test invoked while a benchmark run is in flight

- **Trigger:** the user opens the Provider Edit dialog's Test inference panel while a benchmark run, a judge analysis, or a readiness probe holds the `InferenceActivityStore` gate.
- **Expected:** the Run inference test button is **disabled** with the tooltip `An inference is in flight; please wait.` (bound to `_inference_activity_changed`). If the click is forced by accessibility tooling or a race, the in-method safety net returns `InferenceTestResult(outcome=GATE_BUSY, latency_ms=None, last_error="An inference activity is already in flight.")` without issuing a chat call. The dialog renders the `GATE_BUSY` chip; the gate state is unchanged.
- **Avoid:** two inference activities overlapping; a billable chat call being issued because the UI gate was bypassed.

### EC-PROV-5c — Inference test invoked with no model selected

- **Trigger:** the user opens the Test inference panel but neither selects a model from the dropdown nor types a name in the manual-entry input, then attempts to run the test.
- **Expected:** the Run inference test button is **disabled** until either a model is selected in the dropdown OR the manual-entry toggle is on AND the typed text is non-empty after trim. The user cannot issue an inference call without naming the model. This rule is binding: surprise billing on a paid cloud provider must be impossible.
- **Avoid:** issuing a chat call with no model name; defaulting to an arbitrary model from the discovered list.

### EC-PROV-5d — Inference test against a paid cloud provider with manual model entry

- **Trigger:** the user toggles `Enter model name manually` against a paid cloud provider (Anthropic, OpenAI, Gemini, Azure-hosted OpenAI), types a model name, and clicks Run inference test.
- **Expected:** the inline panel displays a cloud-billing warning strip — `This call is billable on this provider — one short request will be sent to the selected model.` By typing the name and clicking Run the user explicitly accepts the billing implication. The dialog issues exactly one short canned chat call and renders the `InferenceTestResult` inline.
- **Avoid:** silently issuing a billable call with no warning; refusing to allow a manual model name (some users legitimately need to test a model the provider does not list).

### EC-PROV-5e — Inference test times out

- **Trigger:** the chat call inside `LLMClient.test_inference` exceeds `provider.inference_test_timeout_ms` (default 30 s) — the provider hung or the model is loading.
- **Expected:** the method returns `InferenceTestResult(outcome=TIMEOUT, latency_ms≈<deadline>, response_excerpt=None, last_error=<redacted timeout message>)`. `latency_ms` captures the elapsed time at the moment the deadline expired. The dialog renders the `TIMEOUT` chip with the latency. The `PROVIDER_TEST` activity is released; the watchdog (60 s) acts as the final safety net if the deadline itself hangs.
- **Avoid:** the method propagating a `TimeoutError` to the UI; the gate being held forever.

### EC-PROV-5ea — SDK exception text contains an `Authorization` header

- **Trigger:** a provider SDK raises an exception whose message string includes the raw HTTP request that triggered the failure, and that request carries an `Authorization: Bearer <token>` header. This happens with some SDKs (notably `httpx`-based transports at DEBUG/TRACE level) when an authentication failure echoes the request body back.
- **Expected:** the provider adapter is the **sole** place where the raw SDK exception type exists (`16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md` §5, `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` §6.5). Before constructing the application-typed `AppError`, the adapter passes the SDK exception's message string through `redact(text)` (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` surface 2). The placed `AppError.message` therefore reads `Authorization: <redacted>` and contains no live token. From this wrap point onward the message flows to display, the run-log file, the `app.*` log, exports, and the clipboard verbatim — the canonicalisation happened at the adapter boundary and no further redaction is applied.
- **Avoid:** wrapping the SDK exception into `AppError` without applying `redact` first; relying on a downstream UI/log surface to redact (those surfaces no longer apply redaction in the new threat model).

### EC-PROV-5f — Probe records `reachable=True, discovery_supported=True, model_count=0`

- **Trigger:** an `OPENAI_COMPATIBLE` provider is reachable and `GET /v1/models` returned an empty list (the admin disabled every model, or the deployment has no models bound).
- **Expected:** the `ProviderHealth` is `reachable=True, discovery_supported=True, model_count=0` and is treated as **healthy** for readiness purposes (`11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.5 — the provider counts toward `healthy_count`). The Settings dialog Test reachability action renders `✓ reachable · 0 models · <latency> ms`. The New Benchmark widget's test-models picker shows zero models for that provider and the user cannot pick one of its models, but the provider's presence does not block the picker from offering models of other providers.
- **Avoid:** the previous behaviour of counting zero-models as `DEGRADED`/`NOT_READY`; refusing to render the row READY in the readiness section.

### EC-PROV-6 — The environment variable named by a provider's api key is unset/empty

- **Trigger:** the api-key field holds the NAME of an environment variable, and that variable is unset or empty in the process environment at app start (D-R-18).
- **Expected:** the provider stays enabled in configuration, but its readiness probe reports `MISSING_ENV`. Starting a run is blocked for that provider's selected models. The Settings provider list shows the missing-environment badge.
- **Avoid:** a silent inference failure with no diagnosis.

### EC-PROV-7 — The credential field accepts only an env-var name

- **Trigger:** the user types a literal secret value (rather than an environment-variable name) into a provider's api-key field in Settings.
- **Expected:** the credential field accepts only an environment-variable **name** (D-R-18). A literal value is rejected inline at entry — there is no conversion dialog and no "save plain" choice. The commit proceeds only once the field holds an env-var name (or is empty for a keyless local provider); a literal credential never reaches the database. On import, a literal value in an `api_key` field stays a **hard error** (EC-IMP-9).
- **Avoid:** silently persisting a literal secret, or offering a conversion dialog.

### EC-PROV-8 — Two providers with the same identifier on import (SUPERSEDED by EC-PROV-13)

- **SUPERSEDED (DD-33, D-R-13):** providers are matched by **`name`**, not `id` — an imported `id:` key is retired and silently ignored. The duplicate case is therefore **duplicate `name`**, handled by **EC-PROV-13** (and EC-IMP-7 in `10_Domain_and_Data/06_IMPORT_FORMATS.md`). This entry is retained as a superseded pointer; do not implement a duplicate-`id` check.
- **Trigger (historical):** an imported provider-configuration file contained a duplicate `provider_id`.
- **Expected (historical):** the import preview flagged the duplicate as an error and refused the import.
- **Avoid:** a partially applied import that leaves the provider catalog inconsistent.

### EC-PROV-9 — Same model name across two providers

- **Trigger:** the same `model_name` is exposed by two different providers, and both are selected as test models.
- **Expected:** the two are treated as two distinct benchmark targets. The composite `(provider_id, model_name)` is the unit of execution, grouping, grading, aggregation, and export. The displayed label distinguishes the two by provider. Their result rows are never merged.
- **Avoid:** averaging statistics from two physically different model instances under one label.

### EC-PROV-10 — Adding a provider with a duplicate name (DD-33)

- **Trigger:** the user enters a `name` in the Provider Edit sub-dialog (Add) that already matches another provider's `name` in the in-memory working catalog, or matches a row in `ProvidersStore.get_by_name(name)` not represented in the working copy.
- **Expected:** the Name field shows a red border and an inline error `A provider with this name already exists.` The dialog's Save button is **disabled** until the name is changed. The dialog never calls `ProvidersStore.add(draft)` while the validation is failing; the `UNIQUE (name)` constraint in the database is the backstop, never the primary error path. No DB write happens.
- **Avoid:** raising a raw `PersistenceError` to the user; allowing the constraint violation to be the first place the user learns about the collision.

### EC-PROV-11 — Renaming a provider to a name already used (DD-33)

- **Trigger:** the user edits an existing provider in the Provider Edit sub-dialog and types a `name` that matches another provider's `name` in the working catalog.
- **Expected:** the Name field shows the same inline error as EC-PROV-10 and the dialog's Save button is disabled. The provider being edited keeps its `provider_id` (immutable) and the dialog never calls `ProvidersStore.update(provider_id, config)` while the validation is failing.
- **Avoid:** orphaning historical references because the dialog accidentally re-created the row; allowing the constraint violation to surface as a raw `PersistenceError`.

### EC-PROV-12 — Renaming a provider after a run has completed (DD-33)

- **Trigger:** the user successfully renames a provider (no collision; the change commits) after one or more `BenchmarkRun` rows that referenced the original `provider_id` have finished.
- **Expected:** the `providers.name` column is updated in place; the Settings provider table renders the new name immediately. Every completed `BenchmarkRun` row continues to display the SNAPSHOT name from `BenchmarkRun.judge_provider_name` (when the run had a judge against this provider) and every completed `BenchmarkResult` row continues to display the SNAPSHOT name from `benchmark_results.provider_name`. The Resume widget run list, the Result widget Summary / Details / Charts / Run Analysis tabs, every export, and the per-run log file all render the SNAPSHOT name — they do NOT re-look up the current name through `ProvidersStore`. A run currently in flight uses the provider snapshot already frozen at run start (see `RunSnapshotBuilder` §8a), so a rename during an in-flight run never interleaves new and old names in the Progress widget either.
- **Avoid:** retroactively relabelling historical run rows; mixing snapshot and live names across a single run's UI surfaces.

### EC-PROV-13 — Importing a provider configuration with a duplicate name (DD-33)

- **Trigger:** the importer encounters a provider entry in the import file whose `name` either (a) duplicates the `name` of another entry within the same file, or (b) duplicates the `name` of an existing row in `ProvidersStore` and the import action is "Add" rather than the full-replace `replace_providers` flow.
- **Expected:** case (a) — the import preview lists the duplicate-within-file as a hard error and the import is aborted before any DB write (a duplicate **`name`** within the file; the retired duplicate-`id` rule of the superseded EC-PROV-8 no longer applies — D-R-13). Case (b) — the importer's per-row check calls `ProvidersStore.get_by_name(entry.name)`; on a hit, the preview marks the row "Skipped (duplicate name)" with a soft warning, the importer continues with the rest, and the rejection appears in the import summary. The full-replace path (Settings dialog Save) catches this via the `UNIQUE (name)` constraint as a backstop.
- **Avoid:** half-applied imports; surfacing a `UNIQUE` constraint violation to the user without an explanatory message.

______________________________________________________________________

## 4. Settings

### EC-SET-1 — Settings opened while a run is active

- **Trigger:** the user attempts to open Settings while a run is in a non-terminal state.
- **Expected:** out of scope by construction. The Settings menu entry is disabled while a run is active, so settings cannot be edited during a run. This is why the pipeline can safely rely on the run's settings snapshot.
- **Avoid:** allowing a settings edit to race with a running pipeline.

### EC-SET-2 — Settings import contains unknown keys

- **Trigger:** an imported settings file contains keys not present in the current defaults map.
- **Expected:** the import preview lists the unknown keys in a "will be ignored" section; the import still proceeds for the recognised keys. The ignored keys are recorded to the run log.
- **Avoid:** failing the whole import because of one unrecognised key.

### EC-SET-3 — A numeric timeout setting is cleared or made invalid

- **Trigger:** a numeric setting such as `benchmark.min_timeout_seconds` is left empty, zero, or negative.
- **Expected:** the Settings field shows a red border and a tooltip stating the valid range. Save is disabled until the value is corrected.
- **Avoid:** persisting an out-of-range value that would break the pipeline.

### EC-SET-4 — Reset to Defaults during unsaved edits

- **Trigger:** the user has unsaved edits and clicks Reset to Defaults.
- **Expected:** a confirmation states that this discards the unsaved edits and resets to factory defaults, and asks the user to confirm.
- **Avoid:** silently discarding the user's edits.

### EC-SET-5 — A grading phase is disabled but a judge model is still required

- **Trigger:** the user disables the judge phase for a `GRADED` run but the run-level judge analysis narrative is still requested.
- **Expected:** the judge phase and the run-level judge analysis are independent. Disabling the judge phase is allowed; if the run-level judge analysis is requested, a judge model must still be configured. Settings makes the dependency explicit.
- **Avoid:** silently producing no judge analysis when the user requested one.

______________________________________________________________________

## 5. Results, charts, and exports

### EC-RES-1 — Run with zero completed results

- **Trigger:** every task failed or was excluded; no result row reached `COMPLETED`.
- **Expected:** the Summary tab shows a "no completed results" message; every chart shows its empty-data state; the Details tab still lists every row with its failure reason.
- **Avoid:** a blank, unexplained Result Widget.

### EC-RES-2 — Same model name across two providers in aggregation

- **Trigger:** results exist for the same `model_name` under two different `provider_id` values.
- **Expected:** the composite `(provider_id, model_name)` is the unit of aggregation in the Summary tab, the Details tab, all twelve charts, the judge prompts, and every export. The displayed label distinguishes the two by provider. Rows are never merged.
- **Avoid:** averaging metrics from two physically different model instances under a single label.

### EC-RES-3 — Long judge analysis text

- **Trigger:** the judge model emits a very long run-level analysis narrative or a very long per-result judge reasoning string.
- **Expected:** the Run Analysis tab displays the full text with no truncation and no length cap. The complete text is shown in the UI, is stored in full in the data store, and is written in full by the Markdown export. The tab scrolls to accommodate any length.
- **Avoid:** truncating the displayed analysis or appending a truncation marker; capping the stored or exported text.

### EC-RES-4 — Chart exported as PNG in dark mode

- **Trigger:** the user exports a chart as PNG while the app is in dark mode.
- **Expected:** the PNG is rendered with the current theme's tokens, matching what is shown on screen, not the operating system's native palette.
- **Avoid:** a PNG whose colours do not match the displayed chart.

### EC-RES-5 — Export write fails to the app-data folder

- **Trigger:** a disk-full or permission-denied condition while writing an export to the app-data folder, with the direct-save option enabled.
- **Expected:** an error modal explains the failure. The direct-save option stays enabled but no file is written. The user can disable the direct-save option to force a Save dialog and choose another location.
- **Avoid:** a silent failure that leaves the user believing the export succeeded.

### EC-RES-6 — Result Widget refreshes during a live run

- **Trigger:** the run is in progress and producing results; the Result Widget is open.
- **Expected:** the Summary tab, the Details tab, and the charts update in real time as the pipeline produces results. The user sees partial results without waiting for the run to finish.
- **Avoid:** a Result Widget that only populates after the run terminates.

______________________________________________________________________

## 6. Logging

### EC-LOG-1 — Run-log file write fails

- **Trigger:** a disk-full or permission-denied condition while writing the per-run log file during a run.
- **Expected:** the in-memory run-log panel keeps working. The file writer records the failure to the app log once, not once per line. A small warning indicator appears in the toolbar.
- **Avoid:** flooding the app log with one error per log line; losing the in-memory run log because the file writer failed.

### EC-LOG-2 — App-log rotation

- **Trigger:** the application log file exceeds its configured rotation size.
- **Expected:** the log rotates to numbered backups; the oldest backup beyond the configured backup count is dropped.
- **Avoid:** an unbounded log file.

### EC-LOG-3 — Run-log verbosity changed mid-run

- **Trigger:** the user changes the run-log verbosity control during a run.
- **Expected:** the visible run-log panel re-renders from cached raw events at the new verbosity. The run-log file keeps recording at its full verbosity regardless of the panel setting.
- **Avoid:** losing log detail in the file because the panel verbosity was lowered.

______________________________________________________________________

## 7. Workspace and Task Editor

### EC-WS-1 — Switching to the Task Editor while a detached chart window is open

- **Trigger:** a chart has been detached into its own modeless window and the user switches the main workspace to the Task Editor.
- **Expected:** the detached chart window stays open with its own lifetime. The parent Result Widget is hidden with the workspace switch. Switching back re-shows the Result Widget.
- **Avoid:** closing the detached chart window when the workspace switches.

### EC-WS-2 — Quit with both dirty editor buffers and a run in progress

- **Trigger:** the user quits the application while the Task Editor has unsaved buffers and a run is in progress.
- **Expected:** two confirmation modals appear in sequence — first the stop-benchmark-and-quit confirmation, then the save-changes confirmation for the dirty files. Cancel on either modal aborts the quit entirely.
- **Avoid:** quitting without confirming one of the two pending concerns.

### EC-WS-3 — Task Editor YAML preview for a task with hard errors

- **Trigger:** a task has a hard error such as a missing `task_id`, and the user opens the YAML preview.
- **Expected:** the preview shows the YAML that would be written, including the empty field, so the user can see the problem. The Save button stays disabled until the hard error is fixed.
- **Avoid:** enabling Save from the preview while a hard error is unresolved.

### EC-WS-4 — Workspace switch while an editor field is mid-edit

- **Trigger:** the user switches workspaces while a Task Editor field has focus and uncommitted text.
- **Expected:** the in-progress field edit is committed to the in-memory buffer before the workspace switches; the buffer's dirty state is preserved. Switching back shows the buffer with the edit retained.
- **Avoid:** losing the uncommitted field text on a workspace switch.

______________________________________________________________________

## 8. Performance and concurrency

### EC-PERF-1 — UI mutation attempted from a background worker

- **Trigger:** a background worker thread attempts to mutate UI state directly.
- **Expected:** forbidden by construction. Every cross-thread message passes through the event bus, which marshals delivery onto the UI thread. Background workers never touch widgets directly.
- **Avoid:** a direct cross-thread widget mutation.

### EC-PERF-2 — Two readiness probes overlap

- **Trigger:** the user triggers a readiness probe — for example by clicking the health dot — while a probe is already in flight.
- **Expected:** the second request is coalesced into the in-flight probe; the second trigger is a no-op.
- **Avoid:** two concurrent probes racing and producing inconsistent results.

### EC-PERF-3 — High-rate result completion

- **Trigger:** a stress scenario produces results faster than the UI can usefully repaint.
- **Expected:** table and chart refreshes are debounced on a fixed interval. The run-log panel uses a bounded buffer with rolling drop of the oldest lines.
- **Avoid:** an unbounded UI repaint queue or an unbounded log buffer.

### EC-PERF-4 — Pause requested while many workers are in flight

- **Trigger:** the user requests a pause while several inference workers are running concurrently within one phase.
- **Expected:** the (at most one — D-R-16) in-flight worker finishes its task, and the dispatcher persists its result row through the single DB writer (DD-41). Only then does the pipeline report `PAUSED`. No worker is abandoned or detached.
- **Avoid:** reporting `PAUSED` while workers are still running, which would corrupt result rows.

______________________________________________________________________

## 9. Persistence

### EC-PERSIST-1 — Database schema-version mismatch at startup

- **Trigger:** the application launches against a database whose recorded schema version does not match the schema version the current app build expects.
- **Expected (DD-53):** an **older** version within the same major lineage is brought forward by the ordered additive structural steps (`10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §8) — `ADD COLUMN` with `NULL`/default, new tables/indexes only; existing rows are never updated, backfilled, or converted. A **newer-than-app or cross-major** version is a **hard startup error**: the application aborts launch, alters nothing, and shows a clear error dialog explaining the incompatibility. There are no data migrations or conversions, ever.
- **Avoid:** silently mutating the database schema; attempting an automatic, additive DDL repair; launching against an incompatible schema.

### EC-PERSIST-2 — Orphan runs at startup

- **Trigger:** a previous process exited while a run was executing, leaving the run persisted as `INCOMPLETE` with no pipeline loaded.
- **Expected:** the orphan-run sweep at startup **leaves every such run `INCOMPLETE`** (its persisted status is unchanged), records a recovery note ("Recovered from a previous session."), and resets every result row left in a non-terminal status to `PENDING` so it re-executes cleanly on a later resume. The run is directly resumable and continues from the last finished task.
- **Avoid:** trusting a partially written result row; flipping the run to `STOPPED` (which would misrepresent a crash as a deliberate user stop); failing to record that the run was recovered.

### EC-PERSIST-3 — Concurrent writes to the data store

- **Trigger:** the pipeline writes result rows while the UI writes another persisted record.
- **Expected:** the data store guarantees atomic, serialized writes from any thread through the single DB writer — one write connection guarded by one lock (DD-41); each write runs synchronously on the calling thread and is committed when the call returns; causal order per caller is preserved.
- **Avoid:** interleaved partial writes that corrupt a record.

### EC-PERSIST-4 — A retryable failure row after crash recovery

- **Trigger:** the orphan-run sweep encounters a result row already in a retryable failure status — `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, or `ERRORED`.
- **Expected:** the sweep leaves a retryable failure row in its failure status; it resets only non-terminal rows to `PENDING`. The user later decides, in the Resume Widget, whether to retry the failure rows.
- **Avoid:** the sweep silently converting a recorded failure into a `PENDING` row and losing the failure history.

### EC-PERSIST-5 — Database file missing or unreadable at startup

- **Trigger:** the database file is absent, or present but unreadable or not a valid database.
- **Expected:** an absent database file is created fresh with the current schema and recorded schema version, which is a normal first-run path. A present-but-unreadable or corrupt database is a hard startup error with a clear error dialog; the application does not delete or overwrite it.
- **Avoid:** destroying a corrupt database that the user may wish to recover.

### EC-PERSIST-6 — Model-snapshot singleton and result-snapshot-link invariants (SPEC-038)

- **Trigger:** a write attempts to insert a second `judge` row or a second `embedding` row into `benchmark_run_models` for one run, or a `benchmark_results` row is written whose `(run_id, provider_id, model_name)` does not match a `role = 'test'` row in that run's model snapshot.
- **Expected:** the two model-snapshot singletons — at most one `judge` row, at most one `embedding` row per run — are enforced directly by the database via the partial unique indexes `ux_run_models_one_judge` / `ux_run_models_one_embedding`; a second insert of either role raises a UNIQUE violation rather than silently overwriting or duplicating the row. Separately, every `benchmark_results` row's `(run_id, provider_id, model_name)` matches a `role = 'test'` row in `benchmark_run_models` — this link is guaranteed at the write source (the run-creation transaction inserts `pending` result rows only for snapshotted test targets) rather than by a declared foreign key, since the same `(provider_id, model_name)` may legitimately appear under two roles in one run (SPEC-038).
- **Avoid:** relying on application-level checks alone for the singleton invariant instead of the DB-enforced partial unique indexes; a result row that references a `(provider_id, model_name)` absent from the run's `test`-role snapshot.

______________________________________________________________________

## 10. Platform

### EC-PLAT-1 — App-data folder cannot be created

- **Trigger:** the application's per-user data folder cannot be created — a permission or disk-space failure.
- **Expected:** a hard startup error with a clear error dialog naming the path and the reason. The application does not start without a writable data folder.
- **Avoid:** running with no persistence and silently losing all run data.

### EC-PLAT-2 — Display scaling or theme changes while a run is in progress

- **Trigger:** the operating system display scale or light/dark theme changes while a run is executing.
- **Expected:** the UI re-renders at the new scale and theme. The run continues unaffected; visual settings are excluded from the run's settings snapshot and may change live.
- **Avoid:** interrupting or corrupting the run because of a display change.

### EC-PLAT-3 — Monitor disconnected while the window is on it

- **Trigger:** the monitor showing the application window is disconnected.
- **Expected:** the window is repositioned onto an available display. Persisted window geometry that no longer fits any display is clamped to a valid on-screen position on the next launch.
- **Avoid:** a window stranded off-screen and unreachable.

### EC-PLAT-4 — Path with non-ASCII characters

- **Trigger:** a task file path, an export path, or the app-data path contains non-ASCII characters.
- **Expected:** all file input and output uses UTF-8 path handling; non-ASCII paths are read, written, and displayed correctly.
- **Avoid:** a file-not-found or mojibake failure on a valid non-ASCII path.

### EC-PLAT-5 — Long-running run across an OS sleep or wake

- **Trigger:** the operating system sleeps and later wakes while a run is in progress.
- **Expected:** on wake the pipeline continues. An inference call that was interrupted by the sleep is treated as a recoverable failure and retried under the adaptive-timeout policy. Wall-clock-based timeout measurement tolerates the sleep gap by classifying the interrupted attempt as a timeout or connection failure rather than a corrupt result.
- **Avoid:** recording a sleep-interrupted attempt as a valid, complete result.
