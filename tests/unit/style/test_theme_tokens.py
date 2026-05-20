"""Regression tests: font chain and QSS template have no unresolved placeholders."""

import re
import sys
from pathlib import Path

from pytest_mock import MockerFixture

from ollama_llm_bench.ui.style.tokens import _get_font_mono, _get_font_sans, get_tokens

_QSS_DIR = Path(__file__).parents[3] / "src" / "ollama_llm_bench" / "ui" / "style"
_ICONS_DIR = _QSS_DIR / "icons"


def _resolve_qss(theme: str) -> str:
    tokens = {**get_tokens(theme), "icons_dir": str(_ICONS_DIR).replace("\\", "/")}
    template = (_QSS_DIR / f"theme_{theme}.qss").read_text(encoding="utf-8")
    return template.format_map(tokens)


def test_dark_font_mono_has_no_sf_mono() -> None:
    assert "SF Mono" not in get_tokens("dark")["font_mono"]


def test_light_font_mono_has_no_sf_mono() -> None:
    assert "SF Mono" not in get_tokens("light")["font_mono"]


def test_dark_font_sans_has_no_sf_pro_text() -> None:
    assert "SF Pro Text" not in get_tokens("dark")["font_sans"]


def test_light_font_sans_has_no_sf_pro_text() -> None:
    assert "SF Pro Text" not in get_tokens("light")["font_sans"]


def test_dark_tokens_contain_combobox_arrow_tokens() -> None:
    tokens = get_tokens("dark")
    for key in ("bg_hover", "border", "text_secondary", "primary"):
        assert key in tokens, f"Missing token in dark theme: {key}"


def test_light_tokens_contain_combobox_arrow_tokens() -> None:
    tokens = get_tokens("light")
    for key in ("bg_hover", "border", "text_secondary", "primary"):
        assert key in tokens, f"Missing token in light theme: {key}"


def test_shared_tokens_contain_all_font_scale_keys() -> None:
    from ollama_llm_bench.ui.style.tokens import SHARED_TOKENS

    for key in ("font_xs", "font_sm", "font_base", "font_md", "font_lg", "font_xl"):
        assert key in SHARED_TOKENS, f"Missing font token in SHARED_TOKENS: {key}"


def test_font_scale_tokens_are_present_in_dark_theme() -> None:
    tokens = get_tokens("dark")
    for key in ("font_xs", "font_sm", "font_base", "font_md", "font_lg", "font_xl"):
        assert key in tokens, f"Missing font token in dark theme: {key}"


def test_font_scale_tokens_are_present_in_light_theme() -> None:
    tokens = get_tokens("light")
    for key in ("font_xs", "font_sm", "font_base", "font_md", "font_lg", "font_xl"):
        assert key in tokens, f"Missing font token in light theme: {key}"


def test_dark_qss_has_no_unresolved_placeholders() -> None:
    stylesheet = _resolve_qss("dark")
    remaining = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", stylesheet)
    assert remaining == [], f"Unresolved tokens in theme_dark.qss: {remaining}"


def test_light_qss_has_no_unresolved_placeholders() -> None:
    stylesheet = _resolve_qss("light")
    remaining = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", stylesheet)
    assert remaining == [], f"Unresolved tokens in theme_light.qss: {remaining}"


class TestOsAwareFonts:
    def test_mono_darwin_leads_with_menlo(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "darwin")
        assert _get_font_mono().startswith('"Menlo"')

    def test_mono_win32_leads_with_cascadia(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "win32")
        assert _get_font_mono().startswith('"Cascadia Mono"')

    def test_mono_linux_leads_with_ubuntu_mono(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "linux")
        assert _get_font_mono().startswith('"Ubuntu Mono"')

    def test_sans_darwin_leads_with_helvetica_neue(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "darwin")
        assert _get_font_sans().startswith('"Helvetica Neue"')

    def test_sans_win32_leads_with_helvetica_neue(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "win32")
        assert _get_font_sans().startswith('"Helvetica Neue"')

    def test_sans_linux_leads_with_ubuntu(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "linux")
        assert _get_font_sans().startswith('"Ubuntu"')

    def test_mono_darwin_excludes_windows_fonts(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "darwin")
        chain = _get_font_mono()
        assert "Cascadia Mono" not in chain
        assert "Consolas" not in chain

    def test_mono_win32_excludes_macos_fonts(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "win32")
        chain = _get_font_mono()
        assert "Menlo" not in chain
        assert "Monaco" not in chain

    def test_mono_ends_with_courier_new(self, mocker: MockerFixture) -> None:
        for platform in ("darwin", "win32", "linux"):
            mocker.patch.object(sys, "platform", platform)
            assert _get_font_mono().endswith('"Courier New"')

    def test_sans_darwin_ends_with_arial(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "darwin")
        assert _get_font_sans().endswith('"Arial"')

    def test_sans_linux_ends_with_liberation_sans(self, mocker: MockerFixture) -> None:
        mocker.patch.object(sys, "platform", "linux")
        assert _get_font_sans().endswith('"Liberation Sans"')


def test_light_qss_has_header_hover_rule() -> None:
    stylesheet = _resolve_qss("light")
    assert "QHeaderView::section:hover" in stylesheet


def test_both_themes_have_horizontal_scrollbar_hover() -> None:
    for theme in ("dark", "light"):
        stylesheet = _resolve_qss(theme)
        assert "QScrollBar::handle:horizontal:hover" in stylesheet, (
            f"theme_{theme}.qss is missing QScrollBar::handle:horizontal:hover"
        )


def test_themes_header_padding_matches() -> None:
    light = _resolve_qss("light")
    dark = _resolve_qss("dark")
    assert "padding: 8px 10px" in light
    assert "padding: 8px 10px" in dark
