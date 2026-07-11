"""Soft-failure classification: an empty response is not an exception (§6.3)."""

__all__: list[str] = ["classify_soft_failure"]


def classify_soft_failure(text: str) -> str | None:
    """Classify an assembled response as a soft failure, or ``None`` if normal.

    A hard failure (raised) and a soft failure (returned in
    ``ChatResponse.error``) are distinct per §6.3 — this only ever returns a
    short classification string placed verbatim on ``ChatResponse.error``; it
    never raises.

    Args:
        text: The fully assembled response text accumulated from the stream.

    Returns:
        ``"empty_response"`` when ``text`` is empty; ``None`` on a normal,
        non-empty completion.
    """
    if not text:
        return "empty_response"
    return None
