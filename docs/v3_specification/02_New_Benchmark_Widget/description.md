# New Benchmark Widget — Description

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:**
`02_New_Benchmark_Widget/state_machine.md`,
`02_New_Benchmark_Widget/flow_diagram.md`,
`02_New_Benchmark_Widget/implementation_structure.md`,
`02_New_Benchmark_Widget/mockup.html`,
`02_New_Benchmark_Widget/mode_specifics/synthetic.md`,
`02_New_Benchmark_Widget/mode_specifics/tasks.md`,
`02_New_Benchmark_Widget/mode_specifics/graded.md`,
`07_Common_Dialogs/run_summary_dialog.md`,
`08_Cross_Cutting/08-E_interfaces_contracts.md`,
`08_Cross_Cutting/08-G_feature_flags.md`,
`08_Cross_Cutting/08-H_app_modes.md`,
`08_Cross_Cutting/08-I_edge_cases.md`,
`08_Cross_Cutting/08-J_event_bus_catalog.md`,
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`,
`11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`,
`11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md`

The New Benchmark widget is the configure-and-start surface of the Benchmark workspace.
It occupies the left panel's "New Benchmark" tab and lets the user pick a run mode,
select the models to test, supply the workload (synthetic sizes or real task files),
optionally configure a judge, override execution settings for the run, and launch the
benchmark. Its layout is mode-conditional: which sections are visible is decided entirely
by the Mode Visibility Policy. Starting a run produces a confirmed `RunStartEvent` that the
Run Configuration Controller turns into a snapshotted run.

---

## Table of Contents

1. Role and ownership
2. Layout
3. Run modes and the mode selector
4. Section catalog
5. Behaviour per element
6. Validation rules
7. State transitions
8. Persistence
9. Event bus integration
10. Service dependencies
11. Per-mode payload — `RunStartEvent`
12. Section-visibility decision table
13. Edge cases
14. Function inventory

---

## 1. Role and ownership

The widget is responsible for:

- Presenting the three run modes and remembering the last-used mode.
- Collecting the run configuration: test models, task files or performance matrix,
  judge selection, and per-run execution overrides.
- Running the Run Validator on every configuration change and reflecting the result on the
  Start button.
- Building a `RunStartEvent` and routing it through the Run Summary Dialog for final
  confirmation.
- Locking itself read-only once a run starts.

The widget is **not** responsible for:

- Executing the benchmark — that is the Benchmark Pipeline.
- Persisting runs or results — that is the Data Store, invoked by the Run Configuration
  Controller.
- Editing task files — that is the Task Editor workspace.
- Resolving global settings defaults — it reads them through the Settings Store at
  construction time.

The widget owns no domain state beyond the in-progress configuration. The selected
`(provider, model)` pairs live in a selection store held by the Run Configuration
Controller; the widget mutates that store and renders from it.

## 2. Layout

A single vertically scrolling panel rendered at the default left-panel width
(approximately 360 px). Top to bottom:

| Region | Content |
|---|---|
| Mode selector | Radio List of the three run modes (always visible) |
| Conditional body | Performance Matrix, Judge, Test Models, Task Files, Advanced Options — shown or hidden per mode |
| Footer | Sticky Start button |

The conditional body is a column of Section primitives. Each Section is either shown or
removed from the layout (not merely disabled) according to the Mode Visibility Policy.
Section order is fixed; only visibility changes. See `mockup.html` for the three rendered
modes.

## 3. Run modes and the mode selector

The widget supports three values of `RunMode` (see
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`):

| `RunMode` enum value | Display name | Row caption (verbatim) | Purpose |
|---|---|---|---|
| `SYNTHETIC` | **Synthetic Benchmark** | `Synthetic prompt sizes; measures throughput` | Synthetic input/output sizes; measures TTFT, tokens/sec, total time; no real tasks |
| `TASKS` | **Task Benchmark** | `Your task files; throughput only; no grading` | Real task files; measures throughput only; Task Benchmark never grades |
| `GRADED` | **Graded Benchmark** | `Your task files; full grading pipeline` | Real task files; full five-phase batched evaluation pipeline |

The mode selector is a Radio List at the top of the panel. **UI display order** is fixed:
Synthetic Benchmark, Task Benchmark, Graded Benchmark. Each row is 32 px tall and shows a 16 px icon,
the display name, and a one-line description. The **Row caption** column above is the
canonical, verbatim one-line description string rendered under each mode's display name;
it is the source of truth for that copy.

- The selected mode persists to the user setting `benchmark.last_mode`. Its default value
  is `SYNTHETIC`.
