---
id: STORY-100
title: Issue a dedicated lightweight liveness probe when a provider is PROBING
status: done
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

| Breaker state before the row is routed | `run_provider_probe` behaviour                                                                                                                            |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CLOSED`                               | Returns immediately; zero `client.chat` calls; no `record_success`/`record_failure` invoked (a `state()` read still occurs, to make the routing decision) |
| `TRIPPED`                              | Returns immediately; zero `client.chat` calls; no `record_success`/`record_failure` invoked (a `state()` read still occurs, to make the routing decision) |
| `PROBING`                              | Issues exactly one lightweight liveness call against the row's `(provider, model)` target                                                                 |

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
  clock), same file, `test_probe_fires_per_row_not_per_group`. Extended in the review-fix wave
  by two production-wiring tests in the same file,
  `test_probe_wired_into_inference_phase_before_row` and
  `test_probe_wired_into_judge_phase_targets_judge_pair_not_row_model` — both drive the real
  `_internal.stability_phase.run_stability_phase` entry point (not a hand-rolled `before_row`
  closure) with a real breaker already `PROBING`, proving the two actual
  `before_row=_probe_before_row` wiring lines in `stability_phase.py` are present; the judge
  variant additionally proves the probe targets the run's fixed judge pair, never the row's own
  test model.
- STORY-100-AC-5 — regression, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_warmup.py` (existing suite,
  unedited assertions) plus a new parity test in the same file,
  `test_warmup_behaviour_unchanged_after_probe_extraction`.
- EC-PROV-3 — covered by STORY-100-AC-2/AC-3/AC-4 together: the outcome map and the
  never-leaves-PROBING invariant are what let a tripped provider actually recover mid-run.
- Architecture constraint (review-fix wave) —
  `tests/architecture/test_stability_dispatcher_thread_only.py`,
  `test_probe_touches_stability_services_only_from_dispatcher_thread`: AST-walks
  `lightweight_call.py` and `provider_probe.py` specifically and asserts no stability-service
  method call appears inside the callable argument passed to a `.submit(...)` call — the
  positive counterpart the original implementation's skip-list-only extension of
  `_DISPATCHER_THREAD_ONLY_FILE_NAMES` was missing.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-100.
- [x] EC-PROV-3 has a passing test.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The dispatcher-thread architecture scan's allowlist covers `lightweight_call.py` and
  `provider_probe.py`.
- [x] `test_warmup.py`'s existing assertions pass with no edits.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-100.
- [x] The module inventory is unchanged.

## Notes

- **08-G feature-flag finding (recorded as required, not re-derived).**
  `08_Cross_Cutting/08-G_feature_flags.md` line 60 is `benchmark.warmup_enabled`'s only
  definition, and it scopes the flag strictly to "pre-loads the model before the first timed
  inference so cold-load latency does not pollute measurements" — nothing in that entry, or
  anywhere else in the document, ties it to circuit-breaker recovery. `run_provider_probe` is
  therefore wired unconditionally in `stability_phase.py` (both `_run_inference_phase` and
  `_run_judge_phase`), never gated by `warmup_enabled`, consistent with
  `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`'s framing of PROBING recovery as breaker
  machinery, not a warmup optimisation a user can disable.
- **Deliberate divergence from `warmup.py:95-96`.** `run_provider_probe` does not call
  `adaptive_timeout.is_excluded(...)` before issuing its call, unlike `run_model_warmup`'s
  guard. An excluded model is still a valid liveness target for the breaker's own recovery —
  per-role adaptive-timeout exclusion and provider-level breaker health are independent
  concerns, and gating the probe on the former would leave a provider stuck `PROBING` whenever
  its only recently-used model happened to be excluded.
- **`WARMUP_PROMPT`/`WARMUP_MAX_OUTPUT_TOKENS` re-export was not a dead re-export.** Grepped
  every importer before moving the constants: only `test_warmup.py` imports them (from
  `warmup.py`). Since that import site is required to keep working unedited (this story's own
  constraint), the re-export in `warmup.py` is load-bearing, not speculative — kept as
  `from ..._internal.lightweight_call import WARMUP_MAX_OUTPUT_TOKENS, WARMUP_PROMPT` plus
  `warmup.py`'s own `__all__`.
- **Shared call-shape parameterisation.** `lightweight_call.issue_lightweight_call` takes
  `attempts` and `budget_attempt_offset` rather than hard-coding either caller's ladder shape.
  `run_model_warmup` passes `attempts=1 + retry_count, budget_attempt_offset=0` (byte-identical
  to its pre-refactor loop). `run_provider_probe` passes `attempts=1, budget_attempt_offset=retry_count`, so `with_retry`'s own single-attempt policy
  (`policy.attempts=1`) enforces ADR-0013's one-attempt shape by construction — no bespoke
  bypass of `with_retry` was needed — while the one attempt still draws the same top-of-ladder
  budget a real task's final retry would receive.
- **Two architecture-scan allowlists needed updating, both found before running `just arch-test` the first time cost a red result:**
  `tests/architecture/test_stability_dispatcher_thread_only.py`'s
  `_DISPATCHER_THREAD_ONLY_FILE_NAMES` (breaker/adaptive-timeout method calls) and
  `tests/architecture/test_benchmark_pipeline_module.py`'s `_LIGHTWEIGHT_CALL_FILE_NAME`
  addition (the `Future.result()` block-on-futures scan) — both now cover `provider_probe.py`
  and `lightweight_call.py`. This is the STORY-075 lesson the task brief flagged in advance.
