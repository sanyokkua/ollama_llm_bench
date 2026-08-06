"""Accessibility-name conformance for the application shell, the shared modal dialogs,
and the shared visual primitives (STORY-097).

The pinned strings below are written out as literals, deliberately. They are copied
from `docs/v3_specification/12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §7.2 --
importing the production constants instead would make the assertion a tautology that
passes whenever production and spec drift together.
"""

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QLineEdit,
    QTextEdit,
    QWidget,
)
import pytest

from ollama_llm_bench.compose import AppHandle

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

_INTERACTIVE_TYPES: tuple[type[QWidget], ...] = (
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QAbstractSpinBox,
    QAbstractItemView,
)

_COMPOSITE_TYPES: tuple[type[QWidget], ...] = (QComboBox, QAbstractItemView)


def _has_composite_ancestor(widget: QWidget) -> bool:
    """Whether `widget` is Qt's own internal part of a composite control.

    A dropdown's popup list, and a table's column headers and corner button, are
    constructed by Qt itself rather than by application code. They are parts of the
    control the application already named, not controls of their own, so requiring a
    separate name on each would mean announcing filler like "Filter rows popup list"
    and would break every future dropdown or table until boilerplate was added.
    """
    parent = cast("QObject | None", widget.parent())
    while parent is not None:
        if isinstance(parent, _COMPOSITE_TYPES):
            return True
        parent = cast("QObject | None", parent.parent())
    return False


def _interactive_descendants(root: QWidget) -> list[QWidget]:
    """Return every interactive control in `root`'s subtree, `root` included.

    "Interactive" is the set a user can click into or type into. Container widgets,
    plain labels, and custom-painted presentation surfaces are excluded -- the floor
    requires a name on controls, not on decoration. Qt's own internal parts of a
    composite control are excluded too -- see `_has_composite_ancestor`.
    """
    descendants = cast("Iterable[QWidget]", root.findChildren(QWidget))
    found = [
        w
        for w in descendants
        if isinstance(w, _INTERACTIVE_TYPES) and not _has_composite_ancestor(w)
    ]
    if isinstance(root, _INTERACTIVE_TYPES):
        found.append(root)
    return found


_ABOUT = "07_common_dialogs__about"
_ERROR = "07_common_dialogs__error"
_GENERATE = "07_common_dialogs__generate_analysis"

_READINESS_DOT_OBJECT_NAME = "provider_readiness_indicator"
_READINESS_DOT_TOOLTIP_FIRST_LINE = "Provider readiness — click to open Settings / Providers"

# (objectName, accessible name, tooltip)
_SHELL_ROWS: tuple[tuple[str, str, str], ...] = (
    ("settings_menu_button", "Settings", "Open the Settings dialog"),
    (
        "about_menu_button",
        "About",
        "Application information: version, links, data folders",
    ),
    ("workspace_benchmark_button", "Benchmark workspace", "Benchmark workspace"),
    ("workspace_task_editor_button", "Task Editor workspace", "Task Editor workspace"),
    (
        "running_pill_button",
        "Run in progress — open Progress",
        "Switch to the Benchmark workspace and focus the Progress widget",
    ),
)

# (dialog surface key, objectName, accessible name, tooltip)
_DIALOG_ROWS: tuple[tuple[str, str, str, str], ...] = (
    (_ABOUT, "dialog_close_button", "Close dialog", "Close"),
    (_ERROR, "dialog_close_button", "Close dialog", "Close"),
    (
        _ABOUT,
        "open_data_folder_button",
        "Open application data folder",
        "Open the application data folder",
    ),
    (
        _ABOUT,
        "copy_data_folder_path_button",
        "Copy application data folder path",
        "Copy the application data folder path",
    ),
    (
        _GENERATE,
        "gate_busy_indicator",
        "Inference in flight — controls temporarily disabled",
        "An inference is in flight; please wait.",
    ),
)