- On widget construction the selector restores `benchmark.last_mode`.
- Changing the mode emits the `mode_changed` cross-component signal, which drives the
  Mode Visibility Policy lookup and re-renders section visibility.
- The selector is interactive only when no run is in a non-terminal stage
  (`08_Cross_Cutting/08-H_app_modes.md`). While a run is active the whole widget is
  read-only.

## 4. Section catalog

### 4.1 Mode selector

Always visible. See §3.

### 4.2 Performance Matrix — Synthetic Benchmark only

Three Sections shown together when `mode == SYNTHETIC`:

| Group | Primitive | Content |
|---|---|---|
| **Input Sizes** | 5 Toggles | `XS — ~5 tok · 1 sentence · 7 words`, `SM — ~50 tok · 1 paragraph · 70 words`, `MD — ~250 tok · 1 page · 380 words`, `LG — ~1500 tok · long doc · 2300 words`, `XL — ~3500 tok · very long · 5300 words` |
| **Output Sizes** | 5 Toggles | `XS — ~1 sentence · ~15 words · ~25 tok`, `SM — ~5 sentences · ~75 words · ~125 tok`, `MD — ~20 sentences · ~300 words · ~500 tok`, `LG — ~100 sentences · ~1500 words · ~2500 tok`, `XL — ~500 sentences · ~7500 words · ~12500 tok` |
| **Repeats** | Number Stepper | Range 1..20, default 3 |

**Default selection.** When the widget first opens in Synthetic Benchmark (no prior session
state), the size matrix opens with **XS and SM pre-checked in both Input Sizes and Output
Sizes**, and MD / LG / XL unchecked. This gives a runnable default configuration out of
the box (the live estimate opens non-zero). The performance-matrix selection is not
persisted across sessions (§8); each fresh construction restores this XS+SM default rather
than the last session's choice.

A live counter under the Repeats stepper shows the estimated task total. The estimate is
computed from the Performance Task Generator's task-count formula (see
`11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md` — one deterministic prompt
per cell; there is no prompt-template axis), fanned out per model:

```text
estimated_tasks = N_input_sizes × N_output_sizes × N_repeats × N_models
```

where `N_models` is the count of selected `(provider, model)` pairs (one result row per
task × model). When the **Generate run analysis** toggle is ON, the estimate line appends
`+ 1 run-analysis inference` — one extra LLM call performed once after the run; it
produces no result row and is not part of the task count.

**This live estimate exists only in `SYNTHETIC`.** The estimate formula differs per mode:
`TASKS` and `GRADED` have no repeats axis — their totals come from the parsed task files
(`total_tasks × N_models` inference calls, plus per-task judge calls in `GRADED` when the
judge phase is enabled, plus the same `+ 1` run-analysis inference when the toggle is ON)
and are presented in the Run Summary dialog's **Work to be done** line
(`07_Common_Dialogs/run_summary_dialog.md` §6).

### 4.3 Task Files — Task Benchmark and Graded Benchmark

A Section shown when `mode in {TASKS, GRADED}`:

- Header: **"Task Files"** with a secondary action **"Open in Task Editor"** on the
  right.
- Body: a List View with drag-and-drop. The empty state shows a centred dashed-border
  drop zone with the text **"Drop YAML task files or folders here"**. Both the empty
  placeholder and the populated list accept drops.
- Footer: **Add File**, **Add Folder**, **Remove** Buttons.
- Each row shows the file name plus a per-file Badge:
  - `(N tasks)` — the parsed task count, read once from the Task File Loader on add and
    cached.
  - `*` — a dirty marker shown when the file path is currently dirty in the Task Editor,
    sourced from the `_task_file_changed` event and Task Editor state. Tooltip:
    "Unsaved changes in Task Editor — saved tasks may differ from on-disk tasks shown
    here."

The **Open in Task Editor** action switches to the Task Editor workspace via the
Workspace Controller. When one or more rows are selected, it opens each selected path as a
buffer; when no row is selected, it opens the editor with no files.

### 4.4 Judge

A collapsible Section, visible in all modes:

- Toggle **"Generate run analysis for this run"** — controls whether the post-run
  narrative analysis is generated (authored by the configured judge model; it is a
  run-level narrative, not per-task grading). **Optional — controlled by the "Generate run analysis"
  toggle; default ON in `GRADED`, OFF in `SYNTHETIC` and `TASKS`.** The
  toggle is **visible in every mode** and the user can override the default in either
  direction. The toggle does not persist; it applies only to this run and is captured in
  the run settings snapshot (`08_Cross_Cutting/08-G_feature_flags.md`).
