"""Public factories for the task-file loader and validator."""

import icontract

from ollama_llm_bench.backend.task_files._internal.loader_impl import _TaskFileLoaderImpl
from ollama_llm_bench.backend.task_files._internal.validator_impl import _TaskFileValidatorImpl
from ollama_llm_bench.backend.task_files.protocols import TaskFileLoader, TaskFileValidator

__all__: list[str] = ["make_task_file_loader", "make_task_file_validator"]


@icontract.ensure(lambda result: result is not None)
def make_task_file_loader() -> TaskFileLoader:
    """Construct the loader-tolerant ``TaskFileLoader`` (§6.2).

    Returns:
        A stateless, synchronous ``TaskFileLoader`` that skips malformed
        individual tasks rather than raising for them.
    """
    return _TaskFileLoaderImpl()


@icontract.ensure(lambda result: result is not None)
def make_task_file_validator() -> TaskFileValidator:
    """Construct the editor-strict ``TaskFileValidator`` (`14_VALIDATION_CASCADE.md`).

    Returns:
        A stateless, synchronous ``TaskFileValidator`` that reports every
        problem found as a ``ValidationIssue`` rather than skipping any.
    """
    return _TaskFileValidatorImpl()
