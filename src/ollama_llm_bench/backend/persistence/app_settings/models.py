"""Constants owned by ``backend/persistence/app_settings/``.

Source of truth: ADR-0004 (this module houses the shared single-writer connection
manager and schema lifecycle) and
``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §8 (schema
versioning).

``EXPECTED_SCHEMA_VERSION`` is the single embedded expected-version constant per
DD-53 — this module is the canonical owner; only ``compose.py`` imports it across
persistence modules, and no sibling persistence store imports it directly.
"""

from typing import Final

__all__: list[str] = [
    "DB_FILENAME",
    "EXPECTED_SCHEMA_VERSION",
]

EXPECTED_SCHEMA_VERSION: Final[int] = 1
"""The schema generation this application build expects (DD-53)."""

DB_FILENAME: Final[str] = "ollama_llm_bench.db"
"""The database file name within the per-OS application-data root."""
