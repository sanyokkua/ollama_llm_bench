"""The default wall-clock ``Clock`` implementation.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§5 (Clock).
"""

from datetime import UTC, datetime
import time

from ollama_llm_bench.backend.domain.models import Iso8601Utc


class SystemClock:
    """The default, real-time ``Clock`` implementation.

    Satisfies the ``Clock`` Protocol structurally. Synchronous, side-effect-free
    beyond reading the system clock, and safe to call from any thread.
    """

    def now_utc(self) -> Iso8601Utc:
        """Return the current instant as an ISO-8601 UTC string.

        fast-synchronous; callable from any thread. Never raises.

        Returns:
            The current UTC instant, e.g. ``"2026-05-22T14:53:09.123456+00:00"``.
        """
        return datetime.now(UTC).isoformat()

    def monotonic_ms(self) -> int:
        """Return a monotonic millisecond counter for measuring durations.

        fast-synchronous; callable from any thread. Never raises.

        Returns:
            A monotonically non-decreasing millisecond count with no calendar
            meaning; only differences between two calls are meaningful.
        """
        return int(time.monotonic() * 1000)
