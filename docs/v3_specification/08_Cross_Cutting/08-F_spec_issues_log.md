# Design Decisions Log

**Status:** Draft
**Owner:** human-reviewer
**Audience:** human, arch, coder, tester
**Last Updated:** 2026-06-03
**Cross-references:** `08_Cross_Cutting/08-C_settings_hierarchy.md`, `08_Cross_Cutting/08-G_feature_flags.md`, `08_Cross_Cutting/08-P_judge_protocol.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `15_Risks_and_Open_Questions/02_OPEN_QUESTIONS.md`

This document is the consolidated log of resolved design decisions for the application. Each entry records one decision: the topic it concerns, the decision itself, the rationale behind it, and the spec areas that depend on it. The log exists so that a reviewer or implementer can see *why* the specification reads the way it does and so that settled questions are not re-litigated. It records only resolved decisions; questions still open are tracked in `15_Risks_and_Open_Questions/02_OPEN_QUESTIONS.md`. Each decision below is a standalone statement about the application as specified; the log carries no history of how the decision was reached.

---

## Table of Contents

1. How to use this log
2. Decision entries
   - DD-01 Composite (provider, model) identity
   - DD-02 Per-task judge stage and run-level analysis are independent
   - DD-03 Settings unreachable while a run is non-terminal
   - DD-04 Run management is read-only while a run is non-terminal
   - DD-05 Status-bar health indicator auto-tests providers
   - DD-06 Retry selection pre-selects only failed rows
   - DD-07 Per-row Reset reverts to the last saved value
   - DD-08 Judge analysis text is never truncated
   - DD-09 Drag-and-drop is restricted to dedicated drop zones
   - DD-10 Env-var conversion is offered after Import
   - DD-11 Two independent log streams
   - DD-12 Three single-purpose folder buttons
   - DD-13 Per-secret authentication source toggle
   - DD-14 Result tables expose the full field set with persistent filters
   - DD-15 Chart gallery with universal per-chart filters
   - DD-16 No duration estimates
   - DD-17 Transport streaming is always on; the toggle is UI-only
   - DD-18 The judge receives no model identity
   - DD-19 Mode-aware run summary dialog
   - DD-20 In-window menu bar on every platform
   - DD-21 Dialog button ordering
   - DD-22 Full dark and light theme token sets
   - DD-23 Platform detection at startup
   - DD-24 Task Editor is a full-window workspace
   - DD-25 Run-management actions are owned by the Resume widget
   - DD-26 Uniform Result-widget export footer
   - DD-27 Binary verdict; cosine is the only numeric score
   - DD-28 Three run modes
   - DD-29 No schema migration framework
   - DD-30 Run-level judge analysis is optional in every mode (2026-06-02)
   - DD-31 Redaction is scoped to three surfaces; "sole egress path" wording retired (2026-06-01)
   - DD-32 Live inference-progress feedback is emitted by every user-visible LLM-call surface (2026-06-01)
   - DD-33 Provider and embedding-config identifiers are internal auto-generated UUID4 strings; the user-entered unique field is `name` (2026-06-03)
   - DD-34 Adaptive timeout is per-role; judge calls get an independent ladder; embedding is a fixed budget; Test Inference and readiness are exempt (2026-06-03)
   - DD-35 Numeric performance budgets are retired; responsiveness is owned by the concurrency model and stall handling by the Adaptive Timeout Service (2026-06-03)
   - DD-36 Nightly builds retired; auto-update feature retired entirely (2026-06-03)
   - DD-37 Closing the last two open questions: per-task status enum names (D-016 + D-047) and anyio adoption (D-027 confirmed stdlib-only) (2026-06-03)
   - DD-38 The benchmark pipeline runs on a single dedicated dispatcher thread (2026-06-06)
   - DD-39 Two-level cancellation: Pause finishes the in-flight call; Stop and Shutdown abort it promptly (2026-06-06)
   - DD-40 Two serial domains; the dispatcher orchestrates all fan-out batches; pool size pinned (2026-06-06)
   - DD-41 The single DB writer is one write connection plus one lock; writes are synchronous on the calling thread (2026-06-06)
   - DD-42 Halt outcomes derive from one atomic token snapshot; the cancel reason is a closed enum (2026-06-06)
   - DD-43 The async residue purge: the module inventory matches D-R-01, and the async-native libraries are removed (2026-06-06)
   - DD-44 The error model is ratified: exceptions with controlled handling; the pipeline's "never raises" gets its containment mechanism (2026-06-06)
   - DD-45 Cosine grading simplified: one whole-text score, one user-configured threshold; ResponseScope removed (2026-06-06)
   - DD-46 One universal judge prompt steered by category/sub-category; task_type removed; cosine becomes a task-level opt-out; judge context overflow is detected and reported (2026-06-06)
   - DD-47 Advanced Options expose every per-run-overridable setting; overrides travel as registry-keyed entries, changed keys only (2026-06-06)
   - DD-48 No automatic billable calls, including embeddings: handshake-only readiness, one user-initiated embedding test, and a run-start fail-fast embed probe (2026-06-06)
   - DD-49 backend/import_export/ is inventoried; composition-root edge cases cite compose.py (2026-06-06)
   - DD-50 The single-inference gate is lease-owned: try_acquire returns a GateLease; release requires it (2026-06-06)
   - DD-51 chat_stream is the single chat execution surface; chat is sugar; the non-streaming fallback hides behind the same iterator (2026-06-06)
   - DD-52 The accessibility floor is an honestly-stated reduced target; the toolkit's free keyboard traversal is never suppressed (2026-06-06)
   - DD-53 Additive structural schema steps within a major version; no data migration or conversion, ever (2026-06-06)
   - DD-54 CSV exports are verbatim: no formula-injection mangling — trusted-content policy (2026-06-06)
   - DD-55 Import/export is same-user data portability; import validation is correctness-only (2026-06-06)
   - DD-56 Provider wire stub: transport-level adapter testing with pytest-httpserver (2026-06-06)
   - DD-57 Run Drift Detector checks environment availability of the frozen config only; embedding pair frozen per run (2026-06-06)
   - DD-58 Run-mode renaming: Synthetic / Task / Graded Benchmark (2026-06-06)
   - DD-59 User-facing rename: Judge Analysis -> Run Analysis (2026-06-06)
   - DD-60 Throughput never silently empty: request usage + flagged char/4 estimate fallback (2026-06-06)
   - DD-61 Inference temperature defaults to 0.0 for comparable runs (2026-06-06)
   - DD-62 Force-judge defaults OFF; sanity-failed responses never reach the judge (2026-06-06)
   - DD-63 Per-model cosine-coverage flag for uneven embedding coverage (2026-06-06)
   - DD-64 Warmup uses the normal adaptive budget; any response = provider liveness (2026-06-06)
   - DD-65 Run-analysis gets its own RUN_ANALYSIS adaptive bucket (2026-06-06)
   - DD-66 Stage-preserving retry — a judge-only failure re-runs only the judge (2026-06-06)
   - DD-67 Configurable max-output-tokens, default 4096; judge cap raised from 512 (2026-06-06)
   - DD-68 golden_answer is optional, not required (2026-06-06)
   - DD-69 macOS ships arm64 only; Intel dropped (2026-06-06)
   - DD-70 Embedding consecutive-failure short-circuit (2026-06-06)
   - DD-71 Circuit-breaker PROBING uses a lightweight liveness probe (2026-06-06)
3. Decision index by spec area

---

## 1. How to use this log

Read this log when reviewing the specification to understand the intent behind a behaviour, or before proposing a change that might contradict a settled decision. Each entry has a stable identifier (`DD-NN`). Spec documents cite these identifiers when they implement a decision. If a future change reverses a decision, the entry is updated in place and its `Last Updated` date and rationale revised — entries are not deleted.

**Two decision-identifier series (traceability).** This in-tree log uses the `DD-NN` series (the design decisions recorded above). Spec documents also cite a separate `D-NNN` series (for example `D-005`, `D-023`, `D-047`) and the post-review `D-R-NN` series (for example `D-R-01`, `D-R-16`): those refer to the **external project decision log** maintained alongside the project, not to entries in this file. The two series are distinct and non-overlapping — `DD-NN` is in-tree (this document), `D-NNN` / `D-R-NN` is the external project decision log. This note exists so a `D-NNN` citation in the spec is traceable to its source; this file does not reproduce the external decisions' contents.

Decisions about the LLM-as-judge contract in detail live in `08_Cross_Cutting/08-P_judge_protocol.md`; this log records only the cross-cutting product decisions about the judge (DD-02, DD-18, DD-27).

---

## 2. Decision entries

### DD-01 — Composite (provider, model) identity

**Topic:** How a benchmark target is identified and how result rows are aggregated.

**Decision:** A benchmark target is always identified by the composite pair `(provider_id, model_name)`, never by model name alone. When two providers expose a model with the same name, they are two distinct targets and produce two distinct rows in every Summary table, Details table, and chart aggregation. Rows for the same model name on different providers are never merged.

**Rationale:** The same model name served by different providers can differ in quantisation, configuration, and performance. Merging would average away exactly the differences a benchmark exists to measure. A composite key keeps every comparison honest and unambiguous.

**Affected spec areas:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`ModelDescriptor`), `05_Result_Widget/tabs/summary_tab.md`, `05_Result_Widget/tabs/details_tab.md`, chart aggregators in `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`.

---

### DD-02 — Per-task judge stage and run-level analysis are independent

**Topic:** The relationship between per-task judge validation and the run-level narrative analysis.

**Decision:** The application has two separate judge-driven features. (a) **Per-task judge validation** is a toggleable evaluation stage, controlled in Settings → Evaluation alongside the keyword and cosine stages, available only in `FULL_GRADING`. When enabled, the judge evaluates every task that reached the judge phase and returns a binary verdict plus reasoning. (b) The **run-level judge analysis** is a single narrative the judge model writes after the run, comparing the models in the run. It is **optional in every mode** (see DD-30, 2026-06-02), governed by `feature.judge_run_analysis_enabled` — default ON in `FULL_GRADING` and OFF in `SYSTEM_PERFORMANCE` and `SPEED`, with the user able to override either default at run start. The "Generate judge analysis" toggle is **visible in every mode** and governs only the run-level analysis; it does not control the per-task judge stage.

**Rationale:** The two features answer different questions — per-task validation produces verdicts; the run-level analysis produces a comparative narrative. Conflating them under one control removed the user's ability to run a graded benchmark with only keyword and cosine assessment. A configured judge model is required whenever (a) the per-task judge phase is enabled (only possible in `FULL_GRADING`) OR (b) the run-analysis toggle is ON (any mode); when neither condition holds, no judge model is required.

**Affected spec areas:** `08_Cross_Cutting/08-P_judge_protocol.md`, `08_Cross_Cutting/08-G_feature_flags.md` (`eval.phase_judge_enabled`), `02_New_Benchmark_Widget/description.md`, `05_Result_Widget/tabs/judge_analysis_tab.md`, `06_Settings_Dialog/description.md`.

---

### DD-03 — Settings unreachable while a run is non-terminal

**Topic:** Access to the Settings dialog during a benchmark.

**Decision:** The Settings dialog is unreachable whenever any run is in a non-terminal state, including `PAUSED`. The Settings menu item is disabled and carries a tooltip reading "Disabled — a benchmark is in progress (or paused)". If the dialog is somehow already open when a run starts, it becomes read-only immediately and offers no Save.

**Rationale:** A run executes against a frozen snapshot of settings captured at run creation. Allowing settings edits mid-run — including during a pause — would let the user believe a change affects the active run when it cannot, breaking the mental model and risking inconsistent expectations. Blocking the dialog keeps the snapshot contract clear.

**Affected spec areas:** `01_Main_Window/description.md`, `01_Main_Window/state_machine.md`, `06_Settings_Dialog/description.md`.

---

### DD-04 — Run management is read-only while a run is non-terminal

**Topic:** What the user may do to runs while a benchmark is executing.

**Decision:** While any run is in a non-terminal state, all past runs remain browsable and inspectable, but no destructive or generative action may be taken on any run, current or past. Renaming the currently active run is the single permitted exception. Disabled while a run is non-terminal: renaming a past run, deleting any run, resuming a past run, retrying tasks, cloning a run for retry, every export (CSV, Markdown, PNG), and regenerating the judge analysis. Every disabled action shows the tooltip "Disabled — a benchmark is in progress". The restriction applies in both the Result widget and the Resume Benchmark widget.

**Rationale:** Generative and destructive actions during an active run compete for the same provider connections, database writes, and judge model, and risk corrupting either the active run or the run being acted upon. Keeping inspection available while blocking mutation lets the user compare runs without endangering anything. Renaming the active run is safe because it touches only a display label.

**Affected spec areas:** `05_Result_Widget/description.md`, `05_Result_Widget/state_machine.md`, `03_Resume_Benchmark_Widget/description.md`, `04_Progress_Widget/description.md`.

---

### DD-05 — Status-bar health indicator auto-tests providers

**Topic:** Behaviour of clicking the status-bar health indicator.

**Decision:** Clicking the status-bar health dot opens Settings → Providers and immediately fires a connection test on every enabled provider.

**Rationale:** A user clicks the health dot precisely when something looks wrong. Opening the providers page and running the tests in one action puts the diagnostic result in front of the user without a second step. The extra network cost of the tests is small and is exactly what the user wants at that moment.

**Affected spec areas:** `01_Main_Window/description.md`, `06_Settings_Dialog/description.md`, `11_Services_and_Algorithms/09_READINESS_PROBE.md`.

---

### DD-06 — Retry selection pre-selects only failed rows

**Topic:** Default selection in the Retry Selection dialog.

**Decision:** When the Retry Selection dialog opens, only the failed rows are pre-selected. Completed rows are left unchecked but remain selectable, so the user can deliberately add them. No confirmation dialog is shown when completed rows are included.

**Rationale:** The common intent of a retry is to re-run what failed; pre-selecting failed rows matches that intent and makes the safe path the default. Re-running a completed task overwrites its result, but the safe default plus the explicit, deliberate act of checking a completed row is sufficient protection — a confirmation dialog would add friction without adding safety.

**Affected spec areas:** `07_Common_Dialogs/retry_selection_dialog.md`.

---

### DD-07 — Per-row Reset reverts to the last saved value

**Topic:** Behaviour of the per-row Reset control in the provider table.

**Decision:** The per-row Reset control on a provider row discards any unsaved edits made to that provider since the dialog was opened or since the last successful Save, restoring the value currently persisted in the data store. It behaves identically for every provider, regardless of how the provider was added. The dialog-level "Reset to Defaults" control is the only mechanism that restores factory defaults.

**Rationale:** A per-row revert-to-saved is a predictable, low-risk action a user reaches for after a mis-edit. Defining it uniformly for all providers avoids special-casing and keeps the control's meaning consistent. Wiping to factory defaults is a heavier action and stays as a single, clearly separate dialog-level control.

**Affected spec areas:** `06_Settings_Dialog/sub_dialogs/provider_edit.md`, `06_Settings_Dialog/sub_dialogs/reset_confirmation.md`, `06_Settings_Dialog/description.md`.

---

### DD-08 — Judge analysis text is never truncated

**Topic:** Display and export of the run-level judge analysis.

**Decision:** The run-level judge analysis is rendered in full in the Judge Analysis tab and written in full to the exported Markdown. There is no character cap. When the text exceeds the visible area, the panel scrolls.

**Rationale:** The analysis is the substantive comparative output of a graded run. A character cap would silently discard content the user explicitly asked the model to produce. Scrolling handles long text without data loss.

**Affected spec areas:** `05_Result_Widget/tabs/judge_analysis_tab.md`, `10_Domain_and_Data/05_EXPORT_FORMATS.md`.

---

### DD-09 — Drag-and-drop is restricted to dedicated drop zones

**Topic:** Where the application accepts dragged-in YAML task files.

**Decision:** Dragged-in YAML files are accepted only by dedicated drop zones, not by the main window as a whole. The drop zones are the New Benchmark widget's Task Files panel and the entire Task Editor workspace. The main window does not accept window-level drops in the Benchmark workspace.

**Rationale:** A window-level drop target is ambiguous — the destination of a dropped file would depend on which workspace happens to be active. Dedicated drop zones make the destination explicit and predictable. The Task Editor workspace accepts drops over its whole surface because the editor is a single-purpose surface for task files, so there is no ambiguity there.

**Affected spec areas:** `01_Main_Window/description.md`, `02_New_Benchmark_Widget/description.md`, `09_Task_Editor/description.md`.

---

### DD-10 — Env-var conversion is offered after Import

**Topic:** Handling of plain secrets in imported provider configuration.

**Decision:** After an import preview is confirmed, if the imported configuration contains any plain (non-environment-variable) API secrets, the environment-variable conversion dialog opens automatically before the import is committed to the database. This is the same flow used when saving provider changes.

**Rationale:** Imported configuration is a common path for plain secrets to enter the application. Offering conversion at import time, exactly as at save time, gives the secret-handling model a single consistent behaviour and one fewer way for a plain secret to be stored unintentionally.

**Affected spec areas:** `06_Settings_Dialog/description.md`, `06_Settings_Dialog/sub_dialogs/env_var_conversion.md` (removed under D-R-18), `10_Domain_and_Data/06_IMPORT_FORMATS.md`.

**Superseded by D-R-18 (2026-06-05):** credentials are now stored as a bare environment-variable NAME (e.g. `OPENAI_API_KEY`), not a `${ENV_VAR}` reference; the env-var conversion dialog is removed; a literal value is rejected at entry and is a hard error on import. (Intent of D-R-09 preserved: no secret value ever at rest.)

---

### DD-11 — Two independent log streams

**Topic:** How the application logs benchmark activity and diagnostics.

**Decision:** The application maintains two separate log streams. The **Run Log** is per-run and user-facing: one file per run at `<app_data>/logs/run/run_<run_id>_<unix_ts>.log`, always recording the full verbose stream with no level filtering, displayed live in the Progress widget at a user-selectable field density (Short / Normal / Verbose), with a buffer cap (`ui.run_log_max_lines`, default 100000) and a write toggle (`logging.write_run_log_to_file`, default true). For the prompt/response text fields (system prompt, user prompt / task, model response) the three on-screen levels mean: **Verbose** shows the FULL untruncated text plus character/token sizes; **Normal** shows a truncated text excerpt plus character/token sizes; **Short** shows character/token sizes only with no text. All other fields (timestamp, event-kind tag, provider, model, task id, stage, timings, retries, errors, judge verdict) keep their per-level visibility per `04_Progress_Widget/description.md` §8.2. The on-disk file behaviour is unchanged by the on-screen level — it always records the full Verbose field set, including the full untruncated prompt and response text. The **App Log** is per-app-lifetime and diagnostic: a single rotating file at `<app_data>/logs/app/app.log` plus numbered backups, level-filtered by `logging.app_log_level` (default INFO), rotating at `logging.app_log_max_file_mb` (default 10 MB, range 1–50) per file under a total disk ceiling of `logging.app_log_max_total_mb` (default 60 MB, hard max 200) with the backup count derived as `floor(total ÷ file size)`, and not shown in the UI. Settings → General carries two distinct sections, "Logging — Run Logs" and "Logging — App Logs".

**Rationale:** A per-run log and an app-lifetime diagnostic log serve different readers and have different retention needs. The user inspects the run log to follow a specific benchmark; a maintainer reads the app log to diagnose the application itself. One combined stream would force a single verbosity and retention policy onto both purposes.

**Affected spec areas:** `04_Progress_Widget/description.md`, `06_Settings_Dialog/description.md`, `08_Cross_Cutting/08-C_settings_hierarchy.md`, `10_Domain_and_Data/07_FILE_LAYOUT.md`, `12_Quality_and_NFRs/03_OBSERVABILITY.md`.

---

### DD-12 — Three single-purpose folder buttons

**Topic:** The Settings buttons that open application folders.

**Decision:** Settings provides three folder buttons, each opening exactly one folder and nothing else: "Open App folder" (Settings → Storage) opens `<app_data>/`; "Open Run Logs folder" (Settings → Logging — Run Logs) opens `<app_data>/logs/run/`; "Open App Logs folder" (Settings → Logging — App Logs) opens `<app_data>/logs/app/`. No button opens a parent folder that contains the others. The About dialog's filesystem section exposes the same three locations.

**Rationale:** A button that opens a parent folder forces the user to navigate further to reach the folder the button's label implied. Single-purpose buttons land the user exactly where the label promises.

**Affected spec areas:** `06_Settings_Dialog/description.md`, `07_Common_Dialogs/about_dialog.md`, `10_Domain_and_Data/07_FILE_LAYOUT.md`.

---

### DD-13 — Per-secret authentication source toggle

**Topic:** How provider credentials are entered and stored.

**Decision:** The Provider Edit dialog renders each credential field as its own secret card carrying a Plain ↔ Env var segmented control. Single-secret providers (OpenAI-compatible, Anthropic, Gemini, and local OpenAI-compatible endpoints) show one card. Azure-hosted providers show four cards — API key, Azure endpoint, deployment name, API version — each with its own source toggle. The environment-variable conversion dialog operates per secret, one row per Plain-mode card needing a decision. Each card maps to a column in the providers record; the stored value is either a literal string or an `${ENV_VAR}` reference, and resolution is centralised in one environment-resolver service.

**Rationale:** Different credential fields have different sensitivities and a user may want to source some from the environment and keep others literal. A per-field toggle gives that control. Centralising `${ENV_VAR}` resolution in one service keeps the resolution rule single-sourced and testable.

**Affected spec areas:** `06_Settings_Dialog/sub_dialogs/provider_edit.md`, `06_Settings_Dialog/sub_dialogs/env_var_conversion.md` (removed under D-R-18), `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`ProviderConfig`), `10_Domain_and_Data/08_REDACTION_PATTERNS.md`.