- Dropdown **Judge Provider** — the shared `ui/shared/provider_dropdown` widget
  (`11_Services_and_Algorithms/01_SERVICE_INVENTORY.md` §3.1), populated from enabled
  providers via the Provider Registry. Emits `provider_changed(provider_id)`.
- Dropdown **Judge Model** — the shared `ui/shared/model_dropdown` widget
  (`11_Services_and_Algorithms/01_SERVICE_INVENTORY.md` §3.1), wired by this widget so
  every `provider_changed` from the Judge Provider dropdown triggers
  `judge_model_dropdown.set_provider(provider_id)`. The model dropdown is configured with a
  filter that excludes embedding-style models (the same predicate the
  `EmbeddingModelClassifier` applies, intersected with `embedding.hide_from_test_models`).
  Emits `model_changed(model_name)`.
- Button **Refresh** — a small **text button labelled "Refresh"** (not an icon-only
  button), placed inline in the Judge section-title row; tooltip "Refresh the judge
  provider's model list". Re-fetches the model list for the selected judge provider.

The two dropdowns are independent widgets; this widget wires them together as the
consumer (see `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md` §3.1).

Behaviour by mode:

- `GRADED` — the per-task judge phase (Settings → Evaluation) and the run-analysis
  toggle both default ON in this mode, so the judge picker is **required by default**. If
  the user disables **both** the per-task judge phase and the run-analysis toggle, the
  judge picker becomes optional and may be left empty — the Start button accepts that
  configuration. When a judge is required and no enabled judge provider exists, Start is
  disabled with an explanatory tooltip.
- `SYNTHETIC` — the judge call is optional and the analysis toggle defaults OFF.
  When the toggle is OFF the provider and model dropdowns remain **visible but greyed out**
  (recorded for resume consistency; the analysis will not run), matching the System
  Performance mockup. When the toggle is ON and no judge provider is enabled, the dropdowns
  are empty and the Section shows a warning: "No enabled provider for judging. Open Settings
  to add one."
- `TASKS` — the judge call is optional and the analysis toggle defaults OFF. When the
  toggle is OFF the provider and model dropdowns are **hidden** (the Judge Section shows only
  the toggle and its note), matching the Task Benchmark mockup; turning the toggle ON reveals the
  dropdowns. When the toggle is ON and no judge provider is enabled, the dropdowns are empty
  and the Section shows a warning: "No enabled provider for judging. Open Settings to add one."

Per-task judge validation (phase 5) is a separate stage controlled by Settings, not by
this widget — see `mode_specifics/graded.md`.

### 4.5 Embedding — Graded Benchmark only

A read-only status row inside the Judge Section, shown when `mode == GRADED`. It
reports whether an enabled embedding provider and model are configured (needed for
keyword-semantic terms in phase 3 and cosine similarity in phase 4). The embedding model
itself is configured in Settings, not here.

The row has two states:

- **Ready (ok / green).** When the embedding selection is resolved (an enabled embedding
  provider and model are configured) **and** reachable, the row renders in the
  `success.base` colour role and reads, verbatim:

  > Embedding: {provider_display} · {embedding_model} — ready for keyword-semantic and cosine validation.

  (e.g. `Embedding: Ollama (local) · nomic-embed-text — ready for keyword-semantic and cosine validation.`)
  The trailing clause "ready for keyword-semantic and cosine validation" states the two
  phases the embedding feeds (phase 3 keyword-semantic terms, phase 4 cosine similarity);
  "ready" means the embedding is both **resolved** (selected in Settings) and **reachable**
  (the provider responds to a readiness probe).

- **Warning.** When no embedding is configured (or it is unreachable) the row shows a
  warning in the `warning.base` role and contributes a hard validation error (see §6).

### 4.6 Test Models

A Section visible in all modes:

- Header: **"Test Models"** in the section-title row, with the **Refresh** text button
  inline on the right of that title. Directly in the header area, a **Checkbox labelled
  "Hide embedding models"**, bound to `embedding.hide_from_test_models` and **checked by
  default** (matching the `embedding.hide_from_test_models` default of `true` —
  `08_Cross_Cutting/08-G_feature_flags.md`). It is a **transient view filter** over the
  available-models list only: when checked, models that look like embedding models are
  hidden from the available list; it never changes which `(provider, model)` pairs are
  selected. (Its checked state persists via `embedding.hide_from_test_models`; its effect
  on the list is non-destructive.)
- Dropdown **Provider** — shows all enabled providers; the user browses one provider at a
  time.
