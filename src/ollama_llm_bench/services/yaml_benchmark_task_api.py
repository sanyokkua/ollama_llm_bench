import logging
from pathlib import Path
from typing import List, override

import yaml

from src.ollama_llm_bench.core.interfaces import BenchmarkTaskApi
from src.ollama_llm_bench.core.models import BenchmarkTask, BenchmarkTaskAnswer

logger = logging.getLogger(__name__)


class YamlBenchmarkTaskApi(BenchmarkTaskApi):

    def __init__(self, *, task_folder_path: Path):
        super().__init__(task_folder_path=task_folder_path)
        self._tasks_cache: List[BenchmarkTask] = []
        self._task_cache_map = { }

    @override
    def load_tasks(self) -> List[BenchmarkTask]:
        if self._tasks_cache:
            logger.debug("Returning %d cached benchmark tasks", len(self._tasks_cache))
            return self._tasks_cache

        logger.debug("Loading benchmark tasks from %s", self._task_folder_path)
        self._tasks_cache = []
        self._task_cache_map = { }

        task_count = 0
        for file_path in self._task_folder_path.iterdir():
            if not file_path.is_file():
                continue

            if file_path.suffix not in ('.yaml', '.yml'):
                continue

            try:
                with open(file_path, 'r') as file:
                    data = yaml.safe_load(file)

                if not data:
                    logger.debug("YAML file %s is empty, skipping", file_path)
                    continue

                # Handle both single task and list of tasks
                tasks_data = data if isinstance(data, list) else [data]

                for task_data in tasks_data:
                    if not isinstance(task_data, dict):
                        logger.warning("Skipping invalid task format in %s", file_path)
                        continue

                    try:
                        answer_data = task_data.get('expected_answer', { })
                        answer = BenchmarkTaskAnswer(
                            most_expected=answer_data.get('most_expected', ''),
                            good_answer=answer_data.get('good_answer', ''),
                            pass_option=answer_data.get('pass_option', ''),
                        )

                        task = BenchmarkTask(
                            task_id=task_data['task_id'],
                            category=task_data['category'],
                            sub_category=task_data['sub_category'],
                            question=task_data['question'],
                            expected_answer=answer,
                            incorrect_direction=task_data['incorrect_direction'],
                        )

                        self._tasks_cache.append(task)
                        self._task_cache_map[task.task_id] = task
                        task_count += 1

                    except KeyError as e:
                        logger.warning("Missing required field %s in task from %s", e, file_path)
                    except Exception as e:
                        logger.warning("Error processing task from %s: %s", file_path, str(e))

            except Exception as e:
                logger.error("Failed to parse YAML file %s: %s", file_path, str(e))
                continue

        logger.info("Loaded %d benchmark tasks from %d files", task_count, len(self._tasks_cache))
        # TODO: Remove Limit
        return self._tasks_cache[:5]

    @override
    def get_task(self, task_id: str) -> BenchmarkTask:
        if not self._tasks_cache:
            self.load_tasks()

        if task_id not in self._task_cache_map:
            logger.error("Task with ID %s not found", task_id)
            raise ValueError(f"Task with ID {task_id} not found")

        logger.debug("Retrieved task with ID %s", task_id)
        return self._task_cache_map[task_id]
