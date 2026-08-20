"""Accessibility-name conformance for the application shell, the shared modal dialogs,
and the shared visual primitives (STORY-097).

The pinned strings below are written out as literals, deliberately. They are copied
from `docs/v3_specification/12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md` §7.2 --
importing the production constants instead would make the assertion a tautology that
passes whenever production and spec drift together.
"""

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, NamedTuple, cast

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

_COMPOSITE_TYPES: tuple[type[QWidget], ...] = (QComboBox, QAbstractItemView, QAbstractSpinBox)


def _has_composite_ancestor(widget: QWidget) -> bool:
    """Whether `widget` is Qt's own internal part of a composite control.

    A dropdown's popup list, a table's column headers and corner button, and a spin
    box's internal `QLineEdit` are constructed by Qt itself rather than by
    application code. They are parts of the control the application already named,
    not controls of their own, so requiring a separate name on each would mean
    announcing filler like "Filter rows popup list" and would break every future
    dropdown, table, or spin box until boilerplate was added.
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

_DIALOG_SURFACES: tuple[str, ...] = (
    "07_common_dialogs__about",
    "07_common_dialogs__error",
    "07_common_dialogs__rename_run",
    "07_common_dialogs__run_summary",
    "07_common_dialogs__resume_summary",
    "07_common_dialogs__retry_selection",
    "07_common_dialogs__generate_analysis",
)

# Every shell control this module reads a pinned triple off, and the two shell surfaces it
# walks. Kept as one tuple so the snapshot below probes exactly the set the tests assert on.
_SHELL_PROBE_NAMES: tuple[str, ...] = (*(row[0] for row in _SHELL_ROWS), _READINESS_DOT_OBJECT_NAME)
_SHELL_WALK_ROOT_NAMES: tuple[str, ...] = ("menu_bar", "status_bar")


class _A11ySnapshot(NamedTuple):
    """Everything this module's assertions read, extracted once and outliving the Qt objects.

    Every field is a plain-data, immutable container of strings. That is what makes it safe
    to cache across tests: no widget, no dialog, no `AppHandle` is retained, so the whole
    application built to produce this snapshot is torn down normally at the end of whichever
    test built it (STORY-117).
    """

    shell_controls: tuple[tuple[str, tuple[str, str, str]], ...]
    dialog_controls: tuple[tuple[tuple[str, str], tuple[str, str, str]], ...]
    mounted_shell_object_names: frozenset[str]
    unnamed: tuple[str, ...]


def _read_control(root: QWidget, object_name: str) -> tuple[str, str, str] | None:
    """The (objectName, accessible name, tooltip) triple of `object_name` under `root`.

    `None` when nothing by that name is mounted -- the caller's own test asserts that the
    control is mounted, so a missing one must survive into the snapshot as an absence
    rather than being silently substituted.
    """
    control = cast("QWidget | None", root.findChild(QWidget, object_name))
    if control is None:
        return None
    return (control.objectName(), control.accessibleName(), control.toolTip())


def _take_snapshot(*, window: QWidget, dialogs: dict[str, QDialog]) -> _A11ySnapshot:
    """Walk the live shell and the seven live dialogs once, returning plain data.

    This is the only place in the module that touches a Qt object. Everything after it
    reads strings.
    """
    shell_controls: dict[str, tuple[str, str, str]] = {}
    for object_name in _SHELL_PROBE_NAMES:
        triple = _read_control(window, object_name)
        if triple is not None:
            shell_controls[object_name] = triple

    dialog_controls: dict[tuple[str, str], tuple[str, str, str]] = {}
    for surface, object_name, _accessible_name, _tooltip in _DIALOG_ROWS:
        triple = _read_control(dialogs[surface], object_name)
        if triple is not None:
            dialog_controls[surface, object_name] = triple

    mounted = set(shell_controls)
    walk_roots: list[QWidget] = []
    for object_name in _SHELL_WALK_ROOT_NAMES:
        root = cast("QWidget | None", window.findChild(QWidget, object_name))
        if root is not None:
            mounted.add(object_name)
            walk_roots.append(root)
    walk_roots.extend(dialogs[key] for key in _DIALOG_SURFACES)

    unnamed = tuple(
        f"{surface.objectName() or type(surface).__name__} > "
        f"{type(control).__name__}({control.objectName() or '<no objectName>'})"
        for surface in walk_roots
        for control in _interactive_descendants(surface)
        if not control.accessibleName()
    )
    return _A11ySnapshot(
        shell_controls=tuple(shell_controls.items()),
        dialog_controls=tuple(dialog_controls.items()),
        mounted_shell_object_names=frozenset(mounted),
        unnamed=unnamed,
    )


def _snapshot_leaves(value: object) -> list[object]:
    """Flatten `value` to its non-container leaves.

    Lets a test assert the shared snapshot is plain data *all the way down* rather than
    only at its top level -- a tuple whose elements were widgets would pass a shallow
    check and still keep a whole widget tree alive between tests.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, tuple | frozenset):
        return [leaf for item in value for leaf in _snapshot_leaves(item)]
    return [value]


