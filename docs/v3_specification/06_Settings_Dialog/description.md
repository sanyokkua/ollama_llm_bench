# Settings Dialog — Description

**Status:** Draft
**Owner:** coder, tester
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:**
`06_Settings_Dialog/state_machine.md`,
`06_Settings_Dialog/flow_diagram.md`,
`06_Settings_Dialog/implementation_structure.md`,
`06_Settings_Dialog/mockup.html`,
`06_Settings_Dialog/sub_dialogs/provider_edit.md`,
`06_Settings_Dialog/sub_dialogs/reset_confirmation.md`,
`08_Cross_Cutting/08-C_settings_hierarchy.md`,
`08_Cross_Cutting/08-G_feature_flags.md`,
`08_Cross_Cutting/08-E_interfaces_contracts.md`,
`08_Cross_Cutting/08-H_app_modes.md`,
`08_Cross_Cutting/08-J_event_bus_catalog.md`,
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`,
`10_Domain_and_Data/06_IMPORT_FORMATS.md`,
`10_Domain_and_Data/08_REDACTION_PATTERNS.md`,
`11_Services_and_Algorithms/09_READINESS_PROBE.md`

The Settings Dialog is the single modal surface where the user configures the
application: the provider catalog, the embedding-model selection, and every
user-saved setting key. It writes the whole configuration atomically on Save,
exports and imports the configuration as YAML, and restores factory defaults.
The dialog is gated closed while a benchmark run is in any non-terminal state,
so a run's settings snapshot can never diverge from a live edit.

---

## Table of Contents

1. Role and ownership
2. Layout
3. Behaviour per element — Providers tab
4. Behaviour per element — General tab
5. Behaviour per element — footer
6. Save flow (atomic)
7. Export flow
8. Import flow
9. Reset flow
10. Close flow
11. App-data folder layout
12. Provider authentication model
13. Provider test — two distinct actions (Test reachability + Test inference)
14. Auto-check on open and embedding bootstrap
15. Validation rules
16. State transitions
17. Persistence
18. Event bus integration
19. Service dependencies
20. Edge cases
21. Function inventory

---

## 1. Role and ownership

The Settings Dialog is a **Modal Dialog** that owns the entire editable
configuration of the application. It is responsible for:

- Presenting and editing the provider catalog (`ProviderConfig` records).
- Presenting and editing the single embedding-model selection (the `embedding.selected_provider_name` / `embedding.selected_model_name` setting pair).
- Presenting and editing every user-saved setting key catalogued in
  `08_Cross_Cutting/08-G_feature_flags.md`.
- Persisting all of the above in one atomic transaction on Save, spanning the `ProvidersStore` and the `AppSettingsStore`.
- Exporting and importing the configuration as YAML.
- Restoring factory defaults.

It is **not** responsible for: per-run setting overrides (those belong to the
New Benchmark widget and freeze into the run snapshot — see
`08_Cross_Cutting/08-C_settings_hierarchy.md`); running a benchmark; or any
behaviour while a run is in progress. The dialog cannot be opened while a run is
in any non-terminal state (`08_Cross_Cutting/08-H_app_modes.md` §10).

The dialog edits an in-memory working copy of the configuration. Nothing it
collects reaches the `ProvidersStore` or the `AppSettingsStore` until the user
clicks Save Changes; Close without Save discards the working copy.

## 2. Layout

The dialog is a fixed-structure modal sized at roughly 760 px wide. It cannot be
moved off-screen. The layout, from top to bottom:

| Region | Content |
|---|---|
| Title bar | `Settings`, plus a close affordance |
| Tab Strip | `[Providers]` `[General]` — a dirty tab carries an asterisk |
| Tab Body | the active tab's scrollable body |
| Footer | `[Reset to Defaults]` · save-state indicator · `[Import…]` `[Export…]` `[Close]` `[Save Changes]` |

The visual reference is `06_Settings_Dialog/mockup.html`, which renders both
tabs (Providers dirty, General clean), the two Provider Edit Test panels, and
the **Import preview** modal (§8). The remaining sub-dialogs — the **Reset
confirmation** dialog and the **Discard-changes** confirmation — are **not
depicted in this mockup**; each is specified in full in its own document
(`sub_dialogs/reset_confirmation.md`, §10 Close flow) and renders on demand. (The
former Env-var conversion sub-dialog no longer exists — D-R-18; provider
credentials are entered as a bare environment-variable name validated inline.)
The dialog has no per-tab save button: a single Save Changes button in the footer
commits both tabs together (§6).

**Dirty indicator.** When any field on either tab differs from the value last
persisted, the dialog is *dirty*: the Save Changes button gains an asterisk, the
dirty tab's label gains an asterisk, and the footer save-state indicator shows
the pending-change state. A clean dialog shows no asterisk and the save-state
indicator reads as saved or unchanged.

## 3. Behaviour per element — Providers tab

The Providers tab manages the provider catalog and the embedding selection.

### 3.1 Add Provider button

Top-right of the tab. Opens the Provider Edit sub-dialog
(`sub_dialogs/provider_edit.md`) in blank state with a generated draft
identifier. Always enabled while the dialog is open. On the sub-dialog's Save,
a new row is appended to the in-memory provider table and the dialog is marked
dirty.

### 3.2 Provider table

A table listing every `ProviderConfig` in `provider_order`. The table's sort-by-column choices, dropdown labels, and event-log mentions of a provider all render `ProviderConfig.name`; the internal `provider_id` (an auto-generated UUID4 per DD-33) is never displayed in any column and there is no "show internal id" toggle. Columns:

| Column | Content |
|---|---|
| Health | A Health Dot reflecting the provider's most recent `ProviderTestStatus` — `READY` (success colour), `ZERO_MODELS` (warning), `UNREACHABLE` / `MISSING_ENV` (error), `UNTESTED` (muted), `TESTING` (a spinner). |
| Name | `ProviderConfig.name` — the user-entered unique display label. The primary, sortable column. |
| Type | `ProviderConfig.provider_type` — `openai_compatible`, `anthropic`, or `gemini`. |
| Base URL | `ProviderConfig.base_url`, or `(default)` when the type uses an SDK default, or the resolved Azure endpoint URL for an Azure-configured provider. |
| Auth | A badge: `env ✓` (an env-var name is set and the variable resolves to a non-empty value), `env ✗` (a name is set but the variable is unset or empty), or `none` (no name set). |
| Enabled | A toggle bound to `ProviderConfig.enabled`. Toggling marks the dialog dirty. |
| Actions | Four icon buttons, described below. |

A row whose configuration has unsaved edits carries a subtle background tint; a
newly added row carries a primary-coloured tint and a `(new)` marker. The table
is sortable by Name, Type, and Health.

### 3.3 Per-row actions

| Action | Behaviour | Enabled when |
|---|---|---|
| Test connection | Runs the **Test reachability** action (§13) against the **in-memory working copy** of this row, not the persisted value — `LLMClient.probe_health()` only; never an inference. The Health Dot shows `TESTING` while in flight, then the final status. Result detail is shown as a row tooltip and on the row's Auth badge. To run an end-to-end inference test against a chosen model, the user opens the Provider Edit sub-dialog and uses its Test inference panel (`sub_dialogs/provider_edit.md` §8.2). | Always |
| Edit | Opens the Provider Edit sub-dialog populated from this row's working copy. | Always |
| Reset this provider | Reverts this one row's unsaved edits to the value last persisted in the `ProvidersStore` for this `provider_id` — a current-session-scoped revert, not a factory reset. A bundled and a user-added provider behave identically. If the row was added in this session and never persisted, Reset removes it. See `sub_dialogs/reset_confirmation.md` §5. | The row has unsaved edits, or the row is a session-added row |
| Delete | Removes the row from the in-memory provider table and marks the dialog dirty. No persistence write happens until Save. | Always |

The per-row Reset is deliberately distinct from the footer Reset to Defaults
(§9): the row action reverts edits to the *persisted* value; the footer button
restores *factory* defaults for the whole configuration.

### 3.4 Embedding section

Below the table. It manages the **single** embedding-model selection (D-R-13): one `(provider, embedding model)` pair stored as the `embedding.selected_provider_name` / `embedding.selected_model_name` setting keys (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §5.2). There is no embedding-config catalog, no named rows, no internal id, and no Selected radio — just the one active pair. Embeddings have no user-facing name.

| Control | Behaviour |
|---|---|
| Provider dropdown | The shared `ui/shared/provider_dropdown` populated from enabled providers; selection emits `provider_changed(provider_id)`, which repopulates the Model dropdown from that provider's **dynamic** embedding-model list. Initialised to the provider whose name matches `embedding.selected_provider_name`. |
| Model dropdown | The shared `ui/shared/model_dropdown`, populated from the selected provider's discovered embedding models (or its preconfigured list), configured with an embedding-likely-name filter and a "Show all models" toggle. This list is **dynamic and never persisted**; only the chosen model string is saved, into `embedding.selected_model_name`. Initialised to `embedding.selected_model_name` when it is present in the list. |
| Test Embedding | Runs the user-initiated embedding capability test (`11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` §6.6a — DD-48; gate activity `PROVIDER_TEST`) against the currently selected `(provider, model)` pair: it pings the provider and issues one real `embed` call. This is the only billable embedding call outside a run; the automatic readiness check is handshake-only. The inline diagnostic shows `✓` with the vector dimension and latency, or `✗` with a redacted error. |
| Show all models | A checkbox beneath the Model dropdown labelled `Show all models`. When **off** (the default), the Model dropdown is filtered to embedding-likely model names only (the embedding-likely-name filter described in the Model-dropdown row above). When **on**, the filter is bypassed and the dropdown lists **every** model the selected provider discovered, so a user can pick an embedding model whose name the heuristic does not recognise. It is a **transient view filter with no persisted setting key** — this is why, unlike every General-tab control, it carries no dotted key in the mockup. Toggling it only re-populates the Model dropdown from the same dynamic list; it does **not** mark the dialog dirty and writes nothing on Save. This is the same show-all pattern the Provider Edit Test-inference Model picker and the New Benchmark Judge picker use through the shared `ui/shared/model_dropdown` widget. |

There is **no Add / Edit / Delete and no Name field** — the selection is a single pair, not a catalog. Changing either dropdown updates the working selection; the eventual base-dialog Save Changes commit writes `embedding.selected_provider_name` and `embedding.selected_model_name` through `AppSettingsStore.upsert_settings(...)` like any other setting.

When no embedding selection exists or the saved pair fails to resolve (the provider was deleted, or the model is no longer offered), `GRADED` is a disabled run mode in the New Benchmark widget until the user picks a working pair. The embedding selection is global configuration and is **not** per-run-overridable (`08_Cross_Cutting/08-C_settings_hierarchy.md` §4); it is resolved and frozen into the run snapshot at run start.

## 4. Behaviour per element — General tab

The General tab is a scrollable column of sections. Every control writes one
user-saved setting key from the registry in `08_Cross_Cutting/08-G_feature_flags.md`;
no toggle exists outside that registry. Editing any control marks the dialog
dirty. The sections, top to bottom:

### 4.1 Inference

| Control | Setting key | Type |
|---|---|---|
| Stream tokens to Log panel | `ui.stream_tokens_to_log` | bool (live UI preference; not a run input) |
| Default reasoning effort | `feature.reasoning_effort_default` | enum `ReasoningEffort` |
| Sampling temperature (model under test) | `benchmark.temperature` | float ≥0.0 or blank. **Default `0.0`** (DD-61) for comparable cross-model runs; not clamped; per-run-overridable in New Benchmark. Blank ⇒ each provider's own default (run flagged not directly comparable). D-R-04. |
| Max output tokens (model under test) | `benchmark.max_output_tokens` | int ≥256, **default 4096** (DD-67); per-run-overridable; always sent (Anthropic mandates a max-tokens value). |
| Judge max completion tokens | `eval.judge_max_completion_tokens` | int ≥256, **default 4096** (DD-67; raised from 512 so a reasoning judge can emit reasoning before its JSON verdict). |
| Enable model warmup | `benchmark.warmup_enabled` | bool |
| Retry count (recoverable failures) — inference | `benchmark.retry_count` | int 0–10 |
| Inference timeout — minimum (seconds) | `benchmark.min_timeout_seconds` | int 1–3600 |
| Inference timeout — maximum (seconds) | `benchmark.max_timeout_seconds` | int 1–3600 |
| Inference timeout — max max-timeout failures before exclusion | `benchmark.consecutive_max_timeouts_to_exclude` | int ≥1 |

The four inference-timeout values jointly parameterise the Adaptive Timeout Service **for role=INFERENCE** (Phase 2 — test-role inference): the first inference attempt uses the minimum budget; each retry escalates the budget toward the maximum across the retry count; a `(provider, model)` pair that hits the maximum budget on the configured number of consecutive tasks is excluded **at role=INFERENCE** and its remaining tasks are recorded `FAILED_TIMEOUT`. The role=JUDGE adaptive-timeout ladder is configured separately in the Judge timeouts section (§4.3a below). The fixed embedding-call budget is configured separately in the Embedding timeout field (§4.3a below). The full algorithm is in `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`. See DD-34 in `08_Cross_Cutting/08-F_spec_issues_log.md` for the per-role split.

**Streaming clarification.** `ui.stream_tokens_to_log` (a live UI preference, SPEC-116) controls **only** the
Progress widget's Log panel — when on, the panel echoes inference tokens as
they arrive; when off, the full response appears when the inference completes.
Backend (transport) streaming is **always on** regardless of this flag, because
it is how the pipeline measures Time To First Token (`BenchmarkResult.ttft_ms`).
A `(provider, model)` pair whose transport does not support streaming yields a
null `ttft_ms`; this flag never changes that.

### 4.2 Benchmark Events

Four independent toggles. They are captured into the run snapshot at run start
and do not change mid-run.

| Toggle | Setting key | Effect |
|---|---|---|
| Pause when moving to the next provider | `benchmark.pause_on_provider_switch` | The pipeline auto-pauses before the first task of a new provider. |
| Pause when moving to the next model | `benchmark.pause_on_model_switch` | The pipeline auto-pauses before the first task of a new test model. |
| Pause between pipeline stages | `benchmark.pause_on_phase_switch` | The pipeline auto-pauses at each phase boundary (for example inference → keyword check). This is the canonical phase-pause key. |
| Stop the run if a provider's health check fails | `benchmark.stop_on_provider_health_failure` | When on, the run terminates `FAILED` if a provider trips its circuit breaker; when off, affected results are recorded `FAILED_PROVIDER` and the run continues. |

These are four separate toggles, not one combined control. Their purpose is
memory management for locally hosted models — pausing lets the user unload one
model and load the next.

### 4.3 Evaluation

The settings in this section **apply only to `GRADED` runs.** `TASKS` and
`SYNTHETIC` never run any grading phase — they measure timing and
throughput only — so the three phase toggles, the force-judge flag, and the
the cosine threshold is ignored when a run is started in either of those modes.
The values are still persisted and snapshotted into every run for traceability,
but the pipeline consults them only when the run mode is `GRADED`. Within
Graded Benchmark the three grading phases are each individually toggleable. The
deterministic response sanity check always runs and is not toggleable.

| Control | Setting key | Effect |
|---|---|---|
| Enable keyword validation | `eval.phase_keyword_enabled` | When off, the keyword phase is skipped in `GRADED` and `keyword_verdict` stays null. Ignored in `TASKS` and `SYNTHETIC`. |
| Enable cosine similarity validation | `eval.phase_cosine_enabled` | When off, the cosine phase is skipped in `GRADED` and `cosine_similarity` / `cosine_verdict` stay null. Ignored in `TASKS` and `SYNTHETIC`. |
| Enable judge validation | `eval.phase_judge_enabled` | When off, the per-task judge phase is skipped in `GRADED` and `judge_verdict` stays null. Ignored in `TASKS` and `SYNTHETIC`. Disabling it does **not** disable the run-level judge analysis. |
| Run the judge even after an earlier phase failed | `eval.force_judge_on_prior_failure` | When on, the judge runs even if an earlier enabled phase already produced a `FAIL`. Has effect only when judge validation is on. Applies only in `GRADED`. |
| Cosine threshold | `eval.cosine_threshold` | The single pass/fail cutoff for the whole-text Cosine Score (DD-45). Consulted only in `GRADED`. |

The judge returns a binary verdict plus a free-text explanation — never a
numeric score. Disabling judge validation here does not affect the run-level
judge analysis, which is governed separately by
`feature.judge_run_analysis_enabled` (§4.4).

### 4.3a Judge timeouts and embedding timeout

This section is **visible regardless of run mode** — its values are run-time
tuning knobs that the Adaptive Timeout Service (role=JUDGE) and the Embedding
Service consult during execution. See DD-34 (`08_Cross_Cutting/08-F_spec_issues_log.md`)
for the full per-role adaptive-timeout model.

| Control | Setting key | Type |
|---|---|---|
| Judge timeout — minimum (seconds) | `eval.judge_timeout_min_seconds` | int 1–3600 (default 20) |
| Judge timeout — maximum (seconds) | `eval.judge_timeout_max_seconds` | int 1–3600 (default 120) |
| Judge timeout — escalation steps | `eval.judge_timeout_escalation_steps` | int 0–10 (default 2) |
| Judge timeout — max max-timeout failures before exclusion | `eval.judge_timeout_consecutive_threshold` | int ≥1 (default 3) |
| Embedding timeout (fixed, seconds) | `eval.embedding_timeout_seconds` | int 1–3600 (default 30) |

The four judge-timeout fields jointly parameterise the Adaptive Timeout Service
**for role=JUDGE** — consulted by both (a) the Phase 4 per-task judge call in a
benchmark run and (b) the user-initiated run-analysis generation call. The
ladder works identically to the role=INFERENCE ladder (§4.1) but uses these
judge-specific bounds and threshold. The role=JUDGE bucket is **independent** of
the role=INFERENCE bucket — a model excluded as a judge stays usable as a test
model and vice versa.

The **Embedding timeout** field is a **fixed** per-call deadline — embedding
calls do NOT consult the Adaptive Timeout Service and there is no per-`(provider,
model)` escalation or exclusion for embedding. On an embedding timeout, the
affected task's cosine phase fails for that task and the binary verdict cascade
settles per D-012 (cosine-not-run handling); the next task tries the embedding
call afresh with the same fixed budget. A chronically stalled embedding model
therefore produces per-task cosine failures task after task, but never aborts
the run and is never excluded.

**Note.** Test Inference (Provider Edit Test inference action) and the
readiness probe both use their own fixed deadlines and are NOT affected by any
field in this section — they do not consult the Adaptive Timeout Service.

### 4.4 Run-level analysis

| Control | Setting key | Effect |
|---|---|---|
| Generate run-level analysis with the judge model | `feature.judge_run_analysis_enabled` | The post-run narrative `BenchmarkRun.run_analysis`. **Optional — controlled by the "Generate run analysis" toggle; default ON in `GRADED`, OFF in `SYNTHETIC` and `TASKS`.** The toggle is visible in every mode and the user can override the default in either direction; the per-run override on the New Benchmark widget always takes priority over this stored value. |

### 4.5 Embedding Models

| Control | Setting key | Effect |
|---|---|---|
| Hide embedding-like models from selection lists | `embedding.hide_from_test_models` | When on, model names that look like embedding models are filtered out of the test-model picker. |
| Additional patterns (comma-separated) | `embedding.additional_patterns` | Extra substring patterns, beyond the built-in set, that mark a model name as embedding-like. |

This section tunes the embedding-model classifier. The embedding-model
*selection* itself lives on the Providers tab (§3.4).

### 4.6 Display

| Control | Setting key | Effect |
|---|---|---|
| Theme | `ui.theme` | `system`, `dark`, or `light`. |
| Score display format | `ui.score_display_format` | `decimal`, `percent`, or `letter` — rendering only; underlying scores are always 0.00–1.00. |

### 4.7 Logging — Run Logs

Run logs are field-density-based and per-run. They feed the Progress widget log
panel and the per-run log file.

| Control | Setting key | Effect |
|---|---|---|
| Write run log to file | `logging.write_run_log_to_file` | When off, the run log stays in memory only; no per-run file is written. |
| Default run-log verbosity | `ui.run_log_verbosity` | `short`, `normal`, or `verbose` — the initial verbosity for a new run; live-switchable in the Progress panel. |
| Auto-scroll log panel | `ui.auto_scroll_run_log` | Whether the Progress panel auto-scrolls to the newest line. |
| Run-log buffer (lines) | `ui.run_log_max_lines` | User-configurable cap on the in-memory display buffer (one line per event). Default 100,000; accepts 1,000–500,000 and clamps out-of-range input. The per-run file always keeps every event regardless of this value. |
| Open Run Logs folder | — (action) | Opens `<app_data>/logs/run/` only (§11). |

The per-run file is always written at verbose field density regardless of
`ui.run_log_verbosity`; that key changes only the on-screen panel.

### 4.8 Logging — App Logs

App logs are severity-based, rotated, and not shown in the UI.

| Control | Setting key | Effect |
|---|---|---|
| Write app log to file | `logging.write_app_log_to_file` | Toggle for the `<app_data>/logs/app/app.log` writer. |
| App-log level | `logging.app_log_level` | `trace`, `debug`, `info`, `warn`, or `error`. Takes effect immediately on Save. |
| Rotation — max file size (MB) | `logging.app_log_max_file_mb` | Maximum size of one log file before rotation. Default 10 MB; accepts 1–50 MB and clamps out-of-range input. |
| Rotation — total log budget (MB) | `logging.app_log_max_total_mb` | Hard ceiling on the total disk used by the app log (current file plus all backups). Default 60 MB; accepts up to 200 MB, must be ≥ the max file size. The backup count kept (`app.log.1`, `app.log.2`, …) is derived as `floor(total ÷ file size)` so the total can never be exceeded. |
| Open App Logs folder | — (action) | Opens `<app_data>/logs/app/` only (§11). |

### 4.9 Storage

| Control | Behaviour |
|---|---|
| App folder path | A **read-only path label** showing the resolved, platform-specific app-data root (the macOS form `~/Library/Application Support/OllamaLLMBench/` in the mockup is illustrative; the label is non-editable and updates per host OS — resolution per `10_Domain_and_Data/07_FILE_LAYOUT.md`). On that **same row**, a muted **Copy** button copies the **absolute** app-data path to the system clipboard via the OS Adapter (`Clipboard.copy_text`). The Copy action sits on the path-label row and is distinct from the separate "Open App folder" button row beneath it. |
| Open App folder | A separate row beneath the path label: opens `<app_data>/` — the root containing the database, `logs/`, and `exports/` (§11). |

### 4.10 Task Editor

| Control | Setting key | Effect |
|---|---|---|
| Default Task Editor folder | `ui.task_editor_last_folder` | The default folder for the Open / New File pickers in the Task Editor workspace. A folder picker sets it. |
| Auto-format YAML on save | `task_editor.auto_format_on_save` | When on, Task Editor Save rewrites each file in canonical field order. Default on. |
| Warn on empty grading criteria | `task_editor.warn_on_empty_grading_criteria` | When on, an empty `pass_criteria` or `fail_criteria` raises a soft warning. Default on. |

The three folder buttons across §4.7, §4.8, and §4.9 each open a distinct
location; none opens a parent that contains the others (§11).

## 5. Behaviour per element — footer

| Control | Behaviour | Enabled when |
|---|---|---|
| Reset to Defaults | Opens the Reset confirmation sub-dialog (`sub_dialogs/reset_confirmation.md`); on confirm, wipes the configuration and re-seeds factory defaults (§9). | Always; disabled while a Save is committing |
| Save-state indicator | A muted label reading the dialog's clean / dirty / saving / saved state. | Always (display only) |
| Import… | Opens a file picker, validates and previews a settings YAML, replaces the configuration on confirm (§8). | Always; disabled while a Save is committing |
| Export… | Opens a save picker and writes the current configuration to YAML (§7). | Always; disabled while a Save is committing |
| Close | Closes the dialog; prompts to discard if dirty (§10). | Always |
| Save Changes | Commits both tabs atomically across the `ProvidersStore` and the `AppSettingsStore` (§6). Carries an asterisk while dirty. | The dialog is dirty and has no hard validation error |

## 6. Save flow (atomic)

Save Changes commits the whole working copy in one persistence transaction spanning the `ProvidersStore` and the `AppSettingsStore`. The
sequence diagram is `flow_diagram.md` §A. The steps:

1. The user clicks Save Changes.
2. The dialog runs validation across both tabs (§15). A hard error aborts the
   save, focuses the offending control, and shows an inline error; nothing is
   written.
3. The dialog collects the working provider catalog, the embedding selection,
   and the general-tab setting values. Every provider credential field already
   holds only an environment-variable name (or empty) — entry validation in the
   Provider Edit sub-dialog (`sub_dialogs/provider_edit.md` §5.1) guarantees this
   — so there is no secret-handling step here; the Save proceeds straight to the
   transaction.
4. The dialog opens one persistence transaction (spanning the `ProvidersStore` and the `AppSettingsStore`) and within it:
   - calls `ProvidersStore.replace_providers(...)` with the working catalog. The working catalog is the assembled tuple of `ProviderConfig` values where each row either carries the row's persisted `provider_id` (for an unchanged or edited row) or a freshly-generated UUID4 (for a row added in this session — generated by the store inside `replace_providers` for the rows whose `provider_id` is absent). The store enforces `UNIQUE (name)`; per-row duplicate-name pre-checks at dialog time guarantee the friendly-error path was taken before this transaction (DD-33).
   - calls `AppSettingsStore.upsert_settings(...)` with the general-tab values, including `embedding.selected_provider_name` and `embedding.selected_model_name` when the embedding selection has changed.
5. On commit, the dialog emits `_provider_registry_reloaded` and
   `_app_settings_changed` on the Event Bus.
6. A toast `Settings saved` is shown; the dialog becomes clean (no asterisk).
7. The dialog stays open so the user can continue editing.

If the transaction fails, the dialog stays dirty, shows a blocking error
notification, and writes nothing — the transaction is all-or-nothing.

## 7. Export flow

The export flow is `flow_diagram.md` §D. The exported file format is the
provider-configuration and settings YAML defined in
`10_Domain_and_Data/06_IMPORT_FORMATS.md` (export and import share one format).

1. The user clicks Export….
2. A native save picker opens, defaulting the file name to
   `ollama_bench_settings_<YYYY-MM-DD>.yaml`.
3. The exporter writes a single YAML file carrying the provider catalog, the
   embedding selection, and every user-saved setting key.
4. A toast `Exported to <path>` is shown.

API-key handling on export: the stored value is an environment-variable name,
which is written verbatim — it names where a secret lives without containing one.
No literal secret can be present in the configuration (entry validation forbids
it), so the export never carries a plain API key and never needs a "store the
file securely" warning. The export never resolves an environment variable; it
writes only the name.

## 8. Import flow

The import flow is `flow_diagram.md` §D. The full schema, validation severities,
and unknown-key handling are in `10_Domain_and_Data/06_IMPORT_FORMATS.md`; this
section describes the dialog-level behaviour.

1. The user clicks Import….
2. A native file picker opens, accepting `.yaml` / `.yml`.
3. The importer parses and fully validates the file. A file-level hard error
   aborts the import with an error modal naming the cause; nothing is applied.
4. Otherwise an **Import Preview** modal opens. It groups the proposed change
   into Added, Changed, and Unchanged, plus a Skipped / ignored group listing
   every soft warning and soft info with its reason. A provider credential value
   is an environment-variable name, which is shown verbatim because a name is not
   a secret. An imported credential value that is not a valid environment-variable
   name (it looks like an actual key) is rejected for that provider with a soft
   warning in the Skipped / ignored group, guiding the user to supply a variable
   name instead.
5. The user confirms or cancels. Cancelling applies nothing.
6. On confirm, the configuration is applied directly — there is no secret-handling
   step, because every credential value is already an environment-variable name.
7. The configuration is applied in one persistence transaction spanning the `ProvidersStore` and the `AppSettingsStore`: provider
   configuration **replaces** the registry wholesale; settings **merge** (only
   the present, valid keys are written).
8. The dialog emits `_provider_registry_reloaded` and `_app_settings_changed`,
   reloads both tabs from the new state, and shows a toast `Settings imported`.

Two provider entries sharing an `id` is a hard error that aborts the import
before the preview (EC-IMP-7 in `10_Domain_and_Data/06_IMPORT_FORMATS.md`).

## 9. Reset flow

The reset flow is `flow_diagram.md` §C; the confirmation content is
`sub_dialogs/reset_confirmation.md`.

1. The user clicks Reset to Defaults.
2. The Reset confirmation sub-dialog opens, stating what is reset and what is
   preserved.
3. On cancel, nothing changes.
4. On confirm, one persistence transaction (spanning the `ProvidersStore` and the `AppSettingsStore`) deletes every `app_settings`
   and `providers` row (the embedding selection is cleared with the rest of `app_settings`), then re-seeds the three bundled
   providers and the in-code setting defaults.
5. The dialog reloads both tabs, emits `_provider_registry_reloaded` and
   `_app_settings_changed`, and shows a toast `Settings reset to defaults`.

Reset to Defaults discards any unsaved edits in the working copy as part of the
wipe (EC-SET-5). It is the only path to factory defaults; the per-row Reset (§3.3)
only reverts to the persisted value.

## 10. Close flow

The close flow is `flow_diagram.md` §E.

- If the dialog is clean, Close, the title-bar close affordance, and `Esc` close
  it immediately.
- If the dialog is dirty, those actions open a Discard-changes confirmation:
  `Discard` closes the dialog without saving; `Cancel` keeps it open. The
  working copy is discarded only on `Discard`.

## 11. App-data folder layout

The three folder buttons in the General tab each open a different directory
under the platform-specific app-data root. The layout:

```
<app_data>/                              <- "Open App folder"   (Storage)
|-- ollama_llm_bench.db                  <- SQLite database file (shared by every persistence store)
|-- exports/
|   `-- <effective_run_name>_<kind>.<ext>
`-- logs/
    |-- run/                             <- "Open Run Logs folder"
    |   `-- run_<run_id>_<unix_ts>.log
    `-- app/                             <- "Open App Logs folder"
        |-- app.log
        |-- app.log.1
        `-- app.log.N
```

