---
id: STORY-109
title: Implement the concrete Resume gateway over the run, result, and task stores and the resume command
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b3-resumegateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 03_Resume_Benchmark_Widget/implementation_structure.md#7-dependency-protocols
  - 11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#8-error-handling
modules:
  - ui/resume_benchmark/
  - ui/common_dialogs/
  - adapters/ui_gateways/
acceptance_criteria:
  - STORY-109-AC-1
  - STORY-109-AC-2
  - STORY-109-AC-3
  - STORY-109-AC-4
  - STORY-109-AC-5
edge_cases: []
depends_on: []
adrs:
  - ADR-0014
owner: coder
estimate: L
---

# STORY-109 — Implement the concrete Resume gateway over the run, result, and task stores and the resume command

## Goal

Make the Resume panel and its three dialogs work against the real database. The past-run table lists
real runs with real counts and remembers its sort column; Resume restarts an unfinished run from where
crash recovery left it; Retry re-runs just the failures the user picked, preserving a judge-only
failure's existing response; Clone copies a run into a fresh one; Rename and Delete do what they say;
and the Resume Summary dialog warns about configuration that has drifted since the run was created.
All of it goes through one object the panel holds.

## In scope

- The concrete `ResumeGateway` implementation and its `make_resume_gateway(...)` factory on the
  adapters layer's public surface — all twenty-two methods.
- The run-header surface: list, get, create, status patch, rename, delete.
- The result surface: list, resumable list, whole-task reset, stage-preserving retry reset, create,
  patch.
- The task surface: list and create, for Clone.
- The readiness refresh and the drift detection the Resume Summary dialog runs.
- The sort-setting read and write, the resume command, the run-active and active-run queries, and the
  summary/details table serialisation the export actions need.
- Confirming the same concrete class satisfies the Rename Run, Resume Summary and Retry Selection
  dialog gateways with no extra adapter class.

## Out of scope

- Wiring the gateway into `make_resume_benchmark_widget` and `build_app` — owned by STORY-077.
- The panel's and dialogs' own behaviour — already delivered by STORY-056, STORY-057 and STORY-072;
  this story changes no user-interface code.
- The `ExportFilenameHelper` bridge declared by `ui/resume_benchmark/protocols.py` — owned by
  STORY-077 per ADR-0010; this gateway supplies the payload, not the filename.
- The resume row-selection algorithm and the stage-preserving retry semantics themselves — already
  delivered in the pipeline and the results store; this gateway delegates and adds no selection logic.
- The drift comparison algorithm — already delivered by `backend/run_drift/`; this gateway refreshes
  readiness and calls it.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b3-resumegateway` — the twenty-one method signatures,
  verbatim, and the statement that this gateway wraps the runs store, results store, tasks store,
  `ReadinessService` (drift refresh), the settings layer (sort persistence), and the resume command.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the gateway is
  method-only, carries stdlib and `msgspec` types only, no `psygnal` and no Qt symbol, and is scoped
  to the methods its controller actually calls (SPEC-074).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract` — a *fast-synchronous*
  method (a memory read, or a fast SQLite read/write under write-ahead logging) may be called from the
  graphical thread; the graphical thread never blocks.
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — the adapter holds the
  backend Protocols and decides how to satisfy each gateway method.
- `03_Resume_Benchmark_Widget/implementation_structure.md#7-dependency-protocols` — the panel's
  dependency set, read as the capabilities the adapter wires behind this gateway.
- `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#8-error-handling` — the detector reports every
  environment-availability problem as a returned warning and never raises, which is the contract
  `detect_drift` must preserve at the gateway boundary.

## Design constraints

- **Where the code lands.** The implementation lands in `adapters/ui_gateways/`. ADR-0014 is
  accepted and its inventory row now exists, so `modules:` names that path directly.

## Acceptance criteria

### STORY-109-AC-1

Each `ResumeGateway` method performs exactly the stated backend interaction against its injected
collaborators and returns that collaborator's value unchanged:

| Gateway method                        | Backend interaction                                                          |
| ------------------------------------- | ---------------------------------------------------------------------------- |
| `list_runs()`                         | returns the runs store's header list, newest first                           |
| `get_run(run_id)`                     | returns the runs store's fully assembled run for `run_id`                    |
| `create_run(run)`                     | creates a run header plus snapshots through the runs store; returns its id   |
| `update_run_status(run_id, patch)`    | applies the status/counter `patch` through the runs store                    |
| `rename_run(run_id, name)`            | sets or clears `run_id`'s user-facing name through the runs store            |
| `delete_run(run_id)`                  | deletes `run_id` and its dependent rows through the runs store               |
| `list_results(run_id)`                | returns the results store's result rows for `run_id`                         |
| `resumable_results(run_id)`           | returns the results store's resume-eligible rows for `run_id`                |
| `reset_results(result_ids)`           | whole-task resets those rows to pending; returns the count reset             |
| `reset_results_for_retry(result_ids)` | stage-preserving retry reset of those rows; returns the count reset          |
| `create_results(results)`             | inserts those initial result rows through the results store                  |
| `update_result(result_id, patch)`     | applies the partial `patch` to that row through the results store            |
| `list_tasks(run_id)`                  | returns the tasks store's frozen task rows for `run_id`                      |
| `create_tasks(run_id, tasks)`         | inserts `run_id`'s frozen task snapshot through the tasks store              |
| `refresh_readiness()`                 | returns the readiness service's refreshed snapshot                           |
| `detect_drift(run_id)`                | refreshes readiness, then returns the drift detector's warnings for `run_id` |
| `get_sort_setting()`                  | reads the persisted sort column and descending flag from the settings layer  |
| `set_sort_setting(column, desc)`      | writes the sort column and direction through the settings service            |
| `resume_run(run_id)`                  | passes `run_id` to the flow API's resume entry point                         |
| `is_run_active()`                     | returns the flow API's current run-active answer                             |
| `active_run_id()`                     | returns the flow API's executing run id, or `None` when idle                 |
| `serialize_table(run_id, table, fmt)` | returns the table serialiser's payload for that run, table, and format       |

