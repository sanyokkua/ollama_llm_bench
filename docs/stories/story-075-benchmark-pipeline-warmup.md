---
id: STORY-075
title: Pre-load each test model with an adaptive-budget warmup at the model-switch boundary and feed its liveness outcome to the circuit breaker
status: in-progress
spec_clauses:
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-1a
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#69-interaction-with-adaptive-timeout
  - 11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#4-preconditions
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#1-purpose
  - 08_Cross_Cutting/08-G_feature_flags.md#3-benchmark--benchmark-behaviour
modules:
  - backend/benchmark_pipeline/
acceptance_criteria:
  - STORY-075-AC-1
  - STORY-075-AC-2
  - STORY-075-AC-3
  - STORY-075-AC-4
  - STORY-075-AC-5
  - STORY-075-AC-6
edge_cases:
  - EC-PROV-1a
depends_on:
  - STORY-029
  - STORY-030
  - STORY-023
  - STORY-022
owner: coder
estimate: M
---

# STORY-075 — Pre-load each test model with an adaptive-budget warmup at the model-switch boundary and feed its liveness outcome to the circuit breaker

## Goal

Give the benchmark pipeline the model warmup step the specification mandates but the code does
not yet have. When `benchmark.warmup_enabled` is on (the default), the pipeline issues one
lightweight inference against each `(provider, model)` test target the first time it reaches that
target, before the first timed task inference of the group. The warmup pre-loads the model so a
cold-load delay does not pollute the first task's timing measurement, and it turns an
advertised-but-unloadable model into an early, attributable signal: a warmup that never responds
(its adaptive-timeout ladder exhausts, or it fails with a connection/transport error) is reported
to the provider circuit breaker as a provider failure, while any actual response — including a
model-side `4xx`/`404` — proves the provider is alive and is neutral. The per-task inference
remains the authoritative outcome; warmup adds no result rows and never marks a model excluded.

## In scope

- A warmup step in `backend/benchmark_pipeline/` that fires once per `(provider, model)` test
  target at its model-switch boundary — the transition into that target's first eligible
  `Phase.INFERENCE` row — when the run's frozen `benchmark.warmup_enabled` snapshot value is
  `true`.
- Sizing the warmup call by the role=INFERENCE adaptive-timeout ladder for that
  `(provider, model)` (DD-64): the same `min → max` escalation the target's normal inference uses,
  not a separate fixed warmup deadline.
- Classifying the warmup outcome and driving the circuit breaker from it: a response (success or a
  model-side error) is neutral; a ladder-exhausted no-response timeout or a connection/transport
  error is `record_failure(provider_id)`; a user cancellation reports neither.
- Keeping warmup out of the adaptive-timeout model-exclusion counter — a model is excluded only by
  per-task inference timeouts, never by a warmup (`07_ADAPTIVE_TIMEOUT.md` §4).
- Dispatching the warmup as an ordinary serial inference-class unit through the run's `TaskRunner`
  under the already-held `BENCHMARK_RUN` gate, honouring the run's `CancellationToken` at the
  model-switch safe checkpoint.

## Out of scope

- The circuit breaker's own state machine (trip threshold, cooldown, `TRIPPED → PROBING` lazy
  transition) — already delivered by STORY-023; this story only calls `record_failure` on it.
- The circuit breaker's post-cooldown `PROBING` liveness probe (DD-71) — that is the breaker
  admitting one real task; it is a distinct call site from the model-switch warmup and is owned by
  STORY-023/STORY-030, not this story.
- Adaptive-timeout budgeting, escalation, and model exclusion internals — already delivered by
  STORY-022; this story only reads the role=INFERENCE budget for the warmup call.
- The warmup-off first-use load-failure path of EC-PROV-1a (the first task's own inference produces
  the `FAILED_*` row with no warmup involved) — already tested by STORY-074; this story adds the
  complementary warmup-on facet.
