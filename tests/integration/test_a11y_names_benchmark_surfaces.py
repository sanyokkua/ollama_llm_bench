"""Proves: STORY-098-AC-1, STORY-098-AC-2

Accessible-name floor for the New Benchmark, Resume, and Progress widgets
(12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md #7-accessible-names, #72).

This is a cross-module integration test -- it constructs three separate top-level
widgets from three different ``ui/*`` feature modules against one shared walker, which
does not belong in any one module's colocated ``tests/`` (07_TESTING_STANDARD.md
layout; mirrors ``test_a11y_names_shell.py``'s own placement for the same reason).

The pinned strings in ``_PINNED_ROWS`` are written out as literals, deliberately --
see ``test_a11y_names_shell.py``'s module docstring for why (copied from the
accessibility registry so the assertion never becomes a tautology against
production).
"""

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QWidget,
)
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.workspace_controller.testing import FakeWorkspaceController
from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.log_formatting import LogFormatter
from ollama_llm_bench.backend.mode_visibility import ConfigSection, visible_sections
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.ui.new_benchmark import NewBenchmarkCollaborators, make_new_benchmark_widget
from ollama_llm_bench.ui.new_benchmark.testing import FakeNewBenchmarkGateway, FakeRunValidator
from ollama_llm_bench.ui.progress import make_progress_widget
from ollama_llm_bench.ui.progress.protocols import ProgressGateway
from ollama_llm_bench.ui.resume_benchmark import (
    ExportFilenameHelper,
    ResumeBenchmarkCollaborators,
    ResumeGateway,
    make_resume_benchmark_widget,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeSetting, make_theme_manager

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

_PLATFORM_KIND = PlatformKind.MACOS


class _RealBackedModeVisibilityPolicy:
    """Wraps the real ``backend.mode_visibility.visible_sections`` -- mirrors the
    same-named class already established in
    ``tests/integration/test_new_benchmark_start.py`` and
    ``ui/new_benchmark/tests/conftest.py``'s ``real_mode_visibility_policy`` fixture.

    A mock here would make ``visible_sections(mode)`` return a non-iterable
    ``Mock``, breaking every section-visibility computation the New Benchmark
    controller performs during construction -- this collaborator's real backing
    function is pure and free of side effects, so wrapping it is safe and mirrors
    established precedent rather than duplicating a mocking risk.
    """

    def visible_sections(self, mode: RunMode) -> tuple[ConfigSection, ...]:
        return visible_sections(mode)


def _has_composite_ancestor(widget: QWidget) -> bool:
    """Whether `widget` is Qt's own internal part of a composite control.

    Mirrors ``test_a11y_names_shell.py``'s helper of the same name exactly,
    including the ``QAbstractSpinBox`` exclusion (this story's Task 1 fix).
    """
    parent = cast("QObject | None", widget.parent())
    while parent is not None:
        if isinstance(parent, _COMPOSITE_TYPES):
            return True
        parent = cast("QObject | None", parent.parent())
    return False


def _interactive_descendants(root: QWidget) -> list[QWidget]:
    """Return every interactive control in `root`'s subtree, `root` included.

    Mirrors ``test_a11y_names_shell.py``'s helper of the same name exactly.
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


def _build_new_benchmark_widget(qapp: QApplication) -> QWidget:
    """Build a real New Benchmark widget over the module's own fakes (STORY-054,
    STORY-055) -- mirrors ``tests/integration/test_new_benchmark_start.py``'s Arrange
    block exactly, rather than inventing a new construction pattern."""
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=_PLATFORM_KIND
    )
    collaborators = NewBenchmarkCollaborators(
        gateway=FakeNewBenchmarkGateway(),
        event_bus=cast("EventBus", _FakeEventBus()),
        task_file_loader=FakeTaskFileLoader(),
        mode_visibility_policy=_RealBackedModeVisibilityPolicy(),
        run_validator=FakeRunValidator(entries=()),
        native_pickers=FakeNativePickers(),
        workspace=FakeWorkspaceController(),
        theme_manager=theme_manager,
        platform_kind=_PLATFORM_KIND,
    )
    return make_new_benchmark_widget(collaborators=collaborators)


def _build_resume_benchmark_widget(mocker: MockerFixture) -> QWidget:
    """Build a real Resume Benchmark widget. No ``testing.py`` fake exists yet for
    ``ResumeGateway`` (checked: ``ui/resume_benchmark/testing.py`` is absent), so this
    mocks the gateway per ``testing.md``'s mocking discipline, pre-configuring exactly
    the calls ``make_resume_benchmark_widget``'s own ``controller.load_initial_rows()``
    makes synchronously during construction (``get_sort_setting``, then ``list_runs``
    via ``_rebuild_all_rows``) so construction itself does not fail before the
    accessible-name walk ever runs."""
    gateway = mocker.Mock(spec=ResumeGateway)
    gateway.get_sort_setting.return_value = ("started", True)
    gateway.list_runs.return_value = ()
    gateway.is_run_active.return_value = False
    gateway.active_run_id.return_value = None
    collaborators = ResumeBenchmarkCollaborators(
        gateway=gateway,
        event_bus=mocker.Mock(spec=EventBus),
        native_pickers=FakeNativePickers(),
        file_system_actions=mocker.Mock(spec=FileSystemActions),
        export_filenames=mocker.Mock(spec=ExportFilenameHelper),
    )
    return make_resume_benchmark_widget(collaborators=collaborators)


def _build_progress_widget(mocker: MockerFixture) -> QWidget:
    """Build a real Progress widget. ``make_progress_widget``'s own
    ``controller.bind()`` only subscribes to the event bus and pushes the empty
    initial header (verified against ``_internal/controller.py``); the one gateway
    method invoked eagerly during construction is ``LogController.__init__``'s three
    ``get_setting`` reads (max lines/verbosity/auto-scroll), all of which tolerate
    ``None`` and fall back to their documented defaults."""
    gateway = mocker.Mock(spec=ProgressGateway)
    gateway.get_setting.return_value = None
    gateway.run_log_write_failed.return_value = False
    return make_progress_widget(
        bus=mocker.Mock(spec=EventBus),
        gateway=gateway,
        log_formatter=mocker.Mock(spec=LogFormatter),
    )


class _FakeSubscription:
    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn

    def cancel(self) -> None:
        self._cancel_fn()


class _FakeEventBus:
    """A synchronous, in-process ``EventBus`` test double, local to this test module
    -- mirrors the same-named class already established in
    ``tests/integration/test_new_benchmark_start.py``. The New Benchmark widget's
    provider/model dropdowns subscribe to registry-reload signals during construction
    (``ui/shared/provider_dropdown``), which a ``mocker.Mock(spec=EventBus)`` would
    accept structurally but this real, if trivial, in-process bus exercises for real."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[object], None]]] = {}

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> _FakeSubscription:
        self._handlers.setdefault(signal_name, []).append(handler)
        return _FakeSubscription(lambda: self._handlers[signal_name].remove(handler))

    def emit(self, signal_name: str, payload: object) -> None:
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)