### STORY-109-AC-2

Given a drift detector whose readiness collaborator reports an unreachable provider,
when `detect_drift(run_id)` is called,
then it returns the drift warnings describing that condition and raises no exception.

### STORY-109-AC-3

`serialize_table` accepts the same token vocabulary as the Result gateway and returns the serialiser's
payload for each combination:

| `table`   | `fmt`      | Serialiser invoked with                   |
| --------- | ---------- | ----------------------------------------- |
| `summary` | `csv`      | the summary table, comma-separated format |
| `summary` | `markdown` | the summary table, Markdown format        |
| `details` | `csv`      | the details table, comma-separated format |
| `details` | `markdown` | the details table, Markdown format        |

### STORY-109-AC-4

Given a run with one judge-only failure row and one inference-failure row, both selected,
when `reset_results_for_retry` is called with both row identifiers,
then it returns `2`, the judge-only row keeps its stored response, and the inference-failure row is
reset for a whole-task re-run.

### STORY-109-AC-5

Given fake runs-store, results-store, tasks-store, readiness, drift-detector, settings, flow, and
serialiser collaborators that record every call,
when `make_resume_gateway(...)` is called,
then the factory returns a gateway and no method was invoked on any collaborator.

## Test plan

- STORY-109-AC-1 — unit, table-driven (one `@pytest.mark.parametrize` row per gateway method, total
  over all twenty-two), colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_resume_gateway.py`,
  `test_each_method_performs_its_backend_interaction`.
- STORY-109-AC-2 — unit, same file, `test_detect_drift_reports_warnings_and_never_raises`.
- STORY-109-AC-3 — unit, table-driven (one row per table/format pair), same file,
  `test_serialize_table_accepts_the_shared_token_vocabulary`.
- STORY-109-AC-4 — unit, same file, `test_retry_reset_preserves_a_judge_only_failures_response`.
- STORY-109-AC-5 — unit, same file, `test_constructing_the_gateway_touches_no_collaborator`.
- The three Common-Dialogs structural-satisfaction checks are proven by STORY-104-AC-2, not duplicated
  here.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-109.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The traceability record validates with no orphan clause and no orphan test for
  STORY-109 (repo-wide `trace-check` still reports the pre-existing, unrelated EC-M-1..8
  gaps tracked by Phase 11 stories 076-081 — see traceability.yaml diff for this change,
  which touches only STORY-109's own AC rows).
- [x] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.

## Notes

A spec-conformance review of this story's first implementation pass found one real defect:
`detect_drift` sourced its `live_providers` catalog from `ProviderRegistry.list_enabled()`
(the enabled subset only) rather than `ProvidersStore.list_providers()` (every configured
provider). The provider-drift check in `backend/run_drift/_internal/provider_check.py`
distinguishes `PROVIDER_REMOVED` (no live entry at all) from `PROVIDER_NOW_DISABLED` (a live
entry exists but `enabled is False`) purely by reading that flag on each live entry — passing
only the enabled subset made a disabled-but-still-configured provider indistinguishable from a
removed one, and the `PROVIDER_NOW_DISABLED` warning the spec's own §10.2 walks through by name
was structurally unreachable. Fixed by adding `ProvidersStore` as an eleventh gateway
collaborator (`_ResumeGateway.detect_drift` now reads the full catalog from it;
`ProviderRegistry` is still used for `get_client(...)` on each reachable provider), with a new
regression test (`test_detect_drift_includes_disabled_providers_in_the_live_catalog`) asserting
a disabled provider's `ProviderConfig` reaches the detector's `live_providers` input unchanged.

Two smaller items the same review raised are recorded here rather than resolved, since both
are decisions for whoever picks up STORY-077 (the widget-wiring story), not this gateway story:

- **`detect_drift` is genuinely blocking (readiness re-probe fan-out plus one `list_models()`
  network call per enabled, reachable provider), but the one existing caller today**
  (`ui/common_dialogs/api.py`'s `make_resume_summary_dialog`) **invokes it inline from a widget
  factory reachable from a button click** — i.e. on the GUI thread. Nothing breaks today
  because no real gateway is wired into that factory yet, but once STORY-077 wires this
  gateway in, that call site will freeze the UI for the probe's duration unless it is first
  marshalled onto the dispatcher/a worker thread. STORY-077 (or a dedicated follow-up) must
  address this before wiring lands.
- **Sort-column/direction persistence deliberately bypasses `SettingsService`** (see this
  story's own Design decision 3) using two raw `AppSettingsStore` keys not present in
  `backend/settings/_internal/registry.py`'s registry or the settings import/export catalog.
  This was an intentional, precedented choice (mirroring `MainWindowGateway`'s own window-shell
  keys) made because no registered key exists and adding one is out of this story's
  `backend/settings/` scope — but it means these two keys will not round-trip through a
  settings export/import today. A future story should either register them in
  `backend/settings/` or extend the import/export catalog to include raw, unregistered
  `AppSettingsStore` keys.
