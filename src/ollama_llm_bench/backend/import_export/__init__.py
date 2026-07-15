"""Parse, validate, preview, and apply settings/provider-config YAML import-export.

Gives the Settings dialog its data-exchange backend (`06_IMPORT_FORMATS.md`): the
``ImportExportService`` parses a file in safe-load mode (DD-55), validates it
under the three-severity model before anything is written, builds an
Added/Changed/Unchanged/Skipped preview, and applies the confirmed result —
merging settings keys, but replacing the provider registry wholesale — while
enforcing the environment-variable-name-only credential rule (D-R-18).
"""

from ollama_llm_bench.backend.import_export.api import make_import_export_service
from ollama_llm_bench.backend.import_export.models import (
    ImportFinding,
    ImportFindingSeverity,
    ImportPreviewGroup,
    ProviderImportItem,
    ProviderImportPreview,
    ProviderImportResult,
    SettingsImportItem,
    SettingsImportPreview,
    SettingsImportResult,
)
from ollama_llm_bench.backend.import_export.protocols import ImportExportService

__all__: list[str] = [
    "ImportExportService",
    "ImportFinding",
    "ImportFindingSeverity",
    "ImportPreviewGroup",
    "ProviderImportItem",
    "ProviderImportPreview",
    "ProviderImportResult",
    "SettingsImportItem",
    "SettingsImportPreview",
    "SettingsImportResult",
    "make_import_export_service",
]
