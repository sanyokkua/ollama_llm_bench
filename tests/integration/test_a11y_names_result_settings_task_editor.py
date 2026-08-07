"""Proves: STORY-099-AC-1, STORY-099-AC-2

Accessible-name floor for the Result, Settings, and Task Editor widgets
(12_Quality_and_NFRs/08_ACCESSIBILITY_FLOOR.md #7-accessible-names, #72).

This is a cross-module integration test -- it constructs three separate top-level
widgets from three different ``ui/*`` feature modules against one shared walker, which
does not belong in any one module's colocated ``tests/`` (07_TESTING_STANDARD.md
layout; mirrors ``test_a11y_names_shell.py``'s and STORY-098's own
``test_a11y_names_benchmark_surfaces.py`` placement for the same reason).

The pinned strings in ``_PINNED_ROWS`` are written out as literals, deliberately --
see ``test_a11y_names_shell.py``'s module docstring for why (copied from the
accessibility registry so the assertion never becomes a tautology against
production).

The walker helpers below (``_INTERACTIVE_TYPES``, ``_COMPOSITE_TYPES``,
``_has_composite_ancestor``, ``_interactive_descendants``) are copy-pasted verbatim
from ``tests/integration/test_a11y_names_benchmark_surfaces.py``, which itself copied
them from ``tests/integration/test_a11y_names_shell.py`` -- this repo's established,
deliberate precedent (no shared ``tests/support/`` helper module exists to import
from instead).
"""

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import Qt
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

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.task_files import FileValidationResult, ValidationSeverity
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.results import make_result_widget
from ollama_llm_bench.ui.results.models import ResultCollaborators
from ollama_llm_bench.ui.results.protocols import ExportFilenameHelper, ResultGateway
from ollama_llm_bench.ui.settings_dialog import SettingsDialogCollaborators, make_settings_dialog
from ollama_llm_bench.ui.settings_dialog.testing import FakeSettingsGateway
from ollama_llm_bench.ui.shared.model_dropdown import ModelFetcher
from ollama_llm_bench.ui.shared.provider_dropdown import ProviderListSource
from ollama_llm_bench.ui.task_editor import TaskEditorCollaborators, make_task_editor_workspace
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway

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

_SEED_TASK_YAML = (
    "schema_version: 1\n"
    "tasks:\n"
    '  - task_id: "t1"\n'
    "    difficulty: medium\n"
    '    question: "What is 2+2?"\n'
    '    golden_answer: "4"\n'
    '    pass_criteria: "answer is correct"\n'
    '    fail_criteria: "answer is incorrect"\n'
    "    required_terms:\n"
    "      exact: []\n"
    "      semantic: []\n"
    "      forbidden: []\n"
)


