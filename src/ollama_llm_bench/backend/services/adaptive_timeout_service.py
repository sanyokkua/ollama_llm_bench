"""Adaptive per-model timeout service with cross-task memory."""

import logging
import threading
from dataclasses import dataclass, replace

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True, kw_only=True)
class ModelTimeoutState:
    """Carry-over timeout state for one (provider_id, model_name) within a single run."""

    current_good_s: int
    consecutive_max_failures: int = 0
    is_excluded: bool = False


class AdaptiveTimeoutService:
    """Adaptive timeout schedule with per-model memory across tasks.

    Thread-safe via threading.Lock. State lives for exactly one benchmark run
    (create a new instance per run or call reset_for_run()).
    """

    def __init__(
        self,
        *,
        min_s: int,
        max_s: int,
        retry_count: int,
        max_failures_to_exclude: int,
    ) -> None:
        self._min_s = max(1, min_s)
        self._max_s = max(self._min_s, max_s)
        self._retry_count = max(1, retry_count)
        self._max_failures_to_exclude = max(1, max_failures_to_exclude)
        self._lock = threading.Lock()
        self._state: dict[tuple[str, str], ModelTimeoutState] = {}

    def _get_state(self, provider_id: str, model_name: str) -> ModelTimeoutState:
        key = (provider_id, model_name)
        return self._state.get(key, ModelTimeoutState(current_good_s=self._min_s))

    def next_timeout(self, provider_id: str, model_name: str, attempt: int) -> int:
        """Return the timeout in seconds for the given attempt within the current task.

        Uses geometric interpolation from current_good_s to max_s over retry_count steps.
        Attempt 0 always returns current_good_s; last attempt always returns max_s.
        """
        with self._lock:
            state = self._get_state(provider_id, model_name)
        start_s = state.current_good_s
        if self._retry_count <= 1 or start_s >= self._max_s:
            return start_s
        exponent: float = attempt / (self._retry_count - 1)
        ratio: float = self._max_s / start_s
        scaled: float = start_s * (ratio**exponent)
        return max(start_s, min(self._max_s, round(scaled)))

    def record_success(self, provider_id: str, model_name: str, *, successful_timeout_s: int) -> None:
        """Raise current_good_s to successful_timeout_s and reset failure counter."""
        key = (provider_id, model_name)
        with self._lock:
            old = self._get_state(provider_id, model_name)
            new_good = max(old.current_good_s, successful_timeout_s)
            self._state[key] = replace(old, current_good_s=new_good, consecutive_max_failures=0)
        if new_good > old.current_good_s:
            logger.info(
                "adaptive_timeout_promoted",
                extra={
                    "provider": provider_id,
                    "model": model_name,
                    "old_s": old.current_good_s,
                    "new_s": new_good,
                },
            )

    def record_full_failure(self, provider_id: str, model_name: str, *, final_timeout_s: int) -> None:
        """Record a task that exhausted all retries.

        Locks current_good_s at max_s when final_timeout_s >= max_s. If
        consecutive_max_failures reaches max_failures_to_exclude, marks the
        model is_excluded=True.
        """
        key = (provider_id, model_name)
        with self._lock:
            old = self._get_state(provider_id, model_name)
            at_max = final_timeout_s >= self._max_s
            new_consecutive = (old.consecutive_max_failures + 1) if at_max else 0
            new_excluded = new_consecutive >= self._max_failures_to_exclude
            new_good = self._max_s if at_max else old.current_good_s
            new_state = replace(
                old,
                current_good_s=new_good,
                consecutive_max_failures=new_consecutive,
                is_excluded=new_excluded,
            )
            self._state[key] = new_state
        logger.warning(
            "adaptive_timeout_full_failure",
            extra={
                "provider": provider_id,
                "model": model_name,
                "final_timeout_s": final_timeout_s,
                "consecutive_max_failures": new_consecutive,
                "is_excluded": new_excluded,
            },
        )

    def is_excluded(self, provider_id: str, model_name: str) -> bool:
        """Return True if the model has been excluded for the rest of this run."""
        with self._lock:
            return self._get_state(provider_id, model_name).is_excluded

    def reset_for_run(self) -> None:
        """Clear all per-model state. Call before starting a new benchmark run."""
        with self._lock:
            self._state.clear()