- The `New Benchmark` advanced-options and Settings General-tab `benchmark.warmup_enabled` controls
  — those already exist; this story consumes the frozen snapshot value only, no UI change.

## Spec inputs

- `08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-1a` — with warmup on, the warmup at the model-switch
  boundary hits an advertised-but-unloadable model first: a warmup timeout is recorded as a
  provider failure feeding the breaker, and a warmup non-timeout error follows the
  `FAILED_PROVIDER` / `FAILED_INFERENCE` classification (transport error = provider failure;
  model-side error = provider answered, neutral). `READY` never meant loadable.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold` —
  the exact warmup-outcome rules: any response (incl. `4xx`) is provider-liveness and neutral for
  the breaker; a warmup that exhausts its adaptive ladder without responding, or fails with a
  connection/transport error, is `record_failure(provider_id)`; the model, if merely slow, is left
  to adaptive-timeout exclusion, never blamed on the provider.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#69-interaction-with-adaptive-timeout` — the
  breaker's timeout-based signal comes exclusively from the model-switch warmup (per-task
  `FAILED_TIMEOUT` never trips the breaker); a slow-but-responding model, even a slow cold load,
  warms up alive.
- `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#4-preconditions` — DD-64: the model-switch
  warmup is sized by the model's role=INFERENCE budget (escalation headroom, finite max), but its
  outcome feeds the circuit breaker, not this service's model-exclusion counter; a model is
  excluded only by per-task inference timeouts, never by a warmup.
- `11_Services_and_Algorithms/09_READINESS_PROBE.md#1-purpose` — `READY` means reachable +
  advertised, not loadable; the pipeline's warmup is where an advertised-but-unloadable model fails
  fast at run start, so a warmup timeout being a provider failure is the mechanism SPEC-048 relies
  on.
- `08_Cross_Cutting/08-G_feature_flags.md#3-benchmark--benchmark-behaviour` — `benchmark.warmup_enabled`
  (bool, default `true`, per-run-overridable, frozen into the run snapshot); consumed by the
  Benchmark Pipeline to pre-load the model before the first timed inference so cold-load latency
  does not pollute measurements.

## Design constraints

- `backend/benchmark_pipeline/` is Qt-free and asyncio-free; no PySide6 import (architecture-test
  enforced).
- The warmup runs on the dedicated `pipeline-dispatcher` thread's serial loop: it is submitted as
  one blocking inference-class unit through the run's `TaskRunner`, and the dispatcher blocks on
  its `Future` — never more than one inference in flight app-wide, under the `BENCHMARK_RUN` gate
  already held for the whole run (no second `try_acquire`).
- The circuit breaker and the adaptive-timeout service are touched **only** on the dispatcher
  thread; the warmup's `record_failure` and its budget read happen there, never inside the
  worker-submitted warmup callable.
- Warmup never calls `record_success` on the breaker — only a `COMPLETED` real task resets the
  provider's consecutive-failure counter; a warmup response is neutral, not a success.
- Warmup writes no `BenchmarkResult` row and never mutates result state; its only side effects are
  the pre-load and, on a no-response failure, the `record_failure(provider_id)` call.
- The run reads `benchmark.warmup_enabled` from its frozen settings snapshot, never from live
  settings (Settings is unreachable during a run, DD-03).
- Provider/transport-vs-model error classification reuses the existing taxonomy translation the
  provider adapters already perform (`FAILED_PROVIDER`-class = provider-attributable;
  `FAILED_INFERENCE`-class = model answered) — this story adds no new error leaf.

## Acceptance criteria

### STORY-075-AC-1

Given a run whose frozen `benchmark.warmup_enabled` is `true`, when the pipeline reaches the
model-switch boundary for a `(provider, model)` test target (its first eligible inference row),
then exactly one warmup inference is issued against that `(provider, model)` before the group's
first timed task inference runs.

### STORY-075-AC-2

