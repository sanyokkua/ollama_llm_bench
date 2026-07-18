"""The section-visibility engine: RunMode -> the visible ConfigSection set (STORY-054-AC-2).

Thin wrapper over ``ModeVisibilityPolicy.visible_sections`` -- the widget never
hard-codes an ``if mode == RunMode.X`` branch to decide section presence
(``10_MODE_VISIBILITY_POLICY.md`` §7).
"""

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.mode_visibility import ConfigSection
from ollama_llm_bench.ui.new_benchmark.protocols import ModeVisibilityPolicy

__all__: list[str] = ["visible_section_set"]


def visible_section_set(*, mode: RunMode, policy: ModeVisibilityPolicy) -> frozenset[ConfigSection]:
    """Return every ``ConfigSection`` visible for ``mode``, per ``policy``.

    Args:
        mode: The currently selected run mode.
        policy: The Mode Visibility Policy collaborator (never a hard-coded table).

    Returns:
        The set of sections this mode shows -- driving every section container's
        ``setVisible`` call in ``_internal/view.py``.
    """
    return frozenset(policy.visible_sections(mode))
