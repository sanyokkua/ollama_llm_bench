"""Unit tests for sanitize_filename in filename_utils."""

from ollama_llm_bench.backend.utils.filename_utils import sanitize_filename


def test_sanitize_removes_forward_slash() -> None:
    # Arrange
    raw = "a/b"

    # Act
    result = sanitize_filename(raw)

    # Assert
    assert result == "a_b"


def test_sanitize_removes_backslash() -> None:
    # Arrange
    raw = "a\\b"

    # Act
    result = sanitize_filename(raw)

    # Assert
    assert result == "a_b"


def test_sanitize_removes_colon() -> None:
    # Arrange
    raw = "run:1"

    # Act
    result = sanitize_filename(raw)

    # Assert
    assert result == "run_1"


def test_sanitize_removes_all_illegal_chars() -> None:
    # Arrange
    raw = '<>:"/\\|?*'

    # Act
    result = sanitize_filename(raw)

    # Assert
    assert result == "_________"


def test_sanitize_removes_control_chars() -> None:
    # Arrange
    raw = "run\x00name"

    # Act
    result = sanitize_filename(raw)

    # Assert
    assert result == "run_name"


def test_sanitize_preserves_normal_chars() -> None:
    # Arrange
    raw = "run-2024_01_01"

    # Act
    result = sanitize_filename(raw)

    # Assert
    assert result == "run-2024_01_01"


def test_sanitize_empty_string_returns_underscore() -> None:
    # Arrange
    raw = ""

    # Act
    result = sanitize_filename(raw)

    # Assert
    assert result == "_"


def test_sanitize_all_illegal_not_empty() -> None:
    # Arrange
    raw = "???"

    # Act
    result = sanitize_filename(raw)

    # Assert
    assert result == "___"
