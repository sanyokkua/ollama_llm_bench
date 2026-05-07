"""V2 benchmark task loader supporting multiple YAML files and directory scanning."""

import logging
from pathlib import Path
from typing import Any

import yaml

from ollama_llm_bench.backend.core.models import (
    BenchmarkTask,
    Difficulty,
    RequiredTerms,
    ResponseScope,
    TaskType,
)

logger = logging.getLogger(__name__)

_YAML_EXTENSIONS: frozenset[str] = frozenset({".yaml", ".yml"})


class TaskFileLoader:
    """Load V2 benchmark tasks from YAML files or directories.

    Deduplicates by task_id (first occurrence wins), validates required fields,
    and caches results for get_task() lookup. Never raises from load_tasks() or
    scan_directory() — malformed files are logged and skipped.

    Attributes:
        _cache: Map of task_id to BenchmarkTask populated by load_tasks().
    """

    def __init__(self) -> None:
        self._cache: dict[str, BenchmarkTask] = {}

    def scan_directory(self, directory: Path) -> list[Path]:
        """Return all .yaml and .yml files in directory, sorted alphabetically.

        Non-recursive — only files directly inside the given directory are returned.

        Args:
            directory: Directory to scan.

        Returns:
            Sorted list of YAML file paths; empty if directory contains no YAML files.
        """
        return sorted(p for p in directory.iterdir() if p.suffix in _YAML_EXTENSIONS and p.is_file())

    def load_tasks(self, file_paths: list[Path]) -> list[BenchmarkTask]:
        """Load tasks from a list of YAML files, deduplicating by task_id.

        Resets the internal cache on each call. Malformed files are skipped
        with an error log. Duplicate task_ids log a warning and the second
        occurrence is discarded (first-occurrence-wins policy).

        Args:
            file_paths: List of YAML file paths to load.

        Returns:
            Ordered list of valid, deduplicated BenchmarkTask instances; empty if none
            were successfully loaded.
        """
        self._cache = {}
        tasks: list[BenchmarkTask] = []
        for path in file_paths:
            for task in self._load_file(path):
                if task.task_id in self._cache:
                    logger.warning(
                        "duplicate_task_id",
                        extra={"task_id": task.task_id, "file": str(path)},
                    )
                    continue
                self._cache[task.task_id] = task
                tasks.append(task)
        return tasks

    def get_task(self, task_id: str) -> BenchmarkTask:
        """Retrieve a loaded task by ID.

        Args:
            task_id: Unique task identifier.

        Returns:
            The BenchmarkTask with the given ID.

        Raises:
            KeyError: If no task with that ID was loaded via load_tasks().
        """
        return self._cache[task_id]

    def _load_file(self, file_path: Path) -> list[BenchmarkTask]:
        try:
            with file_path.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except Exception as exc:
            logger.error("yaml_load_failed", extra={"file": str(file_path), "error": str(exc)})
            return []

        if not raw:
            logger.debug("yaml_file_empty", extra={"file": str(file_path)})
            return []

        if isinstance(raw, dict) and "tasks" in raw:
            entries_raw: object = raw["tasks"]
        elif isinstance(raw, list):
            entries_raw = raw
        elif isinstance(raw, dict):
            entries_raw = [raw]
        else:
            logger.warning("yaml_unexpected_structure", extra={"file": str(file_path)})
            return []

        if not isinstance(entries_raw, list):
            logger.warning("yaml_tasks_not_a_list", extra={"file": str(file_path)})
            return []

        result: list[BenchmarkTask] = []
        for entry in entries_raw:
            if not isinstance(entry, dict):
                logger.warning("yaml_non_dict_entry", extra={"file": str(file_path)})
                continue
            task = self._parse_task(entry, file_path)
            if task is not None:
                result.append(task)
        return result

    def _parse_task(self, data: dict[str, Any], file_path: Path) -> BenchmarkTask | None:
        task_id = str(data.get("task_id", "")).strip()
        if not task_id:
            logger.warning("missing_task_id", extra={"file": str(file_path)})
            return None

        raw_type = str(data.get("task_type", ""))
        try:
            task_type = TaskType(raw_type)
        except ValueError:
            logger.warning(
                "invalid_task_type",
                extra={"task_id": task_id, "value": raw_type, "file": str(file_path)},
            )
            return None

        question = str(data.get("question", "")).strip()
        if not question:
            logger.warning("missing_question", extra={"task_id": task_id, "file": str(file_path)})
            return None

        golden_answer = str(data.get("golden_answer", "")).strip()
        if not golden_answer:
            logger.warning("missing_golden_answer", extra={"task_id": task_id, "file": str(file_path)})
            return None

        difficulty = self._parse_difficulty(data, task_id, file_path)
        response_scope = self._parse_response_scope(data, task_id, file_path)
        required_terms = self._parse_required_terms(data)

        return BenchmarkTask(
            task_id=task_id,
            category=str(data.get("category", "")),
            sub_category=str(data.get("sub_category", "")),
            task_type=task_type,
            question=question,
            golden_answer=golden_answer,
            pass_criteria=str(data.get("pass_criteria", "")),
            fail_criteria=str(data.get("fail_criteria", "")),
            difficulty=difficulty,
            response_scope=response_scope,
            required_terms=required_terms,
            source_language=str(data["source_language"]) if "source_language" in data else None,
            target_language=str(data["target_language"]) if "target_language" in data else None,
            source_material=str(data["source_material"]) if "source_material" in data else None,
            fail_example=str(data["fail_example"]) if "fail_example" in data else None,
        )

    def _parse_difficulty(self, data: dict[str, Any], task_id: str, file_path: Path) -> Difficulty:
        if "difficulty" not in data:
            return Difficulty.MEDIUM
        try:
            return Difficulty(str(data["difficulty"]))
        except ValueError:
            logger.warning(
                "invalid_difficulty",
                extra={"task_id": task_id, "value": data["difficulty"], "file": str(file_path)},
            )
            return Difficulty.MEDIUM

    def _parse_response_scope(self, data: dict[str, Any], task_id: str, file_path: Path) -> ResponseScope:
        if "response_scope" not in data:
            return ResponseScope.CONTAINS
        try:
            return ResponseScope(str(data["response_scope"]))
        except ValueError:
            logger.warning(
                "invalid_response_scope",
                extra={"task_id": task_id, "value": data["response_scope"], "file": str(file_path)},
            )
            return ResponseScope.CONTAINS

    def _parse_required_terms(self, data: dict[str, Any]) -> RequiredTerms | None:
        if "required_terms" not in data:
            return None
        rt = data["required_terms"]
        if not isinstance(rt, dict):
            return None
        return RequiredTerms(
            exact=tuple(str(t) for t in (rt.get("exact") or [])),
            semantic=tuple(str(t) for t in (rt.get("semantic") or [])),
            forbidden=tuple(str(t) for t in (rt.get("forbidden") or [])),
        )
