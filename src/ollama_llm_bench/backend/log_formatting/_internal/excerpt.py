"""Normal-verbosity excerpt truncation, applied after escaping (§6.4).

Truncation happens **after** escaping so an HTML entity (``&amp;``, ``&lt;``, ``&gt;``,
``&quot;``, ``&#x27;``) is never split mid-entity: the naive character-budget cut point is
pulled back before any entity it would otherwise straddle.
"""

from typing import Final

__all__: list[str] = ["TRUNCATION_BUDGET_CHARS", "truncate_escaped"]

TRUNCATION_BUDGET_CHARS: Final[int] = 200
"""The fixed character budget for a Normal-verbosity excerpt (§6.4, §8: "a fixed
constant of the service"). Applied to the already-escaped text."""

_ELLIPSIS: Final[str] = "…"
_MAX_ENTITY_LENGTH: Final[int] = len("&quot;")  # 6 — the longest entity html.escape emits


def truncate_escaped(escaped_text: str, *, budget: int = TRUNCATION_BUDGET_CHARS) -> str:
    """Truncate already-escaped text to ``budget`` characters with a trailing ellipsis.

    Args:
        escaped_text: HTML-escaped, newline-normalized text.
        budget: The character budget; defaults to ``TRUNCATION_BUDGET_CHARS``.

    Returns:
        ``escaped_text`` unchanged if it is within budget; otherwise the text cut at
        ``budget`` characters (pulled back further if the cut would split an entity)
        plus a trailing ellipsis.
    """
    if len(escaped_text) <= budget:
        return escaped_text
    cut = _safe_cut_point(escaped_text, budget)
    return escaped_text[:cut] + _ELLIPSIS


def _safe_cut_point(escaped_text: str, budget: int) -> int:
    search_start = max(0, budget - _MAX_ENTITY_LENGTH)
    last_ampersand = escaped_text.rfind("&", search_start, budget)
    if last_ampersand == -1:
        return budget
    semicolon_index = escaped_text.find(";", last_ampersand, budget)
    if semicolon_index != -1:
        return budget
    return last_ampersand
