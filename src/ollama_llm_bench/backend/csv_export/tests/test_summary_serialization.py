"""Summary table serialization tests (`19_TABLE_SERIALIZATION.md` §6.3-6.4, `05_EXPORT_FORMATS.md` §4)."""

from ollama_llm_bench.backend.csv_export import SummarySerializationRequest, make_table_serializer
from ollama_llm_bench.backend.csv_export.tests.conftest import make_export_context, make_summary_row

_EXPECTED_SUMMARY_COLUMN_COUNT = 13


def test_summary_csv_and_markdown_share_thirteen_columns() -> None:
    """Proves: STORY-032-AC-1

    Given a Summary serialization request, when it is serialized to CSV and to
    Markdown, both outputs carry exactly the 13 §4 columns in identical header
    order, the Avg Score cell is empty in every row, and the CSV header row is
    present even for an empty row set.
    """
    serializer = make_table_serializer()
    context = make_export_context()
    row_one = make_summary_row(provider_name="ollama_local", model_name="llama3.2:3b")
    row_two = make_summary_row(provider_name="anthropic", model_name="claude-sonnet-4-5")
    request = SummarySerializationRequest(context=context, rows=(row_one, row_two))
    empty_request = SummarySerializationRequest(context=context, rows=())

    csv_text = serializer.serialize_summary_csv(request)
    markdown_text = serializer.serialize_summary_markdown(request)
    empty_csv_text = serializer.serialize_summary_csv(empty_request)

    csv_lines = csv_text.splitlines()
    markdown_lines = markdown_text.splitlines()
    csv_header = csv_lines[0].split(",")
    markdown_header = [cell.strip() for cell in markdown_lines[7].strip("|").split("|")]
    avg_score_index = csv_header.index("Avg Score")
    csv_data_rows = [line.split(",") for line in csv_lines[1:]]
    markdown_data_rows = [
        [cell.strip() for cell in line.strip("|").split("|")] for line in markdown_lines[9:]
    ]

    assert len(csv_header) == _EXPECTED_SUMMARY_COLUMN_COUNT
    assert csv_header == markdown_header
    assert empty_csv_text.splitlines()[0].split(",") == csv_header
    assert all(row[avg_score_index] == "" for row in csv_data_rows)
    assert all(row[avg_score_index] == "" for row in markdown_data_rows)
