# Progress Widget — Description

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `state_machine.md`, `flow_diagram.md`, `implementation_structure.md`, `mockup.html`; `01_Main_Window/description.md`; `03_Resume_Benchmark_Widget/description.md`; `08_Cross_Cutting/08-B_benchmark_state_machine.md`; `08_Cross_Cutting/08-E_interfaces_contracts.md`; `08_Cross_Cutting/08-J_event_bus_catalog.md`; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`; `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`; `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`; `11_Services_and_Algorithms/15_LOG_FORMATTING.md`

The Progress Widget is the centre panel of the Benchmark workspace and the live view of the active benchmark run. It renders a header (stage badge, run name, rename pencil, Pause/Resume, Stop), run-progress counters grouped by result status, a segmented stage progress bar, a model panel with model-stability and provider-stability indicators, a current-task section, and a benchmark event-log panel. While a run is active the Benchmark workspace left configuration panel hides and this widget expands to fill the freed space. When no run is active the widget is read-only and can replay the saved state of a past run.

---

## Table of Contents

1. Role and ownership
2. Layout
3. Header row
4. Run-progress counters
5. Stage progress bar
6. Model panel and stability indicators
7. Current-task section
8. Benchmark event-log panel
9. Run log versus application log
10. State transitions (narrative)
11. Persistence
12. Event-bus integration
13. Service dependencies
14. Edge cases
15. Function inventory

---

## 1. Role and ownership

The Progress Widget owns the live presentation of one benchmark run at a time. It is responsible for:

- Rendering pipeline stage, counters, current task, and the run event log of the displayed run.
- Exposing the three run controls that operate on an active run: Pause/Resume, Stop, and rename.
- Surfacing model and provider health by reading the Adaptive Timeout Service and the Provider Circuit Breaker.
- Replaying a saved run in read-only form when no run is active.

The widget is **not** responsible for:

- Starting a run. The New Benchmark Widget owns run creation; see `02_New_Benchmark_Widget/description.md`.
- Resuming, deleting, or listing runs. The Resume Benchmark Widget owns those; see `03_Resume_Benchmark_Widget/description.md`.
- Driving the pipeline. The benchmark pipeline runs on a background worker and reports through the typed event bus.
- Writing the run log file or the application log file. Backend writers own both; the widget only displays the run log.

The widget never blocks the UI thread. Every update arrives through an event-bus signal delivered on the UI thread.

## 2. Layout

The widget is a single vertical column of stacked sections. The mockup `mockup.html` is the visual source of truth.

```
+-------------------------------------------------------------------+
| Header: [stage badge] run name [pencil]      [Pause/Resume] [Stop] |
+-------------------------------+-----------------------------------+
| Run Progress                  | Model                             |
|   Tasks 40 / 80 (50%)          |   Provider  lm_studio_local       |
|   ETA ~18s                     |   Model     liquid/lfm2-1.2b      |
|   Total Time 1m 07s            |                                   |
|   Initialized 0                |   [model stability indicator]     |
|   Keyword-wait 0               |   [provider stability indicator]  |
|   Cosine-wait 0                |                                   |
|   Judge-wait 40                |                                   |
|   Completed 0                  |                                   |
|   Failed 0                     |                                   |
|   [segmented stage progress bar]                                   |
|   [per-stage badge row]        |                                   |
+-------------------------------+-----------------------------------+
| Current Task                                                       |
|   Task   text_ops_proofread_email                                  |
|   Stage  inference                                                 |
|   Task Time 5s   Timeouts 0   Retry 2/3 - Connection refused        |
+-------------------------------------------------------------------+
| Run Event Log                                                      |
|   Verbosity [Normal v]  Search [............]  [Clear]             |
|   +-------------------------------------------------------------+  |
|   | 12:54:23 [system]   Benchmarking model=...                  |  |
|   | 12:54:25 [task_start] perf_tiny_xs_r0                        |  |
|   | 12:54:38 [done]     time=12800ms                            |  |
|   +-------------------------------------------------------------+  |
+-------------------------------------------------------------------+
```

Layout rules:

- The Run Progress and Model sections share one two-column row. On narrow widths the columns stack; the column order is preserved (progress above model).
- The Current Task section is a single full-width row.
- The Run Event Log panel takes the remaining vertical space and grows with the window.
- All spacing, radius, colour, and typography tokens come from `08_Cross_Cutting/08-D_color_palette_and_typography.md`. The widget embeds no literal hex values.

## 3. Header row

Components, left to right:

### 3.1 Stage badge

A pill showing the current pipeline stage of the displayed run. The stages are the five batched phases of the benchmark pipeline plus the terminal and frozen states defined in `08_Cross_Cutting/08-B_benchmark_state_machine.md`. Colour per stage:

| Stage | Phase | Tone token |
|---|---|---|
| `INITIALIZING` | 1 — init | `info` (blue) |
| `INFERENCE` | 2 — inference | `primary` (teal) |
| `KEYWORD_CHECK` | 3 — keyword | `warn` (amber) |
| `COSINE_CHECK` | 4 — cosine | `warn` (amber) |
| `JUDGE_CHECK` | 5 — judge | `warn` (amber) |
| `FINISHING` | terminal write | `primary` (teal) |
| `COMPLETED` | terminal | `success` (green) |
| `FAILED` | terminal | `error` (red) |
| `STOPPED` | terminal | `mute` (grey) |
| `PAUSED` | frozen | `mute` (grey), overlaid on the frozen phase name |

The badge text always carries the stage name; colour alone never conveys state (see `08_Cross_Cutting/08-D_color_palette_and_typography.md` §7).

### 3.2 Run-name label

The effective run name of the displayed run. Truncated with an ellipsis when it exceeds the available width; the full name appears in a tooltip.

### 3.3 Rename pencil (icon button)

A 28x28 icon button that opens the Rename Run modal dialog. It is **visible only while the displayed run is actively executing** — stages `INITIALIZING`, `INFERENCE`, `KEYWORD_CHECK`, `COSINE_CHECK`, `JUDGE_CHECK`, and `PAUSED`. It is hidden in the terminal stages `FINISHING`, `COMPLETED`, `FAILED`, and `STOPPED`, and hidden entirely when viewing a past run.

This is the only rename affordance outside the Resume Benchmark Widget. It exists so the user can rename the run in progress without leaving the Benchmark workspace. All other rename actions live in the Resume Benchmark Widget context menu; see `03_Resume_Benchmark_Widget/description.md`.

### 3.4 Pause / Resume button

A single toggling button. It reads `Pause` while a run is in an active phase and `Resume` while the run is `PAUSED`. It is disabled when no run is active. **This is the only Resume affordance in the widget, and it applies only to a `PAUSED` run.** The terminal states (`COMPLETED`, `FAILED`, `STOPPED`) offer no action buttons of any kind: a terminal state is final for this widget, the left configuration panel returns to the layout (`01_Main_Window/description.md` §4), and run continuation belongs to the Resume tab — selecting the run there opens the Resume Summary dialog with its full drift-detection and task-selection flow. The Progress widget never resumes, retries, or navigates a terminal run.

Tooltip while showing Pause: *"Pause — Finish the in-flight task, then freeze the pipeline. The run stays open; click Resume to continue. Settings cannot be changed while paused."*

Pause does not abort the in-flight task. The pipeline finishes the current task, persists its result, then halts cleanly with no stale worker threads, then the widget enters the Paused state. See `08_Cross_Cutting/08-B_benchmark_state_machine.md`.

While the pause is **draining** — between the user's Pause click and the `_run_paused` event — the stage badge / status line reads **`Pausing — finishing the current call…`** so the user knows the click was accepted and the pipeline is finishing the single in-flight call before parking. Because execution is strictly serial (D-R-16), there is **at most one in-flight call** to drain, so the draining window is bounded by one call. **Stop is available during this draining pause:** clicking Stop while pausing goes through the **same Stop confirmation dialog** as a normal Stop (SPEC-083) — Stop is destructive (it ends a run that would otherwise pause cleanly), so it is confirmed regardless of timing. **Only on confirm** does the cancellation upgrade to hard (DD-39): the draining call is aborted promptly (its row stays `PENDING`, to be re-run on resume) and the run ends as STOPPED rather than parking as paused (SPEC-026); the status line switches to **`Stopping — cancelling the current call…`**. Cancelling the confirmation leaves the pause to finish draining normally. See `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` §6.8 and `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §6.