Each folder button delegates to `FileSystemActions.open_in_file_manager` with the
resolved path. The three buttons are kept single-purpose deliberately: a
"show everything" link to `logs/` would blur the distinction between run logs
(per-run, human-readable) and app logs (severity-filtered, not shown in the UI).
The per-OS resolution of `<app_data>` is defined in
`10_Domain_and_Data/07_FILE_LAYOUT.md`.

## 12. Provider authentication model

A provider's API-key credential is stored as the **name of an environment
variable** (for example `OPENAI_API_KEY`) — never a literal key (D-R-18). The
Settings Dialog's table shows only a summary Auth badge per provider; the
detailed editing happens in the Provider Edit sub-dialog
(`sub_dialogs/provider_edit.md` §5), where the API key is a single text input
that accepts a valid environment-variable name or empty, validated inline.

- Single-secret providers (a plain OpenAI-compatible provider, Anthropic,
  Gemini) have one credential — the API key — entered as an environment-variable
  name.
- A multi-secret provider — an Azure-hosted OpenAI-compatible endpoint — has the
  API key (an environment-variable name) plus three **plain literal config
  values** that are not secrets: the Azure endpoint URL, the deployment name, and
  the API version (`sub_dialogs/provider_edit.md` §6.2).

At use time the application reads the named variable from the process
environment; the resolved value lives only in memory and is never written to
disk. The Auth badge reflects whether the named variable resolves: `env ✓`
(name set and resolves to a non-empty value), `env ✗` (name set but the variable
is unset or empty), or `none` (no name set). The three bundled local providers
(Ollama, LM Studio, llama.cpp) need no key and leave the API-key field empty, so
their badge is `none`. The application reads environment variables once at
startup, so a newly set or changed variable is picked up only after the
application is restarted.

