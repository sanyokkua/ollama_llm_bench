"""Pure body text for the Reset-confirmation sub-dialog
(``06_Settings_Dialog/sub_dialogs/reset_confirmation.md`` §2)."""

__all__: list[str] = ["RESET_CONFIRMATION_BODY_TEXT"]

RESET_CONFIRMATION_BODY_TEXT = (
    "Reset all settings to factory defaults?\n\n"
    "This will:\n"
    "- Replace the provider catalog with the three bundled providers — Ollama, LM Studio, "
    "and llama.cpp. Any provider you added — OpenAI, Azure, Anthropic, Gemini, or another — "
    "is removed.\n"
    "- Reset every general setting: theme, evaluation thresholds, retry and timeout "
    "values, logging options, and every other key in the setting registry.\n"
    "- Reset the embedding-model selection.\n\n"
    "Your benchmark runs, their results, and your saved log files are not affected."
)
