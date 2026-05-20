# ADR-0001: Adaptive Per-Task Timeout with Cross-Task Memory

## Status

Accepted

## Date

2026-05-12

## Context

Every benchmark task previously reset to the minimum timeout (300 s) regardless
of which timeout value had succeeded for the same model on a prior task.  A slow
model therefore wasted the same full retry sequence on every single task, and the
worst-case wait per task was 28.6 minutes (300 + 519 + 900 s with default
settings).

The key observations that motivate this change:

1. If model M succeeded at attempt 1 (timeout = 520 s), the *next* task is
   unlikely to succeed at 300 s — skipping attempt 0 entirely saves ~300 s.
2. If M consistently exhausts all retries at max timeout, further attempts waste
   wall-clock time without changing the outcome.  Excluding such models after N
   consecutive full failures is strictly better than continuing indefinitely.
3. State must be per-model and per-run, not global — different models in the same
   run can have very different latency profiles.

## Decision

Introduce `AdaptiveTimeoutService` (a new in-memory, thread-safe service) that
remembers the last successful timeout for each `(provider_id, model_name)` key
within one benchmark run.

**Algorithm:**

- `next_timeout(provider, model, attempt)` performs geometric interpolation from
  `current_good_s` to `max_s` across `retry_count` steps.  Attempt 0 always
  returns `current_good_s`; the final attempt always returns `max_s`.
- `record_success(provider, model, successful_timeout_s)` raises
  `current_good_s` to `max(current_good_s, successful_timeout_s)` and resets
  the consecutive failure counter.
- `record_full_failure(provider, model, final_timeout_s)` increments
  `consecutive_max_failures` when `final_timeout_s >= max_s`, and marks the
  model `is_excluded=True` once the counter reaches `max_failures_to_exclude`.
  Sub-max failures reset the counter to 0 (the model recovered partially).
- `is_excluded` returns True once the threshold is reached.  The pipeline skips
  excluded models immediately, records FAILED status, and emits a single
  per-model warning notification (deduplicated by `_excluded_notified` set).

**State scope:** one `AdaptiveTimeoutService` instance per `BenchmarkExecutionTask`
run.  Both the inference stage and the judge stage share the same instance, but
use separate keys: `(result.provider_id, model_name)` for inference and
`(run.judge_provider_id, run.judge_model)` for judging.

**New setting:** `benchmark.retry_max_failures_to_exclude` (default `"3"`) added
to `AppSettingsService` and `_DEFAULTS`.

## Consequences

**Positive:**

- Slow-but-recovering models start at a higher timeout on the next task, saving
  multiple retry attempts per task for the rest of the run.
- Consistently broken models are excluded after 3 consecutive max-timeout
  failures, preventing open-ended waits.
- Zero change to the interface contract of `BenchmarkExecutionTask` — the
  adaptive behaviour is fully encapsulated in the new service.
- 16 new tests (12 unit + 4 integration) cover the service contract.

**Negative:**

- State is in-memory only — if the process crashes and the run is resumed, the
  adaptive state is lost and timeouts reset to `min_s`.  This is acceptable
  because the benefit per resumed run is small and the complexity of persisting
  this state (a new DB table or column) is not justified.
- A model that times out on task 1 but would succeed on task 2 at `min_s` will
  now start task 2 at `max_s` (since `consecutive_max_failures` locks
  `current_good_s` at `max_s`).  This is a rare edge case and the extra wait is
  bounded by `max_s`.

## Alternatives Considered

### Stateless reset (status quo)

Every task resets to `min_s`.  Simple but wastes time on slow models.  Rejected.

### Persist adaptive state in SQLite

Store `current_good_s` and `consecutive_max_failures` in a `run_model_state`
table so resumed runs inherit prior state.  Adds schema complexity and a
migration.  The benefit is marginal (resumes are rare).  Deferred.

### Exponential back-off without memory

Increase `min_s` globally when any model times out.  Affects all models equally,
including fast ones.  Rejected — per-model isolation is required.
