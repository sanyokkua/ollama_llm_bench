"""Score display formatting helpers."""

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