### 3.5 Stop button

A destructive-style button. It is disabled when no run is active. Clicking it opens a confirmation modal dialog before any pipeline call.

Tooltip: *"Stop — Cancel the in-flight task and end this run. Completed results are kept; the run status becomes STOPPED and can be resumed later from the Resume tab."*

### 3.6 Pause versus Stop

Pause parks the pipeline after the in-flight task completes (work-preserving soft cancellation); Stop cancels the in-flight task promptly and terminates the run (hard cancellation, DD-39). They also differ in what the user does next and in how the app layout changes.

| Aspect | Pause | Stop |
|---|---|---|
| In-flight task | finishes and is persisted | aborted promptly (≤ `provider.hard_cancel_max_ms`); nothing partial saved — its row stays `PENDING` and is re-run on resume |
| Pipeline worker | parked, awaiting Resume | parked, then terminated |
| Persisted run status | `INCOMPLETE` if never resumed (Pause is an in-memory `RUNNING` → `PAUSED` transition that is not itself persisted; a paused run left un-resumed is persisted as `INCOMPLETE`) | `STOPPED` (persisted) |
| Window layout | unchanged — left panel stays hidden, centre stays expanded | idle layout restored — left panel reappears, centre shrinks |
| Benchmark interface | stays active and visible | returns to the initial state for starting or resuming a run |
| Confirmation | none | yes — confirmation modal dialog |
| Settings reachable | no (still locked) | yes (run no longer active) |
| User next action | click Resume in this widget | switch to Resume tab, then Resume Run |
| Emitted event | `_run_paused` | `_run_stopped` |

`RUNNING` and `PAUSED` are in-memory run states. `INCOMPLETE`, `COMPLETED`, `FAILED`, and `STOPPED` are the persisted `RunStatus` values; see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`. A paused run that is never resumed is persisted as `INCOMPLETE` and is fully resumable. A stopped run is persisted as `STOPPED` and is also fully resumable.

The Progress Widget has **no Delete control**. Deletion is available only from the Resume Benchmark Widget context menu and only for non-active runs.

## 4. Run-progress counters

A label-and-value grid. Counter keys are the canonical `ResultStatus` members defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` and `08_Cross_Cutting/08-E_interfaces_contracts.md`. They give a per-phase breakdown of the batched five-phase model.

