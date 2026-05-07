"""BadgeLabel — colored text badge for pipeline stages and eval verdicts."""

from __future__ import annotations

import logging
from typing import Final

from PySide6.QtWidgets import QLabel, QWidget

from ollama_llm_bench.backend.core.models import EvalVerdict, PipelineStage
from ollama_llm_bench.ui.style.style_utils import repolish

logger = logging.getLogger(__name__)

_VERDICT_PROPERTY: Final[str] = "verdict"
_PIPELINE_STAGE_PROPERTY: Final[str] = "pipeline_stage"
_VERDICT_PASS: Final[str] = "pass"
_VERDICT_FAIL: Final[str] = "fail"


class BadgeLabel(QLabel):
    """Colored text badge with three display modes.

    - ``set_stage``: QSS pipeline_stage property for styled pipeline-stage badges.
    - ``set_verdict``: QSS verdict property for PASS/FAIL; plain text for UNKNOWN.
    - ``set_custom``: raw text with caller-supplied background (escape hatch).
    """

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def set_stage(self, stage: PipelineStage) -> None:
        """Display stage name driven by QSS pipeline_stage property."""
        self._clear_verdict_property()
        self.setStyleSheet("")
        self.setText(stage.value)
        self.setProperty(_PIPELINE_STAGE_PROPERTY, stage.name)
        repolish(self)

    def set_verdict(self, verdict: EvalVerdict) -> None:
        """Display verdict using QSS property for PASS/FAIL; plain text for UNKNOWN."""
        self._clear_stage_property()
        if verdict is EvalVerdict.PASS:
            self._apply_verdict_property(_VERDICT_PASS, verdict.value)
        elif verdict is EvalVerdict.FAIL:
            self._apply_verdict_property(_VERDICT_FAIL, verdict.value)
        else:
            self._clear_verdict_property()
            self.setText(verdict.value)

    def set_custom(self, text: str, bg_color: str) -> None:
        """Display arbitrary text with the given hex background color."""
        self._clear_verdict_property()
        self._clear_stage_property()
        self.setText(text)
        self.setStyleSheet(
            f"border-radius: 4px; padding: 2px 8px; font-weight: bold; color: white; background-color: {bg_color};"
        )

    def _apply_verdict_property(self, property_value: str, text: str) -> None:
        self.setStyleSheet("")
        self.setText(text)
        self.setProperty(_VERDICT_PROPERTY, property_value)
        repolish(self)

    def _clear_verdict_property(self) -> None:
        if self.property(_VERDICT_PROPERTY):
            self.setProperty(_VERDICT_PROPERTY, None)
            repolish(self)

    def _clear_stage_property(self) -> None:
        if self.property(_PIPELINE_STAGE_PROPERTY):
            self.setProperty(_PIPELINE_STAGE_PROPERTY, None)
            repolish(self)
