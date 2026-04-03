---
description: "Logging rules for PySide6 desktop app — structlog, QueueHandler, log levels, sensitive data masking"
globs: "src/**/*.py"
alwaysApply: false
---

# Python Desktop App Logging

> **Migration note**: The project currently uses basic `logging.getLogger(__name__)`. Target state is `structlog` wrapping stdlib `logging`. Existing code should not be refactored without a migration plan.

## Critical Rules

- MUST use `logging.getLogger(__name__)` at module level — never inside functions, methods, or `__init__`
- MUST use `structlog` wrapping standard `logging` as the application logging facade (target state)
- MUST NOT use f-strings, `.format()`, or string concatenation inside `logger.*()` calls — pass data as keyword arguments (structlog) or `extra` dicts (stdlib)
- MUST NOT log passwords, API keys, tokens, secrets, SSNs, or any sensitive data at any level
- MUST reserve ERROR exclusively for unexpected failures requiring investigation — NOT for validation failures or expected empty results
- MUST NOT both log an exception and re-raise it — choose exactly one action
- MUST use `QueueHandler` / `QueueListener` so log I/O never blocks the Qt event loop thread
- MUST use `logger.exception()` or `exc_info=True` inside `except` blocks — MUST NOT use `logger.error(str(e))`

## Log Level Severity

| Level | Numeric | Use For |
|-------|---------|---------|
| CRITICAL | 50 | Process cannot continue, shutting down |
| ERROR | 40 | Unexpected operation failure, requires investigation |
| WARNING | 30 | Unexpected condition handled gracefully (retry succeeded, fallback activated) |
| INFO | 20 | Significant lifecycle/business event (app started, user action completed) |
| DEBUG | 10 | Diagnostic info — variable state, decision branches |

- MUST disable DEBUG in production builds — set root logger to INFO or above
- MUST NOT use ERROR for: user input validation, expected empty results, handled timeouts with retry

## Logger Instantiation

```python
# Target (structlog)
import structlog
logger = structlog.get_logger()

# Current (stdlib)
import logging
logger = logging.getLogger(__name__)
```

- MUST NOT call `logging.getLogger()` with no argument
- MUST NOT create loggers inside functions or `__init__`
- MUST configure logging exactly once in entry point (`main.py`) before `QApplication`

## Message Format

```python
# GOOD — keyword arguments
logger.info("file_saved", file_path=str(path), size_bytes=size)

# BAD — f-string
logger.info(f"Saved file {path} ({size} bytes)")
```

- PREFER static, `snake_case` event names as first positional argument
- MUST write messages with enough context to understand without reading source code
- MUST NOT write vague messages: `"Error occurred"`, `"Something went wrong"`, `"Done"`

## Events to Log

| Event | Level |
|-------|-------|
| Unhandled exceptions | ERROR |
| Application lifecycle (start, shutdown) | INFO |
| Significant user actions (benchmark start, export) | INFO |
| External interactions (Ollama API, SQLite) | INFO |
| Background task lifecycle (worker started, completed) | INFO |
| Fallback activation, retry success | WARNING |

- MUST NOT log every function entry/exit at INFO
- MUST NOT log per-item inside loops > 100 items — log summary after loop

## Exception Handling

- MUST use `logger.exception()` inside `except` blocks for full traceback
- Choose exactly one per `except`: log it OR re-raise it — never both
- MUST install `sys.excepthook` for uncaught exceptions
- MUST install Qt-level exception hook for exceptions in signals/slots

## Qt Event Loop & Non-Blocking I/O

- MUST use `QueueHandler` + `QueueListener` so all log I/O runs on background thread
- MUST NOT attach `FileHandler` or `StreamHandler` directly to loggers
- MUST register `atexit` callback to stop `QueueListener` and flush

## Sensitive Data Masking

- MUST NEVER log: passwords, API keys, tokens, secrets, credit card numbers, SSNs
- MUST redact personal data (email → `j***@example.com`, phone → `***5309`)
- PREFER implementing masking as a structlog processor before the renderer

## File Output

- MUST use `RotatingFileHandler` with size limits — MUST NOT use bare `FileHandler`
- MUST set `encoding="utf-8"` on all file handlers
- Default: `maxBytes=10_485_760` (10 MB), `backupCount=5`