---

### DD-14 — Result tables expose the full field set with persistent filters

**Topic:** Columns, filters, and column control on the Result widget tables.

**Decision:** The Details table addresses every field available on a result — 19 columns: Provider · Model, Task, Category, Sub-category, Difficulty, Status, Time, TTFT, Tokens, TPS, Layer, Keywords, Cosine, Score, Verdict, Reason, Error, Started at, Finished at — with 10 visible by default and the rest reachable through a column-toggle popover. The Summary table similarly exposes its full column set. Both tables carry a filter bar of chip controls (Models, Tasks, Status, Verdict, Layer, Difficulty, Category) and a per-column right-click filter, plus a "Clear filters" control. A "Columns" control opens a popover toggling each column. Column visibility, column order, and active filters persist per run.

**Rationale:** A benchmark produces many measurements per task; a fixed five-column table hides most of them. Exposing the full field set with column control lets each user shape the table to the question at hand. Persisting the layout per run means reopening a run restores the view the user last built for it.

**Affected spec areas:** `05_Result_Widget/tabs/details_tab.md`, `05_Result_Widget/tabs/summary_tab.md`, `08_Cross_Cutting/08-G_feature_flags.md`.

---

### DD-15 — Chart gallery with universal per-chart filters

**Topic:** The chart catalogue and chart filtering.

**Decision:** The Result widget renders twelve chart kinds. Each chart kind has its own documented analytical purpose, data sources, mode availability, and empty state, and is illustrated in a visual gallery. Every chart carries five global filter chips — Models, Status, Verdict, Category, Difficulty — that re-aggregate the chart on the fly, followed by chart-specific filters where relevant (axis scale toggle, outlier exclusion, metric switch, legend toggles, and so on). Clicking a data element tooltips its value; modifier-clicking a data element filters the Details tab to the matching subset and switches focus there.

**Rationale:** Twelve chart kinds answer twelve different questions, and a chart is most useful when its data can be sliced without leaving the chart. A consistent global filter set plus chart-specific controls makes every chart explorable in the same way. Drill-down to the Details tab connects a visual observation to the underlying rows.

**Affected spec areas:** `05_Result_Widget/tabs/charts_tab.md`, `05_Result_Widget/charts_gallery.html`, `08_Cross_Cutting/08-G_feature_flags.md`, `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`ChartKind`).

---

### DD-16 — No duration estimates

**Topic:** Whether the application predicts how long a run will take.

**Decision:** The application shows no estimated-duration figure anywhere. The Run Summary dialog, the Resume Summary dialog, and the per-mode documents report only the work to be done — the count of inference calls and judge calls — and state explicitly that duration is not estimated. Once a run is underway the user sees actual elapsed time on the Progress widget.

**Rationale:** A duration estimate would require prior measurements of the specific models on the specific machine, which the application does not have before the run. Any predicted figure would be unreliable and would mislead. Reporting the concrete work count is accurate; reporting elapsed time once the run starts is accurate.

**Affected spec areas:** `07_Common_Dialogs/run_summary_dialog.md`, `07_Common_Dialogs/resume_summary_dialog.md`, `02_New_Benchmark_Widget/mode_specifics/`, `04_Progress_Widget/description.md`.

---

### DD-17 — Transport streaming is always on; the toggle is UI-only

**Topic:** What the streaming setting controls.

**Decision:** Backend transport streaming is always on; it is how the pipeline measures Time To First Token. The streaming setting (`feature.streaming_enabled`) and the New Benchmark "Stream tokens to Log" toggle control only whether the Progress widget's Log panel echoes tokens as they arrive or shows the full response at inference completion. The toggle never changes pipeline behaviour.

**Rationale:** Time To First Token can only be measured from a streamed transport, so streaming must always be on for the measurement to exist. The only legitimate user choice is a cosmetic one — whether the Log panel updates token-by-token. Tying the setting to that cosmetic choice keeps the measurement reliable while still offering the UI preference.

**Affected spec areas:** `08_Cross_Cutting/08-G_feature_flags.md` (`feature.streaming_enabled`), `08_Cross_Cutting/08-E_interfaces_contracts.md`, `02_New_Benchmark_Widget/description.md`, `06_Settings_Dialog/description.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`ChatRequest.echo_tokens_to_log`).

---

### DD-18 — The judge receives no model identity

**Topic:** What information the judge model is given.

**Decision:** The judge model receives only the task context and the response text to evaluate. It receives no provider identity and no test-model name. Consequently, name similarity between the judge model and a model under test cannot bias the verdict, and the application surfaces no warning about such similarity.

**Rationale:** The judge's input is constructed from task fields and the response only; identity fields are simply never included. Because identity cannot reach the judge, a bias from name-matching is impossible by construction, and a warning about it would be incorrect.

**Affected spec areas:** `08_Cross_Cutting/08-P_judge_protocol.md`, `02_New_Benchmark_Widget/description.md`, `07_Common_Dialogs/run_summary_dialog.md`.

---

### DD-19 — Mode-aware run summary dialog

**Topic:** The content of the pre-start Run Summary dialog.

**Decision:** The pre-start Run Summary dialog adapts to the selected run mode and surfaces the full per-run snapshot — every setting, flag, limit, retry value, and feature toggle frozen into the run. Mode-irrelevant sections are hidden: the synthetic prompt matrix appears only for `SYSTEM_PERFORMANCE`; the task-file list appears only for the task-driven modes; the embedding section appears only for `FULL_GRADING`. Each displayed value is annotated with the setting key it resolves from. When the dialog opens, the pre-flight checks (provider reachability, and embedding reachability for `FULL_GRADING`) are re-run; if state changed since the Start click, the dialog refuses to open and shows a toast.

**Rationale:** The Run Summary dialog is the user's last checkpoint before committing a run. Showing only mode-relevant sections keeps it readable; showing the full snapshot with setting-key annotations makes every frozen value traceable; re-checking on open prevents starting a run against state that has since gone stale.

**Affected spec areas:** `07_Common_Dialogs/run_summary_dialog.md`, `02_New_Benchmark_Widget/mode_specifics/`, `08_Cross_Cutting/08-G_feature_flags.md`.

---

### DD-20 — In-window menu bar on every platform

**Topic:** Where the application menu bar is rendered.

**Decision:** The application renders its menu bar inside the application window on every platform, including platforms whose convention is a global menu bar. The menu bar is minimal — a workspace switcher plus access to Settings and About — rather than a classic File / Edit / View / Help structure.

**Rationale:** An in-window menu bar makes the application look and behave identically on every operating system, so documentation, screenshots, and tutorials apply everywhere without per-platform variants. The application's surface area does not warrant a classic multi-menu bar; a minimal bar covers what is needed.

**Affected spec areas:** `01_Main_Window/description.md`, `01_Main_Window/mockup.html`, `08_Cross_Cutting/08-L_ui_standardization.md`.

---

### DD-21 — Dialog button ordering

**Topic:** The order of buttons in dialog footers.

**Decision:** In every dialog footer the rightmost button is the primary, default action. Lower-priority actions sit to its left. The escape/back-out action (Cancel, Discard, Close) sits immediately left of the primary confirm. For dialogs with side actions (Reset, Import, Export), the footer splits into a left cluster of side actions and a right cluster ordered back-out then primary.

**Rationale:** A single fixed ordering rule across all dialogs lets the user act without re-reading the footer each time. Placing the primary action rightmost and the back-out action next to it gives a predictable target for both confirmation and cancellation.

**Affected spec areas:** `08_Cross_Cutting/08-L_ui_standardization.md`, `06_Settings_Dialog/description.md`, `07_Common_Dialogs/`.

---

### DD-22 — Full dark and light theme token sets

**Topic:** Theming and colour tokens.

**Decision:** Both a dark theme and a light theme are defined in full as typed token sets, with a WCAG AA contrast matrix covering both. When the theme preference is set to follow the system, the application listens for operating-system colour-scheme changes and switches accordingly. Widgets are built programmatically with Qt Widgets; styling is generated and applied from the typed design tokens by a single theme module, and direct stylesheet calls are forbidden outside that module.

**Rationale:** Defining both themes completely, with a contrast matrix, makes accessibility a verifiable property rather than an aspiration. Generating all styling from one token set through one module keeps the visual language consistent and gives a single place to change it.

**Affected spec areas:** `08_Cross_Cutting/08-D_color_palette_and_typography.md`, `08_Cross_Cutting/08-L_ui_standardization.md`, `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md`, `16_Engineering_Standards/` (UI styling standard).

---

### DD-23 — Platform detection at startup

**Topic:** How the application adapts to the host operating system.

**Decision:** A platform detector runs once at launch and produces a platform profile capturing the operating-system kind, application-data paths, modifier-key conventions, file-manager labels, and the dark-mode detection mechanism. The profile is cached in the application context and consulted by every service that needs operating-system-specific behaviour.

**Rationale:** Operating-system differences are determined once at startup, so detecting them once and caching the result avoids scattering platform checks through the codebase and avoids repeated detection cost. Every consumer reads from one authoritative profile.

**Affected spec areas:** `08_Cross_Cutting/08-M_app_lifecycle.md`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md`.

---

### DD-24 — Task Editor is a full-window workspace

**Topic:** The user interface for creating and editing benchmark task YAML files.

**Decision:** Task file editing is a full-window workspace, not a modal dialog and not a separate window. A workspace switcher in the menu bar toggles between the Benchmark workspace and the Task Editor workspace; the active workspace persists across sessions. The Task Editor is a three-pane surface (Files, Tasks, Field editor) with a read-only YAML preview side panel, a toolbar (Open File, Open Folder, New File, Save, Save All, Reload, View YAML, validation pill), and a validator that distinguishes hard errors (block Save) from soft warnings (Save permitted). A clickable "Running" pill in the menu bar swaps back to the Benchmark workspace and focuses the Progress widget; benchmarks continue regardless of the active workspace.

**Rationale:** The editing form needs three panes plus a preview — too much for a modal dialog and more management overhead than a separate window justifies. A full-window workspace gives the space while keeping everything inside one window. Workspace switching is a familiar pattern for related-but-distinct workflows, and the Running pill ensures editing never hides an in-progress benchmark.

**Affected spec areas:** `09_Task_Editor/`, `01_Main_Window/description.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `08_Cross_Cutting/08-C_settings_hierarchy.md`.

---

### DD-25 — Run-management actions are owned by the Resume widget

**Topic:** Which surface owns rename, delete, retry, clone, and export of runs.

**Decision:** The Resume Benchmark widget is the sole location for renaming, deleting, retrying selected tasks, cloning a run for retry, and per-run exports; these are reached through its right-click context menu. The Result widget header is view-only — it has no rename and no delete controls. The Progress widget header shows a rename control only while the run is actively executing and hides it in terminal states. The Resume widget footer carries only Refresh and Resume Run.

**Rationale:** Concentrating run-management actions in one surface removes the ambiguity of the same action appearing in several places with subtly different scope. The Result widget is for viewing results and the Progress widget for monitoring an active run; keeping management out of them keeps each surface single-purpose.

**Affected spec areas:** `03_Resume_Benchmark_Widget/description.md`, `04_Progress_Widget/description.md`, `05_Result_Widget/description.md`, `01_Main_Window/description.md`.

---

### DD-26 — Uniform Result-widget export footer

**Topic:** The export controls on the Result widget tabs.

**Decision:** Every Result-widget tab uses the same footer layout: a left cluster of tab-appropriate export buttons (Summary and Details: Export CSV and Export MD; Charts: Export PNG; Judge Analysis: Export MD) and a right cluster carrying a shared "Save directly to app data folder" checkbox (`ui.export_save_directly`, default false) and a conditional "Open App Folder" button shown only when the checkbox is checked. Unchecked, an export click opens a save picker defaulted to the user's Desktop with an auto-generated filename. Checked, an export writes directly to `<app_data>/exports/` and the "Open App Folder" button opens that folder. In-tab toolbars carry only non-file actions.

**Rationale:** A single footer layout across all four tabs means the user learns the export controls once. The save-directly option serves repeated exports without a picker each time, while the default (picker to Desktop) keeps the first-time path obvious. Keeping file actions in the footer and non-file actions in the toolbar separates the two cleanly.

**Affected spec areas:** `05_Result_Widget/description.md`, `05_Result_Widget/tabs/`, `08_Cross_Cutting/08-G_feature_flags.md` (`ui.export_save_directly`), `10_Domain_and_Data/05_EXPORT_FORMATS.md`.

---

### DD-27 — Binary verdict; cosine is the only numeric score

**Topic:** The result verdict and the meaning of "score".

**Decision:** A graded result's final verdict is strictly binary — `PASS` or `FAIL`. There is no `UNKNOWN` verdict; a `None`/unset verdict marks only a result still being graded, and a terminal-failure result carries no verdict. The verdict is combined from the enabled evaluation phases by a cascade: with keyword only, the keyword phase decides; with keyword and cosine, a keyword failure short-circuits and otherwise the cosine threshold decides; with the judge enabled, the judge decides when the prior phases did not produce a definitive failure (or always, when force-judge is set). The cosine phase produces a numeric similarity in the range 0.0–1.0, stored as the **Cosine Score** — the only numeric quality value in the application. The judge produces no numeric value; result tables and charts present the Cosine Score and never a "judge score", and a task with no cosine measurement shows no score.

**Rationale:** A binary verdict gives an unambiguous pass/fail outcome that is simple to aggregate into pass rates. Permitting `UNKNOWN` as a final result would force every downstream consumer to handle a third state. A single numeric quality value, sourced from the one phase that genuinely measures a number, prevents the confusion of presenting a fabricated "judge score" alongside a real measurement.