## 13. Provider test — two distinct actions

A provider is tested through **two independently-triggered actions**, each
mapping to a distinct method on the `LLMClient` Protocol
(`08_Cross_Cutting/08-E_interfaces_contracts.md` §10). Both actions run
against the **in-memory working copy** of the configuration, never the
persisted value (EC-PROV-4):

1. **Test reachability** — calls `LLMClient.probe_health()`. Confirms the
   endpoint is reachable and (only if the per-provider implementation supports
   it) issues a model-discovery call. **Never issues an inference call.**
   Never billable. Zero discovered models is informational, not a failure.
   A provider type whose implementation reports `discovery_supported=False`
   (Anthropic) reports the fact and is healthy when reachable. The probe
   reuses the algorithm of
   `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.8.1 and
   `11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.2.
2. **Test inference** — calls `LLMClient.test_inference(model_name)`. Issues
   exactly one short chat call with a fixed canned prompt to the named model
   and returns a typed `InferenceTestResult`. **User-initiated only** — never
   run automatically — because on paid cloud providers this call is billable.
   The user MUST select a model from the shared `ui/shared/model_dropdown`
   widget or enter a model name manually before the Run button is enabled.
   The algorithm is specified in
   `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.8.2.

On a provider row in the Providers tab the table-level **Test connection**
action runs only the reachability test (the row has no model context; the
user opens Provider Edit to run an inference test against a specific model).
The Provider Edit sub-dialog exposes both actions independently, with the
inference test driven by an inline panel — see
`06_Settings_Dialog/sub_dialogs/provider_edit.md` §8 for the full
specification.

The inline result paints the outcome and latency of each action. Every error
string the actions surface has already passed through redaction at the
`LLMClient` boundary.

Both actions acquire the application-wide single-inference gate
(`InferenceActivityStore`, `08_Cross_Cutting/08-E_interfaces_contracts.md`
§13) as `PROVIDER_TEST` for the duration of the call and release it in
`finally`. Their triggering buttons are bound to the gate's state via
`_inference_activity_changed` and are disabled with the tooltip
`Another inference activity is in flight - please wait.` whenever the gate
is held by an activity other than `PROVIDER_TEST`. See
`11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md` §9. The watchdog
auto-release timeout for `PROVIDER_TEST` is 60 seconds
(`08_Cross_Cutting/08-I_edge_cases.md` EC-RUN-14). When `test_inference` is
called and another activity is in flight, the method returns
`InferenceTestResult(outcome=GATE_BUSY, ...)` without issuing a call — the
button gating is the primary defence, the in-method check is the safety net.

## 14. Auto-check on open and embedding bootstrap

- **On every Settings Dialog open**, the dialog requests a readiness refresh so
  the provider Health Dots and the embedding diagnostic reflect current reality
  without the user clicking Test. The request coalesces with any probe already
  in flight (`11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.6); the
  dialog reads the resulting `AppReadinessSnapshot`.
