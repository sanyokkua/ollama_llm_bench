"""Details table cell-escaping tests (`19_TABLE_SERIALIZATION.md` §6.3-6.4, EC-EXP-2)."""

from ollama_llm_bench.backend.csv_export import DetailsSerializationRequest, make_table_serializer
from ollama_llm_bench.backend.csv_export.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
    make_export_context,
)

_TRICKY_RESPONSE = 'Paris, "City of Light" | notes\nSecond line'


def test_details_cell_with_comma_quote_newline_and_pipe() -> None:
    """Proves: STORY-032-AC-2

    Covers: EC-EXP-2

    Given a Details result cell containing a comma, a double quote, and a line
    feed, when it is serialized to CSV, the field is wrapped in double quotes,
    the embedded quote is doubled, and the line feed is kept inside the one
    field per RFC 4180; when serialized to Markdown, the line feed becomes
    `<br>` and a literal pipe becomes `\\|`.
    """
    task = make_benchmark_task()
    result = make_benchmark_result(task_id=task.task_id, sanitized_response=_TRICKY_RESPONSE)
    request = DetailsSerializationRequest(
        context=make_export_context(),
        results=(result,),
        tasks_by_id={task.task_id: task},
    )
    serializer = make_table_serializer()

    csv_text = serializer.serialize_details_csv(request)
    markdown_text = serializer.serialize_details_markdown(request)

    expected_csv_field = '"Paris, ""City of Light"" | notes\nSecond line"'
    expected_markdown_fragment = 'Paris, "City of Light" \\| notes<br>Second line'
    assert expected_csv_field in csv_text
    assert expected_markdown_fragment in markdown_text
    assert "\nSecond line" not in markdown_text
