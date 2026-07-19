"""``StageBadgeWidget``: a six-tone pill rendering ``RunStage``'s text + tone
(``04_Progress_Widget/description.md`` §3.1, ``08_Cross_Cutting/08-L_ui_standardization.md``
§8, STORY-058 AC-1).

Mirrors ``ui/shared/_internal/badge_label.py``'s ``BadgeLabelWidget`` shape without
depending on its narrower five-status ``BadgeStatus`` enum -- the stage badge needs a
distinct six-tone table (``info``/``primary``/``warn``/``success``/``error``/``mute``)
that ``ui/shared``'s ``BadgeStatus`` does not cover (it has no ``primary`` tone).

08-D §3/§4's fixed 30-role colour token set carries a ``.fill`` soft-background
counterpart only for ``success``/``warning``/``error``/``info``/``muted`` -- there is
no ``primary.fill`` role. ``primary.disabled`` (a muted teal in both containers) is
used as the nearest available soft-fill substitute for the ``primary`` tone; this is
a deliberate, narrow substitution using an existing token, not a new one.
"""

from typing import override

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.ui.progress._internal.theme_lookup import resolve_theme_tokens
from ollama_llm_bench.ui.progress.models import RunStage
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, resolve_color

__all__: list[str] = ["StageBadgeWidget", "resolve_stage_color_roles", "resolve_stage_tone"]

_TONE_BY_STAGE: dict[RunStage, str] = {
    RunStage.INITIALIZING: "info",
    RunStage.INFERENCE: "primary",
    RunStage.KEYWORD_CHECK: "warn",
    RunStage.COSINE_CHECK: "warn",
    RunStage.JUDGE_CHECK: "warn",
    RunStage.FINISHING: "primary",
    RunStage.COMPLETED: "success",
    RunStage.FAILED: "error",
    RunStage.STOPPED: "mute",
    RunStage.PAUSED: "mute",
}
_BASE_ROLE_BY_TONE: dict[str, str] = {
    "info": "info.base",
    "primary": "primary.base",
    "warn": "warning.base",
    "success": "success.base",
    "error": "error.base",
    "mute": "muted.base",
}
_FILL_ROLE_BY_TONE: dict[str, str] = {
    "info": "info.fill",
    "primary": "primary.disabled",
    "warn": "warning.fill",
    "success": "success.fill",
    "error": "error.fill",
    "mute": "muted.fill",
}


def resolve_stage_tone(stage: RunStage) -> str:
    """Return the tone name (``info``/``primary``/``warn``/``success``/``error``/``mute``)
    for `stage` (description.md §3.1)."""
    return _TONE_BY_STAGE[stage]


def resolve_stage_color_roles(stage: RunStage) -> tuple[str, str]:
    """Return the ``(base_role, fill_role)`` colour-role names for `stage`'s tone."""
    tone = resolve_stage_tone(stage)
    return _BASE_ROLE_BY_TONE[tone], _FILL_ROLE_BY_TONE[tone]


class StageBadgeWidget(QWidget):
    """A pill-shaped stage badge: soft fill background + base-coloured stage-name text.

    ``theme_manager`` is an optional keyword argument (the established
    ``ui/new_benchmark/_internal/task_files.py`` pattern): when omitted, the badge
    still renders its text with no exception, just with no resolved colour --
    unit tests with no live ``ThemeManager`` stay fully constructible.
    """

    def __init__(
        self,
        *,
        stage: RunStage,
        theme_manager: ThemeManager | None = None,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
    ) -> None:
        super().__init__()
        self.setObjectName("progress.header.stage_badge")
        self._stage = stage
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self.setProperty("stageTone", resolve_stage_tone(stage))
        self.setAccessibleName(f"{stage.value} stage badge")
        self.setToolTip(stage.value)
        if theme_manager is not None:
            theme_manager.theme_changed.connect(self._on_theme_changed)

    @property
    def stage(self) -> RunStage:
        """The stage this badge currently renders."""
        return self._stage

    def set_stage(self, stage: RunStage) -> None:
        """Repaint for a new stage (AC-1); a no-op when `stage` is unchanged."""
        if stage == self._stage:
            return
        self._stage = stage
        self.setProperty("stageTone", resolve_stage_tone(stage))
        self.setAccessibleName(f"{stage.value} stage badge")
        self.setToolTip(stage.value)
        self.update()

    def current_base_color_hex(self) -> str | None:
        """The resolved base (text) colour for the current stage, or `None` with no
        live `ThemeManager`."""
        if self._theme_manager is None:
            return None
        base_role, _fill_role = resolve_stage_color_roles(self._stage)
        tokens = resolve_theme_tokens(
            theme_manager=self._theme_manager, platform_kind=self._platform_kind
        )
        return resolve_color(tokens, base_role)

    def current_fill_color_hex(self) -> str | None:
        """The resolved fill (background) colour for the current stage, or `None`
        with no live `ThemeManager`."""
        if self._theme_manager is None:
            return None
        _base_role, fill_role = resolve_stage_color_roles(self._stage)
        tokens = resolve_theme_tokens(
            theme_manager=self._theme_manager, platform_kind=self._platform_kind
        )
        return resolve_color(tokens, fill_role)

    @override
    def sizeHint(self) -> QSize:  # Qt override signature
        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self._stage.value)
        return QSize(text_width + 24, max(20, metrics.height() + 8))

    def _on_theme_changed(self) -> None:
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:  # Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill_hex = self.current_fill_color_hex()
        if fill_hex is not None:
            painter.setBrush(QColor(fill_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(self.rect()), 3.0, 3.0)
        base_hex = self.current_base_color_hex()
        if base_hex is not None:
            painter.setPen(QColor(base_hex))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._stage.value)
        painter.end()
