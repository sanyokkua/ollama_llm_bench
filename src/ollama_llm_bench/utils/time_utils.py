import logging
import time
from typing import Final

logger = logging.getLogger(__name__)

# Constants for time calculations (avoid magic numbers while preserving output format)
MILLISECONDS_PER_SECOND: Final[int] = 1000
SECONDS_PER_MINUTE: Final[int] = 60
MINUTES_PER_HOUR: Final[int] = 60
HOURS_PER_DAY: Final[int] = 24

# Derived constants matching original calculation values
MILLISECONDS_PER_HOUR: Final[int] = MILLISECONDS_PER_SECOND * SECONDS_PER_MINUTE * MINUTES_PER_HOUR  # 3_600_000
MILLISECONDS_PER_MINUTE: Final[int] = MILLISECONDS_PER_SECOND * SECONDS_PER_MINUTE  # 60_000


def calculate_elapsed_time(start_time: float, end_time: float) -> tuple[float, float, float, float]:
    """
    Calculate elapsed time components from start and end timestamps.

    Args:
        start_time: Start timestamp in seconds.
        end_time: End timestamp in seconds.

    Returns:
        Tuple of (hours, minutes, seconds, milliseconds) representing the elapsed duration.

    Note:
        Logs warning if end time precedes start time, but still returns negative duration.
    """
    duration_ms = int((end_time - start_time) * MILLISECONDS_PER_SECOND)

    # Log warning for invalid time sequence but maintain original behavior
    if duration_ms < 0:
        logger.warning(
            "End time (%.3f) precedes start time (%.3f) - negative duration will be shown",
            end_time, start_time,
        )

    # Break down into components (preserving original calculation approach)
    hours, rem = divmod(duration_ms, MILLISECONDS_PER_HOUR)
    minutes, rem = divmod(rem, MILLISECONDS_PER_MINUTE)
    seconds, milliseconds = divmod(rem, MILLISECONDS_PER_SECOND)

    return hours, minutes, seconds, milliseconds


def format_elapsed_time(start_time: float, end_time: float) -> str:
    """
    Format elapsed time between two timestamps in human-readable format.

    Args:
        start_time: Start timestamp in seconds.
        end_time: End timestamp in seconds.

    Returns:
        Formatted string showing hours, minutes, seconds, and milliseconds elapsed.
    """
    hours, minutes, seconds, milliseconds = calculate_elapsed_time(start_time, end_time)
    return f"Spent time: {hours} hours, {minutes} minutes, {seconds} seconds, {milliseconds} ms"


def format_elapsed_time_interval(start_time: float, end_time: float) -> str:
    """
    Format a time interval with start time, end time, and elapsed duration.

    Args:
        start_time: Start timestamp in seconds.
        end_time: End timestamp in seconds.

    Returns:
        Formatted string showing start time, end time, and elapsed duration.
    """
    start_str = time.strftime("%H:%M:%S", time.gmtime(start_time))
    end_str = time.strftime("%H:%M:%S", time.gmtime(end_time))

    elapsed = format_elapsed_time(start_time, end_time)

    return f"Start time {start_str}, End time {end_str}. {elapsed}"
