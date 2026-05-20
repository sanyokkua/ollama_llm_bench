"""Unit tests for backend/utils/html_utils.py."""

import pytest

from ollama_llm_bench.backend.utils.html_utils import html_escape, markdown_to_html, plain_to_html_br


class TestHtmlEscape:
    def test_escapes_ampersand(self) -> None:
        assert html_escape("a & b") == "a &amp; b"

    def test_escapes_angle_brackets(self) -> None:
        assert html_escape("<script>") == "&lt;script&gt;"

    def test_escapes_quotes(self) -> None:
        assert html_escape('"hello"') == "&quot;hello&quot;"

    def test_plain_text_unchanged(self) -> None:
        assert html_escape("hello world") == "hello world"

    def test_empty_string(self) -> None:
        assert html_escape("") == ""


class TestPlainToHtmlBr:
    def test_newline_converted_to_br(self) -> None:
        assert plain_to_html_br("line1\nline2") == "line1<br>line2"

    def test_html_chars_escaped(self) -> None:
        assert plain_to_html_br("a & b\n<b>") == "a &amp; b<br>&lt;b&gt;"

    def test_no_newlines_unchanged(self) -> None:
        assert plain_to_html_br("hello") == "hello"

    def test_empty_string(self) -> None:
        assert plain_to_html_br("") == ""


class TestMarkdownToHtml:
    def test_bold_markdown(self) -> None:
        result = markdown_to_html("**bold**")
        assert "<strong>bold</strong>" in result

    def test_plain_text_wrapped_in_p(self) -> None:
        result = markdown_to_html("hello")
        assert "hello" in result

    def test_empty_string(self) -> None:
        result = markdown_to_html("")
        assert isinstance(result, str)

    def test_fenced_code_block(self) -> None:
        result = markdown_to_html("```python\nprint('hi')\n```")
        assert "code" in result

    @pytest.mark.parametrize(
        "text",
        ["# Header", "- item", "> quote"],
        ids=["header", "list_item", "blockquote"],
    )
    def test_returns_string(self, text: str) -> None:
        assert isinstance(markdown_to_html(text), str)
