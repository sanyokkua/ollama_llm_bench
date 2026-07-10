"""``configure_logging``: the one-time two-stream ``structlog`` setup.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/06_LOGGING_STANDARD.md``
§2 (the two log streams), §3 (logging configuration), §7 (the redaction processor), §9
(rotation, retention, and locations); ``docs/v3_specification/10_Domain_and_Data/07_FILE_LAYOUT.md``
§8.1 (application-log rotation policy).

``app.*`` pipeline order (§3): merge bound run/correlation context, add level, add an
ISO-8601 UTC timestamp, redact (``redact_for_log``), render — then hand off to a
non-blocking bounded queue drained by a single background writer thread onto the
rotating ``app.log`` file handler. ``run.*`` has no redaction stage and is configured
per-run by ``run_context.open_run_logger`` — this module only prepares the ``app.*``
pipeline.
"""

from collections.abc import Mapping, MutableMapping
import logging
import logging.handlers
from pathlib import Path
from typing import Any, Final

import structlog

from ollama_llm_bench.backend.errors.api import redact_for_log
from ollama_llm_bench.backend.infra._internal.queue_sink import build_queue_handler_and_listener
from ollama_llm_bench.backend.infra._internal.run_context import merge_run_context_processor

_APP_LOGGER_NAMESPACE = "app"

DEFAULT_ROTATION_MAX_BYTES: Final[int] = 10 * 1024 * 1024
DEFAULT_ROTATION_BACKUP_COUNT: Final[int] = 5

# The marker attribute this module stamps onto the app-namespace's stdlib logger so a
# second `configure_logging` call can detect the prior installation and replace it
# cleanly, rather than relying on a module-level mutable boolean flag (which an
# architecture test may flag as a mutable global). Handler *state* is the guard, not a
# separate flag variable.
_INSTALLED_MARKER_ATTR = "_ollama_llm_bench_configured"
_QUEUE_LISTENER_ATTR = "_ollama_llm_bench_queue_listener"


def _merge_run_context(
    logger: object, method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    """Adapt ``merge_run_context_processor`` to structlog's processor call shape."""
    return merge_run_context_processor(logger, method_name, dict(event_dict))


def _redact_for_log(
    logger: object, method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    """Adapt ``redact_for_log`` to structlog's processor call shape."""
    return redact_for_log(logger, method_name, dict(event_dict))


def _build_rotating_file_handler(
    *, app_log_file: Path, max_bytes: int, backup_count: int
) -> logging.handlers.RotatingFileHandler:
    """Build the size-based rotating handler for ``app.log`` (§9; FILE_LAYOUT §8.1)."""
    app_log_file.parent.mkdir(parents=True, exist_ok=True)
    return logging.handlers.RotatingFileHandler(
        app_log_file,
        mode="a",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )


def _teardown_prior_configuration(app_logger: logging.Logger) -> None:
    """Remove and close every handler installed by a previous ``configure_logging`` call.

    Makes ``configure_logging`` idempotent-safe to call twice in a test: instead of a
    module-level mutable flag, the guard inspects the ``app.*`` stdlib logger's own
    handler state and its marker attribute.
    """
    listener = getattr(app_logger, _QUEUE_LISTENER_ATTR, None)
    if listener is not None:
        listener.stop()
    for handler in list(app_logger.handlers):
        app_logger.removeHandler(handler)
        handler.close()
    if hasattr(app_logger, _INSTALLED_MARKER_ATTR):
        delattr(app_logger, _INSTALLED_MARKER_ATTR)


def configure_app_logging(
    *,
    app_log_file: Path,
    level: int,
    max_bytes: int,
    backup_count: int,
) -> None:
    """Install the ``app.*`` stream: processor pipeline, queue sink, rotating file.

    Idempotent: a second call tears down the previously installed handler/listener
    pair before installing a fresh one, so no duplicate handler accumulates and no
    duplicate record is ever written.

    Args:
        app_log_file: The destination path for the rotating application log.
        level: The effective stdlib logging level for the ``app.*`` namespace.
        max_bytes: The rotation trigger size in bytes.
        backup_count: The number of rotated backups to retain.
    """
    app_logger = logging.getLogger(_APP_LOGGER_NAMESPACE)
    _teardown_prior_configuration(app_logger)

    rotating_handler = _build_rotating_file_handler(
        app_log_file=app_log_file, max_bytes=max_bytes, backup_count=backup_count
    )
    rotating_handler.setFormatter(logging.Formatter("%(message)s"))
    queue_handler, queue_listener = build_queue_handler_and_listener(
        target_handler=rotating_handler
    )
    queue_listener.start()

    app_logger.setLevel(level)
    app_logger.propagate = False
    app_logger.addHandler(queue_handler)
    setattr(app_logger, _QUEUE_LISTENER_ATTR, queue_listener)
    setattr(app_logger, _INSTALLED_MARKER_ATTR, True)

    structlog.configure(
        processors=[
            _merge_run_context,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            _redact_for_log,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=False,
    )
    queue_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(processor=structlog.processors.JSONRenderer())
    )
