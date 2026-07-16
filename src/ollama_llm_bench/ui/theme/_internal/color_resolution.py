"""The generic role -> value accessor for ColorTokens (08-D §2)."""

from ollama_llm_bench.ui.theme.models import ThemeTokens


def resolve_color_value(tokens: ThemeTokens, role: str) -> str:
    """Resolve a dotted/dashed colour role name (e.g. "bg.context-strip") to its value."""
    attr = role.replace(".", "_").replace("-", "_")
    return getattr(tokens.colors, attr)  # type: ignore[no-any-return]
