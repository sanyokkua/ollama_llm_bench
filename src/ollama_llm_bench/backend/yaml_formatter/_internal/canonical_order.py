"""Canonical per-task field order (`12_YAML_FORMATTER.md` §6.3)."""

from ruamel.yaml.comments import CommentedMap

CANONICAL_FIELD_ORDER: tuple[str, ...] = (
    "task_id",
    "category",
    "sub_category",
    "cosine_enabled",
    "difficulty",
    "question",
    "golden_answer",
    "pass_criteria",
    "fail_criteria",
    "required_terms",
    "source_language",
    "target_language",
    "source_material",
    "fail_example",
)

REQUIRED_TERMS_FIELD_ORDER: tuple[str, ...] = ("exact", "semantic", "forbidden")


def _ordered_keys(present_keys: list[str], canonical_order: tuple[str, ...]) -> list[str]:
    """Canonical-order-present keys first, then unknown keys in original relative order."""
    canonical_present = [key for key in canonical_order if key in present_keys]
    unknown = [key for key in present_keys if key not in canonical_order]
    return canonical_present + unknown


def _rebuild_in_order(source_map: CommentedMap, ordered_keys: list[str]) -> CommentedMap:
    """Build a new ``CommentedMap`` with ``ordered_keys``, carrying each key's comments.

    Deliberately does not copy ``source_map.ca.end``/``.ca.pre``: empirically,
    a ``ruamel.yaml`` round-trip load never populates either slot on a
    per-task mapping for any of the four comment classes this module
    preserves (end-of-line, standalone-above-key, sequence-item pre-comment,
    file-head/tail) — every one of those lands in ``.ca.items`` (per key) or,
    for the file-head comment, in the top-level document's own
    ``.ca.comment``, which this function never rebuilds. If a future
    ``ruamel.yaml`` version ever did populate ``.ca.end``/``.ca.pre`` on a
    task mapping, the reorder's comment-token-count postcondition
    (``formatter_impl._reorder_with_token_check``) would catch the drop and
    fail loudly rather than silently losing the comment.
    """
    new_map = CommentedMap()
    for key in ordered_keys:
        new_map[key] = source_map[key]
        if key in source_map.ca.items:
            new_map.ca.items[key] = source_map.ca.items[key]
    if source_map.ca.comment is not None:
        new_map.ca.comment = source_map.ca.comment
    return new_map


def reorder_required_terms(required_terms: CommentedMap) -> CommentedMap:
    """Reorder ``required_terms`` to ``exact``, ``semantic``, ``forbidden`` (§6.3).

    Args:
        required_terms: The task's ``required_terms`` mapping as loaded.

    Returns:
        A new mapping with only the present members, in canonical order,
        member comments travelling with their member.
    """
    ordered_keys = _ordered_keys(list(required_terms.keys()), REQUIRED_TERMS_FIELD_ORDER)
    return _rebuild_in_order(required_terms, ordered_keys)


def reorder_task_keys(task_map: CommentedMap) -> CommentedMap:
    """Rebuild one task mapping with its fields in canonical order (§6.3).

    A canonical key absent from ``task_map`` is never inserted. A non-canonical
    (unknown) key is preserved and appended after the last canonical key
    present, in its original relative order. Each key's end-of-line and
    pre-comments travel with it to its new position (§6.5).

    Args:
        task_map: One task mapping from the document's ``tasks:`` sequence.

    Returns:
        A new, canonically ordered ``CommentedMap`` for the same task.
    """
    ordered_keys = _ordered_keys(list(task_map.keys()), CANONICAL_FIELD_ORDER)
    new_map = _rebuild_in_order(task_map, ordered_keys)
    required_terms = new_map.get("required_terms")
    if isinstance(required_terms, CommentedMap):
        new_map["required_terms"] = reorder_required_terms(required_terms)
    return new_map