- **First start with no embedding configured** — the app auto-selects the first
  available embedding model found across all enabled providers. If no embedding
  model is available anywhere, the embedding pair is left empty and the user
  must choose one manually; until then `GRADED` is a disabled run mode.

## 15. Validation rules

Validation runs across both tabs before a Save commits (§6 step 2). Severities
follow the application-wide three-severity model.

### 15.1 Hard errors — block Save

| Rule | Surface |
|---|---|
| Two providers share a `name` (case-sensitive). | The duplicate rows' Name cells; the inline message reads `A provider with this name already exists.` (DD-33, EC-PROV-10). |
| A provider has an empty Name. | The provider row. |
| An `openai_compatible` provider (non-Azure) has an empty Base URL. | The provider row. |
| A required API-key field is empty (cloud endpoint), or holds a value that is not a valid environment-variable name. | The provider row; detailed in Provider Edit (`sub_dialogs/provider_edit.md` §5.1, §9). |
| `benchmark.max_timeout_seconds` is less than `benchmark.min_timeout_seconds`. | The Maximum timeout (inference) field. |
| `eval.judge_timeout_max_seconds` is less than `eval.judge_timeout_min_seconds`. | The Judge timeout — maximum field. |
| Any numeric setting is empty or outside its registered range (for example `benchmark.min_timeout_seconds` outside 1–3600, `eval.judge_timeout_min_seconds` outside 1–3600, `eval.judge_timeout_escalation_steps` outside 0–10, `eval.judge_timeout_consecutive_threshold` < 1, or `eval.embedding_timeout_seconds` outside 1–3600). | The offending field. |
| A cosine threshold is outside 0.0–1.0. | The offending threshold field. |

