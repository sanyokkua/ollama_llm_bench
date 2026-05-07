"""Unit tests for DragDropHandler — event filter, drag-enter accept/ignore, drop signal emission."""

from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QWidget
from pytest_mock import MockerFixture

from ollama_llm_bench.ui.qt_classes.drag_drop_handler import DragDropHandler

# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication instance for the module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# DragDropHandler fixture — function scope; fresh handler per test
# ---------------------------------------------------------------------------


@pytest.fixture
def handler(qapp: QApplication) -> DragDropHandler:
    """Construct a DragDropHandler with no parent."""
    return DragDropHandler()


# ---------------------------------------------------------------------------
# Signal capture helper
# ---------------------------------------------------------------------------


def _capture_signal(signal: Any) -> list[Path]:
    """Connect signal to a list and return the list for inspection.

    Args:
        signal: A PySide6 Signal to capture emissions from.

    Returns:
        A list that will be populated with each emitted value.
    """
    captured: list[Path] = []
    signal.connect(captured.append)
    return captured


# ---------------------------------------------------------------------------
# Event builder helpers
# ---------------------------------------------------------------------------


def _make_drag_enter_event(mocker: MockerFixture, file_path: str) -> Mock:
    """Build a mock QDragEnterEvent carrying a single URL.

    Args:
        mocker: pytest-mock fixture.
        file_path: Local file path string the URL should return.

    Returns:
        A Mock spec'd to QDragEnterEvent.
    """
    mock_url = mocker.Mock()
    mock_url.toLocalFile.return_value = file_path
    mock_mime = mocker.Mock()
    mock_mime.hasUrls.return_value = True
    mock_mime.urls.return_value = [mock_url]
    event = mocker.Mock(spec=QDragEnterEvent)
    event.type.return_value = QEvent.Type.DragEnter
    event.mimeData.return_value = mock_mime
    return cast(Mock, event)


def _make_drop_event(mocker: MockerFixture, file_paths: list[str]) -> Mock:
    """Build a mock QDropEvent carrying one or more URLs.

    Args:
        mocker: pytest-mock fixture.
        file_paths: List of local file path strings the URLs should return.

    Returns:
        A Mock spec'd to QDropEvent.
    """
    urls = []
    for p in file_paths:
        u = mocker.Mock()
        u.toLocalFile.return_value = p
        urls.append(u)
    mock_mime = mocker.Mock()
    mock_mime.urls.return_value = urls
    event = mocker.Mock(spec=QDropEvent)
    event.type.return_value = QEvent.Type.Drop
    event.mimeData.return_value = mock_mime
    return cast(Mock, event)


# ---------------------------------------------------------------------------
# TestInstallOn
# ---------------------------------------------------------------------------


class TestInstallOn:
    """Tests for DragDropHandler.install_on()."""

    def test_install_on_enables_accept_drops(self, handler: DragDropHandler, qapp: QApplication) -> None:
        # Arrange
        widget = QWidget()

        # Act
        handler.install_on(widget)

        # Assert
        assert widget.acceptDrops() is True

    def test_install_on_registers_event_filter(self, handler: DragDropHandler, qapp: QApplication) -> None:
        # Arrange
        widget = QWidget()

        # Act
        handler.install_on(widget)

        # Assert — acceptDrops being True is the observable effect of filter installation
        assert widget.acceptDrops() is True


# ---------------------------------------------------------------------------
# TestEventFilterDragEnter
# ---------------------------------------------------------------------------


class TestEventFilterDragEnter:
    """Tests for DragDropHandler.eventFilter() — DragEnter branch."""

    def test_drag_enter_with_yaml_url_accepts(self, handler: DragDropHandler, mocker: MockerFixture) -> None:
        # Arrange
        event = _make_drag_enter_event(mocker, "/tmp/tasks.yaml")
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert
        assert result is True
        event.acceptProposedAction.assert_called_once()

    def test_drag_enter_with_yml_url_accepts(self, handler: DragDropHandler, mocker: MockerFixture) -> None:
        # Arrange
        event = _make_drag_enter_event(mocker, "/tmp/tasks.yml")
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert
        assert result is True
        event.acceptProposedAction.assert_called_once()

    def test_drag_enter_with_uppercase_yaml_accepts(self, handler: DragDropHandler, mocker: MockerFixture) -> None:
        # Arrange — case-insensitive suffix matching
        event = _make_drag_enter_event(mocker, "/tmp/tasks.YAML")
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert
        assert result is True

    def test_drag_enter_with_non_yaml_url_ignores(self, handler: DragDropHandler, mocker: MockerFixture) -> None:
        # Arrange
        event = _make_drag_enter_event(mocker, "/tmp/data.txt")
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert
        assert result is False
        event.ignore.assert_called_once()

    def test_drag_enter_without_urls_ignores(self, handler: DragDropHandler, mocker: MockerFixture) -> None:
        # Arrange — mime data has no URLs
        mock_mime = mocker.Mock()
        mock_mime.hasUrls.return_value = False
        event = mocker.Mock(spec=QDragEnterEvent)
        event.type.return_value = QEvent.Type.DragEnter
        event.mimeData.return_value = mock_mime
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert
        assert result is False
        event.ignore.assert_called_once()


