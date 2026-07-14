"""`TableSerializer` — this module's swap point (`19_TABLE_SERIALIZATION.md` §2.1)."""

from typing import Protocol

from ollama_llm_bench.backend.csv_export.models import (
    DetailsSerializationRequest,
    SummarySerializationRequest,
)


class TableSerializer(Protocol):
    """Converts the Summary and Details result tables to RFC 4180 CSV and Markdown.

    Every operation is a pure function of its request argument: fast-synchronous,
    in-memory only, no I/O, no shared mutable state — safe to call from any thread
    (§9). The service does not redact; cell content is written verbatim after
    rendering and format-specific escaping (§6.5).
    """

    def serialize_summary_csv(self, request: SummarySerializationRequest) -> str:
        """Serialize the Summary table to RFC 4180 CSV (§6.3).

        fast-synchronous, pure in-memory, no I/O; safe from any thread.
        """
        ...

    def serialize_summary_markdown(self, request: SummarySerializationRequest) -> str:
        """Serialize the Summary table to a GitHub-flavoured Markdown pipe table (§6.4).

        fast-synchronous, pure in-memory, no I/O; safe from any thread.
        """
        ...

    def serialize_details_csv(self, request: DetailsSerializationRequest) -> str:
        """Serialize the Details table to RFC 4180 CSV (§6.3).

        fast-synchronous, pure in-memory, no I/O; safe from any thread.

        Raises:
            KeyError: A result's ``task_id`` is absent from ``tasks_by_id`` — a
                programmer error (§8), not a taxonomy leaf; the caller must always
                supply complete task metadata.
        """
        ...

    def serialize_details_markdown(self, request: DetailsSerializationRequest) -> str:
        """Serialize the Details table to a Markdown pipe table (§6.4).

        fast-synchronous, pure in-memory, no I/O; safe from any thread.

        Raises:
            KeyError: A result's ``task_id`` is absent from ``tasks_by_id`` — a
                programmer error (§8), not a taxonomy leaf; the caller must always
                supply complete task metadata.
        """
        ...
