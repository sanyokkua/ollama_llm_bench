"""Export filename composition and the SPEC-064 sanitisation guard.

`05_EXPORT_FORMATS.md` §2.1.
"""

import re
from typing import Final

from ollama_llm_bench.backend.csv_export.models import ExportKind
from ollama_llm_bench.backend.domain import RunId

_DISALLOWED_CHARS_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]")
_REPEATED_UNDERSCORE_PATTERN: Final[re.Pattern[str]] = re.compile(r"_+")
_MAX_NAME_LENGTH: Final[int] = 80
_LEADING_STRIP_CHARS: Final[frozenset[str]] = frozenset({"_", "."})


def sanitise_run_name(*, run_name: str, run_id: RunId) -> str:
    """Sanitise a run name into a path-traversal-safe filename segment (SPEC-064).

    Replaces every character outside ``[A-Za-z0-9._-]`` with ``_``, collapses
    consecutive underscores, strips a trailing underscore run, then loop-strips
    the leading character while it is ``_`` or ``.`` (so the result never begins
    with ``.`` and never becomes ``.``/``..``), and truncates to 80 characters.
    Falls back to ``Run_<run_id>`` when sanitisation yields an empty string.
    """
    replaced = _DISALLOWED_CHARS_PATTERN.sub("_", run_name)
    collapsed = _REPEATED_UNDERSCORE_PATTERN.sub("_", replaced)
    trailing_stripped = collapsed.rstrip("_")
    leading_stripped = trailing_stripped
    while leading_stripped[:1] in _LEADING_STRIP_CHARS:
        leading_stripped = leading_stripped[1:]
    truncated = leading_stripped[:_MAX_NAME_LENGTH]
    return truncated if truncated else f"Run_{run_id}"


def compose_filename(*, run_name: str, run_id: RunId, kind: ExportKind, ext: str) -> str:
    """Compose the canonical ``<sanitised_run_name>_<kind>.<ext>`` filename (§2.1)."""
    effective_name = sanitise_run_name(run_name=run_name, run_id=run_id)
    return f"{effective_name}_{kind.value}.{ext}"
