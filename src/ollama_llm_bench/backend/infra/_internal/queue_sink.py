"""A non-blocking, bounded-queue-plus-writer-thread sink for the ``app.*`` stream.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/06_LOGGING_STANDARD.md``
§3 (Logging Configuration) — "application-stream records are placed on a bounded
in-memory queue, and a single background thread drains that queue to the rotating
file. The GUI event loop never performs file I/O for logging."

This is the one sanctioned standalone background thread this module owns (distinct
from the dispatcher thread owned by ``backend/concurrency``/the composition root):
a small, dedicated log-writer thread with no cancellation semantics of its own — it is
started once by ``configure_logging`` and stopped by flushing+joining at process exit
via the standard-library ``logging.handlers.QueueListener`` machinery, which already
implements this exact bounded-queue/drain-thread shape without a hand-rolled thread.
"""

import logging
import logging.handlers
import queue
from typing import Final

_QUEUE_MAX_SIZE: Final[int] = 10_000


def build_queue_handler_and_listener(
    *, target_handler: logging.Handler
) -> tuple[logging.Handler, logging.handlers.QueueListener]:
    """Build the bounded queue handler and its draining listener.

    The returned handler is attached to the ``app.*`` logger hierarchy; the
    returned listener owns the single background writer thread that drains the
    queue onto ``target_handler`` (the rotating file handler). The caller is
    responsible for calling ``listener.start()`` and, at shutdown,
    ``listener.stop()``.

    Args:
        target_handler: The real sink (a rotating file handler) the background
            thread writes to.

    Returns:
        A ``(queue_handler, queue_listener)`` pair.
    """
    log_queue: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=_QUEUE_MAX_SIZE)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_listener = logging.handlers.QueueListener(
        log_queue, target_handler, respect_handler_level=True
    )
    return queue_handler, queue_listener