@pytest.fixture(scope="module")
def _a11y_snapshot_cache() -> dict[str, _A11ySnapshot | int]:
    """Module-scoped holder for the one snapshot and the two build counters.

    Deliberately holds no Qt object: everything Qt-owned is destroyed at the teardown of
    whichever test built it, so this survives across tests without keeping a widget, a
    non-daemon `pipeline-dispatcher` thread, a sqlite connection, or an instance lock
    alive (STORY-117).
    """
    return {"shell_builds": 0, "dialog_builds": 0}


@pytest.fixture
def a11y_snapshot(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    common_dialogs_factory: Callable[[], dict[str, QDialog]],
    _a11y_snapshot_cache: dict[str, _A11ySnapshot | int],
) -> Callable[[], _A11ySnapshot]:
    """Return an accessor for the module's one snapshot, building it on first call only.

    Every Qt fixture behind this one stays function-scoped, so `qtbot`, `tmp_path`,
    `monkeypatch`, the Qt parity rig and the readiness-modal dismisser all keep working
    untouched -- the costs `tests/e2e/test_icon_only_registry_conformance.py::registry_app`
    pays for a module-scoped Qt fixture are not paid here. The shell and the seven dialogs
    are built inside, and torn down at the end of, whichever test calls the accessor first;
    what outlives that test is the immutable plain-data snapshot alone.

    Both collaborators are themselves factories, so depending on them constructs nothing.
    """

    def accessor() -> _A11ySnapshot:
        cached = _a11y_snapshot_cache.get("snapshot")
        if isinstance(cached, _A11ySnapshot):
            return cached
        shell_builds = cast("int", _a11y_snapshot_cache["shell_builds"])
        dialog_builds = cast("int", _a11y_snapshot_cache["dialog_builds"])
        if shell_builds != 0:
            message = (
                "the module's snapshot was rebuilt, so the module-scoped cache has regressed. "
                "Rebuilding is refused rather than performed: a second `build_app` against the "
                "same app-data root aborts on the single-instance advisory lock and opens a "
                "fatal `ErrorDialog`, which is a `QDialog` the directory's `QMessageBox`-only "
                "dismisser deliberately cannot close -- it `exec()`s and blocks forever, and "
                "this repository configures no pytest-timeout, so performing the rebuild would "
                "hang the whole run instead of failing this test."
            )
            raise AssertionError(message)
        # Dialogs first, then the shell: that is the order the one pre-STORY-117 test which
        # needed both already used, and it keeps `_build_common_dialogs`'s `qtbot.wait(0)`
        # from pumping the live application's event queue.
        dialogs = common_dialogs_factory()
        _a11y_snapshot_cache["dialog_builds"] = dialog_builds + 1
        handle = build_real_app_without_enabled_providers()
        _a11y_snapshot_cache["shell_builds"] = shell_builds + 1
        snapshot = _take_snapshot(window=handle.window, dialogs=dialogs)
        _a11y_snapshot_cache["snapshot"] = snapshot
        return snapshot

    return accessor


