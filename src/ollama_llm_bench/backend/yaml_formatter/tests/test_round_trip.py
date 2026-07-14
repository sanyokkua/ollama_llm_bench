"""Colocated property test for round-trip determinism — see STORY-031-AC-1 (YF-20)."""

from pathlib import Path
from typing import Any
from uuid import uuid4

from hypothesis import HealthCheck, given, settings, strategies as st
import pytest
from ruamel.yaml import YAML

from ollama_llm_bench.backend.task_files import make_task_file_loader
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter

_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789_"
_TEXT_ALPHABET = st.characters(
    whitelist_categories=("L", "N", "P", "Zs"), min_codepoint=0x20, max_codepoint=0x2FFF
)
_LANGUAGES = ("en", "uk", "fr", "de", "es")


def _text(*, min_size: int = 0, max_size: int = 80) -> st.SearchStrategy[str]:
    return st.text(alphabet=_TEXT_ALPHABET, min_size=min_size, max_size=max_size)


def _nonempty_term() -> st.SearchStrategy[str]:
    return _text(min_size=1, max_size=30).filter(lambda value: value.strip() != "")


@st.composite
def _raw_task(draw: st.DrawFn, *, index: int) -> dict[str, Any]:
    """Draw one YAML-serializable raw task dict guaranteed to load cleanly."""
    suffix = draw(st.text(alphabet=_ID_ALPHABET, min_size=1, max_size=20))
    question = draw(_text(min_size=1, max_size=200).filter(lambda value: value.strip() != ""))
    return {
        "task_id": f"task_{index}_{suffix}",
        "question": question,
        "category": draw(_text(max_size=40)),
        "sub_category": draw(_text(max_size=40)),
        "cosine_enabled": draw(st.booleans()),
        "difficulty": draw(st.sampled_from(["easy", "medium", "hard"])),
        "pass_criteria": draw(_text(max_size=100)),
        "fail_criteria": draw(_text(max_size=100)),
        "golden_answer": draw(st.one_of(st.none(), _text(min_size=1, max_size=150))),
        "source_language": draw(st.one_of(st.none(), st.sampled_from(_LANGUAGES))),
        "target_language": draw(st.one_of(st.none(), st.sampled_from(_LANGUAGES))),
        "source_material": draw(st.one_of(st.none(), _text(max_size=80))),
        "fail_example": draw(st.one_of(st.none(), _text(max_size=80))),
        "required_terms": {
            "exact": draw(st.lists(_nonempty_term(), max_size=3, unique=True)),
            "semantic": draw(st.lists(_nonempty_term(), max_size=3, unique=True)),
            "forbidden": draw(st.lists(_nonempty_term(), max_size=3, unique=True)),
        },
    }


@st.composite
def _raw_task_file(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Draw a whole file's worth of raw tasks, each with a distinct ``task_id``."""
    task_count = draw(st.integers(min_value=1, max_value=5))
    return [draw(_raw_task(index=index)) for index in range(task_count)]


def _write_raw_task_file(path: Path, raw_tasks: list[dict[str, Any]]) -> None:
    """Serialize ``raw_tasks`` to ``path`` with ``ruamel.yaml`` directly.

    Deliberately independent of ``YamlFormatter`` (the code under test) — the
    fixture must not become tautological.
    """
    dumper = YAML(typ="safe")
    dumper.default_flow_style = False
    document = {"schema_version": 1, "tasks": raw_tasks}
    with path.open("w", encoding="utf-8") as handle:
        dumper.dump(document, handle)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(raw_tasks=_raw_task_file())
def test_load_serialize_load_is_identity_modulo_reorder(
    tmp_path: Path, raw_tasks: list[dict[str, Any]]
) -> None:
    """Proves: STORY-031-AC-1

    Loading a valid task file, then round-tripping it through
    ``YamlFormatter.load_document``/``save`` with ``format_on_save=True``,
    then loading the result again, yields the same task list — the round
    trip is an identity on task content modulo canonical field reordering
    (YF-20).
    """
    source_path = tmp_path / f"source_{uuid4().hex}.yaml"
    _write_raw_task_file(source_path, raw_tasks)

    loader = make_task_file_loader()
    formatter = make_yaml_formatter()

    tasks_before = loader.load(str(source_path))
    assert len(tasks_before) == len(raw_tasks)  # sanity: nothing was unexpectedly skipped

    document = formatter.load_document(str(source_path))
    target_path = tmp_path / f"target_{uuid4().hex}.yaml"
    save_result = formatter.save(
        document=document, target_path=str(target_path), format_on_save=True
    )
    assert save_result.succeeded

    tasks_after = loader.load(str(target_path))

    assert tasks_after == tasks_before


@pytest.mark.slow
def test_round_trip_is_deterministic_when_run_twice(tmp_path: Path) -> None:
    """Proves: STORY-031-AC-1

    A concrete regression pin for YF-20: formatting the formatter's own
    output a second time changes nothing further.
    """
    source_path = tmp_path / "source.yaml"
    _write_raw_task_file(
        source_path,
        [
            {
                "task_id": "regression_task",
                "question": "What is the capital of France?",
                "golden_answer": "Paris",
                "required_terms": {"exact": ["Paris"], "semantic": [], "forbidden": []},
            }
        ],
    )

    formatter = make_yaml_formatter()
    first_target = tmp_path / "first.yaml"
    formatter.save(
        document=formatter.load_document(str(source_path)),
        target_path=str(first_target),
        format_on_save=True,
    )
    second_target = tmp_path / "second.yaml"
    formatter.save(
        document=formatter.load_document(str(first_target)),
        target_path=str(second_target),
        format_on_save=True,
    )

    assert first_target.read_text(encoding="utf-8") == second_target.read_text(encoding="utf-8")
