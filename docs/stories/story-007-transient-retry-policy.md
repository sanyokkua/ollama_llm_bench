---
id: STORY-007
title: Provide the transient-only retry policy with bounded exponential backoff
status: done
spec_clauses:
  - 11_Services_and_Algorithms/18_RETRY_POLICY.md#61-the-retry-filter
  - 11_Services_and_Algorithms/18_RETRY_POLICY.md#62-per-category-retry-parameters
  - 11_Services_and_Algorithms/18_RETRY_POLICY.md#63-backoff-computation
  - 11_Services_and_Algorithms/18_RETRY_POLICY.md#64-honouring-a-provider-retry-after
  - 11_Services_and_Algorithms/18_RETRY_POLICY.md#65-respecting-cancellation
modules:
  - backend/retry/
acceptance_criteria:
  - STORY-007-AC-1
  - STORY-007-AC-2
  - STORY-007-AC-3
  - STORY-007-AC-4
  - STORY-007-AC-5
depends_on:
  - STORY-002
owner: coder
estimate: S
---

# STORY-007 — Provide the transient-only retry policy with bounded exponential backoff

## Goal

Give a momentary, transient failure — a network blip, a provider 5xx, a rate limit, a brief
database lock — a bounded number of further attempts with exponential backoff and jitter,
while guaranteeing a non-transient failure is surfaced on its first occurrence and that a
pause or stop is honoured between attempts. This is the single retry primitive the provider
adapters and the persistence layer wrap their calls in.

## In scope

- `with_retry(operation, *, policy, token)`: a pure wrapper around a blocking callable that
  retries only on `TransientError` (the category root, never a leaf list — a new transient
  leaf is retried automatically with no change to this module), re-raising any
  `PermanentError`, `UserError` (including `TaskCancelledError`), or `ProgrammerError`
  immediately on first occurrence without catching the `ProgrammerError` at all.
  `ProgrammerError` descends from `BaseException` outside `Exception`, so an `except Exception` inside this wrapper never intercepts it.
- The `RetryPolicy` value object: `attempts`, `initial_wait`, `max_wait`, `jitter`,
  `total_budget` — all Struct fields — and the default transient policy
  (`attempts = 1 + retry_count`, `initial_wait = 0.5s`, `max_wait = 8.0s`, `jitter = 1.0s`,
  `total_budget = 60s`), plus the ability to construct a leaf-tuned policy (the leaf-specific
  parameter rows for `ProviderOverloadedError`, `ProviderRateLimitedError`,
  `DatabaseLockedError` are supplied by their respective callers as policy values; this
  module does not hardcode which leaf gets which policy).
- The backoff formula: `base = min(initial_wait * 2 ** (n - 1), max_wait)`, `wait = max(0, base + uniform(-jitter, +jitter))`, capped before jitter is added, with a running
  cumulative-elapsed-time check against `total_budget` that stops further attempts (and
  re-raises the last error) before the budget would be exceeded.
- The provider-supplied `retry_after` override: when present on the error, it overrides the
  computed backoff for the next attempt, clamped to the policy's `max_wait`, with the total
  budget check still applied.
- Cancellation-awareness: `token.raise_if_cancelled()` checked at the start of every attempt;
  the backoff sleep implemented as `token.wait(wait_seconds)` so a cancellation mid-backoff
  ends the sleep immediately and the next start-of-attempt checkpoint raises
  `TaskCancelledError`.

## Out of scope

- The adaptive-timeout budget request (`adaptive_timeout.next_budget(...)`) and its
  role-aware success/timeout reporting — owned by `backend/adaptive_timeout/` in a later
  phase; this module's wrapper does not know about timeout roles, only about the
  `TransientError` category and the policy's own attempt/backoff/budget parameters.
- The circuit breaker consultation (`should_skip`, `record_failure`, `record_success`) —
  owned by `backend/circuit_breaker/`, consulted by the pipeline unit outside this wrapper,
  per the retry policy's own §6.8.
- `BenchmarkResultAttempt` row construction and persistence — a later pipeline concern; this
  module only performs the retry loop, it does not persist attempt history.
- The provider-adapter boundary that translates raw SDK exceptions into typed leaves before
  handing them to this wrapper — owned by the Phase-2/3 provider modules.

## Spec inputs

