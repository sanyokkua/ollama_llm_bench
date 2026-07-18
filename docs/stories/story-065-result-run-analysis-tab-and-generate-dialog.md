---
id: STORY-065
title: Build the Result widget Run Analysis tab and the Generate Analysis dialog
status: ready
spec_clauses:
  - 05_Result_Widget/tabs/run_analysis_tab.md#4-generation-timing
  - 05_Result_Widget/tabs/run_analysis_tab.md#6-rendering-and-no-length-cap
  - 05_Result_Widget/tabs/run_analysis_tab.md#9-empty-and-failed-states
  - 05_Result_Widget/tabs/run_analysis_tab.md#10-footer-export
  - 07_Common_Dialogs/generate_analysis_dialog.md#4-provider-and-model-selection
  - 07_Common_Dialogs/generate_analysis_dialog.md#6-filter-rule
  - 07_Common_Dialogs/generate_analysis_dialog.md#8-confirm-behaviour-and-the-single-inference-gate
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/results/
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-065-AC-1
  - STORY-065-AC-2
  - STORY-065-AC-3
  - STORY-065-AC-4
  - STORY-065-AC-5
  - STORY-065-AC-6
  - STORY-065-AC-7
edge_cases:
  - EC-RES-3
  - EC-RUN-12
  - EC-RUN-14
  - EC-PROV-4e
depends_on:
  - STORY-049
  - STORY-052
  - STORY-061
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-065 — Build the Result widget Run Analysis tab and the Generate Analysis dialog

## Goal

Deliver the Run Analysis tab sub-feature package under `ui/results/_internal/run_analysis_tab/`
and the Generate Analysis dialog in `ui/common_dialogs/`: the tab renders `BenchmarkRun.run_analysis`
as Markdown in full with no length cap, shows the generation metadata, exposes Copy and the
dynamic-label Generate / Regenerate button, and handles the empty / generating / ready / failed
states; the dialog picks the analysis `(provider, model)` pair, binds Confirm to the
single-inference gate, and dispatches the generation through the parent controller.

## In scope

- `_internal/run_analysis_tab/controller.py` (`JudgeAnalysisTabController`): subscribes
  `_run_analysis_received` and `_inference_activity_changed`; derives the `empty` / `generating`
  / `ready` / `failed` state, the metadata line, and the Generate/Regenerate button label and
  gating.
- `_internal/run_analysis_tab/view.py`: the Markdown body (theme-aware, no length cap, lazy for
  very long narratives), the metadata strip, and the Copy and Generate/Regenerate toolbar
  buttons; the Markdown-only footer export.
- `ui/common_dialogs/` Generate Analysis dialog factory: the shared provider/model dropdowns
  (model filtered to chat-capable, non-embedding), the snapshot-or-default pre-fill, the
  gate-busy inline message, the confirm-behaviour that acquires `JUDGE_ANALYSIS` through the
  service via the parent controller, and the live progress line (`context=RUN_ANALYSIS`).
- The `regenerate_analysis(run_id, provider_id, model_name)` parent-controller entry point that
  the dialog dispatches through and that persists the returned narrative and emits
  `_run_analysis_received`.

## Out of scope

- The Result shell and footer — owned by STORY-061.
- The `RunAnalysisService` and the single-inference gate implementation — consumed behind the
  gateway; the tab and dialog never call the model directly.
- Wiring the concrete `ResultGateway` and mounting the dialog factory in `compose.py` — this
  story **must not touch** `compose.py` (Phase 11 owns it).

## Spec inputs

- `05_Result_Widget/tabs/run_analysis_tab.md#4-generation-timing` — the auto-vs-on-demand
  generation rule driven by the run's snapshot of `feature.judge_run_analysis_enabled`, not the
  run mode.
- `05_Result_Widget/tabs/run_analysis_tab.md#6-rendering-and-no-length-cap` — full Markdown
  rendering with no truncation, theme-aware, scrolling and lazy for long bodies.
- `05_Result_Widget/tabs/run_analysis_tab.md#9-empty-and-failed-states` — the four tab states and
  the preserve-prior-narrative-on-failure rule.
- `05_Result_Widget/tabs/run_analysis_tab.md#10-footer-export` — the Markdown-only export,
  disabled while any run is non-terminal and while no narrative exists.
- `07_Common_Dialogs/generate_analysis_dialog.md#4-provider-and-model-selection` — the shared
  dropdown wiring and the reset-to-first-admitted-model rule.
- `07_Common_Dialogs/generate_analysis_dialog.md#6-filter-rule` — the chat-capable, non-embedding
  model filter.
