"""Colocated tests for canonical field ordering — see STORY-031-AC-2."""

from pathlib import Path

from ruamel.yaml import YAML

from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter

_read_safe_yaml = YAML(typ="safe")


def _write_source_file(tmp_path: Path, task_yaml: str) -> Path:
    source_path = tmp_path / "source.yaml"
    source_path.write_text(f"schema_version: 1\ntasks:\n{task_yaml}", encoding="utf-8")
    return source_path


def test_formatter_emits_canonical_field_order(tmp_path: Path) -> None:
    """Proves: STORY-031-AC-2

    A task with a non-canonical key order (YF-5 unknown key, YF-6 missing
    optional fields, YF-7 ``required_terms`` sub-order) is rewritten to the
    fixed canonical order on save: a present canonical key moves to its
    canonical position, an absent canonical key is never inserted, and an
    unknown key is preserved after the last canonical key present.
    """
    task_yaml = (
        "  - difficulty: hard\n"
        "    question: What is 2 + 2?\n"
        "    custom_note: keep me\n"
        "    task_id: sample_task\n"
        "    required_terms:\n"
        "      semantic:\n"
        "        - addition\n"
        "      exact:\n"
        '        - "4"\n'
    )
    source_path = _write_source_file(tmp_path, task_yaml)
    formatter = make_yaml_formatter()
    document = formatter.load_document(str(source_path))

    target_path = tmp_path / "target.yaml"
    result = formatter.save(document=document, target_path=str(target_path), format_on_save=True)
    assert result.succeeded

    loaded = _read_safe_yaml.load(target_path.read_text(encoding="utf-8"))
    task = loaded["tasks"][0]

    assert list(task.keys()) == [
        "task_id",
        "difficulty",
        "question",
        "required_terms",
        "custom_note",
    ]
    assert list(task["required_terms"].keys()) == ["exact", "semantic"]
