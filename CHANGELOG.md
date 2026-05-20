# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- Charts 1/2/3 (TTFT, TPS, Time): include `WAITING_FOR_JUDGE` results in inference-performance bars.
- Chart 4 (Success/Failed): add "Incomplete" bucket for `WAITING_FOR_JUDGE` rows.
- Chart 9 (Heatmap): show empty-state message instead of blank "—" cells on non-grading runs.
- Chart 10 (Per-category bar): show empty-state message instead of invisible zero bars on non-grading runs.
- Chart 12 (Boxplot): add footnote when any model has fewer than 5 samples.
- Export PNG (all charts): eliminate blank gutters by computing aspect-preserving canvas height.
- Axis labels (bar/boxplot charts): rotate -45° and disable truncation for long model names.
- Chart selector: disable grading-only charts in dropdown for PERFORMANCE/SPEED/non-grading run modes.

- Progress counters (Not Completed / Completed / Failed) now update in real time during a benchmark run.
- Run Results dropdown now shows the active run immediately when a new run starts.
- Progress counter advances correctly on task failures in both inference and judge stages.
- Progress bar task counter now advances correctly when tasks fail via circuit-breaker trip,
  model exclusion, or missing task definition (previously only the inference exception path
  was counted).
- Charts now refresh on summary data updates, symmetric with detailed data updates.
- Run Results dropdown remains usable while a benchmark is running.

- Judge UNKNOWN cascade: parser now strips markdown fences, handles escaped quotes in reasoning,
  and repairs truncated JSON before falling back to UNKNOWN.
- Bug in `parse_v2_judge_response` regex branch: was returning the wrong variable (`reasoning`
  from the JSON branch) instead of the regex-captured value.
- Post-run analysis tab empty when selecting a previously-completed PERFORMANCE/SPEED run:
  `status_listener` now re-emits `perf_analysis_result` on run switch; `result_widget` caches
  and shows it.
- PROMPT_EVAL runs now receive post-run analysis when `judge_run_analysis_enabled=true`.
- FULL_GRADING runs now correctly respect the `judge_run_analysis_enabled` setting instead of
  always running analysis.
- Fixed multi-provider model selection being silently collapsed to the first provider when
  starting a benchmark run. `RunStartEvent.test_models` now carries `tuple[ModelDescriptor, ...]`
  (preserving per-model provider identity), and `test_provider: str` is removed from the event.
  Models from all selected providers now appear in `models_json` and as `BenchmarkResult` rows.
  Performance mode with no test models is no longer incorrectly rejected.
- Fixed `RuntimeError: libshiboken: Internal C++ object (ProviderCardWidget) already deleted`
  crash that fired every time the Settings → Providers tab was saved, closed, and reopened.
  Root cause: EventBus subscriptions in `ProvidersTabWidget` outlived the widget's C++ lifetime.
  Fix: all `subscribe_to_*` methods now accept an optional `parent: QObject` argument; when set,
  the subscription is automatically disconnected when the parent is destroyed via Qt's `destroyed`
  signal. Added `shiboken6.isValid` liveness guard in `_populate_providers` and removed a
  duplicate `_populate_providers()` call in `_handle_save_changes`.
- Embedding section in Settings no longer raises a RuntimeError when the dialog is closed while a background model-discovery request is in flight.
- Test Models provider dropdown now refreshes automatically when provider settings are saved (previously required app restart).
- Removed `"SF Mono"` from the monospace font chain and `"SF Pro Text"` from the
  sans-serif chain in `tokens.py` to silence the Qt font-alias-lookup warning on macOS.
- Fixed unresolved QSS token warning by removing curly braces from a comment in
  `theme_dark.qss` and `theme_light.qss` that was accidentally treated as a template
  placeholder by `theme_loader.py`.

### Added

- PROMPT_EVAL mode: `test_models_section` visibility policy now includes the shared TestModelsWidget;
  the internal model combo inside PromptVariantsWidget has been removed (deduplication).
