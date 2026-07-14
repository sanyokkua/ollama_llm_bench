"""Public factory for the HTML Rendering Service (`20_HTML_RENDERING.md` §2.1)."""

import icontract

from ollama_llm_bench.backend.html_rendering._internal.renderer import _ResultHtmlRendererImpl
from ollama_llm_bench.backend.html_rendering.models import UiTheme
from ollama_llm_bench.backend.html_rendering.protocols import ResultHtmlRenderer

__all__: list[str] = ["make_result_html_renderer"]


@icontract.ensure(lambda result: result is not None)
def make_result_html_renderer(*, initial_theme: UiTheme = UiTheme.LIGHT) -> ResultHtmlRenderer:
    """Construct the HTML Rendering Service (§7).

    Args:
        initial_theme: The theme active before the first `set_theme` call;
            defaults to `UiTheme.LIGHT`, matching the no-`set_theme`-yet default
            described in §4/§8.

    Returns:
        A `ResultHtmlRenderer` whose only state is the recorded `UiTheme`.
    """
    return _ResultHtmlRendererImpl(initial_theme=initial_theme)