| Label | Value source | Tooltip |
|---|---|---|
| Tasks | `completed_count / total_count` plus percentage | "Tasks resolved (any outcome)" |
| ETA | rolling average of completed task durations | "Estimated time remaining" |
| Total Time | run elapsed time read from the data store | "Total elapsed — survives pause and resume" |
| Pending | `counts_by_status[PENDING]` | "Created, inference not yet started" |
| Keyword-wait | `counts_by_status[AWAITING_KEYWORD_CHECK]` | "Inference done, keyword check pending" |
| Cosine-wait | `counts_by_status[AWAITING_COSINE_CHECK]` | "Keyword done, cosine check pending" |
| Judge-wait | `counts_by_status[AWAITING_JUDGE_CHECK]` | "Cosine done, judge check pending" |
| Completed | `counts_by_status[COMPLETED]` | "All applicable phases done" |
| Failed | sum of `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, and `ERRORED` | "Tasks that failed or errored (a graded task that merely scored FAIL is COMPLETED, not failed)" |

`Total Time` is read from the data store, not from an in-memory wall clock, so it stays correct across pause and resume — elapsed time is persisted and updated after each task completes.

Counters refresh on every `_progress_updated` event, which the pipeline emits after each task transition and which carries the `counts_by_status` map. Per-phase counters irrelevant to the current run mode read 0; a counter that is structurally impossible for the mode (for example, the validation-phase counters in a performance-only run) is hidden rather than shown as 0.

## 5. Stage progress bar

Below the counters, a segmented horizontal bar visualises tasks by pipeline position. Each segment is sized by its share of `total_count`.

| Segment | Tone | Meaning |
|---|---|---|
| Bench | `primary` | Inference done, awaiting a validation phase or no grading required |
| Judge-wait | `warn` | Inference done, judging pending |
| Failed | `error` | Terminal failures |
| Pending | `mute` | Not yet started |
| Done (100% complete) | `success` | At full completion the entire bar renders in the success tone — see below |

**Complete (`done`) fill.** When the run reaches 100% completion — every task in `COMPLETED` and no pending, judge-wait, or failed share remaining — the bar collapses to a single full-width segment painted in the `success` tone, matching the COMPLETED-state mockup (the viewing-past-run and finished panels). This is the visual counterpart of the `done` badge: the `done` badge is derived from `COMPLETED` (the count of completed tasks) and is shown throughout the run, while the success-toned **full** bar fill is the terminal rendering shown only at 100% completion. Below 100%, completed tasks contribute to the `bench` (`primary`) segment as before; the bar only turns fully `success` at full completion.

Below the bar, a row of compact badges shows per-stage counts, for example: `bench 35   judge-wait 5   pending 40   done 35   failed 0`.

The `judge-wait` segment and badge appear only when the run performs per-task judge validation. They are hidden when the judge phase is not part of the run. When the judge phase is active, both `bench` (inference complete) and `judge-wait` appear.

All segment and badge values derive from the same `counts_by_status` map:

- `bench` — rows in any `AWAITING_*_CHECK` state or `COMPLETED` (inference done, regardless of pending validation phase).
- `judge-wait` — `AWAITING_JUDGE_CHECK` specifically.
- `done` — `COMPLETED`.
- `failed` — the aggregate failure badge: `FAILED_INFERENCE` + `FAILED_PROVIDER` + `FAILED_TIMEOUT` + `FAILED_JUDGE_TIMEOUT` + `ERRORED` (a per-reason badge may break one out; §below).
- `pending` — `PENDING` (rows created but not yet started; at most one is momentarily `RUNNING_INFERENCE` under serial execution).

**Per-reason failure badges.** When a specific terminal-failure reason dominates the failures, the badge row renders that reason as its own `error`-toned badge in place of (or alongside) the aggregate `failed` badge, so the user sees *why* tasks failed without opening the log. At minimum the judge-timeout reason is broken out:

| Per-reason badge | `ResultStatus` source | Tone |
|---|---|---|
| `failed_judge_timeout <N>` | `FAILED_JUDGE_TIMEOUT` (judge call exhausted its adaptive budget — DD-34) | `error` |

The `failed_judge_timeout` badge appears when one or more results settled `FAILED_JUDGE_TIMEOUT` — for example after a judge-model exclusion (§6.2), where the remaining judge-phase tasks settle to that status directly. The badge label is the lowercase status name; `<N>` is the count of results in that status.

## 6. Model panel and stability indicators

The right column of the progress row.

### 6.1 Identification

- **Provider** — the display name resolved from the `current_provider_id` field of the `_progress_updated` payload (DD-33). For a **live** run the widget resolves the id through the `ProviderRegistry` / `ProvidersStore` so a rename mid-session takes effect immediately. For a **past** (completed) run the widget instead reads the snapshotted `provider_name` from the relevant `BenchmarkResult` row (or `BenchmarkRun.judge_provider_name` for judge events), so the original display name is preserved across later renames.
- **Model** — `current_model` from the `_progress_updated` payload. While the active result is in its **judge phase** (the current stage is `judge`, i.e. a `BENCHMARK_JUDGE` call is in flight), the Model value appends the role suffix **`(judging)`** to make clear the named model is acting as the judge rather than the test model — for example `qwen3:1.7b (judging)`. The shorter form **`(judge)`** is the equivalent suffix used when the panel is labelling the judge model in a non-streaming context (for example a Model row whose stability is the judge-exclusion callout); both denote role=JUDGE. Outside the judge phase no suffix is appended.

When viewing a past run the identification grid is replaced by a **post-run Model summary** — a label-and-value grid in the same Model panel slot, with these three rows in this order (labels rendered verbatim):

| Label | Value source |
|---|---|
| `Models tested` | the count of distinct test models in the run's frozen model snapshot (distinct `(provider_id, model_name)` test-model rows). |
| `Providers used` | the count of distinct providers the run used, rendered from the distinct snapshotted `name` values on `benchmark_run_providers`. |
| `Excluded mid-run` | the count of models the Adaptive Timeout Service excluded during the run (role=INFERENCE exclusions plus any judge-model exclusion), read from the run's persisted exclusion record. `0` when none were excluded. |

These three rows **replace** the live Provider / Model identification rows in the `ViewingPastRun` state; the live Provider and Model rows are shown only while a run is in flight. (The mockup's COMPLETED panel shows `Models tested 10`, `Providers used 2`, `Excluded mid-run 0`.)

### 6.2 Model stability indicator

The Model panel renders up to **two** stability callouts. The **test-model callout** (always present) reads the Adaptive Timeout Service state for the current `(provider_id, model_name, role=INFERENCE)` bucket — that is, the test-model being benchmarked — and reflects only the role=INFERENCE state. A **judge-model exclusion callout** (present only after the judge model has been excluded) reflects the role=JUDGE bucket; see "Judge-model exclusion callout" below. See `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`.

Test-model callout (role=INFERENCE):

| Indicator | When | Tone |
|---|---|---|
| OK | no consecutive maximum-timeout failures at role=INFERENCE | `success` |
| N of M maximum-timeouts used — "K more maximum-timeouts and this model is excluded" | between 1 and `benchmark.consecutive_max_timeouts_to_exclude` | `warn` |
| Model excluded — remaining tasks for this model are marked FAILED_TIMEOUT | role=INFERENCE exclusion threshold reached | `error` |

The warning band gives the user a clear chance to intervene — Stop the run, check or restart the model server — before the model is auto-excluded.

**Judge-model exclusion callout (role=JUDGE).** When the judge model crosses its role=JUDGE consecutive-max-timeout threshold, the pipeline emits `_judge_model_excluded` (payload `JudgeModelExcludedEvent`). On that event the Model panel renders a **second, red (`error`-toned) stability callout** beneath the test-model callout, reading the template:

> **Judge model excluded** — `<N>` consecutive max-budget timeouts · remaining tasks' judge phase will be skipped

where `<N>` is the event payload's `consecutive_timeouts`. The two callouts are independent because role=JUDGE and role=INFERENCE are separate Adaptive-Timeout buckets (DD-34): the test-model callout stays in its own band (typically OK) while the judge callout is `error`. The judge callout appears at most once per run (the event fires at most once per `BENCHMARK_RUN` activity) and persists for the remainder of the run. This callout is **in addition to**, not instead of, the Event-Log `judge_excluded` entry (§8.3, §9) — the same exclusion is surfaced both as the persistent panel callout and as the one-time log line, so a user who is not watching the log still sees the state.

### 6.3 Provider stability indicator

A callout that reads the Provider Circuit Breaker state for the current `provider_id`; see `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`.

| Breaker state | Indicator | Tone |
|---|---|---|
| `CLOSED`, no recent failures | Provider responsive — last probe N s ago | `success` |
| `CLOSED`, 1–2 recent failures | N failures in the last M min — still serving | `warn` |
| `OPEN` | Provider unresponsive — circuit breaker open — N consecutive failures across K models — last probe failed | `error` |
| `HALF_OPEN` | Probing provider — next probe in N s | `warn` |

In the `OPEN` state the callout shows two inline links: **retry probe** triggers an immediate health probe instead of waiting for the cooldown, and **switch provider in Settings** opens the Settings dialog at the Providers section. The Settings link stays visible while the run is active even though the Settings dialog itself is gated; activating it surfaces the gating message.

### 6.4 Stability event

The test-model and provider callouts repaint on the `_model_stability_changed` event. The pipeline emits it whenever the Adaptive Timeout Service records a failure, promotes, or excludes a model, or whenever the Provider Circuit Breaker changes state. The payload is the `ModelStabilityChangedEvent` struct catalogued in `08_Cross_Cutting/08-J_event_bus_catalog.md`. The **judge-model exclusion callout** (§6.2) is driven instead by the `_judge_model_excluded` event (payload `JudgeModelExcludedEvent`); the widget renders the red judge callout on receipt and keeps it for the rest of the run.

## 7. Current-task section

A label-and-value grid for the in-flight task.

| Label | Source | Notes |
|---|---|---|
| Task | `task_id` of the current result | |
| Stage | current evaluation stage of the task | normally `inference`, `keyword`, `cosine`, or `judge`. When the task is parked because the provider circuit breaker is open, the Stage value reads **`waiting for circuit-breaker probe`** in `error` tone — the task is not progressing through a phase but is waiting for the next provider health probe (§6.3). |
| Task Time | wall time since the current task started | |
| Timeouts | timeouts accumulated on the current task | |
| Retry | `attempt / total_attempts` and the classified reason | shown in `error` tone while a retry is active |
| Inference progress | the most recent `_inference_progress` event with `context=BENCHMARK_TASK` for the active task (`08_Cross_Cutting/08-J_event_bus_catalog.md` §5.3, payload `InferenceProgressEvent`) | a live counters-only status indicator with two sub-states (see §7.1); hidden when no main inference is in flight; **verbosity-independent** |
| Judge progress | the most recent `_inference_progress` event with `context=BENCHMARK_JUDGE` for the active result (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.19a, §7.7a) | a live counters-only status indicator with two sub-states (see §7.1); hidden when no judge call is in flight; **verbosity-independent**; rendered only when the run grades and the per-task judge phase is on (GRADED only) |

The Retry line appears in error tone while a retry is in progress and clears when the task finishes. The classified reason text comes from the `reason` field of the `_task_retry` payload; see `08_Cross_Cutting/08-J_event_bus_catalog.md`. When viewing a past run the section shows a single **"(complete)"** placeholder. When the run is **paused**, the Current-task section shows the single placeholder **"(paused — in-flight task finished and saved)"** — the fuller wording makes clear that Pause let the in-flight task finish and persist before parking (rather than aborting it).

### 7.1 Inference progress row and Judge progress row

The Current-task section renders **two distinct sub-rows** for live LLM-call progress — one for the per-task main inference call, one for the per-task judge call — controlled by the `context` field of the most recent `_inference_progress` event for the active task. Each row's payload carries counters only — `elapsed_ms`, `tokens_received`, and `first_token_received` — never any portion of the model response text. The shared emitter helper (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9) emits at ≥ 1 Hz for the duration of each `chat_stream` call.

The Current-task controller subscribes to `_inference_progress` and **filters by `context`** — it accepts events whose `context` is `BENCHMARK_TASK` or `BENCHMARK_JUDGE` and ignores every other context (`RUN_ANALYSIS` and `PROVIDER_TEST` belong to other surfaces and are routed to those surfaces' subscribers — see `07_Common_Dialogs/generate_analysis_dialog.md` §8 and `06_Settings_Dialog/sub_dialogs/provider_edit.md` §8.2).

The same `result_id` produces progress events of both contexts **sequentially** as the result transitions through phases: first a stream of `BENCHMARK_TASK` events while the main inference is in flight, then (in `GRADED` with the per-task judge phase on) a stream of `BENCHMARK_JUDGE` events while the judge call is in flight. The two streams never overlap on one `result_id` by construction — the judge call cannot start until the main inference completes — and the Current-task section renders only the most recent event for the active result, so a `BENCHMARK_TASK` event observed after a `BENCHMARK_JUDGE` event for the same `result_id` would be an out-of-order delivery (defensive: it is ignored; see `08_Cross_Cutting/08-I_edge_cases.md`).

#### 7.1.1 Inference progress sub-row (`context == BENCHMARK_TASK`)

| Sub-state | Condition | Rendering |
|---|---|---|
| **A — waiting** | No `_inference_progress` snapshot with `context=BENCHMARK_TASK` has yet arrived with `first_token_received == True` for the active result. | `Waiting for first token — N.N s` where the seconds value is `elapsed_ms / 1000` from the latest snapshot. Tone: `info`. |
| **B — generating** | The latest `_inference_progress` snapshot with `context=BENCHMARK_TASK` for the active result has `first_token_received == True`. | `Generating — N tokens · T.T s elapsed` where `N` is `tokens_received` and `T.T` is `elapsed_ms / 1000` from the latest snapshot. Tone: `primary`. |

#### 7.1.2 Judge progress sub-row (`context == BENCHMARK_JUDGE`)

| Sub-state | Condition | Rendering |
|---|---|---|
| **A — judge waiting** | No `_inference_progress` snapshot with `context=BENCHMARK_JUDGE` has yet arrived with `first_token_received == True` for the active result. | `Judge: waiting for response — N.N s` where the seconds value is `elapsed_ms / 1000` from the latest snapshot. Tone: `info`. |
| **B — judge receiving** | The latest `_inference_progress` snapshot with `context=BENCHMARK_JUDGE` for the active result has `first_token_received == True`. | `Judge: receiving — N tokens · T.T s elapsed` where `N` is `tokens_received` and `T.T` is `elapsed_ms / 1000` from the latest snapshot. Tone: `primary`. |

#### 7.1.3 Visibility and reset rules

Both sub-rows share the same visibility discipline:

- Each sub-row is **hidden** when no in-flight call of its context is active for the displayed result. When the widget is in the `Empty`, `Initializing`, `Paused` after a clean per-task boundary, `Stopping`, or `ViewingPastRun` states with no current inference, both sub-rows are hidden.
- **Exception — inference row during the judge phase.** When the active result has finished its main inference and moved into its judge phase (a `BENCHMARK_JUDGE` call is in flight), the Inference progress sub-row is **not** hidden; instead it shows the italic muted placeholder **`(complete — main inference finished)`** while the Judge progress sub-row renders the live judge call. This makes the two-phase sequence legible — the user sees that inference completed and the judge call is now running on the same result. The inference row reverts to hidden once the result leaves its in-flight states entirely (on `_task_completed` / `_task_failed` or the next task's `_inference_started`).
- The Inference progress sub-row is **shown and reset** by each `_inference_started` for the active task: sub-state A is rendered immediately, with `0.0 s` until the first progress emission arrives.
- The Judge progress sub-row is **shown and reset** by each `_judge_started` for the active result: sub-state A is rendered immediately, with `0.0 s` until the first progress emission arrives.
- Each sub-row is **replaced** by the next task's `_inference_started` — there is no stale carry-over from the previous task.
- Each sub-row is **hidden** when the displayed result transitions away from in-flight state — on `_task_completed`, `_task_failed`, or the next task's `_inference_started`.
- Both sub-rows are **verbosity-independent**: they are Current-task status indicators, not log entries, so they do NOT depend on the run-log Verbosity dropdown setting (`ui.run_log_verbosity`). They render in `Short`, `Normal`, and `Verbose` identically.
- When the token-estimation source on the active call is the 4-character heuristic (no provider per-chunk `delta_tokens` and no provider running count — see `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.5a), the active sub-row appends `~` immediately before the token count (for example `Generating — ~N tokens · T.T s elapsed`, or `Judge: receiving — ~N tokens · T.T s elapsed`) to surface that the count is an approximation.

