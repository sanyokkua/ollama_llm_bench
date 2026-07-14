"""CSV / Markdown table serializer — the Summary and Details result table exports.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md``
and ``docs/v3_specification/10_Domain_and_Data/05_EXPORT_FORMATS.md``.

Converts the Result Widget's Summary and Details tables into RFC 4180 CSV and
GitHub-flavoured Markdown, sharing one ordered column descriptor per table so the
two formats never drift, plus the SPEC-064 path-traversal-safe export-filename
composer. Pure, stateless, Qt-free; performs no I/O and applies no redaction —
cell content is written verbatim after rendering and format-specific escaping.
"""

from ollama_llm_bench.backend.csv_export.api import (
    compose_export_filename,
    make_table_serializer,
)
from ollama_llm_bench.backend.csv_export.models import (
    DetailsSerializationRequest,
    ExportKind,
    RunExportContext,
    SummaryRow,
    SummarySerializationRequest,
)
from ollama_llm_bench.backend.csv_export.protocols import TableSerializer

__all__: list[str] = [
    "DetailsSerializationRequest",
    "ExportKind",
    "RunExportContext",
    "SummaryRow",
    "SummarySerializationRequest",
    "TableSerializer",
    "compose_export_filename",
    "make_table_serializer",
]
