"""HTML utility helpers for backend renderers."""

import html as _html

import markdown as md


def html_escape(text: str) -> str:
    """Escape HTML special characters in text.

    Args:
        text: Plain text string to escape.

    Returns:
        HTML-safe string with ``&``, ``<``, ``>``, ``"``, ``'`` replaced by entities.
    """
    return _html.escape(text)


def plain_to_html_br(text: str) -> str:
    """Escape HTML and replace newlines with ``<br>`` tags.

    Args:
        text: Plain text that may contain newlines.

    Returns:
        HTML-safe string with newlines converted to ``<br>`` tags.
    """
    return _html.escape(text).replace("\n", "<br>")


def markdown_to_html(text: str) -> str:
    """Convert markdown text to HTML.

    Uses the ``fenced_code``, ``tables``, and ``nl2br`` extensions.

    Args:
        text: Markdown-formatted string.

    Returns:
        HTML string rendered from the markdown input.
    """
    return md.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
