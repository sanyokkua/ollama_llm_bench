"""Unit tests for TaskFileLoader — YAML loading, validation, deduplication, directory scanning."""

from pathlib import Path

import pytest
import yaml

from ollama_llm_bench.backend.core.interfaces import TaskFileLoaderApi
from ollama_llm_bench.backend.core.models import Difficulty, ResponseScope, TaskType
from ollama_llm_bench.backend.services.task_file_loader import TaskFileLoader


def _valid_task(task_id: str = "t1", **overrides: object) -> dict[str, object]:
    """Return a minimal valid V2 task dict."""
    base: dict[str, object] = {
        "task_id": task_id,
        "task_type": "factual_qa",
        "question": "What is 2+2?",
        "golden_answer": "4",
    }
    base.update(overrides)
    return base


def _write_yaml(path: Path, data: object) -> None:
    path.write_text(yaml.dump(data), encoding="utf-8")


@pytest.fixture
def loader() -> TaskFileLoader:
    return TaskFileLoader()


class TestScanDirectory:
    def test_returns_yaml_and_yml_files_sorted_alphabetically(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        (tmp_path / "b_tasks.yaml").touch()
        (tmp_path / "a_tasks.yml").touch()
        (tmp_path / "c_tasks.yaml").touch()

        result = loader.scan_directory(tmp_path)

        assert [p.name for p in result] == ["a_tasks.yml", "b_tasks.yaml", "c_tasks.yaml"]

    def test_excludes_non_yaml_files(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        (tmp_path / "tasks.yaml").touch()
        (tmp_path / "readme.md").touch()
        (tmp_path / "data.json").touch()

        result = loader.scan_directory(tmp_path)

        assert len(result) == 1
        assert result[0].name == "tasks.yaml"

    def test_returns_empty_list_for_empty_directory(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        assert loader.scan_directory(tmp_path) == []


class TestLoadTasksSingleFile:
    def test_loads_single_task_from_list_format(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("task1")])

        tasks = loader.load_tasks([f])

        assert len(tasks) == 1
        assert tasks[0].task_id == "task1"

    def test_loads_single_task_from_dict_format(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, _valid_task("task1"))

        tasks = loader.load_tasks([f])

        assert len(tasks) == 1
        assert tasks[0].task_id == "task1"

    def test_loads_multiple_tasks_from_list(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("t1"), _valid_task("t2"), _valid_task("t3")])

        tasks = loader.load_tasks([f])

        assert len(tasks) == 3
        assert [t.task_id for t in tasks] == ["t1", "t2", "t3"]

    def test_loads_tasks_from_dict_with_tasks_key(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, {"tasks": [_valid_task("t1"), _valid_task("t2")]})

        tasks = loader.load_tasks([f])

        assert len(tasks) == 2

    def test_skips_task_missing_task_id(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        bad = _valid_task("t1")
        del bad["task_id"]
        _write_yaml(f, [bad, _valid_task("t2")])

        tasks = loader.load_tasks([f])

        assert len(tasks) == 1
        assert tasks[0].task_id == "t2"

    def test_skips_task_with_invalid_task_type(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("t1", task_type="not_valid_type"), _valid_task("t2")])

        tasks = loader.load_tasks([f])

        assert len(tasks) == 1
        assert tasks[0].task_id == "t2"

    def test_skips_task_missing_question(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        bad = _valid_task("t1")
        del bad["question"]
        _write_yaml(f, [bad, _valid_task("t2")])

        tasks = loader.load_tasks([f])

        assert len(tasks) == 1
        assert tasks[0].task_id == "t2"

    def test_skips_task_missing_golden_answer(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        bad = _valid_task("t1")
        del bad["golden_answer"]
        _write_yaml(f, [bad, _valid_task("t2")])

        tasks = loader.load_tasks([f])

        assert len(tasks) == 1
        assert tasks[0].task_id == "t2"

    def test_returns_empty_list_for_malformed_yaml(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        f.write_text(": invalid: yaml: [unclosed", encoding="utf-8")

        tasks = loader.load_tasks([f])

        assert tasks == []

    def test_returns_empty_list_for_empty_file(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        f.write_text("", encoding="utf-8")

        tasks = loader.load_tasks([f])

        assert tasks == []

    def test_defaults_difficulty_to_medium_when_absent(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("t1")])

        tasks = loader.load_tasks([f])

        assert tasks[0].difficulty == Difficulty.MEDIUM

    def test_defaults_response_scope_to_contains_when_absent(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("t1")])

        tasks = loader.load_tasks([f])

        assert tasks[0].response_scope == ResponseScope.CONTAINS

    def test_defaults_difficulty_to_medium_on_invalid_value(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("t1", difficulty="legendary")])

        tasks = loader.load_tasks([f])

        assert tasks[0].difficulty == Difficulty.MEDIUM

    def test_defaults_response_scope_to_contains_on_invalid_value(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("t1", response_scope="fuzzy")])

        tasks = loader.load_tasks([f])

        assert tasks[0].response_scope == ResponseScope.CONTAINS

    def test_parses_required_terms_all_sub_keys(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(
            f,
            [
                _valid_task(
                    "t1",
                    required_terms={
                        "exact": ["foo", "bar"],
                        "semantic": ["baz"],
                        "forbidden": ["qux"],
                    },
                )
            ],
        )

        tasks = loader.load_tasks([f])

        rt = tasks[0].required_terms
        assert rt is not None
        assert rt.exact == ("foo", "bar")
        assert rt.semantic == ("baz",)
        assert rt.forbidden == ("qux",)

    def test_required_terms_is_none_when_key_absent(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("t1")])

        tasks = loader.load_tasks([f])

        assert tasks[0].required_terms is None

    def test_parses_optional_language_fields(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(
            f,
            [_valid_task("t1", source_language="en", target_language="fr", source_material="Some text")],
        )

        tasks = loader.load_tasks([f])

        assert tasks[0].source_language == "en"
        assert tasks[0].target_language == "fr"
        assert tasks[0].source_material == "Some text"

    def test_parses_task_type_correctly(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("t1", task_type="code_generation")])

        tasks = loader.load_tasks([f])

        assert tasks[0].task_type == TaskType.CODE_GENERATION

    def test_resets_cache_on_each_load_call(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("t1")])
        loader.load_tasks([f])

        f2 = tmp_path / "tasks2.yaml"
        _write_yaml(f2, [_valid_task("t2")])
        tasks = loader.load_tasks([f2])

        assert len(tasks) == 1
        assert tasks[0].task_id == "t2"


