---
id: STORY-004
title: Provide the Clock, structlog two-stream logging setup, and OS path resolver
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#5-clock
  - 16_Engineering_Standards/06_LOGGING_STANDARD.md#2-the-two-log-streams
  - 16_Engineering_Standards/06_LOGGING_STANDARD.md#3-logging-configuration
  - 16_Engineering_Standards/06_LOGGING_STANDARD.md#6-bound-context-and-correlation
  - 16_Engineering_Standards/06_LOGGING_STANDARD.md#7-the-redaction-processor
  - 16_Engineering_Standards/06_LOGGING_STANDARD.md#9-rotation-retention-and-locations
  - 10_Domain_and_Data/07_FILE_LAYOUT.md#8-rotation-and-cleanup-policies
modules:
  - backend/infra/
acceptance_criteria:
  - STORY-004-AC-1
  - STORY-004-AC-2
  - STORY-004-AC-3
  - STORY-004-AC-4
  - STORY-004-AC-5
depends_on:
  - STORY-001
owner: coder
estimate: M
---

# STORY-004 — Provide the Clock, structlog two-stream logging setup, and OS path resolver

## Goal

Give every other module the three small, cross-cutting infrastructure primitives it depends
on to be deterministically testable and correctly observable: an injectable time source, the
application's two independent, correctly-redacted log streams, and a resolved on-disk path
API layered over the platform-detected application-data root. This is what lets `backend/*`
stay Qt-free and asyncio-free while still producing structured, non-blocking, correctly
redacted logs and stable timestamps.

## In scope

- The `Clock` Protocol (`now_utc() -> Iso8601Utc`, `monotonic_ms() -> int`) and its default
  wall-clock implementation.
- `configure_logging(...)`: the one-time `structlog` setup installing the two independent,
  non-propagating streams — `run.*` (per-run file, `DEBUG`, no redaction processor except the
  one documented exception for the chained provider-exception detail) and `app.*` (single
  rotating file, `INFO` in a release build, always passed through the `redact_for_log`
  processor) — including the `app.*` processor pipeline order (bind context, level,
  ISO-8601 UTC timestamp, redaction, render) and the non-blocking bounded-queue-plus-writer-
  thread sink.
- The bound-context helpers that bind `run_id`/`correlation_id` via context variables at run
  start so they propagate to every record emitted from the run's worker threads, and that
  close/detach a run's logger at run end.
- A path-resolution surface (`user_data_dir` and the derived `logs/app/`, `logs/run/`
  sub-paths) that composes over the `PlatformDetector`'s `app_data_root` (STORY-005) rather
  than re-detecting the OS itself.
- The `app.log` rotation parameters (10 MB trigger, 5 retained backups, 60 MB ceiling) wired
  into `configure_logging`.

## Out of scope

- The `redact` / `redact_for_log` function bodies and the denylist — owned by STORY-002;
  this story only *installs* the `redact_for_log` processor into the `app.*` pipeline.
- `PlatformDetector` / OS classification and `app_data_root` resolution — owned by STORY-005;
  this story consumes that Protocol, it does not implement OS detection.
- The `TaskRunner`/`CancellationToken` concurrency primitives — owned by STORY-006.
- Run-log cleanup (age/count pruning) and settings-backup cleanup — a later persistence/
  lifecycle story; this story only fixes the rotation trigger for `app.log`.
- The exception hooks (interpreter/thread/Qt message handler) — installed by the composition
  root in a later phase, not by this module.

## Design constraints

- `backend/infra/` is Qt-free; no imports of higher-level `backend/*` services, `ui`, or
  `adapters` (`01_MODULE_INVENTORY.md` §4.1).
- Logging is configured exactly once, called only from the composition root in later phases;
  this story's `configure_logging` must therefore be idempotent-safe to call twice in a test
  without duplicating handlers, but the module itself performs no auto-configuration on
  import. Loggers are obtained at module scope, never inside a constructor.
- The `run.*` namespace never propagates to the root logger and never reaches `app.log`; this
  is enforced by configuring the run logger with `propagate=False` (or equivalent) and is
  independently asserted by a test.
- `Clock` is synchronous, never blocks, never raises, and is callable from any thread.
- No f-string or `%`-formatted message is built inside a log call anywhere in this module's
  own code; every call site uses a static event name plus keyword fields.

## Acceptance criteria

### STORY-004-AC-1