- **Task 4 (STORY-101) follow-up, left untouched by design.** The breaker's real-task probe
  admission (`should_skip`'s PROBING branch, `probe_slot_claimed` bookkeeping,
  `stability_dispatch.py`'s now-superfluous-but-still-correct PROBING conditional) is
  deliberately still in place after this story — this story only adds the new resolver so the
  tree is never left without one; removing the old admission path is STORY-101's job.

### Review-fix wave (2026-07-28)

- **Thread-affinity check was structured backwards.** The original allowlist extension to
  `_DISPATCHER_THREAD_ONLY_FILE_NAMES` in
  `tests/architecture/test_stability_dispatcher_thread_only.py` is a *skip list* for the
  existing "which modules may call a stability-service method at all" scan — adding
  `lightweight_call.py`/`provider_probe.py` to it correctly let those two modules pass that
  scan, but also meant nothing checked *where inside* those files the calls happen. Added the
  missing positive counterpart,
  `test_probe_touches_stability_services_only_from_dispatcher_thread`: it AST-walks both files
  for any stability-service method call inside the callable argument passed to a
  `.submit(...)` call — the actual dispatcher/worker boundary. Verified load-bearing by
  temporarily moving a `next_budget` call into `lightweight_call.py`'s submitted
  `lambda: client.chat(...)` and confirming the new test failed, then reverting. The original
  skip-list entries were kept — they remain necessary for the existing scan and are not
  subsumed by the new positive check, which tests a different property.
- **Production wiring had no test.** `_internal/stability_phase.py`'s two
  `before_row=_probe_before_row` lines (`_run_inference_phase`, `_run_judge_phase`) are the
  probe's only real entry point and were unproven — `test_probe_fires_per_row_not_per_group`
  drives its own hand-rolled `before_row` closure, never the real wiring. Added
  `test_probe_wired_into_inference_phase_before_row` and
  `test_probe_wired_into_judge_phase_targets_judge_pair_not_row_model`, both driving the real
  `run_stability_phase` entry point with a real breaker already `PROBING`. Verified
  load-bearing by temporarily setting each `before_row=` line to `None` and confirming the
  matching test failed, then reverting.
- **`warmup.py` dropped from the `Future.result()` exclusion tuple.** It no longer contains a
  `.result()` call since this story's own extraction into `lightweight_call.py`; keeping it
  allowlisted "defensively" would silently permit a future regression reintroducing one.
  Removed; `just arch-test` stays green, confirming the file is genuinely clean.
- **Duplicated test doubles consolidated.** `RecordingChatClient` and `InlineCallableRunner`
  (the byte-identical `_RecordingChatClient`/`_InlineWarmupRunner`/`_InlineStabilityRunner`/
  `_InlineProbeRunner`/`_InlineRowRunner` doubles duplicated across `test_warmup.py` and
  `test_provider_probe.py`) now live once in
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/conftest.py`; both files import them
  and `cast(...)` to the narrower `TaskRunner[T]` each call site needs, mirroring the pattern
  `_internal/stability_phase.py` itself already uses for `collaborators.task_runner`.
- **`provider_probe.py`'s invariant docstring narrowed.** It previously claimed "no exit path
  other than `TaskCancelledError` leaves the provider `PROBING`", but the guard is
  `except AppError`. Reworded to state the invariant over the `AppError` hierarchy specifically,
  and to note that a non-`AppError` exception escapes `_dispatch_run`
  (`_internal/lifecycle.py`) uncaught, failing the whole run loudly via the dispatcher thread's
  own exception hook rather than silently wedging one provider `PROBING`. No `finally` was
  added — inventing a breaker outcome for an unknown exception is policy ADR-0013 does not
  authorize.
- **"Read-only `next_budget`" claim corrected in three places** (`provider_probe.py`,
  `lightweight_call.py`, and `warmup.py` — the last touched by this review wave too, so
  corrected under the project's "fix what you touch" rule). `AdaptiveTimeoutService.next_budget`
  calls `_get_or_create_bucket(...)` and assigns `bucket.last_queried_budget_ms` — it is not a
  pure read. The three docstrings now state this precisely: no *outcome-reporting* method
  (`record_success`/`record_timeout`) is ever called by a warmup or a probe, which is the actual
  invariant those callers rely on.
- **`_SINGLE_ATTEMPT` given `Final`**, matching `lightweight_call.py`'s sibling constants
  (`coding-style.md`'s module-level-constant rule).
- **AC-1's table reworded.** "no breaker method invoked" was imprecise — `run_provider_probe`
  necessarily calls `circuit_breaker.state(...)` even in the `CLOSED`/`TRIPPED` cases, to decide
  whether to run at all. Reworded to "no `record_success`/`record_failure` invoked (a `state()`
  read still occurs...)" so a later reader does not mistake the `state()` read for a violation.
- **Recorded observation, not acted on (out of scope for this story).** `run_provider_probe`
  hard-codes the INFERENCE adaptive-timeout role
  (`adaptive_timeout.next_budget(..., AdaptiveTimeoutRole.INFERENCE, ...)` via
  `issue_lightweight_call`), so a judge-phase probe sizes itself from the inference ladder and
  materializes an `(judge_provider, judge_model, INFERENCE)` adaptive-timeout bucket that would
  otherwise not exist. ADR-0013 specifies the INFERENCE role for the probe, so changing this
  would contradict an accepted decision record — not something this review-fix wave may do.
  Impact appears bounded: the judge phase's own real attempts re-query their own
  `role=JUDGE` budget immediately afterward, so the stray INFERENCE bucket is otherwise inert.
  Left for a future story if the accepted decision is ever revisited.
