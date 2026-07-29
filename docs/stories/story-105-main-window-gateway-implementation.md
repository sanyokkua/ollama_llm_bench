---
id: STORY-105
title: Implement the concrete Main Window gateway over settings, readiness, and the run flow
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b1-mainwindowgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#12-readiness-service
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4a-the-dispatcher-thread-dd-38
  - 01_Main_Window/implementation_structure.md#6-dependency-protocols
modules:
  - ui/main_window/
  - adapters/ui_gateways/
acceptance_criteria:
  - STORY-105-AC-1
  - STORY-105-AC-2
  - STORY-105-AC-3
edge_cases: []
depends_on: []
adrs:
  - ADR-0014
owner: coder
estimate: M
---

# STORY-105 — Implement the concrete Main Window gateway over settings, readiness, and the run flow

## Goal

Give the application shell a real backend connection. The Main Window remembers its window size,
splitter position, active workspace and theme across restarts; its status-bar health dot shows live
provider readiness and re-probes when clicked; and quitting while a benchmark is running asks the
user and then stops the run gracefully. All of that reaches the backend through one object the shell
holds, so the shell itself never touches a store or a service.

## In scope

- The concrete `MainWindowGateway` implementation and its `make_main_window_gateway(...)` factory on
  the adapters layer's public surface.
- The eight window-shell persistence reads and writes (`ui.window_geometry`, `ui.splitter_sizes`,
  `ui.active_workspace`, `ui.theme`).
- The two readiness methods: the immediate snapshot read for the status-bar dot, and the re-probe
  the dot's click triggers.
- The two quit-decision methods: the run-active query and the bounded graceful shutdown.
- One new `import-linter` contract forbidding any `adapters/*` module from importing `ui/*`. Both
  ADR-0014 and `adapters/file_system_actions/protocols.py` justified duplicating a UI-owned Protocol
  by citing this rule while nothing enforced it; this story closes that gap.

## Out of scope

- Wiring the gateway into `make_main_window` and `build_app` — owned by STORY-077.
- The shell's own behaviour (menu bar, status bar, close handler, geometry restore) — already
  delivered by STORY-053; this story changes no user-interface code.
- The deferred startup readiness tick — already delivered by STORY-053; this story only supplies the
  `reprobe()` that tick calls.
- The quit sequence's step-by-step ordering — owned by STORY-080; this story's `shutdown(timeout_ms)`
  delegates to the existing flow API and adds no ordering logic of its own.
- **Deferring a health-dot click made during a run (EC-RUN-13) — no story owns this yet.** Found by
  the conformance review of this story, and deliberately left unfixed here because the fix is a
  backend change this story's scope does not reach. `reprobe()` hands the probe to the
  pipeline-dispatcher thread, which is a single FIFO queue that a running benchmark occupies for the
  whole run. So a click during a run does not reach `ReadinessService.probe_all()`'s existing
  gate-refusal path (`_acquire_gate_with_one_deferral`); it simply waits in the queue, shows the user
  nothing, and then fires once the run ends. `08_Cross_Cutting/08-I_edge_cases.md` EC-RUN-13 requires
  the opposite — "deferred, **not queued** for the remainder of the run", with the dot showing
  `Checking deferred — run in progress` immediately. Fixing it needs a synchronous gate check before
  anything is enqueued plus a public way for the readiness service to report a deferral without
  running a batch, neither of which exists today. This is a genuine conflict between
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §4a (the batch must orchestrate on the
  dispatcher) and EC-RUN-13 (a mid-run click must report immediately), so it needs an ADR, not just
  a patch.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b1-mainwindowgateway` — the twelve method
  signatures, verbatim, and the statement that this gateway wraps `SettingsService` (window-shell
  persistence keys), `ReadinessService` (status-bar health dot), and `BenchmarkFlowApi` (the quit
  decision and graceful shutdown).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the gateway is
  method-only, carries stdlib and `msgspec` types only, no `psygnal` and no Qt symbol, and is a
  purpose-built facade rather than a store re-export (SPEC-074).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract` — a *fast-synchronous*
  method may be called from the graphical thread; a *blocking* method runs only on a `TaskRunner`
  worker thread; the graphical thread never blocks.
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — the adapter holds the
  backend Protocols and decides how to satisfy each gateway method; the controller never sees a
  Protocol.
- `01_Main_Window/implementation_structure.md#6-dependency-protocols` — the shell's dependency set,
  read as the capabilities the adapter wires behind this gateway.

## Design constraints

- **Where the code lands.** The implementation lands in `adapters/ui_gateways/`. ADR-0014 is
  accepted and its inventory row now exists, so `modules:` names that path directly.
