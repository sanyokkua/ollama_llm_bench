"""Public factory + filename composer for the Table Serialization Service (§2, §6.6)."""

import icontract

from ollama_llm_bench.backend.csv_export._internal.filename import compose_filename
from ollama_llm_bench.backend.csv_export._internal.serializer import _TableSerializerImpl
from ollama_llm_bench.backend.csv_export.models import ExportKind
from ollama_llm_bench.backend.csv_export.protocols import TableSerializer
from ollama_llm_bench.backend.domain import RunId

__all__: list[str] = ["compose_export_filename", "make_table_serializer"]


@icontract.ensure(lambda result: result is not None)
def make_table_serializer() -> TableSerializer:
    """Construct the stateless Table Serialization Service (§9).

    Returns:
        A pure, stateless `TableSerializer`; the same request always yields a
        byte-identical result and it is safe to call from any thread.
    """
    return _TableSerializerImpl()


@icontract.require(
    lambda run_id: run_id > 0,
    "run_id must be a valid persisted RunId — the caller resolves it from an "
    "existing BenchmarkRun before building the export filename, so a non-positive "
    "value here means a bug in the calling code, not a user mistake",
)
def compose_export_filename(*, run_name: str, run_id: RunId, kind: ExportKind, ext: str) -> str:
    """Compose the canonical, path-traversal-safe export filename (§2.1, SPEC-064).

    Args:
        run_name: The run's effective display name; arbitrary user-authored text.
        run_id: The run's persisted identifier, used as the fallback segment when
            sanitisation of `run_name` yields an empty string.
        kind: The export kind token (`Summary` or `Details`).
        ext: The file extension without a leading dot (for example `csv`, `md`).

    Returns:
        `<sanitised_run_name>_<kind>.<ext>`, guaranteed to contain only
        `[A-Za-z0-9._-]` in its name segment, never begin with `.`, and never
        equal `.` or `..`.
    """
    return compose_filename(run_name=run_name, run_id=run_id, kind=kind, ext=ext)