- Button **Refresh** — a small **text button labelled "Refresh"** (not an icon-only
  button), placed inline in the Test Models section-title row. Re-fetches the model list
  for the browsed provider.
- **Available Models** List View with a Toggle per row, each row showing the model name.
  Toggling a row adds or removes the `(provider, model)` pair in the selection store.
- **Select All** / **Clear All** Buttons, scoped to the currently browsed provider.
- **Selected Models Summary** — a scrollable List View, min height 120 px, max height
  240 px, header "Selected models (N across M providers)", each row showing
  `provider · model`.

All selected `(provider, model)` pairs are preserved across provider switches so the
widget supports multi-provider selection.

### 4.7 Advanced Options

A **collapsible Section gated by an activation checkbox**, visible in all modes. The section header carries a checkbox labelled **"Override advanced options for this run"**. The section is **collapsed and the checkbox is unchecked by default**: in this default state the controls are hidden and the run uses each value's currently-effective global setting (the `User-Saved ▶ Default` resolution of `08_Cross_Cutting/08-C_settings_hierarchy.md`), with no per-run override.

When the user **checks** the activation checkbox the section **expands** to reveal its controls; each control is pre-filled with the current global value from the Settings Store and may be changed for this run only. **Unchecking** it collapses the section again and discards the per-run edits, so the run reverts to the global values. Changes made while expanded are not written back to global settings; the values in effect at Start — whether the global defaults (checkbox off) or the user's per-run edits (checkbox on) — are captured into the run settings snapshot when the benchmark starts (`08_Cross_Cutting/08-G_feature_flags.md`). The collapsed/expanded state is purely a per-session view state and is not persisted. (PySide6 implements the section as a checkable, collapsible group — e.g. a checkable `QGroupBox` or an equivalent collapsible container.)

Inference controls:

| Control | Primitive | Default from | Meaning |
|---|---|---|---|
| **Enable Warmup** | Toggle | `benchmark.warmup_enabled` | Whether a warmup inference precedes the measured run for each model |
| **Reasoning Effort** | Dropdown | `feature.reasoning_effort_default` | One of `default`, `low`, `medium`, `high` |
| **Max Output Tokens** | Number Stepper | `benchmark.max_output_tokens` | Maximum completion-token budget for the model under test (DD-67). Default 4096; always sent (Anthropic requires it). Raise for very long expected outputs. Frozen into the run snapshot. |
| **Temperature** | Number Stepper (blank-able) | `benchmark.temperature` | Sampling temperature for the model under test (D-R-04). **Defaults to `0.0`** (DD-61) so the run's models are compared at the same setting; a set value is passed verbatim and **not** clamped (accepted range varies by provider, e.g. 0–1 vs 0–2). **Blanking** it falls back to each provider's own default — the widget then shows a muted note **"Temperatures may differ across models — results not directly comparable"**, mirrored in the Run Summary. Applies only to the benchmarked model, never the judge (pinned to `0.0`). No `seed` control — provider support is inconsistent. Frozen into the run snapshot. |

Adaptive timeout and retry controls:

| Control | Primitive | Default from | Meaning |
|---|---|---|---|
| **Minimum timeout (s)** | Number Stepper | `benchmark.min_timeout_seconds` | The starting per-request timeout for each model |
| **Maximum timeout (s)** | Number Stepper | `benchmark.max_timeout_seconds` | The ceiling the timeout escalates toward; must be ≥ minimum |
| **Retry count** | Number Stepper | `benchmark.retry_count` | How many retry attempts a recoverable failure gets. The timeout escalates across the [minimum, maximum] range over these attempts |
| **Max max-timeout failures before exclusion** | Number Stepper | `benchmark.consecutive_max_timeouts_to_exclude` | When a model accumulates this many consecutive failures at the maximum timeout, it is excluded from the run and its remaining tasks are marked failed |

Run-boundary controls:

| Control | Primitive | Default from | Meaning |
|---|---|---|---|
| **Pause at phase switch** | Toggle | `benchmark.pause_on_phase_switch` | Auto-pause at each phase boundary |
| **Pause at provider switch** | Toggle | `benchmark.pause_on_provider_switch` | Auto-pause when the run moves to the next provider |
| **Pause at model switch** | Toggle | `benchmark.pause_on_model_switch` | Auto-pause when the run moves to the next model (time to unload/load local models) |
| **Stop on provider health failure** | Toggle | `benchmark.stop_on_provider_health_failure` | Stop the run when a provider health check fails mid-run |

