# Ollama LLM Bench — V2 High-Level Implementation Plan

**Date**: 2026-04-15  
**Purpose**: Structured, dependency-ordered plan for all V2 changes. Written to be consumed phase-by-phase by Claude Code in planning mode — each phase section is self-contained enough to generate a detailed task list with pseudocode, diagrams, and state machines.

**Downstream workflow**: Pick a phase → feed to Claude → Claude creates detailed plan with pseudocode/diagrams → feed to Claude Code in planning mode → Claude Code creates implementation task list → implements tasks one by one with context cleanup after each.

---

## Table of Contents

- [Design Philosophy & Core Decisions](#design-philosophy--core-decisions)
- [Phase 0 — Foundational Contracts](#phase-0--foundational-contracts)
  - [0.1 — Database Schema V2](#01--database-schema-v2)
  - [0.2 — Task YAML Format V2](#02--task-yaml-format-v2)
  - [0.3 — Provider Configuration File](#03--provider-configuration-file)
- [Phase 1 — Provider Abstraction Layer](#phase-1--provider-abstraction-layer)
  - [1.1 — Provider Interface & Registry](#11--provider-interface--registry)
  - [1.2 — OpenAI-Compatible Generic Client](#12--openai-compatible-generic-client)
  - [1.3 — Native Cloud Providers (Anthropic, Gemini)](#13--native-cloud-providers-anthropic-gemini)
  - [1.4 — Embedding Provider](#14--embedding-provider)
  - [1.5 — Model Descriptor & Name Parsing](#15--model-descriptor--name-parsing)
- [Phase 2 — Execution Engine V2](#phase-2--execution-engine-v2)
  - [2.1 — Dual-Mode Inference (Sync + Streaming)](#21--dual-mode-inference-sync--streaming)
  - [2.2 — Execution Order & Scheduling](#22--execution-order--scheduling)
  - [2.3 — Event System & Configurable Pause/Stop](#23--event-system--configurable-pausestop)
  - [2.4 — Progress Reporting & Structured Logging](#24--progress-reporting--structured-logging)
- [Phase 3 — Evaluation Pipeline V2](#phase-3--evaluation-pipeline-v2)
  - [3.1 — Speed Mode (Metrics Only)](#31--speed-mode-metrics-only)
  - [3.2 — Full Grading Mode (4-Layer Pipeline)](#32--full-grading-mode-4-layer-pipeline)
  - [3.3 — Prompt Evaluation Mode](#33--prompt-evaluation-mode)
- [Phase 4 — Settings & Feature Flags](#phase-4--settings--feature-flags)
  - [4.1 — Provider Configuration UI](#41--provider-configuration-ui)
  - [4.2 — Feature Flags & App Settings UI](#42--feature-flags--app-settings-ui)
- [Phase 5 — UI Redesign](#phase-5--ui-redesign)
  - [5.1 — Global Layout & Design System](#51--global-layout--design-system)
  - [5.2 — Run Configuration Panel (Left)](#52--run-configuration-panel-left)
  - [5.3 — Progress & Log Panel (Center)](#53--progress--log-panel-center)
  - [5.4 — Results Panel (Right)](#54--results-panel-right)
  - [5.5 — Settings Dialog](#55--settings-dialog)
- [Phase 6 — Quality & Packaging](#phase-6--quality--packaging)
  - [6.1 — Test Infrastructure](#61--test-infrastructure)
  - [6.2 — Cross-Platform Packaging](#62--cross-platform-packaging)
- [Dependency Map](#dependency-map)
- [V1 → V2 Migration Summary](#v1--v2-migration-summary)

---

## Design Philosophy & Core Decisions

These decisions are non-negotiable constraints that every phase must respect:

### 1. Drop the `ollama` Python SDK entirely

Ollama exposes an OpenAI-compatible endpoint at `/v1/`. The native `ollama` SDK returns provider-specific metrics (`eval_count`, `eval_duration`) measured inside the Ollama process. The `openai` SDK returns `usage.completion_tokens` and the client measures wall-clock time. These two approaches produce **different numbers for the same run** — mixing them makes cross-provider comparisons meaningless. V2 uses the OpenAI-compatible endpoint for Ollama, giving truly equal metrics across all providers.

### 2. Both sync AND streaming inference — ADD, not replace

Sync (blocking `.create()`) and streaming (`.stream()` / SSE) serve different purposes. Streaming captures TTFT (time-to-first-token). Sync is simpler and better for structured output. Both modes are implemented per client. The run configuration selects which mode to use.

### 3. Single `OpenAICompatibleProvider` for all local providers

Ollama, LM Studio, llama.cpp, and OpenAI cloud all speak the same REST protocol. One generic client handles all — only `base_url` and `api_key` differ. This is configured in `providers.yaml`. Only Anthropic and Google Gemini require separate SDK clients.

### 4. Standardized metrics everywhere

All performance metrics (`total_time_ms`, `ttft_ms`, `tokens_per_second`) are computed from wall-clock measurements or the standard `usage` block in OpenAI responses. No provider-specific fields. This is the only way comparisons across providers are meaningful.

### 5. `bge-m3` as default embedding model

Multilingual (covers all languages in the task dataset), good semantic similarity performance. Configurable via `providers.yaml` and Settings UI.

### 6. Structured judge output

The judge model returns JSON matching a fixed schema (`verdict`, `score`, `reasoning`). Where the provider supports `response_format` / structured output, enforce at API level. Otherwise parse raw JSON with fallback.

### 7. Architecture invariants (carried from V1)

1. `core/` — pure Python only. No Qt, no `openai`, no `yaml`. Holds dataclasses, enums, Protocols, SQL strings, prompt templates.
2. `services/` — no Qt. All provider/data/task/eval logic here.
3. All threading lives in `qt_classes/` only.
4. UI updates only via `QtEventBus` signals. No widget mutation from background threads.
5. All dependencies injected via constructor (keyword-only args).
6. Absolute imports only.

---

## Phase 0 — Foundational Contracts

Phase 0 defines the three data contracts every later phase depends on. Nothing in Phase 1–6 can be correctly designed without Phase 0 locked.

---

### 0.1 — Database Schema V2

**Current state**: 2 tables — `benchmark_runs` (4 fields), `results` (11 fields). Schema in `core/sql_constants.py`. Foreign keys declared but `PRAGMA foreign_keys = ON` not issued.

**What changes**: Expand to 5 tables. Enable `PRAGMA foreign_keys = ON`. Add schema versioning for future migrations.

**Migration strategy**: On first V2 launch, check `schema_version.version`. If absent or < 2, run `ALTER TABLE` migrations adding new nullable columns. Old V1 rows remain readable — all new fields default to NULL. V1 `results` rows map to V2 `benchmark_results` with new fields NULL.

---

#### Table: `schema_version`

Tracks applied migrations. Allows future ALTER-based upgrades without destructive schema drops.

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `version` | `INTEGER` | `PRIMARY KEY` | `2` | Tracks which schema version is active; migration runner checks this on startup | `SqLiteDataApi._init_db()` on creation; migration runner on upgrade | `SqLiteDataApi._init_db()` to decide if migrations are needed |
| `applied_at` | `TEXT` | `NOT NULL` | `"2026-04-15T10:30:00"` | Audit trail for when schema was upgraded | Migration runner | Diagnostics / debug logging |

---

#### Table: `benchmark_runs`

One row per run initiated by the user. Extended with mode, provider identity, and task tracking fields.

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `run_id` | `INTEGER` | `PK AUTOINCREMENT` | `7` | Unique run identifier; join key for benchmark_results | `SqLiteDataApi.insert_benchmark_run()` | All result queries; Results tab run selector |
| `timestamp` | `TEXT` | `NOT NULL` | `"2026-04-15T10:00:00.000"` | When the run was created; shown in run selector dropdown and sorting | `NewRunWidgetController.handle_start_click()` | Results tab run selector; Previous Runs tab |
| `run_mode` | `TEXT` | `NOT NULL` | `"full_grading"` | Which benchmark mode was used — `"speed"`, `"full_grading"`, or `"prompt_eval"`; determines which columns are relevant in Results display | `NewRunWidgetController` | Results tab (column visibility logic); export formatting |
| `judge_provider_id` | `TEXT` | `NOT NULL` | `"ollama_local"` | Which provider serves the judge model; needed for re-run and audit | `NewRunWidgetController` | Results tab header; re-run logic |
| `judge_model` | `TEXT` | `NOT NULL` | `"qwen3:8b"` | Judge model name; displayed in results and used for re-run | `NewRunWidgetController` | Results tab; Previous Runs display |
| `embedding_provider_id` | `TEXT` | nullable | `"ollama_local"` | Which provider serves the embedding model; NULL if cosine not used (speed mode) | `NewRunWidgetController` | Results tab; audit trail |
| `embedding_model` | `TEXT` | nullable | `"bge-m3"` | Embedding model name; NULL if cosine not used | `NewRunWidgetController` | Results tab |
| `status` | `TEXT` | `NOT NULL` | `"COMPLETED"` | `BenchmarkRunStatus` enum: `NOT_COMPLETED`, `COMPLETED`, `FAILED`. Drives resumability | `BenchmarkExecutionTask` on status transitions | Previous Runs tab (resume indicator); run selector |
| `task_file_paths` | `TEXT` | `NOT NULL` | `'["tasks/coding.yaml","tasks/text.yaml"]'` | JSON list of task file paths used; needed for resume (reload same tasks) and audit | `NewRunWidgetController` (JSON-serialized) | Resume logic; audit trail |
| `models_json` | `TEXT` | `NOT NULL` | `'[{"provider_id":"ollama_local","model_name":"llama3.1:8b"}]'` | JSON list of `ModelDescriptor` objects for all test models in this run | `NewRunWidgetController` (JSON-serialized) | Resume logic; results grouping |
| `total_tasks` | `INTEGER` | `NOT NULL` | `539` | Total task count (models × tasks); set after initialization stage | `BenchmarkExecutionTask` after init | Progress display |
| `completed_tasks` | `INTEGER` | `NOT NULL DEFAULT 0` | `341` | Running counter of completed tasks; updated on each task completion | `BenchmarkExecutionTask` per task | Progress display; resume progress |

---

#### Table: `benchmark_results`

One row per `(run, task, model)` triple. Replaces V1 `results`. All fields organized into 12 logical groups. All new fields are nullable so V1 migrated rows (with NULLs for new fields) remain valid.

**Group 1 — Record Identity**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `result_id` | `INTEGER` | `PK AUTOINCREMENT` | `1042` | Unique row key for updates and references | `SqLiteDataApi.insert_result()` | Update queries; detail views |
| `run_id` | `INTEGER` | `NOT NULL FK → benchmark_runs` | `7` | Links this result to its parent run | `BenchmarkExecutionTask` at init | All result queries; Results tab |
| `run_type` | `TEXT` | `NOT NULL` | `"full_grading"` | Denormalized from `benchmark_runs.run_mode` for faster query filtering without join | Copied from run at insert | Results tab display logic |
| `created_at` | `TEXT` | `NOT NULL` | `"2026-04-15T10:05:00.000"` | When this result row was created; enables ordering | `BenchmarkExecutionTask` at row creation | Sort ordering; audit |
| `completed_at` | `TEXT` | nullable | `"2026-04-15T10:05:45.231"` | When this result reached terminal state; enables duration calculation | `BenchmarkExecutionTask` on COMPLETED/FAILED | Duration reporting |

**Group 2 — Provider & Model Identity**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `provider_id` | `TEXT` | `NOT NULL` | `"ollama_local"` | Which provider served inference for this result; enables per-provider grouping | `BenchmarkExecutionTask` at init | Results grouping; filter UI |
| `provider_type` | `TEXT` | `NOT NULL` | `"openai_compatible"` | Which client class to use; needed for resume | From `ModelDescriptor.provider_type` | Resume logic; diagnostics |
| `model_name` | `TEXT` | `NOT NULL` | `"llama3.1:8b-instruct-q4_K_M"` | Full model name string; primary grouping key in results | `BenchmarkExecutionTask` | Results tables; export |
| `model_family` | `TEXT` | nullable | `"llama3"` | Parsed from model name; enables family-level comparison charts | `ModelNameParser` service at insert | Results visualization grouping |
| `model_size_b` | `REAL` | nullable | `8.0` | Parsed from model name; enables size-tier comparisons | `ModelNameParser` service at insert | Results visualization axis |
| `quantization_label` | `TEXT` | nullable | `"q4_K_M"` | Parsed from model name; enables quantization comparison | `ModelNameParser` service at insert | Results grouping |

**Group 3 — Task Identity**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `task_id` | `TEXT` | `NOT NULL` | `"coding_java_two_sum_indices"` | Matches `BenchmarkTask.task_id`; enables per-task drill-down | `BenchmarkExecutionTask` at init | Detailed results table; filter |
| `task_category` | `TEXT` | `NOT NULL` | `"Coding"` | Denormalized from task; enables category filter without reloading YAML | Copied from `BenchmarkTask.category` | Category filter in Results; breakdown charts |
| `task_type` | `TEXT` | `NOT NULL` | `"code_generation"` | Controls eval pipeline routing — which layers run and which judge prompt template loads | Copied from `BenchmarkTask.task_type` | Eval pipeline router; judge prompt service |
| `task_difficulty` | `TEXT` | nullable | `"medium"` | Enables difficulty breakdown analysis in results | Copied from `BenchmarkTask.difficulty` | Results charts |
| `response_scope` | `TEXT` | nullable | `"covers"` | Controls Layer 3 cosine similarity strategy | Copied from `BenchmarkTask.response_scope` | `CosineSimilarityEvaluator` |
| `source_language` | `TEXT` | nullable | `"en"` | For translation tasks; enables language-pair analysis | Copied from task | Judge prompt addendum; results filter |
| `target_language` | `TEXT` | nullable | `"fr"` | For translation tasks | Copied from task | Judge prompt addendum; results filter |

**Group 4 — Prompt Snapshot**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `prompt_version` | `TEXT` | `NOT NULL DEFAULT "v1"` | `"v2-assertive"` | For Prompt Eval mode: identifies which prompt variant was used; for normal mode: always `"v1"` | `BenchmarkExecutionTask` | Prompt Eval comparison view |
| `prompt_hash` | `TEXT` | `NOT NULL` | `"sha256:a3f8..."` | Deduplication key; detects prompt changes between runs | Computed from final rendered prompt | Prompt change detection |
| `user_prompt_sent` | `TEXT` | `NOT NULL` | `"Write a Java function..."` | Full rendered user prompt actually sent to model; enables exact reproduction | `BenchmarkExecutionTask` | Log display; Prompt Eval comparison |
| `system_prompt_sent` | `TEXT` | nullable | `"You are a helpful..."` | System prompt if one was used | `BenchmarkExecutionTask` | Audit trail |
| `golden_answer` | `TEXT` | `NOT NULL` | `"public int[] twoSum(..."` | Reference answer for this task; used by cosine layer and judge prompt | Copied from `BenchmarkTask.golden_answer` | `CosineSimilarityEvaluator`; `LLMJudgeEvaluator` |

**Group 5 — Raw Inference Output**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `raw_response` | `TEXT` | nullable | `"<think>Let me reason...</think>\npublic int[]..."` | Full model output including `<think>` blocks; preserved for analysis and log display | `BenchmarkExecutionTask` after inference | Log display; thinking block viewer |
| `sanitized_response` | `TEXT` | nullable | `"public int[] twoSum(..."` | Response after stripping `<think>...</think>` tags; this is what all eval layers receive | `BenchmarkExecutionTask` after sanitization | All 4 eval layers; judge prompt |
| `response_char_length` | `INTEGER` | nullable | `1842` | Quick length metric without re-counting; enables verbosity analysis | Computed from `len(sanitized_response)` | Results filter; analysis |
| `has_thinking_block` | `INTEGER` | `NOT NULL DEFAULT 0` | `1` | Flag: 1 if `<think>` tags detected in raw response | Detection logic in sanitize step | Log UI toggle; thinking block filter |

**Group 6 — Performance Metrics**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `status` | `TEXT` | `NOT NULL` | `"COMPLETED"` | `BenchmarkResultStatus` enum: `NOT_COMPLETED`, `WAITING_FOR_JUDGE`, `COMPLETED`, `FAILED`. Drives resume | `BenchmarkExecutionTask` on transitions | Resume logic; result filter; display |
| `total_time_ms` | `INTEGER` | nullable | `14320` | Wall-clock time from request send to full response received; primary speed metric | Wall-clock measurement in provider client | Summary table; speed ranking; TPS calc |
| `ttft_ms` | `INTEGER` | nullable | `312` | Wall-clock time to first token (streaming only; NULL for sync) | Measured in streaming client on first non-empty chunk | TTFT column in results |
| `prompt_tokens` | `INTEGER` | nullable | `187` | From `usage.prompt_tokens` in OpenAI response | Extracted from API response | Cost estimation; context analysis |
| `completion_tokens` | `INTEGER` | nullable | `423` | From `usage.completion_tokens` in OpenAI response | Extracted from API response | Token display; TPS denominator |
| `tokens_per_second` | `REAL` | nullable | `29.5` | Derived: `(completion_tokens / total_time_ms) * 1000` | Computed at storage time | Speed ranking; summary table |

**Group 7 — Layer 1: Rule-Based Pre-filters**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `rule_check_result` | `TEXT` | nullable | `"PASS"` | Layer 1 outcome | `RuleBasedEvaluator.evaluate()` | Pipeline routing; resolution tracking |
| `rule_check_flag` | `TEXT` | nullable | `"empty_output"` | Which rule triggered FAIL (NULL if PASS) | `RuleBasedEvaluator` on FAIL | Results filter; error analysis |
| `rule_check_resolved` | `INTEGER` | `NOT NULL DEFAULT 0` | `0` | 1 if Layer 1 produced terminal FAIL, stopping pipeline early | `RuleBasedEvaluator` | Pipeline routing |

**Group 8 — Layer 2: Keyword Verification**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `keyword_check_result` | `TEXT` | nullable | `"PASS"` | Layer 2 outcome; NULL if task has no `required_terms` | `KeywordEvaluator.evaluate()` | Pipeline routing |
| `missing_exact_terms` | `TEXT` | nullable | `'["HashMap","O(n)"]'` | JSON list of exact terms not found in response | `KeywordEvaluator` on FAIL | Results detail; task debug |
| `found_forbidden_terms` | `TEXT` | nullable | `'["brute force"]'` | JSON list of forbidden terms found in response | `KeywordEvaluator` on FAIL | Results detail |
| `semantic_term_scores` | `TEXT` | nullable | `'{"HashMap":0.92,"O(n)":0.88}'` | JSON map of semantic term → similarity score; soft signal only | `KeywordEvaluator` | Task authoring analysis |
| `keyword_check_resolved` | `INTEGER` | `NOT NULL DEFAULT 0` | `0` | 1 if Layer 2 produced terminal FAIL | `KeywordEvaluator` | Pipeline routing |

**Group 9 — Layer 3: Cosine Similarity**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `cosine_similarity` | `REAL` | nullable | `0.847` | Semantic distance between response and golden_answer; continuous quality gauge | `CosineSimilarityEvaluator` | Results gauge widget; distribution chart |
| `cosine_embedding_model` | `TEXT` | nullable | `"bge-m3"` | Which embedding model produced this score; enables cross-embedding comparison | `CosineSimilarityEvaluator` | Audit trail |
| `cosine_strategy` | `TEXT` | nullable | `"covers"` | Which strategy was applied (from `response_scope`) | `CosineSimilarityEvaluator` | Strategy analysis |
| `cosine_auto_pass` | `INTEGER` | `NOT NULL DEFAULT 0` | `0` | 1 if cosine exceeded auto-pass threshold, skipping judge | `CosineSimilarityEvaluator` | Resolution tracking |
| `cosine_resolved` | `INTEGER` | `NOT NULL DEFAULT 0` | `0` | 1 if cosine produced terminal result (auto-pass or auto-fail) | `CosineSimilarityEvaluator` | Pipeline routing |

**Group 10 — Layer 4: LLM Judge**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `judge_result` | `TEXT` | nullable | `"PASS"` | Judge's PASS/FAIL binary verdict; NULL if earlier layer resolved | `LLMJudgeEvaluator.evaluate()` | Final verdict input |
| `judge_score` | `REAL` | nullable | `0.82` | Judge's confidence score (0.0–1.0), from structured JSON output | Parsed from judge response | Score column in detailed table |
| `judge_reasoning` | `TEXT` | nullable | `"Correct algorithm..."` | Judge's explanation text | Parsed from judge response | Reason column in results |
| `judge_prompt_template` | `TEXT` | nullable | `"judge_coding_v1"` | Which judge prompt template was used (from `JudgePromptService`) | `JudgePromptService` | Prompt template analysis |
| `judge_time_ms` | `INTEGER` | nullable | `3420` | Wall-clock time for judge inference call | Provider client measurement | Judge performance analysis |
| `judge_completion_tokens` | `INTEGER` | nullable | `156` | Tokens used by judge response | From judge response `usage` | Judge cost analysis |

**Group 11 — Final Verdict**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `final_verdict` | `TEXT` | nullable | `"PASS"` | The authoritative outcome; set by whichever layer terminates | Whichever eval layer resolves | Primary results display; pass rate |
| `resolution_layer` | `TEXT` | nullable | `"layer_4_judge"` | Which layer produced the final verdict: `"layer_1_rules"`, `"layer_2_keywords"`, `"layer_3_cosine"`, `"layer_4_judge"` | Set alongside `final_verdict` | Resolution breakdown chart |

**Group 12 — Error Tracking**

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `has_inference_error` | `INTEGER` | `NOT NULL DEFAULT 0` | `0` | Flag for inference-stage error; enables filtering errors from score averages | `BenchmarkExecutionTask` on exception | Error rate metric; results filter |
| `inference_error_message` | `TEXT` | nullable | `"Connection refused"` | Error detail for diagnostics | `BenchmarkExecutionTask` | Log; error summary |
| `has_judge_error` | `INTEGER` | `NOT NULL DEFAULT 0` | `0` | Flag for judge-stage error | `LLMJudgeEvaluator` on exception | Judge error rate |
| `judge_error_message` | `TEXT` | nullable | `"JSON parse failed"` | Judge error detail | `LLMJudgeEvaluator` | Diagnostic log |

---

#### Table: `prompt_variants`

Used exclusively in Prompt Evaluation mode. Stores named prompt variant definitions so performance can be compared across the same tasks and model.

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `variant_id` | `TEXT` | `PK` | `"v2-assertive"` | Unique key for this variant; links to `benchmark_results.prompt_version` | `PromptEvalController` | Results grouping in Prompt Eval view |
| `run_id` | `INTEGER` | `NOT NULL FK → benchmark_runs` | `7` | Links variant to its run | `PromptEvalController` | Query by run |
| `variant_label` | `TEXT` | `NOT NULL` | `"Version 2 — assertive tone"` | Human-readable label for UI display | User input | Display label |
| `system_prompt` | `TEXT` | nullable | `"You are a strict Java engineer..."` | Custom system prompt for this variant; NULL means use default | User input | Sent as system message to model |
| `user_prompt_template` | `TEXT` | `NOT NULL` | `"Write a Java function that {question}"` | Template with `{question}` placeholder, rendered per-task | User input | Rendered with task question before sending |
| `created_at` | `TEXT` | `NOT NULL` | `"2026-04-15T11:00:00"` | Creation timestamp | `PromptEvalController` | Sort order |

---

#### Table: `app_settings`

Key-value store for all persistent feature flags and UI preferences. Replaces hardcoded constants.

| Field | Type | Constraints | Example | Why it exists | Written by | Read by |
|---|---|---|---|---|---|---|
| `key` | `TEXT` | `PK` | `"feature.streaming_enabled"` | Setting identifier | `AppSettingsService.set()` | `AppSettingsService.get()` — any component querying a flag |
| `value` | `TEXT` | `NOT NULL` | `"true"` | Setting value (all stored as text, typed by consumer) | `AppSettingsService.set()` | All consumers |
| `updated_at` | `TEXT` | `NOT NULL` | `"2026-04-15T09:00:00"` | Last modification timestamp | `AppSettingsService.set()` | Diagnostics |

**Known setting keys** (full list in Phase 4):

| Key | Default | Purpose |
|---|---|---|
| `feature.streaming_enabled` | `"true"` | Use streaming inference; sync as fallback |
| `feature.cosine_enabled` | `"true"` | Enable Layer 3 cosine similarity |
| `feature.keyword_check_enabled` | `"true"` | Enable Layer 2 keyword verification |
| `feature.auto_scroll_log` | `"true"` | Auto-scroll log panel |
| `feature.log_to_file` | `"false"` | Write log to disk alongside db.sqlite |
| `ui.theme` | `"dark"` | `"dark"` or `"light"` |
| `ui.log_verbosity` | `"normal"` | `"minimal"`, `"normal"`, `"verbose"` |
| `benchmark.warmup_enabled` | `"true"` | Run warmup inference before timed tasks |
| `benchmark.pause_on_provider_switch` | `"false"` | Pause and prompt when switching providers |
| `benchmark.pause_on_model_switch` | `"false"` | Pause and prompt when switching models |
| `benchmark.stop_on_provider_error` | `"true"` | Stop run on provider health check failure |

**Depends on**: nothing — this is the foundation.

---

### 0.2 — Task YAML Format V2

**Current state**: Tasks have `task_id`, `category`, `sub_category`, `question`, `expected_answer` (three-tier: `most_expected`, `good_answer`, `pass_option`), and `incorrect_direction`. 50 tasks, 4 categories.

**What changes and why**:

- **Three-tier → single `golden_answer`**: Cosine similarity needs one canonical reference vector. The binary judge (PASS/FAIL) doesn't benefit from three tiers — it evaluates against explicit criteria, not tiered scoring.
- **`incorrect_direction` → split into `fail_criteria` + `required_terms.forbidden`**: These serve different eval layers. `fail_criteria` is judge prompt context. `required_terms.forbidden` is Layer 2 hard-fail automation.
- **New `task_type` field**: This is the primary routing key for the eval pipeline — it determines which layers run, which layers are skipped, and which judge prompt template is loaded from `JudgePromptService`.
- **New `response_scope` field**: Controls how cosine similarity is computed (threshold strategy).
- **New `difficulty` field**: Enables difficulty breakdown in results charts.

#### How `task_type` affects the evaluation process and prompts

`task_type` is **not** just metadata — it actively controls pipeline behavior:

| task_type | Layer 1 (Rules) | Layer 2 (Keywords) | Layer 3 (Cosine) | Layer 4 (Judge) | Judge prompt template |
|---|---|---|---|---|---|
| `code_generation` | Always runs | Runs if `required_terms` defined | **SKIP** — code structure is not meaningful in cosine space | Always runs | `judge_coding_v1` (adds: code quality, correctness, style) |
| `code_review` | Always | If defined | **SKIP** | Always | `judge_coding_v1` |
| `reasoning` | Always | If defined | **SKIP** — reasoning paths vary too much for cosine | Always | `judge_reasoning_v1` (adds: logical validity, step quality) |
| `translation` | Always | If defined | Runs with `bge-m3` multilingual | Always | `judge_translation_v1` + language-pair addendum |
| `text_rewrite` | Always | If defined | Runs with cosine | Always | `judge_text_v1` (adds: style, meaning preservation) |
| `factual_qa` | Always | If defined | Runs; auto-PASS on high cosine | Conditional on cosine score | `judge_factual_v1` (adds: factual accuracy weight) |
| `data_extraction` | Always | If defined | Runs with cosine | Always | `judge_data_extraction_v1` (adds: completeness, format) |
| `summarization` | Always | If defined | Runs with cosine | Always | `judge_summarization_v1` (adds: coverage, conciseness) |

The `JudgePromptService` (see 3.2) selects the template by `task_type` and appends language-pair addenda for translation tasks.

#### Complete V2 YAML example — coding task

```yaml
# Each file contains a list under `tasks:`. Files can be organized by category
# or mixed. Multiple files can be loaded per run.
tasks:
  - task_id: coding_java_two_sum_indices
    # UNIQUE identifier across all loaded task files.
    # Convention: {category}_{subcategory}_{short_description}
    # STORED IN: benchmark_results.task_id
    # USED BY: BenchmarkExecutionTask (row creation), Results tab (display)

    category: Coding
    # High-level grouping. Fixed set: Coding | Text Operations |
    # General Knowledge | Data Extraction
    # STORED IN: benchmark_results.task_category
    # USED BY: Category filter in Results tab; breakdown charts

    sub_category: Java
    # Refinement within category. Free text.
    # USED BY: Results tab detailed filter

    task_type: code_generation
    # PRIMARY EVAL ROUTING KEY. Controls:
    #   - Which eval layers run vs skip (see table above)
    #   - Which judge prompt template is loaded from JudgePromptService
    # Values: code_generation | code_review | reasoning | translation |
    #         text_rewrite | factual_qa | data_extraction | summarization
    # STORED IN: benchmark_results.task_type
    # USED BY: Eval pipeline router, JudgePromptService

    difficulty: medium
    # Enables difficulty breakdown analysis in results.
    # Values: easy | medium | hard
    # STORED IN: benchmark_results.task_difficulty
    # USED BY: Results charts

    response_scope: covers
    # Controls Layer 3 cosine similarity strategy:
    #   exact:    response should closely match golden_answer (short factual)
    #   contains: golden_answer is a key phrase the response must include
    #   covers:   response covers semantic content of golden_answer (long-form)
    # NOTE: ignored when task_type routes to cosine SKIP (code, reasoning)
    # STORED IN: benchmark_results.response_scope
    # USED BY: CosineSimilarityEvaluator strategy selection

    question: >
      Write a Java function that, given an array of integers and a target sum,
      returns the indices of two distinct elements whose values add up to the
      target. The solution must run in O(n) time and use O(n) extra space.
      Handle cases where no valid pair exists and where duplicate values are
      present.
    # The prompt text sent verbatim to test models.
    # STORED IN: benchmark_results.user_prompt_sent
    # USED BY: BenchmarkExecutionTask (inference call); judge prompt (context)

    golden_answer: |
      public int[] twoSum(int[] nums, int target) {
          Map<Integer, Integer> seen = new HashMap<>();
          for (int i = 0; i < nums.length; i++) {
              int complement = target - nums[i];
              if (seen.containsKey(complement)) {
                  return new int[]{seen.get(complement), i};
              }
              seen.put(nums[i], i);
          }
          return new int[]{};
      }
    # Single canonical reference answer. Replaces V1 three-tier expected_answer.
    # STORED IN: benchmark_results.golden_answer
    # USED BY:
    #   Layer 3: CosineSimilarityEvaluator encodes this as reference vector
    #   Layer 4: LLMJudgeEvaluator includes this in judge prompt as reference
    #   Prompt Eval: displayed in comparison view

    pass_criteria: >
      Uses a HashMap for O(n) time complexity. Returns empty array or handles
      no-valid-pair case. Correctly handles duplicate values. Clean, readable code.
    # Explicit acceptance rules appended to the judge prompt.
    # USED BY: Layer 4 judge prompt — the judge evaluates AGAINST these criteria.

    fail_criteria: >
      Nested loops (O(n^2) solution). Missing null/empty array handling.
      Modifying the input array in place. No error handling.
    # Explicit rejection signals appended to the judge prompt.
    # Replaces V1 incorrect_direction.
    # USED BY: Layer 4 judge prompt — patterns to penalize.

    required_terms:
      exact:
        - "HashMap"
      # Layer 2 hard check: if any exact term is MISSING from sanitized_response,
      # result is immediate FAIL. No judge called.
      # USED BY: KeywordEvaluator
      # STORED IN: benchmark_results.missing_exact_terms (if any missing)

      semantic:
        - "hash map"
        - "complement"
        - "O(n) time"
      # Layer 2 soft signal: cosine similarity between each term and the response.
      # Does NOT hard-fail. Stored as context signal for analysis.
      # USED BY: KeywordEvaluator → EmbeddingService
      # STORED IN: benchmark_results.semantic_term_scores

      forbidden:
        - "brute force"
        - "O(n^2)"
        - "nested loop"
      # Layer 2 hard check: if any forbidden term is FOUND in sanitized_response
      # (case-insensitive substring), immediate FAIL.
      # USED BY: KeywordEvaluator
      # STORED IN: benchmark_results.found_forbidden_terms
```

#### Translation task example (additional fields)

```yaml
  - task_id: text_operations_translate_en_fr_business_email
    category: Text Operations
    sub_category: Translation
    task_type: translation
    difficulty: easy
    response_scope: covers

    source_language: en
    # For translation tasks: source language code.
    # STORED IN: benchmark_results.source_language
    # USED BY: JudgePromptService — loads source-language-specific addendum

    target_language: fr
    # For translation tasks: target language code.
    # STORED IN: benchmark_results.target_language
    # USED BY: JudgePromptService — loads target-language grammar/style rules

    question: >
      Translate the following business email from English to French,
      maintaining a professional register: [email content here]

    golden_answer: "Madame, Monsieur, ..."
    pass_criteria: "Correct French grammar. Professional register. All key information preserved."
    fail_criteria: "Missing key information. Informal register. Machine-literal word-by-word translation."
```

#### RAG / data extraction task example

```yaml
  - task_id: data_extraction_transaction_summary
    category: Data Extraction
    sub_category: Finance
    task_type: data_extraction
    difficulty: medium
    response_scope: exact

    question: "Extract all transaction amounts from the following bank statement:"

    source_material: |
      Date       Description          Amount
      2026-01-01 Coffee Shop           -4.50
      2026-01-02 Salary             +3200.00
      2026-01-03 Electricity bill     -87.20
    # For RAG-style tasks: the context material appended to the question.
    # USED BY: BenchmarkExecutionTask — appended to user prompt as context.
    # Enables source-material tasks without external retrieval.

    golden_answer: "-4.50, +3200.00, -87.20"
    pass_criteria: "All three amounts extracted. Signs preserved. Order matches source."
    fail_criteria: "Missing any amount. Wrong sign. Extra hallucinated amounts."
```

**Migration from V1 tasks**: Provide a `scripts/migrate_tasks_v1_to_v2.py` utility that reads V1 YAML, maps `most_expected` → `golden_answer`, maps `incorrect_direction` → `fail_criteria`, and requires manual population of `task_type`, `response_scope`, `difficulty`, and `required_terms`. The migration is semi-automated — human review required.

**Depends on**: nothing — this is the foundation.

---

### 0.3 — Provider Configuration File

#### Why `providers.yaml` exists

V1 has Ollama hardcoded — the base URL, model listing, and inference client are embedded in source code. Adding a second provider in V1 requires code changes and a rebuild. `providers.yaml` is an **external configuration file** that lives in the app's data directory (same folder as `db.sqlite`). It lists every provider the user wants to benchmark against, with its type, base URL, API key, and default models. Adding a new provider is a YAML edit — no code change required.

#### How `providers.yaml` is used by the UI

1. **Startup**: `ProviderRegistry` reads `providers.yaml`, constructs one client instance per enabled entry, and exposes them to the UI
2. **Run Configuration panel**: Provider dropdowns for judge and test models are populated from enabled providers in the registry
3. **Model list**: When user selects a provider, the model checkbox list refreshes via `provider.get_available_models()`
4. **Settings → Providers tab**: Shows all providers (enabled and disabled), their health status, connection test button
5. **Health check**: Background task periodically pings each enabled provider; UI shows green/red/yellow dot

#### Loading providers.yaml — file picker and drag-and-drop

Users can load a `providers.yaml` via two paths:

1. **File picker**: Settings → Providers → "Load config file" button → `QFileDialog.getOpenFileName()` for `.yaml`/`.yml` → validate → confirm dialog "Replace current config?" → save to app data directory → reload registry
2. **Drag-and-drop**: The Settings → Providers tab (and optionally the main window) accepts `.yaml`/`.yml` file drops → validate → confirm dialog → save → reload

Both paths call the same `ProviderConfigLoader.load_and_validate(path)` method. Validation checks: required fields present, URL format valid, at least one provider entry, `${ENV_VAR}` references resolve (warn if unset, don't crash).

#### Complete `providers.yaml` example

```yaml
# providers.yaml
# Location: app data directory (same folder as db.sqlite)
# Created by: user manually, OR imported via Settings UI / drag-and-drop
# Read by: ProviderRegistry at startup; reloaded on "Refresh Providers"

providers:

  # ── Ollama (local, via OpenAI-compatible endpoint) ──────────────────────
  - id: ollama_local
    # UNIQUE identifier. Stored in benchmark_results.provider_id and
    # benchmark_runs.judge_provider_id. Must be stable across config reloads.
    # USED BY: ProviderRegistry lookup; all DB references

    label: "Ollama (Local)"
    # Human-readable name shown in UI dropdowns and provider cards.
    # USED BY: UI display only

    type: openai_compatible
    # Selects which client class ProviderRegistry instantiates.
    # Values: openai_compatible | anthropic | gemini
    # Ollama, LM Studio, llama.cpp, OpenAI, Azure ALL use openai_compatible.
    # USED BY: ProviderRegistry (client class selection)

    base_url: "http://localhost:11434/v1"
    # Passed to openai.OpenAI(base_url=...).
    # For Ollama: http://localhost:11434/v1
    # For LM Studio: http://localhost:1234/v1
    # For llama.cpp server: http://localhost:8080/v1
    # For OpenAI cloud: https://api.openai.com/v1
    # USED BY: OpenAICompatibleProvider constructor

    api_key: "ollama"
    # Passed to openai.OpenAI(api_key=...).
    # Local providers accept any non-empty string.
    # Cloud providers: use ${ENV_VAR} syntax → resolved at load time.
    # If env var is unset: provider marked "unavailable" in UI (no crash).
    # USED BY: OpenAICompatibleProvider constructor

    default_models:
      - "llama3.1:8b-instruct-q4_K_M"
      - "qwen3:8b"
      - "gemma3:12b-it-qat"
    # Pre-populates model checkbox list on startup.
    # Does NOT limit selection — user can check any model returned by
    # the provider's /v1/models endpoint.
    # USED BY: UI model selector widget

    enabled: true
    # Disabled providers are loaded but hidden from the UI.
    # Allows keeping a config without activating it.
    # USED BY: ProviderRegistry (filter); Settings UI (toggle)

  # ── LM Studio (same type, different base_url) ──────────────────────────
  - id: lm_studio_local
    label: "LM Studio (Local)"
    type: openai_compatible
    base_url: "http://localhost:1234/v1"
    api_key: "lm-studio"
    enabled: false
    # disabled by default — user enables when LM Studio is running

  # ── llama.cpp server ────────────────────────────────────────────────────
  - id: llamacpp_local
    label: "llama.cpp (Local)"
    type: openai_compatible
    base_url: "http://localhost:8080/v1"
    api_key: "llamacpp"
    enabled: false

  # ── OpenAI cloud (same type, cloud URL + real API key) ──────────────────
  - id: openai_cloud
    label: "OpenAI"
    type: openai_compatible
    base_url: "https://api.openai.com/v1"
    api_key: "${OPENAI_API_KEY}"
    # ${...} resolved from process environment at load time.
    # If env var unset: provider shown in Settings with warning badge,
    # not available for selection in Run Configuration.
    default_models:
      - "gpt-4o"
      - "gpt-4o-mini"
    enabled: true

  # ── Azure OpenAI (also openai_compatible) ───────────────────────────────
  - id: azure_openai
    label: "Azure OpenAI"
    type: openai_compatible
    base_url: "${AZURE_OPENAI_ENDPOINT}/openai/deployments"
    api_key: "${AZURE_OPENAI_KEY}"
    enabled: false

  # ── Anthropic (native SDK — NOT openai_compatible) ──────────────────────
  - id: anthropic_cloud
    label: "Anthropic"
    type: anthropic
    # Uses anthropic Python SDK internally (not openai).
    # base_url is optional — defaults to Anthropic's production endpoint.
    api_key: "${ANTHROPIC_API_KEY}"
    default_models:
      - "claude-sonnet-4-6"
      - "claude-haiku-4-5-20251001"
    enabled: false

  # ── Google Gemini (native SDK) ──────────────────────────────────────────
  - id: gemini_cloud
    label: "Google Gemini"
    type: gemini
    # Uses google-genai Python SDK internally.
    api_key: "${GEMINI_API_KEY}"
    default_models:
      - "gemini-2.0-flash"
      - "gemini-2.5-pro"
    enabled: false

# ── Embedding configuration ───────────────────────────────────────────────
embedding:
  provider_id: ollama_local
  # Which provider entry above serves embedding requests.
  # Must be type: openai_compatible (uses /v1/embeddings endpoint).
  # USED BY: EmbeddingService; CosineSimilarityEvaluator; Settings UI

  model: "bge-m3"
  # Default and recommended: bge-m3 (multilingual, all task languages).
  # Alternative for English-only: nomic-embed-text-v1.5 (faster, smaller).
  # USED BY: EmbeddingService.encode(); stored in benchmark_results.cosine_embedding_model
```

**Depends on**: nothing — this is the foundation.

---

## Phase 1 — Provider Abstraction Layer

Phase 1 builds the runtime client infrastructure that reads `providers.yaml` (Phase 0.3) and exposes a uniform interface to the execution engine (Phase 2).

---

### 1.1 — Provider Interface & Registry

**Current state**: `LLMApi` ABC in `core/interfaces.py` with Ollama-specific methods. `OllamaApi` in `services/` is the only implementation.

**What changes**: Replace `LLMApi(ABC)` with `LLMProviderApi(Protocol)`. Add `ProviderRegistry` service. All V1 code referencing `LLMApi` switches to `LLMProviderApi`.

**New abstractions in `core/interfaces.py`**:

```
LLMProviderApi(Protocol):
    provider_id: str
    provider_type: str
    get_available_models() -> list[ModelDescriptor]
    inference_sync(model, messages, options) -> InferenceResponse
    inference_stream(model, messages, options) -> Generator[StreamChunk, None, InferenceResponse]
    supports_structured_output() -> bool
    supports_streaming() -> bool

EmbeddingProviderApi(Protocol):
    encode(texts: list[str]) -> list[list[float]]
```

**New service `services/provider_registry.py`**:

```
ProviderRegistry:
    __init__(config_loader: ProviderConfigLoader)
    load() -> None                          # reads providers.yaml, constructs clients
    reload() -> None                        # re-reads, re-constructs, emits signal
    get_provider(provider_id) -> LLMProviderApi
    get_all_providers() -> list[LLMProviderApi]
    get_enabled_providers() -> list[LLMProviderApi]
    get_embedding_provider() -> EmbeddingProviderApi
```

On `reload()`, emits `ProviderRegistryReloadedEvent` via EventBus so the UI refreshes dropdowns.

**New service `services/provider_config_loader.py`**:

```
ProviderConfigLoader:
    load_and_validate(path: Path) -> list[ProviderConfig]
    resolve_env_vars(raw_value: str) -> str   # ${VAR} → os.environ["VAR"]
```

Raises `ProviderConfigError` on invalid YAML — surfaced as UI warning, never a crash.

**Depends on**: Phase 0 (all three sections).

---

### 1.2 — OpenAI-Compatible Generic Client

**What it is**: A single `OpenAICompatibleProvider` class that handles Ollama, LM Studio, llama.cpp, OpenAI cloud, and Azure OpenAI. This is the universal client — configured only by `base_url` and `api_key` from `providers.yaml`.

**Why the `ollama` Python SDK is dropped**: The `ollama` SDK returns `eval_count` and `eval_duration` — Ollama-internal metrics measured inside the Ollama process. The `openai` SDK returns `usage.completion_tokens` and the client measures wall-clock time from the outside. These produce different numbers for the same run. Mixing them makes the "AVG. TOKENS/S" column meaningless. Using the OpenAI-compatible endpoint for Ollama means every metric is computed the same way regardless of provider.

**Sync inference** (`inference_sync`):
1. Record `start_ms = time.monotonic_ns() // 1_000_000`
2. Call `openai.OpenAI(base_url=..., api_key=...).chat.completions.create(stream=False, ...)`
3. Record `end_ms`
4. Extract `response.choices[0].message.content`, `response.usage.prompt_tokens`, `response.usage.completion_tokens`
5. Compute `tokens_per_second = (completion_tokens / total_time_ms) * 1000`
6. Return `InferenceResponse(total_time_ms=end_ms-start_ms, ttft_ms=None, ...)`

**Streaming inference** (`inference_stream`):
1. Record `start_ms`
2. Call `.create(stream=True, stream_options={"include_usage": True})` — returns chunk iterator
3. On first non-empty delta content: record `ttft_ms = now_ms - start_ms`
4. Accumulate content chunks; yield `StreamChunk` objects to caller for real-time log display
5. On final chunk: record `end_ms`, extract `usage` from final chunk
6. Return final `InferenceResponse` with `ttft_ms` populated

**Structured output for judge calls**: When `supports_structured_output() -> True` (detected via provider capability), send `response_format={"type": "json_schema", "json_schema": JUDGE_SCHEMA}`. Otherwise, prompt asks for JSON explicitly and response is parsed with `json.loads()` + regex fallback.

**Thinking block handling**: Some models (deepseek-r1, qwen3-thinking) wrap reasoning in `<think>...</think>`. The `sanitize_response()` utility strips these tags. `raw_response` preserves them. `has_thinking_block` flag is set if tags detected. See 3.2 for full thinking block details.

**Model listing**: `GET {base_url}/models` → parse response → return `list[ModelDescriptor]`.

**Depends on**: 1.1 (interface definition).

---

### 1.3 — Native Cloud Providers (Anthropic, Gemini)

**Why separate**: Anthropic and Google Gemini do NOT speak the OpenAI protocol. They require their own SDKs.

**`services/providers/anthropic_provider.py`** — `AnthropicProvider`:
- Uses `anthropic` Python SDK
- Supports thinking blocks via `anthropic.types.ThinkingConfigParam` (budget_tokens)
- `supports_structured_output()` → `False` (use prompt + JSON parsing)
- Metrics: `response.usage.input_tokens`, `response.usage.output_tokens`, wall-clock time
- Both sync and streaming modes

**`services/providers/gemini_provider.py`** — `GeminiProvider`:
- Uses `google-genai` Python SDK
- `supports_structured_output()` → `True` if model supports it
- Metrics: `response.usage_metadata.candidates_token_count`, wall-clock time
- Both sync and streaming modes

Both implement `LLMProviderApi`. The execution engine in `BenchmarkExecutionTask` calls the interface — it never knows which SDK is underneath.

**Depends on**: 1.1 (interface definition).

---

### 1.4 — Embedding Provider

**`services/providers/openai_embedding_provider.py`** — `OpenAIEmbeddingProvider`:
- Uses `openai.OpenAI(base_url=...).embeddings.create(model=..., input=texts)`
- The `/v1/embeddings` endpoint is part of the OpenAI spec; Ollama supports it

**Default embedding model**: `bge-m3`
- Multilingual: covers English, Croatian, French, German, and all other languages in the task dataset
- Available via Ollama: `ollama pull bge-m3`
- Configurable in `providers.yaml` under `embedding.model` and in Settings UI
- Alternative for English-only setups: `nomic-embed-text-v1.5`

**`services/embedding_service.py`** — `EmbeddingService`:
- Wraps `EmbeddingProviderApi` with LRU cache (keyed on text content hash)
- Batch-encodes lists in one API call where possible
- Used by `CosineSimilarityEvaluator` (Layer 3) and `KeywordEvaluator` (semantic terms in Layer 2)

**Depends on**: 1.1, 1.2 (uses OpenAI-compatible endpoint).

---

### 1.5 — Model Descriptor & Name Parsing

**`core/models.py`** gains `ModelDescriptor`:

```
@dataclass(frozen=True)
class ModelDescriptor:
    provider_id: str          # "ollama_local"
    provider_type: str        # "openai_compatible"
    model_name: str           # "llama3.1:8b-instruct-q4_K_M"
    model_family: str | None  # "llama3" — parsed
    model_size_b: float | None  # 8.0 — parsed
    quantization_label: str | None  # "q4_K_M" — parsed
    display_label: str        # "ollama_local / llama3.1:8b" — for UI
```

Replaces all plain `model_name: str` usage across the codebase.

**`services/model_name_parser.py`** — `ModelNameParser`:
- Regex-based parsing: `model_name:size-variant-quantization` patterns
- Returns `None` for fields it cannot parse (cloud models have opaque names)
- Tested with known Ollama, LM Studio, and OpenAI naming conventions

**Depends on**: 1.1 (ModelDescriptor is part of the interface contract).

---

## Phase 2 — Execution Engine V2

Phase 2 builds the machinery that orchestrates benchmark runs using the provider clients from Phase 1.

---

### 2.1 — Dual-Mode Inference (Sync + Streaming)

**Core principle**: Both sync and streaming are implemented on every provider client. Neither replaces the other. The mode used per run is configurable.

**When each mode is used**:

| Scenario | Preferred mode | Reason |
|---|---|---|
| Speed mode inference | Streaming | TTFT is a primary metric |
| Full grading — inference | Streaming | TTFT captured; live log output |
| Full grading — judge call | Sync | Structured output easier; short response |
| Prompt eval inference | Streaming | Live comparison view |
| Fallback | Sync | If streaming fails or provider doesn't support it |

**Run-level override**: `app_settings feature.streaming_enabled` sets the default. Per-run override in advanced options panel.

**Stream chunk handling & UI performance**: Streaming chunks from `inference_stream()` are yielded to `BenchmarkExecutionTask`. The task **buffers** chunks and emits batched `StreamingChunkEvent` to EventBus at max 20 Hz (every 50ms). This prevents Qt event queue flooding on fast models. The UI log widget receives batches and appends text — no synchronous call per token. Buffer flushed on stream completion.

**Depends on**: Phase 1 (provider clients implement both modes).

---

### 2.2 — Execution Order & Scheduling

**V2 execution pipeline stages**:

```
STAGE_INITIALIZING
  ├─ Load task files (all paths in run config)
  ├─ Validate tasks (schema check, required fields, task_type valid)
  ├─ Resolve providers for all selected models via ProviderRegistry
  ├─ Insert all benchmark_results rows with status NOT_COMPLETED
  └─ Emit BenchmarkStartedEvent

STAGE_BENCHMARKING (grouped: per provider → per model → per task)
  ├─ For each provider group:
  │   ├─ Check provider health (GET /v1/models or equivalent)
  │   ├─ Emit ProviderSwitchEvent → check pause policy
  │   └─ For each model in this provider:
  │       ├─ Warm up (if enabled) — single cheap inference, not timed
  │       ├─ Emit ModelSwitchEvent → check pause policy
  │       └─ For each task:
  │           ├─ Emit TaskSwitchEvent
  │           ├─ Run inference (sync or streaming per config)
  │           ├─ Store raw_response, sanitized_response, all Group 5+6 fields
  │           ├─ Update status → WAITING_FOR_JUDGE (full grading) or COMPLETED (speed mode)
  │           └─ Emit TaskCompletedEvent

STAGE_JUDGING (full grading mode only; per result in WAITING_FOR_JUDGE)
  ├─ Layer 1: RuleBasedEvaluator
  ├─ Layer 2: KeywordEvaluator (if task has required_terms)
  ├─ Layer 3: CosineSimilarityEvaluator (if task_type allows)
  ├─ Layer 4: LLMJudgeEvaluator (if not resolved by earlier layer)
  ├─ Write final_verdict, resolution_layer, all layer fields
  └─ Update status → COMPLETED or FAILED

STAGE_FINISHED / STAGE_FAILED
  └─ Update benchmark_runs.status; emit BenchmarkFinishedEvent
```

**Resumability**: On resume, `NOT_COMPLETED` results restart inference; `WAITING_FOR_JUDGE` results skip inference and go directly to judging. Provider health check runs before resuming each provider group.

**Task file loading**: Multiple YAML files or a whole folder can be loaded per run. `TaskFileLoader` service scans directories for `.yaml`/`.yml`, validates each file, deduplicates task IDs, and returns the merged task list. Task file paths are stored in `benchmark_runs.task_file_paths` for resume.

**Depends on**: Phase 1 (provider clients), Phase 0 (schema for result storage, YAML format for task loading).

---

### 2.3 — Event System & Configurable Pause/Stop

The event system is how the execution engine communicates state transitions to the UI and to configurable pause/stop policies. Every switch point emits a typed event. Whether to pause, stop, or continue at each event is controlled by `app_settings` flags.

#### Full event type catalogue

All events are frozen dataclasses in `core/models.py`. All emitted via `QtEventBus`.

**Lifecycle events:**

| Event | Fields | Emitted when |
|---|---|---|
| `BenchmarkStartedEvent` | `run_id`, `total_tasks`, `models: tuple[ModelDescriptor]`, `run_mode` | Run initialization complete |
| `BenchmarkPausedEvent` | `run_id`, `pause_reason` (`"user"` / `"event_policy"` / `"provider_error"`), `paused_at_stage` | Pause triggered by user or policy |
| `BenchmarkResumedEvent` | `run_id` | User resumes from pause |
| `BenchmarkStoppedEvent` | `run_id`, `stop_reason` (`"user"` / `"fatal_error"`) | User stops or unrecoverable error |
| `BenchmarkFinishedEvent` | `run_id`, `total_time_ms`, `completed_count`, `failed_count` | All tasks processed |

**Switch events** (each can trigger a configurable pause):

| Event | Fields | Emitted when | Configurable setting |
|---|---|---|---|
| `ProviderSwitchEvent` | `run_id`, `from_provider_id`, `to_provider_id`, `provider_label` | Moving to next provider group | `benchmark.pause_on_provider_switch` |
| `ProviderHealthCheckEvent` | `run_id`, `provider_id`, `is_healthy`, `error_message` | Health check result | `benchmark.stop_on_provider_error` |
| `ModelSwitchEvent` | `run_id`, `from_model`, `to_model: ModelDescriptor` | Moving to next model within provider | `benchmark.pause_on_model_switch` |
| `TaskSwitchEvent` | `run_id`, `model: ModelDescriptor`, `task_id`, `task_category`, `task_type`, `task_number`, `tasks_total` | Starting next task | (no pause setting — too frequent) |
| `ModeSwitchEvent` | `run_id`, `from_stage`, `to_stage` | Transitioning between pipeline stages | `benchmark.pause_on_stage_switch` |

**Completion events:**

| Event | Fields | Emitted when |
|---|---|---|
| `TaskCompletedEvent` | `run_id`, `result_id`, `model`, `task_id`, `status`, `total_time_ms`, `ttft_ms`, `final_verdict` | One task's inference (and optionally eval) done |
| `JudgeStartedEvent` | `run_id`, `result_id`, `layer` | Entering an eval layer |
| `JudgeCompletedEvent` | `run_id`, `result_id`, `layer`, `verdict`, `resolved` | Eval layer done |

**Streaming events:**

| Event | Fields | Emitted when |
|---|---|---|
| `StreamingChunkEvent` | `run_id`, `result_id`, `model_name`, `task_id`, `chunk_text`, `is_thinking_block` | Buffered at 20 Hz during streaming inference |

**Progress events:**

| Event | Fields | Emitted when |
|---|---|---|
| `ProgressUpdateEvent` | `run_id`, `stage`, `current_provider`, `current_model`, `current_task`, `tasks_completed`, `tasks_total`, `start_time_ms`, `current_time_ms`, `estimated_remaining_ms` | Every task completion (and periodically during long tasks) |

#### Pause/resume implementation

`BenchmarkExecutionTask` checks a `threading.Event` at every stage boundary (before provider switch, before model switch, before stage transition). The Pause button toggles this event. When paused, the thread blocks on `event.wait()` — no CPU usage, no timeout loop.

The Stop button sets a separate cancellation flag. The task checks this flag at the same boundaries. On cancellation, the task writes current progress to DB and exits cleanly.

**Depends on**: Phase 0.1 (app_settings for pause policies), Phase 1 (events reference ModelDescriptor).

---

### 2.4 — Progress Reporting & Structured Logging

#### Structured progress widget

The progress area becomes a structured widget with named fields (not flat text). Each field updates independently — no full repaint per update.

**Progress widget fields** (updated by `ProgressUpdateEvent`):

- **Stage badge**: colored chip — `[Initializing]` blue / `[Benchmarking]` orange / `[Judging]` purple / `[Finished]` green / `[Failed]` red
- **Progress bar**: animated, with percentage label and fraction `341 / 539`
- **ETA label**: `Estimated remaining: 14 min` (rolling average of recent task times)
- **Provider**: provider label + health indicator dot (green ● / red ● / yellow ●)
- **Model**: `ModelDescriptor.display_label`
- **Task**: `task_id` (truncated with ellipsis, full text on hover)
- **Elapsed time**: `2h 48m 33s`

#### Log panel improvements

The log panel becomes a structured, filterable widget with collapsible sections.

**Log entry types** (each rendered distinctly):

| Entry type | Rendering | Shown at verbosity |
|---|---|---|
| `TASK_START` | Indented header: model + task_id | minimal, normal, verbose |
| `PROMPT` | Collapsible section (collapsed by default) | normal (collapsed), verbose (expanded) |
| `STREAM_CHUNK` | Inline text, appended in real time | normal, verbose |
| `THINKING_BLOCK` | Collapsible grey section, visually separated | normal (collapsed), verbose (expanded) |
| `INFERENCE_COMPLETE` | Summary line: `42,232ms · 1,840 tokens · 43.5 tok/s · TTFT 312ms` | minimal, normal, verbose |
| `JUDGE_RESULT` | Verdict chip (✓ PASS green / ✗ FAIL red) + score + short reasoning + resolution layer | minimal, normal, verbose |
| `ERROR` | Red background, error message | minimal, normal, verbose |
| `SYSTEM` | Grey italic, system-level messages | verbose |

**Performance requirements**:
- Log widget MUST NOT call `append()` per streaming token — chunks are buffered at 20 Hz
- Log entries beyond rolling window limit (configurable, default 10,000 lines) are trimmed from top
- Auto-scroll: enabled by default. If user scrolls up manually, auto-scroll disables and a "↓ Jump to bottom" button appears. Re-enables when user scrolls back to bottom.

**Log file output**: When `feature.log_to_file = true`, a `LogFileWriter` service writes each entry to `benchmark_<run_id>_<timestamp>.log` in the app data directory. Format: plain text with timestamp prefix. Log file path shown in progress area as a clickable link.

**Log verbosity levels** (controlled by `ui.log_verbosity`):
- `minimal` — TASK_START, INFERENCE_COMPLETE, JUDGE_RESULT, ERROR only
- `normal` — all entry types, prompts and thinking blocks collapsed
- `verbose` — all entry types, all sections expanded

**Depends on**: 2.3 (event types feed the log).

---

## Phase 3 — Evaluation Pipeline V2

Phase 3 implements the three benchmark modes. Each mode shares the same execution engine (Phase 2) but differs in what happens after inference.

---

### 3.1 — Speed Mode (Metrics Only)

Speed mode focuses entirely on raw inference performance. All eval layers (1–4) are skipped. **Tasks are still required** — the question prompts affect response length and quality, making metrics meaningful and comparable.

**What Speed mode measures**:
- `total_time_ms` — wall-clock inference time
- `ttft_ms` — time to first token (streaming only; NULL if sync)
- `completion_tokens` — tokens generated
- `tokens_per_second` — derived: `(completion_tokens / total_time_ms) * 1000`
- `prompt_tokens` — input context length

**What Speed mode does NOT do**:
- No `final_verdict`, `resolution_layer`, `evaluation_score` — all NULL
- No judge call, no embedding call
- No `WAITING_FOR_JUDGE` status — results go directly to `COMPLETED` after inference
- No `STAGE_JUDGING` — pipeline goes `INITIALIZING → BENCHMARKING → FINISHED`

**Results view in Speed mode**: Summary table shows TIME, TOKENS, TPS, TTFT columns. Score/verdict columns hidden. Detailed table shows per-task timing breakdown. Charts: TPS bar chart, TTFT distribution.

**Run mode stored in DB**: `benchmark_runs.run_mode = "speed"`, each `benchmark_results.run_type = "speed"`. Results tab adapts column set when displaying historical speed-mode runs.

**Depends on**: Phase 2 (execution engine), Phase 0 (schema stores run_mode).

---

### 3.2 — Full Grading Mode (4-Layer Pipeline)

Full grading is the V2 default mode. It runs all 4 evaluation layers in order, stopping as soon as any layer produces a terminal verdict.

#### Thinking blocks handling

Many models produce reasoning wrapped in `<think>...</think>` tags (deepseek-r1, qwen3-thinking variants). These must be handled correctly throughout the pipeline:

- **Detection**: `has_thinking_block = 1` if `<think>` tag found in `raw_response`
- **Storage split**: `raw_response` = full output WITH think tags; `sanitized_response` = content AFTER stripping think tags
- **Eval input**: All 4 eval layers receive `sanitized_response` — think blocks are NEVER shown to the judge
- **Log display**: Think blocks rendered as collapsible grey section in log, separated from the answer
- **Reasoning effort level**: Providers that expose a reasoning budget parameter (e.g., Anthropic's `thinking.budget_tokens`) have a per-run setting: `reasoning_effort = "low" | "medium" | "high" | "default"`. Configurable in advanced run options.

#### Layer 1 — Rule-Based Pre-filters

Service: `services/evaluators/rule_based_evaluator.py`

Rules run in order; first FAIL terminates:
1. `empty_output` — `len(sanitized_response.strip()) == 0`
2. `echo_of_input` — `sanitized_response == user_prompt_sent` (exact match)
3. `too_short` — `response_char_length < MIN_RESPONSE_LENGTH` (configurable, default 5)
4. `error_marker` — response starts with known error patterns ("Error:", "I cannot", "I'm unable to")

On PASS: `rule_check_result = "PASS"`, continue to Layer 2.
On FAIL: `rule_check_result = "FAIL"`, `rule_check_flag = "<rule_name>"`, `rule_check_resolved = 1`, `final_verdict = "FAIL"`, `resolution_layer = "layer_1_rules"`. Pipeline stops.

#### Layer 2 — Keyword Verification

Service: `services/evaluators/keyword_evaluator.py`. **Skipped** if task has no `required_terms` block.

1. **Exact terms**: for each in `required_terms.exact`, check `term.lower() in sanitized_response.lower()`. Any missing → hard FAIL, store in `missing_exact_terms` JSON.
2. **Forbidden terms**: for each in `required_terms.forbidden`, check presence. Any found → hard FAIL, store in `found_forbidden_terms` JSON.
3. **Semantic terms**: for each in `required_terms.semantic`, compute cosine similarity via `EmbeddingService.encode([term])` vs `EmbeddingService.encode([sanitized_response])`. Store scores in `semantic_term_scores` JSON. Does NOT hard-fail — soft signal only.

On all hard checks PASS: `keyword_check_result = "PASS"`, continue to Layer 3.
On FAIL: `keyword_check_resolved = 1`, `final_verdict = "FAIL"`, `resolution_layer = "layer_2_keywords"`. Stop.

#### Layer 3 — Cosine Similarity

Service: `services/evaluators/cosine_evaluator.py`. **Skipped** for `task_type` in `{code_generation, code_review, reasoning}` (see task_type routing table in 0.2).

Process:
1. Encode `golden_answer` and `sanitized_response` via `EmbeddingService.encode()` using configured model (default `bge-m3`)
2. Compute cosine similarity → `cosine_similarity` (float 0.0–1.0)
3. Apply `response_scope` strategy:
   - `exact`: auto-PASS if `>= 0.92`; auto-FAIL if `< 0.30`
   - `contains`: auto-PASS if `>= 0.85`; auto-FAIL if `< 0.25`
   - `covers`: auto-PASS if `>= 0.75`; auto-FAIL if `< 0.20`
4. If auto-resolved: set `cosine_auto_pass`, `cosine_resolved = 1`, `final_verdict`, `resolution_layer = "layer_3_cosine"`. Stop.
5. Otherwise: record `cosine_similarity`, continue to Layer 4.

#### Layer 4 — LLM Judge

Service: `services/evaluators/llm_judge_evaluator.py`.

**Dynamic Prompt Service** (`services/judge_prompt_service.py` — `JudgePromptService`):

The prompt sent to the judge is NOT one-size-fits-all. It varies by `task_type` and language pair:

```
JudgePromptService.build_judge_prompt(task, result) -> JudgePromptPair:
  1. Load base system prompt: JUDGE_SYSTEM_BASE
  2. Load task-type addendum: JUDGE_TASK_TYPE_ADDENDA[task.task_type]
     e.g. code_generation → adds code quality criteria, language-specific rules
     e.g. translation → adds translation accuracy, register assessment
     e.g. reasoning → adds logical validity, step-by-step quality
  3. If task_type == "translation":
     Load language-pair addendum (if available):
     JUDGE_TRANSLATION_ADDENDA[(source_language, target_language)]
  4. Build user prompt from JUDGE_USER_PROMPT_TEMPLATE filling:
     {question}, {golden_answer}, {pass_criteria}, {fail_criteria},
     {answer} (sanitized_response), {cosine_score}, {keyword_signals}
  5. Return JudgePromptPair(system=..., user=...)
```

**Judge prompt template IDs** (stored in `benchmark_results.judge_prompt_template`):
- `judge_coding_v1` — for code_generation, code_review
- `judge_reasoning_v1` — for reasoning tasks
- `judge_translation_v1` + language pair addendum — for translation
- `judge_factual_v1` — for factual_qa
- `judge_text_v1` — for text_rewrite, summarization
- `judge_data_extraction_v1` — for data_extraction

All templates live in `core/prompt_constants.py` as named string constants. `JudgePromptService` assembles them. No runtime string construction outside the service.

**Structured judge output**:

The judge must return JSON matching this schema:

```json
{
  "verdict": "PASS",
  "score": 0.82,
  "reasoning": "The function correctly implements..."
}
```

Two strategies based on provider capability:

1. **Structured output supported** (`provider.supports_structured_output() → True`): Send `response_format={"type": "json_schema", "json_schema": JUDGE_OUTPUT_SCHEMA}` in the inference request. This guarantees valid JSON.
2. **Structured output NOT supported**: The system prompt explicitly instructs: "Respond ONLY with a JSON object...". Parse response with `json.loads()`. If parse fails, attempt regex extraction of `verdict`, `score`, `reasoning` fields. If all extraction fails: `has_judge_error = 1`, `judge_error_message = "JSON parse failed"`.

**Judge call flow**:
1. `JudgePromptService.build_judge_prompt(task, result)` → `JudgePromptPair`
2. `judge_provider.inference_sync(model, messages, options)` → response
3. Parse structured JSON from response
4. Store `judge_result`, `judge_score`, `judge_reasoning`, `judge_prompt_template`, `judge_time_ms`, `judge_completion_tokens`
5. Set `final_verdict = judge_result`, `resolution_layer = "layer_4_judge"`

**Depends on**: Phase 1 (provider clients for judge + embedding), Phase 2 (execution engine calls evaluators), Phase 0 (schema, YAML task_type).

---

### 3.3 — Prompt Evaluation Mode

Prompt Evaluation mode tests how different prompt phrasings affect model output quality for the same tasks.

**Setup**:
- User selects **one** model (the test subject)
- User defines 2–N prompt variants (variant_id + optional system prompt + user prompt template with `{question}`)
- User selects task file(s)
- Judge is configured as normal

**Execution**:
For each task × variant combination, a `benchmark_results` row is created with `run_type = "prompt_eval"` and `prompt_version = variant.variant_id`. The `{question}` placeholder in the variant template is replaced with `task.question`. Full grading (4-layer eval) runs on each result.

**Results view**: Side-by-side comparison — rows = tasks, columns = variants. Each cell: PASS/FAIL verdict + cosine score. Summary row: pass rate per variant. Export includes variant prompt texts.

**Depends on**: Phase 3.2 (full grading for each variant), Phase 0.1 (`prompt_variants` table).

---

## Phase 4 — Settings & Feature Flags

Phase 4 builds the UI for managing provider configuration and all app settings.

---

### 4.1 — Provider Configuration UI

The Settings dialog gains a **Providers** tab:

**Provider list**: Each provider from `providers.yaml` shown as a card:
- Provider label + type badge (e.g., "openai_compatible")
- Base URL (displayed, editable in expanded view)
- Health status: green ● = live, red ● = unreachable, yellow ● = never tested
- Enable/disable toggle
- "Test connection" button → calls `get_available_models()`, shows model count or error
- "Edit" button → expands card to show editable fields

**Config file management buttons**:
- "Load config file" → `QFileDialog` for `.yaml` → validate → confirm → save → reload
- "Save config" → saves current in-memory state to `providers.yaml`
- "Reload" → re-reads from disk
- Drag-and-drop target: the Providers tab accepts `.yaml`/`.yml` drops

**Embedding section** (bottom of Providers tab):
- Embedding provider dropdown (from enabled providers)
- Embedding model text field (default: `bge-m3`)

**Drag-and-drop implementation** (`qt_classes/drag_drop_handler.py`):
- `DragDropHandler` is a `QObject` installable on any widget via `installEventFilter`
- `dragEnterEvent`: accept if mime data contains URLs ending `.yaml`/`.yml`
- `dropEvent`: extract path, validate, show confirmation, save, reload
- Same handler reused for task file drag-and-drop on the Run Configuration panel

**Depends on**: Phase 1 (ProviderRegistry for live testing), Phase 0.3 (providers.yaml format).

---

### 4.2 — Feature Flags & App Settings UI

All feature flags stored in `app_settings` table. Settings dialog exposes them in a **General** tab with grouped toggle switches.

**Setting groups in the UI**:

- **Inference**: streaming enabled, reasoning effort default, warmup enabled
- **Evaluation**: cosine enabled, keyword checks enabled, cosine auto-pass thresholds per scope
- **Benchmark events**: pause on provider switch, pause on model switch, pause on stage switch, stop on provider error
- **Logging**: log to file, log verbosity, auto-scroll, log buffer size
- **Display**: theme (dark/light), score display format (0–1 vs 0–100 — fixes V1 mismatch)

Changes to feature flags take effect on the next benchmark run. UI flags (theme, auto-scroll) take effect immediately.

**Depends on**: Phase 0.1 (app_settings table).

---

## Phase 5 — UI Redesign

Phase 5 redesigns the entire UI from the V1 two-panel layout to a three-panel layout that shows all information simultaneously. Color scheme to be discussed and iterated — the mockups below focus on layout and information architecture.

---

### 5.1 — Global Layout & Design System

#### Window layout — 3-panel horizontal split

Replaces V1's 2-panel layout. All three panels visible simultaneously — no tab switching needed to monitor a running benchmark while reviewing results.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Ollama LLM Bench v2.0                                    [Settings] [─][□][✕]│
├──────────────────┬───────────────────────────┬───────────────────────────────┤
│  LEFT PANEL      │   CENTER PANEL            │   RIGHT PANEL                 │
│  ~22% width      │   ~45% width              │   ~33% width                  │
│                  │                           │                               │
│  Run Config      │   Progress + Log          │   Results                     │
│  (mode, provider │   (structured progress    │   (summary table, charts,     │
│  model selection │   bar, filterable log)    │   detailed table, export)     │
│  task files,     │                           │                               │
│  options)        │                           │                               │
└──────────────────┴───────────────────────────┴───────────────────────────────┘
```

Panels are resizable via `QSplitter`. Minimum widths prevent collapse. Double-click splitter handle to reset to defaults.

#### Design system tokens

Color tokens defined in `ui/style/tokens.py`, injected into QSS stylesheets. Two themes — dark (default) and light.

| Token | Usage |
|---|---|
| `--bg-primary` | Main window background |
| `--bg-secondary` | Panel backgrounds |
| `--bg-card` | Card/widget backgrounds |
| `--accent` | Active tabs, progress bars, selected items |
| `--text-primary` | Main text |
| `--text-secondary` | Labels, metadata |
| `--success` | PASS verdict, completed status, health OK |
| `--failure` | FAIL verdict, error status, health down |
| `--warning` | Partial states, health unknown |
| `--border` | Dividers, widget borders |

Typography: system font stack. Monospace for code blocks and log: `SF Mono, Cascadia Mono, Menlo, Consolas, Ubuntu Mono, DejaVu Sans Mono, Monaco, Courier New, monospace`.

**Depends on**: nothing (visual layer), but content requires Phases 1–4 to be meaningful.

---

### 5.2 — Run Configuration Panel (Left)

```
┌────────────────────────────────┐
│  RUN CONFIGURATION             │
│                                │
│  Mode: ○ Speed  ● Full Grading │
│         ○ Prompt Eval          │
│                                │
│  ── Judge ──────────────────── │
│  Provider: [Ollama (Local) ▼]  │
│  Model:    [qwen3:8b       ▼]  │
│                                │
│  ── Test Models ─────────────  │
│  Provider: [Ollama (Local) ▼]  │
│  ┌──────────────────────────┐  │
│  │ ☑ llama3.1:8b-instruct  │  │
│  │ ☑ qwen3:8b              │  │
│  │ ☐ gemma3:12b-it-qat     │  │
│  │ ☐ devstral:24b          │  │
│  │ ...                      │  │
│  └──────────────────────────┘  │
│  [Select All] [Clear All]      │
│  [+ Add Provider]              │
│                                │
│  ── Task Files ──────────────  │
│  ┌──────────────────────────┐  │
│  │ 📄 coding.yaml     [✕]  │  │
│  │ 📄 text_ops.yaml   [✕]  │  │
│  └──────────────────────────┘  │
│  [+ Add File] [+ Add Folder]   │
│  ┈┈ or drag & drop .yaml ┈┈┈  │
│                                │
│  ── Advanced (▶ expand) ─────  │
│  │ ☑ Streaming  ☑ Warmup    │  │
│  │ Reasoning: [Default   ▼] │  │
│  │                          │  │
│  └──────────────────────────┘  │
│                                │
│  ────────────────────────────  │
│  [▶ Start]  [⏸ Pause] [⏹ Stop]│
│  ────────────────────────────  │
│                                │
│  ── Previous Runs ───────────  │
│  ┌──────────────────────────┐  │
│  │ Run #7 · 2026-04-15     │  │
│  │ full_grading · 539 tasks │  │
│  │ Status: NOT_COMPLETED    │  │
│  │ [Resume]                 │  │
│  └──────────────────────────┘  │
└────────────────────────────────┘
```

**Key changes from V1**:
- Mode selector (Speed / Full Grading / Prompt Eval) at top
- Provider selector for judge and test models separately
- Model list filtered by selected provider; "Add Provider" opens Settings → Providers
- Task files list: multiple YAML files or folder; drag-and-drop target
- Advanced options collapsible
- Previous Runs section at bottom with Resume button (replaces V1's separate tab)
- Start/Pause/Stop replaces V1's Start/Stop/Refresh

**When mode = Prompt Eval** (replaces test models section):

```
│  ── Prompt Variants ─────────  │
│  ┌──────────────────────────┐  │
│  │ v1  Default prompt  [✕]  │  │
│  │ v2  Assertive tone  [✕]  │  │
│  └──────────────────────────┘  │
│  [+ Add Variant] → opens editor│
│  Test Model: [llama3.1:8b  ▼]  │
```

---

### 5.3 — Progress & Log Panel (Center)

```
┌──────────────────────────────────────────────────────┐
│  PROGRESS                                            │
│                                                      │
│  Stage: [■ BENCHMARKING]  Provider: Ollama (Local) ● │
│  ████████████████████░░░░░░░  63%   341 / 539        │
│  ETA: ~1h 42m remaining    Elapsed: 2h 48m 33s       │
│  Model: gemma3:27b-it-qat                            │
│  Task: general_knowledge_literature_harry_potter...   │
│                                                      │
├──────────────────────────────────────────────────────┤
│  LOG  [Verbosity: Normal ▼]  [📁 Save to file]  [🗑] │
│  Filter: [All types ▼] [________________] (search)   │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ▸ gemma3:27b — text_operations_rephrase_croatian    │
│    ▸ Prompt (click to expand)                        │
│    Response:                                         │
│    Evo nekoliko opcija, ovisno koliko opušteno...    │
│    ─── 42,232ms · 1,840 tok · 43.5 tok/s ────────   │
│    ✓ PASS  0.82  [layer_4_judge]                     │
│                                                      │
│  ▸ gemma3:27b — general_knowledge_literature_hp...   │
│    ▸ Prompt (click to expand)                        │
│    ▸ <think> block (312 tokens) — click to expand    │
│    Response:                                         │
│    Harry Potter used the Resurrection Stone...       │
│    ─── 15,593ms · 423 tok · 27.1 tok/s · TTFT 312ms │
│    ✓ PASS  0.91  [layer_3_cosine]                    │
│                                                      │
│  ▸ qwen3:8b — coding_java_two_sum_indices            │
│    Response: (streaming...)                          │
│    public int[] twoSum(int[] nums█                   │
│                                                      │
│                              [↓ Jump to bottom]      │
└──────────────────────────────────────────────────────┘
```

**Key improvements over V1**:
- Structured progress area with ETA, health dots, provider identity
- Log entries are structured cards, not raw text dump
- Prompt and thinking blocks collapsible — log stays readable
- Verbosity selector at the top
- Filter: by model, task category, verdict, entry type, or free text search
- Auto-scroll with manual pause + "Jump to bottom" button
- Live streaming display with cursor indicator

---

### 5.4 — Results Panel (Right)

```
┌──────────────────────────────────────────────────────┐
│  RESULTS                                             │
│  Run: [2026-04-15T10:00:00 ▼]  Mode: Full Grading   │
│  [Compare Runs] [Delete] [Export CSV] [Export MD]    │
├──────────────────────────────────────────────────────┤
│  SUMMARY — Average per Model                         │
│  ┌──────────┬───────┬──────┬──────┬─────┬──────────┐│
│  │ Model    │Time(s)│Tok/s │Score │Pass%│TTFT(ms)  ││
│  ├──────────┼───────┼──────┼──────┼─────┼──────────┤│
│  │qwen3:30b │ 72.02 │ 8.3  │ 0.78 │ 76% │   312    ││
│  │gemma3:27b│ 49.65 │ 7.9  │ 0.77 │ 74% │   287    ││
│  │gemma3:12b│ 22.80 │17.0  │ 0.67 │ 64% │   198    ││
│  └──────────┴───────┴──────┴──────┴─────┴──────────┘│
│  (click row to filter detailed table below)          │
├──────────────────────────────────────────────────────┤
│  Charts: [Pass Rate] [Score Dist] [Speed] [Cosine]   │
│  ┌──────────────────────────────────────────────────┐│
│  │  ┃ █ █     █                                     ││
│  │  ┃ █ █ █   █ █                                   ││
│  │  ┃ █ █ █ █ █ █ █                                 ││
│  │  ┗━━━━━━━━━━━━━━━━━━                             ││
│  │    Pass rate by model (bar chart)                 ││
│  └──────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────┤
│  DETAILED — Run #7   Filter: [All categories ▼]     │
│  ┌─────────┬──────────┬──────┬─────┬─────┬─────────┐│
│  │ Model   │ Task     │Vrdict│Score│Cosn │Layer    ││
│  ├─────────┼──────────┼──────┼─────┼─────┼─────────┤│
│  │qwen3:30b│coding_j… │✓PASS │ 0.82│ N/A │L4:judge ││
│  │qwen3:30b│text_op…  │✓PASS │ 0.91│ 0.89│L3:cosine││
│  │qwen3:30b│gen_kn…   │✗FAIL │ 0.21│ 0.41│L4:judge ││
│  │qwen3:30b│coding_p… │✗FAIL │  —  │  —  │L1:rules ││
│  └─────────┴──────────┴──────┴─────┴─────┴─────────┘│
│  [Export CSV]  [Export Markdown]                      │
│                                                      │
│  Resolution breakdown:                               │
│  L1: 12 (2%)  L2: 8 (1%)  L3: 89 (17%)  L4: 430    │
└──────────────────────────────────────────────────────┘
```

**Key V2 improvements over V1**:
- `Pass%` column — pass rate per model (PASS count / total for that model)
- `TTFT` column — visible when streaming was used
- Score displayed consistently in 0.00–1.00 everywhere (fixes V1 mismatch)
- `Verdict` column — PASS/FAIL with colored indicator
- `Cosine` column — `cosine_similarity` gauge value
- `Layer` column — resolution layer (L1/L2/L3/L4 with label)
- Charts panel: switchable chart types
- Category filter on detailed table
- Resolution breakdown summary at bottom
- "Compare Runs" button (future: opens side-by-side view)

**Speed mode results view** (columns adapted):

```
│  ┌──────────┬───────┬──────┬──────────┬────────────┐│
│  │ Model    │Time(s)│Tok/s │TTFT(ms)  │Prompt Tok  ││
│  ├──────────┼───────┼──────┼──────────┼────────────┤│
│  │qwen3:30b │ 72.02 │ 8.3  │   312    │    187     ││
```

**Prompt Eval mode results view** (columns = variants):

```
│  Prompt Evaluation — Run #9                          │
│  Model: llama3.1:8b-instruct                         │
│  ┌──────────┬───────────┬───────────┬───────────────┐│
│  │ Task     │ v1:Default│ v2:Assert │ v3:Minimal    ││
│  ├──────────┼───────────┼───────────┼───────────────┤│
│  │coding_j… │ ✓ 0.82    │ ✓ 0.91   │ ✗ 0.34       ││
│  │text_op…  │ ✓ 0.88    │ ✓ 0.85   │ ✓ 0.79       ││
│  ├──────────┼───────────┼───────────┼───────────────┤│
│  │Pass rate │ 85%       │ 92%      │ 61%           ││
│  └──────────┴───────────┴───────────┴───────────────┘│
```

---

### 5.5 — Settings Dialog

```
┌──────────────────────────────────────────────────────┐
│  Settings                                     [✕]    │
│                                                      │
│  [Providers] [Evaluation] [Events] [Logging] [UI]    │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ── PROVIDERS TAB ───────────────────────────────    │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │ ● Ollama (Local)     openai_compatible   ● Live│  │
│  │   http://localhost:11434/v1          [Test]    │  │
│  │   14 models available               [Edit]    │  │
│  ├────────────────────────────────────────────────┤  │
│  │ ○ LM Studio (Local)  openai_compatible   ○ Off │  │
│  │   http://localhost:1234/v1           [Test]    │  │
│  ├────────────────────────────────────────────────┤  │
│  │ ● OpenAI             openai_compatible   ● Live│  │
│  │   https://api.openai.com/v1          [Test]    │  │
│  │   2 models available                 [Edit]    │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  [Load config file]  [Save config]  [Reload]         │
│  ┈┈┈ or drag & drop a .yaml file here ┈┈┈┈┈┈┈┈┈┈   │
│                                                      │
│  ── Embedding ────────────────────────────────────   │
│  Provider: [Ollama (Local) ▼]  Model: [bge-m3    ]  │
│                                                      │
│  ── EVALUATION TAB ──────────────────────────────    │
│  ☑ Cosine similarity enabled                         │
│  ☑ Keyword verification enabled                      │
│  Cosine auto-pass threshold (exact): [0.92]          │
│  Cosine auto-pass threshold (contains): [0.85]       │
│  Cosine auto-pass threshold (covers): [0.75]         │
│                                                      │
│  ── EVENTS TAB ──────────────────────────────────    │
│  ☐ Pause on provider switch                          │
│  ☐ Pause on model switch                             │
│  ☐ Pause on stage switch                             │
│  ☑ Stop on provider health check failure             │
│                                                      │
│  ── LOGGING TAB ─────────────────────────────────    │
│  ☐ Log to file                                       │
│  Verbosity: [Normal ▼]                               │
│  Log buffer size: [10000] lines                      │
│  ☑ Auto-scroll log                                   │
│                                                      │
│  ── UI TAB ──────────────────────────────────────    │
│  Theme: ○ Dark  ○ Light                              │
│  Score display: ○ 0.00–1.00  ○ 0–100                │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Depends on**: Phase 0.1 (app_settings table), Phase 1 (ProviderRegistry), Phase 4.1.

---

## Phase 6 — Quality & Packaging

> **Status: COMPLETE** — Tests (unit + integration + HTTP), OS-aware paths, task validation CLI, and PyInstaller packaging configuration are all implemented.

### 6.1 — Test Infrastructure

> **Status: COMPLETE**

Create `tests/` directory. Use `pytest` + `pytest-qt` for PySide6 widget testing.

**Test layers** (priority order):
1. **Unit tests** — `core/` models, enums, SQL constants, prompt template assembly: no Qt, no I/O
2. **Service tests** — evaluators (mock EmbeddingService + LLMProviderApi), ProviderConfigLoader, ModelNameParser, JudgePromptService, AppSettingsService
3. **Integration tests** — SqLiteDataApi with in-memory SQLite (`":memory:"`); migration path V1→V2
4. **Provider tests** — OpenAICompatibleProvider against mock HTTP server (`pytest-httpserver`); verify both sync and streaming paths
5. **Widget tests** — `pytest-qt` for signal emission, button state transitions, drag-and-drop events

**Task validation tool** (`scripts/validate_tasks.py`):
- Loads a task YAML, runs `golden_answer` through all eval layers → must PASS
- If `fail_example` field present, runs it → must FAIL
- Used by CI and task authors before committing new tasks

**Depends on**: all earlier phases (tests exercise the code).

---

### 6.2 — Cross-Platform Packaging

> **Status: COMPLETE**

**Build tool**: PyInstaller

| Platform | Output | Notes |
|---|---|---|
| macOS | `.app` bundle → `.dmg` | Sign + notarize for distribution |
| Linux | AppImage | Includes Qt libs |
| Windows | NSIS installer (`.exe`) | Includes MSVC redistributable |

**Data file locations**:
- `providers.yaml`, `db.sqlite`, log files → user data directory:
  - macOS: `~/Library/Application Support/OllamaLLMBench/`
  - Linux: `~/.local/share/OllamaLLMBench/`
  - Windows: `%APPDATA%\OllamaLLMBench\`
- Default `providers.yaml` (Ollama local only) is bundled in the app; copied to user data dir on first launch
- `db.sqlite` is NOT in the app bundle or repo (fixes V1 debt)

**Depends on**: all earlier phases.

---

## Dependency Map

```
Phase 0.1 (DB Schema) ──────────┐
Phase 0.2 (Task YAML) ──────────┤
Phase 0.3 (providers.yaml) ─────┤
                                 ▼
Phase 1.1 (Interface + Registry) ─────┐
         │                            │
    ┌────┴────┐                       │
    ▼         ▼                       │
Phase 1.2  Phase 1.3                  │
(OpenAI)   (Anthropic/Gemini)         │
    │         │                       │
    ├────┬────┘                       │
    ▼    ▼                            │
Phase 1.4 (Embedding)                 │
Phase 1.5 (ModelDescriptor)           │
    │                                 │
    ▼                                 │
Phase 2.1 (Dual-mode inference) ◄─────┘
Phase 2.3 (Event system)
Phase 2.2 (Execution order)
Phase 2.4 (Progress + logging)
    │
    ▼
Phase 3.1 (Speed mode) ─────────────────┐
Phase 3.2 (Full grading / 4-layer eval) │
Phase 3.3 (Prompt eval mode)            │
    │                                    │
    ▼                                    │
Phase 4.1 (Provider config UI) ◄─────────┘
Phase 4.2 (Feature flags UI)
    │
    ▼
Phase 5.1–5.5 (UI redesign)
    │
    ▼
Phase 6.1 (Tests)
Phase 6.2 (Packaging)
```

**Within-phase dependencies**:
- 1.1 must precede 1.2, 1.3, 1.4, 1.5
- 1.2 must precede 1.4 (embedding uses OpenAI-compatible endpoint)
- 2.3 (events) should be designed before 2.2 (execution references events)
- 3.2 depends on 1.4 (embedding for Layer 3)
- 5.2 depends on 1.5 (ModelDescriptor for multi-provider model list)
- 5.3 depends on 2.4 (structured log entries)

---

## V1 → V2 Migration Summary

| Area | V1 | V2 | Migration action |
|---|---|---|---|
| Python SDK | `ollama` (native) | `openai` (OpenAI-compatible) | Remove `ollama` from deps; rewrite `OllamaApi` as `OpenAICompatibleProvider` |
| Provider support | Ollama only | Ollama, LM Studio, llama.cpp, OpenAI, Azure, Anthropic, Gemini | New `ProviderRegistry` + `providers.yaml` |
| Provider config | Hardcoded | External `providers.yaml` + Settings UI + drag-and-drop | Ship default YAML; load on startup |
| DB tables | 2 | 5 (+schema_version, prompt_variants, app_settings; results→benchmark_results) | ALTER TABLE migration; check schema_version |
| DB fields | 15 total | ~65 total | New fields all nullable for V1 compatibility |
| Task YAML | 3-tier expected_answer + incorrect_direction | Single golden_answer + pass/fail_criteria + required_terms + task_type + difficulty | Semi-auto migration script; manual review needed |
| Eval method | 1 judge, numeric 0–100 | 4 layers, binary PASS/FAIL + cosine float + structured JSON | New eval pipeline; old scores not recalculated |
| Inference mode | Sync only | Sync + streaming (add, not replace) | Add streaming; sync remains as fallback |
| Metrics source | `eval_count` (Ollama internal) | `completion_tokens` (OpenAI usage block) + wall-clock time | Old metrics preserved; new runs use standardized |
| Score display | Summary 0–1, detailed 0–100 (inconsistent) | Everywhere 0.00–1.00 (configurable in settings) | Fix `TableSerializer`; add app_settings key |
| Judge output | Raw text + regex-parsed score | Structured JSON (schema enforcement or prompt+parse) | New judge prompt templates; JudgePromptService |
| Judge prompts | One prompt for all tasks | Task-type-specific templates via JudgePromptService | New prompt constant structure |
| Model identity | Plain string | `ModelDescriptor` (provider + name + parsed metadata) | Update all callers; serialize as JSON in DB |
| Task loading | Single implicit path | Multiple files/folder; drag-and-drop | New `TaskFileLoader`; multi-file list widget |
| Progress display | 4 flat text lines | Structured widget with ETA, health indicators | New `ProgressWidget` |
| Log display | Raw scrolling text dump | Structured filterable entries; collapsible sections; 20Hz buffering | New `LogWidget` with `LogEntry` model |
| Window layout | 2-panel (config + output) | 3-panel (config + progress/log + results) | New `QSplitter` layout |
| Settings | None (all hardcoded) | `app_settings` table + Settings dialog | New `AppSettingsService` |
| Event system | Minimal (progress only) | Full event catalogue: 12+ event types, configurable pause/stop | New event dataclasses; EventBus expansion |
| Thinking blocks | Strip `<think>` on read | Store raw + sanitized separately; collapsible in log; flag in DB | Preserve raw; new sanitize split logic |
| Interfaces | ABC | Protocol (technical debt fix) | Refactor `core/interfaces.py` |
| `db.sqlite` in repo | Accidentally committed | `.gitignore` exclusion | Add to `.gitignore` immediately |
| Tests | None | pytest + pytest-qt; unit/service/integration/provider/widget layers | Create `tests/` directory |
| Packaging | Not packaged | PyInstaller: macOS .dmg, Linux AppImage, Windows .exe | New build scripts |
