"""`set_theme` / dark-palette coverage tests (`20_HTML_RENDERING.md` §6.5, HR-15/16)."""

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.html_rendering import (
    ResultDetailRenderRequest,
    UiTheme,
    make_result_html_renderer,
)
from ollama_llm_bench.backend.html_rendering.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)

_LIGHT_CONTAINER_BG = "background-color:#ffffff;"
_DARK_CONTAINER_BG = "background-color:#1e1e1e;"


def test_set_theme_switches_rendered_container_palette() -> None:
    """Proves: STORY-032 coverage — set_theme(DARK) changes the inline-style
    palette colors render_result_detail uses relative to the default LIGHT
    theme, proving set_theme actually changes rendering rather than being a
    no-op.
    """
    task = make_benchmark_task()
    result = make_benchmark_result(task_id=task.task_id)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.GRADED)
    renderer = make_result_html_renderer()

    light_fragment = renderer.render_result_detail(request)
    renderer.set_theme(UiTheme.DARK)
    dark_fragment = renderer.render_result_detail(request)

    assert _LIGHT_CONTAINER_BG in light_fragment
    assert _LIGHT_CONTAINER_BG not in dark_fragment
    assert _DARK_CONTAINER_BG in dark_fragment
    assert _DARK_CONTAINER_BG not in light_fragment
