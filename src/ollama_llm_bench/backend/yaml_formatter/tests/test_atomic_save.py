"""Colocated tests for the atomic save pipeline — see STORY-031-AC-4."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.backend.yaml_formatter.models import SaveFailureReason


def _build_document(task_id: str) -> CommentedMap:
    document = CommentedMap()
    task = CommentedMap()
    task["task_id"] = task_id
    task["question"] = "What is 2 + 2?"
    document["tasks"] = CommentedSeq([task])
    return document


def test_write_failure_leaves_target_unchanged_and_no_temp(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Proves: STORY-031-AC-4

    A simulated mid-write failure (YF-16) reports a typed ``SaveResult``
    failure, leaves ``target_path`` byte-for-byte unchanged, and removes the
    temporary file it had created (YF-15, YF-17).
    """
    target_path = tmp_path / "existing.yaml"
    original_bytes = b"schema_version: 1\ntasks: []\n"
    target_path.write_bytes(original_bytes)

    mocker.patch(
        "ollama_llm_bench.backend.yaml_formatter._internal.atomic_save._write_and_fsync",
        side_effect=OSError("simulated disk-full mid-write"),
    )

    formatter = make_yaml_formatter()
    document = _build_document("new_task")
    result = formatter.save(document=document, target_path=str(target_path), format_on_save=True)

    assert result.succeeded is False
    assert result.failure_reason == SaveFailureReason.WRITE_FAILED
    assert target_path.read_bytes() == original_bytes
    assert list(tmp_path.iterdir()) == [target_path]


@pytest.mark.parametrize("format_on_save", [True, False])
def test_successful_save_replaces_target_and_leaves_no_temp(
    tmp_path: Path, *, format_on_save: bool
) -> None:
    """Proves: STORY-031-AC-4

    A successful save (the counterpart happy path) commits the new content
    to ``target_path`` and leaves no temporary file behind, regardless of
    ``format_on_save`` (§6.6 is unconditional).
    """
    target_path = tmp_path / "existing.yaml"
    target_path.write_bytes(b"schema_version: 1\ntasks: []\n")

    formatter = make_yaml_formatter()
    document = _build_document("new_task")
    result = formatter.save(
        document=document, target_path=str(target_path), format_on_save=format_on_save
    )

    assert result.succeeded is True
    assert "new_task" in target_path.read_text(encoding="utf-8")
    assert list(tmp_path.iterdir()) == [target_path]