**Affected spec areas:** `08_Cross_Cutting/08-P_judge_protocol.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`Verdict`, `ResolutionLayer`, `BenchmarkResult`), `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md`, `05_Result_Widget/tabs/`.

---

### DD-28 — Three run modes

**Topic:** The set of benchmark run modes.

**Decision:** The application has exactly three run modes: `SYSTEM_PERFORMANCE` (synthetic tasks from an input/output size matrix, measuring raw inference performance, no grading), `SPEED` (real tasks from user task files, measuring timing and throughput, no grading), and `FULL_GRADING` (real tasks through the full evaluation pipeline, the only mode that grades). There is no prompt-evaluation or prompt-variants mode.

**Clarification (2026-05-30):** The earlier draft phrasing "SPEED — grading off by default" was misleading: it implied the user could opt SPEED into the grading phases. They cannot. `SPEED` and `SYSTEM_PERFORMANCE` never grade — they are identical in every grading dimension, differing only in the prompt source (user task files vs synthetic size-matrix prompts). The three `eval.phase_*` toggles and `eval.force_judge_on_prior_failure` apply only in `FULL_GRADING`; they are ignored in `SPEED` and `SYSTEM_PERFORMANCE`. The judge model is needed only when the per-task judge phase is enabled (only possible in `FULL_GRADING`) or when the "Generate judge analysis" toggle (`feature.judge_run_analysis_enabled`) is on (any mode); that toggle is visible in every mode with the per-mode defaults set by DD-30 (default ON in `FULL_GRADING`, OFF in `SYSTEM_PERFORMANCE` and `SPEED`; user-overridable). The canonical phrasing is "Speed never grades", not "no grading by default" or "grading is off in Speed by default".

**Rationale:** Three modes cover the distinct goals a benchmark serves — raw machine performance, throughput on real tasks, and graded quality on real tasks. A fixed, small mode set keeps the mode-visibility policy and the run-summary dialog tractable.

**Affected spec areas:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`RunMode`), `08_Cross_Cutting/08-H_app_modes.md`, `08_Cross_Cutting/08-G_feature_flags.md`, `08_Cross_Cutting/08-B_benchmark_state_machine.md`, `02_New_Benchmark_Widget/`, `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md`, `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`, `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`, `05_Result_Widget/tabs/`.

---

### DD-29 — No schema migration framework *(refined by DD-53: "mismatch is hard error" now applies only to newer-than-app or cross-major versions; older same-major databases are brought forward by additive structural steps)*

**Topic:** How the persistence schema evolves across versions.

**Decision:** The application includes no schema migration framework. The database carries a schema-version marker. A schema-version mismatch at startup is a clear, hard error. A new major version of the application uses a fresh database; within a major version, schema evolution is additive only.

**Rationale:** A migration framework is substantial machinery to build and test for an application whose data is a local benchmarking history rather than irreplaceable records. A hard version-mismatch error with a fresh database for major versions is simple and predictable, and additive-only evolution within a major version avoids needing migrations at all for the common case.

**Affected spec areas:** `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`, `08_Cross_Cutting/08-M_app_lifecycle.md`, `12_Quality_and_NFRs/04_ERROR_RECOVERY.md`.

---

### DD-31 — Redaction is scoped to three surfaces; "sole egress path" wording retired (2026-06-01)

**Topic:** The scope of the redaction module and the retirement of the purpose-specific egress wrappers `redact_for_display` and `redact_for_csv`.

**Decision:** Redaction is applied at exactly **three surfaces** — app log records (`app.*` namespace structlog processor `redact_for_log`), support-bundle generation (the bundle builder masks settings credential values and applies a final regex pass to bundled log files), and provider SDK error-message wrapping at the adapter boundary (`redact(text)` applied to the SDK exception's message string before it is placed on `AppError.message`). The active API surface is a single `redact(text)` function plus the `redact_for_log` structlog processor.

The previous functions `redact_for_display` and `redact_for_csv` are **retired**. Surfaces formerly served by them — the UI display, the run-log panel, the run-log file (`run.*` namespace), CSV/Markdown table exports, the run-analysis Markdown export, HTML rendering, the clipboard, the `InferenceTestResult.response_excerpt`, and the Generate-Analysis dialog's response excerpt preview — no longer apply redaction.

The previous specification rule that named the redaction module "the sole egress path for any text that could contain a secret" is retired with this entry. The active rule is the three-surface rule above.

**Rationale:** Ollama LLM Bench is a single-user desktop application. The user runs it on their own machine, types their own task prompts, and watches their own model produce its own responses. Redacting user-authored prompts and user-machine model responses on display, in exports, on the clipboard, or in the per-run log file is theatre: the user is the only person who sees them, and the only person who could ever leak them is the user themselves, deliberately. The threat-model surfaces that **do** matter are the ones where text can realistically leave the user's machine — the rotating system/debug log file (which is included in support bundles), the support-bundle archive itself, and the wrapped messages of SDK exceptions (whose raw form may echo back `Authorization: Bearer …` headers from a request body dumped at the third-party SDK's DEBUG/TRACE level). Concentrating the redaction module on those three surfaces produces a tighter, more reviewable security control than the previous "redact every text surface" rule.

> **Superseded in part by D-R-17 (2026-06-04).** Crash reporting and the support bundle are **removed** from the product. The support-bundle surface therefore no longer exists, so redaction now applies at **two** surfaces only: (1) app-log records (`app.*` structlog `redact_for_log`) and (2) provider SDK error-message wrapping at the adapter boundary (`redact(text)`). The bundle-builder masking described above is withdrawn. The two-surface rule is authoritative in `10_Domain_and_Data/08_REDACTION_PATTERNS.md` and `12_Quality_and_NFRs/02_SECURITY_MODEL.md`. (The single-user threat-model rationale is otherwise unchanged: the only credential-egress surface that remains is `app.log`, which the user may choose to share manually when reporting a bug.)

**Affected spec areas:** `10_Domain_and_Data/08_REDACTION_PATTERNS.md` (main rewrite — three-surface scope; simplified API; retired functions documented), `16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md` (adapter-boundary `redact(exc_message)` rule; "sole egress" wording removed), `16_Engineering_Standards/06_LOGGING_STANDARD.md` (structlog processor attached to `app.*` only, not `run.*`), `12_Quality_and_NFRs/02_SECURITY_MODEL.md` (three-surface restatement), `12_Quality_and_NFRs/09_PRIVACY_POLICY.md` (clarified scope), `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md` (redaction step removed from the algorithm), `11_Services_and_Algorithms/20_HTML_RENDERING.md` (redaction calls removed), `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md` (redaction removed from response/markdown handling), `11_Services_and_Algorithms/15_LOG_FORMATTING.md` (clarification that `run.*` is not redacted), `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` (adapter-boundary wrap is the canonicalisation point), `08_Cross_Cutting/08-E_interfaces_contracts.md` §22 (API surface simplified), `13_Distribution_and_Release/07_CRASH_REPORTING.md` (support-bundle redaction sweep), `07_Common_Dialogs/error_dialog.md` (dialog does not redact again), `05_Result_Widget/tabs/judge_analysis_tab.md` (narrative displayed verbatim), `08_Cross_Cutting/08-I_edge_cases.md` (EC-PROV-5ea added — SDK Authorization header wrap), `10_Domain_and_Data/05_EXPORT_FORMATS.md` (common-rules redaction row updated).

A reference to `redact_for_display` or `redact_for_csv` in any active spec section after this decision is a defect; the only acceptable mentions are in this decision-log entry and in `10_Domain_and_Data/08_REDACTION_PATTERNS.md` §7.3 (the retirement note).

---

### DD-30 — Run-level judge analysis is optional in every mode (2026-06-02)

**Topic:** The visibility and default of the "Generate judge analysis" toggle (`feature.judge_run_analysis_enabled`) across run modes.

**Decision:** The "Generate judge analysis" toggle is **visible in every run mode**. Its **default** differs by mode:

| Run mode | Toggle visibility | Default |
|---|---|---|
| `SYSTEM_PERFORMANCE` | VISIBLE | OFF |
| `SPEED` | VISIBLE | OFF |
| `FULL_GRADING` | VISIBLE | ON |

The user can override the per-mode default in either direction. The canonical phrasing across the specification is: *"Optional — controlled by the 'Generate judge analysis' toggle; default ON in FULL_GRADING, OFF in SYSTEM_PERFORMANCE and SPEED."* A judge model is required when EITHER (a) the per-task judge phase is enabled (FULL_GRADING only, `eval.phase_judge_enabled` ON) OR (b) the run-analysis toggle is ON (any mode); when neither condition holds, no judge model is required. A FULL_GRADING run started with the analysis toggle OFF finalizes with `BenchmarkRun.run_analysis = null`; the user can post-run generate via the existing Generate Analysis dialog (D-037).

**Decision retired:** The earlier specification rule that the run-level analysis was *"mandatory in FULL_GRADING / toggle hidden / forced ON"* is **retired** with this entry. DD-02 has been updated to match.

**Rationale:** A FULL_GRADING user who only cares about per-task verdicts should not be forced to pay for an additional narrative LLM call. The toggle remains discoverable in every mode for symmetry and predictability, and the per-mode default reflects the expected use — analysis is most useful when the user is grading, so default ON in FULL_GRADING; analysis is opt-in for timing-only modes, so default OFF in SYSTEM_PERFORMANCE and SPEED.

**Affected spec areas:** `08_Cross_Cutting/08-H_app_modes.md`, `08_Cross_Cutting/08-G_feature_flags.md`, `08_Cross_Cutting/08-B_benchmark_state_machine.md`, `08_Cross_Cutting/08-I_edge_cases.md` (EC-RUN-15, EC-RUN-16), `02_New_Benchmark_Widget/description.md` (and `state_machine.md`, `flow_diagram.md`, `mode_specifics/full_grading.md`), `05_Result_Widget/tabs/judge_analysis_tab.md`, `06_Settings_Dialog/description.md`, `07_Common_Dialogs/run_summary_dialog.md`, `07_Common_Dialogs/generate_analysis_dialog.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`BenchmarkRun.run_analysis`), `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`, `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`.

---

### DD-32 — Live inference-progress feedback is emitted by every user-visible LLM-call surface (2026-06-01)

