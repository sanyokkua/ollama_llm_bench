"""Module-local font-role resolution for the Field-editor pane (STORY-069).

``TaskEditorCollaborators`` carries no ``ThemeManager`` (STORY-068 design decision --
the Files/Tasks-pane badges are plain text glyphs precisely so no theme collaborator
is needed). ``golden_answer``'s monospace control (field_reference.md §11) is
therefore resolved through Qt's typed ``QFontDatabase.systemFont`` lookup -- a
platform-appropriate fixed-width family with no per-family probing -- rather than by
widening the collaborator bundle for one font role. No widget in this module calls a
``ui.theme`` function directly; this is the module's own narrow lookup seam, matching
every sibling module's own ``theme_lookup.py``.
"""

from PySide6.QtGui import QFont, QFontDatabase

__all__: list[str] = ["monospace_font"]


def monospace_font() -> QFont:
    """Return the platform's fixed-width system font for the ``golden_answer`` control."""
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
