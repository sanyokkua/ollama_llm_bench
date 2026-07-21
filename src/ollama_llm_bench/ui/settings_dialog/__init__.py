"""The Settings dialog: the Providers tab, the embedding selection, and the
Provider Edit sub-dialog (STORY-066). The General tab and the Save / Import /
Reset transactions are STORY-067's.
"""

from ollama_llm_bench.ui.settings_dialog.api import (
    SettingsDialogCollaborators,
    make_settings_dialog,
)
from ollama_llm_bench.ui.settings_dialog.models import (
    DialogChromeViewModel,
    EmbeddingSectionCollaborators,
    ProviderEditCollaborators,
    ProviderRow,
    SettingsTab,
)
from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway

__all__: list[str] = [
    "DialogChromeViewModel",
    "EmbeddingSectionCollaborators",
    "ProviderEditCollaborators",
    "ProviderRow",
    "SettingsDialogCollaborators",
    "SettingsGateway",
    "SettingsTab",
    "make_settings_dialog",
]