**Topic:** The scope of the `_inference_progress` event introduced by D-043 (the live counters-only progress channel rendered as the Progress widget's Current-task row).

**Decision:** The `_inference_progress` event is emitted by **four** user-visible LLM-call surfaces — not only the per-task main inference. The four are:

| Surface | `InferenceContext` value | Rendered by |
|---|---|---|
| Benchmark Pipeline per-task main inference | `BENCHMARK_TASK` | Progress widget Current-task "Inference progress" sub-row |
| Benchmark Pipeline per-task judge call (FULL_GRADING only) | `BENCHMARK_JUDGE` | Progress widget Current-task "Judge progress" sub-row (NEW with this decision) |
| Run Analysis Service `generate()` | `RUN_ANALYSIS` | Generate Analysis dialog live progress line (replaces the static "Generating…" spinner) |
| `LLMClient.test_inference(...)` flow | `PROVIDER_TEST` | Provider Edit inference-test panel live indicator (replaces the Run-button area) |

A new `InferenceContext` enum (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.19a) discriminates the four; the `InferenceProgressEvent` payload gains one `context` field plus per-context nullability for `result_id` and `task_id` (those are required only for `BENCHMARK_TASK` and `BENCHMARK_JUDGE`; `run_id` is required for `BENCHMARK_TASK`, `BENCHMARK_JUDGE`, and `RUN_ANALYSIS`, and `None` for `PROVIDER_TEST`). The 1-Hz ticker established by D-043 in `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9 becomes a **shared backend helper** (`emit_progress_during(...)`) that all four callers invoke; the same coalescer rule and the same "immediate emit on first token" rule apply uniformly across contexts. Each subscriber filters by `context` (and by `run_id` / `provider_id` where appropriate) so the four streams do not bleed across surfaces.

**Readiness probes are explicitly excluded.** `LLMClient.probe_health()` and the Readiness Service do NOT emit `_inference_progress`; the `InferenceContext` enum deliberately omits any `READINESS_PROBE` member so a future probe path cannot leak progress events onto the bus. The readiness model is unchanged — readiness changes surface through the status-bar health dot and the Settings readiness section, never through a live indicator.

The benchmark pipeline's `BENCHMARK_RUN` activity gate (D-036) is unchanged — the per-task judge call inside a benchmark run still executes under the gate already held by the pipeline; no new gate acquisitions are introduced. The Run Analysis Service still acquires `JUDGE_ANALYSIS` for user-initiated calls (and skips its own acquire when invoked from the pipeline). The `LLMClient.test_inference` flow still acquires `PROVIDER_TEST`.

**Rationale:** D-043 introduced live progress for the per-task main inference and stopped there. The user has three other surfaces where an LLM call can take many seconds — the per-task judge call (a separate model call after the main inference completes), the run-analysis generation/regeneration (a single long call after the run ends), and the Provider Edit Test inference action (a manual probe against any selected model) — and on all three the user previously saw only a static spinner or no indicator at all. Reusing the same channel and the same emitter helper for all four surfaces gives the user a uniform "the app is alive" signal everywhere it matters, without introducing per-surface bespoke progress mechanisms.

**Affected spec areas:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`InferenceContext` enum, `InferenceProgressEvent` `context` field and per-context nullability), `08_Cross_Cutting/08-J_event_bus_catalog.md` (emitters and subscribers per context; readiness-probe exclusion), `08_Cross_Cutting/08-Q_event_payload_schemas.md` (payload schema), `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9 (shared `emit_progress_during` helper, invoked twice per task in `FULL_GRADING`), `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md` §6 (helper invocation with `context=RUN_ANALYSIS`), `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.8.2 (helper invocation with `context=PROVIDER_TEST`), `11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.2 (explicit non-emission note), `04_Progress_Widget/description.md` §7.1 (two sub-rows; per-context rendering rules), `04_Progress_Widget/state_machine.md` §3 (Judge progress sibling sub-state), `04_Progress_Widget/implementation_structure.md` §4.2 (CurrentTaskController context filter), `04_Progress_Widget/mockup.html` (Judge progress sub-row example), `07_Common_Dialogs/generate_analysis_dialog.md` §8 (live progress line replacing the spinner), `06_Settings_Dialog/sub_dialogs/provider_edit.md` §8.2 (live indicator replacing the Run-button area), `06_Settings_Dialog/flow_diagram.md` (Test inference sequence), `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md` (cadence applies regardless of context), `08_Cross_Cutting/08-I_edge_cases.md` (EC-RUN-20 judge fast-return, EC-RUN-21 RUN_ANALYSIS cancel, EC-RUN-22 PROVIDER_TEST timeout, EC-RUN-23 out-of-order BENCHMARK_JUDGE). **Precedent:** D-043 introduced the channel and the ticker; this decision extends both to four contexts and codifies the shared helper.

---

### DD-33 — Provider and embedding-config identifiers are internal auto-generated UUID4 strings; the user-entered unique field is `name` (2026-06-03)

**Topic:** How a `ProviderConfig` (and the analogous `EmbeddingConfig`) is identified by the data layer versus how it is named by the user, and how historical run records preserve a provider's name across a later rename.

**Decision:**

1. **`provider_id` is INTERNAL and AUTO-GENERATED.** The `ProviderId` type alias keeps its declaration as a string (`NewType("ProviderId", str)`); the value form is a **UUID4 textual representation** (e.g. `"a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"`). The `ProvidersStore` generates the id on insert. The id is never displayed in the UI, never entered by the user, never present in import/export YAML, and never copied to the clipboard. It is the stable primary key in the `providers` table and the foreign-key value in `benchmark_runs`, `benchmark_results`, `model_capabilities`, and the run-snapshot tables.
2. **`name` is the user-entered unique display label.** Every `ProviderConfig` carries a non-empty `name` (replacing the prior `label` field); the `providers` table enforces `UNIQUE (name)` and the `ProvidersStore.add` / `update` paths pre-check uniqueness with `ProvidersStore.get_by_name(name)` so a collision reports a service-level validation error before the DB constraint fires. The Settings Provider table column is **Name** (sortable, primary); the `provider_id` is never shown. The reusable provider dropdown (D-037) displays the name; its `currentData()` carries the internal `provider_id`.
3. **Historical-fidelity name snapshot on every run record.** `BenchmarkRun` gains `judge_provider_name: str` (snapshot of the judge provider's display name at run start, alongside the existing `judge_provider_id`). `BenchmarkResult` gains `provider_name: str` (snapshot of the per-task provider's display name at task start, alongside the existing `provider_id`). The pipeline stamps both fields during the existing run-snapshot capture. Historical UI surfaces (Resume widget, Result widget Summary/Details/Charts/Judge Analysis tabs, exports, the per-run log file) render the SNAPSHOT name — they never re-look up the current name through `ProvidersStore`. Live UI surfaces (Settings provider table, in-flight Progress widget) render the CURRENT name via the registry. Renaming a provider after a run completes therefore changes the Settings table immediately but leaves every historical run row showing the original name.
4. **Insert shape.** `ProvidersStore.add(draft: ProviderConfigDraft) -> ProviderId` accepts a `ProviderConfigDraft` (the same field set as `ProviderConfig` minus `provider_id`) and returns the generated UUID4. `ProvidersStore.update(provider_id, config)` updates mutable fields including `name` (after the uniqueness pre-check). `ProvidersStore.get_by_name(name) -> ProviderConfig | None` is the duplicate-name lookup helper for the dialog's live validation and the importer's per-row check.
5. **Embedding configurations follow the same pattern.** `EmbeddingConfig` is no longer a single-row table: it gains `embedding_config_id: EmbeddingConfigId` (internal auto-generated UUID4 string) and `name: str` (user-entered unique display label). The `embedding_configs` table (renamed from the prior single-row `embedding_config`) enforces `UNIQUE (name)`. `EmbeddingConfigStore.add(draft) -> EmbeddingConfigId`, `EmbeddingConfigStore.get_by_name(name) -> EmbeddingConfig | None`, and a `selected_embedding_config_id` setting (or analogous mechanism) records which embedding configuration the application currently uses for run snapshots. The pipeline stamps the chosen embedding configuration's name into the run snapshot the same way it stamps the judge provider name. **Superseded by D-R-13:** the embedding catalog described in this item was later removed. The embedding feature is now a single `(provider, embedding model)` selection stored as two `app_settings` keys (`embedding.selected_provider_name` / `embedding.selected_model_name`) owned by `AppSettingsStore` — there is no `EmbeddingConfig` record, no `embedding_config_id`, no name, no `embedding_configs` table, and no `EmbeddingConfigStore`. The run snapshot now stamps `embedding_provider_name` and `embedding_model_name` instead of `embedding_config_id` / `embedding_config_name`.
6. **Settings dialog implications.** The Provider Edit sub-dialog removes the Provider ID input field entirely; the Name field is the sole identifier control and its inline validation rejects an empty value and any value already used by another provider. For a new provider, Save returns the working draft to the table; the eventual atomic Save Changes commit calls `ProvidersStore.add(draft)`, captures the returned `ProviderId`, and uses it for any subsequent in-session reference. For an existing provider, the dialog's working copy keeps the stored `provider_id`; only mutable fields (including `name`) are updated.
7. **Import/export.** Provider import/export YAML carries `name`, never an `id`. The importer auto-generates the `provider_id` on insert; an `id:` key in an imported file is a soft warning (silently ignored) so older exports remain importable. The same applies to embedding configuration files. Exports surface the provider's snapshotted historical name on run exports and the current `name` on settings exports — internal `provider_id` values never appear in any user-facing file.

**Rationale:** The previous model forced the user to invent two unique values per provider (a user-typed `provider_id` plus a `label`). The user only ever interacts with the display name; the identifier exists solely so the data layer can reference the row across renames. Separating an internal auto-generated key from the user-entered display label collapses the apparent dual-uniqueness burden into one field the user actually sees. UUID4 is the natural choice for an internal opaque key because it is collision-resistant without coordination, stable across renames, and stores cleanly in the existing TEXT column. The historical-name snapshot on the run records preserves correct historical display when the user later renames a provider — a rename should not retroactively rewrite the labels of completed runs.

**Affected spec areas:** `10_Domain_and_Data/01_DOMAIN_MODEL.md` (Provider and EmbeddingConfig entities; entity diagram), `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`ProviderConfig`, `ProviderConfigDraft`, `EmbeddingConfig`, `EmbeddingConfigDraft`, `EmbeddingConfigId`, `BenchmarkRun.judge_provider_name`, `BenchmarkResult.provider_name`, related patch records), `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` (`providers.name UNIQUE`, `embedding_configs` table with `UNIQUE (name)`, `benchmark_runs.judge_provider_name`, `benchmark_results.provider_name`, snapshot rule), `10_Domain_and_Data/05_EXPORT_FORMATS.md` (exports surface `name`, never `provider_id`), `10_Domain_and_Data/06_IMPORT_FORMATS.md` (provider import carries `name`; `id` is retired / silently ignored), `08_Cross_Cutting/08-E_interfaces_contracts.md` (`ProvidersStore.add(draft) -> ProviderId`, `get_by_name`, `EmbeddingConfigStore` analogue, `RunSnapshotBuilder` snapshot fields), `08_Cross_Cutting/08-I_edge_cases.md` (new duplicate-name edge cases EC-PROV-10 through EC-PROV-13), `08_Cross_Cutting/08-J_event_bus_catalog.md` (event-bus rendering rule — events carry `provider_id`; UI resolves to snapshot or current name at render), `08_Cross_Cutting/08-Q_event_payload_schemas.md` (rendering-rule note), `00_Foundation/02_GLOSSARY.md` (Provider ID and Provider name entries), `06_Settings_Dialog/sub_dialogs/provider_edit.md` (Provider ID field removed; Name is the only unique-identifier input; state machine updates), `06_Settings_Dialog/description.md` (Providers table column renaming), `06_Settings_Dialog/mockup.html` (Provider ID input removed), `06_Settings_Dialog/flow_diagram.md` (add-provider sequence updated to show store-generated id), `06_Settings_Dialog/state_machine.md` (Name-validation sub-state replaces ID-validation), `02_New_Benchmark_Widget/`, `03_Resume_Benchmark_Widget/`, `04_Progress_Widget/`, `05_Result_Widget/`, `07_Common_Dialogs/generate_analysis_dialog.md` (dropdowns show name; historical surfaces show snapshot name), `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md`, `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md`, `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` (snapshot capture step), `11_Services_and_Algorithms/15_LOG_FORMATTING.md` (live vs snapshot rendering rule), `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`, `14_Process_and_Traceability/01_MODULE_INVENTORY.md` (store row updates), `15_Risks_and_Open_Questions/01_RISK_REGISTER.md` (provider-rename mitigation note), `12_Quality_and_NFRs/06_DATA_INTEGRITY.md` (UNIQUE-on-name invariant; auto-id atomicity).

---

### DD-34 — Adaptive timeout is per-role; judge calls get an independent ladder; embedding is a fixed budget; Test Inference and readiness are exempt (2026-06-03)

**Topic:** Which LLM-call surfaces consult the Adaptive Timeout Service, how the service keys its per-`(provider, model)` state, and what timeout policy applies to the surfaces that do NOT consult it.

**Decision:**

1. **Per-role state buckets.** The Adaptive Timeout Service's persistent and in-run state is keyed on `(provider_id, model_name, role)` instead of `(provider_id, model_name)`. The role is a member of the new `AdaptiveTimeoutRole` StrEnum (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.10a) with exactly two members: `INFERENCE` (Phase 2 per-task main inference, test role) and `JUDGE` (Phase 4 per-task judge call AND the user-initiated run-analysis generation call). A model used as both a test model AND a judge model carries two independent state buckets; exclusion in one role does NOT exclude the same model in the other.

2. **Service consumers — exhaustive.** The Adaptive Timeout Service is consulted by exactly three call sites: the Benchmark Pipeline Phase 2 (role=INFERENCE), the Benchmark Pipeline Phase 4 per-task judge call (role=JUDGE), and the Run Analysis Service's `generate(...)` call (role=JUDGE — shares the per-`(provider, model)` JUDGE bucket with the per-task judge calls; the persistent last-known-good budget carries between them, but the in-run consecutive-timeout count resets at each activity boundary).

3. **Exempt surfaces — fixed budgets only.** The Embedding Service uses a strictly **fixed** budget `eval.embedding_timeout_seconds` (default 30 s) — no adaptive escalation, no exclusion, no per-role bucket. On embedding timeout the task's cosine phase fails for that task and the binary verdict cascade (D-012) settles per the cosine-not-run handling; the very next task tries embedding afresh with the same fixed budget. `LLMClient.test_inference` (Provider Edit Test inference action) keeps its existing fixed 60 s `PROVIDER_TEST` watchdog (D-036, D-039) — Test Inference does NOT consult the Adaptive Timeout Service. `LLMClient.probe_health` (readiness probe) keeps its existing fixed short deadline — readiness probes do NOT consult the Adaptive Timeout Service either.

4. **New ResultStatus member.** `ResultStatus.FAILED_JUDGE_TIMEOUT` joins the enum. It is set when (a) a per-task judge call exhausts the role=JUDGE escalation ladder for that task, OR (b) the judge model is excluded for the run AFTER crossing `eval.judge_timeout_consecutive_threshold`, in which case every remaining task that would have entered the judge phase settles to `FAILED_JUDGE_TIMEOUT` directly. The task is NOT marked `COMPLETED`; `verdict` stays `None`. `FAILED_JUDGE_TIMEOUT` joins the **retryable terminal-state set** alongside `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, and `ERRORED` — a retry re-runs the **whole task end-to-end** (re-inference + re-grade), uniform with the other `FAILED_*` states (the original attempt's inference text and timings are NOT preserved on retry). *(Refined by DD-66: a `FAILED_JUDGE_TIMEOUT` retry now resumes at `AWAITING_JUDGE_CHECK`, preserving the inference/keyword/cosine outputs and re-running only the judge.)*

5. **New event.** `_judge_model_excluded` (payload `JudgeModelExcludedEvent`) fires once when the role=JUDGE bucket crosses the consecutive-max threshold during a `BENCHMARK_RUN` activity. The Progress widget Event Log renders it as a single warning row. The Run Analysis Service does NOT emit this event — analysis-call exhaustion is signalled inline through `RunAnalysisResult.outcome = FAILED` with `reason = "judge_timeout_exhausted"` and the Generate Analysis dialog renders that failure with a clear "pick a different model and retry" message. The `_judge_model_excluded` event is the judge-role analogue of the test-role exclusion already carried by `_model_stability_changed` (whose `model_state` field can reach `EXCLUDED` for a role=INFERENCE target); both can be active in the same run when the same `(provider, model)` was selected as both a test model AND the judge model.

6. **New settings keys.** Five new per-run-overridable keys are added (`08_Cross_Cutting/08-G_feature_flags.md` §5): `eval.judge_timeout_min_seconds` (default 20), `eval.judge_timeout_max_seconds` (default 120), `eval.judge_timeout_escalation_steps` (default 2), `eval.judge_timeout_consecutive_threshold` (default 3), and `eval.embedding_timeout_seconds` (default 30, fixed). The Settings dialog General tab gains the corresponding form fields (visible regardless of mode — these are run-time tuning knobs).

**Rationale:** Local LLM providers (Ollama, LM Studio, llama.cpp) can stall during model swaps, OOM situations, or for unknown reasons. The Phase 2 inference path was protected against this from the start (D-040 / `07_ADAPTIVE_TIMEOUT.md`); the Phase 4 judge path was not. Without a per-task judge budget a stalled judge could freeze the entire benchmark run indefinitely — the same risk the test-role adaptive timeout was introduced to mitigate. The judge path now gets the same protection, with an independent ladder so a judge-tuned budget does not have to match the test-model budget. Embedding calls are short (vector embeddings, not generative inference), so a fixed budget is sufficient; introducing per-role escalation for embedding would only multiply state without protecting against a real failure mode. Test Inference is a manual one-shot user action with its own 60 s deadline (D-039); the deadline acts as the budget and the user is in the loop. Readiness probes are invisible health checks with their own short fixed deadline (`09_READINESS_PROBE.md`); they must not be allowed to escalate into long timeouts the user cannot see.

**Affected spec areas:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`AdaptiveTimeoutRole` enum, `ResultStatus.FAILED_JUDGE_TIMEOUT`, `ErrorKind.JUDGE_TIMEOUT`, `JudgeModelExcludedEvent` struct, where-used updates), `08_Cross_Cutting/08-C_settings_hierarchy.md` (per-run-overridable group note), `08_Cross_Cutting/08-G_feature_flags.md` (five new keys + interaction notes), `08_Cross_Cutting/08-E_interfaces_contracts.md` (`AdaptiveTimeoutService` Protocol signatures with `role` parameter; per-role bucket semantics), `08_Cross_Cutting/08-I_edge_cases.md` (EC-PROV-4 / EC-PROV-4a / EC-PROV-4b / EC-PROV-4c / EC-PROV-4d / EC-PROV-4e / EC-PROV-4f), `08_Cross_Cutting/08-J_event_bus_catalog.md` (`_judge_model_excluded` row, `_model_stability_changed` per-role note, event-to-payload index), `08_Cross_Cutting/08-Q_event_payload_schemas.md` (`JudgeModelExcludedEvent` §3.6a + imported-types update), `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md` (per-role rewrite), `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` (Phase 4 adaptive consultation + Phase 3 fixed embedding budget + FAILED_JUDGE_TIMEOUT handling), `11_Services_and_Algorithms/05_JUDGE_PROTOCOL.md` (judge call consults Adaptive Timeout Service with role=JUDGE), `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` (fixed `eval.embedding_timeout_seconds`), `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md` (adaptive consultation with role=JUDGE; `judge_timeout_exhausted` outcome), `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md` (per-role note on Adaptive Timeout row), `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` (JUDGE_TIMEOUT entry), `04_Progress_Widget/description.md` (Event Log entry for `_judge_model_excluded`), `04_Progress_Widget/state_machine.md` (`FAILED_JUDGE_TIMEOUT` terminal state), `04_Progress_Widget/mockup.html` (example log line), `05_Result_Widget/description.md` (status badge + Retry action menu treats FAILED_JUDGE_TIMEOUT as retryable), `05_Result_Widget/tabs/summary_tab.md` (filter chip + Status column), `05_Result_Widget/tabs/details_tab.md` (Status field + judge tab surface), `05_Result_Widget/mockup.html` (example row), `07_Common_Dialogs/generate_analysis_dialog.md` (exhaustion failure message), `06_Settings_Dialog/description.md` (Judge timeouts + Embedding timeout fields), `06_Settings_Dialog/mockup.html` (form fields), `06_Settings_Dialog/state_machine.md` (field validation), `02_New_Benchmark_Widget/mode_specifics/full_grading.md` (Judge section pointer to Settings), `00_Foundation/02_GLOSSARY.md` (new entries), `12_Quality_and_NFRs/04_ERROR_RECOVERY.md` (judge / embedding timeout recovery paths), `15_Risks_and_Open_Questions/01_RISK_REGISTER.md` (R-015 mitigation extended).

---

### DD-35 — Numeric performance budgets are retired; responsiveness is owned by the concurrency model and stall handling by the Adaptive Timeout Service (2026-06-03)

**Topic:** Whether the specification should fix numeric performance budgets (cold-start time, resident-set-size caps, UI-latency percentiles, database-open time, test-suite duration, developer-loop wall-clock targets) and gate releases on them.

**Decision:**

1. **The performance-budgets document is retired.** `12_Quality_and_NFRs/01_PERFORMANCE_BUDGETS.md` is deleted from the specification. No file replaces it; the slot at position 01 in `12_Quality_and_NFRs/` is left empty and the remaining sibling files keep their existing numeric prefixes (renumbering would cascade more cross-reference churn than the retirement itself).

2. **No file in the specification fixes a numeric performance budget.** A statement of the form "cold start ≤ X seconds", "resident set size ≤ Y MB", "event-loop tick ≤ Z ms (95th percentile)", "database open ≤ N ms", or "full test suite ≤ M seconds wall-clock" is treated as a defect on sight. Per-test time budgets in `16_Engineering_Standards/07_TESTING_STANDARD.md` §11 are scoped to the test infrastructure (they classify a test as `slow` and exclude it from the PR-gate suite) and are NOT performance budgets in the retired sense.

3. **Performance concerns are addressed where the cause is addressed, not by a separate budget document.**
   - UI responsiveness during long operations is owned by the synchronous-backend + `QThreadPool` `TaskRunner` model (D-R-01): all blocking work runs on worker threads, the GUI thread never blocks, and results are marshalled to the GUI thread by the adapter. Authoritative documents: `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`, `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`, `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md`. *(Was previously the qasync main-loop pattern; superseded by D-R-01, 2026-06-04.)*
   - LLM-call latency and stall handling is owned by the Adaptive Timeout Service (per-role ladders for `INFERENCE` and `JUDGE`) and the fixed embedding timeout. Authoritative document: `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md` (see also DD-34).
   - Database access patterns are owned by the SQLite WAL configuration, the schema, and the single-writer serialisation rule. Authoritative documents: `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`, `12_Quality_and_NFRs/06_DATA_INTEGRITY.md`.
   - Resource ceilings (log file size, support-bundle size, run-log retention, in-memory buffer caps) are owned by `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md`. Those caps remain in force — they are concrete bounds with a defined behaviour at the cap, not numeric performance gates.

4. **Continuous integration enforces correctness gates, not performance gates.** The CI pipeline gates merges on `ruff`, `mypy --strict`, the import-linter contract, the architecture tests, and the `pytest` tiers — never on a wall-clock or memory-cap measurement. The `tests/perf/` directory in the layout is removed.

5. **Wording sweep.** Substantive prose that previously cited a numeric budget is rewritten to cite the responsible mechanism: "the loop-stall performance budget" becomes "the no-blocking-on-the-loop rule and its architecture test"; "chart aggregation exceeding its performance budget" becomes "chart aggregation visibly stalling the GUI loop"; "≤ 2.5 s cold start" used as a voice example in `00_Foundation/01_README.md` is replaced with a non-performance example. The generic acceptance-criteria pattern in `14_Process_and_Traceability/05_ACCEPTANCE_CRITERIA_PATTERNS.md` that previously suggested "move it to a performance budget" now suggests stating the underlying invariant and letting an architecture or concurrency test cover it.

**Rationale:** Ollama LLM Bench is a single-user local desktop application. Numeric budgets that are not gated by an automated CI check and not measured in any committed artifact add ceremony without value: they read as commitments the project does not actually enforce. The real performance concerns the budgets attempted to address are already owned by load-bearing parts of the architecture — the synchronous-backend + `QThreadPool` `TaskRunner` threading model (D-R-01), the GUI-thread-never-blocks rule, the Adaptive Timeout Service, the SQLite WAL configuration, and the resource-limit caps. Removing the budgets concentrates the specification on the mechanisms that produce good behaviour, rather than on numbers that describe an outcome nobody is positioned to measure on the project's reference hardware. Resource caps (Section 3 above's fourth bullet) survive because they are concrete behavioural bounds, not performance percentiles.

