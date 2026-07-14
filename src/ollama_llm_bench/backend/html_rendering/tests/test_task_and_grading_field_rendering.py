"""Header/task/prompts/response/grading optional-field coverage tests (`20_HTML_RENDERING.md` §6.1)."""

import msgspec

from ollama_llm_bench.backend.domain import (
    BenchmarkResultTerm,
    ResultTermKind,
    RunMode,
    Verdict,
)
from ollama_llm_bench.backend.html_rendering import (
    ResultDetailRenderRequest,
    make_result_html_renderer,
)
from ollama_llm_bench.backend.html_rendering.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)


def test_header_section_renders_optional_size_and_repeat_metadata() -> None:
    """Proves: STORY-032 coverage — the header section renders the optional
    input-size/output-size/repeat-index metadata lines when the task sets them.
    """
    base_task = make_benchmark_task()
    task = msgspec.structs.replace(
        base_task, input_size_label="short", output_size_label="long", repeat_index=2
    )
    result = make_benchmark_result(task_id=task.task_id)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "Input size: short" in fragment
    assert "Output size: long" in fragment
    assert "Repeat index: 2" in fragment


def test_task_section_renders_all_optional_descriptor_fields() -> None:
    """Proves: STORY-032 coverage — the task section renders golden answer,
    pass/fail criteria, source/target language, and source material whenever
    the task sets them.
    """
    base_task = make_benchmark_task()
    task = msgspec.structs.replace(
        base_task,
        golden_answer="Paris",
        pass_criteria="Mentions Paris",  # noqa: S106  # task field, not a credential
        fail_criteria="Mentions any other city",
        source_language="en",
        target_language="fr",
        source_material="Wikipedia excerpt",
    )
    result = make_benchmark_result(task_id=task.task_id)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "Golden answer: Paris" in fragment
    assert "Pass criteria: Mentions Paris" in fragment
    assert "Fail criteria: Mentions any other city" in fragment
    assert "Source language: en" in fragment
    assert "Target language: fr" in fragment
    assert "Source material: Wikipedia excerpt" in fragment


def test_prompts_section_renders_system_and_user_prompt_blocks() -> None:
    """Proves: STORY-032 coverage — the prompts section renders both the
    system-prompt and user-prompt blocks when set.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id)
    result = msgspec.structs.replace(
        base_result, system_prompt_sent="You are helpful.", user_prompt_sent="Capital of France?"
    )
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "System prompt" in fragment
    assert "You are helpful." in fragment
    assert "User prompt" in fragment
    assert "Capital of France?" in fragment


def test_response_section_omitted_when_no_response_content_set() -> None:
    """Proves: STORY-032 coverage — the response section is omitted entirely
    when neither `sanitized_response` nor `raw_response` is set.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id, sanitized_response=None)
    result = msgspec.structs.replace(base_result, sanitized_response=None, raw_response=None)
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "Response" not in fragment
    assert "characters</div>" not in fragment


def test_response_section_renders_raw_reasoning_and_char_length_without_sanitized() -> None:
    """Proves: STORY-032 coverage — the response section renders the raw-response
    reasoning block (when `has_thinking_block` and `raw_response` are set) and
    the response character-length line, even when `sanitized_response` is
    unset.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id, sanitized_response=None)
    result = msgspec.structs.replace(
        base_result,
        sanitized_response=None,
        raw_response="<think>reasoning</think>Paris",
        has_thinking_block=True,
        response_char_length=42,
    )
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.TASKS)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "Raw response (with reasoning)" in fragment
    assert "&lt;think&gt;reasoning&lt;/think&gt;Paris" in fragment
    assert "42 characters</div>" in fragment


def test_grading_section_renders_judge_reasoning_and_per_term_table() -> None:
    """Proves: STORY-032 coverage — the GRADED grading section renders the
    judge-reasoning line and the per-term outcome table when `result.terms` is
    non-empty.
    """
    task = make_benchmark_task()
    base_result = make_benchmark_result(task_id=task.task_id)
    term = BenchmarkResultTerm(
        term_kind=ResultTermKind.SEMANTIC, term_order=0, term_text="Paris", similarity_score=0.91
    )
    result = msgspec.structs.replace(
        base_result,
        verdict=Verdict.PASS,
        judge_reasoning="The response correctly names Paris.",
        terms=(term,),
    )
    request = ResultDetailRenderRequest(result=result, task=task, run_mode=RunMode.GRADED)
    renderer = make_result_html_renderer()

    fragment = renderer.render_result_detail(request)

    assert "Judge reasoning: The response correctly names Paris." in fragment
    assert "<table" in fragment
    assert "<td>Paris</td>" in fragment
    assert "0.910" in fragment
