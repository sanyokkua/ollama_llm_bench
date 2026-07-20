"""``ResultGateway`` (D-R-06) -- the Result widget's own adapter gateway, plus the
locally-declared ``ExportFilenameHelper``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.5 for ``ResultGateway`` (method signatures copied verbatim). ``ExportFilenameHelper``
has no existing Protocol anywhere in the codebase or in the interfaces-contracts file, so
it is declared locally here (STORY-061) -- its concrete implementation is a later story's
scope; only the Protocol shape and a test fake are needed by this story.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ChartData,
    ChartKind,
    RunId,
    RunStatusPatch,
    SettingKey,
)

__all__: list[str] = ["ExportFilenameHelper", "ResultGateway"]


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

    def regenerate_run_analysis(self, run_id: RunId) -> None:
        """Regenerate the consolidated run analysis (worker thread)."""
        ...

    def chart_data(self, run_id: RunId, chart_kind: ChartKind) -> ChartData:
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
