---
id: STORY-100
title: Issue a dedicated lightweight liveness probe when a provider is PROBING
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-F_spec_issues_log.md#dd-71--circuit-breaker-probing-uses-a-lightweight-liveness-probe-not-a-full-task-2026-06-06
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#66-probe-behaviour
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-3
modules:
  - backend/benchmark_pipeline/
acceptance_criteria:
  - STORY-100-AC-1
  - STORY-100-AC-2
  - STORY-100-AC-3
  - STORY-100-AC-4
  - STORY-100-AC-5
edge_cases:
  - EC-PROV-3
depends_on: []
adrs:
  - ADR-0013
owner: coder
estimate: M
---

# STORY-100 — Issue a dedicated lightweight liveness probe when a provider is PROBING

## Goal

Give a `PROBING` provider a dedicated, bounded-cost way to prove it is alive again, instead of
waiting for the next real benchmark task to happen to land on it. Per DD-71
(`08_Cross_Cutting/08-F_spec_issues_log.md`), once a tripped provider's cooldown elapses, the
pipeline issues one short, single-attempt, warmup-style call — not a full task on the
retry-laddered inference path — and that call's outcome always decides whether the provider
returns to service or the breaker re-trips. This closes the liveness gap a real-task probe has:
a still-down provider is now confirmed or re-tripped in one budget's worth of wall time, not the
minutes a `(1+retry_count)×`-escalating real task could cost, and the check happens on every row
against a `PROBING` provider — including the common single-`(provider, model)`-group case where
no later group boundary would otherwise ever occur to notice the cooldown had elapsed.

## In scope

- `backend/benchmark_pipeline/_internal/lightweight_call.py` (new): the shared call shape —
  build the `ChatRequest` from the existing `WARMUP_PROMPT`/`WARMUP_MAX_OUTPUT_TOKENS`
  constants (moved here, re-exported from `warmup.py` so existing imports keep working),
  resolve the client, submit the blocking `client.chat` to the `TaskRunner`, wrap in
  `with_retry` with an `attempts`-derived policy. It raises; it never classifies an outcome and
  performs no breaker or adaptive-timeout writes itself.
- `backend/benchmark_pipeline/_internal/provider_probe.py` (new): `run_provider_probe(...)`,
  the dedicated liveness probe described in ADR-0013. Returns immediately unless the breaker
  reports `CircuitState.PROBING`; otherwise calls the `lightweight_call.py` helper with
  `attempts=1` at the first-attempt adaptive budget
  (`adaptive_timeout.next_budget(provider_id, model_name, AdaptiveTimeoutRole.INFERENCE, attempt_index=1 + retry_count)`)
  and maps every reachable outcome to exactly one breaker call per ADR-0013's outcome map. Does
  **not** consult `adaptive_timeout.is_excluded` — an excluded model is still a valid liveness
  target, a deliberate divergence from `warmup.py`'s existing exclusion check.
- `backend/benchmark_pipeline/_internal/dispatcher.py`: a new `before_row` hook on
  `run_phase_with_stability`, invoked in the per-row loop after `token.raise_if_cancelled()` and
  after the row's stability target is resolved, so the hook fires once per row rather than once
  per `(provider, model)` group.
- `backend/benchmark_pipeline/_internal/stability_phase.py`: wire the `before_row` hook to
  `run_provider_probe` for both `_run_inference_phase` and `_run_judge_phase`, so the judge
  provider is probed too.
- `backend/benchmark_pipeline/_internal/warmup.py`: refactored to call the new
  `lightweight_call.py` helper with `attempts=1 + retry_count`, keeping its existing three-way
  `except` outcome handling verbatim. Behaviour is unchanged, byte-identical to before the
  refactor.
- Extending the dispatcher-thread architecture scan's allowlist to cover the two new modules.

## Out of scope

- Deleting the breaker's real-task probe admission (`should_skip`'s `probe_slot_claimed`
  bookkeeping, `stability_dispatch.py`'s PROBING conditional) — owned by STORY-101, which
  depends on this story landing first so the tree is never left with a `PROBING` state that has
  no resolver at all.
- The parametrized zero-breaker-failure conformance test across all three breaker states, and
  the `CHANGELOG.md` entry — owned by STORY-102.
- Correcting `08_CIRCUIT_BREAKER.md`'s stale real-task-probe prose — owned by STORY-103.
- A user-triggered manual probe surface (`ui/progress/protocols.py`'s already-declared
  `manual_provider_probe()`) — `run_provider_probe` is a natural future backend for it, but
  wiring that surface is not part of this story.

## Spec inputs

