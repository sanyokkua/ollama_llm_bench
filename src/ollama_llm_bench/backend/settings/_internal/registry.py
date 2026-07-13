"""The in-code settings registry: ``DEFAULTS`` and ``PER_RUN_OVERRIDABLE``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-G_feature_flags.md`` §3-9
(the exhaustive key-by-key registry — type, default, per-run flag). This module owns
no resolution logic; it is a pure data table.

``DEFAULTS`` is the floor: one entry, in its registry storage-form string, for every
``benchmark.*``, ``feature.*``, ``eval.*``, ``embedding.*``, ``ui.*``, ``logging.*``,
``task_editor.*``, ``provider.*``, and ``readiness.*`` key. Booleans store as
``"true"``/``"false"``, enums store their ``StrEnum`` member's ``.value``.

``provider.probe_timeout_ms`` and ``readiness.snapshot_staleness_ms`` are documented in
``11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`` §7 and
``11_Services_and_Algorithms/09_READINESS_PROBE.md`` §7 respectively but were not yet
present in the ``08-G`` registry document or this in-code table; they are added here
(STORY-016) as a purely additive registry entry — neither per-run-overridable nor
schema-affecting — so the Readiness Service can resolve its timeout/staleness budgets
through ``SettingsService`` instead of a hardcoded literal.

``circuit_breaker.enabled``, ``circuit_breaker.failure_threshold``, and
``circuit_breaker.cooldown_seconds`` are documented in
``11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`` §7 but were not yet present in the
``08-G`` registry document or this in-code table; they are added here (STORY-023) as a
purely additive registry entry, **and** as ``PER_RUN_OVERRIDABLE`` members — the breaker
reads all three once from the run's frozen settings snapshot at construction (§7), so a
settings change mid-run never affects an already-running breaker — so
``backend/circuit_breaker/`` can resolve its configuration through the run snapshot
instead of a hardcoded literal.

``PER_RUN_OVERRIDABLE`` is the exact set of keys frozen into a run's settings snapshot at
run creation — 31 keys: every ``benchmark.*`` key except ``benchmark.last_mode`` (11),
both ``feature.*`` keys (2), every ``eval.*`` key (15), and all three
``circuit_breaker.*`` keys (3, STORY-023). No ``ui.*``, ``embedding.*``, ``logging.*``,
``task_editor.*``, or ``provider.*``/``readiness.*`` key is ever a member — this includes
``ui.stream_tokens_to_log``, which lives in the spec's §4 ``feature.*`` table but is a
live UI/log preference, not a run input (`08-G` §4).

``eval.embedding_cache_max_entries`` is documented in
``11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md`` §7 but was not yet present in the
``08-G`` registry document or this in-code table; it is added here (STORY-027) as a
purely additive registry entry, **and** as a ``PER_RUN_OVERRIDABLE`` member — the
embedding service reads it once from the run's frozen settings snapshot at construction
(§7), bounding its in-memory LRU cache for the life of that run — so
``backend/embedding/`` can resolve its cache bound through the run snapshot instead of a
hardcoded literal.

**Documented decisions (SPEC-110 / DD-30 scope notes for this story):**

- ``benchmark.temperature``'s spec-documented blank-to-opt-out pipeline behaviour (fall
  back to a provider's own default) is a benchmark-pipeline concern, out of this story's
  scope. ``SettingsService.get_float("benchmark.temperature")`` applies the same SPEC-110
  coercion rule as any other float key: a blank or non-coercible user-saved value falls
  through to the in-code default ``0.0`` with a logged warning, never raises.
- ``feature.judge_run_analysis_enabled``'s spec-documented default is mode-dependent (OFF
  in ``SYNTHETIC``/``TASKS``, ON in ``GRADED`` — DD-30). Applying that mode-dependent
  default is the New Benchmark widget's / run-creation use case's job (DD-47), out of this
  story's scope. ``DEFAULTS`` carries one static floor value for this key: ``"false"``.
"""

from ollama_llm_bench.backend.domain import ReasoningEffort, RunMode, SettingKey

__all__: list[str] = [
    "DEFAULTS",
    "PER_RUN_OVERRIDABLE",
]

