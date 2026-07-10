"""Bind/unbind ``run_id``/``correlation_id`` context and manage a run's logger lifecycle.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/06_LOGGING_STANDARD.md``
§6 (Bound Context and Correlation) — "Run-scoped ... context is bound once at the start
of a run ... and then automatically attached to every record emitted within that scope
— including records emitted by the run's worker threads."

``contextvars`` propagate to a thread only when the thread runs inside a copied context
(``contextvars.copy_context().run(...)``) — they do NOT propagate to a plain
``threading.Thread`` started the ordinary way. Callers that need bound context on a
worker thread must start that thread via a copied context; this module does not spawn
threads itself (that is ``backend/concurrency``'s concern).
"""

from collections.abc import Iterator
from contextlib import contextmanager
import contextvars
import logging
import logging.handlers
from pathlib import Path

_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id_var", default=None)
_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id_var", default=None
)

_RUN_LOGGER_NAMESPACE_PREFIX = "run"


def merge_run_context_processor(
    logger: object,  # noqa: ARG001  # part of the structlog-processor call shape
    method_name: str,  # noqa: ARG001  # part of the structlog-processor call shape
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Merge the bound ``run_id``/``correlation_id`` context vars into a record.

    Installed as the first stage of the ``app.*`` processor pipeline (§3, step 1).
    A field already present on ``event_dict`` is never overwritten.
    """
    run_id = _run_id_var.get()
    if run_id is not None and "run_id" not in event_dict:
        event_dict["run_id"] = run_id
    correlation_id = _correlation_id_var.get()
    if correlation_id is not None and "correlation_id" not in event_dict:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def _make_run_file_handler(run_log_file: Path) -> logging.Handler:
    """Build the per-run file handler: UTF-8, append mode, no rotation (§9)."""
    run_log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(run_log_file, mode="a", encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


@contextmanager
def open_run_logger(
    *, run_id: str, correlation_id: str, run_log_file: Path
) -> Iterator[logging.Logger]:
    """Open a run's dedicated logger, bind its context, and close it on exit.

    Binds ``run_id``/``correlation_id`` via context variables for the scope of
    the ``with`` block (propagating to any code running inside a copied
    context on another thread, per ``contextvars.copy_context().run(...)``),
    creates the run's own non-propagating logger writing to ``run_log_file``,
    yields it, and on exit closes the file handler and detaches the logger so
    no further record is associated with this run's context (STORY-004-AC-4).

    The ``run.*`` namespace is never redacted (§7) and never propagates to the
    root logger (`propagate = False`), so it can never reach ``app.log``
    (STORY-004-AC-3).

    Args:
        run_id: The run identifier to bind and to name the logger/file after.
        correlation_id: The correlation identifier to bind for this run.
        run_log_file: The destination file for this run's event stream.

    Yields:
        The run-scoped, ``DEBUG``-level, non-propagating logger.
    """
    run_id_token = _run_id_var.set(run_id)
    correlation_id_token = _correlation_id_var.set(correlation_id)
    logger_name = f"{_RUN_LOGGER_NAMESPACE_PREFIX}.{run_id}"
    run_logger = logging.getLogger(logger_name)
    run_logger.setLevel(logging.DEBUG)
    run_logger.propagate = False
    handler = _make_run_file_handler(run_log_file)
    run_logger.addHandler(handler)
    try:
        yield run_logger
    finally:
        run_logger.removeHandler(handler)
        handler.close()
        _correlation_id_var.reset(correlation_id_token)
        _run_id_var.reset(run_id_token)
