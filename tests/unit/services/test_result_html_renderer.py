"""Unit tests for backend/services/result_html_renderer.py."""

from ollama_llm_bench.backend.core.models import BenchmarkResult
from ollama_llm_bench.backend.services.result_html_renderer import build_result_html

_TOKENS: dict[str, str] = {
    "bg_primary": "#1e1e1e",
    "bg_secondary": "#2d2d2d",
    "text_primary": "#ffffff",
    "text_secondary": "#cccccc",
    "text_muted": "#888888",
    "primary": "#4dabf7",
    "border": "#444444",
    "success_text": "#69db7c",
    "failure_text": "#ff6b6b",
    "warning": "#ffd43b",
    "font_sans": "sans-serif",
    "font_mono": "monospace",
}


def _make_result(**kwargs: object) -> BenchmarkResult:
    return BenchmarkResult(**kwargs)  # type: ignore[arg-type]


class TestBuildResultHtml:
    def test_returns_html_string(self) -> None:
        result = _make_result(model_name="llama3:8b", task_id="task_1")
        html = build_result_html(result, _TOKENS)
        assert isinstance(html, str)
        assert "<html>" in html
        assert "</html>" in html

    def test_contains_model_name(self) -> None:
        result = _make_result(model_name="mistral:7b", task_id="t1")
        html = build_result_html(result, _TOKENS)
        assert "mistral:7b" in html

    def test_contains_task_id(self) -> None:
        result = _make_result(model_name="m", task_id="my_task_42")
        html = build_result_html(result, _TOKENS)
        assert "my_task_42" in html

    def test_prompt_section_shown_when_present(self) -> None:
        result = _make_result(user_prompt_sent="What is 2+2?")
        html = build_result_html(result, _TOKENS)
        assert "PROMPT" in html
        assert "What is 2+2?" in html

    def test_prompt_section_absent_when_empty(self) -> None:
        result = _make_result(user_prompt_sent="")
        html = build_result_html(result, _TOKENS)
        assert "PROMPT" not in html

    def test_response_section_shows_sanitized_over_raw(self) -> None:
        result = _make_result(raw_response="raw text", sanitized_response="clean text")
        html = build_result_html(result, _TOKENS)
        assert "clean text" in html

    def test_response_section_falls_back_to_raw(self) -> None:
        result = _make_result(raw_response="raw only", sanitized_response=None)
        html = build_result_html(result, _TOKENS)
        assert "raw only" in html

    def test_no_response_shows_placeholder(self) -> None:
        result = _make_result(raw_response=None, sanitized_response=None)
        html = build_result_html(result, _TOKENS)
        assert "(no response)" in html

    def test_inference_error_shown(self) -> None:
        result = _make_result(has_inference_error=True, inference_error_message="timeout")
        html = build_result_html(result, _TOKENS)
        assert "Inference Error" in html
        assert "timeout" in html

    def test_inference_error_absent_when_none(self) -> None:
        result = _make_result(has_inference_error=False)
        html = build_result_html(result, _TOKENS)
        assert "Inference Error" not in html

    def test_judge_section_shown_when_score_present(self) -> None:
        result = _make_result(judge_score=0.85, judge_reasoning="Good answer")
        html = build_result_html(result, _TOKENS)
        assert "0.85" in html

    def test_judge_section_absent_when_no_score(self) -> None:
        result = _make_result(judge_score=None)
        html = build_result_html(result, _TOKENS)
        assert "Judge score" not in html

    def test_cosine_section_shown_when_similarity_present(self) -> None:
        result = _make_result(cosine_similarity=0.9234, cosine_strategy="mean")
        html = build_result_html(result, _TOKENS)
        assert "0.9234" in html

    def test_cosine_section_absent_when_none(self) -> None:
        result = _make_result(cosine_similarity=None)
        html = build_result_html(result, _TOKENS)
        assert "Cosine similarity" not in html

    def test_missing_terms_shown(self) -> None:
        import json

        result = _make_result(missing_exact_terms=json.dumps(["term1", "term2"]))
        html = build_result_html(result, _TOKENS)
        assert "Missing required terms" in html
        assert "term1" in html

    def test_token_colors_applied(self) -> None:
        result = _make_result(model_name="m")
        html = build_result_html(result, _TOKENS)
        assert _TOKENS["bg_primary"] in html
        assert _TOKENS["font_sans"] in html

    def test_html_special_chars_escaped(self) -> None:
        result = _make_result(model_name="model<script>", task_id="task&1")
        html = build_result_html(result, _TOKENS)
        assert "<script>" not in html
        assert "&amp;" in html or "&lt;" in html

    def test_verdict_pass_uses_success_color(self) -> None:
        result = _make_result(final_verdict="pass")
        html = build_result_html(result, _TOKENS)
        assert _TOKENS["success_text"] in html

    def test_verdict_fail_uses_failure_color(self) -> None:
        result = _make_result(final_verdict="fail")
        html = build_result_html(result, _TOKENS)
        assert _TOKENS["failure_text"] in html
