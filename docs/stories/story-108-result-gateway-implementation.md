---
id: STORY-108
title: Implement the concrete Result gateway over the run reads, charts, exports, and run analysis
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 05_Result_Widget/implementation_structure.md#9-dependency-protocols
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#21-public-api-surface
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#9-threading-and-concurrency
modules:
  - ui/results/
acceptance_criteria:
  - STORY-108-AC-1
  - STORY-108-AC-2
  - STORY-108-AC-3
  - STORY-108-AC-4
  - STORY-108-AC-5
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: M
---

# STORY-108 — Implement the concrete Result gateway over the run reads, charts, exports, and run analysis

## Goal

Make the Result surface show real data. Its run selector lists the real runs; the Summary, Details and
Charts tabs read that run's real results and task metadata; the export footer produces real CSV and
Markdown; the tab choice and export preferences persist; and the Run Analysis tab can generate a fresh
narrative through a provider and model the user picks, refusing politely when another inference is
already in flight. All of it goes through one object the widget holds.

## In scope

- The concrete `ResultGateway` implementation and its `make_result_gateway(...)` factory on the
  adapters layer's public surface.
- The five run and result read methods (run header list, single run header, results, tasks) and the
  run-analysis persistence write.
- The two settings methods backing `ui.last_result_tab`, `ui.export_save_directly` and
  `ui.score_display_format`.
- The chart-data computation and the summary/details table serialisation.
- `regenerate_run_analysis(...)`: the single-inference-gate acquisition, the worker dispatch, the
  graphical-thread completion callback, and translating the backend run-analysis result into the
  user-interface-local result type — including resolving the analysis provider's display **name** so
  the tab never sees the internal provider identifier.

## Out of scope

- Wiring the gateway into `make_result_widget` and `build_app` — owned by STORY-077.
- The widget's own behaviour and its four tab sub-features — already delivered by STORY-061 …
  STORY-065 and STORY-071; this story changes no user-interface code.
- The `ExportFilenameHelper` bridge declared by `ui/results/protocols.py` — owned by STORY-077 per
  ADR-0010; this gateway supplies the payload, not the filename.
- Writing an export to disk — owned by the native pickers and file-system-actions adapters at the
  dialog level; `serialize_table` returns the payload only.
- The Generate Analysis dialog's own `RunAnalysisDispatcher` Protocol — already satisfied structurally
  by the Run Analysis tab controller (STORY-065); no adapter object is written for it.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway` — the ten base method signatures,
  verbatim, and the statement that this gateway wraps the runs store (headers; persisting
  `run_analysis`), the results store (tab caches), the tasks store (per-task metadata), the settings
  layer (`ui.last_result_tab`, `ui.export_save_directly`, `ui.score_display_format`), the run-analysis
  service (regenerate), the chart service, and the table serialisation service.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the gateway is
  method-only, carries stdlib and `msgspec` types only, no `psygnal` and no Qt symbol, and is scoped
  to the methods its controller actually calls (SPEC-074).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract` — chart aggregation and
  CSV generation are submitted to the `TaskRunner`; a worker never touches a widget, and results reach
  the graphical thread through the adapter.
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — view-model conversion is
  the adapter's job: it translates a backend domain record into the shape the view renders.
- `05_Result_Widget/implementation_structure.md#9-dependency-protocols` — the widget's dependency set,
  read as the capabilities the adapter wires behind this gateway.
- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#21-public-api-surface` — the run-analysis
  service takes the caller-chosen run, provider and model and returns an outcome record; it loads the
  run, results and task metadata itself, so the gateway assembles none of them.
- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#9-threading-and-concurrency` — the generate
  call is blocking and runs on a `TaskRunner` worker thread, and it holds the judge-analysis activity
  on the single-inference gate for its duration.

## Design constraints

- **Where the code lands, and why `modules:` says `ui/results/`.** The implementation lands in
  `adapters/ui_gateways/`, which the read-only module inventory does not yet list; ADR-0014 records
  the pending one-row correction. `modules:` names the user-interface module whose gateway Protocol
  this story satisfies, per the STORY-076/ADR-0010 precedent. Add `adapters/ui_gateways/` once the
  correction is ratified.
- `regenerate_run_analysis`'s signature is a documented local addition this module's own Protocol
  already records: it takes the run, provider and model plus a keyword-only completion callback and
  returns `bool`. Implement that shape exactly — do not "correct" it back to §7b.5's shorter draft.
