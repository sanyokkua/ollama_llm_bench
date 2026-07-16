"""Verdict and health display-state -> base colour role mapping (08-D §5, §6)."""

from ollama_llm_bench.ui.theme._internal.color_resolution import resolve_color_value
from ollama_llm_bench.ui.theme.models import HealthDisplayState, ThemeTokens, VerdictDisplayState

VERDICT_STATE_ROLE: dict[VerdictDisplayState, str] = {
    VerdictDisplayState.PASS: "success.base",
    VerdictDisplayState.FAIL: "error.base",
    VerdictDisplayState.PENDING: "muted.base",
    VerdictDisplayState.FAILED_STATE: "warning.base",
}

HEALTH_STATE_ROLE: dict[HealthDisplayState, str] = {
    HealthDisplayState.LIVE: "success.base",
    HealthDisplayState.REACHABLE_NO_MODELS: "warning.base",
    HealthDisplayState.DOWN: "error.base",
    HealthDisplayState.NOT_TESTED: "muted.base",
    HealthDisplayState.CHECKING: "muted.base",
}


def verdict_color_value(tokens: ThemeTokens, state: VerdictDisplayState) -> str:
    """Resolve a verdict display state to its base colour role's value."""
    return resolve_color_value(tokens, VERDICT_STATE_ROLE[state])


def health_color_value(tokens: ThemeTokens, state: HealthDisplayState) -> str:
    """Resolve a health display state to its base colour role's value."""
    return resolve_color_value(tokens, HEALTH_STATE_ROLE[state])
