"""YAML formatter DTOs: the document handle type and the typed save result."""

from enum import StrEnum

import msgspec
from ruamel.yaml.comments import CommentedMap

type TaskFileDocument = CommentedMap
"""The round-trip ``ruamel.yaml`` document handle, carrying data and comment tokens.

An opaque, mutable I/O handle — not a ``msgspec.Struct`` — because it is not
structured domain data crossing a boundary; it is the in-memory representation
of a task file's YAML text, comment tokens included, the same category as an
I/O handle such as ``sqlite3.Connection`` passed as a raw parameter type
elsewhere in the codebase.
"""


class SaveFailureReason(StrEnum):
    """Why an atomic save failed (§8)."""

    DIRECTORY_NOT_WRITABLE = "directory_not_writable"
    WRITE_FAILED = "write_failed"
    RENAME_FAILED = "rename_failed"


class SaveResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The typed outcome of a save; the formatter never raises for an I/O failure (§3, §8).

    Attributes:
        succeeded: Whether ``target_path`` now holds the new content.
        failure_reason: The typed reason on failure; ``None`` on success.
        detail: A human-readable, OS-provided failure detail, or ``""`` on success.
    """

    succeeded: bool
    failure_reason: SaveFailureReason | None = None
    detail: str = ""
