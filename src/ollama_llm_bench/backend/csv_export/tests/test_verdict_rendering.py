"""Details `Verdict` column PASS/FAIL/ERROR/UNKNOWN branch coverage tests (`19_TABLE_SERIALIZATION.md` §6.2)."""

import msgspec
import pytest

from ollama_llm_bench.backend.csv_export import DetailsSerializationRequest, make_table_serializer
from ollama_llm_bench.backend.csv_export.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
    make_export_context,
)
from ollama_llm_bench.backend.domain import ResultStatus, Verdict

_VERDICT_COLUMN_HEADER = "Verdict"


@pytest.mark.parametrize(
    "verdict,status,expected_verdict_token",
    [
        (Verdict.PASS, ResultStatus.COMPLETED, "PASS"),
        (None, ResultStatus.ERRORED, "ERROR"),
        (None, ResultStatus.COMPLETED, "UNKNOWN"),
    ],
    ids=[
        "set-verdict-renders-pass",
        "terminal-failure-status-renders-error",
        "non-terminal-no-verdict-renders-unknown",
    ],
)
def test_details_verdict_column_renders_expected_token(
    verdict: Verdict | None, status: ResultStatus, expected_verdict_token: str
) -> None:
    """Proves: STORY-032 coverage — the Details `Verdict` column renders
    `PASS`/`FAIL` for a set `Verdict`, the render-only `ERROR` token for a
    terminal-failure status with no set `Verdict`, and the render-only
    `UNKNOWN` token for any other row with neither a set `Verdict` nor a
    terminal-failure status.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id, status=status)
    result = msgspec.structs.replace(base_result, verdict=verdict)
    request = DetailsSerializationRequest(
        context=make_export_context(),
        results=(result,),
        tasks_by_id={task.task_id: task},
    )
    serializer = make_table_serializer()

    csv_text = serializer.serialize_details_csv(request)

    header_row, data_row = csv_text.splitlines()[0], csv_text.splitlines()[1]
    verdict_index = header_row.split(",").index(_VERDICT_COLUMN_HEADER)
    assert data_row.split(",")[verdict_index] == expected_verdict_token
