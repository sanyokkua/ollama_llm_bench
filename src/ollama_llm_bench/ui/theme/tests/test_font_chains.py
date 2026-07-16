"""Proves STORY-049-AC-3 (08-D §7)."""

import pytest

from ollama_llm_bench.ui.theme import PlatformKind, make_dark_theme_tokens

_EXPECTED_CHAINS = {
    PlatformKind.MACOS: (
        ("Helvetica Neue", "Arial", "sans-serif"),
        ("Menlo", "Monaco", "Courier New", "monospace"),
    ),
    PlatformKind.WINDOWS: (
        ("Segoe UI", "Arial", "sans-serif"),
        ("Consolas", "Cascadia Mono", "Courier New", "monospace"),
    ),
    PlatformKind.LINUX: (
        ("Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans", "sans-serif"),
        ("DejaVu Sans Mono", "Ubuntu Mono", "Noto Sans Mono", "Liberation Mono", "monospace"),
    ),
    PlatformKind.UNKNOWN: (
        (
            "Segoe UI",
            "Helvetica Neue",
            "Cantarell",
            "Ubuntu",
            "Noto Sans",
            "DejaVu Sans",
            "Arial",
            "sans-serif",
        ),
        (
            "Consolas",
            "Menlo",
            "Cascadia Mono",
            "DejaVu Sans Mono",
            "Ubuntu Mono",
            "Monaco",
            "Courier New",
            "monospace",
        ),
    ),
}


@pytest.mark.parametrize("platform_kind", list(PlatformKind))
def test_font_chain_matches_spec_per_platform(platform_kind: PlatformKind) -> None:
    """Proves: STORY-049-AC-3

    For each PlatformKind, the resolved font.sans and font.mono chains equal the ordered family
    list the 08-D §7.2 table prescribes for that platform.
    """
    tokens = make_dark_theme_tokens(platform_kind=platform_kind)
    expected_sans, expected_mono = _EXPECTED_CHAINS[platform_kind]
    assert tokens.fonts.sans == expected_sans
    assert tokens.fonts.mono == expected_mono
