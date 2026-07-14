"""HTML escaping — the mandatory safety pipeline (`20_HTML_RENDERING.md` §6.3).

Every value that originates from a domain record, a task file, model output, or a
provider message is routed through `escape_html` immediately before it is
concatenated into a fragment. The only HTML the service emits is the structural
and styling markup its own templates generate; escaping this way structurally
prevents an untrusted value from ever injecting a tag or attribute.
"""

_ESCAPE_TABLE: tuple[tuple[str, str], ...] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)
"""Ordered so `&` is escaped first — otherwise the entities introduced by the
later replacements would themselves be re-escaped."""


def escape_html(text: str) -> str:
    """Escape `&`, `<`, `>`, `"` to their HTML entities (§6.3)."""
    result = text
    for char, entity in _ESCAPE_TABLE:
        result = result.replace(char, entity)
    return result
