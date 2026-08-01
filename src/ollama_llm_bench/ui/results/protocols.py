"""``ResultGateway`` (D-R-06) -- the Result widget's own adapter gateway, plus the
locally-declared ``ExportFilenameHelper``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.5 for ``ResultGateway`` (method signatures copied verbatim). ``ExportFilenameHelper``
has no existing Protocol anywhere in the codebase or in the interfaces-contracts file, so
it is declared locally here (STORY-061) -- its concrete implementation is a later story's
scope; only the Protocol shape and a test fake are needed by this story.

``regenerate_run_analysis``'s signature is a **documented local addition** (STORY-065):
the verbatim 08-E §7b.5 draft is ``(run_id) -> None``, but
``RunAnalysisService.generate(run_id, provider_id, model_name) -> RunAnalysisResult``
(``11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`` §2.1) needs the caller-chosen
``(provider, model)`` pair and returns an outcome the Run Analysis tab must render. This
mirrors the same precedent already used for ``NewBenchmarkGateway.notify_error``
(STORY-055) and the ``ResumeGateway.serialize_table`` gap (STORY-056) -- see STORY-065's
Notes section.

``JudgeAnalysisGenerationOutcome``/``JudgeAnalysisGenerationResult`` are imported from
``ollama_llm_bench.adapters.ui_gateways`` (ADR-0017, STORY-113) -- the single canonical
declaration of this mirror of ``backend.run_analysis.RunAnalysisOutcome``/
``RunAnalysisResult`` (STORY-065). ``ui/results/`` may not import ``backend.run_analysis``
directly -- an architecture test enforces STORY-061's Definition of done ("no file in
``ui/results/`` imports ... the RunAnalysisService ... directly -- every one is wrapped
behind ``ResultGateway``") -- and importing from ``adapters/ui_gateways`` instead of
re-declaring locally is what makes the concrete ``ResultGateway`` genuinely assignable to
this module's own Protocol under ``mypy --strict`` (a two-copy nominal-type declaration is
not, per ADR-0017's Context and problem statement). The concrete adapter translates the
real backend result into this shape at the Gateway boundary, matching the existing
``ExportFilenameHelper`` pattern of a Protocol with no backend-owned counterpart type
crossing this module's boundary.
"""

from collections.abc import Callable
from typing import Protocol

from ollama_llm_bench.adapters.ui_gateways import (
    JudgeAnalysisGenerationOutcome,
    JudgeAnalysisGenerationResult,
)
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ChartData,
    ChartKind,
    HeatmapData,
    ModelName,
    ProviderId,
    RunId,
    RunStatusPatch,
    SettingKey,
)

__all__: list[str] = [
    "ExportFilenameHelper",
    "JudgeAnalysisGenerationOutcome",
    "JudgeAnalysisGenerationResult",
    "ResultGateway",
]


class ResultGateway(Protocol):
    """Adapter gateway for the Result widget (D-R-06)."""

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return the run headers for the run-selector dropdown."""
        ...

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Read one run header (for the active-run analysis and metadata)."""
        ...

    def persist_run_analysis(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Persist the consolidated ``run_analysis`` via a run-header patch."""
        ...

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Read a run's results for the Summary / Details / Charts / Analysis caches."""
        ...

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Read per-task metadata (question, golden answer, required terms)."""
        ...

    def get_setting(self, key: SettingKey) -> str | None:
        """Read ``ui.last_result_tab`` / ``ui.export_save_directly`` /
        ``ui.score_display_format``, or ``None``."""
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist ``ui.last_result_tab`` / ``ui.export_save_directly``."""
        ...

    def regenerate_run_analysis(
        self,
        run_id: RunId,
        provider_id: ProviderId,
        model_name: ModelName,
        *,
        on_complete: Callable[[JudgeAnalysisGenerationResult], None],
    ) -> bool:
        """Attempt to acquire ``JUDGE_ANALYSIS`` and dispatch run-analysis generation.

        fast-synchronous: attempts ``InferenceActivityStore.try_acquire`` and, on
        success, enqueues ``RunAnalysisService.generate(run_id, provider_id,
        model_name)`` to a worker thread, returning ``True`` immediately.
        ``on_complete`` is invoked on the GUI thread with the terminal
        ``JudgeAnalysisGenerationResult`` once the call settles. Returns ``False``, without
        dispatching and without ever calling ``on_complete``, when the gate is
        already held by another activity (STORY-065-AC-5/AC-6; a local addition
        beyond 08-E §7b.5's verbatim ``(run_id) -> None`` draft -- see this
        module's docstring and STORY-065's Notes).
        """
        ...

    def chart_data(self, run_id: RunId, chart_kind: ChartKind) -> ChartData | HeatmapData:
        """Compute one chart's prepared ``ChartData`` / ``HeatmapData``."""
        ...

    def serialize_table(self, run_id: RunId, table: str, fmt: str) -> str:
        """Produce the Summary / Details CSV or Markdown payload."""
        ...


class ExportFilenameHelper(Protocol):
    """Compose the canonical export filename (10_Domain_and_Data/05_EXPORT_FORMATS.md §2).

    Declared locally to ``ui/results/`` (STORY-061) -- no other module or interfaces
    file declares this Protocol yet.
    """

    def compose_filename(self, *, run: BenchmarkRun, kind: str, ext: str) -> str:
        """Build ``<sanitised_run_name>_<kind>.<ext>``.

        Falls back to ``Run_<run_id>`` when sanitisation of the run's effective
        name yields an empty string (EC-RES-6).

        Args:
            run: The run the export belongs to; its effective name is sanitised.
            kind: The export kind token (``Summary``, ``Details``, ``RunAnalysis``,
                or ``Chart_<chart-slug>``).
            ext: The file extension without a leading dot (``csv``, ``md``, ``png``,
                ``svg``).

        Returns:
            The composed, collision-free-at-name-level canonical filename.
        """
        ...