**Affected spec areas:** `12_Quality_and_NFRs/01_PERFORMANCE_BUDGETS.md` (deleted), `00_Foundation/01_README.md` (folder-structure listing and Voice example), `00_Foundation/06_CROSS_REF.md` (`12_Quality_and_NFRs/` description; topic-to-document map row), `12_Quality_and_NFRs/03_OBSERVABILITY.md` (summary table row for log-loop blocking), `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md` (no-blocking-on-the-loop paragraph; summary table row), `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md` (cross-references header), `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` (cross-references header), `16_Engineering_Standards/07_TESTING_STANDARD.md` (cross-references header; `tests/perf/` directory removed from the layout), `08_Cross_Cutting/08-N_implementation_pointers.md` (Continuous integration section's behavioural-spec pointer; concern-to-document index row), `14_Process_and_Traceability/05_ACCEPTANCE_CRITERIA_PATTERNS.md` (anti-pattern remediation wording), `15_Risks_and_Open_Questions/01_RISK_REGISTER.md` (R-010 mitigation and trigger-conditions wording).

---

### DD-36 — Nightly builds retired; auto-update feature retired entirely (2026-06-03)

**Topic:** Whether CI runs scheduled / nightly workflows and whether the application has any auto-update mechanism (background update check, update-feed reader, in-app "Check for updates" affordance, signed in-place update flow).

**Decision:**

1. **CI triggers narrow to two events.** The GitHub Actions workflows run on exactly two trigger events: (a) `pull_request` events (opened, synchronize, reopened) — runs the correctness gates (ruff, mypy --strict, import-linter, pytest, architecture tests) on the head SHA; produces no artifacts; (b) `push` of a tag matching the release-version pattern (e.g. `v*.*.*`) — runs the correctness gates and builds the per-OS artifacts and publishes them to the GitHub Release for that tag. There is NO `schedule` trigger, NO nightly cron, NO main-branch artifact build, and NO `workflow_dispatch` manual trigger. Slow tests excluded from the PR-gate suite are excluded outright — they can be run locally on demand. The CVE scan is either a manual/local task or part of the PR-gate, not a separate nightly workflow.

2. **The application has no auto-update mechanism.** No background update check; no on-startup update check; no periodic version poll; no "Check for updates" menu entry, button, dialog, or notification; no remote `updates.json` or version manifest; no signature verification of updates (because the application never fetches updates). The About dialog may show the application's current version for user reference, but the value is not compared to anything remote. There is no auto-updater module, no update-related settings keys, and no update-related feature flags.

3. **Updates are manual user actions.** Users learn of new releases by visiting the project's GitHub Releases page or by GitHub's "watch releases" notification (out of band). To update, the user downloads the new per-OS artifact, replaces the existing installation files, and relaunches. The application's data directory (database, logs, settings) is in the user home and is not touched by replacing the installation. The release-artifact channel is unchanged: GitHub Releases page; per-OS artifacts per D-028 (Windows zip; macOS/Linux per the existing spec).

4. **Document deletion.** `13_Distribution_and_Release/03_AUTO_UPDATE.md` is deleted from the specification. Sibling files in `13_Distribution_and_Release/` keep their existing numeric prefixes (the folder retains a gap at position 03).

5. **Constraint added.** `00_Foundation/05_CONSTRAINTS.md` carries a new hard constraint "No automatic update mechanism" (already added in the prior cascade). The existing "No telemetry, no analytics, no network calls except to LLM providers" constraint is now strictly consistent with the no-auto-update rule.

**Rationale:** Ollama LLM Bench is a single-user local desktop application distributed unsigned to a technical audience. An auto-update channel would add a recurring outbound network call (incompatible with the no-telemetry guarantee), a signing-key topology, an update-verification UI, and a permanent maintenance surface — costs the project will not pay for users who already track releases out of band. Nightly CI workflows likewise add minute consumption and operational surface without producing artifacts the project ships; correctness signal comes from PR-gate runs, and release artifacts come from tag-triggered builds.

**Affected spec areas:** `13_Distribution_and_Release/03_AUTO_UPDATE.md` (deleted), `00_Foundation/05_CONSTRAINTS.md` (new constraint), `00_Foundation/06_CROSS_REF.md` (folder description), `08_Cross_Cutting/08-N_implementation_pointers.md` (behavioural-spec pointer), `12_Quality_and_NFRs/02_SECURITY_MODEL.md` (update-handling bullet), `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md` (KI-05, KI-06, tested-version definition), `13_Distribution_and_Release/02_INSTALLATION.md` (auto-updater rationale removed; Updating section added), `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md` (auto-updater Q&A removed), `13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md` (defaults list), `13_Distribution_and_Release/06_VERSIONING_POLICY.md` (cross-references; auto-update paragraphs; release-pipeline description), `15_Risks_and_Open_Questions/01_RISK_REGISTER.md` (mitigations; nightly framing), `15_Risks_and_Open_Questions/03_PROPOSED_ADRS.md` (auto-update mention), `16_Engineering_Standards/02_TOOLCHAIN.md` (pytest-rerunfailures purpose), `16_Engineering_Standards/07_TESTING_STANDARD.md` (slow-tests + CVE scan paragraphs), `16_Engineering_Standards/08_CICD_AND_PACKAGING.md` (CI section, already rewritten in prior cascade).

---

### DD-37 — Closing the last two open questions: per-task status enum names (D-016 + D-047) and anyio adoption (D-027 confirmed stdlib-only) (2026-06-03)

**Topic:** The two remaining items in `15_Risks_and_Open_Questions/02_OPEN_QUESTIONS.md` — Q-001 (per-task status enum names) and Q-002 (anyio adoption) — and their resolutions.

**Decision:**

1. **Q-001 — Per-task status enum names is closed; the open-questions doc was stale.** The names were already frozen by D-016: `PENDING`, `RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`, `AWAITING_COSINE_CHECK`, `AWAITING_JUDGE_CHECK`, `COMPLETED`, `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `ERRORED`. D-047 added `FAILED_JUDGE_TIMEOUT` for a total of 11 statuses. The authoritative shape lives in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`. The verdict (PASS / FAIL) is a separate field, set only when status = COMPLETED. The five retryable terminal states are FAILED_INFERENCE, FAILED_PROVIDER, FAILED_TIMEOUT, FAILED_JUDGE_TIMEOUT, ERRORED.

2. **Q-002 — anyio is NOT adopted; stdlib-only is confirmed.** *(SUPERSEDED by D-R-01, 2026-06-04: the application now uses a synchronous, Qt-free backend on a `QThreadPool` `TaskRunner` with a `threading.Event`-backed `CancellationToken`; `asyncio`, `qasync`, and `anyio` are all absent, so the anyio-vs-stdlib question is moot. Authoritative: `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` and `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`.)* The historical decision: the concurrency model uses standard-library asyncio + qasync + an application-defined `CancellationToken` (per D-027). Shielded cleanup is expressed with `asyncio.shield`, try/finally blocks, and `asyncio.TaskGroup` with shielded subroutines — not with anyio cancel-scopes. The dependency set does not include anyio.

**Rationale:** Q-001 was a documentation drift — the decision had been made twice (D-016 and D-047) but the open-questions register was never updated. Q-002 was a genuine deferral; the choice to stay on stdlib aligns with the project's lean-dependency posture and avoids the conceptual overlap between asyncio's and anyio's TaskGroup / cancel-scope primitives. Shielded-cleanup paths in this specification are simple enough to express with stdlib primitives.

**Affected spec areas:** `15_Risks_and_Open_Questions/02_OPEN_QUESTIONS.md` (both Q entries marked resolved), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (explicit no-anyio declaration + shielded-cleanup pattern), `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` (any anyio mention retired), `16_Engineering_Standards/02_TOOLCHAIN.md` (verify anyio absent from dependency tables).

---

### DD-38 — The benchmark pipeline runs on a single dedicated dispatcher thread (2026-06-06)

**Topic:** Which thread owns benchmark execution — the host thread of the pipeline's serial run loop (the "dispatcher" that submits one unit, blocks on its `Future`, persists the result, and submits the next).

**Decision:** The run loop executes on **one dedicated, long-lived dispatcher thread**, created by the composition root, owned by the adapter layer alongside the `TaskRunner`, named (`pipeline-dispatcher`), and joined at shutdown. `BenchmarkFlowApi.start`/`resume` are fast-synchronous on the GUI thread: they enqueue a run command to the dispatcher thread and return promptly. The application has exactly three execution contexts: the GUI thread (never blocks), the dispatcher thread (the **only** thread permitted to block awaiting a unit's `Future`; the only thread that touches the ProviderCircuitBreaker and the AdaptiveTimeoutService, persists results, and emits run-domain events), and the `TaskRunner` pool workers (run individual blocking units; a pool worker never submits work to the pool and blocks awaiting it). The no-raw-threads anti-pattern is scoped to *work units*; the dispatcher thread is its single sanctioned exception. The backend remains thread-agnostic: the pipeline is plain synchronous code that runs on whatever thread invokes it (the dispatcher thread in the app; the test's own thread under an inline runner).

**Rationale:** The dispatcher must block awaiting unit `Future`s, which is illegal on the GUI thread (frozen UI) and self-deadlocking on a pool worker (a worker waiting on work that needs a worker — pool starvation). A dedicated owned thread is the only placement that preserves the three standing commitments at once: a responsive GUI, the Qt-free synchronous backend (D-R-01), and a deadlock-free pool. It also makes the lock-free single-owner design of the circuit breaker and adaptive-timeout service provably safe by giving them exactly one accessing thread. Resolves review issue SPEC-002.

**Affected spec areas:** `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` (new §4a; §1, §2 diagram + key facts, §8 thread-boundary rules, §12 anti-patterns), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (new §6.1a; intro, §4 preconditions, §6.2, §6.6, §6.8 diagram, §6.9 shutdown, §9, test case 16), `08_Cross_Cutting/08-E_interfaces_contracts.md` (§4 threading contract — three execution contexts; §11 `BenchmarkFlowApi` docstrings + threading note), `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md` (§4 new guarantee, §8 shutdown ordering, §9 summary row), `08_Cross_Cutting/08-J_event_bus_catalog.md` (run-domain emitter wording), `08_Cross_Cutting/08-N_implementation_pointers.md` (dispatcher wording).

---

### DD-39 — Two-level cancellation: Pause finishes the in-flight call; Stop and Shutdown abort it promptly (2026-06-06)

**Topic:** What happens to the in-flight provider call when the user pauses, stops, or quits — and the resolution of the contradiction between the LLM-client contract ("a cancelled call stops consuming promptly") and the concurrency standard ("a request already issued is never interrupted mid-flight").

**Decision:** The `CancellationToken` carries two monotonic cancellation levels — `NONE → SOFT → HARD`, never downgraded, guarded by one internal lock. **Soft** (Pause, automatic pauses): the in-flight unit finishes and is saved; the halt lands at the next safe checkpoint; worst-case wait is the single unit's remaining adaptive budget. **Hard** (Stop, Shutdown): the in-flight call is aborted promptly — the LLM client polls `is_hard_cancelled` at each chunk boundary AND registers a hard-cancel **abort hook** (`token.add_hard_cancel_hook(close_stream)`, removed in the call's `finally`) that `cancel(hard=True)` invokes on the cancelling thread to close the in-flight streaming response, bounding even a silent no-token wait. The abort completes within `provider.hard_cancel_max_ms` (default 2000 ms, new settings key). A hard-aborted call raises `TaskCancelledError`; nothing partial is parsed, scored, or persisted — the unit's result row stays `PENDING` and is re-run on resume; a cancelled attempt reports **no outcome** to the AdaptiveTimeoutService or the ProviderCircuitBreaker. A Stop clicked during a draining Pause upgrades soft→hard and genuinely accelerates the halt; a Pause during a pending Stop is a no-op (hard is sticky). Shutdown hard-cancels, so `os._exit` becomes a genuine last resort rather than a routine path. Hooks must be idempotent, thread-safe, and non-raising.

**Rationale:** The two levels match the two user intents. Pause exists to preserve work (its primary use is swapping local models), so it must not discard the in-flight call. Stop and app-quit express exit intent; making them wait out a call whose ceiling is `benchmark.max_timeout_seconds` (default 900 s) produces a Stop button that can stall for 15 minutes — users would force-kill the app, causing exactly the dirty exits the spec guards against. The client document already specified prompt chunk-boundary cancellation; this decision scopes that text to the hard level and the standard's "never interrupted" text to the soft level, making both true. Resolves review issue SPEC-003; supplies the monotonic-level primitive SPEC-010's pause-vs-stop outcome fix builds on.

**Affected spec areas:** `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` (§5 token redefined two-level with abort hooks + updated sequence diagram; §6 Pause/Stop/Shutdown rewritten; "Why Pause finishes the in-flight unit — and Stop does not"; §12 anti-pattern rows), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (§6.3; §6.6 cancelled-unit-reports-no-outcome; §6.8 Stop, stop-during-pause, latency bounds, UI copy; §6.9 shutdown; test cases 9, 13, new 17), `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` (§2 contract; §6.3/§6.4 pseudocode — hard-only poll + hook registration + `TaskCancelledError`; §6.6 rewritten; settings table + `provider.hard_cancel_max_ms`; §11 edge row), `08_Cross_Cutting/08-B_benchmark_state_machine.md` (§8.1, §8.4 Stop, invariant 4), `04_Progress_Widget/description.md` (§3.4 draining copy, §3.5 Stop tooltip, §3.6 Pause-vs-Stop table, Stopping state), `11_Services_and_Algorithms/18_RETRY_POLICY.md` (§6.5), `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md` (§4 bullet, §8 step 1, §9 summary row).

---

### DD-40 — Two serial domains; the dispatcher orchestrates all fan-out batches; pool size pinned (2026-06-06)

**Topic:** The exact scope of the application's serial / one-at-a-time restrictions, the deadlock in the readiness probe's `probe_all` (a pool worker submitting child probes to its own pool and blocking on them), and the unspecified `QThreadPool` size.