Given a run whose frozen `benchmark.warmup_enabled` is `false`, when the pipeline reaches a
model-switch boundary, then no warmup inference is issued and the group's first task inference runs
directly.

### STORY-075-AC-3

The warmup outcome drives the circuit breaker per its provider-liveness meaning, for every warmup
outcome:

| Warmup outcome                                                 | Circuit-breaker action                             | Adaptive-timeout model-exclusion action |
| -------------------------------------------------------------- | -------------------------------------------------- | --------------------------------------- |
| Responds successfully (a normal completion)                    | neutral — no `record_failure`, no `record_success` | not recorded (no exclusion signal)      |
| Responds with a model-side error (e.g. `4xx` / `404`)          | neutral — no `record_failure`                      | not recorded                            |
| Exhausts its adaptive ladder without ever responding (timeout) | `record_failure(provider_id)`                      | not recorded (never excludes the model) |
| Fails with a connection / transport error                      | `record_failure(provider_id)`                      | not recorded                            |

### STORY-075-AC-4

Given a warmup call about to run for a `(provider, model)` target, when the pipeline resolves its
per-attempt timeout, then the budget is read from that target's role=INFERENCE adaptive-timeout
ladder (`benchmark.min_timeout_seconds → benchmark.max_timeout_seconds` escalation), not from a
separate fixed warmup deadline.

### STORY-075-AC-5

Given `benchmark.warmup_enabled` is `true` and a selected model that passed readiness cannot load
at run time so its warmup never responds (its adaptive ladder exhausts with no response), when the
model-switch warmup runs, then the warmup timeout is recorded as a provider failure to the circuit
breaker — surfacing the unloadable model at first use, not silently mid-run (EC-PROV-1a, warmup-on
facet).

### STORY-075-AC-6

Given a hard stop is requested at the model-switch boundary before a warmup completes, when the
warmup unit reaches its safe checkpoint, then the run halts through the `CancellationToken` without
issuing that group's task inferences, and the cancelled warmup reports neither a success nor a
failure to the circuit breaker.

## Test plan

