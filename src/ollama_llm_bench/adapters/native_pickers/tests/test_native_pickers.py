"""Colocated unit tests for ``adapters.native_pickers`` (STORY-048)."""

from typing import Any

import pytest

from ollama_llm_bench.adapters.native_pickers import (
    FilePickerOptions,
    FolderPickerOptions,
    SavePickerOptions,
    make_native_pickers,
)
from ollama_llm_bench.backend.errors import OsAdapterError

_SAVE_OPTIONS = SavePickerOptions(title="Save", suggested_name="out.csv")
_OPEN_FILE_OPTIONS = FilePickerOptions(title="Open")
_OPEN_FOLDER_OPTIONS = FolderPickerOptions(title="Open Folder")

_INTERNAL = "ollama_llm_bench.adapters.native_pickers._internal.qt_native_pickers"


@pytest.mark.parametrize(
    ("qt_target", "qt_return", "call", "expected"),
    [
        (
            f"{_INTERNAL}.QFileDialog.getSaveFileName",
            ("", ""),
            lambda pickers: pickers.save_file(_SAVE_OPTIONS),
            None,
        ),
        (
            f"{_INTERNAL}.QFileDialog.getOpenFileName",
            ("", ""),
            lambda pickers: pickers.open_file(_OPEN_FILE_OPTIONS),
            (),
        ),
        (
            f"{_INTERNAL}.QFileDialog.getExistingDirectory",
            "",
            lambda pickers: pickers.open_folder(_OPEN_FOLDER_OPTIONS),
            None,
        ),
    ],
)
def test_cancel_returns_none_or_empty_per_picker(  # noqa: PLR0913
    qtbot: Any, mocker: Any, qt_target: str, qt_return: Any, call: Any, expected: Any
) -> None:
    """Proves: STORY-048-AC-1

    Each picker method returns its cancellation sentinel -- None for
    save_file/open_folder, an empty tuple for open_file -- and never raises.
    """
    # Arrange
    mocker.patch(qt_target, return_value=qt_return)
    pickers = make_native_pickers()
    # Act
    result = call(pickers)
    # Assert
    assert result == expected


@pytest.mark.parametrize(
    ("qt_target", "qt_return", "call", "expected"),
    [
        (
            f"{_INTERNAL}.QFileDialog.getSaveFileName",
            ("/tmp/out.csv", "CSV (*.csv)"),  # noqa: S108
            lambda pickers: pickers.save_file(_SAVE_OPTIONS),
            "/tmp/out.csv",  # noqa: S108
        ),
        (
            f"{_INTERNAL}.QFileDialog.getOpenFileName",
            ("/tmp/in.yaml", "YAML (*.yaml)"),  # noqa: S108
            lambda pickers: pickers.open_file(_OPEN_FILE_OPTIONS),
            ("/tmp/in.yaml",),  # noqa: S108
        ),
        (
            f"{_INTERNAL}.QFileDialog.getExistingDirectory",
            "/tmp/folder",  # noqa: S108
            lambda pickers: pickers.open_folder(_OPEN_FOLDER_OPTIONS),
            "/tmp/folder",  # noqa: S108
        ),
    ],
)
def test_selection_returns_chosen_paths_per_picker(  # noqa: PLR0913
    qtbot: Any, mocker: Any, qt_target: str, qt_return: Any, call: Any, expected: Any
) -> None:
    """Proves: STORY-048-AC-2

    Each picker method returns the user's chosen path(s) unchanged.
    """
    # Arrange
    mocker.patch(qt_target, return_value=qt_return)
    pickers = make_native_pickers()
    # Act
    result = call(pickers)
    # Assert
    assert result == expected


def test_open_file_with_allow_multiple_returns_chosen_paths(qtbot: Any, mocker: Any) -> None:
    """Proves: STORY-048-AC-2

    With ``allow_multiple=True`` and the user selecting multiple files,
    ``open_file`` uses the plural ``getOpenFileNames`` path and returns the
    chosen paths unchanged.
    """
    # Arrange
    mocker.patch(
        f"{_INTERNAL}.QFileDialog.getOpenFileNames",
        return_value=(["/tmp/a.yaml", "/tmp/b.yaml"], "YAML (*.yaml)"),  # noqa: S108
    )
    options = FilePickerOptions(title="Open", allow_multiple=True)
    pickers = make_native_pickers()
    # Act
    result = pickers.open_file(options)
    # Assert
    assert result == ("/tmp/a.yaml", "/tmp/b.yaml")  # noqa: S108


@pytest.mark.parametrize(
    ("qt_target", "call"),
    [
        (
            f"{_INTERNAL}.QFileDialog.getSaveFileName",
            lambda pickers: pickers.save_file(_SAVE_OPTIONS),
        ),
        (
            f"{_INTERNAL}.QFileDialog.getOpenFileName",
            lambda pickers: pickers.open_file(_OPEN_FILE_OPTIONS),
        ),
        (
            f"{_INTERNAL}.QFileDialog.getExistingDirectory",
            lambda pickers: pickers.open_folder(_OPEN_FOLDER_OPTIONS),
        ),
    ],
)
def test_integration_failure_raises_os_adapter_error(
    qtbot: Any, mocker: Any, qt_target: str, call: Any
) -> None:
    """Proves: STORY-048-AC-5

    A dialog-subsystem failure raises OsAdapterError chaining the original
    cause, with no raw platform exception text on the message.
    """
    # Arrange
    mocker.patch(qt_target, side_effect=RuntimeError("dialog service crashed: /secret/detail"))
    pickers = make_native_pickers()
    # Act / Assert
    with pytest.raises(OsAdapterError) as exc_info:
        call(pickers)
    assert "/secret/detail" not in exc_info.value.message
    assert isinstance(exc_info.value.__cause__, RuntimeError)
