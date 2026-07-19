---
id: STORY-057
title: Build the Resume and Retry flows — Resume Summary dialog with drift and the Retry Selection dialog
status: ready
spec_clauses:
  - 03_Resume_Benchmark_Widget/description.md#41-resumable-run
  - 07_Common_Dialogs/resume_summary_dialog.md#5-drift-warnings
  - 07_Common_Dialogs/resume_summary_dialog.md#6-resume-gating
  - 07_Common_Dialogs/resume_summary_dialog.md#7-task-selection-inline-picker
  - 07_Common_Dialogs/resume_summary_dialog.md#11-resume-effects
  - 07_Common_Dialogs/retry_selection_dialog.md#7-pre-selection-rule
  - 07_Common_Dialogs/retry_selection_dialog.md#13-confirm-effects
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b3-resumegateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/resume_benchmark/
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-057-AC-1
  - STORY-057-AC-2
  - STORY-057-AC-3
  - STORY-057-AC-4
  - STORY-057-AC-5
  - STORY-057-AC-6
  - STORY-057-AC-7
edge_cases:
  - EC-RUN-5
  - EC-RUN-6
  - EC-RUN-11
  - EC-PERSIST-4
depends_on:
  - STORY-049
  - STORY-051
  - STORY-056
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-057 — Build the Resume and Retry flows — Resume Summary dialog with drift and the Retry Selection dialog

## Goal

Deliver the two flows that re-run persisted work: the Resume Summary dialog (opened by the
Resume Run button / double-click) that shows the run's frozen configuration, current progress,
the Run Drift Detector warnings, and an inline pre-checked task picker before handing off to
`resume_run`; and the Retry Selection dialog (opened by the Retry row action) that lists every
result row with a status filter, pre-selects the failed and incomplete rows, and on confirm
resets the chosen rows and resumes.

## In scope

- `ui/resume_benchmark/`: the Resume Run enablement (resumable AND not executing), the Resume
  Summary dialog invocation and the resume hand-off through `ResumeGateway.resume_run`, and the
  Retry row action invoking the Retry Selection dialog.
- `ui/common_dialogs/` Resume Summary dialog factory: the drift-warning panel grouped by
  severity, the `BLOCKING`-warning "Resume anyway" gate, the Fix-in-Settings routing, and the
  inline Tasks-to-resume picker with its pre-check rule.
- `ui/common_dialogs/` Retry Selection dialog factory: the checkable result table, the Filter
  dropdown defaulting to `Only failed`, the group-based pre-selection, the bulk visible-row
  toggles, the selection summary line, and the reset-then-resume confirm effects.

## Out of scope

- The run table, search, sort, and the clone/rename/delete/export/log actions — delivered by
  STORY-056.
- The `RunDriftDetector` algorithm and the pipeline resume use case — consumed behind the
  gateway; the drift result is rendered, not computed here.
- Wiring the concrete `ResumeGateway` and mounting the dialog factories in `compose.py` — this
  story **must not touch** `compose.py` (Phase 11 owns it).

## Spec inputs

- `03_Resume_Benchmark_Widget/description.md#41-resumable-run` — the resumable-status and
  resumable-result definition that gates the Resume Run action.
- `07_Common_Dialogs/resume_summary_dialog.md#5-drift-warnings` — the drift-warning grouping by
  `DriftSeverity` and the Fix-in-Settings affordance per blocking provider/embedding warning.
- `07_Common_Dialogs/resume_summary_dialog.md#6-resume-gating` — Resume enabled directly when no
  `BLOCKING` warning, gated behind the "Resume anyway" checkbox otherwise.
- `07_Common_Dialogs/resume_summary_dialog.md#7-task-selection-inline-picker` — the inline
  picker, the not-yet-completed-pre-checked rule, and the completed-but-tickable rule.
- `07_Common_Dialogs/resume_summary_dialog.md#11-resume-effects` — the reset-checked-tasks and
  resume-against-frozen-snapshot sequence.
- `07_Common_Dialogs/retry_selection_dialog.md#7-pre-selection-rule` — the per-group
  pre-selection (failed + incomplete checked, completed unchecked).