## 8. Benchmark event-log panel

The lower region of the widget. A read-only multi-line view with per-event HTML rendering. It shows the **run event log** for the displayed run only — never the application log.

### 8.1 Toolbar

- **Verbosity** — a dropdown with `Short`, `Normal`, and `Verbose`. It controls which fields render per event. Persisted in `ui.run_log_verbosity`; default `Normal`.
- **Search** — a single-line input that filters visible lines and highlights matches. Case-insensitive substring match.
- **Clear** — a button that clears the visible view only. It does not touch the run log file or the cached raw events; switching verbosity afterwards re-renders the full buffer.
- **Log-write-failure warning indicator** — a small `warn`-toned line shown **between the toolbar and the log box** (only when active). It appears when the run-log **file** writer fails to write — disk full, path not writable (EC-LOG-1) — signalled by the `file_write_warning` view-model field. It carries a warning-triangle glyph and short text such as **"Run log file write failed — the on-screen log is still live"**, making clear that on-screen rendering continues from the in-memory buffer even though the file is no longer being written. The indicator is hidden (removed from the layout, per `08-L` §1) whenever no write failure is active.

### 8.2 Verbosity-aware fields

The pipeline always records the full Verbose stream to the per-run log file `<app-data>/logs/run/run_<run_id>_<unix_ts>.log`. The verbosity dropdown controls only what is rendered in the panel — switching verbosity re-renders the cached raw events without touching the file, which is always written with the full Verbose field set. The verbosity model for the prompt and response text fields is:

