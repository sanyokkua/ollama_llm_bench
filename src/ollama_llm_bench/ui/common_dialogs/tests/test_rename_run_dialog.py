"""Colocated unit tests for the Rename Run dialog (STORY-056)."""

from typing import TYPE_CHECKING, cast

from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import BenchmarkRun, RunId, RunMode, RunStatus
from ollama_llm_bench.ui.common_dialogs import make_rename_run_dialog
from ollama_llm_bench.ui.common_dialogs._internal.rename_run_select import validate_name

if TYPE_CHECKING:
    from ollama_llm_bench.ui.common_dialogs._internal.rename_run_view import RenameRunDialog

_EXPECTED_RUN_ID = 7


class _FakeRenameRunGateway:
    def __init__(self, *, existing_names: frozenset[str]) -> None:
        self._runs = tuple(
            BenchmarkRun(
                run_id=index + 100,
                run_name=name,
                timestamp="2024-01-01T00:00:00+00:00",
                run_mode=RunMode.TASKS,
                status=RunStatus.COMPLETED,
                total_tasks=1,
                completed_tasks=1,
                total_elapsed_ms=0,
                schema_version=1,
                created_at="2024-01-01T00:00:00+00:00",
            )
            for index, name in enumerate(existing_names)
        )
        self.last_rename: tuple[RunId, str | None] | None = None

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return self._runs

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        self.last_rename = (run_id, name)


def test_rename_commits_name_or_none(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-6

    A valid unique trimmed name commits rename_run(run_id, name); Use
    default commits rename_run(run_id, None).
    """
    # Arrange
    gateway = _FakeRenameRunGateway(existing_names=frozenset({"other run"}))
    dialog = cast(
        "RenameRunDialog",
        make_rename_run_dialog(
            gateway=gateway,
            run_id=7,
            current_custom_name=None,
            computed_default_name="Run 7 — Task Benchmark — 2024-01-01 00:00",
        ),
    )
    qtbot.addWidget(dialog)

    # Act
    dialog.new_name_edit.setText("  My New Name  ")
    dialog._run_validation_now()
    dialog.rename_button.click()

    # Assert
    assert gateway.last_rename == (7, "My New Name")

    # Arrange (Use default path, on a fresh dialog reflecting the just-committed name)
    dialog2 = cast(
        "RenameRunDialog",
        make_rename_run_dialog(
            gateway=gateway,
            run_id=7,
            current_custom_name="My New Name",
            computed_default_name="Run 7 — Task Benchmark — 2024-01-01 00:00",
        ),
    )
    qtbot.addWidget(dialog2)

    # Act
    dialog2.use_default_button.click()
    dialog2.rename_button.click()

    # Assert
    default_intent_rename = gateway.last_rename
    assert default_intent_rename is not None
    assert default_intent_rename[0] == _EXPECTED_RUN_ID
    assert default_intent_rename[1] is None


def test_rename_dialog_constructs_and_shows_with_no_error_logs(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-7

    make_rename_run_dialog constructs and shows with a fake gateway, raises
    no exception, reports isVisible(), and emits no error/critical
    structlog record.
    """
    # Arrange
    gateway = _FakeRenameRunGateway(existing_names=frozenset())

    # Act
    with structlog.testing.capture_logs() as captured:
        dialog = make_rename_run_dialog(
            gateway=gateway,
            run_id=1,
            current_custom_name=None,
            computed_default_name="Run 1 — Task Benchmark — 2024-01-01 00:00",
        )
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)

    # Assert
    assert dialog.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in captured)


def test_validate_name_empty_input_is_default_intent() -> None:
    """Proves: STORY-056-AC-6

    Empty (post-trim) input is DefaultIntent, not Invalid.
    """
    # Act
    result = validate_name("", existing_names=frozenset(), excluded_run_id_name=None)
    # Assert
    assert result.is_default_intent is True
    assert result.is_valid is True


def test_validate_name_rejects_names_over_80_characters() -> None:
    """Proves: STORY-056-AC-6

    V-2: a name over 80 characters fails with the too-long message.
    """
    # Act
    result = validate_name("x" * 81, existing_names=frozenset(), excluded_run_id_name=None)
    # Assert
    assert result.message == "Name is too long (maximum 80 characters)."


def test_validate_name_rejects_control_characters() -> None:
    """Proves: STORY-056-AC-6

    V-3: a control character fails with the disallowed-characters message.
    """
    # Act
    result = validate_name("bad\x01name", existing_names=frozenset(), excluded_run_id_name=None)
    # Assert
    assert result.message == "Name contains characters that are not allowed."


def test_validate_name_rejects_disallowed_punctuation() -> None:
    """Proves: STORY-056-AC-6

    V-4: a character outside the allowed set fails with the
    disallowed-characters message.
    """
    # Act
    result = validate_name("bad*name", existing_names=frozenset(), excluded_run_id_name=None)
    # Assert
    assert result.message == "Name contains characters that are not allowed."


def test_validate_name_rejects_case_insensitive_duplicate() -> None:
    """Proves: STORY-056-AC-6

    V-5: a case-insensitive duplicate against another run's name fails.
    """
    # Act
    result = validate_name(
        "Existing", existing_names=frozenset({"existing"}), excluded_run_id_name=None
    )
    # Assert
    assert result.message == 'A run named "Existing" already exists.'
