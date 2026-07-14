"""Recursive comment-token counting — the input to the reorder postcondition (§6.5, §8)."""

from typing import Any

from ruamel.yaml.comments import CommentedBase
from ruamel.yaml.tokens import CommentToken


def _count_slot(slot: Any) -> int:
    """Count the ``CommentToken`` instances in one raw ``.ca`` slot value."""
    if slot is None:
        return 0
    if isinstance(slot, CommentToken):
        return 1
    if isinstance(slot, list | tuple):
        return sum(_count_slot(item) for item in slot)
    return 0


def count_comment_tokens(node: Any) -> int:
    """Recursively count every comment token attached anywhere under ``node``.

    Walks a ``ruamel.yaml`` round-trip structure — mappings, sequences, and
    their ``.ca`` (comment-attachment) records — and sums every
    ``CommentToken`` found. Used to prove a reorder pass moved every comment
    rather than dropping or duplicating one (§6.5's comment-token-count check).

    Args:
        node: Any value from a round-trip-loaded document: a ``CommentedMap``,
            a ``CommentedSeq``, a plain scalar, or a nested combination.

    Returns:
        The total number of comment tokens found under ``node``, inclusive.
    """
    total = 0
    if isinstance(node, CommentedBase) and node.ca is not None:
        total += _count_slot(node.ca.comment)
        total += _count_slot(node.ca.end)
        total += _count_slot(node.ca.pre)
        for item_comment in node.ca.items.values():
            total += _count_slot(item_comment)
    if isinstance(node, dict):
        for value in node.values():
            total += count_comment_tokens(value)
    elif isinstance(node, list):
        for item in node:
            total += count_comment_tokens(item)
    return total
