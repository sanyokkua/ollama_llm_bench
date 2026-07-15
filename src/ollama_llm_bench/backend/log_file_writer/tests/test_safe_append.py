"""Colocated tests for the atomic-append write primitive — see STORY-037-AC-3."""

from pathlib import Path

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.log_file_writer._internal.safe_append import append_line_safely
from ollama_llm_bench.backend.log_file_writer.models import WriteFailureReason


def test_append_creates_new_file_with_owner_only_permissions(tmp_path: Path) -> None:
    """Proves: STORY-037-AC-4

    A freshly created log file is mode 0600 (owner read/write only), applied at
    creation, not as a follow-up ``chmod``.
    """
    target_path = tmp_path / "sub" / "app.log"

    result = append_line_safely(path=target_path, line="hello")

    assert result.succeeded is True
    assert oct(target_path.stat().st_mode)[-3:] == "600"


def test_append_writes_exactly_one_trailing_newline(tmp_path: Path) -> None:
    """Proves: STORY-037-AC-3

    A successful append adds exactly the given line with one trailing newline —
    no double newline, no missing newline.
    """
    target_path = tmp_path / "app.log"

    append_line_safely(path=target_path, line="first")
    append_line_safely(path=target_path, line="second")

    assert target_path.read_text(encoding="utf-8") == "first\nsecond\n"


def test_directory_creation_failure_reports_typed_outcome(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Proves: STORY-037-AC-3

    A failure creating the parent directory tree is reported as a typed
    ``DIRECTORY_NOT_WRITABLE`` outcome rather than raising.
    """
    target_path = tmp_path / "sub" / "app.log"
    mocker.patch("pathlib.Path.mkdir", side_effect=OSError("simulated permission denied"))

    result = append_line_safely(path=target_path, line="hello")

    assert result.succeeded is False
    assert result.failure_reason == WriteFailureReason.DIRECTORY_NOT_WRITABLE


def test_file_open_failure_reports_typed_outcome(tmp_path: Path, mocker: MockerFixture) -> None:
    """Proves: STORY-037-AC-3

    A failure opening the destination file is reported as a typed
    ``DIRECTORY_NOT_WRITABLE`` outcome rather than raising.
    """
    target_path = tmp_path / "app.log"
    mocker.patch(
        "ollama_llm_bench.backend.log_file_writer._internal.safe_append.os.open",
        side_effect=OSError("simulated open failure"),
    )

    result = append_line_safely(path=target_path, line="hello")

    assert result.succeeded is False
    assert result.failure_reason == WriteFailureReason.DIRECTORY_NOT_WRITABLE


def test_write_failure_leaves_file_byte_for_byte_unchanged(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Proves: STORY-037-AC-3

    A simulated mid-write disk-full failure (EC-FL-9) leaves the target file
    byte-for-byte unchanged from before the call — no partial line — and reports a
    typed ``WRITE_FAILED`` outcome rather than raising.
    """
    target_path = tmp_path / "app.log"
    original_bytes = b"existing line\n"
    target_path.write_bytes(original_bytes)

    mocker.patch(
        "ollama_llm_bench.backend.log_file_writer._internal.safe_append._write_and_fsync",
        side_effect=OSError("simulated disk-full mid-write"),
    )

    result = append_line_safely(path=target_path, line="new line")

    assert result.succeeded is False
    assert result.failure_reason == WriteFailureReason.WRITE_FAILED
    assert target_path.read_bytes() == original_bytes
