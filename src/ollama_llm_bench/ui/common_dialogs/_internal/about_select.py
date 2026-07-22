"""Pure ``version, data_folder_path -> AboutDialogViewModel`` derivation (STORY-070).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/about_dialog.md`` §4
(identity block, EC-AB-6 version-omission rule). No Qt, no I/O.
"""

from ollama_llm_bench.ui.common_dialogs.models import AboutDialogViewModel

__all__: list[str] = ["select_about_view_model"]

_APP_NAME = "Ollama LLM Bench"
_DESCRIPTION = (
    "Ollama LLM Bench — a local-first desktop tool for benchmarking large language "
    "models. It runs your benchmark tasks against local and cloud providers and "
    "grades the results."
)
_REPOSITORY_URL = "https://github.com/sanyokkua/ollama_llm_bench"


def select_about_view_model(*, version: str | None, data_folder_path: str) -> AboutDialogViewModel:
    """Derive the About dialog's view model from the injected build version and path.

    Applies the version-omission rule (EC-AB-6): an empty or ``None`` version
    string is normalised to ``None`` so the view layer omits the version line
    entirely rather than fabricating or displaying a placeholder.

    Args:
        version: The injected build-time version string, or ``None``/empty
            when no version was injected.
        data_folder_path: The resolved, absolute application-data folder path.

    Returns:
        The frozen view model the About dialog renders.
    """
    normalised_version = version if version else None
    return AboutDialogViewModel(
        app_name=_APP_NAME,
        version=normalised_version,
        description=_DESCRIPTION,
        repository_url=_REPOSITORY_URL,
        data_folder_path=data_folder_path,
    )
