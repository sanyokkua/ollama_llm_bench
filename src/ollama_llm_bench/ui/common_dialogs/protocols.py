"""``RunSummaryGateway`` (D-R-06) -- the Run Summary dialog's own narrow gateway.

Source of truth: ``docs/v3_specification/07_Common_Dialogs/run_summary_dialog.md``
§8 (preflight re-check), §12 (Start Effects). Declared locally, scoped to exactly
this dialog's two backend calls -- it must not import ``NewBenchmarkGateway`` from
a sibling UI module's ``protocols.py`` (that module's Gateway is its own swap
point, not a shared one). A concrete adapter satisfying both Gateway Protocols
with one class, or two thin ones, is Phase 11's decision (compose.py), not this
story's -- ``NewBenchmarkGateway`` already exposes both methods below and so
satisfies this Protocol structurally, with no adapter shim, exactly like
``ModeVisibilityPolicy``'s structural-satisfaction pattern (STORY-054).
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import AppReadinessSnapshot, RunId, RunStartRequest

__all__: list[str] = ["RunSummaryGateway"]


class RunSummaryGateway(Protocol):
    """Adapter gateway for the Run Summary dialog (D-R-06)."""

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot.

        fast-synchronous. Re-checked on every dialog open (§8).
        """
        ...

    def start_run(self, request: RunStartRequest) -> RunId:
        """Start a benchmark run from the assembled request; returns the run id.

        fast-synchronous (enqueues to the dispatcher thread and returns). §12
        Start Effects.
        """
        ...
