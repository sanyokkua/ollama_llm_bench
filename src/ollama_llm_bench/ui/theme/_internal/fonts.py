"""Per-platform font chains (08-D §7.2) — no QFontDatabase probing (§7.5)."""

from ollama_llm_bench.ui.theme.models import FontChainTokens, PlatformKind

_FONT_CHAINS: dict[PlatformKind, FontChainTokens] = {
    PlatformKind.MACOS: FontChainTokens(
        sans=("Helvetica Neue", "Arial", "sans-serif"),
        mono=("Menlo", "Monaco", "Courier New", "monospace"),
    ),
    PlatformKind.WINDOWS: FontChainTokens(
        sans=("Segoe UI", "Arial", "sans-serif"),
        mono=("Consolas", "Cascadia Mono", "Courier New", "monospace"),
    ),
    PlatformKind.LINUX: FontChainTokens(
        sans=("Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans", "sans-serif"),
        mono=(
            "DejaVu Sans Mono",
            "Ubuntu Mono",
            "Noto Sans Mono",
            "Liberation Mono",
            "monospace",
        ),
    ),
    PlatformKind.UNKNOWN: FontChainTokens(
        sans=(
            "Segoe UI",
            "Helvetica Neue",
            "Cantarell",
            "Ubuntu",
            "Noto Sans",
            "DejaVu Sans",
            "Arial",
            "sans-serif",
        ),
        mono=(
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


def select_font_chain(platform_kind: PlatformKind) -> FontChainTokens:
    """Return the platform-prescribed sans/mono chain (08-D §7.1)."""
    return _FONT_CHAINS[platform_kind]
