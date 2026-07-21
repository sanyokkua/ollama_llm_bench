"""Pure grouping/derivation for the Import-preview sub-dialog
(``10_Domain_and_Data/06_IMPORT_FORMATS.md`` §8)."""

from ollama_llm_bench.ui.settings_dialog.models import (
    ProviderImportPreview,
    SettingsImportPreview,
    Severity,
)

__all__: list[str] = ["has_hard_error"]


def has_hard_error(preview: SettingsImportPreview | ProviderImportPreview) -> bool:
    """Whether Apply must be disabled for this preview.

    Args:
        preview: A settings-import or provider-import preview.

    Returns:
        ``True`` when any finding in ``preview.findings`` is a ``HARD_ERROR``.
    """
    return any(finding.severity is Severity.HARD_ERROR for finding in preview.findings)
