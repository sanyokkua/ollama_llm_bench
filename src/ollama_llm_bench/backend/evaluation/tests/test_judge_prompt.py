"""Tests for backend/evaluation/_internal/judge/prompt.py."""

from ollama_llm_bench.backend.domain import RequiredTerms
from ollama_llm_bench.backend.evaluation._internal.judge.prompt import build_judge_messages
from ollama_llm_bench.backend.evaluation.tests.conftest import make_task

_SENTINEL_PROVIDER_NAME = "Definitely-Not-A-Real-Provider-9000"
_SENTINEL_MODEL_NAME = "definitely-not-a-real-model-9000"


def test_judge_prompt_is_anonymous_and_omits_absent_fields() -> None:
    """Proves: STORY-028-AC-4

    The assembled judge prompt (system + user) contains no provider
    identifier and no test-model name, carries sanitized_response, and
    omits every absent optional field per the §4.2 placeholder rules.
    """
    task = make_task(
        golden_answer=None,
        pass_criteria="",
        fail_criteria="",
        source_material=None,
        fail_example=None,
        required_terms=RequiredTerms(),
    )

    system_message, user_message = build_judge_messages(
        task=task,
        sanitized_response="Paris is the capital of France.",
        system_prompt_sent=None,
        is_retry=False,
    )

    combined = system_message.content + user_message.content
    assert _SENTINEL_PROVIDER_NAME not in combined
    assert _SENTINEL_MODEL_NAME not in combined
    assert "Paris is the capital of France." in user_message.content
    assert 'REFERENCE ("GOLDEN") ANSWER:\n(none provided)' in user_message.content
    assert "PASS CRITERIA:\n(none provided" in user_message.content
    assert "FAIL CRITERIA:\n(none provided)" in user_message.content
    assert "SYSTEM PROMPT GIVEN TO THE MODEL:" not in user_message.content
    assert "SUPPORTING MATERIAL:" not in user_message.content
    assert "REQUIRED KEYWORDS" not in user_message.content
    assert "EXAMPLE OF A WRONG ANSWER:" not in user_message.content


def test_judge_prompt_includes_present_optional_fields() -> None:
    """Proves: STORY-028-AC-4

    Present optional fields render their labeled block.
    """
    task = make_task(
        golden_answer="Paris",
        pass_criteria="Names Paris.",  # noqa: S106  # task field, not a credential
        fail_criteria="Names any other city.",
        source_material="Some background text.",
        fail_example="Lyon",
        required_terms=RequiredTerms(exact=("Paris",), semantic=("capital city",)),
    )

    _, user_message = build_judge_messages(
        task=task,
        sanitized_response="Paris.",
        system_prompt_sent="Answer concisely.",
        is_retry=False,
    )

    assert "SYSTEM PROMPT GIVEN TO THE MODEL:\nAnswer concisely." in user_message.content
    assert "SUPPORTING MATERIAL:\nSome background text." in user_message.content
    assert 'REFERENCE ("GOLDEN") ANSWER:\nParis' in user_message.content
    assert "REQUIRED KEYWORDS" in user_message.content
    assert "Paris" in user_message.content
    assert "capital city" in user_message.content
    assert "EXAMPLE OF A WRONG ANSWER:\nLyon" in user_message.content


def test_retry_appends_the_stricter_corrective_instruction() -> None:
    """Proves: STORY-028-AC-5

    is_retry=True appends the §9.1 corrective instruction to the system
    message.
    """
    task = make_task()

    system_message, _ = build_judge_messages(
        task=task, sanitized_response="Paris.", system_prompt_sent=None, is_retry=True
    )

    assert "A previous attempt did not return a valid response" in system_message.content


def test_uncategorized_task_reads_uncategorized_in_area_line() -> None:
    """Proves: STORY-028-AC-4

    A task with neither category nor sub_category produces the
    "(uncategorized)" area line (DD-46).
    """
    task = make_task(category="", sub_category="")

    system_message, user_message = build_judge_messages(
        task=task, sanitized_response="Paris.", system_prompt_sent=None, is_retry=False
    )

    assert "(uncategorized)" in system_message.content
    assert "TASK AREA: (uncategorized)" in user_message.content
