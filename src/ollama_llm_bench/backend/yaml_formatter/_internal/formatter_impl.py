"""``YamlFormatter`` concrete implementation — the save pipeline of §6.2."""

import io
from pathlib import Path

import icontract
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ollama_llm_bench.backend.yaml_formatter._internal.atomic_save import atomic_write
from ollama_llm_bench.backend.yaml_formatter._internal.canonical_order import reorder_task_keys
from ollama_llm_bench.backend.yaml_formatter._internal.comment_tokens import count_comment_tokens
from ollama_llm_bench.backend.yaml_formatter._internal.style_normalization import (
    normalize_multiline_scalars,
    normalize_required_terms_list_styles,
)
from ollama_llm_bench.backend.yaml_formatter._internal.top_level_shape import normalize_to_form_a
from ollama_llm_bench.backend.yaml_formatter.models import SaveResult, TaskFileDocument

_NO_LINE_FOLDING_WIDTH = 1_000_000

# Module-level shared instance: ruamel.yaml's YAML() carries mutable per-call
# state during load()/dump(), so concurrent calls from two threads at once are
# not guaranteed safe. §9 constrains the editor to one save per file in flight
# at a time, but this instance is shared across *all* files/tabs — a future
# caller saving two different files concurrently on two worker threads would
# need its own instance per call, or a lock around this one.
_round_trip_yaml = YAML()
# Two-space indentation throughout, with the sequence dash itself indented
# two spaces under its parent key (§6.1, §6.4) — `tasks:\n  - task_id: ...`.
_round_trip_yaml.indent(mapping=2, sequence=4, offset=2)
_round_trip_yaml.width = _NO_LINE_FOLDING_WIDTH  # no line-width folding (§6.1)
_round_trip_yaml.explicit_start = False


@icontract.ensure(
    lambda result, task_map: count_comment_tokens(result) == count_comment_tokens(task_map),
    "reordering a task's keys must not change its total comment-token count "
    "(FormatterDefect, §8) — a mismatch here is a bug in the reorder step, never "
    "a property of the file content",
)
def _reorder_with_token_check(task_map: CommentedMap) -> CommentedMap:
    """Reorder one task's fields, guarding the comment-token-count invariant (§6.5, §8)."""
    return reorder_task_keys(task_map)


def _apply_format_on_save(document: CommentedMap) -> None:
    """Apply canonical field order and style normalization to every task (§6.3, §6.4)."""
    tasks = document.get("tasks")
    if not isinstance(tasks, CommentedSeq):
        return
    for index, task_map in enumerate(tasks):
        if not isinstance(task_map, CommentedMap):
            continue
        reordered = _reorder_with_token_check(task_map)
        normalize_multiline_scalars(reordered)
        required_terms = reordered.get("required_terms")
        if isinstance(required_terms, CommentedMap):
            normalize_required_terms_list_styles(required_terms)
        tasks[index] = reordered


def _serialize(document: CommentedMap) -> str:
    """Render ``document`` to UTF-8 text with exactly one trailing newline (§6.4, §6.6)."""
    buffer = io.StringIO()
    _round_trip_yaml.dump(document, buffer)
    text = buffer.getvalue()
    return text.rstrip("\n") + "\n"


class _YamlFormatterImpl:
    """The single ``YamlFormatter`` implementation; constructed by ``make_yaml_formatter``."""

    def load_document(self, source_path: str, /) -> TaskFileDocument:
        text = Path(source_path).read_text(encoding="utf-8-sig")
        loaded = _round_trip_yaml.load(text)
        return normalize_to_form_a(loaded)

    def save(
        self, *, document: TaskFileDocument, target_path: str, format_on_save: bool
    ) -> SaveResult:
        normalized = normalize_to_form_a(document)
        if format_on_save:
            _apply_format_on_save(normalized)
        text = _serialize(normalized)
        return atomic_write(text=text, target_path=target_path)