def _has_composite_ancestor(widget: QWidget) -> bool:
    """Whether `widget` is Qt's own internal part of a composite control.

    Mirrors ``test_a11y_names_shell.py``'s helper of the same name exactly,
    including the ``QAbstractSpinBox`` exclusion.
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


class _AlwaysCleanTaskFileValidator:
    """A minimal ``TaskFileValidator`` fake returning a clean result for any path
    it is asked about (source path or the buffer's internally-computed scratch
    path) -- avoids this test needing to know ``_internal/buffer.py``'s private
    scratch-path convention, which ``tests/integration`` must not import."""

    def validate(self, source_path: str, /) -> FileValidationResult:
        return FileValidationResult(
            source_path=source_path, severity=ValidationSeverity.CLEAN, save_enabled=True
        )


def _build_result_widget(mocker: MockerFixture) -> QWidget:
    """Build a real Result widget over ``mocker.Mock(spec=...)`` collaborators --
    no ``testing.py`` fake exists for ``ResultGateway`` (checked:
    ``ui/results/testing.py`` is absent), so this mocks it per
    ``testing-standard-pyqt``'s mocking discipline, pre-configuring exactly the
    calls ``ResultController.load_initial_state()`` makes synchronously during
    construction. The four tab views (including the Charts nav bar this
    story's AC-2 pins) are constructed unconditionally in ``bind()``, with no
    run selected."""
    gateway = mocker.Mock(spec=ResultGateway)
    gateway.list_runs.return_value = ()
    gateway.get_setting.return_value = None
    provider_source = mocker.Mock(spec=ProviderListSource)
    provider_source.list_enabled.return_value = ()
    return make_result_widget(
        collaborators=ResultCollaborators(
            bus=mocker.Mock(spec=EventBus),
            gateway=gateway,
            native_pickers=FakeNativePickers(),
            clipboard=mocker.Mock(spec=Clipboard),
            file_system_actions=mocker.Mock(spec=FileSystemActions),
            notifications=FakeNotificationService(),
            export_filenames=mocker.Mock(spec=ExportFilenameHelper),
            provider_source=provider_source,
            model_fetcher=mocker.Mock(spec=ModelFetcher),
        )
    )


def _build_settings_dialog_widget(mocker: MockerFixture) -> QWidget:
    """Build a real Settings dialog over ``ui/settings_dialog/testing.py``'s
    ``FakeSettingsGateway``, seeded with one Providers-tab row so the Providers
    table and its row-action delegate are actually mounted (an empty table
    under-covers AC-1 for this surface)."""
    gateway = FakeSettingsGateway()
    gateway.set_providers(
        (
            ProviderConfig(
                provider_id="aaaaaaaa-1111-4111-8111-111111111111",
                name="Ollama Local",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                base_url="http://localhost:11434/v1",
                enabled=True,
            ),
        )
    )
    return make_settings_dialog(
        collaborators=SettingsDialogCollaborators(
            gateway=gateway,
            event_bus=mocker.Mock(spec=EventBus),
            native_pickers=FakeNativePickers(),
            clipboard=mocker.Mock(spec=Clipboard),
            file_system_actions=mocker.Mock(spec=FileSystemActions),
            notifications=FakeNotificationService(),
        )
    )


def _build_task_editor_widget(*, qtbot: QtBot, mocker: MockerFixture, tmp_path: Path) -> QWidget:
    """Build a real Task Editor workspace and open one seeded task file through a
    real user click on the toolbar's Open File button, so the Tasks pane and the
    Field Editor's rows (including the ``question_help_button``/
    ``golden_answer_help_button`` pair this story's AC-2 pins) are actually
    mounted (an empty workspace under-covers AC-1 for this surface)."""
    source_path = tmp_path / "sample_tasks.yaml"
    source_path.write_text(_SEED_TASK_YAML, encoding="utf-8")
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    widget = make_task_editor_workspace(
        bus=mocker.Mock(spec=EventBus),
        collaborators=TaskEditorCollaborators(
            gateway=FakeTaskEditorGateway(),
            task_file_loader=FakeTaskFileLoader(),
            task_file_validator=_AlwaysCleanTaskFileValidator(),
            yaml_formatter=make_yaml_formatter(),
            file_change_watcher=FakeFileChangeWatcher(),
            native_pickers=native_pickers,
            file_system_actions=mocker.Mock(spec=FileSystemActions),
            clipboard=mocker.Mock(spec=Clipboard),
        ),
    )
    qtbot.addWidget(widget)
    open_file_button = cast(
        "QAbstractButton", widget.findChild(QAbstractButton, "task_editor.toolbar.open_file")
    )
    qtbot.mouseClick(open_file_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    return widget


def _result_factory(_qapp: QApplication, mocker: MockerFixture, _tmp_path: Path) -> QWidget:
    return _build_result_widget(mocker)


def _settings_factory(_qapp: QApplication, mocker: MockerFixture, _tmp_path: Path) -> QWidget:
    return _build_settings_dialog_widget(mocker)


def _task_editor_factory(
    _qapp: QApplication, mocker: MockerFixture, tmp_path: Path, *, qtbot: QtBot
) -> QWidget:
    return _build_task_editor_widget(qtbot=qtbot, mocker=mocker, tmp_path=tmp_path)


@pytest.fixture
def result_settings_task_editor_widgets(
    qtbot: QtBot, qapp: QApplication, mocker: MockerFixture, tmp_path: Path
) -> list[QWidget]:
    """Build all three surface widgets (Result, Settings, Task Editor), already
    registered with ``qtbot``.

    Widget construction and ``qtbot`` registration happen in the fixture body
    (where ``for`` loops are allowed), keeping the test body clean per
    .claude/rules/testing.md:69 (no if/for in a test body).
    """
    widgets = [
        _build_result_widget(mocker),
        _build_settings_dialog_widget(mocker),
        _build_task_editor_widget(qtbot=qtbot, mocker=mocker, tmp_path=tmp_path),
    ]
    for widget in widgets:
        qtbot.addWidget(widget)
    return widgets


@pytest.fixture
def surface_widget_factory(
    qtbot: QtBot, qapp: QApplication, mocker: MockerFixture, tmp_path: Path
) -> Callable[[str], QWidget]:
    """Build one named surface widget, already handed to ``qtbot``.

    Bundling ``qtbot``/``qapp``/``mocker``/``tmp_path`` behind one factory
    fixture keeps the parametrized pinned-values test at the coding-style.md
    5-parameter ceiling, mirroring
    ``test_a11y_names_benchmark_surfaces.py``'s own ``surface_widget_factory``.
    """
    factories: dict[str, Callable[[], QWidget]] = {
        "result": lambda: _result_factory(qapp, mocker, tmp_path),
        "settings": lambda: _settings_factory(qapp, mocker, tmp_path),
        "task_editor": lambda: _task_editor_factory(qapp, mocker, tmp_path, qtbot=qtbot),
    }

    def _build(surface: str) -> QWidget:
        widget = factories[surface]()
        qtbot.addWidget(widget)
        return widget

    return _build


def test_every_result_settings_task_editor_control_has_a_nonempty_accessible_name(
    result_settings_task_editor_widgets: list[QWidget],
) -> None:
    """Proves: STORY-099-AC-1

    Every interactive control mounted by the Result, Settings, and Task Editor
    widgets reports a non-empty accessible name, so an assistive technology can
    announce it and a name-based UI test can address it.
    """
    # Arrange
    widgets = result_settings_task_editor_widgets

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
        "result", "chart_prev_button", "Previous chart", "Previous chart", id="result-chart-prev"
    ),
    pytest.param("result", "chart_next_button", "Next chart", "Next chart", id="result-chart-next"),
    pytest.param(
        "result",
        "detach_chart_button",
        "Detach chart",
        "Open the chart in its own window",
        id="result-detach-chart",
    ),
    pytest.param(
        "task_editor",
        "question_help_button",
        "Help: Question",
        "About this field",
        id="task-editor-field-help-question",
    ),
    pytest.param(
        "task_editor",
        "golden_answer_help_button",
        "Help: Golden answer",
        "About this field",
        id="task-editor-field-help-golden-answer",
    ),
    pytest.param(
        "task_editor",
        "validation_summary_button",
        "Validation summary — focus first issue",
        "Click to focus the first task with a warning",
        id="task-editor-validation-summary",
    ),
)


@pytest.mark.parametrize(("surface", "object_name", "accessible_name", "tooltip"), _PINNED_ROWS)
def test_result_settings_task_editor_registry_controls_use_pinned_values(
    surface_widget_factory: Callable[[str], QWidget],
    surface: str,
    object_name: str,
    accessible_name: str,
    tooltip: str,
) -> None:
    """Proves: STORY-099-AC-2

    Each of this story's five registry rows -- the three Result Charts nav/
    detach buttons and the two Task Editor rows (one field-help button
    parametrized over two distinct field keys, plus the validation-summary
    pill) -- reports exactly its pinned objectName/accessible name/tooltip
    triple, no substitute, abbreviated, or generic value.
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
