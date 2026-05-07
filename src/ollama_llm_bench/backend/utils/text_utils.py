import json
import logging
import re

from ollama_llm_bench.backend.core.models import EvalVerdict

logger = logging.getLogger(__name__)

# Constants for string patterns
XML_TAG_PATTERN = r"<(start|end)_of_turn>"
MARKDOWN_CODE_BLOCK_PATTERN = r"```json\s*|\s*```"
TRIM_PATTERNS = [
    (XML_TAG_PATTERN, ""),
    (MARKDOWN_CODE_BLOCK_PATTERN, ""),
]
REASONING_TAG_PATTERN = re.compile(r"(<think>.*?</think>)", re.DOTALL)


def extract_json_object(input_string: str) -> str:
    """
    Extract the first complete JSON object from a string.

    Args:
        input_string: String that may contain JSON embedded in other text.

    Returns:
        The extracted JSON string, or original string if no JSON found.
    """
    start_index = input_string.find("{")
    end_index = input_string.rfind("}")

    if start_index == -1 or end_index == -1 or end_index < start_index:
        return input_string

    return input_string[start_index : end_index + 1]


def sanitize_json_string(input_string: str) -> str:
    """
    Remove common wrapper patterns from JSON-containing strings.

    Handles:
    - XML-style turn markers (<start_of_turn>, <end_of_turn>)
    - Markdown code blocks (```json, ```)
    - Leading/trailing whitespace

    Args:
        input_string: Raw string that may contain JSON with wrappers.

    Returns:
        Cleaned string with wrappers removed.
    """
    # Process all patterns in a single pass
    cleaned = input_string
    for pattern, replacement in TRIM_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned)

    return cleaned.strip()


def parse_judge_response(json_string: str) -> tuple[bool, float, str]:
    """
    Parse judge response JSON with comprehensive validation.

    Args:
        json_string: Raw string containing judge response JSON.

    Returns:
        Tuple of (has_error, grade, reason) where:
        - has_error: Whether parsing encountered errors.
        - grade: Numeric score (0.0-100.0).
        - reason: Explanation of score or error.

    Note:
        Returns default values on error with detailed error logging.
    """
    try:
        # Sanitize and extract in logical order
        cleaned = sanitize_json_string(json_string)
        json_candidate = extract_json_object(cleaned)

        # Parse with validation
        data = json.loads(json_candidate)

        # Schema validation
        reason = data.get("reason", "")
        if not isinstance(reason, str):
            raise ValueError("Reason must be a string")

        grade = data.get("grade")
        if grade is None:
            raise ValueError("Missing required 'grade' field")

        try:
            grade = float(grade)
            if not 0 <= grade <= 100:
                raise ValueError("Grade must be between 0 and 100")
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid grade format: {e}") from None

        return False, grade, reason

    except (json.JSONDecodeError, ValueError) as e:
        error_msg = f"Failed to parse judge response: {e!s} | Input: '{json_string[:200]}{'...' if len(json_string) > 200 else ''}'"
        logger.warning(error_msg)
        return True, 0.0, str(e)


def parse_v2_judge_response(text: str) -> tuple[bool, EvalVerdict, float, str]:
    """Parse a V2 judge response JSON into structured verdict, score, and reasoning.

    Args:
        text: Raw string from the judge LLM, expected to contain a JSON object
            with ``verdict``, ``score``, and ``reasoning`` fields.

    Returns:
        Tuple of ``(has_error, verdict, score, reasoning)`` where:
        - ``has_error``: True when parsing completely failed.
        - ``verdict``: ``EvalVerdict.PASS``, ``FAIL``, or ``UNKNOWN``.
        - ``score``: Float clamped to ``[0.0, 1.0]``.
        - ``reasoning``: Explanation string, or error description on failure.

    Note:
        Attempts full JSON parsing first; falls back to regex extraction.
        Distinct from the V1 ``parse_judge_response()`` which returns a 0-100 grade.
    """
    cleaned = text.strip()
    try:
        data = json.loads(cleaned)
        verdict_raw = str(data.get("verdict", "")).lower()
        if verdict_raw == "pass":
            verdict = EvalVerdict.PASS
        elif verdict_raw == "fail":
            verdict = EvalVerdict.FAIL
        else:
            verdict = EvalVerdict.UNKNOWN
        score = max(0.0, min(1.0, float(data.get("score", 0.0))))
        reasoning = str(data.get("reasoning", ""))
        return False, verdict, score, reasoning
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Regex fallback for partially malformed JSON
    v_match = re.search(r'"verdict"\s*:\s*"(pass|fail)"', cleaned, re.IGNORECASE)
    s_match = re.search(r'"score"\s*:\s*([0-9.]+)', cleaned)
    r_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', cleaned)
    if v_match and s_match:
        verdict = EvalVerdict.PASS if v_match.group(1).lower() == "pass" else EvalVerdict.FAIL
        score = max(0.0, min(1.0, float(s_match.group(1))))
        reasoning = r_match.group(1) if r_match else ""
        return False, verdict, score, reasoning

    preview = cleaned[:200] if cleaned else "(empty response)"
    logger.warning("parse_v2_judge_response_failed", extra={"preview": preview})
    return True, EvalVerdict.UNKNOWN, 0.0, f"Could not parse: {preview}"


def sanitize_text(text: str) -> str:
    """
    Remove reasoning tags and sanitize text.
    Args:
        text: Input text that may contain reasoning tags.
    Returns:
        Sanitized text with reasoning tags removed and leading/trailing whitespace stripped.
    Notes:
        Uses a compiled regex pattern to remove all occurrences of <think>...</think>,
        including multiline content. Returns empty string for empty input.
        Falls back to basic stripping if an error occurs during processing.
    """
    if not text:
        logger.debug("sanitize_text: Empty input provided")
        return ""
    logger.debug(f"sanitize_text: Input length={len(text)}")
    try:
        cleaned_text = REASONING_TAG_PATTERN.sub("", text)
        logger.debug(f"sanitize_text: Removed reasoning tags - new length={len(cleaned_text)}")
        result = cleaned_text.strip()
        logger.debug(f"sanitize_text: Output length={len(result)}")
        return result
    except re.error as e:
        logger.error(f"sanitize_text: Regex error during sanitization - {e}")
        return text.strip()
    except Exception as e:
        logger.error(f"sanitize_text: Unexpected error during sanitization - {e}", exc_info=True)
        return text.strip()