- `PromptVariantSpec` frozen dataclass for UI-side prompt variant definition (fields:
  `variant_id`, `variant_label`, `user_prompt_template`, `system_prompt`).
- Variant editor dialog with live preview, duplicate-ID validation, and auto-generated default
  `variant_N` ID to reduce friction when adding variants.
- YAML and TXT import for prompt variants; YAML accepts both a bare list and a
  `{variants: [...]}` wrapper, and both long-form (`variant_id`, `variant_label`,
  `user_prompt_template`, `system_prompt`) and short-form (`id`, `label`, `template`, `system`)
  key conventions.
- Preview pane now shows `[System]` and `[User]` sections when a system prompt is set.
- Performance size buttons now show tier + description
  (e.g. "XS · Tiny (~40 tokens)") via `INPUT_SIZE_DESCRIPTIONS` / `OUTPUT_SIZE_DESCRIPTIONS`.
- Task files widget: drop-hint placeholder is shown when the list is empty (dashed-border
  `QLabel[role="drop-zone"]` styled in both QSS theme files).
- Selected-models scroll area: `setMinimumHeight(120)` / `setMaximumHeight(240)` to prevent
  layout collapse when no models are selected.

- SQLite-backed provider configuration storage with automatic YAML migration and archival
  (archive written to `.yaml.migrated-YYYYMMDD`; DB seeded on first launch).
- Provider list displayed as a sortable `QTableView` with column-header tooltips (replaces card layout).
- Per-row and global "Reset to Defaults" for providers.
- Import/Export YAML for providers (load syncs to DB; export writes a chosen file).
- Font-size design tokens (`font_xs`, `font_sm`, `font_base`, `font_md`, `font_lg`, `font_xl`) —
  all QSS font sizes now use tokens; no inline `Npx` literals remain.
- Embedding provider combo: auto-selects first available embedding model on provider change;
  "Show all models" toggle reveals non-embedding models.
- Batch API-key environment-variable conversion dialog (replaces per-provider modal chain).
- "Read env" button in provider edit form shows masked value of the referenced environment variable.
- Non-blocking warning when saving with the selected embedding provider disabled.

- Retry timeouts now carry over between tasks for the same model — subsequent tasks start at the last successful timeout instead of always resetting to the minimum (adaptive backoff with cross-task memory).
- Models that consistently fail at the maximum timeout are excluded from the remainder of the run with a single warning notification. Threshold is configurable via `benchmark.retry_max_failures_to_exclude` (default 3).
- Renamed `ModelCircuitBreaker` → `ProviderCircuitBreaker` in `circuit_breaker.py` for clarity.

### Changed

- Combobox drop-down arrow is now a CSS-rendered triangle (visible on all themes).
- Enabling a provider now gates on a successful health check; the checkbox reverts when the
  check fails.
- Local/trivial API keys (e.g. `ollama`, `lm-studio`) no longer trigger the env-var conversion
  prompt when the base URL is a loopback address.
- Provider save now targets SQLite as the primary store; YAML is written as a backup only.

- `_MAX_JUDGE_TOKENS` raised from 256 to 512 to prevent truncation on reasoning models.
- Judge inference now requests `response_format={"type":"json_object"}` for providers that
  support structured output, reducing empty-response rate.
- Judge retry loop now retries once on non-terminal UNKNOWN (empty/unparseable response),
  not just on timeout.
- Post-run analysis uses `JudgeSummaryService` for all run modes (PERFORMANCE, SPEED,
  PROMPT_EVAL, FULL_GRADING) with mode-specific prompts; replaces the ad-hoc
  `_stage_performance_analysis` throughput table.
- `judge_run_analysis_enabled` setting now gates analysis for ALL modes including FULL_GRADING.
- Embedding model dropdown now filters discovered models to embedding-like names (falls back to the full list when none match).
- Saving an embedding model name that was not in the discovered list now shows a non-blocking informational warning.
- Enabling a provider and saving now repopulates the embedding-provider combo without requiring a dialog restart.