- `08_Cross_Cutting/08-F_spec_issues_log.md#dd-71--circuit-breaker-probing-uses-a-lightweight-liveness-probe-not-a-full-task-2026-06-06` —
  the binding product-owner decision this story implements: the probe is a lightweight
  warmup-style call, not a full task.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing` —
  what "PROBING" means operationally and when the pipeline is expected to act on it; per
  ADR-0013's precedence ruling, DD-71 governs the parts of this clause's prose that still
  describe a real-task probe.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#66-probe-behaviour` — the pre-DD-71
  walkthrough of the real-task probe; ADR-0013 supersedes it in place with the dedicated-probe
  design and outcome map this story implements.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold` —
  the "any response, including a 4xx, proves the provider is alive" rule this story's outcome
  map restates for the probe call site, and the warmup call's existing three-way outcome
  handling this story must not disturb.
- `08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-3` — a provider tripping the breaker mid-run; this
  story is what lets such a provider actually recover instead of staying permanently skipped.

## Design constraints

- `backend/benchmark_pipeline/` is Qt-free and asyncio-free. The breaker and adaptive-timeout
  services are touched only from the dispatcher thread; `run_provider_probe` follows
  `warmup.py`'s existing pattern exactly — all service reads/writes happen in the probe's own
  body on the dispatcher thread, and only the blocking `client.chat` call is submitted to the
  `TaskRunner`.
- The probe makes **exactly one** network attempt — no `with_retry` ladder, no backoff, no
  second attempt on failure — per ADR-0013's one-attempt-shape ruling. `retry_count` selects
  where on the adaptive-timeout ladder the single budget is drawn from; it does not drive a
  retry loop.
- No exit path from `run_provider_probe` other than `TaskCancelledError` may leave the provider
  `PROBING`. A bare `except AppError: return` is forbidden in this module.
- `warmup.py` and `provider_probe.py` share the `lightweight_call.py` call shape but never merge
  into one function with a mode flag: warmup must never call `record_success` (a good warmup on
  model B must not reset a failure run spanning models A and B), while the probe must call it
  (that is how the breaker closes). `test_warmup.py`'s existing assertions must pass unedited.
- The `before_row` hook fires per row, not per `(provider, model)` group — hanging it off the
  existing per-group warmup hook would leave the single-group, single-model case (the most
  common repro of the underlying bug) permanently unfixed, since no later group boundary would
  ever occur to re-invoke it.
- No new public `api.py` symbol and no `ProviderCircuitBreaker` Protocol method is added or
  resignatured — the probe is wired entirely behind the existing pipeline internals.

## Acceptance criteria

### STORY-100-AC-1

Before routing a row, `run_provider_probe` behaves per the breaker's current state for that
row's provider:

| Breaker state before the row is routed | `run_provider_probe` behaviour                                                            |
| -------------------------------------- | ----------------------------------------------------------------------------------------- |
| `CLOSED`                               | Returns immediately; zero `client.chat` calls; no breaker method invoked                  |
| `TRIPPED`                              | Returns immediately; zero `client.chat` calls; no breaker method invoked                  |
| `PROBING`                              | Issues exactly one lightweight liveness call against the row's `(provider, model)` target |

### STORY-100-AC-2

When `run_provider_probe` issues its one liveness call while the provider is `PROBING`, the
outcome maps totally onto exactly one breaker call:

| Outcome of the single attempt                                                                       | Breaker call               |
| --------------------------------------------------------------------------------------------------- | -------------------------- |
| A `ChatResponse` is returned (any completion, including a model-side error the LLM itself produced) | `record_success`           |
| `HttpTimeoutError` or `HttpConnectionError`                                                         | `record_failure`           |
| Any other `AppError` originating in a provider response (401, 404, 400, 422, 429, 5xx, etc.)        | `record_success`           |
| `ConfigurationError` or `MissingEnvVarError` raised by `get_client()` before any network call       | `record_failure`           |
| `TaskCancelledError`                                                                                | Re-raised; no breaker call |

### STORY-100-AC-3

For every reachable outcome of the single probe attempt other than `TaskCancelledError`,
`run_provider_probe` calls exactly one of `record_success` or `record_failure` before returning,
so the breaker is never left in `PROBING` once the call has returned; only `TaskCancelledError`
is re-raised with no breaker call made.

### STORY-100-AC-4

Given a single `(provider, model)` group with three or more rows, where that group's provider
trips on the first row, when the cooldown elapses before the second row is dispatched, then
`run_provider_probe` fires again before that second row is routed and before every row after it
until the breaker resolves — it is invoked from the dispatcher's per-row hook, not only once
from a per-group model-switch hook that a single-group run would never revisit.

### STORY-100-AC-5

Given `run_model_warmup`'s existing three-way outcome handling (any response is neutral for the
breaker, a ladder-exhausted timeout or connection/transport error calls `record_failure`,
`record_success` is never called), when `warmup.py` is refactored to call the new
`lightweight_call.py` helper, then its observable behaviour is unchanged — it still never calls
`circuit_breaker.record_success`, and the existing `test_warmup.py` suite passes with no edits
to its assertions.

## Test plan

- STORY-100-AC-1 — unit (table-driven over `{CLOSED, TRIPPED, PROBING}`), colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_provider_probe.py`,
  `test_probe_is_skipped_unless_probing`.
- STORY-100-AC-2 — unit (table-driven over the outcome map), same file,
  `test_probe_outcome_maps_to_close_or_retrip`.
- STORY-100-AC-3 — property, driving the real `make_circuit_breaker` with a `FakeClock`,
  parametrized over the full reachable outcome set (`ChatResponse`, `ProviderAuthError`,
  `ModelNotAvailableError`, `ProviderBadRequestError`, `ProviderContextLengthError`,
  `ProviderServerError`, `ProviderRateLimitedError`, `ConfigurationError`,
  `MissingEnvVarError`, `HttpTimeoutError`, `HttpConnectionError`), same file,
  `test_probe_never_leaves_breaker_probing`; plus `test_probe_cancellation_reports_no_outcome`
  for the `TaskCancelledError` branch.
- STORY-100-AC-4 — unit/integration (one group, three or more rows, real breaker, advanced fake
  clock), same file, `test_probe_fires_per_row_not_per_group`.
- STORY-100-AC-5 — regression, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_warmup.py` (existing suite,
  unedited assertions) plus a new parity test in the same file,
  `test_warmup_behaviour_unchanged_after_probe_extraction`.
- EC-PROV-3 — covered by STORY-100-AC-2/AC-3/AC-4 together: the outcome map and the
  never-leaves-PROBING invariant are what let a tripped provider actually recover mid-run.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-100.
- [ ] EC-PROV-3 has a passing test.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The dispatcher-thread architecture scan's allowlist covers `lightweight_call.py` and
  `provider_probe.py`.
- [ ] `test_warmup.py`'s existing assertions pass with no edits.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-100.
- [ ] The module inventory is unchanged.
