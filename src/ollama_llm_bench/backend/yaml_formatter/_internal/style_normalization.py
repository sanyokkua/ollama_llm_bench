"""Scalar and collection style normalization (`12_YAML_FORMATTER.md` §6.4).

Documented discrepancy: `10_Domain_and_Data/04_YAML_TASK_FORMAT.md` §6/§7 says a
single-item ``required_terms`` list is written in flow style, while
`11_Services_and_Algorithms/12_YAML_FORMATTER.md` §6.4 — this story's cited
``spec_clauses`` entry — says a single-item list is written in block style.
This module follows §6.4 because it is both the more detailed algorithm
document and the clause this story implements against; a future story
reconciling the two documents should revisit this note rather than silently
picking a side.
"""

from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import LiteralScalarString

_REQUIRED_TERMS_LIST_KEYS: tuple[str, ...] = ("exact", "semantic", "forbidden")


def normalize_multiline_scalars(task_map: CommentedMap) -> None:
    """Rewrite every multi-line string field as a literal block scalar (§6.4).

    Mutates ``task_map`` in place so each field's comment-attachment entry
    (keyed by field name) stays valid.
    """
    for key in list(task_map.keys()):
        value = task_map[key]
        if isinstance(value, str) and not isinstance(value, LiteralScalarString) and "\n" in value:
            task_map[key] = LiteralScalarString(value)


def normalize_required_terms_list_styles(required_terms: CommentedMap) -> None:
    """Flow-style an empty list, block-style everything else, per member (§6.4)."""
    for list_key in _REQUIRED_TERMS_LIST_KEYS:
        value = required_terms.get(list_key)
        if not isinstance(value, CommentedSeq):
            continue
        if len(value) == 0:
            value.fa.set_flow_style()
        else:
            value.fa.set_block_style()
