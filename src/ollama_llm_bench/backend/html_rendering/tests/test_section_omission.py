"""Result-detail section-order and section-omission tests (`20_HTML_RENDERING.md` §6.1, HR-01/02)."""

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.html_rendering import (
    ResultDetailRenderRequest,
    make_result_html_renderer,
)
from ollama_llm_bench.backend.html_rendering.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)


def test_synthetic_result_omits_grading_section() -> None:
    """Proves: STORY-032-AC-5

    Covers: HR-01, HR-02

    Given a result-detail render request, when it is rendered, sections
    appear in the fixed §6.1 order (task question before the response, the
    response before performance metrics) and a `SYNTHETIC`-mode result omits
    the grading section and the per-term table entirely — not as empty
    markup, but structurally absent from the fragment.
    """
    task = make_benchmark_task()
    result = make_benchmark_result(task_id=task.task_id)
    synthetic_request = ResultDetailRenderRequest(
        result=result, task=task, run_mode=RunMode.SYNTHETIC
    )
    graded_request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.GRADED)
    renderer = make_result_html_renderer()

    synthetic_fragment = renderer.render_result_detail(synthetic_request)
    graded_fragment = renderer.render_result_detail(graded_request)

    assert "Keyword verdict" not in synthetic_fragment
    assert "Cosine score" not in synthetic_fragment
    assert "<table" not in synthetic_fragment
    assert "Keyword verdict" in graded_fragment
    question_index = synthetic_fragment.index(task.question)
    response_index = synthetic_fragment.index("Paris")
    assert question_index < response_index
