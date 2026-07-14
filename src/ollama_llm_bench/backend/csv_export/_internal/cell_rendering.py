"""Common cell-value render pipeline (`19_TABLE_SERIALIZATION.md` §6.1).

Every function here performs the *render* step only: it converts a typed value to
its display text. Format-specific escaping (RFC 4180 or Markdown pipe/`<br>`) is
applied afterward by ``csv_writer.py`` / ``markdown_writer.py``. No function in this
module redacts — cell content is written verbatim (§6.5).
"""


def render_optional_str(value: str | None) -> str:
    """Render an optional free-text field; ``None`` becomes the empty string."""
    return value if value is not None else ""


def render_count(value: int | None) -> str:
    """Render an integer count field as plain base-10 text; ``None`` becomes empty."""
    return str(value) if value is not None else ""


def render_seconds(value: float | None) -> str:
    """Render a duration already expressed in seconds, 3 decimal places."""
    return f"{value:.3f}" if value is not None else ""


def render_duration_ms_as_seconds(value_ms: int | None) -> str:
    """Render a millisecond duration as seconds, 3 decimal places (§6.1)."""
    return f"{value_ms / 1000:.3f}" if value_ms is not None else ""


def render_ratio(value: float | None) -> str:
    """Render a 0.000-1.000 ratio (pass rate, cosine, judge score), 3 decimals."""
    return f"{value:.3f}" if value is not None else ""


def render_tps(value: float | None, *, estimated: bool) -> str:
    """Render tokens-per-second, 2 decimals; ``~`` prefix when estimated (SPEC-047)."""
    if value is None:
        return ""
    rendered = f"{value:.2f}"
    return f"~{rendered}" if estimated else rendered