### 15.2 Soft warnings — allow Save, shown inline

| Rule | Note |
|---|---|
| A provider's API-key field names an environment variable that is unset or empty. | The provider Auth badge shows `env ✗`; the provider is usable once the variable is set and the app relaunched. |

### 15.3 Edge inputs

If the user clears a numeric field, the field is treated as empty — a hard error
(§15.1) — not as zero (EC-SET-3). The Save Changes button stays disabled until the
field carries a valid value.

## 16. State transitions

The dialog's state machine is specified fully in `state_machine.md`. In summary:
the dialog opens into `Loaded`; any field change moves it to `Dirty`; a
successful Save returns it to `Loaded`; the sub-dialogs (Provider Edit, Reset
confirmation, Import preview, Discard confirmation) each open on top of the base
dialog and only one is open at a time; the dialog closes from `Loaded` directly
when clean and through the Discard confirmation when dirty.

## 17. Persistence

| State | Persisted | Where |
|---|---|---|
| Provider catalog | On Save / Import / Reset | `providers` + `provider_models` tables, via `ProvidersStore.replace_providers` (which generates UUID4 ids for any row whose `provider_id` is absent; DD-33). |
| Embedding selection | On Save / Import / Reset | `app_settings` keys `embedding.selected_provider_name` / `embedding.selected_model_name`, via `AppSettingsStore.upsert_settings` (no dedicated table). |
| User-saved setting keys | On Save / Import / Reset | `app_settings` table, via `AppSettingsStore.upsert_settings`. Includes the embedding selection keys above. |
| In-memory working copy | Never persisted directly | Discarded on Close without Save. |
| Dialog geometry | Not persisted | The modal opens centred on the parent window each time. |

