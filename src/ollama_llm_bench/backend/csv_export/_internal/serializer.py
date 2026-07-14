"""Concrete `TableSerializer` composing the CSV/Markdown writers (§6.6, §9)."""

from ollama_llm_bench.backend.csv_export._internal.column_descriptors import (
    DETAILS_COLUMNS,
    SUMMARY_COLUMNS,
)
from ollama_llm_bench.backend.csv_export._internal.csv_writer import build_csv_document
from ollama_llm_bench.backend.csv_export._internal.markdown_writer import build_markdown_document
from ollama_llm_bench.backend.csv_export.models import (
    DetailsSerializationRequest,
    SummarySerializationRequest,
)


class _TableSerializerImpl:
    """Pure, stateless `TableSerializer` implementation.

    Every operation is a function of its request argument only; safe to call
    from any thread (§9).
    """

    def serialize_summary_csv(self, request: SummarySerializationRequest) -> str:
        header = tuple(label for label, _extractor in SUMMARY_COLUMNS)
        rows = tuple(
            tuple(extractor(row) for _label, extractor in SUMMARY_COLUMNS) for row in request.rows
        )
        return build_csv_document(header=header, rows=rows)

    def serialize_summary_markdown(self, request: SummarySerializationRequest) -> str:
        header = tuple(label for label, _extractor in SUMMARY_COLUMNS)
        rows = tuple(
            tuple(extractor(row) for _label, extractor in SUMMARY_COLUMNS) for row in request.rows
        )
        return build_markdown_document(
            kind_label="Summary", context=request.context, header=header, rows=rows
        )

    def serialize_details_csv(self, request: DetailsSerializationRequest) -> str:
        header = tuple(label for label, _extractor in DETAILS_COLUMNS)
        rows = tuple(
            tuple(
                extractor(result, request.tasks_by_id[result.task_id])
                for _label, extractor in DETAILS_COLUMNS
            )
            for result in request.results
        )
        return build_csv_document(header=header, rows=rows)

    def serialize_details_markdown(self, request: DetailsSerializationRequest) -> str:
        header = tuple(label for label, _extractor in DETAILS_COLUMNS)
        rows = tuple(
            tuple(
                extractor(result, request.tasks_by_id[result.task_id])
                for _label, extractor in DETAILS_COLUMNS
            )
            for result in request.results
        )
        return build_markdown_document(
            kind_label="Details", context=request.context, header=header, rows=rows
        )
