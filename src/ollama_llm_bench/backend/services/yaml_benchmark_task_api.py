import logging
from pathlib import Path
from typing import override

import yaml

from ollama_llm_bench.backend.core.interfaces import BenchmarkTaskApi
from ollama_llm_bench.backend.core.models import (
    BenchmarkTask,
    Difficulty,
    RequiredTerms,
    ResponseScope,
    TaskType,
)

logger = logging.getLogger(__name__)


class YamlBenchmarkTaskApi(BenchmarkTaskApi):
    """Concrete implementation of BenchmarkTaskApi that loads tasks from YAML files.

    Supports V2 task YAML format with caching for performance. Skips malformed
    tasks with a warning rather than raising, so a single bad file does not
    prevent other tasks from loading.
    """

    def __init__(self, *, task_folder_path: Path):
        """Initialize the YAML-based task loader.

        Args:
            task_folder_path: Directory containing YAML task definition files.
        """
        super().__init__(task_folder_path=task_folder_path)
        self._tasks_cache: list[BenchmarkTask] = []
        self._task_cache_map: dict[str, BenchmarkTask] = {}

    @override
    def load_tasks(self) -> list[BenchmarkTask]:
        """Load all benchmark tasks from YAML files in the configured directory.

        Returns:
            List of loaded benchmark tasks. Returns cached results on subsequent calls.
        """
        if self._tasks_cache:
            logger.debug("Returning %d cached benchmark tasks", len(self._tasks_cache))
            return self._tasks_cache

        logger.debug("Loading benchmark tasks from %s", self._task_folder_path)
        self._tasks_cache = []
        self._task_cache_map = {}

        file_count = 0
        for file_path in sorted(self._task_folder_path.iterdir()):
            if not file_path.is_file() or file_path.suffix not in (".yaml", ".yml"):
                continue

            file_count += 1
            self._load_file(file_path)

        logger.info(
            "Loaded %d benchmark tasks from %d files",
            len(self._tasks_cache),
            file_count,
        )
        return self._tasks_cache

    def _load_file(self, file_path: Path) -> None:
        """Parse a single YAML file and add valid tasks to the cache.

        Args:
            file_path: Path to the YAML file to load.
        """
        try:
            with file_path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except Exception as e:
            logger.error("Failed to parse YAML file %s: %s", file_path, e)
            return

        if not data:
            logger.debug("YAML file %s is empty, skipping", file_path)
            return

        if isinstance(data, dict) and "tasks" in data:
            tasks_data = data["tasks"]
        elif isinstance(data, list):
            tasks_data = data  # backward compat: list at root
        else:
            logger.warning("Unexpected YAML structure in %s", file_path)
            return

        if not isinstance(tasks_data, list):
            logger.warning("'tasks' key in %s is not a list, skipping", file_path)
            return

        for task_data in tasks_data:
            if not isinstance(task_data, dict):
                logger.warning("Skipping non-dict task entry in %s", file_path)
                continue
            task = self._parse_task(task_data, file_path)
            if task is not None:
                self._tasks_cache.append(task)
                self._task_cache_map[task.task_id] = task

    def _parse_task(self, task_data: dict[str, object], file_path: Path) -> BenchmarkTask | None:
        """Build a BenchmarkTask from a parsed YAML dict.

        Args:
            task_data: Parsed task dictionary from YAML.
            file_path: Source file path used in warning messages.

        Returns:
            A BenchmarkTask instance, or None if the task is malformed.
        """
        required_str_fields = (
            "task_id",
            "category",
            "sub_category",
            "question",
            "golden_answer",
            "pass_criteria",
            "fail_criteria",
        )
        for field in required_str_fields:
            if field not in task_data:
                logger.warning(
                    "Missing required field '%s' in task from %s (task_id=%s)",
                    field,
                    file_path,
                    task_data.get("task_id", "<unknown>"),
                )
                return None

        try:
            task_type = TaskType(str(task_data["task_type"]))
        except (KeyError, ValueError):
            logger.warning(
                "Invalid or missing 'task_type' in task %s from %s",
                task_data.get("task_id", "<unknown>"),
                file_path,
            )
            return None

        difficulty: Difficulty | None = None
        if "difficulty" in task_data:
            try:
                difficulty = Difficulty(str(task_data["difficulty"]))
            except ValueError:
                logger.warning(
                    "Invalid 'difficulty' value '%s' in task %s from %s",
                    task_data["difficulty"],
                    task_data.get("task_id"),
                    file_path,
                )

        response_scope: ResponseScope | None = None
        if "response_scope" in task_data:
            try:
                response_scope = ResponseScope(str(task_data["response_scope"]))
            except ValueError:
                logger.warning(
                    "Invalid 'response_scope' value '%s' in task %s from %s",
                    task_data["response_scope"],
                    task_data.get("task_id"),
                    file_path,
                )

        required_terms = self._parse_required_terms(task_data)

        return BenchmarkTask(
            task_id=str(task_data["task_id"]),
            category=str(task_data["category"]),
            sub_category=str(task_data["sub_category"]),
            task_type=task_type,
            question=str(task_data["question"]),
            golden_answer=str(task_data["golden_answer"]),
            pass_criteria=str(task_data["pass_criteria"]),
            fail_criteria=str(task_data["fail_criteria"]),
            difficulty=difficulty,
            response_scope=response_scope,
            required_terms=required_terms,
            source_language=str(task_data["source_language"]) if "source_language" in task_data else None,
            target_language=str(task_data["target_language"]) if "target_language" in task_data else None,
            source_material=str(task_data["source_material"]) if "source_material" in task_data else None,
        )

    def _parse_required_terms(self, task_data: dict[str, object]) -> RequiredTerms | None:
        """Parse the optional required_terms block from a task dict.

        Args:
            task_data: Parsed task dictionary.

        Returns:
            A RequiredTerms instance if the block is present, otherwise None.
        """
        rt_data = task_data.get("required_terms")
        if not isinstance(rt_data, dict):
            return None
        return RequiredTerms(
            exact=tuple(rt_data.get("exact") or []),
            semantic=tuple(rt_data.get("semantic") or []),
            forbidden=tuple(rt_data.get("forbidden") or []),
        )

    @override
    def get_task(self, task_id: str) -> BenchmarkTask:
        """Retrieve a specific benchmark task by its identifier.

        Args:
            task_id: Unique ID of the task to retrieve.

        Returns:
            The requested benchmark task.

        Raises:
            ValueError: If no task with the given ID exists.
        """
        if not self._tasks_cache:
            self.load_tasks()

        if task_id not in self._task_cache_map:
            logger.error("Task with ID %s not found", task_id)
            raise ValueError(f"Task with ID {task_id} not found")

        logger.debug("Retrieved task with ID %s", task_id)
        return self._task_cache_map[task_id]
