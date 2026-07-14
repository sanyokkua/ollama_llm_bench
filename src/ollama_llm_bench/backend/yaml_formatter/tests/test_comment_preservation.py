"""Colocated tests for comment anchoring and preservation — see STORY-031-AC-3."""

from pathlib import Path

from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.backend.yaml_formatter._internal.comment_tokens import count_comment_tokens

_SOURCE_TEXT = """\
# file head comment
tasks:
  - difficulty: hard
    task_id: task_one  # eol comment on task_id
    question: What is 2 + 2?
  # comment above second task
  - task_id: task_two
    question: What is 3 + 3?
# file tail comment
"""


def test_comments_survive_reorder_and_token_count_matches(tmp_path: Path) -> None:
    """Proves: STORY-031-AC-3

    A file carrying a file-head comment, an end-of-line comment on a field
    that reordering moves, a standalone comment anchored above a sequence
    item, and a file-tail comment (YF-1..YF-4) all survive a
    ``format_on_save=True`` write, each still anchored to the construct it
    was written against, with the total comment-token count unchanged (YF-19).
    """
    source_path = tmp_path / "source.yaml"
    source_path.write_text(_SOURCE_TEXT, encoding="utf-8")

    formatter = make_yaml_formatter()
    document_before = formatter.load_document(str(source_path))
    tokens_before = count_comment_tokens(document_before)

    target_path = tmp_path / "target.yaml"
    result = formatter.save(
        document=document_before, target_path=str(target_path), format_on_save=True
    )
    assert result.succeeded

    output_text = target_path.read_text(encoding="utf-8")
    assert "# file head comment" in output_text
    assert "# eol comment on task_id" in output_text
    assert "# comment above second task" in output_text
    assert "# file tail comment" in output_text

    # The end-of-line comment must have moved with task_id to its new
    # (first) canonical position, not stayed behind on the old `difficulty`
    # line it was never attached to.
    task_id_line = next(line for line in output_text.splitlines() if "task_id: task_one" in line)
    assert "# eol comment on task_id" in task_id_line

    document_after = formatter.load_document(str(target_path))
    tokens_after = count_comment_tokens(document_after)
    assert tokens_after == tokens_before