- STORY-075-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_warmup.py`,
  `test_warmup_fires_once_before_first_task_inference_when_enabled`.
- STORY-075-AC-2 — unit, same file,
  `test_warmup_off_issues_no_warmup_and_runs_first_task_directly`.
- STORY-075-AC-3 — unit (table-driven, one `@pytest.mark.parametrize` row per outcome), same file,
  `test_warmup_outcome_drives_circuit_breaker_and_never_excludes_model`.
- STORY-075-AC-4 — unit, same file,
  `test_warmup_budget_read_from_role_inference_ladder`.
- STORY-075-AC-5 — integration,
  `tests/integration/test_warmup_on_first_use_model_load_failure.py`,
  `test_warmup_timeout_for_unloadable_model_records_provider_failure`. Covers EC-PROV-1a (warmup-on
  facet).
- STORY-075-AC-6 — unit, same file as AC-1..AC-4,
  `test_hard_stop_at_warmup_halts_run_and_reports_no_breaker_outcome`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-075.
- [x] EC-PROV-1a's warmup-on facet has a passing test (STORY-075-AC-5).
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/benchmark_pipeline/`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-075.
- [x] The module inventory is unchanged (warmup lives inside the existing
  `backend/benchmark_pipeline/` module's `_internal/`).
- [x] Tester pass complete (independent test review/hardening).
- [ ] Spec-conformance-reviewer pass complete.
- [ ] Story status flipped to `done`.

## Notes

**This gap predates Phase 10 (the UI phase).** It is backend-pipeline scope. It was discovered
during the 2026-07-22 Phase-10 verification, when STORY-074 could only cover the warmup-off path of
EC-PROV-1a and explicitly deferred the warmup-on variant here (STORY-074 Notes: "`benchmark.warmup_enabled`
exists only as a settings toggle; the pipeline has no warmup implementation … Building the warmup
pipeline and its EC-PROV-1a/EC-PROV-3 warmup-timeout behaviour is out of scope and should be its own
`backend/benchmark_pipeline/` story."). A grep of `src/ollama_llm_bench/backend/benchmark_pipeline/`
confirms zero warmup code exists today. This story is the prerequisite for full EC-PROV-1a coverage
beyond STORY-074's warmup-off scope.

**Shared claim of EC-PROV-1a with STORY-074 is intentional, not a conflict.** EC-PROV-1a has two
facets: the warmup-off first-use failure (owned and tested by STORY-074) and the warmup-on
model-switch failure (this story). Both stories name EC-PROV-1a in `edge_cases:`; the traceability
edge-case index treats that as coverage, not uniqueness, so the id resolves to both proving tests.
The EC-PROV-1a mapping row that was missing from
`14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` was added on 2026-07-22 by the
project-owner-sanctioned one-time spec correction recorded in STORY-074's Notes; that row's
"Behaviour under test" text covers both facets, so no further mapping change is needed for this
story.

**No ADR is warranted.** The warmup behaviour is fully pinned by the specification (DD-64,
EC-PROV-1a, `08_CIRCUIT_BREAKER.md` §6.4/§6.9, `07_ADAPTIVE_TIMEOUT.md` §4); per the ADR rule an ADR
must not duplicate a decision the spec already fixes. The clauses are cited above instead.

## Settled decisions (project owner, 2026-07-22)

The specification is silent on the following warmup details. They were raised to the project owner
during story review and settled as follows; the coder implements these values, not alternatives:

1. **Warmup prompt content.** The warmup sends the literal fixed prompt `Reply with exactly: OK` —
   deterministic, trivially cheap, and its expected one-token reply lets a test assert the call
   produced a real completion.
1. **Warmup completion-token budget.** A fixed `max_output_tokens` of `16` — small enough to be
   instant on any loaded model, large enough that every tokenizer/provider can emit a complete
   short reply without truncation edge cases. Never the run's `benchmark.max_output_tokens`.
1. **Number of warmup attempts.** The full ladder — `1 + benchmark.retry_count` escalating attempts,
   the same attempt ladder as an ordinary inference call (the plain reading of
   `07_ADAPTIVE_TIMEOUT.md` §4's "escalation headroom"). "Exhausts its adaptive ladder without ever
   responding" therefore means: all `1 + retry_count` attempts ended without a response.
1. **Adaptive-timeout state on a warmup response.** A successful warmup leaves adaptive state
   entirely untouched — its trivial completion time is not representative of a real task and must
   not seed the role=INFERENCE last-known-good budget. Warmup only pre-loads the model and feeds
   the breaker's liveness verdict.

## Open question (may be settled at implementation kickoff)

1. **Warmup observability.** It is unspecified whether the warmup emits its own run-log line or
   event (beyond the breaker's existing `_model_stability_changed` on a trip), or runs silently.
   The event-bus catalog has no dedicated warmup event. Recommended default, pending owner
   confirmation: emit an ordinary `run.*` structlog line at warmup start and settle (no new
   event-bus kind, no UI surface); silent-running hides a potentially multi-second model load from
   the run log.

## Notes (implementation, 2026-07-23)

**Observability question settled silent at kickoff.** The open question above was settled
**silent** at kickoff on 2026-07-23: warmup emits no structlog line and no new event-bus kind.
The earlier "emit an ordinary `run.*` structlog line" recommendation was withdrawn once the
pipeline's actual logging shape was checked — the benchmark pipeline emits no structlog calls at
all, and the per-run log file is built exclusively from `EventBus` events, so a plain structlog
line at warmup start would never reach the run log as wired; it would be dead code producing
output nobody reads. Making warmup visible in the run log is a future story's job, and it should
add a spec-sanctioned event-bus kind (not a structlog call) so the visibility actually lands where
users look.

**AC-5 proves the breaker trip through row outcomes, not a stability event.** STORY-075-AC-5's
test asserts the circuit breaker trips by checking that the affected group's `BenchmarkResult`
rows settle `FAILED_PROVIDER` with the breaker-skip message, not by asserting a
`_model_stability_changed` `TRIPPED` event on the event bus. That event is currently emitted only
from the `JUDGE_CHECK` phase's stability-dispatch path, never from `Phase.INFERENCE` where warmup
lives — a pre-existing gap in the stability-event wiring, not something this story introduced.
Wiring the stability-changed event into the `INFERENCE` phase so a warmup-triggered trip also
surfaces there is a follow-up candidate for a future story.

**Two dispatcher-thread-only architecture-scan allowlists extended.**
`tests/architecture/test_benchmark_pipeline_module.py` and
`tests/architecture/test_stability_dispatcher_thread_only.py` both allowlist
`_internal/warmup.py` alongside the existing `_internal/stability_dispatch.py` entry. Warmup runs
on the pipeline dispatcher thread and blocks on the single unit it submits to the `TaskRunner`
worker pool — the same sanctioned "dispatcher submits, worker executes one blocking call, breaker
and adaptive-timeout state are touched only back on the dispatcher thread" pattern the stability
dispatcher already uses, so it needed the same allowlist entries rather than a new exception
shape.

**AC-5's `warmup_enabled` flag is read through the mocked `SettingsService` seam.** The
integration test for AC-5 supplies `benchmark.warmup_enabled=true` via the mocked
`SettingsService.get_bool("benchmark.warmup_enabled", run=run)` call rather than a raw dict entry
in a snapshot fixture, because that is how `lifecycle.py` actually reads the frozen flag in
production (a `SettingsService` call scoped to the run, not a direct snapshot-object attribute
read). Matching the real read path keeps the test honest about what production code calls.

**Discovered pre-existing deviation (final whole-branch review, 2026-07-23): per-task timeout
exhaustion still feeds the circuit breaker.** `_internal/stability_dispatch.py` (the STORY-030
per-task path, untouched by this story) calls `circuit_breaker.record_failure(provider_id)` when
a task's own adaptive ladder exhausts with a timeout, before settling the row `FAILED_TIMEOUT`.
`08_CIRCUIT_BREAKER.md` §6.4 says a `FAILED_TIMEOUT` task does **not** count toward the breaker
(MISS-25), and §6.9 says the breaker's timeout-based signal comes **exclusively** from the
model-switch warmup — the exclusivity this story's spec inputs restate. The same call site also
fires for role=JUDGE ladder exhaustion. No existing test pins the deviant behaviour. This story's
warmup code conforms to §6.4/§6.9; the conflict is pre-existing and out of this story's declared
scope ("this story only calls `record_failure`"). Follow-up story needed: remove that per-task
`record_failure` call and pin §6.4/§6.9 exclusivity with a test covering both the INFERENCE and
JUDGE ladder-exhaustion paths.

**Consolidated test-harness follow-up.** Three related cleanups are queued as one future
"pipeline/integration test-harness consolidation" item rather than scattered notes: (1) the AC-5
integration test duplicates the STORY-074 sibling's local harness helpers (`_InlineRunDispatcher`,
`_synchronous_submit`, `_make_task`, `_make_run_start_request`) verbatim — third occurrence of
this pattern, strengthening the case for a shared `tests/integration/` conftest extraction;
(2) `test_warmup.py`'s `_RecordingResultsStore` hand-wraps the full `ResultsStore` Protocol where
a `FakeResultsStore` subclass overriding `update_result` would do; (3) AC-4's `retry_count=1`
case sleeps one real jittered retry backoff (0.5–1.5 s) — same shape as STORY-074's AC-3
follow-up; a zero-jitter injectable retry policy for tests would fix both.
