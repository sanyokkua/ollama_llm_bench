---
id: STORY-107
title: Implement the concrete Progress gateway over the run controls, run reads, and the manual probe
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 04_Progress_Widget/implementation_structure.md#8-dependency-protocols
modules:
  - ui/progress/
  - ui/common_dialogs/
  - adapters/ui_gateways/
acceptance_criteria:
  - STORY-107-AC-1
  - STORY-107-AC-2
  - STORY-107-AC-3
  - STORY-107-AC-4
edge_cases: []
depends_on: []
adrs:
  - ADR-0014
owner: coder
estimate: M
---

# STORY-107 — Implement the concrete Progress gateway over the run controls, run reads, and the manual probe

## Goal

Make the live run-progress surface work against the real backend. Pause, Resume and Stop actually
control the running benchmark; the counters, current task and header read the run's real rows; the
run log can replay a past run's saved file and remembers its verbosity and auto-scroll preferences;
the inline rename pencil renames the run; and the stability panel's retry-probe button triggers a real
provider probe. All of it goes through one object the widget holds.

## In scope

- The concrete `ProgressGateway` implementation and its `make_progress_gateway(...)` factory on the
  adapters layer's public surface.
- The three run-control commands (pause, resume, stop) and the run-active query.
- The four run-read methods (run metadata, run header, per-task counters, past run-log load) and the
  run-header list the rename pencil's uniqueness check needs.
- The rename command and the two run-log settings methods.
- The manual provider probe and the run-log write-failure query.
- Confirming the same concrete class satisfies the Rename Run dialog's own gateway with no extra
  adapter class.

## Out of scope

- Wiring the gateway into `make_progress_widget` and `build_app` — owned by STORY-077.
- The widget's own behaviour, its four sub-controllers, the bounded log buffer, and the reconciliation
  timer — already delivered by STORY-058 … STORY-060 and STORY-073; this story changes no
  user-interface code.
- The pipeline's pause/resume/stop semantics and the cooperative cancellation token — already
  delivered; this story's commands delegate and add no control logic.
- Marshalling pipeline events onto the graphical thread — that is the event bus's Qt deliverer
  (`adapters/qt_event_bus/`), not a gateway concern; push state never arrives through a gateway
  return value.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b4-progressgateway` — the eleven base method
  signatures, verbatim, and the statement that this gateway wraps the flow service (pause, resume,
  stop), the run registry (run metadata, rename), the runs store (elapsed time, header, summary), the
  results store (per-task counters), the run-log reader (past-log load), the settings layer
  (`ui.run_log_verbosity`, `ui.auto_scroll_run_log`), and a manual-provider-probe command.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the gateway is
  method-only, carries stdlib and `msgspec` types only, no `psygnal` and no Qt symbol, and is scoped
  to the methods its controller actually calls (SPEC-074).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract` — cancellation is
  cooperative: pause and stop set the token and return; they never kill a worker mid-statement, and
  the graphical thread never blocks.
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — the adapter holds the
  backend Protocols and decides how to satisfy each gateway method.
- `04_Progress_Widget/implementation_structure.md#8-dependency-protocols` — the widget's dependency
  set, read as the capabilities the adapter wires behind this gateway.

## Design constraints

- **Where the code lands.** The implementation lands in `adapters/ui_gateways/`. ADR-0014 is
  accepted and its inventory row now exists, so `modules:` names that path directly.

## Acceptance criteria

### STORY-107-AC-1

Each `ProgressGateway` method performs exactly the stated backend interaction against its injected
collaborators and returns that collaborator's value unchanged:

| Gateway method             | Backend interaction                                                               |
| -------------------------- | --------------------------------------------------------------------------------- |
| `pause_run()`              | requests a cooperative pause of the active run through the flow API               |
| `resume_run()`             | requests resumption of the paused run through the flow API                        |
| `stop_run(reason)`         | requests a cooperative stop of the active run through the flow API, with `reason` |
| `run_metadata(run_id)`     | returns the run registry's record for `run_id`                                    |
| `rename_run(run_id, name)` | sets or clears `run_id`'s user-facing name through the runs store                 |
| `run_header(run_id)`       | returns the runs store's header row for `run_id`                                  |
| `task_counters(run_id)`    | returns the results store's result rows for `run_id`                              |
| `load_past_log(run_id)`    | returns the run-log reader's saved log text for `run_id`                          |
| `get_setting(key)`         | reads `key` from the app-settings store; returns `None` when unset                |
| `set_setting(key, value)`  | writes `key` through the settings service                                         |
| `manual_provider_probe()`  | submits a provider probe and returns `None` without waiting for it                |
| `list_runs()`              | returns the runs store's full header list                                         |
| `is_run_active()`          | returns the flow API's current run-active answer                                  |
| `run_log_write_failed()`   | returns whether the run-log writer's most recent write attempt failed             |

### STORY-107-AC-2

Given a gateway wired to a probe collaborator that records the thread it ran on,
when `manual_provider_probe()` is called from the graphical thread,
then it returns before the probe completes and the probe runs on a `TaskRunner` worker thread, not the
graphical thread.

### STORY-107-AC-3

Given a run is active and its cancellation token is observable,
when `stop_run(reason)` is called,
then the call returns promptly with the token marked cancelled and the worker was not terminated
mid-statement.

### STORY-107-AC-4

Given fake flow, run-registry, runs-store, results-store, run-log-reader, settings, and probe
collaborators that record every call,
when `make_progress_gateway(...)` is called,
then the factory returns a gateway and no method was invoked on any collaborator.

## Test plan

- STORY-107-AC-1 — unit, table-driven (one `@pytest.mark.parametrize` row per gateway method, total
  over all fourteen), colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_progress_gateway.py`,
  `test_each_method_performs_its_backend_interaction`.
- STORY-107-AC-2 — unit, same file, `test_manual_provider_probe_runs_on_a_worker_thread`.
- STORY-107-AC-3 — unit, same file, `test_stop_run_sets_the_token_and_returns_promptly`.
- STORY-107-AC-4 — unit, same file, `test_constructing_the_gateway_touches_no_collaborator`.
- The `RenameRunGateway` structural-satisfaction check is proven by STORY-104-AC-2, not duplicated
  here.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-107.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.