- **Verbose** — the FULL untruncated text of every prompt and response is shown (system prompt, user prompt / task, model response), with the character and token counts alongside.
- **Normal** — a truncated text excerpt plus the character and token counts (the previous "Verbose" behaviour for these fields).
- **Short** — character and token counts only, no text content (the previous "Normal" behaviour for these fields).

All other fields (timestamp, event-kind tag, provider, model, task id, stage, timings, retries, errors, judge verdict) keep their per-level visibility unchanged. The field selection per level is defined in `11_Services_and_Algorithms/15_LOG_FORMATTING.md`:

| Field | Verbose | Normal | Short |
|---|:---:|:---:|:---:|
| timestamp | yes | yes | yes |
| event kind tag | yes | yes | yes |
| provider name | yes | yes | yes |
| model name | yes | yes | yes |
| task id | yes | yes | yes |
| stage | yes | yes | yes |
| start / end timestamp | yes | yes | yes |
| system prompt | full content + size | truncated excerpt + size | size only |
| user prompt (task) | full content + size | truncated excerpt + size | size only |
| model response | full content + size | truncated excerpt + size | size only |
| time to first token | yes | no | no |
| total time | yes | yes | no |
| tokens per second | yes | no | no |
| token counts | yes | no | no |
| retry attempts and reason | yes | reason only | count only |
| errors | yes | yes | yes |
| judge verdict and reasoning | yes | verdict and reasoning | verdict only |