- **The nullable settings reads need `AppSettingsStore`, not only `SettingsService`.** Three of the
  four read methods return `str | None`, and `SettingsService` has no nullable getter — `get_str`
  guarantees a default floor and never returns `None`. So the `get_*` reads go through
  `AppSettingsStore.get_setting(key)` while the `set_*` writes go through `SettingsService.set(key, value)` so the settings-changed event still fires. `get_theme()` returns `str`, not `str | None`,
  so it resolves through `SettingsService.get_str`. This is a documented refinement of §7b.1's
  one-line "wraps `SettingsService`" summary, matching the existing precedent for documented local
  gateway additions in `ui/new_benchmark/protocols.py` and `ui/results/protocols.py`.
- **`reprobe()` hands the probe to the pipeline-dispatcher thread, not to the worker pool.**
  `reprobe()` returns `None`, so it must not run `ReadinessService.probe_all()` on the calling
  thread. But it must not submit it to the `TaskRunner` pool either: `probe_all()` itself fans one
  probe per provider out to that same pool and then blocks waiting for all of them, so running it
  *on* a pool thread is a pool thread waiting on pool threads.
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §4a forbids exactly that and names the
  readiness `probe_all` batch as one of only two operations that must be orchestrated on the
  dispatcher thread; `08_Cross_Cutting/08-E_interfaces_contracts.md` §12 agrees. The harm is real
  at both ends: with the pool fixed at four threads, a probe batch of four or more providers plus
  the embedding unit exhausts the pool while one worker is already consumed by the orchestrator, so
  it starves; short of that, each provider's timeout clock starts when its probe is *queued* rather
  than when it *starts*, so healthy providers get reported unreachable. On precedence: §7b.1's "on a
  worker thread" is a parenthetical inside a method docstring, while §12 is the clause that actually
  specifies this method's threading — the specific clause governs, and `08-E` §4 independently names
  the concurrency standard authoritative. No appeal to D-R-01 is needed. So `reprobe()` submits to
  the `RunDispatcher` and returns.
- `readiness_snapshot()` and `is_run_active()` are fast-synchronous reads callable from the graphical
  thread; neither may probe or block.
- Constructing the gateway must be side-effect free — no backend read, no probe, no network call —
  because `build_app` constructs it and STORY-077-AC-2 requires the whole graph to be built with no
  network call.
- The gateway holds no Qt symbol on its public surface and returns only `backend/domain` DTOs and
  built-in types.
- `adapters/ui_gateways/` must not import `ui` (`import-linter`); the Protocol is satisfied
  structurally.

## Acceptance criteria

### STORY-105-AC-1

Each `MainWindowGateway` method performs exactly the stated backend interaction against its injected
collaborators and returns that collaborator's value unchanged:

| Gateway method                | Backend interaction                                                                |
| ----------------------------- | ---------------------------------------------------------------------------------- |
| `get_window_geometry()`       | reads `ui.window_geometry` from the app-settings store; returns `None` when unset  |
| `set_window_geometry(value)`  | writes `ui.window_geometry` through the settings service                           |
| `get_splitter_sizes()`        | reads `ui.splitter_sizes` from the app-settings store; returns `None` when unset   |
| `set_splitter_sizes(value)`   | writes `ui.splitter_sizes` through the settings service                            |
| `get_active_workspace()`      | reads `ui.active_workspace` from the app-settings store; returns `None` when unset |
| `set_active_workspace(value)` | writes `ui.active_workspace` through the settings service                          |
| `get_theme()`                 | resolves `ui.theme` through the settings service, returning the effective value    |
| `set_theme(value)`            | writes `ui.theme` through the settings service                                     |
| `readiness_snapshot()`        | returns the readiness service's current snapshot without probing                   |
| `reprobe()`                   | submits a readiness probe and returns `None` without waiting for it                |
| `is_run_active()`             | returns the flow API's current run-active answer                                   |
| `shutdown(timeout_ms)`        | calls the flow API's bounded graceful shutdown with the given timeout              |

### STORY-105-AC-2

Given a gateway wired to a readiness service that records the thread it was probed on,
when `reprobe()` is called from the graphical thread,
then `reprobe()` returns before the probe completes and the probe runs on the pipeline-dispatcher
thread, not the graphical thread.

### STORY-105-AC-3

Given fake settings, readiness, and flow collaborators that record every call,
when `make_main_window_gateway(...)` is called,
then the factory returns a gateway and no method was invoked on any of the three collaborators.

## Test plan

- STORY-105-AC-1 — unit, table-driven (one `@pytest.mark.parametrize` row per gateway method,
  total over all twelve), colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_main_window_gateway.py`,
  `test_each_method_performs_its_backend_interaction`.
- STORY-105-AC-2 — unit, same file, `test_reprobe_runs_the_probe_on_the_dispatcher_thread`. Uses a
  fake readiness service that records `threading.get_ident()` inside `probe_all` and then blocks,
  driven through a real `make_run_dispatcher()`-backed submission.
- STORY-105-AC-3 — unit, same file, `test_constructing_the_gateway_touches_no_collaborator`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-105.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.