The dialog never performs a partial write: every persisting action (§6, §8, §9)
is one atomic persistence transaction spanning the `ProvidersStore` and the `AppSettingsStore`. There are no data migrations (DD-53); the
configuration tables evolve additively only.

## 18. Event bus integration

| Signal | Direction | Payload | When |
|---|---|---|---|
| `_provider_registry_reloaded` | emitted | `ProviderRegistryReloadedEvent` | After a Save, Import, or Reset commits — the provider catalog changed. |
| `_app_settings_changed` | emitted | `AppSettingsChangedEvent` | After a Save, Import, or Reset commits — one or more setting keys changed. |
| `_app_readiness_changed` | subscribed | `AppReadinessChangedEvent` | Repaints the provider Health Dots and the embedding diagnostic when a readiness probe resolves. |
| `_provider_inference_test_completed` | emitted, subscribed | `ProviderInferenceTestCompletedEvent` | The Provider Edit sub-dialog emits this when `LLMClient.test_inference` returns; the Providers tab subscribes to refresh the row's summary without re-reading the working copy. |

Payload schemas are in `08_Cross_Cutting/08-J_event_bus_catalog.md` and
`08_Cross_Cutting/08-Q_event_payload_schemas.md`. The dialog's emissions of
`_provider_registry_reloaded` cause the Readiness Service to run a fresh
`probe_all`, which the dialog then observes through `_app_readiness_changed`.

