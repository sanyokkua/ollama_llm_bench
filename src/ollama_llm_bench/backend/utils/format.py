"""Score display formatting helpers."""

from collections.abc import Sequence

_PERCENT = "percent"
_BOTH = "both"


def displayed_score(value: float, fmt: str) -> str:
    """Format a 0.00-1.00 score for display according to the user's chosen format.

    Args:
        value: Score in the range 0.0-1.0.
        fmt: One of "decimal", "percent", or "both". Unknown values fall back to "decimal".

    Returns:
        Human-readable score string.
    """
    decimal_str = f"{value:.2f}"
    percent_str = f"{round(value * 100):.0f}%"
    if fmt == _PERCENT:
        return percent_str
    if fmt == _BOTH:
        return f"{decimal_str} / {percent_str}"
    return decimal_str


def format_progress_label(completed: int, total: int) -> str:
    """Format a progress counter as ``"c / t (pct%)"`` for display.

    Args:
        completed: Number of completed tasks.
        total: Total number of tasks.

    Returns:
        Formatted string such as ``"5 / 10 (50%)"``; ``"0 / 0 (0%)"`` when total is zero.
    """
    if total <= 0:
        return "0 / 0 (0%)"
    pct = min(100, max(0, int(completed / total * 100)))
    return f"{completed} / {total} ({pct}%)"


def format_attempt_durations(durations_ms: Sequence[float | int]) -> str:
    """Format attempt durations as ``"Attempt 1: Xs · Attempt 2: Ys · Total: Zs"``.

    Args:
        durations_ms: List of attempt durations in milliseconds.

    Returns:
        Formatted string joining each attempt with its duration; empty string if the list is empty.
    """
    if not durations_ms:
        return ""
    parts = [f"Attempt {i + 1}: {int(d // 1000)}s" for i, d in enumerate(durations_ms)]
    total_s = int(sum(durations_ms) // 1000)
    return " · ".join(parts) + f" · Total: {total_s}s"
