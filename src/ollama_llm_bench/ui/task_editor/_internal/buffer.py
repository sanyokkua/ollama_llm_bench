"""The in-memory buffer model: the round-trip YAML document handle, the draft task
list, the dirty flag, and the per-buffer scratch-file materialization seam
(STORY-068-AC-3, AC-5, AC-6; STORY-069-AC-2, AC-5).

``TaskBuffer`` is a strictly private, mutable per-module type (coding-style.md's
``@dataclass``-for-``_internal``-only exception) -- it never crosses the module
boundary; ``_internal/view_model_select.py`` and ``_internal/controller.py`` are its
only consumers. Form B/Form C -> Form A conversion and comment/unknown-key preservation
are ``YamlFormatter.load_document``'s job (STORY-068-AC-5) -- every function here
only extracts and mutates the already-converted ``document["tasks"]`` sequence, never
re-implementing shape detection of its own.

Neither ``TaskFileValidator.validate()`` nor ``YamlFormatter`` can operate on
in-memory, unsaved content directly (``validate()`` re-reads and re-parses from disk;
``YamlFormatter`` has no pure serialize-to-string method). ``materialize_to_scratch``
resolves this entirely inside ``ui/task_editor/`` by writing the buffer's current
in-memory document to a lazily-created, per-buffer temp file through the real
``YamlFormatter.save`` -- reusing the real Formatter/Validator code paths verbatim
and producing exactly "the YAML that Save would write," per this file's owning
story's design.
"""

import copy
from dataclasses import dataclass
import hashlib
from pathlib import Path
import tempfile

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ollama_llm_bench.backend.domain import Difficulty
from ollama_llm_bench.backend.task_files import FileValidationResult, ValidationSeverity
from ollama_llm_bench.backend.yaml_formatter import TaskFileDocument, YamlFormatter

__all__: list[str] = [
    "TaskBuffer",
    "add_task",
    "close_scratch",
    "commit_boolean_field",
    "commit_field_edit",
    "duplicate_task",
    "filename_stem",
    "is_saveable",
    "load_buffer",
    "materialize_to_scratch",
    "move_task",
    "remove_tasks",
    "scratch_path_for",
    "scratch_path_for_source",
    "set_chip_values",
    "task_at",
    "task_count",
    "task_ids",
]

_SCRATCH_PREFIX = "ollama_llm_bench_task_editor_"
_SCRATCH_SUFFIX = ".yaml"
_SCRATCH_DIGEST_LENGTH = 16


@dataclass
class TaskBuffer:
    """One open task-file buffer's in-memory state (``state_machine.md`` §3)."""

    source_path: str
    document: TaskFileDocument
    is_dirty: bool = False
    is_external_changed: bool = False
    is_in_use_by_run: bool = False
    validation: FileValidationResult | None = None
    scratch_path: str | None = None


def load_buffer(*, source_path: str, yaml_formatter: YamlFormatter) -> TaskBuffer:
    """Load ``source_path`` through the ``YamlFormatter`` and wrap it as a fresh buffer.

    Args:
        source_path: The absolute path of the ``.yaml``/``.yml`` file to open.
        yaml_formatter: Supplies the comment-preserving, Form-A-normalizing load.

    Returns:
        A freshly loaded, clean (not dirty) buffer.
    """
    document = yaml_formatter.load_document(source_path)
    return TaskBuffer(source_path=source_path, document=document)


def _tasks_sequence(buffer: TaskBuffer) -> CommentedSeq:
    tasks = buffer.document.get("tasks")
    if not isinstance(tasks, CommentedSeq):
        tasks = CommentedSeq()
        buffer.document["tasks"] = tasks
    return tasks


def task_count(buffer: TaskBuffer) -> int:
    """Return the buffer's current task count."""
    return len(_tasks_sequence(buffer))


def task_ids(buffer: TaskBuffer) -> tuple[str, ...]:
    """Return every task's ``task_id`` in file order."""
    return tuple(str(task.get("task_id", "")) for task in _tasks_sequence(buffer))


def task_at(buffer: TaskBuffer, index: int) -> CommentedMap:
    """Return the raw task mapping at ``index`` (for field-row selection/commits)."""
    return _tasks_sequence(buffer)[index]  # type: ignore[no-any-return]  # ruamel stub gap


