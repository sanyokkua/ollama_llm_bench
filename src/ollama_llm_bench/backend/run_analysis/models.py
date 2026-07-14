"""DTOs owned by the Run Analysis Service (§2.2)."""

from enum import StrEnum

import msgspec

__all__: list[str] = ["RunAnalysisOutcome", "RunAnalysisResult"]


class RunAnalysisOutcome(StrEnum):
    """The three — and only three — outcomes of one ``generate()`` call (§2.2)."""

    GENERATED = "generated"
    SKIPPED = "skipped"
    FAILED = "failed"


class RunAnalysisResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The result of one ``RunAnalysisService.generate()`` call (§2.2, §3).

    ``run_analysis_markdown`` is non-empty Markdown only when ``outcome`` is
    ``GENERATED``; ``error_message`` is set only when ``outcome`` is ``FAILED``.
    ``is_regeneration`` is ``True`` when the run already had a non-``None``
    ``run_analysis`` at the call's entry — informational only, affects logging.
    """

    outcome: RunAnalysisOutcome
    run_analysis_markdown: str | None = None
    error_message: str | None = None
    is_regeneration: bool = False
