"""Safe-load parsing and plain YAML rendering for the import/export file boundary.

Source of truth: `10_Domain_and_Data/06_IMPORT_FORMATS.md` §2 (encoding, extension,
parser, severities). Reading uses ``ruamel.yaml.YAML(typ="safe")`` (DD-55 — no
arbitrary object construction); writing uses a plain ``ruamel.yaml.YAML()``. This
module never reuses ``backend/task_files``'s ``yaml_formatter`` — that module is
task-file-specific (round-trip mode, canonical key reordering), not a fit here.
"""

import io
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ollama_llm_bench.backend.errors import ConfigurationError, TaskFileError
from ollama_llm_bench.backend.import_export.models import ImportFinding, ImportFindingSeverity

__all__: list[str] = [
    "SUPPORTED_SCHEMA_VERSION",
    "check_kind_matches",
    "dump_yaml_mapping",
    "load_yaml_mapping",
    "resolve_schema_version",
]

SUPPORTED_SCHEMA_VERSION = 1
_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".yaml", ".yml"})

# Module-level shared instances: ruamel.yaml's YAML() carries mutable per-call state
# during load()/dump(), so concurrent calls from two threads at once are not
# guaranteed safe. Import/export is invoked one file at a time (a single Settings
# dialog action), so a shared instance is safe today.
_safe_yaml = YAML(typ="safe")
_plain_yaml = YAML()
_plain_yaml.default_flow_style = False


def load_yaml_mapping(file_path: str) -> dict[str, Any]:
    """Parse a YAML file into its raw top-level mapping (§2).

    Args:
        file_path: The absolute path of the ``.yaml``/``.yml`` file to parse.

    Returns:
        The raw, safe-loaded top-level mapping.

    Raises:
        TaskFileError: The extension is not ``.yaml``/``.yml``, the file could
            not be read or decoded, the YAML does not parse at all, or the root
            is not a mapping.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix not in _SUPPORTED_EXTENSIONS:
        raise TaskFileError(
            message=f"{file_path}: file extension {suffix or '(none)'} is not .yaml or .yml"
        )
    try:
        text = Path(file_path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise TaskFileError(message=f"{file_path}: could not read file") from exc
    try:
        loaded = _safe_yaml.load(text)
    except YAMLError as exc:
        raise TaskFileError(message=f"{file_path}: could not parse YAML") from exc
    if not isinstance(loaded, dict):
        raise TaskFileError(message=f"{file_path}: top-level YAML content must be a mapping")
    return loaded


def check_kind_matches(raw: dict[str, Any], *, expected_kind: str) -> None:
    """Guard the optional ``kind`` top-level key against the chosen import action (§6.1).

    Args:
        raw: The raw top-level mapping.
        expected_kind: ``"settings"`` or ``"provider_config"``.

    Raises:
        ConfigurationError: ``kind`` is present and does not equal ``expected_kind``.
    """
    kind = raw.get("kind")
    if kind is not None and kind != expected_kind:
        raise ConfigurationError(
            message=f"kind {kind!r} does not match the expected {expected_kind!r} import"
        )


def resolve_schema_version(raw: dict[str, Any]) -> ImportFinding | None:
    """Resolve the optional ``schema_version`` top-level key (§6.1).

    Args:
        raw: The raw top-level mapping.

    Returns:
        A soft-warning finding when the value is present but non-integer or
        less than 1 (treated as ``1``); ``None`` when absent or already valid.

    Raises:
        ConfigurationError: ``schema_version`` is an integer newer than this
            build supports.
    """
    schema_version = raw.get("schema_version")
    if schema_version is None:
        return None
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        return ImportFinding(
            severity=ImportFindingSeverity.SOFT_WARNING,
            item_key=None,
            reason=f"schema_version {schema_version!r} is not a valid integer; treated as 1",
        )
    if schema_version > SUPPORTED_SCHEMA_VERSION:
        raise ConfigurationError(
            message=(
                f"schema_version {schema_version} is newer than the highest version this "
                f"build supports ({SUPPORTED_SCHEMA_VERSION})"
            )
        )
    if schema_version < 1:
        return ImportFinding(
            severity=ImportFindingSeverity.SOFT_WARNING,
            item_key=None,
            reason=f"schema_version {schema_version} is less than 1; treated as 1",
        )
    return None


def dump_yaml_mapping(document: dict[str, Any]) -> bytes:
    """Render a plain mapping to canonical UTF-8 YAML bytes for export (§9).

    Args:
        document: The plain (non-``CommentedMap``) mapping to serialize.

    Returns:
        The UTF-8-encoded YAML document, with exactly one trailing newline.
    """
    buffer = io.StringIO()
    _plain_yaml.dump(document, buffer)
    text = buffer.getvalue().rstrip("\n") + "\n"
    return text.encode("utf-8")