The judge returns a binary verdict — PASS or FAIL — plus a one-sentence explanation. It returns no numeric score. The numeric score shown elsewhere in result tables is the cosine-similarity measurement, not a judge output. See `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` is unrelated; the judge contract lives in the evaluation pipeline spec.

The mockup `mockup.html` shows the same task list at all three verbosity levels.

### 8.3 Event kinds

Each event kind renders with a distinct tone token from `08_Cross_Cutting/08-D_color_palette_and_typography.md`. The mapping is owned by the log-formatting service in `11_Services_and_Algorithms/15_LOG_FORMATTING.md`:

| Kind | Source signal | Tone |
|---|---|---|
| `stage` | `_stage_changed` | `info` |
| `system` | `_model_stability_changed` / `_provider_registry_reloaded` (registry and breaker notes) | `info` |
| `task_start` | `_inference_started` | `primary` |
| `done` | `_task_completed` | `success` |
| `judge_started` | `_judge_started` | `warn` |
| `judge` | `_judge_completed` | `warn` |
| `retry` | `_task_retry` | `error` |
| `provider_switch` | `_provider_switched` | `info` |
| `model_switch` | `_model_switched` | `info` |
| `stop` | `_run_stopped` | `mute` |
| `finished` | `_run_finished` | `success` |
| `failed` | `_run_failed` | `error` |
| `judge_excluded` | `_judge_model_excluded` (payload `JudgeModelExcludedEvent`, `08_Cross_Cutting/08-Q_event_payload_schemas.md` §3.6a) | `error` |
| `task_judge_timeout` | `_task_completed` carrying `status = FAILED_JUDGE_TIMEOUT` (per-task judge-call exhaustion; the affected result settled to the new terminal status — DD-34) | `error` |

The `judge_excluded` event log entry renders the canonical text **"Judge model '\<name\>' excluded: \<N\> consecutive max-budget timeouts. Remaining tasks' judge phase will be skipped."** — where `<name>` is the live-resolved display name of the excluded judge provider (read from the registry while the run is in flight, per DD-33) and `<N>` is the event payload's `consecutive_timeouts`. The line appears exactly once per run (the event itself fires at most once per `BENCHMARK_RUN` activity).