The `Clock` Protocol's default implementation returns a `now_utc()` value that round-trips as
a valid ISO-8601 UTC timestamp and a `monotonic_ms()` value that is non-decreasing across two
successive calls; a fake/injectable `Clock` used in tests produces deterministic values.

### STORY-004-AC-2

After `configure_logging` runs, a record emitted on the `app.*` namespace is written to
`<app-data>/logs/app/app.log` with the fields the app-pipeline order requires (bound context,
level, ISO-8601 UTC timestamp) and has passed through `redact_for_log`; a record emitted on a
run-scoped `run.*` logger is written to `<app-data>/logs/run/run_<run_id>_<unix_ts>.log` and
is **not** passed through `redact_for_log`.

### STORY-004-AC-3

A record emitted on the `run.*` namespace never appears in `app.log` and a record emitted on
the `app.*` namespace never appears in a run log file (the two streams are independently
observed to be disjoint via their respective handlers/propagation settings).

### STORY-004-AC-4

Binding `run_id` and `correlation_id` once at run start causes every subsequent record
emitted on that run's logger — including one emitted from a different worker thread within
the bound scope — to carry both fields; unbinding (closing the run's logger at run end) stops
further records on that run id from being associated with the old context.

### STORY-004-AC-5

Given a fake `PlatformDetector` supplying a known `app_data_root`, the path-resolution
surface returns `<app_data_root>/logs/app/app.log` and `<app_data_root>/logs/run/` as the
resolved locations `configure_logging` writes into, and `app.log`'s rotation is configured
with a 10 MB trigger and 5 retained backups.

## Test plan

- STORY-004-AC-1 — unit, colocated `src/ollama_llm_bench/backend/infra/tests/test_clock.py`,
  `test_clock_now_utc_and_monotonic_ms_contract`.
- STORY-004-AC-2 — integration-style unit (real file I/O against `tmp_path`), same directory
  `src/ollama_llm_bench/backend/infra/tests/test_logging.py`,
  `test_app_stream_is_redacted_and_run_stream_is_not`.
- STORY-004-AC-3 — unit, same file, `test_run_stream_never_propagates_to_app_log`.
- STORY-004-AC-4 — unit, same file, `test_bound_run_context_propagates_across_worker_threads`.
- STORY-004-AC-5 — unit,
  `src/ollama_llm_bench/backend/infra/tests/test_path_resolution.py`,
  `test_log_paths_resolve_from_platform_detector_and_rotation_is_configured`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-004.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/infra/`.
- [x] Backend branch coverage for `backend/infra/` meets the Phase 1 ≥90% gate.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.

## Notes

- **Module-boundary table reading (clarification, explicit user direction).**
  `16_Engineering_Standards/01_PROJECT_STRUCTURE.md` line 341's per-row table, read
  literally, would forbid `backend/infra/` from importing anything from any other
  `backend/*` sub-package at all. That literal reading is too strict and is not how this
  constraint is applied in this codebase: the real constraint is that `backend/` stays
  decoupled from `ui`/`adapters` (backend never imports `ui`/`adapters`) — not that every
  backend sub-package is walled off from every other. Within `backend/`, sub-packages
  freely reuse each other's types/functions/classes. Concretely, this story imports
  `Iso8601Utc` directly from `backend/domain/models.py` (used as the `Clock` Protocol's
  and `SystemClock`'s `now_utc()` return type — no local redeclaration) and imports
  `redact_for_log` directly from `backend/errors/api.py`, installing it as the `app.*`
  pipeline's redaction processor with no injected-callable indirection — both per this
  explicit clarification overriding a literal reading of the module-boundary table.
- **`PlatformDetector` Protocol location (clarification, explicit user direction).**
  STORY-005 (`backend/platform/`, the real `PlatformDetector`) is still `status: draft`
  with no code at all, but this story's AC-5 needs path resolution tested against "a
  fake `PlatformDetector`". Since there is nothing in `backend/platform/` yet to import,
  a narrow, structurally-typed `PlatformDetector` Protocol carrying only the single
  `app_data_root` member this module needs is declared locally in
  `backend/infra/protocols.py`, rather than this story reaching into STORY-005's
  not-yet-existent module. STORY-005's future concrete class satisfies this Protocol
  structurally with zero coupling (Protocol matching is structural, not nominal), and
  this keeps this story's `modules: [backend/infra/]` front-matter accurate.