Evaluation controls — **shown only in `GRADED`** (hidden, not greyed, in `TASKS` and `SYNTHETIC`, per `08-L` §1 — no grading phase runs there):

| Control | Primitive | Default from | Meaning |
|---|---|---|---|
| **Keyword phase** | Toggle | `eval.phase_keyword_enabled` | Enable/disable the keyword check for this run |
| **Cosine phase** | Toggle | `eval.phase_cosine_enabled` | Enable/disable the cosine check for this run |
| **Judge phase** | Toggle | `eval.phase_judge_enabled` | Enable/disable the per-task judge for this run |
| **Force judge after prior failure** | Toggle | `eval.force_judge_on_prior_failure` | Judge even results an earlier phase failed |
| **Cosine threshold** | Number Stepper (0.0–1.0) | `eval.cosine_threshold` | The single pass/fail cutoff for the whole-text Cosine Score (DD-45) |
| **Judge timeout min / max (s)** | Number Steppers | `eval.judge_timeout_min_seconds` / `eval.judge_timeout_max_seconds` | The role=JUDGE adaptive-timeout bounds; max must be ≥ min |
| **Judge timeout escalation steps** | Number Stepper | `eval.judge_timeout_escalation_steps` | Rungs of the judge timeout ladder |
| **Judge consecutive-timeout threshold** | Number Stepper | `eval.judge_timeout_consecutive_threshold` | Consecutive max-budget judge timeouts before judge exclusion |
| **Embedding timeout (s)** | Number Stepper | `eval.embedding_timeout_seconds` | Fixed per-call budget for embedding calls |
| **Minimum sample size** | Number Stepper | `eval.min_sample_size` | Below this `n`, chart groups are flagged low-sample |

**Completeness rule (DD-47).** The Advanced Options section exposes **every** key the
settings registry flags as per-run-overridable (`08_Cross_Cutting/08-G_feature_flags.md`,
the ✓ column), except `feature.judge_run_analysis_enabled`, which is the form's primary
analysis toggle. Adding a per-run-overridable key to the registry REQUIRES adding its
control here; a UI test compares the section's control map against `PER_RUN_OVERRIDABLE`
and fails on any gap.

**Carriage rule (DD-47).** Controls are seeded from the `User-Saved ▶ Default` resolution.
With the override checkbox ON, only the keys whose value the user **changed** from the
seeded value are carried on `RunStartRequest.setting_overrides` (registry-keyed
`BenchmarkRunSettingEntry` rows, values in registry storage form); an absent key keeps the
saved value, which snapshot step 1 already captured (`08-C` §5).

Below the four adaptive-timeout-and-retry steppers, the section shows a single canonical
explanatory note, verbatim:

> Each retry uses a longer timeout from the [min, max] range. A model failing this many
> times at the maximum is excluded; its remaining tasks are marked failed.

This note is **shown in all three modes** (it is not mode-conditional) because the adaptive
timeout and retry controls themselves are visible in all modes (§12). Where the mockup's
Task Benchmark panel omits the note, that omission is **incidental to the mockup** and not a
behavioural difference — the note is rendered identically in Synthetic Benchmark, Task Benchmark, and
Graded Benchmark.

Retries apply only to recoverable failures (provider unavailability, connection
interruption, inference timeout). Validation failures are never retried.

### 4.8 Start button