- The gateway is the only object that may hold the provider registry here, so it is the only place the
  analysis provider's display **name** can be resolved. The result it hands the callback carries that
  resolved name; the internal provider identifier is never placed on it and never displayed (DD-33).
- The user-interface-local result and outcome types are a deliberate mirror of the backend
  run-analysis types, because `ui/results/` may not import the run-analysis module. The gateway
  performs the translation at its own boundary; it must not leak a backend run-analysis type across
  it.
- `get_setting` returns `str | None`, so it reads through `AppSettingsStore.get_setting(key)`;
  `set_setting` writes through `SettingsService.set(key, value)`, so the settings-changed event still
  fires. `SettingsService` has no nullable getter, which is why both collaborators are needed.
- Constructing the gateway must be side-effect free — no backend read, no probe, no network call — so
  STORY-077-AC-2 (`build_app` issues no network call) holds.
- The gateway holds no Qt symbol on its public surface. `adapters/ui_gateways/` must not import `ui`
  (`import-linter`); the Protocol is satisfied structurally.

## Acceptance criteria

### STORY-108-AC-1

Each `ResultGateway` method other than `regenerate_run_analysis` performs exactly the stated backend
interaction against its injected collaborators and returns that collaborator's value unchanged:

| Gateway method                        | Backend interaction                                                    |
| ------------------------------------- | ---------------------------------------------------------------------- |
| `list_runs()`                         | returns the runs store's full header list                              |
| `get_run(run_id)`                     | returns the runs store's header row for `run_id`                       |
| `persist_run_analysis(run_id, patch)` | applies `patch` to `run_id`'s header through the runs store            |
| `list_results(run_id)`                | returns the results store's result rows for `run_id`                   |
| `list_tasks(run_id)`                  | returns the tasks store's task rows for `run_id`                       |
| `get_setting(key)`                    | reads `key` from the app-settings store; returns `None` when unset     |
| `set_setting(key, value)`             | writes `key` through the settings service                              |
| `chart_data(run_id, chart_kind)`      | returns the chart service's prepared data for that run and chart kind  |
| `serialize_table(run_id, table, fmt)` | returns the table serialiser's payload for that run, table, and format |

### STORY-108-AC-2

Given the single-inference gate is free,
when `regenerate_run_analysis(run_id, provider_id, model_name, on_complete=...)` is called from the
graphical thread,
then it returns `True` immediately, the run-analysis service runs on a `TaskRunner` worker thread, and
`on_complete` is later invoked on the graphical thread exactly once.

### STORY-108-AC-3

Given the single-inference gate is already held by another activity,
when `regenerate_run_analysis(...)` is called,
then it returns `False`, the run-analysis service is never called, and `on_complete` is never invoked.

### STORY-108-AC-4

Given the run-analysis service returns a successful outcome for a provider whose display name differs
from its internal identifier,
when the completion callback receives the result,
then the result carries that provider's display name and no field on it contains the internal provider
identifier.

### STORY-108-AC-5

Given fake runs-store, results-store, tasks-store, settings, run-analysis, chart, serialiser, gate,
and provider-registry collaborators that record every call,
when `make_result_gateway(...)` is called,
then the factory returns a gateway and no method was invoked on any collaborator.

## Test plan

- STORY-108-AC-1 — unit, table-driven (one `@pytest.mark.parametrize` row per method, total over all
  nine), colocated `src/ollama_llm_bench/adapters/ui_gateways/tests/test_result_gateway.py`,
  `test_each_method_performs_its_backend_interaction`.
- STORY-108-AC-2 — unit (`pytest-qt`, offscreen, for the graphical-thread callback assertion), same
  file, `test_regenerate_dispatches_to_a_worker_and_calls_back_on_the_gui_thread`.
- STORY-108-AC-3 — unit, same file, `test_regenerate_refuses_when_the_gate_is_held`.
- STORY-108-AC-4 — unit, same file, `test_result_carries_the_provider_display_name_not_the_id`.
- STORY-108-AC-5 — unit, same file, `test_constructing_the_gateway_touches_no_collaborator`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-108.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory change ADR-0014 describes has been ratified and applied, and
  `adapters/ui_gateways/` appears in this story's `modules:`.
