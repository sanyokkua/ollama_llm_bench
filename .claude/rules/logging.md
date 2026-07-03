---
paths:
  - "src/**/*.py"
---

# Logging Standard

Source of truth: `docs/v3_specification/16_Engineering_Standards/06_LOGGING_STANDARD.md`. The
application emits two independent log streams using `structlog` as the structured logging
facade over the standard-library logging transport. Log I/O is non-blocking so the GUI event
loop is never stalled. The application emits **no telemetry**.

## The two log streams — never shared, never propagated

| Stream | Namespace | Destination | Content | Redacted? |
|---|---|---|---|---|
| **Benchmark run log** | `run.*` | One file per run: `<app-data>/logs/run/run_<run_id>_<unix_ts>.log` | Per-run pipeline events, request/response timing, the chained provider exception detail (run through `redact()` first), retry attempts, circuit-breaker transitions | **No** — by design |
| **Application/system log** | `app.*` | A single rotating file: `<app-data>/logs/app/app.log` | Application lifecycle, user actions, UI events, redacted error summaries, settings changes, update checks | **Yes** — always |

- The two streams are fully independent. The `run.*` namespace **never** propagates to the
  application stream and never reaches `app.log`. Each run logger is configured so its records
  do not bubble up to the root logger.
- The `run.*` stream has **no redaction processor** — it logs user prompts and model responses
  as plain text, by design: they are the user's own data on the user's own machine, and the
  file never leaves the machine except by the user's manual choice. The **one exception**: the
  chained provider-exception detail written to `run.*` is passed through `redact()` first
  (SPEC-060) — only the SDK-exception string is redacted, not the prompts/responses.
- The `app.*` stream is **always pre-redacted** by the `redact_for_log` structlog processor.
- A `run.*` logger is created per run, bound with the run id and correlation id, and closed
  when the run ends. The `app.*` namespace is a single shared logger hierarchy for the whole
  application.

## Configuration — exactly once, before QApplication

Logging is configured **once**, in `compose.py`, before the `QApplication` is constructed and
before any worker exists. No other module configures logging. Loggers are obtained at **module
scope** — never inside a constructor (obtaining a logger must not be a side effect of
constructing a class).

The `app.*` processor pipeline, in order: (1) merge bound context variables (run/correlation
context), (2) add the log level, (3) add an ISO-8601 UTC timestamp, (4) the redaction
processor, (5) render the record as a structured line.

**Non-blocking sink**: application-stream records are placed on a bounded in-memory queue, and
a single background thread drains that queue to the rotating file. The GUI event loop never
performs file I/O for logging.

## Log levels

| Level | Use for |
|---|---|
| `CRITICAL` | The process cannot continue and is shutting down |
| `ERROR` | An unexpected failure that requires investigation |
| `WARNING` | An unexpected condition that was handled gracefully (a retry, a fallback) |
| `INFO` | A significant lifecycle or benchmark event |
| `DEBUG` | Diagnostic detail — variable state, decision branches |

`ERROR` is reserved for genuinely unexpected failures — **not** used for user input
validation, an expected empty result, or a timeout handled by a retry (those are `WARNING` or
`INFO`). In a release build the application stream's effective level is `INFO`; `DEBUG` is
disabled. The per-run benchmark stream is always at `DEBUG`. Inside an `except` block, use the
exception-logging call so the full traceback is captured; for any one `except` block, log **or**
re-raise, never both.

## Message format — static event name + keyword fields

```python
log.info("run_started", run_id=run_id, provider_id=provider_id, model_count=model_count)
log.warning("provider_retry", provider_id=provider_id, attempt=attempt, wait_s=wait_s)
log.exception("persistence_failed", run_id=run_id, table="benchmark_result")
```

- The first argument is a **static, snake_case event name** — never interpolated data.
- All variable data is passed as keyword arguments. An f-string or `%`-formatted string is
  never built inside a log call — it destroys the structured fields and can interpolate a
  secret.
