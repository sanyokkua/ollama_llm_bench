"""Markdown metadata header block and pipe-table assembly.

`19_TABLE_SERIALIZATION.md` §6.4 and `05_EXPORT_FORMATS.md` §5.1.
"""

from typing import Final

from ollama_llm_bench.backend.csv_export.models import RunExportContext
from ollama_llm_bench.backend.domain import RunMode

_RUN_MODE_DISPLAY_LABELS: Final[dict[RunMode, str]] = {
    RunMode.SYNTHETIC: "Synthetic Benchmark",
    RunMode.TASKS: "Task Benchmark",
    RunMode.GRADED: "Graded Benchmark",
}
"""Human display labels for the `Mode:` metadata line, private to this module."""


def escape_markdown_cell(value: str) -> str:
    """Escape one Markdown table cell (§6.4).

    A literal pipe becomes ``\\|``; a line feed becomes ``<br>``; an empty cell
    renders as a single space so the pipe grid does not collapse.
    """
    if value == "":
        return " "
    return value.replace("|", "\\|").replace("\n", "<br>")


def build_markdown_document(
    *,
    kind_label: str,
    context: RunExportContext,
    header: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> str:
    """Assemble a complete Markdown document: metadata header block + pipe table.

    The metadata header block, the header row, and the separator row are always
    present, even when ``rows`` is empty (§5, EC-RES-1).
    """
    mode_label = _RUN_MODE_DISPLAY_LABELS[context.run_mode]
    lines: list[str] = [
        f'# {kind_label} — Run "{context.effective_run_name}"',
        "",
        f"- Run id: {context.run_id}",
        f"- Mode: {mode_label}",
        f"- Exported: {context.exported_at}",
        f"- Application: Ollama LLM Bench {context.app_version}",
        "",
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend(
        "| " + " | ".join(escape_markdown_cell(cell) for cell in row) + " |" for row in rows
    )
    return "\n".join(lines) + "\n"