The `task_judge_timeout` event log entry renders **"Task '\<task_id\>' settled FAILED_JUDGE_TIMEOUT: judge call exhausted adaptive budget for this task."** — one line per affected task. After the judge-model exclusion has fired (`judge_excluded` above) the remaining `task_judge_timeout` lines for affected tasks render in the more concise form **"Task '\<task_id\>' skipped judge: judge model excluded."** (driven by the `error_message` field on the result).

The pause and resume run-control actions append `system`-kind Event-Log lines with canonical text. On pause the line reads **"Run paused by user · pipeline parked, no stale threads"**; on resume the line reads **"Run resumed by user · pipeline restarted from the frozen stage"**. Both render in the `system` tone (`info`). These are fixed strings, not free-form messages, so the log reads consistently across runs.

The widget never builds the HTML itself. It passes the event to the log-formatting service and appends the returned line.

### 8.4 Buffer cap

The visible buffer holds at most `ui.run_log_max_lines` lines (default 100000; user-configurable within the hard range 1,000–500,000, clamped if out of range). The panel renders one line per pipeline event, so the cap counts events and lines interchangeably. When the cap is exceeded, the oldest lines are removed from the top. The per-run log file is never trimmed by the widget.

### 8.5 Auto-scroll

The panel auto-scrolls to the newest line while the user has not scrolled away from the bottom. If the user scrolls up, auto-scroll suspends until they return to the bottom. The auto-scroll preference is persisted in `ui.auto_scroll_run_log`.

## 9. Run log versus application log

The app maintains two independent log streams. The Progress Widget displays only the run log.

| Aspect | Run log | Application log |
|---|---|---|
| Purpose | what happened during a benchmark run — user facing | internal app behaviour — support facing |
| Display | this panel, plus a per-run file | not shown in any UI |
| File path | `<app-data>/logs/run/run_<run_id>_<unix_ts>.log` | `<app-data>/logs/app/app.log` plus rotation files |
| One file per | run | app lifetime (rotating) |
| Verbosity model | field density — Short, Normal, Verbose | severity level — DEBUG, INFO, WARNING, ERROR, CRITICAL |
| Verbosity setting key | `ui.run_log_verbosity` | `logging.app_log_level` |
| Write-to-file setting key | `logging.write_run_log_to_file` | `logging.write_app_log_to_file` |
| Always written in full | yes | filtered by level at write time |

The run log is a curated subset of pipeline-emitted event-bus signals, formatted by the log-formatting service. The application log is structured developer logging written by the structured logging stack and is out of scope for this widget.

## 10. State transitions (narrative)

The widget has one state per pipeline situation. Full diagram in `state_machine.md`.

- **Empty** — no run active and no run selected. All controls hidden; counters show dashes; the log panel shows a placeholder.
- **Initializing** — `_run_started` received. Stage badge shows `INITIALIZING`. Stop available; Pause not yet available; rename pencil visible.
- **Running** — the run is in `INFERENCE`, `KEYWORD_CHECK`, `COSINE_CHECK`, or `JUDGE_CHECK`. Pause, Stop, and rename available; counters and log update live.
- **Paused** — Pause finished the in-flight task and parked the pipeline. The badge shows `PAUSED`; Resume and Stop available; counters frozen; layout unchanged.
- **Stopping** — Stop confirmed; the pipeline is cancelling the in-flight task (hard cancel, bounded by `provider.hard_cancel_max_ms` — DD-39) and terminating. Status line reads `Stopping — cancelling the current call…`; controls disabled; badge shows `STOPPED` after the terminal event.

**Draining-sub-state safety net (SPEC-098).** The transient `Pausing`/`Stopping` sub-states are entered on the user's click (no bus event) and normally left on `_run_paused` / `_run_stopped` / `_run_failed`. To guard against a lost terminal event (a wedged dispatcher per SPEC-015, or a crash after the gate is released but before the event is delivered), on entering either sub-state the widget arms a **bounded reconciliation timeout** (a small multiple of the worst-case drain bound — `provider.hard_cancel_max_ms` plus a margin). On expiry the widget **re-reads the run's authoritative status** (`BenchmarkFlowApi.is_running()` and the persisted `RunStatus`) and reconciles: if the run is no longer active, it leaves the draining sub-state for the correct terminal/paused display instead of sticking on `Pausing…/Stopping…`. No new bus event is introduced; this is a client-side fallback only.
- **Viewing past run** — no run active; a past run is selected through the Resume tab or a run dropdown. Read-only: terminal badge, frozen final counters, log replayed from the run file, no controls.

## 11. Persistence

| State | Stored where | When written |
|---|---|---|
| Run log verbosity | `ui.run_log_verbosity` | on dropdown change |
| Auto-scroll preference | `ui.auto_scroll_run_log` | on toggle |
| Run log buffer cap | `ui.run_log_max_lines` | settings only; read at construction |
| Run elapsed time | data store `runs` row | by the pipeline after each task |
| Run name | data store `runs` row | by the rename action |
| Run log content | per-run log file | by the run-log file writer, gated by `logging.write_run_log_to_file` |

The widget holds no run state of its own across restarts. On reopen it rebuilds from the data store and the run log file.

## 12. Event-bus integration

All subscriptions are owner-bound to this widget; the bus auto-cancels them on destruction (see `08_Cross_Cutting/08-J_event_bus_catalog.md`).

Subscribed signals:

