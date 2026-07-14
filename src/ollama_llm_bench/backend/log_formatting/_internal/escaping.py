"""HTML escaping and newline normalization for user/model-supplied text (§6.4).

Applied only to values that did not originate inside the application: a model name, a
provider label, a task id, the prompt/response text, an error message, and the judge's
reasoning. The static label text and markup this service itself emits are never escaped.
"""

import html
import re
from typing import Final

__all__: list[str] = ["escape_and_normalize"]

_NEWLINE_RE: Final[re.Pattern[str]] = re.compile(r"\r\n|\r|\n")


def escape_and_normalize(text: str) -> str:
    """Escape HTML special characters, then collapse every newline to one space (§6.4).

    Args:
        text: The raw user-, model-, or provider-supplied text.

    Returns:
        The escaped text (``&``, ``<``, ``>``, ``"``, ``'`` replaced with entities) with
        every ``\\n``/``\\r\\n``/``\\r`` replaced by a single space, so the fragment stays
        one logical line.
    """
    escaped = html.escape(text, quote=True)
    return _NEWLINE_RE.sub(" ", escaped)