**Decision:** Three connected rulings. **(1) The two serial domains.** The serial restrictions apply to exactly two things and nothing else: the **benchmark run** (tasks one-by-one, stage-by-stage — D-R-16) and **LLM inference globally** (at most one inference-class call — chat, per-task judge, embedding computation, test inference — in flight anywhere, enforced by the single-inference gate). Non-inference work is unrestricted and may run concurrently on the worker pool: reachability handshakes and model-list fetches (`probe_health`, `list_models` — they make no model compute anything), CPU-bound computations (chart aggregation, CSV assembly), and file I/O. **(2) Dispatcher-orchestrated fan-out.** The dispatcher thread (DD-38) is the only sanctioned block-on-futures orchestrator: besides the run loop it hosts the readiness `probe_all` batch — the dispatcher submits the per-provider reachability handshakes to the shared `TaskRunner` concurrently and joins them; the single `embed` probe (the batch's only inference-class call) runs once, serially, after the fan-out, under the `READINESS_PROBE` gate hold. A leaf pool unit never submits-and-waits on the pool, so pool-starvation deadlock is impossible by construction; the gate guarantees a probe batch and a benchmark run never overlap, so the dispatcher is free whenever a batch can run. **(3) Pool size.** `QThreadPool.maxThreadCount` is fixed at **4**, set once in the composition root: N enabled providers complete a probe batch in at most `ceil(N/4)` probe-timeout windows (8 providers ≈ 10 s), comfortably inside the 30 s `READINESS_PROBE` watchdog.

**Rationale:** The serial restrictions exist to keep benchmark measurements undistorted (D-R-16) and to avoid concurrent model compute on local servers — purposes that concern the run and inference only; serializing handshakes or CPU work would slow the application for no benefit (product-owner clarification, 2026-06-06). The previous `probe_all` design had a worker block on children needing slots in the same pool — a starvation deadlock on the startup path, and a violation of DD-38's no-submit-and-wait rule. Orchestrating the batch on the dispatcher thread fixes the deadlock structurally with zero new threads, preserves the "exactly one `TaskRunner`" and "no component owns threads" guarantees verbatim, and keeps startup readiness fast. Resolves review issue SPEC-004.

**Affected spec areas:** `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` (§1 "The two serial domains" normative block; §3 pool size pinned; §4a dispatcher-as-orchestrator rule), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (§6.0 inference-scope clarification; §6.1a orchestrator bullet), `11_Services_and_Algorithms/09_READINESS_PROBE.md` (§4 preconditions; §6.4 algorithm + timing; §9 threading rewritten; RP-08 updated; new RP-18/RP-19), `08_Cross_Cutting/08-E_interfaces_contracts.md` (§12 ReadinessService threading note), `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md` (§2 two-domains bullet; §7 pool size; §9 summary row), `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md` (§6 pool row).

---

### DD-41 — The single DB writer is one write connection plus one lock; writes are synchronous on the calling thread (2026-06-06)

**Topic:** The concrete definition of "the single DB writer" — previously left as "a single-writer queue, or an equivalent write lock" with one document committing to a bounded back-pressure queue — and the contradiction over whether the worker unit or the dispatcher persists a run's result rows.

**Decision:** The single DB writer is **exactly one write connection** (opened by the persistence layer at startup) **guarded by one `threading.Lock`**. A store write acquires the lock, runs its transaction with `BEGIN IMMEDIATE`, **synchronously on the calling thread**, commits, and releases — a write is durably committed when the call returns; the durability point and the code line coincide. There is **no write queue and no back-pressure**. Readers use separate read-only connections (WAL snapshot reads). Write affinity: during a run, all run-domain writes (result rows, run header) are issued **only by the dispatcher thread** (DD-38) — worker units return their data and never write to the database and never emit run-domain events (their only emissions are the live `_inference_progress` heartbeats from inside the streaming call); the GUI thread issues only small fast writes (settings save, rename); a worker unit outside a run (configuration import) writes through the same lock. Ordering language is corrected from "FIFO" to what the integrity argument actually needs: writes are **serialized, atomic, and causally ordered per caller** (a lock does not promise global fairness; no guarantee relies on it). The dispatcher persists each unit's result before submitting the next, so "every completed unit is durably saved before the next starts" — the property pause/resume and crash recovery depend on — holds by construction.

**Rationale:** A queue makes "save" mean "enqueue", silently breaking the resume/crash guarantee unless every critical caller blocks on a flush — at which point the queue adds machinery, a third owned thread, and a back-pressure failure mode (a stalled run creation) without adding throughput where it matters. Serial execution (D-R-16) makes write contention naturally rare, so a synchronous lock is both the simplest and the strongest design. Settling write affinity on the dispatcher resolves the §6.6-worker-persists vs §6.2-dispatcher-persists contradiction in the direction DD-38 already established and keeps the event catalog's single-emitter total-ordering proof intact. Resolves review issue SPEC-005.

**Affected spec areas:** `12_Quality_and_NFRs/06_DATA_INTEGRITY.md` (§3 rewritten; causal-order bullet; summary row), `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md` (§3 two bullets; §9 summary row), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (§6.6 worker steps + dispatcher persist paragraph; §6.8 pause sequence diagram), `12_Quality_and_NFRs/07_RESOURCE_LIMITS.md` (§4 writer row; §6 connections row; §7 summary row), `08_Cross_Cutting/08-E_interfaces_contracts.md` (§7 store envelope), `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` (new §2.1 connection topology), `08_Cross_Cutting/08-O_persistence_schema.md` (§3), `08_Cross_Cutting/08-I_edge_cases.md` (EC-PERSIST-3), `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` (EC-PERSIST-3 row), `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` (§8 DB-writer bullet; §12 anti-pattern row).

---

### DD-42 — Halt outcomes derive from one atomic token snapshot; the cancel reason is a closed enum (2026-06-06)

**Topic:** How the pipeline decides whether a halted run settles as in-memory `PAUSED`, persisted `STOPPED`, or is left `INCOMPLETE` at shutdown — previously unwritten, with the answer spread across free-text reason strings read non-atomically (a torn read between a Stop click's level and reason writes could misclassify the run).

**Decision:** Three additions on top of DD-39's two-level token. **(1) Typed state.** The cancel reason becomes a closed enum `CancelReason` (`USER_PAUSE`, `AUTO_PAUSE`, `USER_STOP`, `APP_SHUTDOWN`) and the level is exposed as `CancelLevel` (`NONE`/`SOFT`/`HARD`) — both defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.22/§4.23; `TaskCancelledError` carries the `CancelReason`. **(2) Atomic snapshot.** `CancellationToken.snapshot()` returns the `(CancelLevel, CancelReason)` pair in one read under the token's existing lock; level and reason are written together under the same lock, so a torn read is impossible. **(3) The outcome matrix and read point.** The dispatcher derives the halt outcome from exactly **one** snapshot per halt, taken after the in-flight unit settles (saved on soft / discarded on hard) and before any terminal status is persisted or terminal event emitted: `NONE` → normal completion; `SOFT` + `USER_PAUSE`/`AUTO_PAUSE` → park as `PAUSED` (persisted stays `INCOMPLETE`); `HARD` + `USER_STOP` → persist `STOPPED`; `HARD` + `APP_SHUTDOWN` → persist nothing terminal, leave `INCOMPLETE` for next-launch recovery. A cancel arriving **after** the snapshot is never lost: a run parked as `PAUSED` still holds its token, and a later hard cancel wakes the parked dispatcher through the `Paused → Stopping` transition, where the matrix is applied again.

**Rationale:** The terminal classification of a run must not depend on an improvised multi-field read pattern with a milliseconds-wide race window — the exact window the impatient-user input pattern (Pause… Stop) hits. One lock-guarded snapshot plus a normative matrix makes the rule reviewable and testable; the closed enum (product-owner refinement) makes the reasons typo-proof and exhaustively matchable; the parked-state rule closes the post-snapshot window structurally rather than by timing. Resolves review issue SPEC-010; completes the DD-39 foundation.

**Affected spec areas:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (new §4.22 `CancelLevel`, §4.23 `CancelReason`), `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` (§5 token listing typed + `snapshot()`; closed-enum + read-point rule; diagrams/steps use enum members), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (§6.8 "Outcome derivation (DD-42)" matrix; enum members in walkthroughs; test case 18), `08_Cross_Cutting/08-B_benchmark_state_machine.md` (§2.3 matrix note), `08_Cross_Cutting/08-E_interfaces_contracts.md` (§11 `stop()` signature/docstring), `11_Services_and_Algorithms/18_RETRY_POLICY.md` (example).

---

### DD-43 — The async residue purge: the module inventory matches D-R-01, and the async-native libraries are removed (2026-06-06)

**Topic:** Surviving artifacts of the superseded `asyncio` design (pre-D-R-01) in the authoritative module inventory, the service inventory, the toolchain dependency set, the provider registry's thread-safety reasoning, and the glossary.

**Decision:** All async-era residue is purged. **(1) Module inventory.** The five rows that declared methods "async" now state the real contracts: readiness `probe` is a blocking `TaskRunner` leaf unit and `probe_all` is dispatcher-orchestrated (DD-38/DD-40); the Anthropic and Gemini adapters' `chat`/`probe_health` are blocking methods on `TaskRunner` workers; pipeline `start`/`resume` are fast-synchronous handoffs to the dispatcher thread (DD-38); embedding `embed` is blocking on a worker. **(2) Dependencies.** `purgatory` (asyncio-native circuit breaker) and `stamina` (async-oriented retry) are removed from the runtime dependency set and added to the banned-libraries table; the in-house synchronous circuit breaker (`11/08_CIRCUIT_BREAKER.md`) and the in-house `CancellationToken`-aware retry wrapper (`11/18_RETRY_POLICY.md`) — both already fully specified — are the implementations. **(3) Registry reasoning.** `03_PROVIDER_REGISTRY.md` §6.1/§9 now justify reload safety in terms of the real model: dispatcher/worker-thread readers and one atomic reference assignment (atomic under CPython's GIL), not cooperative async scheduling. **(4) Terminology.** All "dispatched to the executor" phrasing (an asyncio-era concept) becomes "dispatched to a `TaskRunner` worker" (module + service inventories); the glossary's "async tasks" example primitive is replaced. **(5) Enforcement.** The architecture-test for D-R-01 is extended: no application module defines an `async def` function.

**Rationale:** The module inventory names itself the authoritative cross-check — the document a coder builds each module from. Five of its rows mandated `async` methods that have no event loop to run on, a direct path to implementing the highest-risk subsystem against a dead architecture. The two async-native libraries either fail or smuggle an event loop into a codebase whose architecture tests forbid one — and neither matches the spec'd algorithms (per-role adaptive ladders, token-aware backoff, dispatcher-confined breaker state) anyway. Executes D-R-01; resolves review issue SPEC-007.

**Affected spec areas:** `14_Process_and_Traceability/01_MODULE_INVENTORY.md` (7 rows), `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md` (4 rows), `16_Engineering_Standards/02_TOOLCHAIN.md` (version table, `[dependency-groups]`, banned-libraries table), `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md` (§6.1, §9), `00_Foundation/02_GLOSSARY.md` (concurrency vocabulary note), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (test case 1).

---

### DD-44 — The error model is ratified: exceptions with controlled handling; the pipeline's "never raises" gets its containment mechanism (2026-06-06)

**Topic:** The product brief's architecture goal "No exceptions (result/error returns instead)" appeared to contradict the binding exception-native error standard — and, independently, the pipeline's "never raises to its caller" guarantee was asserted without a mechanism (its dependencies all raise; the persist-failure case was undefined).

**Decision:** The exception-native standard is **ratified** as the binding error model, with the product owner's clarified context recorded for provenance: *the brief's "No exceptions" referred to requirements compliance — "all requirements should be followed without any exceptions from the rules" — not to Python exceptions. The application should use exceptions (standard Python behaviour), with controlled handling everywhere: some caught and returned as results from the function, some caught, wrapped, and re-thrown to drive exception-based logic; the user must never see the app broken by an uncaught exception; the app is not re-implemented "in the GoLang way".* (Product owner, 2026-06-06.) The standard now states the three sanctioned handling shapes normatively (catch-and-return-as-data at the failure-as-data surfaces; catch-wrap-rethrow at adapter boundaries; never-catch for `ProgrammerError`) and the user-facing guarantee. The pipeline contract gains **§11a Exception containment**: a table mapping every exception class its dependencies can raise to its catch point and conversion — including the previously undefined **persist-failure path** (`DatabaseLockedError` retried per the retry table; an exhausted/permanent persistence failure settles the run `FAILED` best-effort; if even the header write fails: log to `app.*`, emit `_run_failed`, leave the run `INCOMPLETE` for the next-launch sweep). Enforcement: an architecture test invokes every public `BenchmarkFlowApi` method against fakes raising each taxonomy category; all must return normally except `ProgrammerError`.

**Rationale:** The spec is internally consistent and exception-native across all 145 files; the brief's goal turned out to be a terminology collision, not a competing design. What the goal genuinely requires — no exception chaos reaching callers or users — is exactly what the failure-as-data boundaries deliver, and the one real defect was the unspecified containment mechanism, now closed at its most dangerous point (a write failure inside the durability-critical persist call). Resolves review issue SPEC-006.

**Affected spec areas:** `16_Engineering_Standards/05_ERROR_HANDLING_STANDARD.md` (§1 ratification block), `08_Cross_Cutting/08-E_interfaces_contracts.md` (§11 errors note; new §11a containment table + enforcement), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (§8 persist-failure bullet).

---

### DD-45 — Cosine grading simplified: one whole-text score, one user-configured threshold; ResponseScope removed (2026-06-06)

**Topic:** The cosine phase's `ResponseScope` machinery (`EXACT`/`CONTAINS`/`COVERS`) and its three threshold keys — including the review-found contradiction where the normative whole-text algorithm (§6.4) was contradicted by stale sliding-window test cases, and a latent defaults mismatch (08-G said 0.90/0.70/0.60; the embedding service said 0.92/0.85/0.75).

**Decision (product owner, 2026-06-06):** The cosine stage is exactly: embed the full LLM answer **without reasoning** (`sanitized_response`); embed the full `golden_answer`; compare the two embeddings; clamp the cosine into `[0, 1]` (values below 0 dropped to 0); store the Cosine Score; mark the task's cosine verdict PASS/FAIL against **one user-configured threshold** — the new setting `eval.cosine_threshold` (float `CosineThreshold` 0.0–1.0, default **0.85**, per-run-overridable, frozen into the run snapshot). `EXACT`/`CONTAINS`/`COVERS` are **removed entirely** — "the cosine value already shows how close the answer is; we do not need additional interpretations": the `ResponseScope` enum is retired (tombstoned §4.7), `BenchmarkTask.response_scope` and the `benchmark_tasks.response_scope` column are deleted, the YAML key is retired (a legacy file containing it loads with the key ignored and a soft warning), the Task Editor field is removed (form, field reference §9 tombstoned, mockup, YAML preview), and the three `eval.cosine_threshold_*` keys are replaced by the single key everywhere (registry, Settings dialog + mockup, run-summary dialog, pipeline, embedding service). The stale sliding-window test cases die with the scopes; new tests assert the whole-text single-score property and the at-or-above boundary. **Kept deliberately:** the cosine skip for `code_generation`/`code_review`/`reasoning` task types (§6.6 — confirmed by the product owner), the embedding cache, the semantic-term check with its own per-term threshold, and the [0,1] clamp (which already matched the requested behaviour).

**Rationale:** The three scopes computed the identical score and differed only in which of three numbers it was compared to — an interpretation layer with no informational payload, paid for with a per-task authoring decision, three settings, a DB column, a YAML key, and an editor field. One threshold says the only thing left to decide: is this closeness acceptable. The change also dissolves the §6.4-vs-test-cases contradiction and the 08-G defaults mismatch as side effects. Resolves review issue SPEC-008 (superset of its Option A).

**Affected spec areas:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (§4.7 tombstoned; `BenchmarkTask`; enum-persistence index), `10_Domain_and_Data/01_DOMAIN_MODEL.md` (ER), `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` (DDL), `10_Domain_and_Data/04_YAML_TASK_FORMAT.md` (field table; §5.3; key order; §9.2 retired-key rule; 3 examples; EC row), `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` (intro; inputs/outputs/preconditions; §6.4 rewritten; semantic-term clause; config; examples; tests 7–9, 11), `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` (inputs; cosine phase; flowchart; config), `08_Cross_Cutting/08-G_feature_flags.md` (one key, one consult row), `06_Settings_Dialog/description.md` + `mockup.html`, `07_Common_Dialogs/run_summary_dialog.md`, `09_Task_Editor/` (description, field_reference §9 tombstone + ToC + column list, implementation_structure, mockup ×3 blocks), `08_Cross_Cutting/08-I_edge_cases.md` (EC-TASK-5), `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` (EC-TASK-5), `11_Services_and_Algorithms/12_YAML_FORMATTER.md` (key order), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (Example 1 field list), `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md` (defaults row).

---

### DD-46 — One universal judge prompt steered by category/sub-category; task_type removed; cosine becomes a task-level opt-out; judge context overflow is detected and reported (2026-06-06)

**Topic:** The judge protocol's missing rubric texts (every document pointed at another; the rubric bodies existed nowhere) and the product owner's redesign of the judge and the task schema.

**Decision (product owner, 2026-06-06):** Four connected rulings. **(1) One universal judge prompt.** There is no per-`task_type` rubric and no `{rubric_text}`: the system message is a single template whose domain expertise is steered by the task's `category` / `sub_category` ("You are a judge … in the area of: {category} / {sub_category} … apply the established best practices of this area"); the decisive grading instructions are the task-authored pass/fail criteria. The judge is single-shot and non-agentic, so the user message deliberately carries the **full task context** — question, the system prompt the candidate model received, source material, golden answer (one acceptable answer, not the only one), pass/fail criteria, keyword lists (required, semantic, forbidden), fail example, and the candidate response — "bad context is the problem of the user who created the task." **(2) Prior-stage results are excluded from the judge prompt.** The judge is the independent final gate that can confirm or overturn the keyword/cosine stages in either direction; feeding it their outcomes would anchor the verdict and destroy that corrective power. **(3) `task_type` is removed.** After (1) and the cosine flag in (4) it had zero behavioral consumers (charts/filters already use `category`); the field, `TaskTypeStr`, `WELL_KNOWN_TASK_TYPES` (§4.21 tombstoned), the DB column, the YAML key (retired: ignored + soft warning), the Task Editor field and its conditional-group mechanism (optional groups are now always available), and the rubric-era validation rules are all gone; the synthetic generator marks tasks via `category = "System Performance"`. **(4) Cosine is a task-level decision: `cosine_enabled`** (bool, optional, default `true`; field_reference slot 7) — cosine runs iff `cosine_enabled` and a `golden_answer` exists, exactly analogous to the keyword phase skipping when no keywords are declared; the hardcoded code/reasoning-type skip is superseded (amending the "kept" clause of DD-45). **Plus: judge context overflow handling.** The judge prompt is by construction the largest prompt the application builds; the user is told (Settings/judge-picker help) that the judge model needs a sufficient context window; a provider context-length rejection is translated to the new permanent leaf `ProviderContextLengthError` (never retried — retrying cannot shrink the prompt), settling the result `ERRORED` with a user-facing message naming the judge model, carrying the provider's redacted detail, and advising a larger-context judge model (inference-phase overflow settles `FAILED_INFERENCE`).

**Rationale:** Task types are an open vocabulary, so pre-written rubrics could never cover real usage, and users will not author custom rubrics — but every task already carries author-written criteria and an area label. A universal prompt with full context makes the judge implementable, golden-testable, and honest about its single-shot nature; excluding prior-stage outcomes preserves its role as the corrective final gate. Removing a zero-consumer field eliminates a third redundant label. Resolves review issue SPEC-009 (and the prompt-improvement was applied to the owner's draft wording as requested).

**Affected spec areas:** `08_Cross_Cutting/08-P_judge_protocol.md` (§4.1 universal template; §4.2 TASK AREA + placeholder rules + prior-stage exclusion; new §4.3 context size and overflow; §5 tombstoned; tests 14/14a/14b + edge row), `11_Services_and_Algorithms/05_JUDGE_PROTOCOL.md` (pointer text), `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` (judge para; inputs; cosine-phase rule; embedding precondition; 2 examples), `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` (new `ProviderContextLengthError` leaf + diagram node), `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` (§6.6 rewritten to `cosine_enabled`; inputs; preconditions; example; tests 10–12), `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`cosine_enabled` field; `TaskTypeStr` removed; §4.21 tombstoned), `10_Domain_and_Data/01_DOMAIN_MODEL.md` (ER + prose), `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` (column swap; open-vocabulary exceptions removed), `10_Domain_and_Data/04_YAML_TASK_FORMAT.md` (§5.2 replaced; field table; key order; validation rows; 10 example lines; EC-TASK-4), `09_Task_Editor/` (description — control kinds, conditional groups now always-available, hard-error list, EC-TE-03/04; field_reference — slot 7 now `cosine_enabled`, translation-field rules unconditioned, column list; implementation_structure; mockup — field, group header, YAML preview, empty-state field, severity-badge legend), `11_Services_and_Algorithms/12_YAML_FORMATTER.md` (canonical order + comment examples), `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md` (rules/examples re-keyed), `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md` (synthetic markers), `05_Result_Widget/tabs/details_tab.md` (column 6 → Category; meta grid), `08_Cross_Cutting/08-I_edge_cases.md` (EC-TASK-3/4), `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` (EC-TASK-4), `08_Cross_Cutting/08-O_persistence_schema.md` (value conventions)., `10_Domain_and_Data/05_EXPORT_FORMATS.md` (Details export Task Type column removed — residual fixed during SPEC-023)

---

### DD-47 — Advanced Options expose every per-run-overridable setting; overrides travel as registry-keyed entries, changed keys only (2026-06-06)

**Topic:** The snapshot pseudo-code in `08-C` §5 read three fields that do not exist on `RunStartRequest` (`streaming_enabled`, `reasoning_effort`, `warmup_enabled`), and — per the product owner's clarified intent — the New Benchmark Advanced Options were incomplete: only 8 of the 24 per-run-overridable registry keys had controls.

**Decision (product owner, 2026-06-06):** The original intent is made normative: *every* setting that affects the run and is configurable in the Settings window is also visible and overridable, for the current run, in the New Benchmark Advanced Options. **(1) Completeness rule.** §4.7 exposes every `PER_RUN_OVERRIDABLE` key (`08-G` ✓ column) except `feature.judge_run_analysis_enabled`, which is the form's primary analysis toggle; the previously missing controls are added — run-boundary toggles (`benchmark.pause_on_phase/provider/model_switch`, `benchmark.stop_on_provider_health_failure`) in every mode, and the evaluation block (`eval.phase_keyword/cosine/judge_enabled`, `eval.force_judge_on_prior_failure`, `eval.cosine_threshold`, the four `eval.judge_timeout_*` keys, `eval.embedding_timeout_seconds`, `eval.min_sample_size`) shown only in `FULL_GRADING` (hidden, not greyed, elsewhere). Adding a per-run-overridable key to the registry REQUIRES adding its control; a UI test compares the control map against `PER_RUN_OVERRIDABLE`. **(2) Seeding and carriage.** Controls are seeded from the `User-Saved ▶ Default` resolution; only the keys the user **changed** are carried on `RunStartRequest.setting_overrides` as registry-keyed `BenchmarkRunSettingEntry` rows (an absent key keeps the saved value, which snapshot step 1 already captured); every carried key must be in `PER_RUN_OVERRIDABLE` — an unknown key is a run-creation validation error rejected before the snapshot freezes. **(3) The recipe matches the DTO.** `08-C` §5's pseudo-code now applies the one named field (`judge_analysis_enabled` — the widget owns its mode-driven default; the value at Start is captured verbatim) plus a generic loop over `setting_overrides`; the three phantom field reads are gone. The widget view-model carries `advanced_values: dict[SettingKey, str]` + `advanced_dirty: frozenset[SettingKey]` instead of eight named fields.

**Rationale:** One mechanism, keyed identically to the settings registry, means a new run-affecting setting never again requires a DTO change — and the user's mental model ("the Settings values, overridable per run") is exactly what the form delivers. Resolves review issue SPEC-011.

**Affected spec areas:** `08_Cross_Cutting/08-C_settings_hierarchy.md` (§5 step 2, pseudo-code, mode-default ownership), `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`setting_overrides` contract row), `02_New_Benchmark_Widget/description.md` (§4.7 two new control groups + completeness and carriage rules; view-model), `02_New_Benchmark_Widget/mockup.html` (both expanded Advanced panels gain the new rows; evaluation rows in the grading panel), `02_New_Benchmark_Widget/mode_specifics/` (3 files).

---

### DD-48 — No automatic billable calls, including embeddings: handshake-only readiness, one user-initiated embedding test, and a run-start fail-fast embed probe (2026-06-06)

**Topic:** The readiness probe automatically issued a real `embed("readiness probe")` call at startup, on every provider-registry reload, and on stale-cache refreshes — billable on paid embedding providers and a direct violation of the cost-safety invariant the spec states for chat ("billable calls are NEVER run automatically"). Two separately specified embedding-test paths (readiness §6.3 automatic under `READINESS_PROBE`; capability probe §6.6a user-initiated) also left the gate/trigger model ambiguous.

**Decision (product owner, 2026-06-06):** **(1) The automatic readiness check is handshake-only.** `probe_embedding()` never calls `embed()`: it verifies only free signals — a selection exists, its provider's client exists and its reachability handshake succeeded in the same batch, the client has an embedding surface, and (where discovery is supported) the selected model is listed. That is the new meaning of `embedding_reachable`. The cost-safety invariant in `02_LLM_CLIENT_PROTOCOL.md` §6.8.2 is extended to cover `embed()` explicitly. **(2) One user-initiated embedding test.** The real `embed("probe")` capability verification lives on a single path — the Settings *Test Embedding* action, also fired when the user changes the embedding selection — under the `PROVIDER_TEST` gate activity, billable exactly as Test Inference and permitted for the same reason: the user asked. (This unifies the duplicate §6.3/§6.6a paths — also resolving review issue SPEC-111.) **(3) Run-start fail-fast probe.** If a starting or resuming run needs embeddings (cosine-graded tasks or semantic terms), the pipeline issues one `embed("probe")` **before any inference begins**, under the already-held `BENCHMARK_RUN` gate (user-initiated via Start/Resume): on failure the run settles `FAILED` immediately with an error naming the embedding pair and the provider's redacted detail — the user never waits through the whole inference phase to discover a broken embedding endpoint at the cosine stage; a `FAILED` run remains resumable and resume repeats the probe. **Accepted gap, stated honestly:** a listed-but-cannot-embed endpoint (e.g. chat-only `llama.cpp` without `--embedding`) passes the automatic check; it is caught by the user-initiated test at configuration time or by the fail-fast probe at Start — never mid-run at the cosine stage, and never by billing the user silently.

**Rationale:** No billability heuristic can distinguish a free local `OPENAI_COMPATIBLE` endpoint from a paid cloud one, so the only safe rule is structural: model compute happens only on user action. The fail-fast probe converts the weaker automatic signal into a hard guarantee exactly where it matters — at the moment the user commits to a run. Resolves review issues SPEC-012 and SPEC-111.

**Affected spec areas:** `11_Services_and_Algorithms/09_READINESS_PROBE.md` (§6.3 rewritten handshake-only; §8 rows; examples 10.1/10.2; RP-02/03/13), `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` (§6.6a — the single user-initiated test, `PROVIDER_TEST` gate, fail-fast cross-reference), `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` (§6.8.2 invariant extended to `embed()`), `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` (§4 embedding fail-fast probe step), `08_Cross_Cutting/08-B_benchmark_state_machine.md` (§8.3 resume re-validation concretized), `06_Settings_Dialog/description.md` (Test Embedding row).

---

### DD-49 — backend/import_export/ is inventoried; composition-root edge cases cite compose.py (2026-06-06)

**Topic:** The edge-case-to-test mapping cited `backend/import_export/` (all EC-IMP-1..13 plus EC-PROV-8/13) and `backend/composition_root/` (EC-M-4/M-8) as proving modules, but neither path existed in the authoritative module inventory — the traceability validator would reject every such story, and the import/export feature (a security-relevant untrusted-input boundary specified in depth in `10_Domain_and_Data/06_IMPORT_FORMATS.md`) had no home module at all.

**Decision:** `backend/import_export/` is added to the module inventory: it parses, validates, previews, and applies the YAML settings and provider-configuration import files and produces the matching exports; exports `ImportExportService` Protocol + `make_import_export_service`; depends on `ruamel.yaml` (safe-load), `backend/domain`, `backend/errors`, the `ProvidersStore`/`AppSettingsStore` Protocols, and `backend/events`; independently test-targeted with a `testing.py` fake; file parsing runs as a blocking `TaskRunner` unit and the apply step writes through the single DB writer (DD-41). The inventory's stratum row and totals are updated (61 → **62** modules; independent-test 52 → **53**). EC-M-4 and EC-M-8 are re-pathed to `compose.py`, the inventory's real composition-root entry. The 14 import-related mapping rows are unchanged and now valid.

**Rationale:** The inventory is the document the traceability gate validates against; a security-relevant feature must have a contract, a fake, and a test home rather than being built ad-hoc inside an unrelated module. Resolves review issue SPEC-013 (the last Critical of the 2026-06-06 review).

**Affected spec areas:** `14_Process_and_Traceability/01_MODULE_INVENTORY.md` (new row; stratum row; totals), `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` (EC-M-4/EC-M-8 paths).

---

### DD-50 — The single-inference gate is lease-owned: try_acquire returns a GateLease; release requires it (2026-06-06)

**Topic:** `InferenceActivityStore.release(activity)` identified the holder only by the activity **enum**, so the sequence *watchdog-release → new same-class acquire → original holder's late `finally`* would silently free the **successor's** gate — letting two inference activities overlap, the one invariant the gate exists to prevent.

**Decision:** Ownership becomes the lease, not the enum. `try_acquire(activity, context)` returns an opaque **`GateLease`** (`activity`, monotonically increasing `lease_id`, `acquired_at`; new frozen DTO in `10/02`) on success and `None` when held (failure stays data, never an exception). `release(lease)` frees the gate **iff** the lease is the current holder; a superseded or foreign lease is a logged no-op. The watchdog arms with the lease it observed and auto-releases by calling `release(that_lease)` — stealing a successor's hold is impossible by construction. All acquire-site documents updated to the lease-returning contract.

**Rationale:** Closes review issue SPEC-016's double-release/stolen-gate race structurally with a one-type, one-parameter delta, preserving both the watchdog's recovery purpose and the gate's data-not-exception failure mode.

**Affected spec areas:** `08_Cross_Cutting/08-E_interfaces_contracts.md` (§13), `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`GateLease`), `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md` (§6.0; test 15), `08_Cross_Cutting/08-I_edge_cases.md` (EC-RUN-12/14), `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md`, `11_Services_and_Algorithms/09_READINESS_PROBE.md`, `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`, `05_Result_Widget/tabs/judge_analysis_tab.md`, `07_Common_Dialogs/generate_analysis_dialog.md`, `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`.

---

### DD-51 — chat_stream is the single chat execution surface; chat is sugar; the non-streaming fallback hides behind the same iterator (2026-06-06)

**Topic:** The authoritative `LLMClient` Protocol (08-E §10) omitted `chat_stream` even though the progress emitter, the ≥1 Hz heartbeat, TTFT capture, and the DD-39 stream-close cancellation all depend on it — and two sentences in `02_LLM_CLIENT_PROTOCOL.md` ("the benchmark inference phase uses `chat`… the only consumer of `chat_stream` is the live-token echo") contradicted the helper specification, the four-context heartbeat contract, and the `ChatChunk` DTO.

**Decision (product owner, 2026-06-06):** Streaming everywhere it is possible — TTFT is only measurable by streaming. `chat_stream(request) -> ChatStream` joins the authoritative Protocol as **the** chat execution surface: a synchronous iterator of `ChatChunk` (content chunks plus ≥ 1 Hz empty-content heartbeat chunks during provider silence, produced by the sub-second per-read timeout) followed by `trailing_response() -> ChatResponse`; the DD-39 abort hook registers around the in-flight stream. **The non-streaming fallback is hidden inside it**: when a provider cannot stream (capability `False` or call-time rejection) the client silently issues a non-streaming request behind the *same* iterator contract — heartbeats while waiting, one full-content chunk, the trailing response — so callers cannot tell except through metrics: the new `ChatResponse.streamed: bool` records the path and `ttft_ms` stays `None` when not genuinely streamed (never fabricated). **No `stream=` parameter** (a modal flag is two behaviours behind one name); instead `chat` remains in the Protocol as required convenience sugar, contractually "consume your own `chat_stream` to completion" — exactly what the `ChatChunk` DTO already stated. Consumers: every user-visible LLM call (benchmark per-task inference, per-task judge, run-analysis generation, `test_inference`) executes through `emit_progress_during(chat_stream(...))`; the log echo additionally consumes the chunks; internal no-progress callers may use the sugar.

**Rationale:** One transport path means progress, TTFT, cancellation, and fallback behave identically everywhere and cannot diverge; the two stray sentences were the only texts in the spec contradicting the design the helper, the heartbeat contract, and the DTO already encoded. Resolves review issue SPEC-017.

**Affected spec areas:** `08_Cross_Cutting/08-E_interfaces_contracts.md` (§10 — `chat` docstring, new `chat_stream`, threading note), `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`ChatResponse.streamed`; `ChatStream` note on §7.6a), `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` (method table, §6.1 Consumers paragraph, §6.2 fallback extended to call-time rejection, §6.4 closing, success contract line).

