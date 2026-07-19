"""Frozen ViewModel structs for ``ui/common_dialogs/`` (STORY-055).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/run_summary_dialog.md``
§3-§7. Scoped to exactly the Run Summary dialog -- see this package's
``__init__.py`` docstring for why the other Common Dialogs are out of scope.
"""

import msgspec

from ollama_llm_bench.backend.domain import RunMode

__all__: list[str] = ["RunSummaryViewModel"]


class RunSummaryViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Run Summary dialog's full displayed state, in one frozen snapshot.

    Attributes:
        run_mode: The run mode this dialog previews.
        run_name_preview: The previewed run-name display string (§4). A
            simplified preview -- the canonical ``Run N -- ... -- YYYY-MM-DD
            HH:MM`` format needs the next run number and creation timestamp,
            both resolved by the (out-of-scope) run-creation use case at Start.
        test_model_rows: One ``"provider · model"`` row per benchmark target (§4).
        work_to_be_done: The inference/judge call-count summary line; no
            duration is ever shown (§4).
        warnings: Every non-blocking Run Validator finding; empty omits the
            Warnings callout (§4).
        synthetic_matrix_rows: The synthetic prompt matrix rows, ``SYNTHETIC``
            only (§6.1); ``None`` otherwise.
        task_file_summary: The task-file count summary, ``TASKS``/``GRADED``
            only (§6.2, §6.3); ``None`` otherwise.
        judge_summary: The Judge section's summary line, every mode (§6).
        embedding_summary: The embedding readiness summary, ``GRADED`` only
            (§6.3); ``None`` otherwise.
        inference_snapshot_rows: ``"value · setting.key"`` rows for the
            Inference snapshot section (§7) -- limited to the per-run
            overrides actually carried on the request; the full resolved
            snapshot needs the (out-of-scope) ``RunSnapshotBuilder``.
        pipeline_events_rows: ``"value · setting.key"`` rows for the Pipeline
            events snapshot section (§7); same scoping note as above.
        evaluation_phase_rows: ``"value · setting.key"`` rows for the
            Evaluation phases snapshot section, ``GRADED`` only; ``None``
            otherwise.
    """

    run_mode: RunMode
    run_name_preview: str
    test_model_rows: tuple[str, ...]
    work_to_be_done: str
    warnings: tuple[str, ...]
    synthetic_matrix_rows: tuple[str, ...] | None
    task_file_summary: str | None
    judge_summary: str
    embedding_summary: str | None
    inference_snapshot_rows: tuple[str, ...]
    pipeline_events_rows: tuple[str, ...]
    evaluation_phase_rows: tuple[str, ...] | None