def _new_benchmark_factory(qapp: QApplication, _mocker: MockerFixture) -> QWidget:
    return _build_new_benchmark_widget(qapp)


def _resume_factory(_qapp: QApplication, mocker: MockerFixture) -> QWidget:
    return _build_resume_benchmark_widget(mocker)


def _progress_factory(_qapp: QApplication, mocker: MockerFixture) -> QWidget:
    return _build_progress_widget(mocker)


_SURFACE_FACTORIES: dict[str, Callable[[QApplication, MockerFixture], QWidget]] = {
    "new_benchmark": _new_benchmark_factory,
    "resume": _resume_factory,
    "progress": _progress_factory,
}


@pytest.fixture
def surface_widget_factory(
    qtbot: QtBot, qapp: QApplication, mocker: MockerFixture
) -> Callable[[str], QWidget]:
    """Build one named benchmark-surface widget, already handed to ``qtbot``.

    Bundling ``qtbot``/``qapp``/``mocker`` behind one factory fixture keeps
    ``test_benchmark_surface_registry_controls_use_pinned_values`` at the
    coding-style.md 5-parameter ceiling despite needing all three collaborators plus
    the four parametrized pinned-value columns.
    """

    def _build(surface: str) -> QWidget:
        widget = _SURFACE_FACTORIES[surface](qapp, mocker)
        qtbot.addWidget(widget)
        return widget

    return _build


def test_every_benchmark_surface_control_has_a_nonempty_accessible_name(
    qtbot: QtBot, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-098-AC-1

    Every interactive control mounted by the New Benchmark, Resume, and Progress
    widgets reports a non-empty accessible name, so an assistive technology can
    announce it and a name-based UI test can address it.
    """
    # Arrange
    widgets = [
        _build_new_benchmark_widget(qapp),
        _build_resume_benchmark_widget(mocker),
        _build_progress_widget(mocker),
    ]
    for widget in widgets:
        qtbot.addWidget(widget)

    # Act
    unnamed = [
        f"{type(widget).__name__} > {type(w).__name__}({w.objectName() or '<no objectName>'})"
        for widget in widgets
        for w in _interactive_descendants(widget)
        if not w.accessibleName()
    ]

    # Assert
    assert unnamed == [], "controls with no accessible name:\n" + "\n".join(unnamed)


_PINNED_ROWS = (
    pytest.param(
        "progress", "rename_run_button", "Rename run", "Rename run", id="progress-rename-pencil"
    ),
    pytest.param(
        "new_benchmark",
        "judge_model_refresh_button",
        "Refresh judge model list",
        "Refresh the judge provider's model list",
        id="new-benchmark-judge-refresh",
    ),
)


@pytest.mark.parametrize(("surface", "object_name", "accessible_name", "tooltip"), _PINNED_ROWS)
def test_benchmark_surface_registry_controls_use_pinned_values(
    surface_widget_factory: Callable[[str], QWidget],
    surface: str,
    object_name: str,
    accessible_name: str,
    tooltip: str,
) -> None:
    """Proves: STORY-098-AC-2

    Each icon-only control this story pins by exact value -- the Progress header's
    rename pencil and the New Benchmark Judge section's model-list refresh button --
    reports exactly the objectName, accessible name, and tooltip the accessibility
    registry pins; no substitute, abbreviated, or generic value.
    """
    # Arrange
    widget = surface_widget_factory(surface)

    # Act
    control = cast("QAbstractButton | None", widget.findChild(QAbstractButton, object_name))

    # Assert
    assert control is not None, f"no control named {object_name!r} is mounted on {surface}"
    assert (control.objectName(), control.accessibleName(), control.toolTip()) == (
        object_name,
        accessible_name,
        tooltip,
    )