---

### DD-52 — The accessibility floor is an honestly-stated reduced target; the toolkit's free keyboard traversal is never suppressed (2026-06-06)

**Topic:** The mouse-only product constraint excluded keyboard operability without stating the assistive-workflow consequence; the always-visible focus-ring rule was untestable for momentary buttons (platform-dependent click focus); and Qt's free built-in `Tab`/`Shift+Tab` traversal was neither kept nor banned.

**Decision:** Three rulings. **(1) Honest scope.** The floor states explicitly that it is a deliberately reduced target: WCAG 2.1 AA is adopted for **colour contrast only**, no overall WCAG conformance is claimed, and excluding supported keyboard operability excludes keyboard-dependent assistive workflows — an accepted consequence of the recorded product decision, not an oversight. **(2) Never suppress the free behaviour.** Mirroring the Enter/Esc modal-default precedent (D-R-07), Qt's built-in focus traversal is permitted and never actively suppressed (no `NoFocus` policy on interactive controls, no traversal-disabling code); it remains an unsupported, untested path — the mouse is the only supported and verified input. **(3) Testable focus rule.** The never-suppressed focus-ring requirement and its release check are scoped to **focus-retaining input controls** (text inputs, combos, spinners, lists, tables); momentary action controls are excluded from the requirement and the check.

**Rationale:** Honesty over implication (a future reader must see the cut was deliberate); zero-cost retention of what the toolkit gives free, fully consistent with "no custom shortcuts"; and a verification that can actually pass on every platform. Resolves review issue SPEC-020.

**Affected spec areas:** `12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` (§4 two new statements; §5 ring-rule scope; §10 verification row), `00_Foundation/05_CONSTRAINTS.md` (mouse-only constraint — non-suppression sentence).

---

### DD-53 — Additive structural schema steps within a major version; no data migration or conversion, ever (2026-06-06)

**Topic:** The versioning policy forbade any schema change within a major version while performing no migrations, so adding a single persisted column forced a destructive MAJOR release whose "fresh start" abandons every user's benchmark run history — the application's core data — and contradicted `08-N`'s "schema evolves additively only within a major."