- `11_Services_and_Algorithms/18_RETRY_POLICY.md#61-the-retry-filter` — the binding rule that
  retry is decided on `isinstance(error, TransientError)`, the category root, never a
  leaf-by-leaf list.
- `11_Services_and_Algorithms/18_RETRY_POLICY.md#62-per-category-retry-parameters` — the
  default transient parameter row and the three leaf-tuned rows this module's `RetryPolicy`
  type must be able to represent (even though this story does not wire the leaf-specific
  policies to their callers — that is each caller's own concern).
- `11_Services_and_Algorithms/18_RETRY_POLICY.md#63-backoff-computation` — the exact backoff
  formula, the cap-before-jitter rule, and the cumulative-budget cutoff.
- `11_Services_and_Algorithms/18_RETRY_POLICY.md#64-honouring-a-provider-retry-after` — the
  retry-after override and its clamp-to-`max_wait` rule.
- `11_Services_and_Algorithms/18_RETRY_POLICY.md#65-respecting-cancellation` — the
  start-of-attempt cancellation checkpoint and the cancellation-aware backoff sleep via
  `token.wait(...)`.

## Design constraints

- `backend/retry/` is Qt-free; it imports only `backend/infra` (for randomness/backoff
  timing helpers, if needed) and the standard library (`01_MODULE_INVENTORY.md` §4.1). No
  network code lives here — this is a pure policy primitive.
- `with_retry` is a pure function over its arguments: it takes a callable, a policy, and a
  token, and returns the callable's result or re-raises the final exception with its
  `__cause__` chain intact — no module-level globals, no shared mutable state.
- The retry wrapper runs synchronously on whatever thread calls it (a `TaskRunner` worker
  thread in the real application); it performs no threading of its own.
- Only `TransientError` is retried by this wrapper; every other exception — including a
  `ProgrammerError`, which this wrapper's `except Exception` clause structurally cannot
  catch — propagates on the first attempt.

## Acceptance criteria

### STORY-007-AC-1

Given a callable that raises a custom `TransientError` subclass (not one of the four
built-in transient leaves) twice then succeeds, `with_retry` returns the success value and
the callable was invoked exactly three times — proving the filter matches on the category
root, not a hardcoded leaf list.

### STORY-007-AC-2

Given a callable that always raises the default-policy transient error, `with_retry`
re-raises that error after exactly `1 + retry_count` attempts (the default policy), with the
original exception chained as `__cause__`; given `retry_count = 0` it makes exactly one
attempt.

### STORY-007-AC-3

Given a callable that raises a `PermanentError`, a `UserError`, or a `TaskCancelledError`,
`with_retry` re-raises it immediately after exactly one attempt; given a callable that raises
a `ProgrammerError` subclass, `with_retry` does not catch it at all (it propagates
uncaught, verified by asserting no retry bookkeeping occurred).

### STORY-007-AC-4

Successive computed backoff waits (absent a `retry_after` override) grow geometrically per
the documented formula, are capped at `max_wait` before jitter is added, and a series of
transient failures whose cumulative backoff would exceed `total_budget` stops before the
budget is breached and re-raises the last error without a further attempt. A `retry_after`
value on the error overrides the computed backoff for the next attempt, clamped to
`max_wait`.

### STORY-007-AC-5

A cancellation requested between attempts (before the next attempt starts) causes the next
`token.raise_if_cancelled()` checkpoint to raise `TaskCancelledError` with no further attempt
made; a cancellation requested during the backoff sleep ends the sleep immediately (the wait
returns well before its full `wait_seconds` duration) and the next checkpoint raises
`TaskCancelledError`.

## Test plan

- STORY-007-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/retry/tests/test_with_retry.py`,
  `test_retry_filter_matches_transient_category_root_not_leaf_list`.
- STORY-007-AC-2 — unit, same file, `test_default_policy_attempt_cap_and_cause_chaining`.
- STORY-007-AC-3 — table-driven unit, same file,
  `test_permanent_user_and_programmer_errors_are_not_retried`.
- STORY-007-AC-4 — property + unit, same file,
  `test_backoff_growth_cap_budget_cutoff_and_retry_after_override`.
- STORY-007-AC-5 — unit, same file,
  `test_cancellation_at_attempt_start_and_during_backoff_sleep`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-007.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/retry/`.
- [ ] Backend branch coverage for `backend/retry/` meets the Phase 1 ≥90% gate.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
