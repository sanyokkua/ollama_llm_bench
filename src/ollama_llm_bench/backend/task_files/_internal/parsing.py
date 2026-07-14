"""Loader/validator-shared YAML text parsing (`10_Domain_and_Data/04_YAML_TASK_FORMAT.md` §3, §4).

Parses a task file's text into a flat list of raw per-task ``dict`` objects,
normalising Form B (bare sequence) and Form C (single bare mapping) to Form A's
flat task list in memory. This module never preserves comments — that is
``backend/yaml_formatter``'s job; this parser only feeds the loader and the
validation cascade.
"""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ollama_llm_bench.backend.errors import TaskFileError

_SUPPORTED_SCHEMA_VERSION = 1

# Module-level shared instance: ruamel.yaml's YAML() carries mutable per-call
# state during load()/dump(), so concurrent calls from two threads at once are
# not guaranteed safe. Not a problem today — the loader/validator are invoked
# one file at a time (run-configuration load, or a single Task Editor tab's
# validation pass) — but this assumption would need revisiting if a future
# caller parses multiple files concurrently on different worker threads.
_safe_yaml = YAML(typ="safe")


def _normalize_items(items: list[Any]) -> list[dict[str, Any]]:
    """Coerce every sequence item to a ``dict``, treating a non-mapping item as empty.

    A non-mapping item (e.g. a bare string) has no usable fields; representing
    it as ``{}`` lets the validation cascade flag it as an empty-``question``
    error rather than requiring a separate malformed-item code path.
    """
    return [item if isinstance(item, dict) else {} for item in items]


def parse_task_file(source_path: str) -> list[dict[str, Any]]:
    """Parse a task file into raw per-task dicts, normalised to Form A's flat list.

    Args:
        source_path: The absolute path of the ``.yaml``/``.yml`` file to parse.

    Returns:
        One raw ``dict`` per task, in file order. An empty file yields ``[]``.

    Raises:
        TaskFileError: The YAML does not parse at all, or ``schema_version``
            is newer than this build supports. The extension check is owned
            by ``_internal/cascade.py`` (shared by the loader and the
            validator), not by this parser.
        OSError: The file could not be opened or read.
    """
    text = Path(source_path).read_text(encoding="utf-8-sig")

    try:
        loaded = _safe_yaml.load(text)
    except YAMLError as exc:
        raise TaskFileError(message=f"{source_path}: could not parse YAML") from exc

    if loaded is None:
        return []
    if isinstance(loaded, list):
        return _normalize_items(loaded)
    if isinstance(loaded, dict):
        if "tasks" not in loaded:
            # Form C — a single bare task mapping.
            return [loaded]
        schema_version = loaded.get("schema_version")
        if isinstance(schema_version, int) and schema_version > _SUPPORTED_SCHEMA_VERSION:
            raise TaskFileError(
                message=f"{source_path}: schema_version {schema_version} is newer than the "
                f"highest version this build supports ({_SUPPORTED_SCHEMA_VERSION})"
            )
        tasks_value = loaded.get("tasks")
        if tasks_value is None:
            return []
        if not isinstance(tasks_value, list):
            raise TaskFileError(message=f"{source_path}: top-level `tasks` must be a sequence")
        return _normalize_items(tasks_value)

    raise TaskFileError(
        message=f"{source_path}: top-level YAML content must be a mapping or a sequence"
    )
