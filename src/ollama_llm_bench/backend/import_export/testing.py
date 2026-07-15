"""A fake ``ImportExportService`` for downstream consumers' tests."""

from ollama_llm_bench.backend.import_export.models import (
    ProviderImportPreview,
    ProviderImportResult,
    SettingsImportPreview,
    SettingsImportResult,
)

__all__: list[str] = ["FakeImportExportService"]


class FakeImportExportService:
    """Records every call and returns a canned, settable result per method."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.next_settings_preview: SettingsImportPreview = SettingsImportPreview(
            items=(), findings=(), resolved_values={}
        )
        self.next_settings_result: SettingsImportResult = SettingsImportResult(
            applied_count=0, skipped_count=0
        )
        self.next_provider_preview: ProviderImportPreview = ProviderImportPreview(
            items=(), embedding_provider_name="", embedding_model_name="", findings=()
        )
        self.next_provider_result: ProviderImportResult = ProviderImportResult(
            applied_count=0, skipped_count=0
        )
        self.next_settings_export: bytes = b""
        self.next_providers_export: bytes = b""

    def build_settings_import_preview(self, file_path: str) -> SettingsImportPreview:
        """Record the call and return ``self.next_settings_preview``."""
        self.calls.append(("build_settings_import_preview", file_path))
        return self.next_settings_preview

    def apply_settings_import(self, preview: SettingsImportPreview) -> SettingsImportResult:
        """Record the call and return ``self.next_settings_result``."""
        self.calls.append(("apply_settings_import", preview))
        return self.next_settings_result

    def build_provider_import_preview(self, file_path: str) -> ProviderImportPreview:
        """Record the call and return ``self.next_provider_preview``."""
        self.calls.append(("build_provider_import_preview", file_path))
        return self.next_provider_preview

    def apply_provider_import(self, preview: ProviderImportPreview) -> ProviderImportResult:
        """Record the call and return ``self.next_provider_result``."""
        self.calls.append(("apply_provider_import", preview))
        return self.next_provider_result

    def export_settings(self) -> bytes:
        """Record the call and return ``self.next_settings_export``."""
        self.calls.append(("export_settings", None))
        return self.next_settings_export

    def export_providers(self) -> bytes:
        """Record the call and return ``self.next_providers_export``."""
        self.calls.append(("export_providers", None))
        return self.next_providers_export
