"""Colocated unit tests for ``adapters.file_system_actions`` (STORY-048)."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.adapters.file_system_actions._internal.qt_file_system_actions import (
    QtFileSystemActions,
)
from ollama_llm_bench.backend.errors import OsAdapterError

_INTERNAL = "ollama_llm_bench.adapters.file_system_actions._internal.qt_file_system_actions"


@pytest.mark.parametrize(
    ("platform_identifier", "expected_command_template"),
    [
        ("darwin", ["open", "-R", "{path}"]),
        ("win32", ["explorer", "/select,{path}"]),
        ("linux", ["xdg-open", "{parent}"]),
    ],
)
def test_open_in_file_manager_invokes_reveal_for_existing_path(
    tmp_path: Path,
    mocker: MockerFixture,
    platform_identifier: str,
    expected_command_template: list[str],
) -> None:
    """Proves: STORY-048-AC-4

    Invokes the platform-correct reveal command for an existing FILE path and
    returns without raising (table-driven over macOS/Windows/Linux). Linux has
    no reveal-and-select mechanism, so its expected command targets the file's
    containing folder rather than the file itself.
    """
    # Arrange
    target = tmp_path / "result.csv"
    target.write_text("data")
    run_mock = mocker.patch(f"{_INTERNAL}.subprocess.run")
    actions = QtFileSystemActions(platform_identifier=platform_identifier)
    expected_command = [
        part.format(path=str(target), parent=str(target.parent))
        for part in expected_command_template
    ]
    # Act
    actions.open_in_file_manager(str(target))
    # Assert
    run_mock.assert_called_once_with(expected_command, check=False)


def test_open_in_file_manager_linux_folder_target_passes_folder_unchanged(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Proves: STORY-048-AC-4

    A Linux FOLDER target is passed to xdg-open unchanged -- not its parent --
    distinguishing folder targets from file targets in the Linux fallback.
    """
    # Arrange
    target = tmp_path / "results_folder"
    target.mkdir()
    run_mock = mocker.patch(f"{_INTERNAL}.subprocess.run")
    actions = QtFileSystemActions(platform_identifier="linux")
    # Act
    actions.open_in_file_manager(str(target))
    # Assert
    run_mock.assert_called_once_with(["xdg-open", str(target)], check=False)


def test_open_in_file_manager_raises_for_nonexistent_path(tmp_path: Path) -> None:
    """Proves: STORY-048-AC-5

    A nonexistent path raises OsAdapterError before any subprocess launches.
    """
    # Arrange
    actions = QtFileSystemActions(platform_identifier="linux")
    missing = tmp_path / "does-not-exist.csv"
    # Act / Assert
    with pytest.raises(OsAdapterError):
        actions.open_in_file_manager(str(missing))


def test_integration_failure_raises_os_adapter_error(tmp_path: Path, mocker: MockerFixture) -> None:
    """Proves: STORY-048-AC-5

    A file-manager launch failure raises OsAdapterError chaining the original
    cause, with no raw platform exception text on the message.
    """
    # Arrange
    target = tmp_path / "result.csv"
    target.write_text("data")
    mocker.patch(
        f"{_INTERNAL}.subprocess.run",
        side_effect=FileNotFoundError("xdg-open: command not found, /secret/detail"),
    )
    actions = QtFileSystemActions(platform_identifier="linux")
    # Act / Assert
    with pytest.raises(OsAdapterError) as exc_info:
        actions.open_in_file_manager(str(target))
    assert "/secret/detail" not in exc_info.value.message
    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_run_log_exists_true_when_file_present(tmp_path: Path, mocker: MockerFixture) -> None:
    """Proves: STORY-056 (FileSystemActions extension)

    run_log_exists returns True when the derived log path exists on disk.
    """
    # Arrange
    mocker.patch(
        f"{_INTERNAL}.run_log_path",
        return_value=tmp_path / "run_7_1700000000.log",
    )
    (tmp_path / "run_7_1700000000.log").write_text("log")
    actions = QtFileSystemActions(platform_identifier="linux")
    # Act / Assert
    assert actions.run_log_exists(run_id=7, started_at="2023-11-14T22:13:20+00:00") is True


def test_run_log_exists_false_when_file_absent(tmp_path: Path, mocker: MockerFixture) -> None:
    """Proves: STORY-056 (FileSystemActions extension)

    run_log_exists returns False when the derived log path does not exist.
    """
    # Arrange
    mocker.patch(
        f"{_INTERNAL}.run_log_path",
        return_value=tmp_path / "run_7_1700000000.log",
    )
    actions = QtFileSystemActions(platform_identifier="linux")
    # Act / Assert
    assert actions.run_log_exists(run_id=7, started_at="2023-11-14T22:13:20+00:00") is False


def test_run_log_path_str_returns_derived_path(tmp_path: Path, mocker: MockerFixture) -> None:
    """Proves: STORY-056 (FileSystemActions extension)

    run_log_path_str returns the same derived path as run_log_exists, as a string.
    """
    # Arrange
    expected = tmp_path / "run_7_1700000000.log"
    mocker.patch(f"{_INTERNAL}.run_log_path", return_value=expected)
    actions = QtFileSystemActions(platform_identifier="linux")
    # Act / Assert
    assert actions.run_log_path_str(run_id=7, started_at="2023-11-14T22:13:20+00:00") == str(
        expected
    )
