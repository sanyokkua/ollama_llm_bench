"""Shared fixtures and fakes for ``ui/task_editor/tests/`` (STORY-068).

Mirrors ``ui/results/tests/conftest.py``'s in-process synchronous ``EventBus`` test
double (immediate delivery) and ``ui/resume_benchmark/tests/test_controller.py``'s
locally-declared Protocol fakes pattern. Reuses the already-declared cross-module
fakes where they exist (``adapters.native_pickers.testing.FakeNativePickers``,
``backend.task_files.testing.FakeTaskFileLoader``/``FakeTaskFileValidator``, the
real ``backend.yaml_formatter`` -- Form B/C conversion and comment/unknown-key
preservation are that module's own job, so AC-5 exercises it for real rather than
faking it away) and this module's own ``testing.FakeTaskEditorGateway``/
``FakeFileChangeWatcher``. No fake for ``EventBus``/``FileSystemActions`` exists
elsewhere in the codebase (verified by repository grep before writing this file),
so both are declared locally here, exactly as ``ui/results/tests/conftest.py`` and
``ui/resume_benchmark/tests/test_controller.py`` do for their own modules.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.events import Subscription
from ollama_llm_bench.backend.task_files import FileValidationResult, ValidationSeverity
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader, FakeTaskFileValidator
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor._internal.controller import TaskEditorController
from ollama_llm_bench.ui.task_editor._internal.view import TaskEditorView
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway

__all__: list[str] = [
    "FakeEventBus",
    "FakeFileSystemActions",
    "make_bound_task_editor_controller",
    "make_clean_validation_result",
]


class _FakeSubscription:
    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn
        self._cancelled = False

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._cancel_fn()


class FakeEventBus:
    """A synchronous, in-process ``EventBus`` test double (immediate delivery)."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[object], None]]] = {}
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        self._handlers.setdefault(signal_name, []).append(handler)

        def _cancel() -> None:
            self._handlers[signal_name].remove(handler)

        return _FakeSubscription(_cancel)

    def emit(self, signal_name: str, payload: object) -> None:
        self.emitted.append((signal_name, payload))
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)


class FakeFileSystemActions:
    """A minimal ``FileSystemActions`` fake recording every write/reveal call.

    ``write_text_file`` also writes the real file to disk (not just the
    in-memory record) so a caller that immediately reads the path back
    through a real collaborator (e.g. ``TaskEditorController.on_new_file_clicked``
    handing the freshly written path to the real ``YamlFormatter``) sees the
    content, matching the real adapter's contract.
    """

    def __init__(self) -> None:
        self.written_text: dict[str, str] = {}
        self.revealed_paths: list[str] = []

    def open_in_file_manager(self, path: str) -> None:
        self.revealed_paths.append(path)

    def run_log_exists(self, *, run_id: int, started_at: str) -> bool:
        return False

    def run_log_path_str(self, *, run_id: int, started_at: str) -> str:
        return ""

    def write_export_file(self, *, filename: str, content: str) -> str:
        raise NotImplementedError

    def write_text_file(self, *, path: str, content: str) -> None:
        self.written_text[path] = content
        Path(path).write_text(content, encoding="utf-8")

    def write_export_file_bytes(self, *, filename: str, content: bytes) -> str:
        raise NotImplementedError

    def write_binary_file(self, *, path: str, content: bytes) -> None:
        raise NotImplementedError

    def exports_folder_path(self) -> str:
        raise NotImplementedError


def make_clean_validation_result(source_path: str) -> FileValidationResult:
    """Build a clean (no issues) ``FileValidationResult`` for ``source_path``."""
    return FileValidationResult(
        source_path=source_path, severity=ValidationSeverity.CLEAN, save_enabled=True
    )


def make_bound_task_editor_controller(
    *, qtbot: QtBot, collaborators: TaskEditorCollaborators
) -> tuple[TaskEditorController, FakeEventBus]:
    """Build a ``TaskEditorController`` bound to a real ``TaskEditorView`` (never a
    mock -- see ``testing-standard-pyqt``), mirroring ``ui/progress/tests/
    test_controller.py``'s ``_make_bound_controller`` precedent. The caller builds
    ``collaborators`` itself (the dependency-bundle ``msgspec.Struct``) so it keeps
    direct references to whichever individual fakes its scenario needs to inspect
    afterward."""
    bus = FakeEventBus()
    controller = TaskEditorController(collaborators=collaborators, event_bus=bus)
    view = TaskEditorView()
    qtbot.addWidget(view)
    controller.bind(view)
    controller.load_initial_state()
    return controller, bus


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def fake_gateway() -> FakeTaskEditorGateway:
    return FakeTaskEditorGateway()


@pytest.fixture
def fake_file_change_watcher() -> FakeFileChangeWatcher:
    return FakeFileChangeWatcher()


@pytest.fixture
def fake_native_pickers() -> FakeNativePickers:
    return FakeNativePickers()


@pytest.fixture
def fake_task_file_validator() -> FakeTaskFileValidator:
    return FakeTaskFileValidator()


@pytest.fixture
def task_editor_collaborators(
    fake_gateway: FakeTaskEditorGateway,
    fake_file_change_watcher: FakeFileChangeWatcher,
    fake_native_pickers: FakeNativePickers,
    fake_task_file_validator: FakeTaskFileValidator,
) -> TaskEditorCollaborators:
    return TaskEditorCollaborators(
        gateway=fake_gateway,
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=fake_task_file_validator,
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=fake_file_change_watcher,
        native_pickers=fake_native_pickers,
        file_system_actions=FakeFileSystemActions(),
    )