- `07_Common_Dialogs/generate_analysis_dialog.md#8-confirm-behaviour-and-the-single-inference-gate` —
  the `try_acquire(JUDGE_ANALYSIS)` gate handling, the Generating sub-state, and the stay-open
  inline-busy path when the gate is held.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway` — `regenerate_run_analysis`,
  `persist_run_analysis`, `serialize_table` (Markdown export).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store` — the gate the
  Generate/Regenerate button and the dialog Confirm bind to.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The tab sub-controller depends only on `ResultGateway`, `EventBus`, `Clipboard`, and the shared
  dropdowns' `ProviderRegistry` (via those widgets); it holds no `RunAnalysisService` directly
  (D-R-06).
- A failed regeneration never overwrites a previously stored narrative.
- The Generate/Regenerate button label is `Generate analysis` when the run has no `run_analysis`
  and `Regenerate analysis` when it does; it is disabled with the matching tooltip while
  non-terminal, gate-held, or the run has zero completed results.
- The narrative body is never truncated and never redacted (own-machine data).
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-065-AC-1

Given a run whose `run_analysis` is set, when the tab renders, then the full Markdown narrative
is displayed with no length cap or truncation and the metadata line shows the generation time,
duration, and snapshot analysis-model name.

### STORY-065-AC-2

For each tab state, the body renders the specified content:

| Condition                                                       | State                                           |
| --------------------------------------------------------------- | ----------------------------------------------- |
| `run_analysis` absent, run still running                        | empty ("generated when the benchmark finishes") |
| `run_analysis` absent, finished run, analysis not requested     | empty ("was not requested … Generate now")      |
| a generation is in flight for this run                          | generating (spinner, `Generating...`)           |
| the most recent generation failed and no prior narrative exists | failed (classified reason)                      |

### STORY-065-AC-3

Given a regeneration fails while a prior good narrative is stored, when the failure arrives,
then the prior narrative stays rendered and `run_analysis` is not overwritten, with a soft error
banner shown above the body.

### STORY-065-AC-4

Given the selected run is terminal with completed results and the inference gate is `IDLE`, when
the tab renders the toolbar, then the Generate/Regenerate button is enabled with the label
matching whether `run_analysis` is present; and when a `_inference_activity_changed` reports the
gate held by another activity, then the button is disabled with the matching tooltip.

### STORY-065-AC-5

Given the Generate Analysis dialog is open, when the user selects a provider, then the model
dropdown repopulates filtered to chat-capable, non-embedding models; and when the user confirms,
then the generation is dispatched through the parent controller's
`regenerate_analysis(run_id, provider_id, model_name)`.

### STORY-065-AC-6

Given the dialog Confirm is clicked while `try_acquire(JUDGE_ANALYSIS)` would fail (the gate is
held by another activity), then the dialog stays open, shows the inline busy message, disables
Confirm, and re-enables it when `_inference_activity_changed` reports the gate `IDLE`.

### STORY-065-AC-7

Given the Generate Analysis dialog is constructed via its own factory function
(`make_generate_analysis_dialog`) with a fake `ResultGateway` and mounted under `qtbot`, when it
is shown (`qtbot.addWidget(...)`, `.show()`, one `qtbot.wait(0)`/event-loop pump), then no
exception is raised, the dialog reports `isVisible()`, and no `error`/`critical`-level
`structlog` record is captured — verified by wrapping construction+show in
`structlog.testing.capture_logs()` and asserting no captured entry's `log_level` is in
`{"error", "critical"}`.

## Test plan

- STORY-065-AC-1 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/results/tests/test_run_analysis_tab.py`,
  `test_full_narrative_and_metadata_rendered`. Covers EC-RES-3.
- STORY-065-AC-2 — table-driven unit (`pytest-qt`), same file,
  `test_tab_state_per_condition`.
- STORY-065-AC-3 — unit (`pytest-qt`), same file,
  `test_failed_regeneration_preserves_prior_narrative`. Covers EC-PROV-4e.
- STORY-065-AC-4 — unit (`pytest-qt`), same file,
  `test_generate_button_label_and_gate_binding`. Covers EC-RUN-12, EC-RUN-14.
- STORY-065-AC-5 — unit (`pytest-qt`, fake shared dropdowns + `ResultGateway`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_generate_analysis_dialog.py`,
  `test_model_filter_and_confirm_dispatch`.
- STORY-065-AC-6 — unit (`pytest-qt`), same file,
  `test_gate_busy_keeps_dialog_open_and_re_enables_on_idle`.
- STORY-065-AC-7 — unit (`pytest-qt`, fake `ResultGateway`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_generate_analysis_dialog.py`,
  `test_generate_analysis_dialog_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-065.
- [ ] EC-RES-3, EC-RUN-12, EC-RUN-14, and EC-PROV-4e each have a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the Run Analysis tab's
  empty/generating/ready/failed states and the Generate Analysis dialog state machine.
- [ ] An architecture test confirms the tab and dialog depend only on `ResultGateway` (via the
  widget) and consume `ProviderRegistry`/`RunAnalysisService` only through the shared
  dropdowns and the gateway, and that the modules reference no `setStyleSheet`, embed no
  colour literal, and import no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/results/` and `ui/common_dialogs/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-065.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
