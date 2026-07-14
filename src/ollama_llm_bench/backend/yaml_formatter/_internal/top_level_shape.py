"""Top-level shape normalization: Form B/Form C -> Form A.

Source of truth: `10_Domain_and_Data/04_YAML_TASK_FORMAT.md` §3 and
`11_Services_and_Algorithms/12_YAML_FORMATTER.md` §6.3. Applied unconditionally
— both at load time (so the returned ``TaskFileDocument`` handle is always a
``CommentedMap``) and again, idempotently, in the save pipeline (§6.2),
regardless of ``format_on_save``.
"""

from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq


def normalize_to_form_a(loaded: Any) -> CommentedMap:
    """Normalize a round-trip-loaded document to Form A: one ``tasks:`` sequence.

    Args:
        loaded: The raw object the round-trip loader produced — a
            ``CommentedMap`` already carrying ``tasks:`` (Form A), a bare
            ``CommentedSeq`` (Form B), a bare single-task ``CommentedMap``
            (Form C), or ``None`` for an empty file.

    Returns:
        A ``CommentedMap`` whose ``"tasks"`` key holds a ``CommentedSeq`` of
        task mappings — Form A, unconditionally. Already-Form-A input is
        returned unchanged (identity), so re-normalizing is a no-op.
    """
    if isinstance(loaded, CommentedMap) and "tasks" in loaded:
        return loaded
    if isinstance(loaded, CommentedSeq):
        return _wrap_sequence(loaded, head_comment=loaded.ca.comment)
    if isinstance(loaded, CommentedMap):
        # Form C — a single bare task mapping with no `tasks:` key.
        wrapped_tasks = CommentedSeq([loaded])
        return _wrap_sequence(wrapped_tasks, head_comment=loaded.ca.comment)
    # None (empty file) or an unexpected scalar top level: TaskFileValidator is
    # the content-rejection authority (§1), not this module — normalize to an
    # empty task list rather than raising.
    return _wrap_sequence(CommentedSeq(), head_comment=None)


def _wrap_sequence(tasks: CommentedSeq, *, head_comment: Any) -> CommentedMap:
    wrapped = CommentedMap()
    wrapped["tasks"] = tasks
    if head_comment is not None:
        wrapped.ca.comment = head_comment
    return wrapped