- Field names are stable and snake_case; reuse the same field name for the same concept across
  event types so the streams stay queryable.

## Bound context and correlation

Run-scoped context is bound **once** at run start and automatically attached to every record
emitted within that scope, including records from the run's worker threads. A run binds a
`run_id` and a `correlation_id` at run start. The binding uses context variables so it
propagates correctly through the worker-thread/unit hierarchy (`concurrency-standard.md`). The
`correlation_id` is the same identifier carried on `ErrorContext`
(`error-handling-standard.md`), so a single operation's records can be cross-referenced across
both log files.

## The redaction processor (`redact_for_log`)

Installed in the `app.*` pipeline **only** — never `run.*`. Every record written to `app.log`
passes through it; there is no way to write an un-redacted record there. It walks the record's
fields and replaces the value of any field whose name (case-insensitively) is on the
never-log-key list with a placeholder, then — after the record is serialised to its log-line
form — scrubs the line against the secret denylist (provider API keys, bearer tokens,
`api_key=`/`authorization:` fragments, `Bearer ...` tokens, JWTs, the high-entropy catch-all)
and applies a 4000-character length cap. A property-based test fuzzes records with randomly
embedded secrets and asserts no denylist pattern survives a pass through the `app.*` pipeline.

## Exception hooks

The composition root installs a coherent set of hooks: interpreter exception hook (main
thread), thread exception hook (any non-main thread), thread excepthook (`TaskRunner` worker
threads), and a Qt message handler (re-tagged into `app.qt.*`). A programmer-error
(`BaseException`-rooted) is logged at `CRITICAL` with its full traceback and then allowed to
crash the process — surfacing the crash dialog. The application generates **no** support
bundle and sends nothing off the machine. Any other uncaught exception is logged at `ERROR`
with its full traceback.

## Rotation, retention, locations

```
<app-data>/
  logs/
    app.log            application stream (rotating)
    app.log.1 .. .5    rotated backups
    runs/
      run_<run_id>_<unix_ts>.log   one file per benchmark run
```

`<app-data>` resolves per OS (macOS: `~/Library/Application Support/OllamaLLMBench/`; Linux:
`~/.local/share/OllamaLLMBench/`; Windows: `%LOCALAPPDATA%\OllamaLLMBench\`). `app.log` rotates
at a fixed size with a bounded backup count; run files are **not** auto-deleted (a run's log is
part of its evidence — the app offers a manual housekeeping action). All log files are UTF-8.

## No telemetry

No analytics service, no crash-reporting service, no usage reporting, no background
"phone-home" of any kind. All log data stays in the per-user application data directory. Logs
leave the machine only if the user **manually** shares a log file at their own discretion. This
is a binding product decision applying to every build and release channel.

## Anti-patterns

| Anti-pattern | Why it is wrong | Correct approach |
|---|---|---|
| `print(...)` for diagnostics | No level, no structure, no destination | Structured facade with an event name |
| An f-string built inside a log call | Defeats structured fields; can interpolate a secret | Static event name plus keyword fields |
| Logging the raw string of an exception after `except` | Loses the traceback | The facade's exception-logging call |
| Logging a failure *and* re-raising it | Double-handling, duplicate records | Choose exactly one per `except` block |
| Logging a credential-bearing string to **any** stream | Leaks a secret into a shareable file | `app.*` is redacted by the processor; only the SDK-exception detail on `run.*` is redacted |
| Letting the `run.*` stream propagate to the root logger | Run detail leaks into `app.log` | Configure the run logger so it does not propagate |
| Obtaining a logger inside a class constructor | Makes construction side-effecting | Obtain loggers at module scope |
| Sending any log data off the machine | Violates the no-telemetry decision | The application never transmits logs; sharing is manual and user-initiated |
| File I/O for logging on the GUI thread | Stalls the event loop under bursty load | The non-blocking queue plus background writer thread |
