"""Live theme switching: OS colour-scheme tracking + the switch sequence (08-D §13)."""

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.ui.theme._internal.factory import (
    assemble_dark_theme_tokens,
    assemble_light_theme_tokens,
)
from ollama_llm_bench.ui.theme._internal.palette_builder import render_palette
from ollama_llm_bench.ui.theme._internal.stylesheet_builder import render_stylesheet
from ollama_llm_bench.ui.theme._internal.theme_selection import resolve_active_theme_kind
from ollama_llm_bench.ui.theme.models import (
    ActiveThemeKind,
    OsColorScheme,
    PlatformKind,
    ThemeSetting,
)


def _map_qt_color_scheme(scheme: Qt.ColorScheme) -> OsColorScheme:
    if scheme is Qt.ColorScheme.Dark:
        return OsColorScheme.DARK
    return OsColorScheme.LIGHT  # Light, and Unknown-as-fallback (08-D §13 is silent on Unknown)


class ThemeManager(QObject):
    """Owns the active container and drives the 08-D §13 switch sequence."""

    theme_changed = Signal()

    def __init__(
        self, *, app: QApplication, theme_setting: ThemeSetting, platform_kind: PlatformKind
    ) -> None:
        super().__init__()
        self._app = app
        self._theme_setting = theme_setting
        self._platform_kind = platform_kind
        self._active_kind = self._compute_active_kind()
        self._apply(self._active_kind)
        app.styleHints().colorSchemeChanged.connect(self._on_os_color_scheme_changed)

    @property
    def active_theme_kind(self) -> ActiveThemeKind:
        return self._active_kind

    def set_theme_setting(self, theme_setting: ThemeSetting) -> None:
        self._theme_setting = theme_setting
        self._reapply_if_changed()

    def _on_os_color_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        self._reapply_if_changed()

    def _reapply_if_changed(self) -> None:
        new_kind = self._compute_active_kind()
        if new_kind is self._active_kind:
            return
        self._active_kind = new_kind
        self._apply(new_kind)
        self.theme_changed.emit()

    def _compute_active_kind(self) -> ActiveThemeKind:
        os_scheme = _map_qt_color_scheme(self._app.styleHints().colorScheme())
        return resolve_active_theme_kind(
            theme_setting=self._theme_setting, os_color_scheme=os_scheme
        )

    def _apply(self, kind: ActiveThemeKind) -> None:
        tokens = (
            assemble_dark_theme_tokens(platform_kind=self._platform_kind)
            if kind is ActiveThemeKind.DARK
            else assemble_light_theme_tokens(platform_kind=self._platform_kind)
        )
        self._app.setStyleSheet(render_stylesheet(tokens))
        self._app.setPalette(render_palette(tokens))