DEFAULTS: dict[SettingKey, str] = {
    # --- benchmark.* (`08-G` §3) — 12 keys, all per-run-overridable except last_mode ---
    "benchmark.warmup_enabled": "true",
    "benchmark.retry_count": "3",
    "benchmark.max_output_tokens": "4096",
    "benchmark.temperature": "0.0",
    "benchmark.min_timeout_seconds": "300",
    "benchmark.max_timeout_seconds": "900",
    "benchmark.consecutive_max_timeouts_to_exclude": "3",
    "benchmark.pause_on_phase_switch": "false",
    "benchmark.pause_on_provider_switch": "false",
    "benchmark.pause_on_model_switch": "false",
    "benchmark.stop_on_provider_health_failure": "false",
    "benchmark.last_mode": RunMode.SYNTHETIC.value,
    # --- feature.* / ui.stream_tokens_to_log (`08-G` §4) — 2 + 1 keys ---
    "feature.reasoning_effort_default": ReasoningEffort.DEFAULT.value,
    "feature.judge_run_analysis_enabled": "false",
    "ui.stream_tokens_to_log": "true",
    # --- eval.* (`08-G` §5) — 15 keys, all per-run-overridable ---
    "eval.phase_keyword_enabled": "true",
    "eval.phase_cosine_enabled": "true",
    "eval.phase_judge_enabled": "true",
    "eval.force_judge_on_prior_failure": "false",
    "eval.cosine_threshold": "0.85",
    "eval.judge_max_completion_tokens": "4096",
    "eval.judge_timeout_min_seconds": "20",
    "eval.judge_timeout_max_seconds": "120",
    "eval.judge_timeout_escalation_steps": "2",
    "eval.judge_timeout_consecutive_threshold": "3",
    "eval.embedding_timeout_seconds": "30",
    "eval.min_sample_size": "5",
    "eval.embedding_consecutive_failures_to_skip": "3",
    "eval.embedding_cache_max_entries": "4096",
    "eval.min_cosine_coverage": "0.8",
    # --- embedding.* (`08-G` §6) — 4 keys, none per-run-overridable ---
    "embedding.selected_provider_name": "",
    "embedding.selected_model_name": "",
    "embedding.hide_from_test_models": "true",
    "embedding.additional_patterns": "",
    # --- ui.* (`08-G` §7) — 11 keys besides ui.stream_tokens_to_log above ---
    "ui.theme": "system",
    "ui.score_display_format": "decimal",
    "ui.window_geometry": "",
    "ui.splitter_sizes": "",
    "ui.active_workspace": "benchmark",
    "ui.last_result_tab": "summary",
    "ui.task_editor_last_folder": "",
    "ui.export_save_directly": "false",
    "ui.run_log_verbosity": "normal",
    "ui.run_log_max_lines": "100000",
    "ui.auto_scroll_run_log": "true",
    # --- logging.* (`08-G` §8) — 5 keys, none per-run-overridable ---
    "logging.write_run_log_to_file": "true",
    "logging.write_app_log_to_file": "true",
    "logging.app_log_level": "info",
    "logging.app_log_max_file_mb": "10",
    "logging.app_log_max_total_mb": "60",
    # --- task_editor.* (`08-G` §9) — 2 keys, none per-run-overridable ---
    "task_editor.auto_format_on_save": "true",
    "task_editor.warn_on_empty_grading_criteria": "true",
    # --- provider.* / readiness.* (STORY-016; `02_LLM_CLIENT_PROTOCOL.md` §7,
    # `09_READINESS_PROBE.md` §7) — 2 keys, none per-run-overridable ---
    "provider.probe_timeout_ms": "5000",
    "readiness.snapshot_staleness_ms": "30000",
    # --- circuit_breaker.* (STORY-023; `08_CIRCUIT_BREAKER.md` §7) — 3 keys,
    # all per-run-overridable ---
    "circuit_breaker.enabled": "true",
    "circuit_breaker.failure_threshold": "5",
    "circuit_breaker.cooldown_seconds": "60",
}

PER_RUN_OVERRIDABLE: frozenset[SettingKey] = frozenset(
    {
        # Every benchmark.* key except benchmark.last_mode (11)
        "benchmark.warmup_enabled",
        "benchmark.retry_count",
        "benchmark.max_output_tokens",
        "benchmark.temperature",
        "benchmark.min_timeout_seconds",
        "benchmark.max_timeout_seconds",
        "benchmark.consecutive_max_timeouts_to_exclude",
        "benchmark.pause_on_phase_switch",
        "benchmark.pause_on_provider_switch",
        "benchmark.pause_on_model_switch",
        "benchmark.stop_on_provider_health_failure",
        # Both feature.* keys (2) — NOT ui.stream_tokens_to_log
        "feature.reasoning_effort_default",
        "feature.judge_run_analysis_enabled",
        # Every eval.* key (14)
        "eval.phase_keyword_enabled",
        "eval.phase_cosine_enabled",
        "eval.phase_judge_enabled",
        "eval.force_judge_on_prior_failure",
        "eval.cosine_threshold",
        "eval.judge_max_completion_tokens",
        "eval.judge_timeout_min_seconds",
        "eval.judge_timeout_max_seconds",
        "eval.judge_timeout_escalation_steps",
        "eval.judge_timeout_consecutive_threshold",
        "eval.embedding_timeout_seconds",
        "eval.min_sample_size",
        "eval.embedding_consecutive_failures_to_skip",
        "eval.embedding_cache_max_entries",
        "eval.min_cosine_coverage",
        # All three circuit_breaker.* keys (3, STORY-023)
        "circuit_breaker.enabled",
        "circuit_breaker.failure_threshold",
        "circuit_breaker.cooldown_seconds",
    }
)