def filename_stem(buffer: TaskBuffer) -> str:
    """Return the buffer's filename without its extension (for generated task ids)."""
    return Path(buffer.source_path).stem


def _blank_task_map() -> CommentedMap:
    """Build one seed-scaffold task mapping (``description.md`` §3.8)."""
    task = CommentedMap()
    task["task_id"] = ""
    task["difficulty"] = Difficulty.MEDIUM.value
    task["question"] = ""
    task["golden_answer"] = ""
    task["pass_criteria"] = ""
    task["fail_criteria"] = ""
    required_terms = CommentedMap()
    required_terms["exact"] = CommentedSeq()
    required_terms["semantic"] = CommentedSeq()
    required_terms["forbidden"] = CommentedSeq()
    task["required_terms"] = required_terms
    return task


def add_task(buffer: TaskBuffer) -> int:
    """Append a blank task with the generated ``<stem>_new_<N>`` id (STORY-068-AC-3).

    Args:
        buffer: The buffer to append to; marked dirty on return.

    Returns:
        The zero-based index of the newly appended task.
    """
    prefix = f"{filename_stem(buffer)}_new_"
    existing = sum(
        1
        for task_id in task_ids(buffer)
        if task_id.startswith(prefix) and task_id[len(prefix) :].isdigit()
    )
    task = _blank_task_map()
    task["task_id"] = f"{prefix}{existing + 1}"
    tasks = _tasks_sequence(buffer)
    tasks.append(task)
    buffer.is_dirty = True
    return len(tasks) - 1


def duplicate_task(buffer: TaskBuffer, index: int) -> int:
    """Clone the task at ``index`` with a unique ``_copy<N>`` id, inserted below it
    (STORY-068-AC-3).

    Args:
        buffer: The buffer holding the task to duplicate; marked dirty on return.
        index: The zero-based index of the task to duplicate.

    Returns:
        The zero-based index of the newly inserted clone.
    """
    tasks = _tasks_sequence(buffer)
    original = tasks[index]
    clone = copy.deepcopy(original)
    base_id = str(original.get("task_id", ""))
    existing_ids = set(task_ids(buffer))
    suffix = 1
    new_id = f"{base_id}_copy{suffix}"
    while new_id in existing_ids:
        suffix += 1
        new_id = f"{base_id}_copy{suffix}"
    clone["task_id"] = new_id
    tasks.insert(index + 1, clone)
    buffer.is_dirty = True
    return index + 1


def remove_tasks(buffer: TaskBuffer, indices: tuple[int, ...]) -> None:
    """Delete the tasks at ``indices`` (STORY-068 in-scope; Tasks pane Remove).

    Args:
        buffer: The buffer to remove tasks from; marked dirty on return.
        indices: The zero-based indices to delete, in any order.
    """
    tasks = _tasks_sequence(buffer)
    for index in sorted(indices, reverse=True):
        del tasks[index]
    buffer.is_dirty = True


def move_task(buffer: TaskBuffer, index: int, *, offset: int) -> int:
    """Swap the task at ``index`` with its neighbour ``offset`` positions away.

    Args:
        buffer: The buffer whose task list is reordered; marked dirty when moved.
        index: The zero-based index of the task to move.
        offset: ``-1`` to move up, ``1`` to move down.

    Returns:
        The task's new index, unchanged from ``index`` when the move is out of bounds.
    """
    tasks = _tasks_sequence(buffer)
    target = index + offset
    if target < 0 or target >= len(tasks):
        return index
    tasks[index], tasks[target] = tasks[target], tasks[index]
    buffer.is_dirty = True
    return target


def commit_field_edit(
    buffer: TaskBuffer, *, task_index: int, field_name: str, draft_text: str
) -> None:
    """Commit an in-progress field edit into the buffer (STORY-068-AC-6, EC-WS-4).

    Args:
        buffer: The buffer holding the edited task; marked dirty on return.
        task_index: The zero-based index of the task the field belongs to.
        field_name: The task field's YAML key.
        draft_text: The uncommitted text to write into the field.
    """
    tasks = _tasks_sequence(buffer)
    tasks[task_index][field_name] = draft_text
    buffer.is_dirty = True