@pytest.mark.parametrize(
    ("object_name", "accessible_name", "tooltip"),
    _SHELL_ROWS,
    ids=[row[0] for row in _SHELL_ROWS],
)
def test_shell_registry_controls_use_pinned_values(
    a11y_snapshot: Callable[[], _A11ySnapshot],
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
    snapshot = a11y_snapshot()

    # Act
    control = dict(snapshot.shell_controls).get(object_name)

    # Assert
    assert object_name in snapshot.mounted_shell_object_names, (
        f"no control named {object_name!r} is mounted on the shell"
    )
    assert control == (object_name, accessible_name, tooltip)


@pytest.mark.parametrize(
    ("surface", "object_name", "accessible_name", "tooltip"),
    _DIALOG_ROWS,
    ids=[f"{row[0]}:{row[1]}" for row in _DIALOG_ROWS],
)
def test_dialog_registry_controls_use_pinned_values(
    a11y_snapshot: Callable[[], _A11ySnapshot],
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
    snapshot = a11y_snapshot()

    # Act
    control = dict(snapshot.dialog_controls).get((surface, object_name))

    # Assert
    assert control is not None, f"no control named {object_name!r} is mounted on {surface}"
    assert control == (object_name, accessible_name, tooltip)


def test_readiness_dot_tooltip_leads_with_the_pinned_sentence(
    a11y_snapshot: Callable[[], _A11ySnapshot],
) -> None:
    """Proves: STORY-097-AC-2

    The provider-readiness dot reports the pinned objectName and accessible name, and its
    tooltip's FIRST line is the registry's pinned sentence. Only the first line is pinned:
    the lines beneath it carry the per-provider reachability detail the Main Window
    specification separately requires, which the registry's one sentence does not include.
    """
    # Arrange
    snapshot = a11y_snapshot()

    # Act
    dot = dict(snapshot.shell_controls).get(_READINESS_DOT_OBJECT_NAME)

    # Assert
    assert dot is not None, "no provider-readiness dot is mounted on the shell"
    assert (dot[0], dot[1], dot[2].splitlines()[0]) == (
        _READINESS_DOT_OBJECT_NAME,
        "Provider readiness status",
        _READINESS_DOT_TOOLTIP_FIRST_LINE,
    )


def test_every_shell_control_has_a_nonempty_accessible_name(
    a11y_snapshot: Callable[[], _A11ySnapshot],
) -> None:
    """Proves: STORY-097-AC-1

    Every interactive control mounted by the application shell, the seven shared modal
    dialogs, and the shared visual primitives reports a non-empty accessible name, so an
    assistive technology can announce it and a name-based UI test can address it.
    """
    # Arrange
    snapshot = a11y_snapshot()
    assert {"menu_bar", "status_bar"} <= snapshot.mounted_shell_object_names

    # Act
    unnamed = list(snapshot.unnamed)

    # Assert
    assert unnamed == [], "controls with no accessible name:\n" + "\n".join(unnamed)


def test_the_shell_and_the_dialogs_are_built_once_for_the_whole_module(
    a11y_snapshot: Callable[[], _A11ySnapshot],
    _a11y_snapshot_cache: dict[str, _A11ySnapshot | int],
) -> None:
    """Proves: STORY-117-AC-1

    One full run of this module builds the application shell exactly once and constructs
    the seven shared modal dialogs exactly once -- 1 shell and 7 dialogs, against the 7 and
    42 this file cost before STORY-117.

    Asserting `== 1` rather than the criterion's `<= 2` is what makes this order-independent:
    whatever position `pytest-randomly` gives this test, a cache that had stopped working
    would leave the counters reading this test's own ordinal position, and it would fail. It
    cannot be fooled by running first either, because the accessor refuses to build a second
    time at all -- see its rebuild guard, which fails whichever test asks for the snapshot
    second rather than hanging the run on a second `build_app`.
    """
    # Arrange
    a11y_snapshot()

    # Act
    counts = (_a11y_snapshot_cache["shell_builds"], _a11y_snapshot_cache["dialog_builds"])

    # Assert
    assert counts == (1, 1)


def test_nothing_shared_between_tests_is_mutable_or_qt_owned(
    a11y_snapshot: Callable[[], _A11ySnapshot],
) -> None:
    """Proves: STORY-117-AC-2

    No test in this module can observe state another test left behind, because the only
    thing shared between them is the snapshot -- and every value in it, all the way down to
    its leaves, is an immutable plain string. Nothing is mutable for one test to change
    under another, and nothing Qt-owned survives the teardown of the test that built it.
    """
    # Arrange
    snapshot = a11y_snapshot()

    # Act
    non_plain = [
        f"{field}: {type(leaf).__name__}"
        for field, value in snapshot._asdict().items()
        for leaf in _snapshot_leaves(value)
        if not isinstance(leaf, str)
    ]

    # Assert
    assert non_plain == [], "shared snapshot retains non-plain-data values:\n" + "\n".join(
        non_plain
    )