@pytest.mark.parametrize(
    ("object_name", "accessible_name", "tooltip"),
    _SHELL_ROWS,
    ids=[row[0] for row in _SHELL_ROWS],
)
def test_shell_registry_controls_use_pinned_values(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    object_name: str,
    accessible_name: str,
    tooltip: str,
) -> None:
    """Proves: STORY-097-AC-2

    Each icon-only or ambiguous control the application shell owns reports exactly the
    objectName, accessible name, and tooltip pinned by the accessibility registry -- no
    substitute, abbreviated, or generic value.
    """
    # Arrange
    handle = build_real_app_without_enabled_providers()

    # Act
    control = cast("QWidget | None", handle.window.findChild(QWidget, object_name))

    # Assert
    assert control is not None, f"no control named {object_name!r} is mounted on the shell"
    assert (control.accessibleName(), control.toolTip()) == (accessible_name, tooltip)


@pytest.mark.parametrize(
    ("surface", "object_name", "accessible_name", "tooltip"),
    _DIALOG_ROWS,
    ids=[f"{row[0]}:{row[1]}" for row in _DIALOG_ROWS],
)
def test_dialog_registry_controls_use_pinned_values(
    common_dialogs: dict[str, QDialog],
    surface: str,
    object_name: str,
    accessible_name: str,
    tooltip: str,
) -> None:
    """Proves: STORY-097-AC-2

    Each icon-only or ambiguous control the shared modal dialogs own reports exactly the
    objectName, accessible name, and tooltip pinned by the accessibility registry.
    """
    # Arrange
    root = common_dialogs[surface]

    # Act
    control = cast("QWidget | None", root.findChild(QWidget, object_name))

    # Assert
    assert control is not None, f"no control named {object_name!r} is mounted on {surface}"
    assert (control.accessibleName(), control.toolTip()) == (accessible_name, tooltip)


def test_readiness_dot_tooltip_leads_with_the_pinned_sentence(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
) -> None:
    """Proves: STORY-097-AC-2

    The provider-readiness dot reports the pinned objectName and accessible name, and its
    tooltip's FIRST line is the registry's pinned sentence. Only the first line is pinned:
    the lines beneath it carry the per-provider reachability detail the Main Window
    specification separately requires, which the registry's one sentence does not include.
    """
    # Arrange
    handle = build_real_app_without_enabled_providers()

    # Act
    dot = cast("QWidget | None", handle.window.findChild(QWidget, _READINESS_DOT_OBJECT_NAME))

    # Assert
    assert dot is not None, "no provider-readiness dot is mounted on the shell"
    assert (dot.accessibleName(), dot.toolTip().splitlines()[0]) == (
        "Provider readiness status",
        _READINESS_DOT_TOOLTIP_FIRST_LINE,
    )


_DIALOG_SURFACES: tuple[str, ...] = (
    "07_common_dialogs__about",
    "07_common_dialogs__error",
    "07_common_dialogs__rename_run",
    "07_common_dialogs__run_summary",
    "07_common_dialogs__resume_summary",
    "07_common_dialogs__retry_selection",
    "07_common_dialogs__generate_analysis",
)


def test_every_shell_control_has_a_nonempty_accessible_name(
    common_dialogs: dict[str, QDialog],
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
) -> None:
    """Proves: STORY-097-AC-1

    Every interactive control mounted by the application shell, the seven shared modal
    dialogs, and the shared visual primitives reports a non-empty accessible name, so an
    assistive technology can announce it and a name-based UI test can address it.
    """
    # Arrange
    handle = build_real_app_without_enabled_providers()
    menu_bar = cast("QWidget | None", handle.window.findChild(QWidget, "menu_bar"))
    status_bar = cast("QWidget | None", handle.window.findChild(QWidget, "status_bar"))
    assert menu_bar is not None
    assert status_bar is not None
    surfaces: list[QWidget] = [
        menu_bar,
        status_bar,
        *(common_dialogs[key] for key in _DIALOG_SURFACES),
    ]

    # Act
    unnamed = [
        f"{surface.objectName() or type(surface).__name__} > "
        f"{type(control).__name__}({control.objectName() or '<no objectName>'})"
        for surface in surfaces
        for control in _interactive_descendants(surface)
        if not control.accessibleName()
    ]

    # Assert
    assert unnamed == [], "controls with no accessible name:\n" + "\n".join(unnamed)
