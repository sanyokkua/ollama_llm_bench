"""Unit tests for LogFileWriter service."""

import re
from pathlib import Path

from ollama_llm_bench.backend.core.models import LogEntryType
from ollama_llm_bench.backend.services.log_file_writer import LogFileWriter


def test_write_entry_creates_log_directory_and_file(tmp_path: Path) -> None:
    # Arrange
    writer = LogFileWriter(app_root=tmp_path)

    # Act
    writer.write_entry(1, LogEntryType.SYSTEM, "hello")

    # Assert
    assert (tmp_path / "logs").is_dir()
    log_files = list((tmp_path / "logs").glob("*.log"))
    assert len(log_files) == 1


def test_write_entry_line_format_contains_entry_type_and_content(tmp_path: Path) -> None:
    # Arrange
    writer = LogFileWriter(app_root=tmp_path)

    # Act
    writer.write_entry(1, LogEntryType.SYSTEM, "test content")

    # Assert
    log_files = list((tmp_path / "logs").glob("*.log"))
    content = log_files[0].read_text(encoding="utf-8")
    assert re.search(r"\[\d{2}:\d{2}:\d{2}\] \[system\] test content", content)


def test_get_log_path_returns_path_for_open_run(tmp_path: Path) -> None:
    # Arrange
    writer = LogFileWriter(app_root=tmp_path)
    writer.write_entry(5, LogEntryType.SYSTEM, "init")

    # Act
    path = writer.get_log_path(5)

    # Assert
    assert path.exists()
    assert path.suffix == ".log"


def test_close_removes_handle_and_idempotent(tmp_path: Path) -> None:
    # Arrange
    writer = LogFileWriter(app_root=tmp_path)
    writer.write_entry(1, LogEntryType.SYSTEM, "entry")

    # Act + Assert: first close
    writer.close(1)

    # Second close should not raise
    writer.close(1)


def test_close_nonexistent_run_is_noop(tmp_path: Path) -> None:
    # Arrange
    writer = LogFileWriter(app_root=tmp_path)

    # Act + Assert: no exception raised
    writer.close(999)


def test_multiple_run_ids_produce_separate_files(tmp_path: Path) -> None:
    # Arrange
    writer = LogFileWriter(app_root=tmp_path)

    # Act
    writer.write_entry(1, LogEntryType.TASK_START, "run 1")
    writer.write_entry(2, LogEntryType.TASK_START, "run 2")

    # Assert
    log_files = list((tmp_path / "logs").glob("*.log"))
    assert len(log_files) == 2


def test_write_after_close_reopens_and_succeeds(tmp_path: Path) -> None:
    # Arrange
    writer = LogFileWriter(app_root=tmp_path)
    writer.write_entry(1, LogEntryType.SYSTEM, "first")
    writer.close(1)

    # Act: write again after close — must reopen a new handle without raising
    writer.write_entry(1, LogEntryType.SYSTEM, "second")

    # Assert: content is present in one of the log files
    log_files = sorted((tmp_path / "logs").glob("*.log"))
    all_content = "".join(f.read_text(encoding="utf-8") for f in log_files)
    assert "second" in all_content
