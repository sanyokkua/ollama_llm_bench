"""Escaping-safety tests for `render_result_detail` (`20_HTML_RENDERING.md` §6.3, HR-06/07/17)."""

import re

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.html_rendering import (
    ResultDetailRenderRequest,
    make_result_html_renderer,
)
from ollama_llm_bench.backend.html_rendering.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)

_MALICIOUS_RESPONSE = (
    "<script>alert(1)</script><style>body{display:none}</style>"
    '<iframe src="https://evil.example/"></iframe>'
    '<img src=x onerror="alert(2)"><a href="https://evil.example/">click</a>'
)
_ACTIVE_TAG_ATTACK_PATTERN = re.compile(
    r'<[a-z][^>]*\s(?:on\w+\s*=|(?:href|src)\s*=\s*"https?://)', re.IGNORECASE
)


def test_result_detail_escapes_markup_and_emits_no_active_html() -> None:
    """Proves: STORY-032-AC-4

    Covers: HR-06, HR-07, HR-17

    Given a result-detail render request whose model response literally
    contains `<script>alert(1)</script>` (embedded in a wider markup-injection
    payload), when it is rendered, the raw markup never appears, its escaped
    entity form does, and the fragment contains no `<style>`, `<iframe>`, any
    `on*` event attribute, or network `href`/`src` on a real tag.
    """
    task = make_benchmark_task()
    result = make_benchmark_result(task_id=task.task_id, sanitized_response=_MALICIOUS_RESPONSE)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.GRADED)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "<script>alert(1)</script>" not in fragment
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in fragment
    assert "<style" not in fragment.lower()
    assert "<iframe" not in fragment.lower()
    assert _ACTIVE_TAG_ATTACK_PATTERN.search(fragment) is None
