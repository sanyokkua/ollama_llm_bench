"""General coverage of top-level shape parsing and whole-file rejection reasons.

Not tied to one acceptance criterion — exercises `10_Domain_and_Data/
04_YAML_TASK_FORMAT.md` §3's Form B/Form C acceptance and the loader/validator
whole-file-rejection paths that STORY-031-AC-5/AC-6's own test cases do not
otherwise reach.
"""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.errors import TaskFileError
from ollama_llm_bench.backend.task_files import make_task_file_loader, make_task_file_validator
from ollama_llm_bench.backend.task_files.models import ValidationSeverity


def test_loader_accepts_form_b_bare_sequence(tmp_path: Path) -> None:
    """A top-level bare sequence (Form B) loads the same as Form A."""
    source_path = tmp_path / "form_b.yaml"
    source_path.write_text("- task_id: bare_one\n  question: What is 1 + 1?\n", encoding="utf-8")

    loader = make_task_file_loader()
    tasks = loader.load(str(source_path))

    assert [task.task_id for task in tasks] == ["bare_one"]


def test_loader_accepts_form_c_single_task_mapping(tmp_path: Path) -> None:
    """A top-level single bare task mapping (Form C) loads as one task."""
    source_path = tmp_path / "form_c.yaml"
    source_path.write_text("task_id: single_task\nquestion: What is 2 + 2?\n", encoding="utf-8")

    loader = make_task_file_loader()
    tasks = loader.load(str(source_path))

    assert [task.task_id for task in tasks] == ["single_task"]


def test_loader_raises_task_file_error_for_schema_version_too_new(tmp_path: Path) -> None:
    """A ``schema_version`` newer than supported is a whole-file rejection."""
    source_path = tmp_path / "too_new.yaml"
    source_path.write_text(
        "schema_version: 2\ntasks:\n  - task_id: x\n    question: Q?\n", encoding="utf-8"
    )

    loader = make_task_file_loader()
    with pytest.raises(TaskFileError):
        loader.load(str(source_path))


def test_loader_raises_task_file_error_for_unparseable_yaml(tmp_path: Path) -> None:
    """YAML that does not parse at all is a whole-file rejection, not a per-task skip."""
    source_path = tmp_path / "broken.yaml"
    source_path.write_text("tasks:\n  - task_id: a\n  bad: [unterminated\n", encoding="utf-8")

    loader = make_task_file_loader()
    with pytest.raises(TaskFileError):
        loader.load(str(source_path))


def test_validator_converts_schema_version_too_new_to_file_level_error(tmp_path: Path) -> None:
    """The validator never raises for a content rejection — it becomes a file-level error."""
    source_path = tmp_path / "too_new.yaml"
    source_path.write_text(
        "schema_version: 2\ntasks:\n  - task_id: x\n    question: Q?\n", encoding="utf-8"
    )

    validator = make_task_file_validator()
    result = validator.validate(str(source_path))

    assert result.severity == ValidationSeverity.ERROR
    assert result.save_enabled is False
    assert result.file_issues


def test_validator_raises_task_file_error_for_os_level_read_failure(tmp_path: Path) -> None:
    """A genuine OS-level read failure is the one case the validator itself raises for."""
    missing_path = tmp_path / "does_not_exist.yaml"

    validator = make_task_file_validator()
    with pytest.raises(TaskFileError):
        validator.validate(str(missing_path))