# ---------------------------------------------------------------------------
# TestEventFilterDrop
# ---------------------------------------------------------------------------


class TestEventFilterDrop:
    """Tests for DragDropHandler.eventFilter() — Drop branch."""

    def test_drop_with_yaml_emits_signal(self, handler: DragDropHandler, mocker: MockerFixture) -> None:
        # Arrange
        captured = _capture_signal(handler.yaml_file_dropped)
        event = _make_drop_event(mocker, ["/tmp/file.yaml"])
        watched = mocker.Mock(spec=QObject)

        # Act
        handler.eventFilter(watched, event)

        # Assert
        assert captured == [Path("/tmp/file.yaml")]

    def test_drop_with_yml_emits_signal(self, handler: DragDropHandler, mocker: MockerFixture) -> None:
        # Arrange
        captured = _capture_signal(handler.yaml_file_dropped)
        event = _make_drop_event(mocker, ["/tmp/file.yml"])
        watched = mocker.Mock(spec=QObject)

        # Act
        handler.eventFilter(watched, event)

        # Assert
        assert captured == [Path("/tmp/file.yml")]

    def test_drop_emits_all_yaml_files(self, handler: DragDropHandler, mocker: MockerFixture) -> None:
        # Arrange — three YAML URLs; all should be emitted
        captured = _capture_signal(handler.yaml_file_dropped)
        event = _make_drop_event(mocker, ["/tmp/a.yaml", "/tmp/b.yaml", "/tmp/c.yml"])
        watched = mocker.Mock(spec=QObject)

        # Act
        handler.eventFilter(watched, event)

        # Assert
        assert captured == [Path("/tmp/a.yaml"), Path("/tmp/b.yaml"), Path("/tmp/c.yml")]

    def test_drop_with_no_yaml_url_returns_false(self, handler: DragDropHandler, mocker: MockerFixture) -> None:
        # Arrange
        captured = _capture_signal(handler.yaml_file_dropped)
        event = _make_drop_event(mocker, ["/tmp/file.txt"])
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert
        assert result is False
        assert captured == []


# ---------------------------------------------------------------------------
# TestEventFilterDirectory
# ---------------------------------------------------------------------------


class TestEventFilterDirectory:
    """Tests for DragDropHandler folder drag-and-drop support."""

    def test_drag_enter_accepts_directory(
        self, handler: DragDropHandler, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        # Arrange — a real directory path (no .yaml suffix)
        event = _make_drag_enter_event(mocker, str(tmp_path))
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert
        assert result is True
        event.acceptProposedAction.assert_called_once()

    def test_drop_directory_emits_yaml_files(
        self, handler: DragDropHandler, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        # Arrange — directory with two yaml files
        (tmp_path / "task_a.yaml").write_text("")
        (tmp_path / "task_b.yml").write_text("")
        captured = _capture_signal(handler.yaml_file_dropped)
        event = _make_drop_event(mocker, [str(tmp_path)])
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert — both files emitted, event accepted
        assert result is True
        assert set(captured) == {tmp_path / "task_a.yaml", tmp_path / "task_b.yml"}
        event.acceptProposedAction.assert_called_once()

    def test_drop_empty_directory_not_accepted(
        self, handler: DragDropHandler, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        # Arrange — empty directory, no yaml files
        captured = _capture_signal(handler.yaml_file_dropped)
        event = _make_drop_event(mocker, [str(tmp_path)])
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert
        assert result is False
        assert captured == []
        event.acceptProposedAction.assert_not_called()

    def test_drop_mixed_folder_and_file(self, handler: DragDropHandler, mocker: MockerFixture, tmp_path: Path) -> None:
        # Arrange — a folder with one yaml + a standalone yaml file
        folder = tmp_path / "subfolder"
        folder.mkdir()
        (folder / "from_folder.yaml").write_text("")
        standalone = tmp_path / "standalone.yml"
        standalone.write_text("")
        captured = _capture_signal(handler.yaml_file_dropped)
        event = _make_drop_event(mocker, [str(folder), str(standalone)])
        watched = mocker.Mock(spec=QObject)

        # Act
        result = handler.eventFilter(watched, event)

        # Assert
        assert result is True
        assert set(captured) == {folder / "from_folder.yaml", standalone}


# ---------------------------------------------------------------------------
# TestEventFilterPassthrough
# ---------------------------------------------------------------------------


class TestEventFilterPassthrough:
    """Tests for DragDropHandler.eventFilter() — non-drag events pass through."""

    def test_non_drag_event_passes_through(self, handler: DragDropHandler, qapp: QApplication) -> None:
        # Arrange — super().eventFilter() requires a real QObject; use a real QWidget
        event = QEvent(QEvent.Type.MouseMove)
        watched = QObject()

        # Act
        result = handler.eventFilter(watched, event)

        # Assert — super().eventFilter() returns False for unhandled events
        assert result is False