## 19. Service dependencies

The dialog's controller is constructed with these service Protocols (full
contracts in `08_Cross_Cutting/08-E_interfaces_contracts.md`):

| Protocol | Used for |
|---|---|
| `ProvidersStore` | reading and writing the provider catalog (`list_providers`, `get_by_name`, `add(draft)`, `update`, `delete`, `replace_providers`); the provider-side half of the atomic Save / Import / Reset transactions |
| `AppSettingsStore` | reading and writing the user-saved settings layer, **including the embedding selection** keys `embedding.selected_provider_name` / `embedding.selected_model_name`; the settings-side half of the atomic Save / Import / Reset transactions |
| `SettingsService` | resolving the current effective value of each general-tab key |
| `ProviderRegistry` | obtaining `LLMClient` instances for the Test connection probe and model discovery |
| `ReadinessService` | the auto-check on open; reading `AppReadinessSnapshot` for the Health Dots |
| `EventBus` | emitting `_provider_registry_reloaded` / `_app_settings_changed`; subscribing to `_app_readiness_changed` |
| `NotificationService` | the save / export / import / reset toasts and the blocking error notifications |
| `NativePickers` | the Export save picker, the Import file picker, the Task Editor folder picker |
| `FileSystemActions` | the three Open-folder buttons (`open_in_file_manager`) |
| `Clipboard` | the Copy-path button (`copy_text`) |
| Redaction functions | redacting every secret shown in the Import preview and in probe error messages |

