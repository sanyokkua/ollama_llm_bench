# Glossary

**Status:** Draft
**Owner:** architect
**Audience:** all
**Last Updated:** 2026-06-06
**Cross-references:** 08_Cross_Cutting/08-E_interfaces_contracts.md; 10_Domain_and_Data/01_DOMAIN_MODEL.md; 00_Foundation/01_README.md

This glossary is the authoritative vocabulary for the Ollama LLM Bench specification. It defines every UI primitive, layout primitive, visual-feedback state, application-service role, lifecycle/threading term, persistence term, domain term, semantic colour, and severity level used anywhere in the specification set. Wherever another document uses one of these names, the meaning defined here applies as a contract: the named thing must exhibit exactly the behaviour described. The application is a Python 3.13 desktop tool built on PySide6 (Qt Widgets); service-role definitions name that stack where it clarifies intent, but no implementation code appears here. Read this file before any other specification document.

---

## Table of Contents

1. [UI Primitives](#1-ui-primitives)
2. [Layout Primitives](#2-layout-primitives)
3. [Visual Feedback States](#3-visual-feedback-states)
4. [Application Service Roles](#4-application-service-roles)
5. [Lifecycle and Threading Terms](#5-lifecycle-and-threading-terms)
6. [Persistence Vocabulary](#6-persistence-vocabulary)
7. [Domain Terminology](#7-domain-terminology)
8. [Semantic Colours](#8-semantic-colours)
9. [Severity Levels](#9-severity-levels)

---

## 1. UI Primitives

This section defines the interactive controls and window-level primitives the application is built from. Each maps to a concrete Qt Widgets element; the specification names the primitive, the implementation provides the widget.

**Application.** The running Ollama LLM Bench process the user interacts with. It owns exactly one [Main Window](#main-window) and may spawn [Modal Dialogs](#modal-dialog) and [Modeless Dialogs](#modeless-dialog). The application is single-window, single-user, single-machine, and emits no telemetry.

**Main Window.** <a id="main-window"></a>The single top-level frame of the application. It persists for the whole session and contains the [Menu Bar](#menu-bar), the [Workspace Region](#workspace-region), and the [Status Bar](#status-bar). There is never more than one Main Window.

**Menu Bar.** <a id="menu-bar"></a>The horizontal strip at the very top of the [Main Window](#main-window). It contains the [Workspace](#workspace) switcher, the Settings and About entries, and (while a benchmark run is active) the [Running Pill](#running-pill). It is always rendered inside the window on every platform, including macOS where the global system menu bar is bypassed. The Menu Bar is deliberately minimal: there are no File / Edit / View / Help menus.

**Workspace Region.** <a id="workspace-region"></a>The portion of the [Main Window](#main-window) between the [Menu Bar](#menu-bar) and the [Status Bar](#status-bar). Whatever the active [Workspace](#workspace) renders is placed here. Swapping workspaces replaces the entire contents of this region.

**Status Bar.** <a id="status-bar"></a>The horizontal strip at the bottom of the [Main Window](#main-window). It shows the application health [Dot](#dot), transient [Toast](#toast) messages, and the active workspace's contextual status text.

**Modal Dialog.** <a id="modal-dialog"></a>A child window that blocks input to its parent until it is dismissed. Used for the Settings dialog, confirmation prompts, the About dialog, and similar focus-demanding flows. Note: "modal" here is the windowing term; do not confuse it with "mode" in the sense of a benchmark [Run Mode](#run-mode).

**Modeless Dialog.** <a id="modeless-dialog"></a>A child window that does not block its parent; the user can keep interacting with the [Main Window](#main-window) while it is open. Used for detached chart views.

**Button.** A clickable action trigger. A button carries one of several visual styles: *primary* (the default action of a surface), *secondary* (an ordinary action), *destructive* (a dangerous action such as Delete), *icon-only* (see [Icon Button](#icon-button)), or *muted* (a de-emphasised action). Maps to a Qt push button.

**Icon Button.** <a id="icon-button"></a>A compact, roughly square [Button](#button) rendered as a single glyph (for example a pencil, lightning bolt, refresh arrow, or trash can). An Icon Button always carries a hover [Tooltip](#tooltip) describing its action, because the glyph alone is not self-explanatory. Maps to a Qt tool button.

**Toggle / Checkbox.** A two-state control that is either on or off. Maps to a Qt checkbox.

**Tri-state Checkbox.** A checkbox with three states: on, off, and mixed. Used for "select all in group" controls where some but not all children are selected; the mixed state communicates partial selection.

**Radio List.** A one-of-many selector in which exactly one option is chosen at a time. Rendered either as traditional radio buttons or as card-style rows. The benchmark [Run Mode](#run-mode) selector is a Radio List.

**Segmented Control.** A one-of-many selector rendered as a row of connected pill buttons. Used for the [Workspace](#workspace) switcher in the [Menu Bar](#menu-bar) and for per-field source toggles (for example switching a secret between a plain value and an environment-variable reference).

**Single-line Input.** One row of editable text. May be masked for passwords and secret values. Maps to a Qt line edit.

**Multi-line Input.** An editable text area, either auto-growing or fixed-height. May be plain-text or code-styled (monospace) for prompts, golden answers, and YAML. Maps to a Qt text-edit widget.

**Number Stepper.** A numeric input with increment and decrement controls and an enforced minimum/maximum range. Maps to a Qt spin box.

**Dropdown.** A closed list that opens on click to reveal a set of selectable items. May be *editable*, combining free-text entry with suggestions. Maps to a Qt combo box.

**Multi-select Dropdown.** A [Dropdown](#dropdown) in which each item carries a checkbox, allowing several items to be selected at once. Used for column-visibility and filter controls.

**Chip Input.** A multi-value text input where each committed value renders as a small removable chip. Typing a comma or clicking the inline "Add" button commits the current text as a chip. Used wherever a list of short string values is entered (for example required keyword terms).

**List View.** A vertical, scrollable list of homogeneous rows. Supports single or multiple selection. Maps to a Qt list view.

**Table View.** A tabular display with sortable column headers and per-column filtering. Used for the run list, the Summary tab, and the Details tab. Maps to a Qt table view backed by a Model/View model.

**Tree View.** A hierarchical list with expandable and collapsible nodes. Reserved for completeness; not used by any current surface.

**File Picker / Folder Picker / Save Picker.** OS-provided [Modal Dialogs](#modal-dialog) for, respectively, choosing one or more existing files, choosing a folder, and choosing a destination path to write a new file. The application requests these from the host OS rather than drawing its own.

---

## 2. Layout Primitives

This section defines the non-interactive containers that arrange [UI Primitives](#1-ui-primitives) on screen.

**Workspace.** <a id="workspace"></a>A swappable top-level layout that fills the [Workspace Region](#workspace-region). Exactly one workspace is active at a time. The application defines two: the **Benchmark** workspace (configure, run, and review benchmark runs across three panels) and the **Task Editor** workspace (a full-window editor for benchmark task YAML files). The active workspace is persisted under the setting `ui.active_workspace` and restored on the next launch. Do not confuse "workspace" with "window"; both workspaces live inside the single [Main Window](#main-window).

**Panel.** A bounded rectangular region inside a [Workspace](#workspace) that holds widgets. The Benchmark workspace is composed of a left management panel, a centre progress panel, and a right results panel.

**Splitter.** A horizontal or vertical container whose children are [Panels](#panel) separated by user-draggable dividers. Each child enforces a minimum size so a panel cannot be collapsed below usability.

**Tab Strip.** A horizontal row of tab labels. Clicking a label activates the corresponding [Tab Body](#tab-body).

**Tab Body.** <a id="tab-body"></a>The content area beneath a [Tab Strip](#tab-strip) that renders whichever tab is currently active.

**Section.** A vertically stacked, optionally labelled group of related fields within a [Panel](#panel). A section may be *collapsible*, carrying a header with an expand/collapse chevron.

**Group Box.** A labelled, bordered [Section](#section) with a title. The terms "group box" and "labelled section" are synonymous.

**Form.** A vertical list of [Field Rows](#field-row). A Form may be scrollable when it is taller than its container.

**Field Row.** <a id="field-row"></a>The smallest reusable unit of a [Form](#form): one labelled input plus an optional help icon, an optional format hint, and an optional validation strip that shows inline [Severity Level](#9-severity-levels) feedback.

**Toolbar.** A horizontal row of [Buttons](#button), pickers, and status [Pills](#pill) positioned above or below a panel's main content. The Task Editor's Editor Toolbar is an example.

**Footer.** A non-scrolling region pinned to the bottom of a [Panel](#panel), typically holding actions and status. The Result panel's uniform export footer is an example.

---

## 3. Visual Feedback States

This section defines the small visual indicators used to communicate status, progress, and supplementary information.

**Badge.** A small inline label, usually coloured by a [Semantic Colour](#8-semantic-colours). Used for [Verdict](#verdict) tags, counts, and status markers.

**Dot.** <a id="dot"></a>A small circular indicator. Used for application health in the [Status Bar](#status-bar) (green = ready, amber = degraded, red = not ready, grey = checking) and for presence indicators.

**Pill.** A rounded inline label, larger than a [Badge](#badge), and typically clickable. The [Running Pill](#running-pill) is the principal example.

**Running Pill.** <a id="running-pill"></a>A clickable [Pill](#pill) shown in the [Menu Bar](#menu-bar) only while a benchmark run is active. It surfaces the running run and lets the user jump to the centre [Progress](#progress-widget) panel.

**Spinner.** An animated, indeterminate-progress glyph shown while an operation is running but its completion fraction is unknown.

**Progress Bar.** A horizontal bar showing fractional completion. It may be *segmented* into multiple coloured sections, as the stage progress bar is during a run.

**Tooltip.** <a id="tooltip"></a>Hover-revealed explanatory text. It appears after a short delay (on the order of 200 milliseconds) and hides automatically when the pointer leaves the element.

**Popover.** An anchored overlay carrying rich content (text, links, lists). It dismisses on a click outside it.

**Toast.** <a id="toast"></a>A transient, automatically dismissed message rendered in the [Status Bar](#status-bar) or as a brief overlay. Default lifetime is at most five seconds; a Toast never blocks interaction.

**Banner.** A persistent in-pane message strip that remains visible until the user dismisses it or the underlying condition is resolved. Unlike a [Toast](#toast), a Banner does not auto-dismiss.

---

## 4. Application Service Roles

This section defines the backend service roles. Each role is an abstract responsibility with a contract; the implementation provides a concrete class for each. Full method signatures live in `08_Cross_Cutting/08-E_interfaces_contracts.md`. No implementation code appears here.

**Platform Detector.** Runs once at application startup and produces a `PlatformProfile` describing the host operating system, the [App-Data Folder](#app-data-folder) location, and theme-detection capabilities.

**Event Bus.** A publish/subscribe channel carrying cross-component signals. Components emit typed events and subscribe to them without referencing each other directly. Every subscription must use [Ownership Binding](#ownership-binding) so it is cancelled when its owner is destroyed.

**Data Store.** The embedded relational database (SQLite in WAL mode) holding benchmark runs, results, providers, tasks, and application settings. It is fully relational with no opaque blob columns and has no migration framework: a schema mismatch is a hard, clearly reported startup error.

**Settings Service.** Reads and writes user-saved settings and resolves an effective value by merging three layers: the per-run [Settings Snapshot](#settings-snapshot), the user-saved value, and the built-in default. See `08_Cross_Cutting/08-E_interfaces_contracts.md` for the resolution contract.

**Provider Registry.** Resolves a provider identifier to an [LLM Client](#llm-client) instance, and reloads itself when provider configuration changes. It is the single point through which the rest of the application reaches a provider.

**LLM Client.** <a id="llm-client"></a>A per-provider adapter that implements the LLM contract: list available models, run a chat/inference request, compute embeddings, and probe provider health. One LLM Client exists per configured [Provider](#provider).

**Pipeline (Benchmark Pipeline).** <a id="pipeline"></a>The background process that executes a benchmark run through its five [Phases](#phase) and emits [Event Bus](#event-bus) signals describing progress. See [Phase](#phase) and [Run Mode](#run-mode) for what the Pipeline does in each mode.

**Readiness Service.** Periodically probes every enabled [Provider](#provider) and publishes an aggregate application-readiness verdict — ready, degraded, not ready, or checking — which the [Status Bar](#status-bar) [Dot](#dot) reflects.

**Task File Loader.** Parses benchmark task YAML files into in-memory [Benchmark Task](#benchmark-task) records. It is *tolerant*: malformed entries are skipped with a warning so a usable subset of tasks still loads.

**Task File Validator.** Performs an *editor-strict* pass over raw task YAML and emits per-row [Diagnostics](#diagnostic). It powers the red/amber/green validation badges in the Task Editor. Where the [Task File Loader](#task-file-loader) is tolerant, the Validator is strict.

**YAML Formatter.** Writes [Benchmark Task](#benchmark-task) records back to YAML in a canonical field order, preserving comments where possible. Used by the Task Editor on save.

**Adaptive Timeout Service.** Tracks per-([Provider](#provider), [Model](#model), [Adaptive Timeout Role](#adaptive-timeout-role)) call timing and raises or lowers the per-attempt timeout within configured minimum and maximum bounds — **per role**. After a configured number of consecutive maximum-timeout failures it excludes a model from the run **for that role**. Two role buckets are independent: a model excluded at role=JUDGE may still run normally at role=INFERENCE, and vice versa. Consulted by the Phase 2 inference call (role=INFERENCE), the Phase 4 per-task judge call (role=JUDGE), and the user-initiated run-analysis generation call (role=RUN_ANALYSIS — its own independent bucket, DD-65). NOT consulted by the Embedding Service (fixed `eval.embedding_timeout_seconds` budget), `LLMClient.test_inference` (fixed 60 s), or `LLMClient.probe_health` (fixed short). See DD-34.

**Adaptive Timeout Role.** Identifies which per-`(provider, model)` adaptive-timeout state bucket a call belongs to. Two members: `INFERENCE` for Phase 2 per-task main inference (test-role models) — which also **sizes** the model-switch warmup call (DD-64; the warmup's outcome feeds the circuit breaker, not model exclusion) — and `JUDGE` for Phase 4 per-task judge calls (user-initiated run-analysis generation runs on its own dedicated bucket, DD-65). A model used as both a test model AND a judge model carries two independent state buckets. Embedding, Test Inference, and readiness probes have no `AdaptiveTimeoutRole` — they do not consult the service.

**FAILED_JUDGE_TIMEOUT.** A terminal [ResultStatus](#resultstatus) (see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.3) set on a [BenchmarkResult](#benchmark-result) when (a) the per-task judge call exhausted the role=JUDGE adaptive-timeout ladder for that task, OR (b) the judge model was excluded for the remainder of the run after crossing `eval.judge_timeout_consecutive_threshold` — every remaining task that would have entered the judge phase settles to this status directly. The task is NOT marked `COMPLETED`; `verdict` stays `None`. Member of the **retryable terminal-state set** alongside `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, and `ERRORED`. A retry re-runs the WHOLE task end-to-end (re-inference + re-grade), uniform with the other `FAILED_*` retries. See DD-34.

**Judge Model Exclusion.** When the role=JUDGE adaptive-timeout bucket crosses `eval.judge_timeout_consecutive_threshold` consecutive max-budget timeouts during a benchmark run, the pipeline excludes the judge model for the rest of the run. The pipeline emits `_judge_model_excluded` exactly once; every remaining task that would have entered the judge phase settles to [FAILED_JUDGE_TIMEOUT](#failed_judge_timeout) without the judge call being attempted. Phase 2 (inference) and Phase 3 (cosine) for those remaining tasks continue normally — the run does NOT abort. The role=JUDGE exclusion does NOT affect the same `(provider, model)` at role=INFERENCE. See `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md` §6.5.

**Circuit Breaker (Provider Circuit Breaker).** A per-provider health gate. It trips when failures accumulate within a sliding window, blocking further work for that provider, then periodically probes for recovery before closing again.

**Workspace Controller.** Owns the active-[Workspace](#workspace) state, swaps the [Workspace Region](#workspace-region) contents on switch, and persists `ui.active_workspace`.

**Notification Service.** Surfaces user-facing messages through one API: non-blocking [Toasts](#toast) and blocking error [Modal Dialogs](#modal-dialog).

**OS Adapter (OS File Manager Opener).** Opens a folder or file in the host operating system's file manager and provides other OS-integration entry points. The [System Clipboard](#system-clipboard) is a related OS-integration capability.

**System Clipboard.** <a id="system-clipboard"></a>Reads and writes text from the host operating system clipboard, for copy actions such as copying the App-Data Folder path.

**File-System Change Watcher.** Notifies subscribers when a tracked file's modification time changes. Used by the Task Editor to detect external edits to an open task file.

**Background Worker.** Runs a unit of work off the [UI Thread](#ui-thread) — I/O, network calls, or compute — and reports start, progress, and completion back via [Event Bus](#event-bus) signals.

**Run Validator.** Checks a proposed benchmark configuration before the run starts, distinguishing [hard errors](#hard-error) (which block the Start button) from [soft warnings](#soft-warning) (which the user may proceed past).

**Mode Visibility Policy.** Decides which configuration sections are visible for the currently selected [Run Mode](#run-mode), so the New Benchmark form only shows fields that apply.

**Run Drift Detector.** When a run is resumed, compares the run's original configuration against the current environment (for example a provider that is now disabled or unreachable) and reports drift warnings.

**Chart Aggregators.** Compute the aggregated datasets that back each chart from the stored [Benchmark Results](#benchmark-result).

**Chart Registry.** Catalogues the available chart kinds and the per-[Run Mode](#run-mode) visibility of each.

**Export Filename Helper.** Produces consistent, descriptive file names for exported tables, charts, and analysis documents.

**Run Analysis Service.** Generates the narrative, post-run analysis shown on the Run Analysis tab (`11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`). It produces prose, not numbers. The configured judge-role model authors the narrative, but the output is a run-level analysis, not per-task grading.

**Embedding Service.** Computes text embeddings used by the semantic keyword check and the [Cosine Score](#cosine-score) phase, using the configured embedding [Provider](#provider) and embedding [Model](#model).

**Log Formatter.** Formats [Run Log](#run-log) event records for display in the centre Progress panel and for writing to the run log file, respecting the selected verbosity.

**Composition Root (ApplicationContext).** The single object, built once at startup, that constructs every service, wires their dependencies, and hands references to the UI. There is exactly one Composition Root.

---

## 5. Lifecycle and Threading Terms

This section defines the concurrency and lifetime vocabulary. The application's observable threading behaviour is contracted; the specific concurrency primitives chosen (the `QThreadPool` worker pool, the dispatcher thread, worker objects) are an implementation detail — with the binding exception that `asyncio` is not used anywhere (D-R-01).

**UI Thread.** <a id="ui-thread"></a>The single thread that owns the creation and mutation of all widgets. Any change to the user interface originating on another thread must be marshalled onto the UI Thread before it is applied.

**Background Thread / Worker.** <a id="background-thread"></a>A non-UI thread spawned for I/O, network calls, or compute. It never touches widgets directly; it communicates results back to the [UI Thread](#ui-thread) by emitting [Event Bus](#event-bus) signals.

**Cross-thread Signal.** An [Event Bus](#event-bus) emission originating on a [Background Thread](#background-thread) that is delivered, queued, on the [UI Thread](#ui-thread). Queued delivery is what makes background-to-UI communication safe.

**Ownership Binding.** <a id="ownership-binding"></a>The relationship by which an [Event Bus](#event-bus) subscription is automatically cancelled when the object that created it is destroyed. Every subscription made by a widget must be bound to that widget's lifetime so no signal is delivered to a dead object.

**Deferred Tick.** An instruction to run a small piece of work on the next idle moment of the [UI Thread](#ui-thread). Used for post-construction setup that must wait until the window is visible.

**Debouncing.** Coalescing a rapid burst of signals into a single later emission — for example, persisting window geometry only after the user stops dragging, or refreshing a table a fixed delay after the last task completes.

**Phase (Stage).** <a id="phase"></a>One of the five sequential, batched steps the [Pipeline](#pipeline) executes for a benchmark run: (1) **init** — initialise the run, resolve the task set, and create result records; (2) **inference** — run every model against every task and capture the responses and timings; (3) **keyword** — apply keyword validation to the captured responses; (4) **cosine** — compute [Cosine Score](#cosine-score) similarity against golden answers; (5) **judge** — run the [Judge](#judge) over every result. The pipeline runs each phase fully (batched) before the next. "Phase" and "Stage" are used interchangeably; the persisted run-stage enum names them INITIALIZING, BENCHMARKING, KEYWORD_CHECK, COSINE_CHECK, and JUDGE_CHECK. Which phases run depends on the [Run Mode](#run-mode): Synthetic Benchmark runs only init and inference; Task Benchmark runs init and inference; Graded Benchmark runs all five.

**Run Lifecycle.** The sequence of states a benchmark run passes through from start to terminal state, controlled by the user's Pause, Resume, and Stop actions and by the [Pipeline](#pipeline)'s own progress. The persisted terminal states are completed, not-completed, stopped, and failed.

---

## 6. Persistence Vocabulary

This section defines the terms for everything the application stores on disk.

**App-Data Folder.** <a id="app-data-folder"></a>The operating-system-specific writable folder owned by the application. It holds the [Data Store](#data-store) database file, the `logs/run/` and `logs/app/` directories, and the `exports/` directory. Its exact path is determined by the [Platform Detector](#4-application-service-roles).

**Run Log.** <a id="run-log"></a>One file per benchmark run, recording the full verbose stream of [Pipeline](#pipeline) events for that run. It is one of the application's two independent log streams.

**App Log.** A single rotating diagnostic log file for the application as a whole, covering startup, errors, and background activity. It is the second of the two independent log streams; its rotation size and backup count are configurable.

**Exports Folder.** The directory inside the [App-Data Folder](#app-data-folder) that holds user-exported artefacts: tables (CSV and Markdown), charts (PNG), and analysis documents (Markdown).

**Settings Snapshot.** <a id="settings-snapshot"></a>A frozen copy of all run-overridable settings captured at the moment a run starts and persisted with that run. It is immutable for the run's entire lifetime, so a run's behaviour cannot drift if the user later changes settings. When a run is resumed, its existing snapshot is reused unchanged.

**Schema Version Marker.** A stored value identifying the [Data Store](#data-store) schema the database was created with. There is no migration framework; if the marker does not match the schema the running application expects, startup fails with a clear error rather than attempting an automatic upgrade.

---

## 7. Domain Terminology

This section defines the benchmark-domain concepts. These terms describe what the application does, independent of any screen. The authoritative data shapes are in `10_Domain_and_Data/01_DOMAIN_MODEL.md`.

**Provider.** <a id="provider"></a>A configured source of LLM inference — a local server (Ollama, LM Studio, llama.cpp) or a cloud service (OpenAI, Anthropic, Google, Microsoft, Amazon). Each Provider has an internal auto-generated identifier (see [Provider ID](#provider-id)), a user-entered unique [Provider Name](#provider-name), a type, an endpoint, and credentials. The [Provider Registry](#4-application-service-roles) resolves a Provider to an [LLM Client](#llm-client).

**Provider ID.** <a id="provider-id"></a>The **internal** primary key of a Provider in the data layer. The value is a **UUID4** textual representation (for example `"a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"`), generated by the `ProvidersStore` on insert. The Provider ID is NEVER displayed in the UI, NEVER entered by the user, NEVER carried by import/export YAML, and NEVER copied to the clipboard. It is the foreign-key value in `benchmark_runs.judge_provider_id`, `benchmark_results.provider_id`, `model_capabilities.provider_id`, and the run-snapshot tables, and is the linkage value carried by every Event Bus event payload that names a provider. The id is stable across renames — renaming a Provider changes only its [Provider Name](#provider-name), never its Provider ID. See DD-33 (`08_Cross_Cutting/08-F_spec_issues_log.md`).

**Provider Name.** <a id="provider-name"></a>The **user-entered unique display label** of a Provider, stored as `ProviderConfig.name`. The Name is the only Provider field the user types and the only Provider field shown anywhere in the UI — Settings table column, dropdowns (the reusable provider dropdown widget's user-visible text), event log, run-summary, charts legends, exports, and dialogs. The `providers` table enforces `UNIQUE (name)`; the Provider Edit dialog pre-checks for duplicates via `ProvidersStore.get_by_name(name)` and the Save button is disabled while the Name is empty or collides with another Provider's Name. Renaming a Provider changes the Settings table immediately; historical run rows continue to display the SNAPSHOT name captured at run start (`BenchmarkRun.judge_provider_name`, `BenchmarkResult.provider_name`), so a rename does not retroactively relabel completed runs.

**Model.** <a id="model"></a>A specific named LLM exposed by a [Provider](#provider) — for example a chat model used as a test target, a [Judge](#judge) model, or an embedding model. A model name alone does not uniquely identify a benchmark target; see [Composite Model Identity](#composite-model-identity).

**Composite Model Identity.** <a id="composite-model-identity"></a>The rule that a benchmark target is identified by the pair (`provider_id`, `model_name`) together, never by the model name alone. If two different providers each expose a model with the same name, they are two distinct benchmark targets and are aggregated, charted, and reported separately. All per-model rows, statistics, and chart series key on this composite identity.

**Run Mode.** <a id="run-mode"></a>One of exactly three modes a benchmark run executes in. **Synthetic Benchmark** uses synthetic prompts to measure raw inference speed (time-to-first-token, tokens per second, throughput); it runs no real tasks and produces no grading. **Task Benchmark** runs real task files but times them only — it captures timings without grading. **Graded Benchmark** runs real task files through the complete five-[Phase](#phase) pipeline, including keyword validation, [Cosine Score](#cosine-score) similarity, and [Judge](#judge) evaluation. There are exactly these three modes and no others.

**Benchmark Run.** <a id="benchmark-run"></a>One execution of the [Pipeline](#pipeline) under a chosen [Run Mode](#run-mode) against a chosen set of [Models](#model) and tasks. A run has a unique identifier, an optional user-given name, a [Settings Snapshot](#settings-snapshot), a stored status, and a collection of [Benchmark Results](#benchmark-result).

**Benchmark Task.** <a id="benchmark-task"></a>A single unit of work defined in a task YAML file: a question or prompt, an expected golden answer, grading criteria, required keyword terms, and metadata such as category, difficulty, and task type. In Synthetic Benchmark mode the tasks are generated synthetically instead of loaded from files.

**Benchmark Result.** <a id="benchmark-result"></a>The outcome of running one [Benchmark Task](#benchmark-task) against one (`provider`, `model`) pair. It records the model's response, timing measurements, per-phase evaluation outcomes, the [Cosine Score](#cosine-score), the [Judge](#judge) outcome, the final [Verdict](#verdict), and the resolution layer that decided the verdict.

**Task File.** A YAML document containing one or more [Benchmark Task](#benchmark-task) definitions. Task Files are authored and validated in the Task Editor [Workspace](#workspace) and consumed by the [Task File Loader](#task-file-loader).

**Verdict.** <a id="verdict"></a>The evaluation outcome of a [Benchmark Result](#benchmark-result). The *final* verdict is strictly **binary: PASS or FAIL**. A value of UNKNOWN (or null) is **not** a final verdict — it marks a result whose evaluation is still pending while [Phases](#phase) of the pipeline have yet to run. Once the pipeline finishes a result, its verdict is always PASS or FAIL.

**Keyword Validation.** The pipeline phase that checks the model's response for required terms: exact terms that must appear, forbidden terms that must not appear, and semantic terms whose presence is judged by embedding similarity. It contributes to the final [Verdict](#verdict).

**Cosine Score.** <a id="cosine-score"></a>The cosine similarity between the embedding of the model's response and the embedding of the task's golden answer, computed in the cosine [Phase](#phase) using the [Embedding Service](#4-application-service-roles). It is the **only numeric score** in the application; the result-table column displaying it is labelled "Cosine Score". Whether a Cosine Score passes is decided against a threshold that depends on the task's response scope.

**Judge.** <a id="judge"></a>An LLM, configured as a dedicated judge [Model](#model), that evaluates a model's response against the task's criteria in the final pipeline [Phase](#phase). The Judge returns a **pass/fail decision plus a written explanation** and produces **no numeric score**. The only numeric score in the application is the [Cosine Score](#cosine-score).

**Run Analysis (run-level).** A narrative, prose summary of an entire [Benchmark Run](#benchmark-run), generated by the [Run Analysis Service](#4-application-service-roles) and shown on the Run Analysis tab. It is **optional in every mode**, controlled by the "Generate run analysis" toggle (`feature.judge_run_analysis_enabled`): default ON in Graded Benchmark, OFF in Synthetic Benchmark and Task Benchmark; user-overridable in any mode. It can be regenerated on demand from any finished run, including a Graded Benchmark run whose snapshot had the toggle off. It is distinct from the per-task [Judge](#judge) evaluation.

**Adaptive Timeout.** The mechanism, owned by the [Adaptive Timeout Service](#4-application-service-roles), by which the per-call timeout for a (`provider`, `model`, `role`) bucket is raised or lowered based on observed timing, within configured bounds, and by which a persistently timing-out model is excluded from the run **for that role**. Two roles exist — `INFERENCE` (Phase 2 per-task inference) and `JUDGE` (Phase 4 per-task judge and run-analysis generation) — each with its own parameter set and exclusion threshold. See DD-34.

**Resolution Layer.** The label recorded on a [Benchmark Result](#benchmark-result) identifying which evaluation layer produced its final [Verdict](#verdict) — for example keyword, cosine, or judge — so the user can see why a result passed or failed.

**Embedding Model.** A [Model](#model) whose role is to turn text into vector embeddings. It is required for semantic keyword checks and for the [Cosine Score](#cosine-score) phase, and is configured separately from the test models.

**Embedding Configuration.** <a id="embedding-configuration"></a>The single selected `(embedding [Provider](#provider), [Embedding Model](#embedding-model))` pair used for semantic keyword checks and the [Cosine Score](#cosine-score) phase (D-R-13). It is not a catalog entity: there is no `EmbeddingConfig` record, no internal id, and no user-entered name. The selection is stored as two `app_settings` keys owned by `AppSettingsStore` — `embedding.selected_provider_name` (the stable provider name, not a UUID) and `embedding.selected_model_name` (the embedding model string). The per-provider list of available embedding models is discovered dynamically from the provider and is NOT persisted; only the last selection is stored. A start-up capability probe (one real `embed("probe")` call) re-validates that the selection resolves; when it does not resolve or is unset, `GRADED` is disabled. Historical run rows snapshot the resolved pair into `embedding_provider_name` and `embedding_model_name` at run start so a later change does not retroactively relabel completed runs.

---

## 8. Semantic Colours

Semantic colours are *roles*, not literal hex values. Concrete colour tokens for the Dark and Light themes are defined in the design-system documentation. Wherever this specification names a semantic colour, it refers to the role below.

**success.** A passed [Verdict](#verdict), a healthy provider or readiness state, a valid form.

**warning.** A recoverable issue or a soft validation failure — something the user should review but that does not block them.

**error.** A failed [Verdict](#verdict), a blocked save, or an unrecoverable problem.

**info.** Neutral metadata or an informational annotation; no action implied.

**mute.** Secondary text, disabled controls, and helper hints — visually de-emphasised content.

**primary.** The active selection, the default action of a surface, and the application's brand accent.

---

## 9. Severity Levels

Severity levels classify validation messages and log entries. They map onto the [Semantic Colours](#8-semantic-colours) above when surfaced visually.

**hard error.** <a id="hard-error"></a>The operation cannot proceed. The Save button is disabled, or the benchmark run is blocked, until the user fixes the underlying problem. Surfaced with the **error** colour.

**soft warning.** <a id="soft-warning"></a>The operation may proceed, but the user should review it first — for example an optional-but-recommended field left empty. Surfaced with the **warning** colour.

**info.** Purely advisory. No action is required. Surfaced with the **info** colour.

**trace / debug.** Diagnostic detail written to the [App Log](#app-log) only and never surfaced in the user interface.
