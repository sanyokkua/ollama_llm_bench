# 08-G — Feature Flag and Setting Registry

**Status:** Draft
**Owner:** architect
**Audience:** coder, architect, tester
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-C_settings_hierarchy.md`, `08_Cross_Cutting/08-H_app_modes.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`

This document is the single registry of every setting, flag, and gating condition in the application. Each entry names a dotted **key**, its **type**, its **default**, the **resolution layer** at which it is read (see `08-C_settings_hierarchy.md`), and the **widgets and services that consume it**. Any time another spec document says "if X is enabled" or "configurable", X must appear here; nothing toggleable exists outside this registry. The registry is exhaustive: it lists every `benchmark.*`, `feature.*`, `eval.*`, `embedding.*`, `ui.*`, `logging.*`, and `task_editor.*` key the application defines.

---

## Table of Contents

1. Resolution layers
2. How to read a registry entry
3. `benchmark.*` — benchmark behaviour
4. `feature.*` — inference and analysis behaviour
5. `eval.*` — evaluation behaviour
6. `embedding.*` — embedding behaviour
7. `ui.*` — UI preferences
8. `logging.*` — logging behaviour
9. `task_editor.*` — Task Editor behaviour
10. Result-table persistence model
11. Behaviour matrices
12. Adding a new flag

---

## 1. Resolution layers

Every key is resolved through the three-layer model defined in `08-C_settings_hierarchy.md`.

| Layer | Symbol | Mutability |
|---|---|---|
| Per-Run Snapshot | `R` | Immutable for a run's lifetime; captured once at run creation |
| User-Saved | `U` | Mutable through the Settings dialog; written to the `app_settings` table |
| Default | `D` | Immutable; defined in the in-code defaults map |

Per-run-overridable keys resolve `R ▶ U ▶ D`. All other keys resolve `U ▶ D` only. The **Per-Run** column in each table below states whether the key belongs to the `PER_RUN_OVERRIDABLE` set. A `✓` means the key is frozen into the run snapshot; a `—` means it is always read live from the user-saved layer.

---

## 2. How to read a registry entry

- **Key** — the dotted `SettingKey` string, stored verbatim in `app_settings.setting_key` (and, for per-run keys, copied into `benchmark_run_settings.setting_key`).
- **Type** — the logical type. All values are serialised to text for storage (`AppSettingRecord.setting_value` and `BenchmarkRunSettingEntry.setting_value` are both `str`); booleans store as `"true"` / `"false"`, integers and floats store as their decimal text form, enums store as their `StrEnum` member value.
- **Default** — the value returned when neither the snapshot nor the user-saved layer holds the key. This is the floor and is never absent.
- **Per-Run** — membership in `PER_RUN_OVERRIDABLE`.
- **Consumed by** — the widgets and services that read the key, and the surface (Settings dialog tab, New Benchmark control) that writes it.

---

## 3. `benchmark.*` — benchmark behaviour

All `benchmark.*` keys are per-run-overridable. They are frozen into the run snapshot at run start; the running pipeline reads only the snapshot.

| Key | Type | Default | Per-Run | Consumed by |
|---|---|---|:--:|---|
| `benchmark.warmup_enabled` | bool | `true` | ✓ | Benchmark Pipeline (pre-loads the model before the first timed inference so cold-load latency does not pollute measurements); New Benchmark advanced options. |
| `benchmark.retry_count` | int (`RetryCount`, 0–10) | `3` | ✓ | Benchmark Pipeline (per-task retry loop); Adaptive Timeout Service. The number of additional inference attempts after the first one fails. |
| `benchmark.max_output_tokens` | int (≥256) | `4096` (DD-67) | ✓ | LLM Client (model under test) — the maximum completion-token budget per inference call, sent as the provider's max-tokens parameter (mandatory for Anthropic). Default 4096 so a reasoning model has room to emit reasoning plus its answer; raise it for very long expected outputs. Settings → Advanced + New Benchmark advanced options; frozen into the run snapshot. |
| `benchmark.temperature` | float (≥0.0) or blank | `0.0` (DD-61) | ✓ | LLM Client (model under test) — sampling temperature for the benchmarked model (D-R-04). **Defaults to `0.0`** so every model in a run is compared at the same low-variance setting (sound cross-model comparison). The user may set any `≥0.0` value (passed through verbatim, **not clamped**; accepted range varies by provider, e.g. 0–1 vs 0–2), or **blank** it to fall back to each provider's own default — in which case different models may run at different effective temperatures and the run is flagged **not directly comparable** (DD-61). Settings → Advanced, with a per-run override in the New Benchmark advanced options; frozen into the run snapshot. No `seed` setting exists (inconsistent provider support). Does **not** apply to the judge call, which is pinned to temperature `0.0` (`08_Cross_Cutting/08-P_judge_protocol.md`). |
| `benchmark.min_timeout_seconds` | int (`TimeoutSeconds`, 1–3600) | `300` | ✓ | Adaptive Timeout Service — the budget for a task's first inference attempt. |
| `benchmark.max_timeout_seconds` | int (`TimeoutSeconds`, 1–3600) | `900` | ✓ | Adaptive Timeout Service — the ceiling the adaptive budget grows toward across retries. |
| `benchmark.consecutive_max_timeouts_to_exclude` | int (≥1) | `3` | ✓ | Adaptive Timeout Service (role=INFERENCE) — the number of consecutive max-timeout failures for one `(provider, model)` pair AT THE INFERENCE ROLE after which that model is excluded from the rest of the run. Judge-role exclusion is governed by the parallel `eval.judge_timeout_consecutive_threshold` key (§5). |
| `benchmark.pause_on_phase_switch` | bool | `false` | ✓ | Benchmark Pipeline — when `true`, the pipeline auto-pauses each time it transitions between phases (for example inference → keyword check), letting the user inspect intermediate state before continuing. This is the canonical pause key. |
| `benchmark.pause_on_provider_switch` | bool | `false` | ✓ | Benchmark Pipeline — auto-pause when the pipeline moves to the next provider. |
| `benchmark.pause_on_model_switch` | bool | `false` | ✓ | Benchmark Pipeline — auto-pause when the pipeline moves to the next test model. |
| `benchmark.stop_on_provider_health_failure` | bool | `false` | ✓ | Provider Circuit Breaker → Benchmark Pipeline — when `true`, the run terminates with `RunStatus.FAILED` if a provider trips its circuit breaker; when `false`, the affected results are recorded as `FAILED_PROVIDER` and the run continues. |
| `benchmark.last_mode` | enum `RunMode` (`synthetic`, `tasks`, `graded`) | `synthetic` | — | New Benchmark widget — the run mode preselected when the widget opens. Written after every successful run start. Not per-run-overridable: it is a UI convenience, not a run input. |

**Adaptive timeout interaction (role=INFERENCE).** `benchmark.min_timeout_seconds`, `benchmark.max_timeout_seconds`, `benchmark.retry_count`, and `benchmark.consecutive_max_timeouts_to_exclude` jointly parameterise the Adaptive Timeout Service **for role=INFERENCE** (Phase 2 — test-role inference). The first attempt uses the minimum budget; each retry raises the budget toward the maximum; a model that hits the maximum budget on `benchmark.consecutive_max_timeouts_to_exclude` consecutive tasks is excluded **from the test-role bucket only** for the remainder of the run, and its remaining tasks are recorded as `FAILED_TIMEOUT`. The Phase 4 per-task judge call (role=JUDGE) AND the user-initiated run-analysis generation call (role=RUN_ANALYSIS — an independent bucket, DD-65) use a **separate** adaptive-timeout ladder from inference, both parameterised by the `eval.judge_timeout_*` keys in §5; the `benchmark.*` keys above do NOT govern judge or analysis calls. Embedding calls use a **fixed** `eval.embedding_timeout_seconds` budget — no adaptive escalation, no exclusion. Test Inference and readiness probes use their own fixed deadlines and never consult the Adaptive Timeout Service.

---

## 4. `feature.*` — inference and analysis behaviour

All `feature.*` keys are per-run-overridable.

| Key | Type | Default | Per-Run | Consumed by |
|---|---|---|:--:|---|
| `ui.stream_tokens_to_log` | bool | `true` | — | **Live UI/log preference (SPEC-116; renamed from `feature.streaming_enabled`).** When `true`, the Progress widget log panel echoes inference tokens as they arrive; when `false`, the full response is shown only when the inference completes. It is a **live `ui.*` setting — NOT per-run-overridable and NOT frozen into the run snapshot**, because it has **no effect on computed results or reproducibility** (backend streaming is always on regardless — it is how the pipeline measures TTFT). It takes effect immediately, including mid-run. A `(provider, model)` whose transport cannot stream yields a null `ttft_ms`, unaffected by this preference. |
| `feature.reasoning_effort_default` | enum `ReasoningEffort` (`default`, `low`, `medium`, `high`) | `default` | ✓ | Benchmark Pipeline (sets `ChatRequest.reasoning_effort` for each test inference); New Benchmark advanced options. Models without the `REASONING_EFFORT` capability ignore the parameter. |
| `feature.judge_run_analysis_enabled` | bool | mode-dependent: `false` in `SYNTHETIC` and `TASKS`, `true` in `GRADED` | ✓ | Benchmark Pipeline (whether to generate the consolidated run-level analysis narrative, `BenchmarkRun.run_analysis`); New Benchmark "Generate run analysis" toggle. **Optional — controlled by the "Generate run analysis" toggle; default ON in GRADED, OFF in SYNTHETIC and TASKS.** The toggle is **visible in every mode** and the user can override the default in either direction; the New Benchmark per-run override always takes priority over the stored user-saved value. A judge model is required when this toggle is ON (any mode) or when the per-task judge phase is enabled (`GRADED` only); when neither condition holds, no judge model is required. |

---

## 5. `eval.*` — evaluation behaviour

All `eval.*` keys are per-run-overridable. The three evaluation phases — keyword, cosine, and judge — each have an independent enable toggle, surfaced in Settings → Evaluation. **Every `eval.*` key applies only in `GRADED`.** `SYNTHETIC` and `TASKS` never run any grading phase, so these keys are ignored when the run mode is one of those two — the values are still snapshotted into the run for traceability, but the pipeline does not consult them. Within Graded Benchmark, a run may execute with the judge phase off (keyword and cosine only), or with any single phase active.

| Key | Type | Default | Per-Run | Consumed by |
|---|---|---|:--:|---|
| `eval.phase_keyword_enabled` | bool | `true` | ✓ | Benchmark Pipeline (keyword phase); Settings → Evaluation toggle. When off, the keyword phase is skipped and `BenchmarkResult.keyword_verdict` stays null. **Applies only in `GRADED`; ignored in `SYNTHETIC` and `TASKS`.** |
| `eval.phase_cosine_enabled` | bool | `true` | ✓ | Benchmark Pipeline (cosine-similarity phase); Settings → Evaluation toggle. When off, the cosine phase is skipped and `BenchmarkResult.cosine_similarity` / `.cosine_verdict` stay null. **Applies only in `GRADED`; ignored in `SYNTHETIC` and `TASKS`.** |
| `eval.phase_judge_enabled` | bool | `true` | ✓ | Benchmark Pipeline (per-task LLM judge phase); Settings → Evaluation toggle. When off, the per-task judge phase is skipped and `BenchmarkResult.judge_verdict` stays null. **Applies only in `GRADED`; ignored in `SYNTHETIC` and `TASKS`.** Disabling this key does **not** disable the run-level judge analysis — that is governed separately by `feature.judge_run_analysis_enabled` (§4). |
| `eval.force_judge_on_prior_failure` | bool | `false` (DD-62) | ✓ | Benchmark Pipeline — default `false` (DD-62): a deterministic keyword **FAIL** short-circuits and stands as the final verdict (the cheap deterministic phases decide; no judge call is spent on an already-failed task). Set `true` to make the judge the authoritative final gate that runs and decides even over an earlier keyword/cosine `FAIL`. **Independently of this flag, a response that fails the sanity pre-check (empty / error-marker) is never sent to the judge** (nothing to grade; DD-62). Has effect only when `eval.phase_judge_enabled` is `true`. **Applies only in `GRADED`; ignored in `SYNTHETIC` and `TASKS`.** |
| `eval.cosine_threshold` | float (`CosineThreshold`, 0.0–1.0) | `0.85` | ✓ | Cosine Evaluator — the single user-configured pass/fail cutoff for the whole-text Cosine Score (DD-45). Consulted only when the cosine phase runs. |
| `eval.judge_max_completion_tokens` | int (≥256) | `4096` (DD-67) | ✓ | Judge call — maximum completion-token budget (raised from the former 512 so a reasoning judge can emit its reasoning before the JSON verdict; mandatory for Anthropic). Settings → Advanced; `GRADED` and run-analysis. |
| `eval.judge_timeout_min_seconds` | int (`TimeoutSeconds`, 1–3600) | `20` | ✓ | Adaptive Timeout Service — the budget for a per-task judge call's first attempt and the floor of the ladder; also the floor of the **independent** role=RUN_ANALYSIS bucket (DD-65). Consulted only in `GRADED` (per-task judge) and whenever the user-initiated run analysis runs. |
| `eval.judge_timeout_max_seconds` | int (`TimeoutSeconds`, 1–3600) | `120` | ✓ | Adaptive Timeout Service (role=JUDGE) — the ceiling the judge budget grows toward across the escalation ladder; the budget at which timeouts count toward judge-role exclusion. Must satisfy `eval.judge_timeout_min_seconds <= eval.judge_timeout_max_seconds`. |
| `eval.judge_timeout_escalation_steps` | int (≥0, ≤10) | `2` | ✓ | Adaptive Timeout Service (role=JUDGE) — the number of intermediate budget rungs between min and max; `0` collapses the ladder to a single rung at the floor. Consulted only when the judge call is executing or being retried. |
| `eval.judge_timeout_consecutive_threshold` | int (≥1) | `3` | ✓ | Adaptive Timeout Service (role=JUDGE) — the number of consecutive max-budget judge timeouts for one `(provider, model)` pair AT THE JUDGE ROLE after which that model is excluded for the rest of the run. Triggers the `_judge_model_excluded` event; every remaining task that would have entered the judge phase settles to `FAILED_JUDGE_TIMEOUT` directly. |
| `eval.embedding_timeout_seconds` | int (`TimeoutSeconds`, 1–3600) | `30` | ✓ | Embedding Service — **fixed** per-request budget for every embedding call (cosine-phase main embedding and keyword-phase semantic terms). **NOT adaptive.** On timeout the task's cosine phase fails for that task; the binary verdict cascade (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.6) settles per D-012. A stalled embedding model keeps being retried task after task — there is no exclusion, no consecutive-max threshold, no per-role bucket. |
| `eval.min_sample_size` | int (≥1) | `5` | ✓ | Chart Aggregators & Run Analysis Service — the minimum number of completed results a per-model group must hold before its aggregate (pass rate, mean cosine, mean TPS, etc.) is presented as authoritative (D-R-04, MISS-02). Groups below this `n` are flagged as low-sample in charts and the analysis narrative so a tiny sample is not shown like a large one. Every aggregate also surfaces its `n`. |
| `eval.embedding_consecutive_failures_to_skip` | int (≥1) | `3` | ✓ | Embedding Service (DD-70) — after this many consecutive embedding failures/timeouts in a run, the cosine phase is skipped run-wide for the remaining tasks (a one-time notice is shown); bounds the worst-case dead time of a stalled embedding model from `N×30s` to `K×30s`. The run is not failed; keyword/judge still grade. `GRADED` only. |
| `eval.min_cosine_coverage` | float (0.0–1.0) | `0.8` | ✓ | Summary tab, Chart Aggregators & Run Analysis Service (DD-63) — the minimum share of a model's **cosine-eligible** completed tasks (tasks with a golden answer and `cosine_enabled`) that must actually carry a Cosine Score before the model's mean cosine is treated as evenly covered. When a model's coverage is below this AND at least one other model in the run is at/above it, that model's cosine aggregate is flagged **partial coverage** (intermittent embedding failures graded it on fewer tasks than its peers), so an uneven-basis comparison is never shown as if equal. `GRADED` only. |

**Phase outputs.** The keyword and cosine phases are mechanical and produce a binary phase verdict (`Verdict.PASS` / `Verdict.FAIL`); the cosine phase additionally produces a numeric `cosine_similarity` (the Cosine Score, the application's only numeric quality metric). The judge phase produces a binary verdict plus a free-text `judge_reasoning` comment; it produces **no numeric score**. The combined `BenchmarkResult.verdict` is decided by the highest enabled phase that ran, and `BenchmarkResult.resolution_layer` records which phase decided it.

**Judge timeout interaction (role=JUDGE).** `eval.judge_timeout_min_seconds`, `eval.judge_timeout_max_seconds`, `eval.judge_timeout_escalation_steps`, and `eval.judge_timeout_consecutive_threshold` jointly parameterise the Adaptive Timeout Service **for role=JUDGE**. The escalation ladder works the same way as the role=INFERENCE ladder (`07_ADAPTIVE_TIMEOUT.md`), but with the judge-specific floor, ceiling, and exclusion threshold. These keys parameterise **two independent buckets** (DD-65): the role=JUDGE bucket used by the Phase 4 per-task judge calls (during a `BENCHMARK_RUN`), and a separate role=RUN_ANALYSIS bucket used by the user-initiated run-analysis generation call (during a `JUDGE_ANALYSIS`). Each keeps its own last-known-good and its own in-run consecutive-timeout counter — the run-analysis prompt never inherits a per-task judge LKG already at the ceiling, so it gets full escalation headroom. A judge model that crosses `eval.judge_timeout_consecutive_threshold` consecutive max-budget timeouts during a `BENCHMARK_RUN` is excluded for that run's remaining tasks (each remaining task that would have entered the judge phase settles to `FAILED_JUDGE_TIMEOUT`); a judge model that exhausts the ladder during a `JUDGE_ANALYSIS` invocation produces a `RunAnalysisResult` with outcome `FAILED` and reason `judge_timeout_exhausted`. Per-role independence: a model excluded at role=JUDGE remains usable at role=INFERENCE, and vice versa.

**Embedding timeout (fixed).** `eval.embedding_timeout_seconds` is a strictly fixed per-call deadline for the Embedding Service. No adaptive escalation, no exclusion, no per-role bucket: on a timeout the affected task's cosine phase fails, the binary verdict cascade settles per D-012, and the next task's embedding call uses the same fixed budget afresh.

---

## 6. `embedding.*` — embedding behaviour

The `embedding.*` keys are not per-run-overridable. The embedding model selection itself is stored as two of these keys — `embedding.selected_provider_name` and `embedding.selected_model_name` (the single selected `(provider, embedding model)` pair, by name; see D-R-13 and `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §4.4). There is no separate embedding-config table or record. The selection is read live from the user-saved layer **outside a run** (Settings dialog, capability probe, readiness); **at run start** it is resolved once and frozen into the run snapshot (the `embedding_provider_name`/`embedding_model_name` header pair and the `EMBEDDING`-role `benchmark_run_models` row); **during the run and on resume** only the frozen pair is used — never re-resolved from live settings (`11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` §6.2; Run Drift Detector DD-57 checks the frozen pair's availability at resume).

| Key | Type | Default | Per-Run | Consumed by |
|---|---|---|:--:|---|
| `embedding.selected_provider_name` | string | `""` | — | Embedding service, readiness probe, run-creation snapshot — the **name** of the provider hosting the selected embedding model. Empty until the first-start probe or the user picks one in Settings; when empty (or unresolvable) `GRADED` is disabled. |
| `embedding.selected_model_name` | string | `""` | — | Embedding service, readiness probe, run-creation snapshot — the selected embedding model string. Paired with `embedding.selected_provider_name`. |
| `embedding.hide_from_test_models` | bool | `true` | — | Test Models picker (New Benchmark) — when `true`, model names that look like embedding models are filtered out of the test-model list so they cannot be benchmarked as chat models. |
| `embedding.additional_patterns` | string (comma-separated) | `""` | — | Embedding-model classifier — extra substring patterns, beyond the built-in set, that mark a model name as embedding-like. |

---

## 7. `ui.*` — UI preferences

The `ui.*` keys are visual preferences, never per-run-overridable. They are always read live from the user-saved layer.

| Key | Type | Default | Per-Run | Consumed by |
|---|---|---|:--:|---|
| `ui.theme` | enum (`system`, `dark`, `light`) | `system` | — | Application theme. |
| `ui.score_display_format` | enum (`decimal`, `percent`, `letter`) | `decimal` | — | Result widget Summary and Details tables — formatting of pass-rate and Cosine Score values. |
| `ui.window_geometry` | opaque | `""` | — | Main Window — restored window position and size on launch. |
| `ui.splitter_sizes` | opaque | `""` | — | Benchmark workspace — restored three-panel splitter sizes. |
| `ui.active_workspace` | enum (`benchmark`, `task_editor`) | `benchmark` | — | Workspace Controller — the workspace restored on launch. Written on every workspace switch. |
| `ui.last_result_tab` | string | `summary` | — | Result widget — the tab shown first when the widget opens. |
| `ui.task_editor_last_folder` | string | `""` | — | Task Editor — default folder for the Open / Open Folder / New File pickers. Written after each successful open or save. |
| `ui.export_save_directly` | bool | `false` | — | Result widget footer (all four tabs and detached chart windows) — when `true`, every Export button writes straight to `<app_data>/exports/` and the `Open App Folder` button is shown; when `false`, every Export click opens a save picker defaulted to the user's Desktop. |
| `ui.run_log_verbosity` | enum (`short`, `normal`, `verbose`) | `normal` | — | Progress widget log panel — initial field density. Live-switchable while a run is in progress. |
| `ui.run_log_max_lines` | int (`1000`–`500000`) | `100000` | — | Progress widget log panel — user-configurable cap on the in-memory display buffer. The panel renders one line per pipeline event, so the cap counts events and lines interchangeably (1:1). When the buffer is full the oldest line is dropped to admit the newest (rolling drop); the per-run log *file* is never trimmed and always keeps every event. Hard-bounded so the panel's memory stays bounded by `cap × per-line memory` (each line itself bounded by the 4000-character redaction cap); a value outside the range is clamped to the nearest bound. |
| `ui.auto_scroll_run_log` | bool | `true` | — | Progress widget log panel — whether the panel auto-scrolls to the newest line. |

The per-run result-table view state (filters, column visibility, column order) is **not** stored under fixed `ui.*` keys; it is persisted per run. See §10.

---

## 8. `logging.*` — logging behaviour

The `logging.*` keys affect the log writers, not the run computation, and are never per-run-overridable.

| Key | Type | Default | Per-Run | Consumed by |
|---|---|---|:--:|---|
| `logging.write_run_log_to_file` | bool | `true` | — | Run-log file writer — when `false`, the run log is kept in memory only and no per-run log file is written. |
| `logging.write_app_log_to_file` | bool | `true` | — | App-log file writer — toggle for the `<app_data>/logs/app/app.log` writer. |
| `logging.app_log_level` | enum (`trace`, `debug`, `info`, `warn`, `error`) | `info` | — | Root logger — minimum level filter. Takes effect immediately. Friendly values map to standard Python `logging` levels: `trace`→custom `TRACE` (below `DEBUG`), `debug`→`DEBUG`, `info`→`INFO`, `warn`→`WARNING`, `error`→`ERROR`; `CRITICAL` is always emitted (see `12_Quality_and_NFRs/03_OBSERVABILITY.md` §2). |
| `logging.app_log_max_file_mb` | int (`1`–`50`) | `10` | — | Rotating app-log writer — maximum size in MB of a single app-log file before it rotates. User-configurable within the hard bounds; clamped if out of range. |
| `logging.app_log_max_total_mb` | int (`app_log_max_file_mb`–`200`) | `60` | — | Rotating app-log writer — hard ceiling in MB for the **total** disk used by the app log (current file plus all backups). User-configurable up to a 200 MB hard maximum; must be ≥ `app_log_max_file_mb` and is clamped if out of range. The number of backup files kept is **derived**: `floor(app_log_max_total_mb / app_log_max_file_mb)` files in total (the current file plus its backups), so the on-disk total can never exceed this ceiling. At the defaults (60 / 10) the writer keeps the current file plus five backups, i.e. 60 MB across six 10 MB files. |

The per-run log file is always written at **Verbose** field density regardless of `ui.run_log_verbosity`; that key changes only what the on-screen panel shows.

---

## 9. `task_editor.*` — Task Editor behaviour

The `task_editor.*` keys are editor preferences, never per-run-overridable.

| Key | Type | Default | Per-Run | Consumed by |
|---|---|---|:--:|---|
| `task_editor.auto_format_on_save` | bool | `true` | — | YAML Formatter — when `true`, Save rewrites each task file with fields in canonical order and multi-line strings as YAML literal blocks. |
| `task_editor.warn_on_empty_grading_criteria` | bool | `true` | — | Task File Validator — when `true`, an empty `pass_criteria` or `fail_criteria` raises a soft warning instead of passing silently. |

---

## 10. Result-table persistence model

The Result widget's Summary and Details tables each carry view state: the active **filter-chip selection**, the **column visibility** set, and the **column order**. This state is persisted **per run**, not as a single global preference.

**Resolution rule.**

| Situation | View state used |
|---|---|
| A run is opened for the first time (a newly created run, or any run never previously selected in the Result widget) | The built-in **default** view state for that table and the run's mode — default filters (all selected), default column visibility, default column order. |
| A previously-opened run is reopened | The **last saved** view state for that run — the filters, visibility, and order the user left it in. |

**Storage.** The per-run view state is stored keyed by `run_id` (see `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` for the storage table). When a new run is created it has no stored view state, so the defaults apply; when the user changes a filter, hides or shows a column, or reorders columns, the new state is written back against that `run_id`. A run thus remembers how the user last looked at it.

**Charts tab.** The Charts tab carries its own per-run view state by the same rule — the per-chart-kind filter selection, hidden legend series, last-opened chart kind, and outlier-exclusion toggle are stored against `run_id` and follow the same new-run-defaults / reopened-run-restores behaviour.

---

## 11. Behaviour matrices

### 11.1 Visibility and enablement per workspace

| Function | Benchmark workspace | Task Editor workspace |
|---|---|---|
| Workspace switcher | visible, active = `benchmark` | visible, active = `task_editor` |
| Running pill | visible if a run is non-terminal | visible if a run is non-terminal |
| Settings menu-bar action | enabled (disabled while a run is non-terminal) | enabled (disabled while a run is non-terminal) |
| About menu-bar action | visible | visible |
| Editor Toolbar (Open / New / Save / Reload / View YAML) | not present | visible |
| Tasks-pane controls (Add / Duplicate / Remove / Move Task) | not present | visible |
| Status-bar provider readiness | shown | hidden — replaced by editor counts |

There is **no File, Edit, View, or Help menu.** Task Editor operations live on the Editor Toolbar and the Tasks pane, which are present only in the Task Editor workspace.

### 11.2 Visibility per run mode

| Section / setting | `SYNTHETIC` | `TASKS` | `GRADED` |
|---|:--:|:--:|:--:|
| Input Sizes / Output Sizes / Repeats | ✓ | — | — |
| Task Files | — | ✓ | ✓ |
| "Generate run analysis" toggle (`feature.judge_run_analysis_enabled`) | shown — default OFF, optional | shown — default OFF, optional | shown — default ON, optional (user may turn off to skip the extra inference cost) |
| Keyword phase (`eval.phase_keyword_enabled`) | not applicable — no grading | not applicable — no grading | Settings → Evaluation toggle |
| Cosine phase (`eval.phase_cosine_enabled`) | not applicable — no grading | not applicable — no grading | Settings → Evaluation toggle |
| Per-task judge phase (`eval.phase_judge_enabled`) | not applicable — no grading | not applicable — no grading | Settings → Evaluation toggle |
| `eval.force_judge_on_prior_failure` consulted | — | — | only when `eval.phase_judge_enabled` is on |
| `eval.cosine_threshold` consulted | — | — | only when the cosine phase is on |
| Embedding model required at run start | — | — | ✓ |

### 11.3 When operations are blocked

| Operation | Blocked when |
|---|---|
| Open Settings dialog | A benchmark run is in any non-terminal state, including paused. |
| Switch workspace | Never blocked. If the Task Editor has dirty buffers, a save / discard / cancel prompt appears first. |
| Start benchmark | No test model selected, or no task files for `TASKS` / `GRADED`, or `GRADED` without a ready embedding model, or any other start precondition fails. |
| Save in Task Editor | The active file has at least one hard validation error. |
| Delete a run | The run is currently executing. |
| Resume a run | The run is currently executing, or the run has no pending results to resume. |

The full composite blocked-states contract — the exact disabled control and tooltip for each case — is in `08-H_app_modes.md` §10.

---

## 12. Adding a new flag

When the application is extended with a new toggle:

1. Add the entry to the matching section of this registry with its key, type, default, per-run flag, and consumers.
2. Add the default to the in-code defaults map (the Default layer).
3. Add a control to the appropriate Settings dialog tab, or — if the key is per-run-overridable — expose it on the New Benchmark widget.
4. Add the key to `PER_RUN_OVERRIDABLE` if, and only if, the user should be able to override it for a single run.
5. Update `08-C_settings_hierarchy.md` if the per-run-overridable set changed.