**Decision (product owner, 2026-06-06):** Within one major lineage, exactly **three structural change kinds** are legal in a MINOR version: `ALTER TABLE … ADD COLUMN` (nullable or with a `DEFAULT`), new `CREATE TABLE`/`CREATE INDEX`, and new `app_settings` keys. Each step increments the integer `schema_version` and ships as one idempotent single-transaction statement; startup brings an older same-major database forward by applying the ordered steps, then continues. **No data migration or conversion exists, ever** (the owner's explicit boundary): no `UPDATE`, no backfill, no value transformation, no rewriting of existing rows — existing rows merely acquire the new column's `NULL`/default. A newer-than-app or cross-major version at startup remains a hard error; anything beyond additive (rename, drop, retype, or any change whose correctness would require touching existing rows) remains a MAJOR version with a fresh start. A mid-step failure leaves prior committed steps applied and halts naming the failed step.

**Rationale:** User run history survives normal product evolution at near-zero framework cost — additive structural statements carry none of the maintenance and correctness burden the original no-migration decision rightly avoided, because they never touch stored data. Harmonizes the versioning policy with `08-N`. Resolves review issue SPEC-021.

**Affected spec areas:** `13_Distribution_and_Release/06_VERSIONING_POLICY.md` (§2, §3 minor rule, §8 update note), `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` (§8 startup sequence + closing note), `00_Foundation/05_CONSTRAINTS.md` (constraint renamed and reworded), `12_Quality_and_NFRs/04_ERROR_RECOVERY.md` (§7 + summary rows), `08_Cross_Cutting/08-N_implementation_pointers.md`, `08_Cross_Cutting/08-I_edge_cases.md` (EC-PERSIST-1)., `08_Cross_Cutting/08-O_persistence_schema.md` (§6), `08_Cross_Cutting/08-M_app_lifecycle.md`, `10_Domain_and_Data/01_DOMAIN_MODEL.md`, `06_Settings_Dialog/description.md`

---

### DD-54 — CSV exports are verbatim: no formula-injection mangling (trusted-content policy) (2026-06-06)

**Topic:** Whether the CSV serializer defends against spreadsheet formula injection (cells beginning with `=`, `+`, `-`, `@`).

**Decision (product owner, 2026-06-06):** Exported CSV cells are written **verbatim**. There is no neutralizing apostrophe prefix, no defensive quoting beyond RFC 4180 well-formedness, and no content alteration of any kind. The previously specified "formula-injection guard" (quote-if-first-char-in-`=+-@`) is removed — it was also technically ineffective, since RFC 4180 quoting does not change how a spreadsheet interprets unquoted cell content. The export threat model is recorded as a security-model non-goal: exports carry the application's own database content — the user's own task data and the responses of models the user explicitly configured and ran — and are trusted local content by design. Byte-for-byte cell fidelity is the export contract.

**Rationale:** The exports are the user's own data on the user's own machine, produced from the application's own database. Mangling content to defend the user from their own files breaks fidelity for downstream parsers; the one real mitigation (apostrophe prefix) alters data, and a placebo guard that claims safety without providing it is worse than an honest verbatim contract. Resolves review issue SPEC-024.

**Affected spec areas:** `10_Domain_and_Data/05_EXPORT_FORMATS.md` (§3.1 verbatim rule; EC-EXP-1 rewritten), `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md` (§1 purpose bullet; §6.3 step 3; §10.3 edge case rewritten; flow-diagram node), `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` (EC-EXP-1 row — verbatim round-trip invariant), `12_Quality_and_NFRs/02_SECURITY_MODEL.md` (§9 new non-goal bullet).

---

### DD-55 — Import/export is same-user data portability; import validation is correctness-only (2026-06-06)

**Topic:** The threat model of the settings / provider-configuration import flow — whether imported files are an untrusted-input security boundary.

**Decision (product owner, 2026-06-06):** Import/export exists for one purpose: **same-user backup and restore** — surviving an OS reinstall, an application reinstall, or a move to another device. An import file is treated as the user's own previously exported data; the realistic population of import files is files this application wrote. Import validation checks **correctness only**: schema shape (`kind`, `schema_version`), required fields, and value validity (including that a non-empty `base_url` is a syntactically valid URL — the same rule the provider-edit dialog applies). It is not a security control; "malicious import file" defense is an explicit security-model non-goal. YAML safe-load parsing is retained as ordinary engineering hygiene, not as a threat mitigation. The security model's "contacts no endpoint the user did not configure" guarantee is worded to include endpoints restored from the user's own imported file via the explicit preview-confirmed flow.

**Rationale:** Nobody downloads provider configurations from the internet for a local benchmarking tool; treating the import path as a hostile boundary would buy allowlists and warnings for a near-nonexistent attacker at real UX and machinery cost. The preview-before-apply flow already gives the user full visibility and explicit confirmation. The previously false toolchain claim ("no untrusted-input boundary exists here") is replaced with an accurate statement rather than inverted into security machinery. Resolves review issue SPEC-025.

**Affected spec areas:** `10_Domain_and_Data/06_IMPORT_FORMATS.md` (§1 purpose paragraph; §6.3 base-URL value-validity row), `12_Quality_and_NFRs/02_SECURITY_MODEL.md` (§7 base-URL bullet; §9 new non-goal), `16_Engineering_Standards/02_TOOLCHAIN.md` (pydantic ban rationale corrected), `14_Process_and_Traceability/01_MODULE_INVENTORY.md` (`backend/import_export/` boundary wording).

---

### DD-56 — Provider wire stub: transport-level adapter testing with pytest-httpserver (2026-06-06)

**Topic:** How the real provider adapters (`LLMClient` implementations) are tested deterministically offline, and what backs the R-008 "integration-test layer per provider" mitigation.

**Decision (product owner, 2026-06-06):** Provider adapters are tested at the **transport level**: the real adapter and the real provider SDK make genuine HTTP calls to a local `pytest-httpserver` stub on `127.0.0.1`, reached via the base-URL override that every supported SDK exposes. Tests register canned wire payloads — streaming SSE chunk sequences, completion bodies, usage payloads, and an error matrix (401/404/429/500, context-length error bodies, malformed/truncated chunks, mid-stream disconnect, missing usage, non-streaming rejection for the DD-51 fallback) — and assert the adapter's observable contract (taxonomy errors, `ChatResponse`/`ChatChunk` values, `streamed`, `ttft_ms`, usage). The `LLMClient` contract suite's real leg runs against this stub; no test contacts a live model and CI is fully offline. The stub fixtures live under `tests/integration/provider_stub/`; payload shapes are pinned per provider dialect and refreshed from captured traffic when an SDK is deliberately bumped. `pytest-httpserver` joins the dev dependencies. Each provider module's `testing.py` fake remains the collaborator double for *other* modules and never stands in for the adapter in the adapter's own tests. (Evaluated and not chosen: StacklokLabs MockLLM — no error simulation, no Gemini endpoint, uncontrolled wire shapes, stale near-single-maintainer project; in-process httpx interception (respx) — couples tests to SDK-internal HTTP client choice and bypasses the real transport path.)

**Rationale:** The previous text was self-contradictory (the contract suite mandated a real leg that needed a live model, while §7 circularly "tested adapters against the fake") and left R-008 — a High-probability risk under the latest-versions policy — with an unbacked mitigation. A wire stub exercises exactly the code that breaks when an SDK changes (streaming parse, error translation, TTFT/usage capture) with exact, deterministic assertions. Resolves review issue SPEC-026.

**Affected spec areas:** `16_Engineering_Standards/07_TESTING_STANDARD.md` (§6a real-leg bullet; §7 adapter bullet rewritten; new §7a; ToC), `16_Engineering_Standards/02_TOOLCHAIN.md` (dev-dependency row + pyproject snippet), `15_Risks_and_Open_Questions/01_RISK_REGISTER.md` (R-008 mitigation bullet).

---

### DD-57 — Run Drift Detector scope: environment availability of the frozen configuration only (2026-06-06)

**Topic:** What "drift" means for the Resume flow — and confirming that the embedding selection is frozen into the run snapshot.

**Decision (product owner, 2026-06-06):** A resumed run uses **only its frozen snapshot** — the settings captured at creation (user-saved values plus any Advanced-Options overrides), the frozen provider copies, the frozen test/judge models, and the frozen embedding `(provider, model)` pair. Live configuration *differences* are therefore invisible to the run and are **not drift**. The Run Drift Detector checks one thing: **whether the current environment can still satisfy the frozen configuration** — provider removed/disabled/unreachable; a frozen model no longer served; the frozen `api_key_raw` environment variable no longer set or empty (new kind `PROVIDER_ENV_VAR_MISSING`, BLOCKING); the frozen embedding pair's provider unavailable (`EMBEDDING_NOW_UNREACHABLE`) or its model no longer served (new kind `EMBEDDING_MODEL_UNAVAILABLE`, BLOCKING). Retired kinds: `PROVIDER_SECRET_CHANGED` (live field diffs don't affect a resume through the frozen provider copy), `EMBEDDING_MODEL_CHANGED` and `EMBEDDING_NOW_UNCONFIGURED` (the live selection is never consulted), `SETTINGS_DEFAULT_DIVERGED` and the whole `INFO` severity (settings differences are not drift; the dialog's static "Settings note" already explains the frozen-settings rule). The detector now runs four availability checks; live embedding selection is removed from its inputs and the read-only process environment added. Also ratified: the embedding pair is frozen at run start (header `embedding_provider_name`/`embedding_model_name` + `EMBEDDING`-role model row) and never re-resolved mid-run or on resume — the three residual "resolved live at use time" passages (08-G, 08-O, 08-E) are corrected to the two-phase story (live outside a run; frozen within one).

**Rationale:** The user's principle: "Run use only the frozen settings… Drift detection should focus on the changes of the environment." Difference-warnings created noise about things that cannot affect the resumed run, while the one environmental failure users actually hit (an API-key env var gone after a relaunch) was unchecked. Resolves review issue SPEC-040.

**Affected spec areas:** `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md` (purpose, inputs, enums, checks 1/4 rewritten, check 5 deleted, dialog-surfacing, examples, tests), `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.9 (DriftKind/DriftSeverity members + tombstone comment), `07_Common_Dialogs/resume_summary_dialog.md` (§5 severity table, Fix-in-Settings kinds), `07_Common_Dialogs/mockup.html` (INFO row removed; note), `03_Resume_Benchmark_Widget/description.md` (EC-RB-4), `03_Resume_Benchmark_Widget/mockup.html` (drift rows + note), `08_Cross_Cutting/08-G_feature_flags.md`, `08_Cross_Cutting/08-O_persistence_schema.md`, `08_Cross_Cutting/08-E_interfaces_contracts.md` (embedding two-phase resolution wording).

---

### DD-58 — Run-mode renaming: Synthetic / Task / Graded Benchmark (2026-06-06)

**Topic:** The canonical product names of the three run modes, superseding both the original brief's names ("Task Performance", "Comprehensive Evaluation") and the prior spec names ("System Performance", "Speed", "Full Grading").

**Decision (product owner, 2026-06-06):** The three run modes are renamed throughout the specification, mockups, and stored values:

| Old display | New display | Old enum/stored | New enum/stored | Selector caption |
|---|---|---|---|---|
| System Performance | **Synthetic Benchmark** | `SYSTEM_PERFORMANCE` / `system_performance` | `SYNTHETIC` / `synthetic` | `Synthetic prompt sizes; measures throughput` |
| Speed | **Task Benchmark** | `SPEED` / `speed` | `TASKS` / `tasks` | `Your task files; throughput only; no grading` |
| Full Grading | **Graded Benchmark** | `FULL_GRADING` / `full_grading` | `GRADED` / `graded` | `Your task files; full grading pipeline` |

The enum members and DB-stored strings change with the display names (pre-release; no data-migration concern — DD-53 untouched). The `mode_specifics` files are renamed `synthetic.md` / `tasks.md` / `graded.md`. UI display order and the default selection (`SYNTHETIC`) are unchanged. Generic uses of the word "speed" (tokens/sec prose, the `SPEED_VS_QUALITY_SCATTER` chart kind, the "Speed sweep" example run name) are deliberately untouched. Historical entries in this decision log retain the old vocabulary as dated records.

**Rationale:** "System Performance" vs "Speed" did not communicate the actual distinction (synthetic prompts vs the user's task files), and the brief's names were never adopted. The new triple makes the prompt-source and grading distinctions explicit in the names themselves. Resolves review issue SPEC-041.

**Affected spec areas:** repo-wide rename — 71 files across `00_Foundation/`, `01_Main_Window/`–`07_Common_Dialogs/`, `08_Cross_Cutting/` (08-B, 08-C, 08-G, 08-H, 08-I, 08-J, 08-O, 08-P, 08-Q, 08-R), `09_Task_Editor/`, `10_Domain_and_Data/` (RunMode enum, persistence CHECK constraint, examples), `11_Services_and_Algorithms/`, `12_Quality_and_NFRs/`, `14_Process_and_Traceability/`, all widget mockup HTML files, and `02_New_Benchmark_Widget/mode_specifics/{synthetic,tasks,graded}.md` (renamed).

---

### DD-59 — User-facing rename: "Judge Analysis" → "Run Analysis" (2026-06-06)

**Topic:** The user-facing name of the run-level narrative tab and its toggle.

**Decision (product owner, 2026-06-06):** Every user-facing surface says **"Run Analysis"**: the Result-widget tab (file renamed `run_analysis_tab.md`), the toggle label "Generate run analysis" (help text notes the configured judge model authors it), the glossary terms (stale "Judge Summary Service" entry corrected to the Run Analysis Service). Internal identifiers are unchanged: the settings key `feature.judge_run_analysis_enabled`, the DTO field `judge_analysis_enabled`, and the `InferenceActivity.JUDGE_ANALYSIS` gate class — they are not user-facing and remain accurate (a judge-role model generates the narrative). The view-model tab id and slice method follow the tab module rename (`"run_analysis"`, `apply_run_analysis`).

**Rationale:** The tab exists in every mode, including Synthetic/Task Benchmark runs that never run a per-task judge; "Judge Analysis" implied grading verdicts those runs do not have. The service, DTO field, and dialog were already named "run analysis" — this finishes the migration. Resolves review issue SPEC-044.

**Affected spec areas:** 38-file user-facing sweep + `05_Result_Widget/tabs/run_analysis_tab.md` (renamed), `00_Foundation/02_GLOSSARY.md` (two entries), `05_Result_Widget/implementation_structure.md` (tab id + slice method), `02_New_Benchmark_Widget/description.md` (toggle help text).

---

### DD-60 — Throughput is never silently empty: request usage, flagged char/4 estimate fallback (2026-06-06)

**Topic:** The headline throughput metric (`tokens_per_second`) going `None` for backends that do not report token usage.

**Decision (product owner, 2026-06-06):** Two-part fix. (1) The `OPENAI_COMPATIBLE` request `translate()` always sets `stream_options = {"include_usage": true}`, so a modern backend (Ollama 2024-08+, LM Studio, llama.cpp) returns usage. (2) When the provider still reports no usage, the inference phase computes an **estimated** `tokens_per_second` from `ceil(len(raw_response)/4)` and sets the new `BenchmarkResult.tokens_estimated = True`; the provider-grade `completion_tokens` field is left `None` (never polluted with a tokenizer guess, preserving billing/context consistency). The estimate is surfaced with an `≈`/`~` marker on the Details TPS cell, the Summary Avg-TPS group, the `AVG_TPS_PER_MODEL` chart group, and the Details CSV export. `tokens_per_second` is therefore never silently `None` for a completed inference in a throughput mode.

**Rationale:** Throughput is the headline metric for the Synthetic and Task Benchmark modes; a silently-empty chart for a non-reporting backend is a product failure. Requesting usage fixes the common case; the flagged estimate guarantees a value while keeping it clearly distinguishable from provider-measured counts. Resolves review issue SPEC-047. The live in-flight counter already had this char/4 fallback (§6.5a); this extends the same honest basis to the persisted metric.

**Affected spec areas:** `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` (§6.5 — include_usage + estimate computation), `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` (§3 timing/throughput outputs note), `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (`BenchmarkResult` + `ResultPatch` gain `tokens_estimated: bool`), `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` (`tokens_estimated` column, additive — DD-53-safe), `05_Result_Widget/tabs/details_tab.md` & `summary_tab.md` (`≈` marker), `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md` (`AVG_TPS_PER_MODEL` estimate flag), `10_Domain_and_Data/05_EXPORT_FORMATS.md` (Details TPS `~` marker), `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md` (§7 Ollama usage note).

---

### DD-61 — Inference temperature defaults to 0.0 for comparable runs (2026-06-06)

**Decision (product owner, 2026-06-06):** Q1/SPEC-049. `benchmark.temperature` default changed from blank to **`0.0`** so every model in a run is compared at the same low-variance setting. The user may set any `≥0.0` value (passed verbatim, not clamped — D-R-04 preserved) or blank it to use each provider's own default, in which case models may run at different effective temperatures and the run is flagged **not directly comparable** in the New Benchmark widget and Run Summary. Judge stays pinned at 0.0.

**Affected spec areas:** `08_Cross_Cutting/08-G_feature_flags.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (ChatRequest note), `06_Settings_Dialog/description.md`, `02_New_Benchmark_Widget/description.md`.

---

### DD-62 — Force-judge defaults OFF; sanity-failed responses never reach the judge (2026-06-06)

**Decision (product owner, 2026-06-06):** Q2/SPEC-050. `eval.force_judge_on_prior_failure` default flipped `true`→**`false`**: by default a deterministic keyword `FAIL` is final and no judge call is spent (the cheap phases decide); the user opts into judge-as-authoritative-gate. **Independently of the flag, a response that fails the sanity pre-check (empty / error-marker) is never sent to the judge** — nothing to grade. Sanity floor rationale reworded (only empty/1-char trips it; "42" passes).

**Affected spec areas:** `08_Cross_Cutting/08-G_feature_flags.md`, `08_Cross_Cutting/08-P_judge_protocol.md` (§judge-flag, §cascade), `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` (§6.2 sanity, §6.6 combination + config row + worked example).

---

### DD-63 — Per-model cosine-coverage flag for uneven embedding coverage (2026-06-06)

**Decision (product owner, 2026-06-06):** Q3/SPEC-051. New overridable `eval.min_cosine_coverage` (default 0.8). When a model's cosine coverage (scored ÷ cosine-eligible completed rows) falls below it while a peer meets it, the model's mean-cosine is flagged ⚠ partial-coverage in the Summary tab and AVG_COSINE_BY_MODEL chart, surfacing the comparison bias from intermittent embedding failures. Grading unchanged.

**Affected spec areas:** `08_Cross_Cutting/08-G_feature_flags.md`, `05_Result_Widget/tabs/summary_tab.md`, `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`.

---

### DD-64 — Warmup uses the normal adaptive budget; any response = provider liveness (2026-06-06)

**Decision (product owner, 2026-06-06):** Q4/SPEC-052. The model-switch warmup is an ordinary lightweight inference **sized by the role=INFERENCE adaptive ladder** (not a separate fixed deadline), so a legitimate slow cold-load gets escalation headroom and a finite max. Its outcome feeds the **circuit breaker**, not model exclusion: any response (incl. 4xx) = provider alive = neutral; a warmup that exhausts the ladder without responding, or fails with a transport error, is a provider failure — consecutive such failures trip the breaker (early detection of a wedged/OOM/looping/stuck-unloading local provider preserved exactly). Per owner: no separate budget; warmup judged like any call.

**Affected spec areas:** `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` (§warmup bullet + §6.5 paragraph), `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md` (§1.2 warmup note), `00_Foundation/02_GLOSSARY.md` (Adaptive Timeout Role).

---

### DD-65 — Run-analysis gets its own RUN_ANALYSIS adaptive bucket (2026-06-06)

**Decision (product owner, 2026-06-06):** Q5/SPEC-053. New `AdaptiveTimeoutRole.RUN_ANALYSIS` — an independent bucket for the user-initiated run-analysis call, with its own last-known-good (init min, promoted by its own successes) and its own in-run counter, parameterised by the same `eval.judge_timeout_*` keys. It never inherits the per-task JUDGE bucket's (often maxed) LKG, so the longer analysis prompt escalates its own full ladder min→max with real headroom. Supersedes BOTH prior contradictory models (07's "run at max directly" and 22/05's "shared JUDGE bucket"). The 10-min JUDGE_ANALYSIS gate watchdog remains the outer bound (global early-detection caveat honored: finite max + watchdog).

**Affected spec areas:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (enum + note), `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md` (scope table, LKG row, boundary semantics, §6.x, worked example, T-20/T-22), `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md` (§ + example 10.6 + RA-22/24/25), `11_Services_and_Algorithms/05_JUDGE_PROTOCOL.md` (§adaptive), `08_Cross_Cutting/08-G_feature_flags.md` (judge_timeout interaction), `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-I_edge_cases.md`, `12_Quality_and_NFRs/04_ERROR_RECOVERY.md`, `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md`, `00_Foundation/02_GLOSSARY.md`.

---

### DD-66 — Stage-preserving retry — a judge-only failure re-runs only the judge (2026-06-06)

**Decision (product owner, 2026-06-06):** Q2/SPEC-056. A retry resumes a result **from its failed stage** instead of always re-running the whole task. A `FAILED_JUDGE_TIMEOUT` row (and a judge-stage `ERRORED` row with a response) is reset to `AWAITING_JUDGE_CHECK`, preserving the inference response, timing/token metrics, keyword verdict, and cosine score; the pipeline re-runs **only the judge** against the preserved `sanitized_response` (same text → consistent with the recorded keyword/cosine outcomes; no wasted re-inference). Every other retryable status (`FAILED_INFERENCE`/`PROVIDER`/`TIMEOUT`, response-less `ERRORED`, in-pipeline rows) full-resets to `PENDING`. New `ResultsStore.reset_results_for_retry`. A crash before the re-judge falls back to a whole-task re-run via the startup sweep (which resets `AWAITING_*`→`PENDING`).

**Affected spec areas:** `08_Cross_Cutting/08-E_interfaces_contracts.md` (`ResultsStore.reset_results_for_retry` + gateway), `07_Common_Dialogs/retry_selection_dialog.md` (§13), `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` (resume-from-stage), `12_Quality_and_NFRs/04_ERROR_RECOVERY.md` (per-role recovery), `08_Cross_Cutting/08-I_edge_cases.md` (EC-PROV-4d).

---

### DD-67 — Configurable max-output-tokens, default 4096; judge cap raised from 512 (2026-06-06)

**Decision (product owner, 2026-06-06):** Q3/SPEC-057. `ChatRequest.max_output_tokens` added (default 4096), always sent (Anthropic mandates `max_tokens`). New per-run-overridable settings `benchmark.max_output_tokens` (model under test, default 4096) and `eval.judge_max_completion_tokens` (judge, default 4096 — raised from the former fixed 512 that trapped reasoning judges in a truncated-before-JSON malformed loop). Per-provider mapping: OpenAI `max_tokens`/`max_completion_tokens`, Anthropic `max_tokens` (required), Gemini `max_output_tokens`. Judge malformed-retry now surfaces a **budget-exhausted** diagnostic ('raise the cap or pick a non-reasoning judge') instead of looping to ERRORED.

**Affected spec areas:** `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` (ChatRequest + field note), `08_Cross_Cutting/08-G_feature_flags.md` (two keys), `08_Cross_Cutting/08-P_judge_protocol.md` (§judge-call table, §9.2 diagnostic, test 13), `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` (per-provider mapping row), `02_New_Benchmark_Widget/description.md` (Advanced Options), `06_Settings_Dialog/description.md` (Advanced).

---

### DD-68 — golden_answer is optional, not required (2026-06-06)

**Decision (product owner, 2026-06-06):** Q4/SPEC-090. `golden_answer` is **optional** in the YAML task format (matching the nullable DTO/DB and synthetic tasks): an empty/absent value is a **soft warning**, never a hard error. In a Graded run a task with no golden answer skips the cosine phase and the judge grades on criteria/keywords only; Task/Synthetic runs never read it. One consistent rule across YAML, DTO, DB, and all three modes — the same task file works in any mode.

**Affected spec areas:** `10_Domain_and_Data/04_YAML_TASK_FORMAT.md` (field table, long-string rule, validation row).

---

### DD-69 — macOS ships arm64 only — Intel (x86-64) dropped (2026-06-06)

**Decision (product owner, 2026-06-06):** Q8/SPEC-097. The macOS release artifact is a single **arm64** `.dmg`; Intel (x86-64) macOS is no longer supported or built (Apple has ended Intel support in current macOS, and going forward only arm64 is targeted). CI builds arm64 only. Resolves the undecided universal-vs-per-arch question and the matrix/claim mismatch.

**Affected spec areas:** `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md` (matrix, CPU-arch table, notes), `16_Engineering_Standards/08_CICD_AND_PACKAGING.md` (build matrix).

---

### DD-70 — Embedding consecutive-failure short-circuit caps stalled-cosine dead time (2026-06-06)

**Decision (product owner, 2026-06-06):** Q5/SPEC-100. New `eval.embedding_consecutive_failures_to_skip` (default 3): after that many consecutive embedding failures/timeouts in a run, the cosine phase is **skipped run-wide** for the remaining tasks (a one-time Progress/Run-Analysis notice is shown), bounding worst-case dead time from `N×30s` to `K×30s`. The run is not failed — keyword/judge still grade. No adaptive ladder/exclusion for embedding (unchanged); this is a run-level circuit-stop for the cosine phase only.

**Affected spec areas:** `11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` (§ + EC), `08_Cross_Cutting/08-G_feature_flags.md` (new key).

---

### DD-71 — Circuit-breaker PROBING uses a lightweight liveness probe, not a full task (2026-06-06)

**Decision (product owner, 2026-06-06):** Q7/SPEC-108. The breaker's post-cooldown PROBING probe is the single-attempt, single-short-budget warmup-style call (DD-64), **not** a full benchmark task on the retry-laddered inference path. A still-down provider's re-trip is decided in seconds rather than the minutes a `(1+retry_count)×`-escalating real task would cost while other tasks wait; on probe success the next real task proceeds.

**Affected spec areas:** `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` (§intro, §6.x, state table).

---

## 3. Decision index by spec area

| Spec area | Decisions |
|---|---|
| Main window and shell | DD-03, DD-04, DD-05, DD-09, DD-20, DD-23, DD-24, DD-25 |
| New Benchmark widget | DD-02, DD-09, DD-16, DD-17, DD-18, DD-19, DD-28, DD-30, DD-47 |
| Resume Benchmark widget | DD-04, DD-25 |
| Progress widget | DD-04, DD-11, DD-16, DD-17, DD-25, DD-32, DD-39 |
| Result widget | DD-01, DD-04, DD-08, DD-14, DD-15, DD-26, DD-27, DD-30, DD-31 |
| Settings dialog | DD-03, DD-05, DD-07, DD-10, DD-11, DD-12, DD-13, DD-21, DD-30, DD-32, DD-45, DD-48 |
| Common dialogs | DD-06, DD-12, DD-16, DD-18, DD-19, DD-21, DD-30, DD-31, DD-32 |
| Task Editor | DD-09, DD-24, DD-45, DD-46 |
| Cross-cutting and domain | DD-01, DD-02, DD-11, DD-22, DD-27, DD-28, DD-29, DD-30, DD-31, DD-32, DD-34, DD-36, DD-37, DD-38, DD-39, DD-40, DD-41, DD-42, DD-43, DD-44, DD-45, DD-46, DD-47, DD-48, DD-49, DD-55, DD-57, DD-58, DD-59 |
| Evaluation and judge | DD-02, DD-08, DD-18, DD-27, DD-30, DD-32, DD-34, DD-45, DD-46, DD-48 |
| Quality, distribution, engineering | DD-11, DD-22, DD-23, DD-28, DD-29, DD-31, DD-32, DD-35, DD-36, DD-37, DD-43, DD-44, DD-49, DD-52, DD-53, DD-54, DD-56, DD-60, DD-61, DD-62, DD-63, DD-64, DD-65, DD-66, DD-67, DD-68, DD-69, DD-70, DD-71 |
| Security and redaction | DD-31 |
| Provider identity and naming | DD-33 |
| Adaptive timeout and stability | DD-34 |
| Concurrency model and open-question closeouts | DD-37, DD-38, DD-39, DD-40, DD-41, DD-42, DD-43, DD-44, DD-45, DD-46, DD-47, DD-48, DD-49, DD-50, DD-51 |
