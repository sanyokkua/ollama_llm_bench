"""Details cell verbatim-content tests (`19_TABLE_SERIALIZATION.md` §6.3, EC-EXP-1, EC-RES-2)."""

import csv
import io

from hypothesis import example, given, strategies as st
import pytest

from ollama_llm_bench.backend.csv_export import DetailsSerializationRequest, make_table_serializer
from ollama_llm_bench.backend.csv_export.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
    make_export_context,
)

_FORMULA_INJECTION_PREFIXES = ("=", "+", "-", "@")
_SAFE_SUFFIX_ALPHABET = st.characters(blacklist_categories=("Cs", "Cc"), blacklist_characters="\r")
_EXPECTED_ROW_COUNT = 2


def _serialize_single_response(*, response: str) -> str:
    """Serialize one Details CSV document whose `Response` cell is `response`."""
    task = make_benchmark_task()
    result = make_benchmark_result(task_id=task.task_id, sanitized_response=response)
    request = DetailsSerializationRequest(
        context=make_export_context(),
        results=(result,),
        tasks_by_id={task.task_id: task},
    )
    return make_table_serializer().serialize_details_csv(request)


def _response_cell(*, csv_text: str) -> str:
    """Parse `csv_text` back with the stdlib CSV reader and return the `Response` cell."""
    header_row, data_row = list(csv.reader(io.StringIO(csv_text)))
    return data_row[header_row.index("Response")]


@pytest.mark.slow
@pytest.mark.property
@given(
    prefix=st.sampled_from(_FORMULA_INJECTION_PREFIXES),
    suffix=st.text(alphabet=_SAFE_SUFFIX_ALPHABET, max_size=80),
)
@example(prefix="=", suffix="SUM(A1:A9)")
@example(prefix="@", suffix="SUM(1+1)*cmd|' /C calc'!A0")
def test_cell_content_is_verbatim_no_prefix(prefix: str, suffix: str) -> None:
    """Proves: STORY-032-AC-6

    Covers: EC-EXP-1

    For a Details `Response` cell whose content originates from a model
    response and begins with `=`, `+`, `-`, or `@`, round-tripping the CSV
    output back through a standard RFC 4180 reader recovers the content
    byte-for-byte — proving the serializer wrote it verbatim, with no
    redaction and no formula-injection neutralising prefix ever added.
    """
    content = f"{prefix}{suffix}"

    csv_text = _serialize_single_response(response=content)

    assert _response_cell(csv_text=csv_text) == content


def test_same_model_name_across_providers_yields_distinct_unmerged_rows() -> None:
    """Proves: STORY-032-AC-6

    Covers: EC-RES-2

    Two results sharing one `model_name` under two different `provider_name`
    values (the same model benchmarked on two providers) serialize as two
    distinct Details rows, distinguished by the `Provider` column, never
    merged into one aggregated row.
    """
    task = make_benchmark_task()
    first = make_benchmark_result(task_id=task.task_id, provider_name="first_provider")
    second = make_benchmark_result(task_id=task.task_id, provider_name="second_provider")
    request = DetailsSerializationRequest(
        context=make_export_context(),
        results=(first, second),
        tasks_by_id={task.task_id: task},
    )

    csv_text = make_table_serializer().serialize_details_csv(request)

    data_rows = csv_text.splitlines()[1:]
    assert len(data_rows) == _EXPECTED_ROW_COUNT
    assert data_rows[0] != data_rows[1]
