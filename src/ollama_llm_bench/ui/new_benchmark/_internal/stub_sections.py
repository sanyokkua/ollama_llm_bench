"""Placeholder section containers for content not yet built (STORY-054 Design Decision 1-2).

Used for ``ConfigSection.INPUT_SIZES``/``OUTPUT_SIZES``/``REPEATS`` (collectively
"Performance Matrix" -- content is a new, not-yet-drafted future story) and
``JUDGE_MODEL_PICKER``/``EMBEDDING_MODEL_INFO``/``ADVANCED_OPTIONS`` (content owned by
STORY-055). Each stub carries a title label only; the section-visibility engine
still drives its ``setVisible`` call like every real section, so STORY-054-AC-2 is
provable end-to-end without inventing unscoped content.
"""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

__all__: list[str] = ["make_stub_section"]


def make_stub_section(title: str) -> QWidget:
    """Build an empty, titled placeholder container for a not-yet-built section.

    Args:
        title: The section's display title (e.g. ``"Performance Matrix"``).

    Returns:
        A ``QWidget`` with a single title label and no interactive content.
    """
    widget = QWidget()
    widget.setObjectName(f"new_benchmark.stub.{title.lower().replace(' ', '_')}")
    layout = QVBoxLayout(widget)
    label = QLabel(title)
    label.setProperty("role", "section-title")
    layout.addWidget(label)
    return widget