- `07_Common_Dialogs/retry_selection_dialog.md#13-confirm-effects` — the
  `reset_results_for_retry` stage-preserving reset and the resume hand-off.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b3-resumegateway` — `resumable_results`,
  `reset_results` / `reset_results_for_retry`, `refresh_readiness`, `resume_run`.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The dialogs present and route only; they never edit a run, its snapshot, or a result in
  place beyond the reset the confirm action performs through the gateway.
- The pre-selection is computed once on open; changing the filter never re-applies it.
- A `COMPLETED` row is never re-run unless the user explicitly checks it.
- A `FAILED_JUDGE_TIMEOUT` retry is stage-preserving via `reset_results_for_retry` (DD-66);
  every other retryable status resets to `PENDING` and re-runs the whole task.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-057-AC-1

Given a run that is resumable and not executing, when the widget renders the footer, then the
Resume Run button is enabled; and given a run whose status is `COMPLETED`, then the Resume Run
button is disabled with the "fully completed — nothing to resume" reason.

### STORY-057-AC-2

Given the Run Drift Detector returned one or more `BLOCKING` warnings, when the Resume Summary
dialog renders, then the Resume Run button is disabled until the "Resume anyway" checkbox is
ticked, and enabling it once ticked.

### STORY-057-AC-3

Given the Resume Summary inline task picker, each resumable task row's initial check state
follows its status:

| Task status on open                                                                  | Pre-checked |
| ------------------------------------------------------------------------------------ | ----------- |
| PENDING                                                                              | yes         |
| FAILED_INFERENCE / FAILED_PROVIDER / FAILED_TIMEOUT / FAILED_JUDGE_TIMEOUT / ERRORED | yes         |
| RUNNING_INFERENCE / AWAITING\_\*                                                     | yes         |
| COMPLETED                                                                            | no          |

### STORY-057-AC-4

Given the user confirms the Resume Summary dialog, when Resume Run is clicked, then only the
checked tasks are reset and `ResumeGateway.resume_run(run_id)` is called; unchecked tasks keep
their stored status and are not re-run.

### STORY-057-AC-5

Given the Retry Selection dialog opens against a run, then the Filter defaults to `Only failed`
and the failed and incomplete rows are pre-checked while completed rows are unchecked; and when
the user confirms, then `ResumeGateway.reset_results_for_retry(result_ids)` is called with the
checked result ids and the resume is triggered.

### STORY-057-AC-6

For each retry-reset row, the reset target matches its status per `reset_results_for_retry`:

| Row status                                          | Reset target                                          |
| --------------------------------------------------- | ----------------------------------------------------- |
| FAILED_JUDGE_TIMEOUT                                | AWAITING_JUDGE_CHECK (judge-only, response preserved) |
| FAILED_INFERENCE / FAILED_PROVIDER / FAILED_TIMEOUT | PENDING (whole-task re-run)                           |
| ERRORED (no response)                               | PENDING                                               |
| RUNNING_INFERENCE / AWAITING\_\*                    | PENDING                                               |

### STORY-057-AC-7

For each of this story's dialog factory functions, constructing it with a fake `ResumeGateway`
and mounting it under `qtbot`, then showing it (`qtbot.addWidget(...)`, `.show()`, one
`qtbot.wait(0)`/event-loop pump), raises no exception, reports `isVisible()`, and captures no
`error`/`critical`-level `structlog` record — verified by wrapping construction+show in
`structlog.testing.capture_logs()` and asserting no captured entry's `log_level` is in
`{"error", "critical"}`:

| Factory function              | Owning module        |
| ----------------------------- | -------------------- |
| `make_resume_summary_dialog`  | `ui/common_dialogs/` |
| `make_retry_selection_dialog` | `ui/common_dialogs/` |

## Test plan

- STORY-057-AC-1 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_resume_gating.py`,
  `test_resume_button_enabled_only_for_resumable_not_executing`. Covers EC-RUN-5, EC-RUN-6.
- STORY-057-AC-2 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_resume_summary_dialog.py`,
  `test_blocking_drift_gates_resume_behind_checkbox`. Covers EC-RUN-11.
- STORY-057-AC-3 — table-driven unit (`pytest-qt`), same file,
  `test_task_picker_precheck_per_status`. Covers EC-PERSIST-4.
- STORY-057-AC-4 — unit (`pytest-qt`, fake `ResumeGateway`), same file,
  `test_resume_resets_only_checked_and_calls_resume_run`.
- STORY-057-AC-5 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_retry_selection_dialog.py`,
  `test_default_filter_preselection_and_confirm_resets_and_resumes`.
- STORY-057-AC-6 — table-driven unit, same file, `test_retry_reset_target_per_status`.
- STORY-057-AC-7 — unit (`pytest-qt`, fake `ResumeGateway`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_resume_summary_dialog.py`,
  `test_resume_summary_dialog_constructs_and_shows_with_no_error_logs`, and colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_retry_selection_dialog.py`,
  `test_retry_selection_dialog_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-057.
- [x] EC-RUN-5, EC-RUN-6, EC-RUN-11, and EC-PERSIST-4 each have a passing test.
- [x] The `pytest-qt` suite reaches ≥60% branch coverage and exercises every state in the
  Resume Summary and Retry Selection dialog state machines.
- [x] An architecture test confirms the dialogs and the resume/retry actions depend only on
  `ResumeGateway` (via the widget), and that the modules reference no `setStyleSheet`, embed
  no colour literal, and import no `asyncio`.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/resume_benchmark/` and
  `ui/common_dialogs/`.
- [x] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-057. (Repo-wide `just trace-check` still fails on
  ~33 pre-existing edge-case gaps from earlier stories, unrelated to STORY-057 -- confirmed by
  diffing against the pre-STORY-057 commit, which already showed the same failures plus
  EC-RUN-5/6/11 that this story's tests now additionally close.)
- [x] The module inventory is unchanged.
- [x] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
