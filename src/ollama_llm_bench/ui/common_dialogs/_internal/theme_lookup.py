"""Module-local font-role resolution for ``ui/common_dialogs/`` (STORY-070).

This module carries no ``ThemeManager`` collaborator, so the monospaced role used
by the About dialog's path display (about_dialog.md §5) and the Error dialog's
detail block (error_dialog.md §4) is resolved through Qt's typed
``QFontDatabase.systemFont`` lookup -- a platform-appropriate fixed-width family
with no per-family probing -- rather than by widening every dialog factory's
collaborator bundle for one font role. No widget in this module calls a
``ui.theme`` function directly; this is the module's own narrow lookup seam,
matching every sibling module's own ``theme_lookup.py`` (e.g.
``ui.task_editor._internal.theme_lookup``).
"""

from PySide6.QtGui import QFont, QFontDatabase

__all__: list[str] = ["monospace_font"]


def monospace_font() -> QFont:
    """Return the platform's fixed-width system font for a monospaced role."""
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
