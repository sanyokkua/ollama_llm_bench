"""Colocated tests for ``TaskFileLoader`` — see STORY-031-AC-5."""

from pathlib import Path

from ollama_llm_bench.backend.domain import Difficulty, TaskOrigin
from ollama_llm_bench.backend.task_files import make_task_file_loader

_LONG_TASK_ID = "x" * 130


def test_loader_skips_malformed_tasks_and_returns_valid(tmp_path: Path) -> None:
    """Proves: STORY-031-AC-5

    A file mixing two valid tasks with an empty-``question`` task and an
    over-128-character-``task_id`` task returns only the two valid tasks,
    with no raise for either malformed row.
    """
    content = f"""\
schema_version: 1
tasks:
  - task_id: valid_task_one
    question: What is 2+2?
    golden_answer: "4"
  - task_id: empty_question_task
    question: "   "
  - task_id: {_LONG_TASK_ID}
    question: This task_id is too long.
  - task_id: valid_task_two
    question: What is the capital of France?
    golden_answer: Paris
"""
    source_path = tmp_path / "mixed.yaml"
    source_path.write_text(content, encoding="utf-8")

    loader = make_task_file_loader()
    tasks = loader.load(str(source_path))

    assert {task.task_id for task in tasks} == {"valid_task_one", "valid_task_two"}
    assert all(task.task_origin == TaskOrigin.FILE for task in tasks)


def test_loader_falls_back_to_defaults_for_invalid_difficulty_and_cosine_enabled(
    tmp_path: Path,
) -> None:
    """Proves: STORY-031-AC-5

    A task with an out-of-enum ``difficulty`` and a task with a non-bool
    ``cosine_enabled`` both load successfully with the struct's own field
    default applied (`04_YAML_TASK_FORMAT.md` §9.2 — both are soft-warning
    fallbacks, not hard errors) — the loader must never drop a whole task
    over one fallback-eligible field.
    """
    content = """\
schema_version: 1
tasks:
  - task_id: bad_difficulty_task
    question: What is 2 + 2?
    difficulty: not_a_real_difficulty
  - task_id: bad_cosine_enabled_task
    question: What is 3 + 3?
    cosine_enabled: not_a_bool
"""
    source_path = tmp_path / "fallbacks.yaml"
    source_path.write_text(content, encoding="utf-8")

    loader = make_task_file_loader()
    tasks_by_id = {task.task_id: task for task in loader.load(str(source_path))}

    assert set(tasks_by_id) == {"bad_difficulty_task", "bad_cosine_enabled_task"}
    assert tasks_by_id["bad_difficulty_task"].difficulty == Difficulty.MEDIUM
    assert tasks_by_id["bad_cosine_enabled_task"].cosine_enabled is True
