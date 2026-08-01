"""Unit tests for ``compose.py``'s ``_ExportFilenameBridge`` (STORY-077-AC-4).

Cross-module: the bridge under test lives in ``compose.py`` (the composition root), which
is explicitly exempted from the usual ``_internal/`` privacy boundary for testing purposes
(the module's own docstring frames it as the sole wiring point, not a feature module with a
public-surface contract) -- so this top-level ``tests/unit/`` file imports its private
``_ExportFilenameBridge``/``_EXPORT_KIND_MAP``/``_sanitise_run_name`` names directly, and
additionally reaches ``backend/csv_export``'s private ``sanitise_run_name`` helper solely to
prove AC-4's own "byte-for-byte" claim about compose.py's local copy of it.

Table-driven (Pattern B): AC-4's own table enumerates a finite, total set of UI ``kind``
strings the two real call sites (``ui/results/_internal/footer.py``,
``ui/resume_benchmark/_internal/actions.py``) pass.
"""

import pytest

from ollama_llm_bench.backend.csv_export import ExportKind, compose_export_filename

# Deliberate cross-check of compose.py's documented copy of this private helper -- see the
# module docstring for why this narrow exception is safe here.
from ollama_llm_bench.backend.csv_export._internal.filename import sanitise_run_name
from ollama_llm_bench.backend.domain import BenchmarkRun, RunMode, RunStatus
from ollama_llm_bench.compose import _ExportFilenameBridge

_RUN_ID = 42


def _make_run(*, run_name: str | None) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=run_name,
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.COMPLETED,
        total_tasks=2,
        completed_tasks=2,
        total_elapsed_ms=500,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
    )


@pytest.mark.parametrize(
    ("ui_kind", "export_kind"),
    [("Summary", ExportKind.SUMMARY), ("Details", ExportKind.DETAILS)],
    ids=["summary", "details"],
)
def test_bridge_maps_ui_kind_to_export_kind(ui_kind: str, export_kind: ExportKind) -> None:
    """Proves: STORY-077-AC-4

    Given a run and one of the two UI ``kind`` strings the real call sites pass
    (``Summary``/``Details``), when the bridge composes a filename, then the result
    is byte-for-byte identical to calling ``compose_export_filename`` directly with
    the matching ``ExportKind`` -- proving genuine delegation, not a re-implementation.
    """
    # Arrange
    run = _make_run(run_name="My Run! #1")
    bridge = _ExportFilenameBridge()

    # Act
    bridged = bridge.compose_filename(run=run, kind=ui_kind, ext="csv")

    # Assert
    expected = compose_export_filename(
        run_name=run.run_name or f"Run {run.run_id}", run_id=run.run_id, kind=export_kind, ext="csv"
    )
    assert bridged == expected


@pytest.mark.parametrize(
    "ui_kind", ["RunAnalysis", "Chart_bar", "Chart"], ids=["run_analysis", "chart_bar", "chart"]
)
def test_bridge_falls_back_to_local_sanitiser_for_unmapped_kinds(ui_kind: str) -> None:
    """Proves: STORY-077-AC-4

    Given a run and one of the ``kind`` strings ``backend/csv_export``'s ``ExportKind``
    does not cover (``RunAnalysis``, ``Chart_<slug>``, ``Chart`` -- the other real values
    the two call sites pass), when the bridge composes a filename, then it falls back to
    a local sanitise-then-suffix implementation whose output is byte-for-byte identical
    to ``backend/csv_export``'s own private ``sanitise_run_name`` helper, so behaviour
    matches between the mapped and unmapped paths.
    """
    # Arrange
    run = _make_run(run_name="Weird/Run Name??")
    bridge = _ExportFilenameBridge()

    # Act
    bridged = bridge.compose_filename(run=run, kind=ui_kind, ext="md")

    # Assert
    expected_name = sanitise_run_name(
        run_name=run.run_name or f"Run {run.run_id}", run_id=run.run_id
    )
    assert bridged == f"{expected_name}_{ui_kind}.md"


def test_bridge_falls_back_to_run_id_when_run_name_is_none() -> None:
    """Proves: STORY-077-AC-4

    Given a run whose ``run_name`` is ``None``, when the bridge composes a filename for
    a mapped kind, then it uses the ``"Run {run_id}"`` fallback display name -- the same
    fallback the two real call sites rely on -- before delegating to
    ``compose_export_filename``.
    """
    # Arrange
    run = _make_run(run_name=None)
    bridge = _ExportFilenameBridge()

    # Act
    bridged = bridge.compose_filename(run=run, kind="Summary", ext="csv")

    # Assert
    expected = compose_export_filename(
        run_name=f"Run {run.run_id}", run_id=run.run_id, kind=ExportKind.SUMMARY, ext="csv"
    )
    assert bridged == expected
