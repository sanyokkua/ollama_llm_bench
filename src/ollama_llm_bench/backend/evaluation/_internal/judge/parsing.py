"""Strict-then-lenient judge response parsing (§8 of 08-P_judge_protocol.md)."""

from dataclasses import dataclass
import json
import re

from ollama_llm_bench.backend.domain import Verdict

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_VERDICT_KEY_PATTERN = re.compile(r"verdict[\"']?\s*[:\-]\s*[\"']?(PASS|FAIL)\b", re.IGNORECASE)
_DEFAULT_REASONING = "(no reasoning provided by judge)"
_MAX_REASONING_CHARS = 2000


@dataclass(slots=True, frozen=True)
class _ParsedJudgeResponse:
    """A successfully parsed judge verdict — private to this module (§8)."""

    verdict: Verdict
    reasoning: str


def parse_judge_response(body: str) -> _ParsedJudgeResponse | None:
    """Parse one judge response body strictly, then leniently (§8).

    Args:
        body: The raw judge response text.

    Returns:
        The parsed verdict/reasoning, or ``None`` when both steps fail —
        the response is malformed (§9).
    """
    parsed = _parse_strict(body)
    if parsed is not None:
        return parsed
    return _parse_lenient(body)


def _parse_strict(body: str) -> _ParsedJudgeResponse | None:
    try:
        decoded = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None
    return _extract_from_object(decoded)


def _parse_lenient(body: str) -> _ParsedJudgeResponse | None:
    stripped = _strip_code_fences(body)
    bracketed = _extract_bracketed_object(stripped)
    if bracketed is not None:
        extracted = _try_decode_object(bracketed)
        if extracted is not None:
            return extracted
    return _extract_key_adjacent_token(stripped)


def _try_decode_object(text: str) -> _ParsedJudgeResponse | None:
    try:
        decoded = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return _extract_from_object(decoded)


def _strip_code_fences(body: str) -> str:
    match = _FENCE_PATTERN.search(body)
    return match.group(1) if match else body


def _extract_bracketed_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _extract_from_object(decoded: object) -> _ParsedJudgeResponse | None:
    if not isinstance(decoded, dict):
        return None
    raw_verdict = decoded.get("verdict")
    if not isinstance(raw_verdict, str):
        return None
    normalised = raw_verdict.strip().upper()
    if normalised not in (Verdict.PASS.value.upper(), Verdict.FAIL.value.upper()):
        return None
    verdict = Verdict.PASS if normalised == Verdict.PASS.value.upper() else Verdict.FAIL
    raw_reasoning = decoded.get("reasoning")
    if isinstance(raw_reasoning, str) and raw_reasoning.strip():
        reasoning = raw_reasoning.strip()
    else:
        reasoning = _DEFAULT_REASONING
    return _ParsedJudgeResponse(verdict=verdict, reasoning=reasoning[:_MAX_REASONING_CHARS])


def _extract_key_adjacent_token(text: str) -> _ParsedJudgeResponse | None:
    matches = _VERDICT_KEY_PATTERN.findall(text)
    if len(matches) != 1:
        return None
    verdict = Verdict.PASS if matches[0].upper() == "PASS" else Verdict.FAIL
    reasoning = text.strip()[:_MAX_REASONING_CHARS] or _DEFAULT_REASONING
    return _ParsedJudgeResponse(verdict=verdict, reasoning=reasoning)
