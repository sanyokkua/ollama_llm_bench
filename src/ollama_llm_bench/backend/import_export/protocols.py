"""The ``ImportExportService`` contract (`08-E_interfaces_contracts.md` §7.4/§7.4a/§7.6;
`06_IMPORT_FORMATS.md`).
"""

from typing import Protocol

from ollama_llm_bench.backend.import_export.models import (
    ProviderImportPreview,
    ProviderImportResult,
    SettingsImportPreview,
    SettingsImportResult,
)

__all__: list[str] = ["ImportExportService"]


class ImportExportService(Protocol):
    """Parse, validate, preview, and apply a settings-or-provider-config YAML file."""

    def build_settings_import_preview(self, file_path: str) -> SettingsImportPreview:
        """Parse and fully validate a settings YAML file into a preview (§3, §6.2, §8).

        blocking (file I/O + parse); invoked only on a ``TaskRunner`` worker thread.

        Args:
            file_path: The absolute path of the settings YAML file to import.

        Returns:
            The full validated preview: every surviving key grouped against its
            current value, plus every soft finding. Nothing is written yet.

        Raises:
            TaskFileError: The file could not be parsed at all (bad extension,
                malformed YAML, root not a mapping).
            ConfigurationError: A schema-shape hard error (``kind`` mismatch,
                ``schema_version`` too new, ``settings`` missing or not a mapping).
        """
        ...

    def apply_settings_import(self, preview: SettingsImportPreview) -> SettingsImportResult:
        """Write a confirmed settings-import preview's resolved values (§8).

        blocking; invoked only on a ``TaskRunner`` worker thread. Merges: only
        the keys present in ``preview.resolved_values`` are written; every other
        setting keeps its current value.

        Args:
            preview: A preview previously returned by
                ``build_settings_import_preview`` and confirmed by the user.

        Returns:
            The count of keys applied and skipped.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def build_provider_import_preview(self, file_path: str) -> ProviderImportPreview:
        """Parse and fully validate a provider-configuration YAML file (§4, §6.3, §8).

        blocking (file I/O + parse); invoked only on a ``TaskRunner`` worker thread.

        Args:
            file_path: The absolute path of the provider-config YAML file to import.

        Returns:
            The full validated preview: every surviving entry, the resolved
            embedding selection, and every finding. Nothing is written yet.

        Raises:
            TaskFileError: The file could not be parsed at all (bad extension,
                malformed YAML, root not a mapping).
            ConfigurationError: A schema-shape hard error (``kind`` mismatch,
                ``schema_version`` too new, ``providers``/``embedding`` missing or
                wrong shape, every entry dropped, a duplicate ``name`` within the
                file, or ``embedding.provider_name`` matching no surviving entry).
        """
        ...

    def apply_provider_import(self, preview: ProviderImportPreview) -> ProviderImportResult:
        """Replace the provider registry wholesale with a confirmed preview (§8, DD-55).

        blocking; invoked only on a ``TaskRunner`` worker thread. This is a
        **replace**, not a merge: the resulting catalog is exactly the preview's
        surviving (``ADDED``) entries.

        Args:
            preview: A preview previously returned by
                ``build_provider_import_preview`` and confirmed by the user.

        Returns:
            The count of providers applied and skipped.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def export_settings(self) -> bytes:
        """Serialize every user-saved setting to the canonical settings YAML (§9).

        blocking; invoked only on a ``TaskRunner`` worker thread. The disk write
        itself is owned by a later UI story's ``FileSystemActions``/``NativePickers``
        adapters — this call returns the payload only.

        Returns:
            The UTF-8-encoded YAML document.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def export_providers(self) -> bytes:
        """Serialize the provider catalog and embedding selection to YAML (§9).

        blocking; invoked only on a ``TaskRunner`` worker thread. ``provider_id``
        never appears in the payload (§9, DD-33).

        Returns:
            The UTF-8-encoded YAML document.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...
