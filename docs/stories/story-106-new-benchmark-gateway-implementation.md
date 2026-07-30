---
id: STORY-106
title: Implement the concrete New Benchmark gateway over settings, providers, readiness, and run start
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b2-newbenchmarkgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 02_New_Benchmark_Widget/implementation_structure.md#7-dependency-protocols
  - 07_Common_Dialogs/run_summary_dialog.md#8-preflight-re-check-on-open
modules:
  - ui/new_benchmark/
  - ui/common_dialogs/
  - adapters/ui_gateways/
acceptance_criteria:
  - STORY-106-AC-1
  - STORY-106-AC-2
  - STORY-106-AC-3
  - STORY-106-AC-4
edge_cases: []
depends_on: []
adrs:
  - ADR-0014
owner: coder
estimate: M
---

# STORY-106 — Implement the concrete New Benchmark gateway over settings, providers, readiness, and run start

## Goal

Make the New Benchmark panel able to actually start a benchmark. The panel remembers the mode the
user last chose and their advanced-option defaults, lists the providers available for the model
picker, checks readiness before the run is allowed to begin, and hands the assembled run request to
the pipeline — all through one object it holds, so the panel never touches a store or a service.

## In scope

- The concrete `NewBenchmarkGateway` implementation and its `make_new_benchmark_gateway(...)` factory
  on the adapters layer's public surface.
- The two settings methods backing the advanced-option defaults, `benchmark.last_mode`, and
  `embedding.hide_from_test_models`.
- The enabled-provider list for the model picker, the pre-run readiness snapshot, and the run-start
  command.
- `notify_error(message)`, the documented local addition that surfaces the Run Summary dialog's
  preflight-refusal toast.
- Confirming the same concrete class satisfies the Run Summary dialog's own gateway with no extra
  adapter class.

## Out of scope

- Wiring the gateway into `make_new_benchmark_widget` and `build_app` — owned by STORY-077.
- The panel's own behaviour, mode-conditional sections, and the Run Summary dialog flow — already
  delivered by STORY-054, STORY-055 and STORY-071; this story changes no user-interface code.
- `ModeVisibilityPolicy` — already satisfied structurally by `backend/mode_visibility/`'s own
  `visible_sections` free function; no adapter object is needed and none is written here.
- `RunValidator` — a backend service whose home is `backend/benchmark_pipeline/`, still unowned; see
  STORY-104's Notes.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b2-newbenchmarkgateway` — the five method
  signatures, verbatim, and the statement that this gateway wraps the settings layer
  (advanced-option defaults, `benchmark.last_mode`, `embedding.hide_from_test_models`),
  `ProviderRegistry` (provider and model selection lists), `ReadinessService` (pre-run readiness),
  and the run-start command.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the gateway is
  method-only, carries stdlib and `msgspec` types only, no `psygnal` and no Qt symbol, and is scoped
  to the methods its controller actually calls (SPEC-074).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract` — `start_run` is
  fast-synchronous: it hands the run to the dispatcher thread and returns promptly.
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — command construction and
  view-model conversion belong to the adapter; the controller never sees a backend Protocol.
- `02_New_Benchmark_Widget/implementation_structure.md#7-dependency-protocols` — the panel's
  dependency set, read as the capabilities the adapter wires behind this gateway.
- `07_Common_Dialogs/run_summary_dialog.md#8-preflight-re-check-on-open` — the actual authority for
  `notify_error`'s existence (a non-blocking toast naming the failure when the preflight re-check
  fails); the sixth method is a local addition per §7b's purpose-built-facade rule, not one of the
  five verbatim `08-E` §7b.2 methods.

## Design constraints

- **Where the code lands.** The implementation lands in `adapters/ui_gateways/`. ADR-0014 is
  accepted and its inventory row now exists, so `modules:` names that path directly.

## Acceptance criteria

### STORY-106-AC-1

Each `NewBenchmarkGateway` method performs exactly the stated backend interaction against its injected
collaborators and returns that collaborator's value unchanged:

| Gateway method            | Backend interaction                                                         |
| ------------------------- | --------------------------------------------------------------------------- |
| `get_setting(key)`        | reads `key` from the app-settings store; returns `None` when unset          |
| `set_setting(key, value)` | writes `key` through the settings service                                   |
| `provider_list()`         | returns the provider registry's enabled providers, in the order it supplied |
| `readiness_snapshot()`    | returns the readiness service's current snapshot without probing            |
| `start_run(request)`      | passes `request` to the flow API's start entry point and returns its run id |
| `notify_error(message)`   | passes `message` to the notification service unchanged                      |

### STORY-106-AC-2

Given a gateway wired to a flow API whose start entry point records that it was called and returns a
known run id,
when `start_run(request)` is called from the graphical thread,
then it returns that run id without waiting for the run to reach any status.

### STORY-106-AC-3

Given a message, including one containing a value the redaction module treats as a secret,
when `notify_error(message)` is called,
then the exact string is handed to the notification service unchanged, with no redaction applied.

`08_Cross_Cutting/08-E_interfaces_contracts.md` §22 (backed by
`10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1) restricts redaction to exactly two surfaces — the
`app.*` log pipeline and provider-SDK error-message wrapping at the adapter boundary — and states that
UI/display surfaces do not apply it (the earlier `redact_for_display` was deliberately retired). A
user-facing toast is a display surface, so `notify_error` must not call `redact`; doing so would risk
the denylist's catch-all patterns silently masking legitimate diagnostic text (e.g. a long hex model
digest) that the Run Summary dialog's preflight-refusal toast (`run_summary_dialog.md` §8,
EC-RS-2/3/4) needs to show verbatim. This corrects an initial draft of this criterion that required
redaction here, based on a stale "already-redacted" phrase in `NotificationService`'s own docstring
(`08-E` §20 itself never says this) — that docstring is corrected alongside this story.

### STORY-106-AC-4

Given fake settings, provider-registry, readiness, flow, and notification collaborators that record
every call,
when `make_new_benchmark_gateway(...)` is called,
then the factory returns a gateway and no method was invoked on any collaborator.

## Test plan

- STORY-106-AC-1 — unit, table-driven (one `@pytest.mark.parametrize` row per gateway method, total
  over all six), colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_new_benchmark_gateway.py`,
  `test_each_method_performs_its_backend_interaction`.
- STORY-106-AC-2 — unit, same file, `test_start_run_returns_the_run_id_without_waiting`.
- STORY-106-AC-3 — unit, same file, `test_notify_error_passes_the_message_through_unchanged`.
- STORY-106-AC-4 — unit, same file, `test_constructing_the_gateway_touches_no_collaborator`.
- The `RunSummaryGateway` structural-satisfaction check is proven by STORY-104-AC-2, not duplicated
  here.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-106.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.