| Signal | Handler effect |
|---|---|
| `_run_started` | reset all sections to a fresh run |
| `_stage_changed` | repaint the stage badge |
| `_progress_updated` | refresh counters, stage bar, model identification |
| `_inference_started` | update the current-task section; append a log line |
| `_task_completed` | append a log line; refresh counters |
| `_judge_started`, `_judge_completed` | append log lines |
| `_judge_model_excluded` | render the red judge-model exclusion stability callout (§6.2) and append the `judge_excluded` log line (§8.3) |
| `_task_retry` | set the Retry line with the classified reason |
| `_model_stability_changed` | repaint the stability callouts |
| `_provider_switched`, `_model_switched` | append log lines |
| `_run_paused`, `_run_resumed` | enter or leave the Paused state |
| `_run_stopped`, `_run_finished`, `_run_failed` | enter the matching terminal state |
| `_run_renamed` | update the run-name label |
| `_run_id_changed` | when no run is active, load the selected run's saved state and log |
| `_model_stability_changed` / `_provider_registry_reloaded` (system notes), `_log_cleared` | append or clear log lines |

Emitted signals: the widget emits none directly. Run control actions call services that emit on its behalf — Pause and Resume call the benchmark flow service, Stop calls it after confirmation, and rename calls the run-registry service which emits `_run_renamed`.

## 13. Service dependencies

The widget factory receives these dependencies (see `implementation_structure.md`):

- **Event bus** — all live updates.
- **Benchmark flow service** — `pause()`, `resume()`, `stop()` for the active run.
- **Run-registry store** — read run metadata; `rename_run(run_id, new_name)`.
- **Data store** — read run elapsed time and terminal run summary.
- **Run-log file reader** — load the saved log of a past run.
- **Log-formatting service** — render each event into an HTML log line at the chosen verbosity.
- **Adaptive Timeout Service** and **Provider Circuit Breaker** — read live model and provider stability state (the `_model_stability_changed` payload already carries a snapshot; direct reads back the "retry probe" action).
- **Settings store** — read and persist `ui.run_log_verbosity` and `ui.auto_scroll_run_log`.

## 14. Edge cases

Referenced by ID from `08_Cross_Cutting/08-I_edge_cases.md`:

- **EC-RUN-1** — Start clicked while a run is active. The New Benchmark Widget gates Start; this widget's Pause and Stop are the active controls instead.
- **EC-RUN-2** — Pause clicked between two stages. Pause waits for the in-flight task to finish, then parks; no task is split.
- **EC-RUN-4** — Window close while a run is in progress. The Stop confirmation modal precedes the quit; see `01_Main_Window/description.md`.
- **EC-PROV-1** — Model returns an HTTP error during inference. The Retry line shows the classified reason.
- **EC-PROV-2** — All retries exhausted for a task. The Retry line clears and the Failed counter increments.
- **EC-PROV-3** — Provider trips the circuit breaker. The provider stability callout enters the `OPEN` band with the retry-probe link.
- **EC-PROV-4** — Test (inference-role) model crosses the adaptive-timeout exclusion threshold (role=INFERENCE). The model stability callout enters the `error` band; remaining tasks for that model are marked `FAILED_TIMEOUT` by the pipeline.
- **EC-PROV-4a** — Per-task judge call exhausts its adaptive budget (role=JUDGE). The Event Log appends one `task_judge_timeout` entry; the task settles `FAILED_JUDGE_TIMEOUT`. The model stability callout (role=INFERENCE) is NOT affected.
- **EC-PROV-4b** — Judge model crosses the role=JUDGE consecutive-max threshold. The Event Log appends exactly one `judge_excluded` entry rendered as "Judge model '\<name\>' excluded: \<N\> consecutive max-budget timeouts. Remaining tasks' judge phase will be skipped." Subsequent affected tasks emit `task_judge_timeout` entries in the concise "Task '\<id\>' skipped judge: judge model excluded." form. The run does NOT abort.
- **EC-PROV-4c** — Embedding call times out (fixed `eval.embedding_timeout_seconds`). No log entry is emitted at the Event Log level; the per-task `_task_completed` event surfaces `cosine_verdict = None` for that task. The embedding model is not excluded.
- **EC-LOG-1** — Run log file write fails. The toolbar shows a warning indicator; the panel keeps rendering from the in-memory buffer.
- **EC-LOG-3** — Verbosity changed mid-run. The panel re-renders from the cached raw events; no event is lost.
- **EC-PERF-3** — High-rate task completion. Counter and log updates are coalesced; the buffer stays bounded by `ui.run_log_max_lines`.
- **EC-PERSIST-2** — Orphan run detected at startup. A run left `INCOMPLETE` is rendered with its terminal badge and frozen counters; no controls are shown.

## 15. Function inventory

A flat list of every callable behaviour, for tester traceability.

| Function | Primitive | Gated by |
|---|---|---|
| Rename the running run | icon button (pencil) | displayed run is in a non-terminal stage |
| Pause the run | button | run in an active phase (`INFERENCE`, `KEYWORD_CHECK`, `COSINE_CHECK`, `JUDGE_CHECK`) |
| Resume the run | button | run in `PAUSED` |
| Stop the run | button | run in a non-terminal stage; confirmation required |
| Change run-log verbosity | dropdown | always; persists to `ui.run_log_verbosity` |
| Search the run log | single-line input | always |
| Clear the visible run log | button | always; clears the view only |
| Toggle auto-scroll | implicit on scroll | persists to `ui.auto_scroll_run_log` |
| Cap the run-log buffer | implicit | bounded by `ui.run_log_max_lines` |
| Retry the provider health probe | inline link | provider breaker state is `OPEN` |
| Open Settings at Providers | inline link | provider breaker state is `OPEN`; surfaces the gating message while a run is active |
| Load and replay a past run | implicit on `_run_id_changed` | no run active |
