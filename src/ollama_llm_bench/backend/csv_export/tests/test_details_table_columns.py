"""Details table column-order/parity coverage tests (`05_EXPORT_FORMATS.md` §6, TS-16, §6.6)."""

from ollama_llm_bench.backend.csv_export import DetailsSerializationRequest, make_table_serializer
from ollama_llm_bench.backend.csv_export.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
    make_export_context,
)

_EXPECTED_DETAILS_COLUMN_COUNT = 17


def test_details_csv_and_markdown_share_seventeen_columns() -> None:
    """Proves: STORY-032 coverage — the Details table carries exactly the 17 §6
    columns in identical header order between the CSV and Markdown paths, and
    the CSV header row is present even for an empty `results` tuple.

    Covers: TS-16, the §6.6 column-order invariant.
    """
    serializer = make_table_serializer()
    context = make_export_context()
    task_one = make_benchmark_task(task_id="factual_capitals_france")
    task_two = make_benchmark_task(
        task_id="factual_capitals_germany", question="What is the capital of Germany?"
    )
    result_one = make_benchmark_result(task_id=task_one.task_id)
    result_two = make_benchmark_result(task_id=task_two.task_id, provider_name="anthropic")
    request = DetailsSerializationRequest(
        context=context,
        results=(result_one, result_two),
        tasks_by_id={task_one.task_id: task_one, task_two.task_id: task_two},
    )
    empty_request = DetailsSerializationRequest(context=context, results=(), tasks_by_id={})

    csv_text = serializer.serialize_details_csv(request)
    markdown_text = serializer.serialize_details_markdown(request)
    empty_csv_text = serializer.serialize_details_csv(empty_request)

    csv_lines = csv_text.splitlines()
    markdown_lines = markdown_text.splitlines()
    csv_header = csv_lines[0].split(",")
    markdown_header = [cell.strip() for cell in markdown_lines[7].strip("|").split("|")]

    assert len(csv_header) == _EXPECTED_DETAILS_COLUMN_COUNT
    assert csv_header == markdown_header
    assert empty_csv_text.splitlines()[0].split(",") == csv_header
