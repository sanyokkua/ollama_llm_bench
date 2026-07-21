"""Colocated unit tests for the in-memory buffer model (STORY-068).

No Qt involvement -- ``load_buffer`` and the buffer mutators are pure/blocking
functions over a ``TaskBuffer`` and a real ``YamlFormatter``.
"""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor._internal.buffer import (
    add_task,
    duplicate_task,
    filename_stem,
    load_buffer,
    move_task,
    remove_tasks,
    task_count,
    task_ids,
)


@pytest.mark.parametrize(
    ("source_yaml", "expected_task_ids"),
    [
        pytest.param(
            "- task_id: bare_one\n  question: What is 1 + 1?\n  custom_note: keep me\n",
            ("bare_one",),
            id="form_b_bare_sequence",
        ),
        pytest.param(
            "task_id: single_task\nquestion: What is 2 + 2?\ncustom_note: keep me\n",
            ("single_task",),
            id="form_c_single_mapping",
        ),
    ],
)
def test_form_b_c_to_a_and_unknown_key_preserved(
    tmp_path: Path, source_yaml: str, expected_task_ids: tuple[str, ...]
) -> None:
    """Proves: STORY-068-AC-5

    A Form B (bare sequence) or Form C (single bare mapping) task file loads
    into a buffer whose document is Form A (a single ``tasks:`` sequence),
    with an unknown per-task YAML key (``custom_note``) preserved verbatim.
    """
    # Arrange
    source_path = tmp_path / "source.yaml"
    source_path.write_text(source_yaml, encoding="utf-8")
    formatter = make_yaml_formatter()

    # Act
    buffer = load_buffer(source_path=str(source_path), yaml_formatter=formatter)

    # Assert
    assert list(buffer.document.keys()) == ["tasks"]
    assert task_ids(buffer) == expected_task_ids
    assert buffer.document["tasks"][0]["custom_note"] == "keep me"


def test_add_task_generates_stem_new_n_id(tmp_path: Path) -> None:
    """Add-task id generation (buffer-layer unit; STORY-068-AC-3 is proven
    end-to-end through the Tasks pane in ``test_tasks_pane.py``)."""
    # Arrange
    source_path = tmp_path / "sample_tasks.yaml"
    source_path.write_text(
        "tasks:\n  - task_id: existing_one\n    question: Q?\n", encoding="utf-8"
    )
    buffer = load_buffer(source_path=str(source_path), yaml_formatter=make_yaml_formatter())

    # Act
    new_index = add_task(buffer)

    # Assert
    assert new_index == 1
    assert task_ids(buffer) == ("existing_one", "sample_tasks_new_1")
    assert buffer.is_dirty


def test_duplicate_task_appends_unique_copy_suffix(tmp_path: Path) -> None:
    """Duplicate-task id generation (buffer-layer unit)."""
    # Arrange
    source_path = tmp_path / "sample_tasks.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    buffer = load_buffer(source_path=str(source_path), yaml_formatter=make_yaml_formatter())

    # Act
    new_index = duplicate_task(buffer, 0)

    # Assert
    assert new_index == 1
    assert task_ids(buffer) == ("t1", "t1_copy1")
    assert buffer.is_dirty


def test_remove_move_and_stem_helpers(tmp_path: Path) -> None:
    """The remaining buffer mutators (remove/move) plus the filename-stem helper."""
    # Arrange
    source_path = tmp_path / "ops.yaml"
    source_path.write_text(
        "tasks:\n  - task_id: t1\n    question: Q1?\n  - task_id: t2\n    question: Q2?\n",
        encoding="utf-8",
    )
    buffer = load_buffer(source_path=str(source_path), yaml_formatter=make_yaml_formatter())

    # Act
    assert filename_stem(buffer) == "ops"
    moved_index = move_task(buffer, 0, offset=1)
    assert task_ids(buffer) == ("t2", "t1")
    assert moved_index == 1
    remove_tasks(buffer, (0,))

    # Assert
    assert task_ids(buffer) == ("t1",)
    assert task_count(buffer) == 1
    assert buffer.is_dirty
