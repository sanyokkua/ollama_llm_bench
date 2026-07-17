"""HealthDot: a status dot + text label for provider/embedding health (08-D §6)."""

from typing import override

from PySide6.QtCore import QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ollama_llm_bench.ui.shared._internal.theme_resolution import resolve_active_tokens
from ollama_llm_bench.ui.theme import (
    HealthDisplayState,
    PlatformKind,
    ThemeManager,
    resolve_health_color,
)

_DOT_DIAMETER = 10


class _HealthDotGlyph(QWidget):
    """The painted circle: resolves the active health colour role; pulses while CHECKING."""

    def __init__(
        self,
        *,
        state: HealthDisplayState,
        theme_manager: ThemeManager,
        platform_kind: PlatformKind,
    ) -> None:
        super().__init__()
        self._state = state
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self._opacity = 1.0
        self._pulse_animation: QVariantAnimation | None = None
        self.setFixedSize(_DOT_DIAMETER, _DOT_DIAMETER)
        theme_manager.theme_changed.connect(self._on_theme_changed)
        if state is HealthDisplayState.CHECKING:
            self._start_pulse()

    @property
    def is_pulsing(self) -> bool:
        return self._pulse_animation is not None

    def current_color_hex(self) -> str:
        tokens = resolve_active_tokens(
            theme_manager=self._theme_manager, platform_kind=self._platform_kind
        )
        return resolve_health_color(tokens, self._state)

    def _start_pulse(self) -> None:
        tokens = resolve_active_tokens(
            theme_manager=self._theme_manager, platform_kind=self._platform_kind
        )
        animation = QVariantAnimation(self)
        animation.setDuration(tokens.motion.standard_ms)
        animation.setStartValue(1.0)
        animation.setKeyValueAt(0.5, 0.3)
        animation.setEndValue(1.0)
        animation.setLoopCount(-1)
        animation.valueChanged.connect(self._on_pulse_value_changed)
        animation.start()
        self._pulse_animation = animation

    def _on_pulse_value_changed(self, value: float) -> None:
        self._opacity = value
        self.update()

    def _on_theme_changed(self) -> None:
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:  # Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.current_color_hex())
        color.setAlphaF(self._opacity)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(self.rect()))
        painter.end()


class HealthDotWidget(QWidget):
    """A status dot plus its accompanying text label (08-D §6)."""

    def __init__(
        self,
        *,
        state: HealthDisplayState,
        text: str,
        theme_manager: ThemeManager,
        platform_kind: PlatformKind,
    ) -> None:
        super().__init__()
        self._state = state
        self._glyph = _HealthDotGlyph(
            state=state, theme_manager=theme_manager, platform_kind=platform_kind
        )
        self._label = QLabel(text)
        self.setProperty("healthState", state.value)
        self.setAccessibleName(f"{state.value}: {text}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._glyph)
        layout.addWidget(self._label)

    @property
    def state(self) -> HealthDisplayState:
        return self._state

    @property
    def text_label(self) -> str:
        return self._label.text()

    @property
    def is_pulsing(self) -> bool:
        return self._glyph.is_pulsing

    def current_color_hex(self) -> str:
        return self._glyph.current_color_hex()
