# Python Developer — Logging Standards

Logging rules for Ollama LLM Bench. See [SKILL.md](SKILL.md) for general Python rules.

> **Migration note**: The project currently uses stdlib `logging` directly. Target state is `structlog` wrapping stdlib with `QueueHandler`/`QueueListener` for thread-safe Qt integration.

---

## Critical Rules

- Log exclusively through `logging.getLogger(__name__)` — MUST NOT use `print()`, `sys.stdout.write()`, or `sys.stderr.write()`
- MUST use `%s`-style parameterized placeholders — MUST NOT use f-strings or `.format()` in log arguments
- Exactly one action per caught exception: log it OR reraise it — MUST NOT do both; MUST NOT silently swallow
- `ERROR` is reserved for unexpected failures only — MUST NOT use for expected business outcomes
- NEVER log passwords, tokens, API keys, or authentication secrets at any level

---

## Log Level Guide

| Level | When to use | Example |
|-------|-------------|---------|
| `ERROR` | Unexpected failure requiring investigation | Unhandled exception, data corruption |
| `WARNING` | Unexpected condition handled gracefully | Missing optional config, deprecated format |
| `INFO` | Significant event completed normally | Benchmark run started/completed, app initialized |
| `DEBUG` | Developer diagnostics: variable state, decisions | Model warm-up result, task execution path |
| Not used | `TRACE` not available in stdlib — use `DEBUG` | — |

Default: `INFO` in release, `DEBUG` during development (`--log-level` flag).

---

## Logger Declaration

```python
import logging

logger = logging.getLogger(__name__)

class MyService:
    def process(self, item_id: str) -> None:
        logger.info("Processing item: %s", item_id)
```

MUST declare logger at module level. MUST NOT create loggers inside methods.

---

## Message Construction

```python
# CORRECT — parameterized placeholders (lazy evaluation)
logger.info("File loaded: %s (%d bytes)", file_name, file_size)

# WRONG — f-string (evaluated even if level is disabled)
logger.debug(f"Processing file {file_name} at {path}")

# WRONG — .format() (also eager evaluation)
logger.debug("Processing file {} at {}".format(file_name, path))
```

Guard expensive computations:

```python
if logger.isEnabledFor(logging.DEBUG):
    logger.debug("Document structure: %s", document.to_tree_string())
```

---

## Exception Logging

Pass `Throwable` as `exc_info` or as the last argument:

```python
# CORRECT — preserves stack trace
logger.error("Failed to save file: %s", file_path, exc_info=True)

# CORRECT — exception as last arg
logger.error("Failed to save: %s", file_path, exc_info=e)

# WRONG — loses stack trace
logger.error("Failed: %s", e)
```

One action per except block:

```python
# CORRECT — log and handle
except ConnectionError as e:
    logger.error("Ollama server unreachable: %s", e, exc_info=True)
    return InferenceResponse(has_error=True, error_message=str(e))

# CORRECT — reraise for caller
except ConnectionError as e:
    raise OllamaConnectionError("Server unreachable") from e

# WRONG — log AND reraise (duplicate log entries)
except ConnectionError as e:
    logger.error("Connection failed", exc_info=True)
    raise  # caller may also log
```

---

## Events to Log

### MUST log
- Application lifecycle: startup, shutdown
- Benchmark run start/complete/fail
- Unhandled exceptions (via global exception handler)
- Database initialization, migration events

### PREFER logging
- Model warm-up results (`INFO`)
- Task execution progress (`DEBUG`)
- User-facing error recovery (`WARNING`)

### MUST NOT log
- Every method entry/exit at `INFO`
- Routine UI events (button clicks, widget updates)
- Successful no-op operations at `INFO` or above
- Full LLM responses (too large — log summary metrics only)

---

## Qt Thread Considerations

Install global uncaught exception handler in application startup:

```python
import sys

def _exception_hook(exc_type, exc_value, exc_tb):
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))

sys.excepthook = _exception_hook
```

MUST NOT log expensive `str()` calls or large data structures on the main thread — defer to background or guard with level check.

---

## Hot Path Restrictions

MUST NOT log at `INFO` or above inside tight loops. Emit a single summary after:

```python
for task in tasks:
    logger.debug("Processing: %s", task.task_id)
    process(task)
logger.info("Processed %d tasks", len(tasks))
```

MUST NOT log inside Qt paint events, `resizeEvent`, or property listeners on frequently-changing values.

---

## Target: structlog + QueueHandler

Future migration pattern (not yet implemented):

```python
import structlog

logger = structlog.get_logger(__name__)

# Structured key-value logging
logger.info("benchmark_started", run_id=run_id, model_count=len(models))
logger.error("task_failed", task_id=task_id, error=str(e))
```

Thread-safe Qt integration via `QueueHandler`/`QueueListener` to marshal log records from background threads to the main thread for display in the log widget.
