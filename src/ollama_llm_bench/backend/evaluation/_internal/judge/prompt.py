"""Judge prompt assembly — system + user messages (§4 of 08-P_judge_protocol.md)."""

from ollama_llm_bench.backend.domain import BenchmarkTask, ChatMessage, ChatRole

_SYSTEM_MESSAGE_TEMPLATE = """You are an impartial evaluation judge for an LLM benchmark. Your job is to decide
whether a candidate response correctly accomplishes a user task in the area of:
{area}.
Apply the established best practices and quality standards of this area when judging
correctness.

Rules you must follow:
- Decide a single binary verdict: PASS or FAIL. There is no partial credit and no
  "unknown" option.
- The pass criteria and fail criteria, when provided, are decisive: PASS means the
  response satisfies the pass criteria and matches no fail criterion.
- The reference ("golden") answer is one acceptable answer, not the only one. Judge
  the substance of the response, not its surface form: a correct answer that uses
  different wording, structure, or approach than the reference answer is still
  correct.
- Check the response against the question's own instructions: requirements stated in
  the task prompt must be followed.
- Do not reward a response merely for being long, fluent, or confident.
- Base your decision only on the information given in the user message.

Respond with exactly one JSON object and nothing else. No prose before or after it,
no Markdown code fences. The object must have exactly two string fields:
  "verdict"  - the string "PASS" or the string "FAIL"
  "reasoning" - one or two sentences explaining the verdict"""

_RETRY_APPENDIX = """

IMPORTANT: A previous attempt did not return a valid response. You must now reply
with exactly one JSON object and nothing else — no Markdown, no code fences, no
text before or after the object. The object must contain exactly the field
"verdict" set to the string "PASS" or "FAIL", and the field "reasoning" set to a
short string. Example of a valid reply:
{"verdict": "FAIL", "reasoning": "The response omits the required error handling."}"""


def build_judge_messages(
    *,
    task: BenchmarkTask,
    sanitized_response: str,
    system_prompt_sent: str | None,
    is_retry: bool,
) -> tuple[ChatMessage, ChatMessage]:
    """Assemble the anonymous judge prompt (system + user) for one task (§4).

    Args:
        task: The frozen task row; only its own fields are read (SPEC-018 —
            no provider identity and no test-model name are ever included).
        sanitized_response: The candidate response with any reasoning block
            already stripped (never ``raw_response``).
        system_prompt_sent: The system prompt the candidate model received
            for this result, or ``None``.
        is_retry: When ``True``, appends the stricter corrective
            instruction (§9.1) to the system message.

    Returns:
        ``(system_message, user_message)`` as ``ChatMessage`` values.
    """
    area = _format_area(task.category, task.sub_category)
    system_text = _SYSTEM_MESSAGE_TEMPLATE.format(area=area)
    if is_retry:
        system_text += _RETRY_APPENDIX
    user_text = _build_user_message(
        task=task, sanitized_response=sanitized_response, system_prompt_sent=system_prompt_sent
    )
    return (
        ChatMessage(role=ChatRole.SYSTEM, content=system_text),
        ChatMessage(role=ChatRole.USER, content=user_text),
    )


def _format_area(category: str, sub_category: str) -> str:
    if category and sub_category:
        return f"{category} / {sub_category}"
    if category:
        return category
    if sub_category:
        return sub_category
    return "(uncategorized)"


def _build_user_message(
    *, task: BenchmarkTask, sanitized_response: str, system_prompt_sent: str | None
) -> str:
    lines = [
        f"TASK AREA: {_format_area(task.category, task.sub_category)}",
        "",
        "QUESTION:",
        task.question,
    ]
    for block in (
        _system_prompt_block(system_prompt_sent),
        _source_material_block(task.source_material),
    ):
        if block:
            lines.extend(["", block])
    lines.extend(["", 'REFERENCE ("GOLDEN") ANSWER:', _golden_answer_line(task.golden_answer)])
    lines.extend(["", "PASS CRITERIA:", _pass_criteria_line(task.pass_criteria)])
    lines.extend(["", "FAIL CRITERIA:", _fail_criteria_line(task.fail_criteria)])
    for block in (
        _required_keywords_block(task),
        _fail_example_block(task.fail_example),
    ):
        if block:
            lines.extend(["", block])
    lines.extend(
        [
            "",
            "CANDIDATE RESPONSE UNDER TEST:",
            sanitized_response,
            "",
            "Decide the verdict for the candidate response and return the JSON object.",
        ]
    )
    return "\n".join(lines)


def _golden_answer_line(golden_answer: str | None) -> str:
    return golden_answer if golden_answer and golden_answer.strip() else "(none provided)"


def _pass_criteria_line(pass_criteria: str) -> str:
    if pass_criteria.strip():
        return pass_criteria
    return "(none provided — judge against the question and reference answer)"


def _fail_criteria_line(fail_criteria: str) -> str:
    return fail_criteria if fail_criteria.strip() else "(none provided)"


def _system_prompt_block(system_prompt_sent: str | None) -> str:
    if not system_prompt_sent or not system_prompt_sent.strip():
        return ""
    return f"SYSTEM PROMPT GIVEN TO THE MODEL:\n{system_prompt_sent}"


def _source_material_block(source_material: str | None) -> str:
    if not source_material or not source_material.strip():
        return ""
    return f"SUPPORTING MATERIAL:\n{source_material}"


def _required_keywords_block(task: BenchmarkTask) -> str:
    exact = task.required_terms.exact
    semantic = task.required_terms.semantic
    if not exact and not semantic:
        return ""
    terms = ", ".join((*exact, *semantic))
    return f"REQUIRED KEYWORDS (the response is expected to address these):\n{terms}"


def _fail_example_block(fail_example: str | None) -> str:
    if not fail_example or not fail_example.strip():
        return ""
    return f"EXAMPLE OF A WRONG ANSWER:\n{fail_example}"
