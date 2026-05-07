"""QSS theme loader — reads QSS template, injects design tokens, applies to QApplication."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.ui.style.tokens import get_tokens

logger = logging.getLogger(__name__)

_DEFAULT_THEME: Final[str] = "dark"


class _SafeTokenMap(dict[str, str]):
    """Preserve unrecognised {key} patterns instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def apply_theme(app: QApplication, theme: str = _DEFAULT_THEME) -> None:
    """Load the QSS template for the given theme, inject tokens, and apply to the app.

    Args:
        app: The running QApplication instance.
        theme: Theme name — "dark", "light", or "system". "system" resolves to the OS
               color scheme via colorScheme(). Unknown values fall back to "dark".
    """
    resolved = detect_system_theme() if theme == "system" else theme
    if resolved not in ("dark", "light"):
        resolved = "dark"
    tokens = get_tokens(resolved)
    qss_path = Path(__file__).parent / f"theme_{resolved}.qss"

    try:
        template = qss_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("qss_file_not_found", extra={"path": str(qss_path)})
        return

    icons_path = Path(__file__).parent / "icons"
    tokens = {**tokens, "icons_dir": str(icons_path).replace("\\", "/")}
    stylesheet = template.format_map(_SafeTokenMap(tokens))
    remaining = set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", stylesheet))
    if remaining:
        logger.warning("unresolved_qss_tokens", extra={"missing": sorted(remaining)})
    logger.debug("qss_rendered", extra={"theme": resolved, "length": len(stylesheet)})
    app.setStyleSheet(stylesheet)
    logger.info("theme_applied", extra={"theme": resolved, "requested": theme})


def get_color(theme: str, token_name: str) -> str:
    """Return a hex color value for use in QPainter code (not QSS).

    Args:
        theme: Theme name — "dark" or "light".
        token_name: Token key from the merged token dict.

    Returns:
        Hex color string, e.g. "#14B8A6".

    Raises:
        KeyError: If the token name does not exist in the merged dict.
    """
    return get_tokens(theme)[token_name]


def detect_system_theme() -> str:
    """Detect the current OS color scheme and return "dark" or "light".

    Returns:
        "dark" if the OS is using a dark color scheme, "light" otherwise.
    """
    instance = QApplication.instance()
    if not isinstance(instance, QApplication):
        return _DEFAULT_THEME
    scheme = instance.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Light:
        return "light"
    return "dark"  # Dark or Unknown → dark


def connect_system_theme_listener(callback: Callable[[str], None]) -> None:
    """Connect a callback to OS color scheme changes.

    The callback receives "dark" or "light" when the OS theme changes.

    Args:
        callback: Function accepting a theme string ("dark" or "light").
    """
    instance = QApplication.instance()
    if not isinstance(instance, QApplication):
        return
    instance.styleHints().colorSchemeChanged.connect(
        lambda scheme: callback("light" if scheme == Qt.ColorScheme.Light else "dark")
    )