class TestLoadTasksMultipleFiles:
    def test_loads_tasks_from_multiple_files(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f1 = tmp_path / "a.yaml"
        f2 = tmp_path / "b.yaml"
        _write_yaml(f1, [_valid_task("t1"), _valid_task("t2")])
        _write_yaml(f2, [_valid_task("t3")])

        tasks = loader.load_tasks([f1, f2])

        assert len(tasks) == 3
        assert [t.task_id for t in tasks] == ["t1", "t2", "t3"]

    def test_first_occurrence_wins_on_duplicate_task_id(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f1 = tmp_path / "a.yaml"
        f2 = tmp_path / "b.yaml"
        _write_yaml(f1, [_valid_task("t1", question="Original question")])
        _write_yaml(f2, [_valid_task("t1", question="Duplicate question")])

        tasks = loader.load_tasks([f1, f2])

        assert len(tasks) == 1
        assert tasks[0].question == "Original question"

    def test_duplicate_task_id_logs_warning(
        self, tmp_path: Path, loader: TaskFileLoader, caplog: pytest.LogCaptureFixture
    ) -> None:
        f1 = tmp_path / "a.yaml"
        f2 = tmp_path / "b.yaml"
        _write_yaml(f1, [_valid_task("t1")])
        _write_yaml(f2, [_valid_task("t1")])

        loader.load_tasks([f1, f2])

        assert "duplicate_task_id" in caplog.text

    def test_continues_loading_after_bad_file(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f1 = tmp_path / "a.yaml"
        f2 = tmp_path / "b.yaml"
        f1.write_text(": bad yaml [", encoding="utf-8")
        _write_yaml(f2, [_valid_task("t1")])

        tasks = loader.load_tasks([f1, f2])

        assert len(tasks) == 1
        assert tasks[0].task_id == "t1"


class TestGetTask:
    def test_returns_task_after_load(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        f = tmp_path / "tasks.yaml"
        _write_yaml(f, [_valid_task("my_task")])
        loader.load_tasks([f])

        task = loader.get_task("my_task")

        assert task.task_id == "my_task"

    def test_raises_key_error_for_unknown_task_id(self, tmp_path: Path, loader: TaskFileLoader) -> None:
        loader.load_tasks([])

        with pytest.raises(KeyError):
            loader.get_task("nonexistent")


class TestProtocolConformance:
    def test_isinstance_check_passes_against_task_file_loader_api(self) -> None:
        loader = TaskFileLoader()
        assert isinstance(loader, TaskFileLoaderApi)
