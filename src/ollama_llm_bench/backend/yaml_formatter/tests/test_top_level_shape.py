"""General coverage of Form B/Form C top-level shape normalization.

Not tied to one acceptance criterion — exercises `10_Domain_and_Data/
04_YAML_TASK_FORMAT.md` §3's Form B/Form C acceptance for the formatter's
``load_document``/``save`` pair, which STORY-031-AC-1..AC-3's own Form-A test
fixtures do not otherwise reach.
"""

from pathlib import Path

from ruamel.yaml import YAML

from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.backend.yaml_formatter.models import SaveFailureReason

_read_safe_yaml = YAML(typ="safe")


def test_save_normalizes_form_b_bare_sequence_to_form_a(tmp_path: Path) -> None:
    """A loaded Form B (bare sequence) file is always saved as Form A."""
    source_path = tmp_path / "form_b.yaml"
    source_path.write_text("- task_id: bare_one\n  question: What is 1 + 1?\n", encoding="utf-8")

    formatter = make_yaml_formatter()
    document = formatter.load_document(str(source_path))
    target_path = tmp_path / "target.yaml"
    result = formatter.save(document=document, target_path=str(target_path), format_on_save=True)

    assert result.succeeded
    loaded = _read_safe_yaml.load(target_path.read_text(encoding="utf-8"))
    assert list(loaded.keys()) == ["tasks"]
    assert loaded["tasks"][0]["task_id"] == "bare_one"


def test_save_normalizes_form_c_single_mapping_to_form_a(tmp_path: Path) -> None:
    """A loaded Form C (single bare task mapping) file is always saved as Form A."""
    source_path = tmp_path / "form_c.yaml"
    source_path.write_text("task_id: single_task\nquestion: What is 2 + 2?\n", encoding="utf-8")

    formatter = make_yaml_formatter()
    document = formatter.load_document(str(source_path))
    target_path = tmp_path / "target.yaml"
    result = formatter.save(document=document, target_path=str(target_path), format_on_save=True)

    assert result.succeeded
    loaded = _read_safe_yaml.load(target_path.read_text(encoding="utf-8"))
    assert list(loaded.keys()) == ["tasks"]
    assert [task["task_id"] for task in loaded["tasks"]] == ["single_task"]


def test_save_to_nonexistent_directory_reports_directory_not_writable(tmp_path: Path) -> None:
    """A target directory that does not exist fails cleanly with a typed reason."""
    formatter = make_yaml_formatter()
    empty_document = formatter.load_document(str(_write_empty(tmp_path)))
    target_path = tmp_path / "missing_dir" / "target.yaml"

    result = formatter.save(
        document=empty_document, target_path=str(target_path), format_on_save=True
    )

    assert result.succeeded is False
    assert result.failure_reason == SaveFailureReason.DIRECTORY_NOT_WRITABLE


def _write_empty(tmp_path: Path) -> Path:
    source_path = tmp_path / "empty.yaml"
    source_path.write_text("tasks: []\n", encoding="utf-8")
    return source_path