def commit_boolean_field(
    buffer: TaskBuffer, *, task_index: int, field_name: str, value: bool
) -> None:
    """Commit a checkbox field edit as a real Python ``bool`` (STORY-069-AC-1).

    Writing a real ``bool`` (not a string) keeps ``cosine_enabled: true`` a YAML
    boolean scalar on save, never a quoted ``'true'`` string.

    Args:
        buffer: The buffer holding the edited task; marked dirty on return.
        task_index: The zero-based index of the task the field belongs to.
        field_name: The boolean task field's YAML key (``cosine_enabled``).
        value: The checkbox's new state.
    """
    tasks = _tasks_sequence(buffer)
    tasks[task_index][field_name] = value
    buffer.is_dirty = True


def set_chip_values(
    buffer: TaskBuffer, *, task_index: int, field_name: str, values: tuple[str, ...]
) -> None:
    """Replace a term-list field's whole chip set (STORY-069-AC-1).

    Args:
        buffer: The buffer holding the edited task; marked dirty on return.
        task_index: The zero-based index of the task the field belongs to.
        field_name: The nested term-list key (``exact``, ``semantic``, ``forbidden``).
        values: The field's complete new chip list, replacing whatever was there.
    """
    tasks = _tasks_sequence(buffer)
    task = tasks[task_index]
    required_terms = task.get("required_terms")
    if not isinstance(required_terms, CommentedMap):
        required_terms = CommentedMap()
        task["required_terms"] = required_terms
    chip_sequence = CommentedSeq()
    chip_sequence.extend(values)
    required_terms[field_name] = chip_sequence
    buffer.is_dirty = True


def is_saveable(buffer: TaskBuffer) -> bool:
    """Return whether ``buffer`` has no hard error and can be written by Save."""
    return buffer.validation is None or buffer.validation.severity is not ValidationSeverity.ERROR


def scratch_path_for_source(source_path: str) -> str:
    """Return the deterministic scratch-file path a buffer for ``source_path``
    uses, without requiring a ``TaskBuffer`` instance.

    Deterministic (a stable hash of ``source_path``, not a random temp name) so a
    test can precompute the same path to pre-register a fake validator's result
    before the buffer exists. Lives in the real OS temp directory -- never a
    sibling of ``source_path`` -- so it can never be picked up by Open Folder's
    top-level ``.yaml``/``.yml`` scan.
    """
    digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:_SCRATCH_DIGEST_LENGTH]
    return str(Path(tempfile.gettempdir()) / f"{_SCRATCH_PREFIX}{digest}{_SCRATCH_SUFFIX}")


def scratch_path_for(buffer: TaskBuffer) -> str:
    """Return ``buffer``'s lazily-computed scratch-file path (see
    ``scratch_path_for_source``), used to materialize the buffer's exact current
    in-memory state for validation and preview passes that need real file content
    (see this module's docstring).
    """
    if buffer.scratch_path is None:
        buffer.scratch_path = scratch_path_for_source(buffer.source_path)
    return buffer.scratch_path


def materialize_to_scratch(
    buffer: TaskBuffer, *, yaml_formatter: YamlFormatter, format_on_save: bool
) -> str:
    """Write ``buffer``'s current in-memory document to its scratch file and
    return the resulting text -- exactly "the YAML that Save would write."

    Args:
        buffer: The buffer whose current document is materialized.
        yaml_formatter: The real ``YamlFormatter``, used for the scratch write.
        format_on_save: Whether canonical field ordering/style normalization
            applies (mirrors the ``task_editor.auto_format_on_save`` setting).

    Returns:
        The scratch file's full text content after the write.
    """
    path = scratch_path_for(buffer)
    yaml_formatter.save(document=buffer.document, target_path=path, format_on_save=format_on_save)
    return Path(path).read_text(encoding="utf-8")


def close_scratch(buffer: TaskBuffer) -> None:
    """Delete ``buffer``'s scratch file, if one was ever created (buffer close)."""
    if buffer.scratch_path is not None:
        Path(buffer.scratch_path).unlink(missing_ok=True)
        buffer.scratch_path = None
