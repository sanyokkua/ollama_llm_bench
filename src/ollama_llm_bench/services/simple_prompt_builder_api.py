import logging
from typing import Tuple, override

from ollama_llm_bench.core.interfaces import BenchmarkTaskApi, PromptBuilderApi
from ollama_llm_bench.core.models import BenchmarkResult
from ollama_llm_bench.core.prompt_constants import SYSTEM_PROMPT, USER_PROMPT

logger = logging.getLogger(__name__)


class SimplePromptBuilderApi(PromptBuilderApi):
    """
    Concrete implementation of PromptBuilderApi that constructs prompts for benchmarking and judging.
    Uses template substitution to generate judge prompts based on task and result data.
    """

    def __init__(self, *, task_api: BenchmarkTaskApi):
        """
        Initialize the prompt builder.

        Args:
            task_api: Interface for retrieving benchmark tasks.
        """
        super().__init__(task_api=task_api)
        logger.debug("Initialized PromptBuilderApiImpl")

    @override
    def build_prompt(self, task_id: str) -> str:
        """
        Construct a user-facing prompt for executing a benchmark task.

        Args:
            task_id: Identifier of the task to build a prompt for.

        Returns:
            The question text of the specified task.

        Raises:
            Exception: If the task cannot be retrieved.
        """
        logger.debug("Building prompt for task ID: %s", task_id)
        try:
            task = self._task_api.get_task(task_id)
            logger.debug("Successfully retrieved task with ID: %s", task_id)
            return task.question
        except Exception as e:
            logger.error("Failed to build prompt for task ID %s: %s", task_id, str(e))
            raise

    @override
    def build_judge_prompt(self, benchmark_result: BenchmarkResult) -> Tuple[str, str]:
        """
        Construct a prompt used to evaluate (judge) a benchmark result.

        Args:
            benchmark_result: Result to be evaluated, containing model response and task ID.

        Returns:
            Tuple containing (user_prompt, system_prompt) for the judge model.

        Raises:
            Exception: If task retrieval fails or template substitution encounters an error.
        """
        task_id = benchmark_result.task_id
        logger.debug("Building judge prompt for task ID: %s", task_id)

        try:
            task = self._task_api.get_task(task_id)
            logger.debug("Successfully retrieved task with ID: %s", task_id)
        except Exception as e:
            logger.error("Failed to retrieve task with ID %s for judge prompt: %s", task_id, str(e))
            raise

        format_data = {
            'question': task.question,
            'most_expected': task.expected_answer.most_expected,
            'good_answer': task.expected_answer.good_answer,
            'pass_option': task.expected_answer.pass_option,
            'incorrect_direction': task.incorrect_direction,
            'answer': benchmark_result.llm_response or "",
            'category': task.category,
            'sub_category': task.sub_category
        }

        try:
            # Perform regex-based replacements
            user_prompt = USER_PROMPT
            for key, value in format_data.items():
                pattern = "".join(['{', key, '}'])
                user_prompt = user_prompt.replace(pattern, value)

            logger.debug("Successfully built judge prompt for task ID: %s", task_id)
            return user_prompt, SYSTEM_PROMPT
        except KeyError as e:
            logger.error("Template key error: %s", str(e))
            raise ValueError(f"Missing required template key: {str(e)}") from None
        except Exception as e:
            logger.error("Failed to build judge prompt for task ID %s: %s", task_id, str(e))
            raise
