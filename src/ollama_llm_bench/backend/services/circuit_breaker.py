"""ModelCircuitBreaker — per-model retry reduction for consistently failing inference."""

import logging

logger = logging.getLogger(__name__)

_CLOSED: str = "closed"
_OPEN: str = "open"
_HALF_OPEN: str = "half_open"


class ModelCircuitBreaker:
    """Per-model state machine that reduces inference retries after consecutive timeouts.

    Tracks consecutive full-failure tasks (all retries timed out) and opens the
    circuit after reaching the failure threshold. While open, tasks run with a
    single attempt to avoid wasting time on retries. After probe_interval tasks
    in open state, one probe task gets full retries to test if the model recovered.
    """

    def __init__(self, *, failure_threshold: int, probe_interval: int) -> None:
        self._failure_threshold: int = max(1, failure_threshold)
        self._probe_interval: int = max(1, probe_interval)
        self._state: str = _CLOSED
        self._consecutive_full_failures: int = 0
        self._tasks_in_open_state: int = 0

    @property
    def state(self) -> str:
        """Current circuit state: 'closed', 'open', or 'half_open'."""
        return self._state

    @property
    def is_open(self) -> bool:
        """True when the circuit is not in normal (closed) operation."""
        return self._state != _CLOSED

    def get_effective_retry_count(self, base_retry_count: int) -> int:
        """Return the retry count to use for the next task.

        When OPEN, returns 1 (single attempt) unless the probe interval is
        reached, in which case it transitions to HALF_OPEN and returns the
        full retry count.  CLOSED and HALF_OPEN always return the full count.

        Args:
            base_retry_count: The configured maximum retry count.

        Returns:
            Effective retry count — 1 when open, base_retry_count otherwise.
        """
        if self._state in (_CLOSED, _HALF_OPEN):
            return max(1, base_retry_count)
        # OPEN state: check if probe time
        if self._tasks_in_open_state >= self._probe_interval:
            self._state = _HALF_OPEN
            self._tasks_in_open_state = 0
            logger.info("circuit_breaker_probe_started")
            return max(1, base_retry_count)
        return 1

    def record_success(self) -> None:
        """Record that inference succeeded (no TimeoutError raised).

        Closes the circuit from any state.  A success on a single attempt
        while OPEN is treated as model recovery.
        """
        prev = self._state
        self._state = _CLOSED
        self._consecutive_full_failures = 0
        self._tasks_in_open_state = 0
        if prev != _CLOSED:
            logger.info("circuit_breaker_closed", extra={"prev_state": prev})

    def record_full_failure(self) -> None:
        """Record that all retry attempts timed out (TimeoutError was raised).

        Updates state per the transition rules: increments the failure counter
        from CLOSED, reopens from HALF_OPEN, and counts task in OPEN state.
        """
        if self._state == _CLOSED:
            self._consecutive_full_failures += 1
            if self._consecutive_full_failures >= self._failure_threshold:
                self._state = _OPEN
                self._tasks_in_open_state = 0
                logger.warning(
                    "circuit_breaker_opened",
                    extra={"consecutive_failures": self._consecutive_full_failures},
                )
        elif self._state == _HALF_OPEN:
            self._state = _OPEN
            self._tasks_in_open_state = 0
            logger.warning("circuit_breaker_probe_failed_reopened")
        elif self._state == _OPEN:
            self._tasks_in_open_state += 1
