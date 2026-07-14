"""PASS/FAIL/ERROR header badge mapping (`20_HTML_RENDERING.md` §6.1).

No `UNKNOWN` badge exists; a result carrying no verdict and no terminal-failure
status (for example, a `SYNTHETIC` result) shows no badge at all (§10.3).

This mapping intentionally duplicates the small terminal-failure-status set also
used by `backend/csv_export/_internal/verdict_rendering.py` rather than importing
it — cross-module `_internal/` imports are forbidden (import-linter).
"""

from ollama_llm_bench.backend.domain import BenchmarkResult, ResultStatus, Verdict
from ollama_llm_bench.backend.html_rendering._internal.palette import palette_for
from ollama_llm_bench.backend.html_rendering.models import UiTheme

_TERMINAL_FAILURE_STATUSES: frozenset[ResultStatus] = frozenset(
    {
        ResultStatus.FAILED_INFERENCE,
        ResultStatus.FAILED_PROVIDER,
        ResultStatus.FAILED_TIMEOUT,
        ResultStatus.FAILED_JUDGE_TIMEOUT,
        ResultStatus.ERRORED,
    }
)


def _badge(*, bg: str, fg: str, label: str) -> str:
    return (
        f'<span style="background-color:{bg};color:{fg};padding:2px 8px;'
        f'border-radius:4px;font-weight:600;">{label}</span>'
    )


def render_verdict_badge(*, result: BenchmarkResult, theme: UiTheme) -> str | None:
    """Render the header verdict badge, or `None` when no badge applies (§6.1, §10.3)."""
    palette = palette_for(theme)
    if result.verdict is Verdict.PASS:
        return _badge(bg=palette.badge_success_bg, fg=palette.badge_success_fg, label="PASS")
    if result.verdict is Verdict.FAIL:
        return _badge(bg=palette.badge_fail_bg, fg=palette.badge_fail_fg, label="FAIL")
    if result.status in _TERMINAL_FAILURE_STATUSES:
        return _badge(bg=palette.badge_error_bg, fg=palette.badge_error_fg, label="ERROR")
    return None
