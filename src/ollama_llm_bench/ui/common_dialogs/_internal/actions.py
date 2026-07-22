"""Small side-effecting action helpers for ``ui/common_dialogs/`` (STORY-057).

``resume_summary_fix_in_settings_not_yet_available`` follows the STORY-056
placeholder-action pattern (a stub action that only emits a 'not yet available'
toast): actually opening ``ui/settings_dialog/`` focused on a provider/tab is
Phase-11/main-window cross-widget navigation, out of this story's ``modules:``.
"""

import structlog

from ollama_llm_bench.backend.events import SIGNAL_GLOBAL_MESSAGE, EventBus, GlobalMessageEvent

__all__: list[str] = ["resume_summary_fix_in_settings_not_yet_available"]

logger = structlog.get_logger(__name__)


def resume_summary_fix_in_settings_not_yet_available(*, event_bus: EventBus) -> None:
    """Toast a not-yet-available message for the Fix in Settings action.

    Args:
        event_bus: Emits the toast.
    """
    logger.debug("resume_summary_fix_in_settings_not_yet_available")
    event_bus.emit(
        SIGNAL_GLOBAL_MESSAGE,
        GlobalMessageEvent(
            text="Open Settings, fix the highlighted provider, then resume again.",
            severity="info",
        ),
    )
