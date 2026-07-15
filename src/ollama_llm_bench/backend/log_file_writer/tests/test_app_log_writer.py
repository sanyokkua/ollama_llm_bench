"""Colocated tests for the rotating application-log writer — see §8.1."""

from pathlib import Path

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.log_file_writer._internal.app_log_writer import AppLogWriterImpl
from ollama_llm_bench.backend.log_file_writer.models import WriteFailureReason


def test_second_small_write_to_an_existing_file_does_not_rotate(tmp_path: Path) -> None:
    """Proves: STORY-037-AC-1

    A second write to an already-existing file that still stays under the size
    trigger appends in place with no rotation — exercising the "file exists but under
    trigger" branch distinct from the "file does not yet exist" first-write case.
    """
    log_file = tmp_path / "app.log"
    writer = AppLogWriterImpl(log_file=log_file, max_bytes=1000, backup_count=5)
    writer.write_line("first line")

    writer.write_line("second line")

    assert log_file.read_text(encoding="utf-8") == "first line\nsecond line\n"
    assert not log_file.with_name("app.log.1").exists()


def test_rotation_failure_reports_typed_outcome_and_leaves_current_file_unwritten(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Proves: STORY-037-AC-3

    A failure during rotation (a rename that raises) is reported as a typed
    ``ROTATION_FAILED`` outcome rather than raising, and the new line is never
    appended.
    """
    log_file = tmp_path / "app.log"
    writer = AppLogWriterImpl(log_file=log_file, max_bytes=20, backup_count=5)
    writer.write_line("first line is long enough")
    mocker.patch(
        "ollama_llm_bench.backend.log_file_writer._internal.app_log_writer.Path.rename",
        side_effect=OSError("simulated rename failure"),
    )

    result = writer.write_line("second line is also long enough")

    assert result.succeeded is False
    assert result.failure_reason == WriteFailureReason.ROTATION_FAILED
    assert log_file.read_text(encoding="utf-8") == "first line is long enough\n"


def test_write_below_trigger_does_not_rotate(tmp_path: Path) -> None:
    """Proves: STORY-037-AC-1

    A write that stays well under the size trigger leaves no ``app.log.1`` backup —
    rotation only occurs once the trigger would be exceeded.
    """
    log_file = tmp_path / "app.log"
    writer = AppLogWriterImpl(log_file=log_file, max_bytes=1000, backup_count=5)

    writer.write_line("small line")

    assert log_file.read_text(encoding="utf-8") == "small line\n"
    assert not log_file.with_name("app.log.1").exists()


def test_write_crossing_trigger_rotates_current_into_backup_one(tmp_path: Path) -> None:
    """Proves: STORY-037-AC-1

    A write that would push the current file past a small test ``max_bytes`` rotates
    first: ``app.log.1`` ends up holding the prior content and ``app.log`` holds only
    the new line.
    """
    log_file = tmp_path / "app.log"
    writer = AppLogWriterImpl(log_file=log_file, max_bytes=20, backup_count=5)
    writer.write_line("first line is long enough")

    writer.write_line("second")

    assert log_file.read_text(encoding="utf-8") == "second\n"
    assert log_file.with_name("app.log.1").read_text(encoding="utf-8") == (
        "first line is long enough\n"
    )


def test_rotating_again_shifts_the_backup_chain_and_drops_the_oldest(tmp_path: Path) -> None:
    """Proves: STORY-037-AC-1

    With backups already occupying ``.1``..``.N``, a further rotation drops the oldest
    backup beyond ``backup_count`` and shifts every remaining backup up by one
    generation.
    """
    log_file = tmp_path / "app.log"
    log_file.with_name("app.log.1").write_text("gen-1\n", encoding="utf-8")
    log_file.with_name("app.log.2").write_text("gen-2\n", encoding="utf-8")
    writer = AppLogWriterImpl(log_file=log_file, max_bytes=20, backup_count=2)
    writer.write_line("current content that is long enough")

    writer.write_line("newest")

    assert log_file.read_text(encoding="utf-8") == "newest\n"
    assert log_file.with_name("app.log.1").read_text(encoding="utf-8") == (
        "current content that is long enough\n"
    )
    assert log_file.with_name("app.log.2").read_text(encoding="utf-8") == "gen-1\n"
    assert not log_file.with_name("app.log.3").exists()
