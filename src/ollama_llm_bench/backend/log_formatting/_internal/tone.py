"""``RunLogEventKind`` -> tone class mapping (§6.3).

The tone class string is ``"tone-{tone}"`` (e.g. ``"tone-info"``, ``"tone-success"``) —
this is the concrete CSS-class-name format this service commits to; the future
``ui/theme/`` phase resolves each ``tone-*`` class to a concrete colour per the active
theme (§6.3: "the service emits a tone name; the theme resolves it to a colour").
"""

from typing import Final

from ollama_llm_bench.backend.domain import RunLogEventKind

__all__: list[str] = ["resolve_tag_label", "resolve_tone", "tone_class"]

_TONE_CLASS_PREFIX: Final[str] = "tone-"

_DEFAULT_TONE: Final[str] = "info"
"""The fallback tone for an unrecognized event kind (§9)."""

_GENERIC_TAG_LABEL: Final[str] = "EVENT"
"""The fallback kind-tag text for an unrecognized event kind (§9)."""

_TONE_BY_KIND: Final[dict[RunLogEventKind, str]] = {
    RunLogEventKind.STAGE: "info",
    RunLogEventKind.SYSTEM: "info",
    RunLogEventKind.PROVIDER_SWITCH: "info",
    RunLogEventKind.MODEL_SWITCH: "info",
    RunLogEventKind.TASK_START: "primary",
    RunLogEventKind.DONE: "success",
    RunLogEventKind.FINISHED: "success",
    RunLogEventKind.JUDGE: "warning",
    RunLogEventKind.RETRY: "error",
    RunLogEventKind.FAILED: "error",
    RunLogEventKind.STOPPED: "muted",
}
"""The eleven-kind-to-tone mapping (§6.3)."""


def resolve_tone(kind: RunLogEventKind) -> str:
    """Return the semantic tone name for ``kind``, or ``"info"`` if unrecognized (§9)."""
    return _TONE_BY_KIND.get(kind, _DEFAULT_TONE)


def resolve_tag_label(kind: RunLogEventKind) -> str:
    """Return the kind-tag text for ``kind``, or a generic tag if unrecognized (§9)."""
    if kind in _TONE_BY_KIND:
        return kind.value.upper()
    return _GENERIC_TAG_LABEL


def tone_class(tone: str) -> str:
    """Return the CSS class name for a tone name, e.g. ``"info"`` -> ``"tone-info"``."""
    return f"{_TONE_CLASS_PREFIX}{tone}"