## 20. Edge cases

| ID | Description | Handling |
|---|---|---|
| EC-PROV-4 | The provider Test runs against form values, not persisted values. | The probe always reads the in-memory working copy (§13). |
| EC-PROV-5 | A provider's API-key field names an environment variable that is unset or empty. | A soft warning; the Auth badge shows `env ✗`; the provider is usable after the variable is set and the app relaunched. |
| EC-PROV-6 | A value that is not a valid environment-variable name (it looks like an actual key) is entered in the API-key field. | Rejected inline in Provider Edit (`sub_dialogs/provider_edit.md` §5.1); the value cannot be saved until it is a valid name or empty. There is no secret-handling step at Save. |
| EC-PROV-7 | An imported configuration has two providers with the same `id`. | Hard error; the import aborts before the preview. |
| EC-SET-2 | An imported settings file contains keys the build does not know. | The unknown keys are ignored and listed in the preview's Skipped / ignored group; known keys still import. |
| EC-SET-3 | The user clears a numeric setting field (for example `benchmark.min_timeout_seconds`). | The empty field is a hard error; Save Changes stays disabled until a valid value is entered. |
| EC-SET-4 | A run starts while the dialog is somehow open, or the user tries to open the dialog mid-run. | The dialog cannot be opened while a run is in any non-terminal state; the menu action is disabled (`08_Cross_Cutting/08-H_app_modes.md` §10). This case does not arise in practice. |
| EC-SET-5 | Reset to Defaults is clicked while the dialog has unsaved edits. | The confirmation states the working edits will be discarded; on confirm, the wipe-and-reseed replaces everything, working edits included. |

## 21. Function inventory

| Action | Description | Gated by |
|---|---|---|
| Open dialog | Show the Settings Modal Dialog. | No run in a non-terminal state. |
| Switch tab | Change the active tab body. | Dialog open. |
| Edit any field | Mark the dialog dirty. | Dialog open. |
| Add Provider | Open a blank Provider Edit sub-dialog. | Dialog open. |
| Edit Provider | Open the Provider Edit sub-dialog for a row. | Dialog open. |
| Test connection (row) | Run **Test reachability** (`LLMClient.probe_health()`, reachability only — never inference) on the row's working copy. End-to-end **Test inference** lives in the Provider Edit sub-dialog (§13). | Dialog open. |
| Reset Provider (row) | Revert the row's unsaved edits to the persisted value. | The row has unsaved edits, or is session-added. |
| Toggle Provider enabled | Flip `ProviderConfig.enabled` for the row. | Dialog open. |
| Delete Provider | Remove the row from the in-memory catalog. | Dialog open. |
| Select embedding provider / model | Set the working `(provider, embedding model)` selection pair. | Dialog open. |
| Test Embedding | Run the embedding probe on the selected pair. | An embedding pair is selected. |
| Edit a general-tab setting | Set a working setting value. | Dialog open. |
| Open Run Logs folder | Open `<app_data>/logs/run/`. | Dialog open. |
| Open App Logs folder | Open `<app_data>/logs/app/`. | Dialog open. |
| Open App folder | Open `<app_data>/`. | Dialog open. |
| Copy App folder path | Place the app-data path on the clipboard. | Dialog open. |
| Save Changes | Atomic persistence write of providers and embedding (`ProvidersStore`) and settings (`AppSettingsStore`). | Dialog dirty; no hard validation error. |
| Export… | Write the configuration to a YAML file. | Not while a Save is committing. |
| Import… | Replace the configuration from a YAML file, with preview. | Not while a Save is committing. |
| Reset to Defaults | Wipe the configuration and re-seed factory defaults. | Confirmation required. |
| Close | Close the dialog; prompt to discard if dirty. | Always. |