A primary Button **"Start Benchmark"** sticky at the bottom of the panel footer. It is
enabled only when the Run Validator returns no hard errors **and** the application-wide
single-inference gate (`InferenceActivityStore`,
`08_Cross_Cutting/08-E_interfaces_contracts.md` §13) is `IDLE`. While the gate is held by
any activity (`BENCHMARK_RUN`, `JUDGE_ANALYSIS`, `PROVIDER_TEST`, or `READINESS_PROBE`)
the button is disabled with the tooltip `Another inference activity is in flight — please
wait.` The widget subscribes to `_inference_activity_changed`
(`08_Cross_Cutting/08-J_event_bus_catalog.md` §5.7) so the button re-enables atomically
when the gate returns to `IDLE`. Clicking it builds the `RunStartEvent` and opens the Run
Summary Dialog (`07_Common_Dialogs/run_summary_dialog.md`) for final confirmation. On
Accept the widget fires the event to the Run Configuration Controller; the Benchmark
Pipeline then acquires `BENCHMARK_RUN` on the store for the duration of the run (see
`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §9 and
`08_Cross_Cutting/08-B_benchmark_state_machine.md` §12 invariant 10).

## 5. Behaviour per element

| Element | Enabled when | Effect on use |
|---|---|---|
| Mode Radio List | No run in a non-terminal stage | Emits `mode_changed`; persists `benchmark.last_mode`; re-renders section visibility; re-validates |
| Input/Output Size Toggles | `mode == SYNTHETIC` | Toggle the size in the performance matrix; re-compute the task estimate; re-validate |
| Repeats Stepper | `mode == SYNTHETIC` | Set repeat count 1..20; re-compute the task estimate |
| Add File / Add Folder | `mode in {TASKS, GRADED}` | Open the OS file/folder picker; parse picked YAML via the Task File Loader; append rows; re-validate |
| Remove | A Task File row is selected | Remove selected rows; re-validate |
| Task File drop target | `mode in {TASKS, GRADED}` | Accept dragged YAML files or folders; parse and append rows |
| Open in Task Editor | `mode in {TASKS, GRADED}`; Workspace Controller available | Switch to the Task Editor workspace; open selected paths as buffers |
| Judge analysis Toggle | Always (visible in every mode; default OFF in `SYNTHETIC` / `TASKS`, default ON in `GRADED`) | Store value in panel state; do not persist; included in `RunStartEvent` |
| Judge Provider Dropdown | Judge enabled or `GRADED` | Repopulate the Judge Model dropdown |
| Judge Model Dropdown | A judge provider is chosen | Set the judge model |
| Judge Refresh | A judge provider is chosen | Re-fetch the judge provider's model list |
| Hide embedding models Checkbox (checked by default) | Always | Persist `embedding.hide_from_test_models`; re-filter the available and judge model lists |
| Test Models Provider Dropdown | At least one enabled provider | Render the available models for the chosen provider |
| Test Models Refresh | A provider is chosen | Re-fetch the provider's model list |
| Available Models Toggles | A provider is chosen | Add/remove the `(provider, model)` pair in the selection store; update the summary; re-validate |
| Select All / Clear All | A provider is chosen | Add/remove all of the browsed provider's models |
| Toggle "Override advanced options for this run" | Always | Expand/collapse the Advanced Options section. OFF (default) = collapsed, controls hidden, run uses global defaults; ON = expanded, controls become editable per-run overrides. Unchecking discards the per-run edits. |
| Advanced Options controls | Section expanded (override ON) | Set the per-run override value; re-validate (timeout pair) |
| Start Benchmark | Run Validator returns no hard error | Build `RunStartEvent`; open the Run Summary Dialog |

## 6. Validation rules

Before showing the Run Summary Dialog, and on every configuration change, the panel runs
the **Run Validator**. It returns a list of entries, each with a severity (`hard error`
or `soft warning`) and a message. Hard errors block Start; soft warnings are surfaced in
the Run Summary Dialog and the user may proceed.

| Condition | Severity | Message |
|---|---|---|
| 0 models selected | hard error | "Select at least one model to test." |
| Mode needs tasks (`TASKS`/`GRADED`) and no task files added | hard error | "Add at least one task file." |
| `SYNTHETIC` and no input × output combination checked | hard error | "Select at least one input size and one output size." |
| No enabled judge provider while either the per-task judge phase is enabled or the run-analysis toggle is ON (any mode) | hard error | "A judge model is required when the per-task judge phase or the run-analysis toggle is on. Add an enabled provider in Settings, or disable both toggles." |
| `GRADED`, no embedding configured, and keyword-semantic or cosine validation is enabled in Settings | hard error | "Graded Benchmark uses cosine similarity (phase 4). Configure an embedding model in Settings, or disable cosine validation." |
| Maximum timeout < Minimum timeout | hard error | "Maximum timeout must be greater than or equal to the minimum timeout." |
| A selected model's provider does not advertise backend streaming support | soft warning | "Backend streaming is not advertised for one or more selected models — TTFT may be unmeasurable for those rows." |

When a hard error is present, the Start button is disabled and its tooltip lists the
reasons. When only soft warnings are present, Start is enabled and its tooltip reads
"Click to review warnings before starting."

## 7. State transitions

The widget moves through: **Loading** (constructed, restoring providers and mode) →
**Idle** (interactive, continuously re-validating) → **Confirming** (Run Summary Dialog
open) → **Starting** (event fired, awaiting `_run_started`) → **Locked** (read-only
for the duration of the run). Clicking Back in the Run Summary Dialog returns to Idle. The full
diagram, including the section-visibility, Test Models, Task Files, and Judge
sub-machines, is in `state_machine.md`.

## 8. Persistence

| State | Persisted | Where |
|---|---|---|
| Selected run mode | Yes | User setting `benchmark.last_mode` |
| Hide embedding models toggle | Yes | User setting `embedding.hide_from_test_models` |
| Judge analysis toggle | No | Per-run only; captured in the run settings snapshot |
| Selected `(provider, model)` pairs | No | In-memory selection store; cleared on run start |
| Task file list | No | In-memory; cleared on run start |
| Performance matrix selection | No | In-memory; cleared on run start |
| Advanced Options overrides | No | Per-run only; captured in the run settings snapshot |

Advanced Options controls are seeded from the Settings Store at construction; editing them
does not write back to global settings.

## 9. Event bus integration

Signals subscribed (all subscriptions ownership-bound to the widget; see
`08_Cross_Cutting/08-J_event_bus_catalog.md`):

| Signal | Handler behaviour |
|---|---|
| `_provider_registry_reloaded` | Rebuild the Test Models and Judge provider dropdowns with enabled providers; keep the selection if still present, else select the first |
| `_task_file_changed` | Refresh the dirty `*` markers and re-count tasks for the affected Task Files rows |
| `_workspace_changed` | When the workspace returns to `benchmark`, refresh Task Files dirty markers |
| `_run_started` | Transition to Locked; render the whole widget read-only |
| `_run_finished` / `_run_failed` / `_run_stopped` | Return to Idle; re-enable the widget |
| `_inference_activity_changed` | Enable or disable the Start button based on the gate state (the Start button is `IDLE`-only); update its tooltip |

Signals emitted:

| Signal | When |
|---|---|
| `RunStartEvent` (to the Run Configuration Controller) | The user confirms the Run Summary Dialog |
| `mode_changed` (cross-component, in-process) | The user changes the run mode |

## 10. Service dependencies

The widget factory consumes these dependency Protocols (constructor injection):

| Protocol | Used for |
|---|---|
| `SettingsStore` | Read defaults for Advanced Options, `benchmark.last_mode`, `embedding.hide_from_test_models` |
| `ProviderRegistry` | Enumerate enabled providers; fetch model lists for Test Models and Judge |
| `EventBus` | Subscribe to provider/task/run signals; publish `RunStartEvent` |
| `TaskFileLoader` | Parse YAML task files on add and report task counts |
| `RunValidator` | Compute validation entries for the current configuration |
| `ModeVisibilityPolicy` | Map `(mode, flags)` to the visible section set |
| `WorkspaceController` | Switch to the Task Editor workspace for "Open in Task Editor" |
| `ReadinessService` | Report whether providers, judge, and embedding are reachable for the selected mode |
| `InferenceActivityStore` | Disable the Start button while the application-wide single-inference gate is held by any activity (consumed via the `_inference_activity_changed` event) |

## 11. Per-mode payload — `RunStartEvent`

The Start button builds a `RunStartEvent` (see
`08_Cross_Cutting/08-E_interfaces_contracts.md`):

```text
RunStartEvent {
    run_mode: RunMode                       // SYNTHETIC | TASKS | GRADED
    test_models: tuple[tuple[str, str], ...] // all (provider_id, model_name) pairs
    task_paths: tuple[str, ...]              // task-file paths; empty in SYNTHETIC
    performance_config: PerformanceConfig?   // matrix config if SYNTHETIC, else null
    judge_provider: str                      // "" when no judge provider chosen
    judge_model: str                         // "" when no judge model chosen
    judge_analysis_enabled: bool             // run-level analysis toggle (default ON in GRADED, OFF in SYNTHETIC/TASKS; user-overridable in every mode)
    advanced_options_overridden: bool        // Advanced Options activation checkbox; false (default) = section collapsed, run uses global defaults; true = section expanded, the fields below are per-run overrides (§4.7)
    advanced_values: dict[SettingKey, str]   // every §4.7 control's current value, seeded from the Settings Store (registry keys, storage form — DD-47)
    advanced_dirty: frozenset[SettingKey]    // the keys the user changed; only these are carried on RunStartRequest.setting_overrides
}
```

The Run Configuration Controller snapshots every per-run-overridable field into
`run.run_settings_snapshot` at run start.

## 12. Section-visibility decision table

| Section | `SYNTHETIC` | `TASKS` | `GRADED` |
|---|---|---|---|
| Mode selector | Visible | Visible | Visible |
| Performance Matrix (Input/Output Sizes, Repeats) | Visible | Hidden | Hidden |
| Judge | Visible (analysis toggle default OFF; judge optional) | Visible (analysis toggle default OFF; judge optional) | Visible (analysis toggle default ON; judge required by default — optional only if both the per-task judge phase and the analysis toggle are disabled) |
| Embedding status row | Hidden | Hidden | Visible |
| Test Models | Visible | Visible | Visible |
| Task Files | Hidden | Visible | Visible |
| Advanced Options | Visible | Visible | Visible |
| Start button | Visible | Visible | Visible |

Visibility is computed by the Mode Visibility Policy
(`11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`), which maps `(mode, flags)` to
the visible section set. The widget never hard-codes per-mode conditionals.

**Scope of "Greyed" (mockup legend).** The mockup's legend defines three states — **Visible**
(section rendered for this mode), **Hidden** (section removed from the layout), and **Greyed**
(visible but interactive children disabled). The **Greyed** state is **not** a general,
sanctioned pattern: `08_Cross_Cutting/08-L_ui_standardization.md` §1 is a hard rule that a
control which does not apply is **hidden, not greyed out**. In this widget there is exactly
**one** legitimate greyed case, and the legend's "Greyed" entry refers **only** to it: the
**Synthetic Benchmark Judge provider/model dropdowns when the "Generate run analysis" toggle
is OFF** — they stay visible but disabled so the (unused) selection is recorded for
resume/snapshot consistency (§4.4; `state_machine.md` `ControlsGreyed`). Every other
non-applicable section in the matrix above is **Hidden**, never greyed. The "Greyed" legend
term must therefore not be read as permission to grey out any other control.

## 13. Edge cases

Referenced by ID from `08_Cross_Cutting/08-I_edge_cases.md`:

- **EC-RUN-1** — Start clicked while a run is already running. The widget is already Locked,
  so this cannot occur from this surface; the Start button is non-interactive.
- **EC-RUN-3** — Start with no reachable providers for selected models. The Run Validator
  raises a hard error; Start is disabled.
- **EC-TASK-1** — Malformed YAML file dropped or added. The Task File Loader rejects the file;
  the widget shows an inline error and does not add the row.
- **EC-TASK-2** — Duplicate `task_id` across loaded files. The widget shows a soft warning in
  the Run Summary Dialog.
- **EC-TASK-3** — Task missing required fields. The offending task is skipped at load time;
  the file's `(N tasks)` Badge reflects the surviving count.
- **EC-TASK-8** — Folder picker selects a folder with no YAML files. The widget shows an
  inline message and adds no rows.
- **EC-PROV-5** — A plain API key references an unset environment variable. The Run Validator
  raises a hard error; Start is blocked.
- **EC-WS-1** — Workspace switch while a detached chart is open. Referenced when the user
  uses "Open in Task Editor"; handled by the Workspace Controller.

## 14. Function inventory

| Function | Primitive | Gated by |
|---|---|---|
| Select run mode | Radio List | No run in a non-terminal stage |
| Toggle "Generate run analysis for this run" | Toggle | Always (visible in every mode; default OFF in `SYNTHETIC` / `TASKS`, default ON in `GRADED`) |
| Pick Judge Provider | Dropdown | Enabled providers exist; no run active |
| Pick Judge Model | Dropdown | A judge provider is chosen |
| Refresh judge model list | Button (text "Refresh") | A judge provider is chosen |
| Set Input Sizes / Output Sizes | Toggles | `mode == SYNTHETIC` |
| Set Repeats | Number Stepper | `mode == SYNTHETIC` |
| Add File / Add Folder / Remove task files | Buttons | `mode in {TASKS, GRADED}` |
| Drag-drop task files | Drop target | `mode in {TASKS, GRADED}` |
| Open in Task Editor | Button | `mode in {TASKS, GRADED}`; Workspace Controller available |
| Browse provider in Test Models | Dropdown | Enabled providers exist |
| Pick Test Models | List View Toggles | A provider is browsed |
| Select All / Clear All | Buttons | A provider is browsed |
| Toggle Hide embedding models | Checkbox (checked by default) | Always; persists `embedding.hide_from_test_models` |
| Toggle Enable Warmup | Toggle | Always; per-run override |
| Pick Reasoning Effort | Dropdown | Always; per-run override |
| Set Temperature | Number Stepper (blank-able) | Always; per-run override; blank ⇒ provider default; not clamped |
| Set Minimum / Maximum timeout (s) | Number Steppers | Always; per-run override; max ≥ min |
| Set Retry count | Number Stepper | Always; per-run override |
| Set Max max-timeout failures before exclusion | Number Stepper | Always; per-run override |
| Start Benchmark | Primary Button | Run Validator returns no hard error |
