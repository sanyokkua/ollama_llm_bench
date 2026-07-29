---
id: STORY-105
title: Implement the concrete Main Window gateway over settings, readiness, and the run flow
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b1-mainwindowgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 01_Main_Window/implementation_structure.md#6-dependency-protocols
modules:
  - ui/main_window/
acceptance_criteria:
  - STORY-105-AC-1
  - STORY-105-AC-2
  - STORY-105-AC-3
edge_cases: []
depends_on: []
adrs: []
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

## Out of scope

- Wiring the gateway into `make_main_window` and `build_app` — owned by STORY-077.
- The shell's own behaviour (menu bar, status bar, close handler, geometry restore) — already
  delivered by STORY-053; this story changes no user-interface code.
- The deferred startup readiness tick — already delivered by STORY-053; this story only supplies the
  `reprobe()` that tick calls.
- The quit sequence's step-by-step ordering — owned by STORY-080; this story's `shutdown(timeout_ms)`
  delegates to the existing flow API and adds no ordering logic of its own.

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

- **Where the code lands, and why `modules:` says `ui/main_window/`.** The implementation lands in
  `adapters/ui_gateways/`, which the read-only module inventory does not yet list; ADR-0014 records
  the pending one-row correction. `modules:` names the user-interface module whose gateway Protocol
  this story satisfies, per the STORY-076/ADR-0010 precedent. Add `adapters/ui_gateways/` once the
  correction is ratified.
- **The nullable settings reads need `AppSettingsStore`, not only `SettingsService`.** Three of the
  four read methods return `str | None`, and `SettingsService` has no nullable getter — `get_str`
  guarantees a default floor and never returns `None`. So the `get_*` reads go through
  `AppSettingsStore.get_setting(key)` while the `set_*` writes go through `SettingsService.set(key, value)` so the settings-changed event still fires. `get_theme()` returns `str`, not `str | None`,
  so it resolves through `SettingsService.get_str`. This is a documented refinement of §7b.1's
  one-line "wraps `SettingsService`" summary, matching the existing precedent for documented local
  gateway additions in `ui/new_benchmark/protocols.py` and `ui/results/protocols.py`.
- `reprobe()` returns `None` and §7b.1 states the re-probe happens "on a worker thread", so it must
  not run `ReadinessService.probe_all()` on the calling thread — it submits the probe to the single
  `TaskRunner` and returns.
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
then `reprobe()` returns before the probe completes and the probe runs on a `TaskRunner` worker
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
- STORY-105-AC-2 — unit, same file, `test_reprobe_runs_the_probe_on_a_worker_thread`. Uses a fake
  readiness service that records `threading.get_ident()` inside `probe_all` and a real
  `TaskRunner`-backed submission.
- STORY-105-AC-3 — unit, same file, `test_constructing_the_gateway_touches_no_collaborator`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-105.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory change ADR-0014 describes has been ratified and applied, and
  `adapters/ui_gateways/` appears in this story's `modules:`.
