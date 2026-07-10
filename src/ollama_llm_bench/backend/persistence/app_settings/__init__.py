"""AppSettingsStore (typed user-saved settings incl. the two embedding-selection keys +
app_meta), plus the shared single-writer connection manager and schema lifecycle
(ADR-0004)."""

from ollama_llm_bench.backend.persistence.app_settings.api import (
    DB_FILENAME,
    EXPECTED_SCHEMA_VERSION,
    AppSettingsStore,
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)

__all__: list[str] = [
    "DB_FILENAME",
    "EXPECTED_SCHEMA_VERSION",
    "AppSettingsStore",
    "create_app_settings_store",
    "ensure_schema",
    "open_read_connection",
    "open_write_connection",
]
