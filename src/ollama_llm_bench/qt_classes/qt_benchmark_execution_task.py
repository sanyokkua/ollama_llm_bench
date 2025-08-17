import logging
import time
from collections import defaultdict

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from ollama_llm_bench.core.interfaces import BenchmarkTaskApi, DataApi, LLMApi, PromptBuilderApi
from ollama_llm_bench.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    ReporterStatusMsg,
)
from ollama_llm_bench.core.stages_constants import (
    STAGE_BENCHMARKING,
    STAGE_FAILED,
    STAGE_FINISHED,
    STAGE_INITIALIZING,
    STAGE_JUDGING,
)
from ollama_llm_bench.utils.text_utils import parse_judge_response
from ollama_llm_bench.utils.time_utils import format_elapsed_time


class BenchmarkExecutionTask(QRunnable):
    """
    Runnable task for executing a full benchmark run including inference and judging phases.
    Runs in a background thread to avoid blocking the UI.
    """

    class Signals(QObject):
        """
        Signals emitted by the benchmark execution task for progress and status updates.
        """
        status_changed = pyqtSignal(bool)  # is_running
        log_message = pyqtSignal(str)  # log text
        progress = pyqtSignal(ReporterStatusMsg)  # run status

    def __init__(
        self,
        run_id: int,
        data_api: DataApi,
        task_api: BenchmarkTaskApi,
        prompt_builder_api: PromptBuilderApi,
        llm_api: LLMApi,
    ):
        """
        Initialize the benchmark execution task.

        Args:
            run_id: Identifier of the benchmark run to execute.
            data_api: Interface for accessing benchmark data.
            task_api: Interface for retrieving benchmark tasks.
            prompt_builder_api: Interface for constructing prompts.
            llm_api: Interface for interacting with LLMs.
        """
        super().__init__()
        self.run_id = run_id
        self.data_api = data_api
        self.task_api = task_api
        self.prompt_builder_api = prompt_builder_api
        self.llm_api = llm_api

        self.logger = logging.getLogger(f"{__name__}.BenchmarkExecutionTask[{run_id}]")
        self.signals = self.Signals()
        self._stop_requested = False
        self.setAutoDelete(True)

        # Progress tracking
        self._total_tasks = 0
        self._completed_tasks = 0
        self._current_model = ""
        self._current_task_id = ""
        self._stage = STAGE_INITIALIZING
        self._start_time: float = 0
        self._end_time: float = 0

    def _log_msg_to_global_logger(self, msg: str) -> None:
        """
        Forward log message to the global logging system.

        Args:
            msg: Message to log.
        """
        self.signals.log_message.emit(msg)

    def _notify(self, message: str) -> None:
        """
        Log a debug message and emit it to the global logger.

        Args:
            message: Message to log and emit.
        """
        self.logger.debug(message)
        self._log_msg_to_global_logger(message)

    def _notify_warn(self, message: str) -> None:
        """
        Log a warning message and emit it to the global logger.

        Args:
            message: Warning message to log and emit.
        """
        self.logger.warning(message)
        self._log_msg_to_global_logger(message)

    def _log_stop_requested(self) -> None:
        """
        Notify that benchmark execution was stopped by user request.
        """
        self._notify(
            f"Benchmark run #{self.run_id} was stopped by user request. "
            f"Incomplete tasks will resume on next run.",
        )

    def stop(self) -> None:
        """
        Request cancellation of the benchmark execution.
        """
        if not self._stop_requested:
            self._stop_requested = True
            self._notify("Stopping benchmark execution...")

    def is_stopped(self) -> bool:
        """
        Check if a stop has been requested.

        Returns:
            True if stop was requested, False otherwise.
        """
        return self._stop_requested

    def _should_stop(self) -> bool:
        """
        Check if execution should stop and log the reason if so.

        Returns:
            True if execution should stop, False otherwise.
        """
        if self.is_stopped():
            self._log_stop_requested()
            return True
        return False

    def run(self) -> None:
        """
        Execute the benchmark run in the background thread.
        Handles both benchmarking and judging stages with error recovery.
        """
        self.logger.info(f"Starting benchmark execution for run_id={self.run_id}")
        self._update_progress()
        try:
            self.signals.status_changed.emit(True)
            self._start_time = time.time()
            self._execute_benchmark()
            self._stage = STAGE_FINISHED
            self.logger.info(f"Benchmark execution completed for run_id={self.run_id}")
        except Exception as e:
            import traceback
            error_msg = f"Execution error: {e}\n{traceback.format_exc()}"
            self._notify_warn(error_msg)
            self._stage = STAGE_FAILED
        finally:
            self._current_task_id = ''
            self._current_model = ''
            self._end_time = time.time()
            self._stop_requested = True
            self.signals.status_changed.emit(False)
            self.logger.debug("Benchmark execution thread completed")
            self._update_progress()
            self._notify(format_elapsed_time(self._start_time, self._end_time))

    def _execute_benchmark(self) -> None:
        """
        Execute both benchmarking and judging stages sequentially.
        """
        if not self._execute_benchmark_for_tasks():
            return
        self._update_progress()
        if not self._execute_judging_for_tasks():
            return
        self._update_progress()
        self._notify(f"Finished benchmark for run: {self.run_id}.")

    def _execute_benchmark_for_tasks(self) -> bool:
        """
        Execute the benchmarking stage: run inference for all pending tasks.

        Returns:
            True if stage completed successfully, False if stopped or failed.
        """
        try:
            self._notify("Starting benchmark stage...")
            self._stage = STAGE_BENCHMARKING
            if self._should_stop():
                return False

            all_tasks = self.data_api.retrieve_benchmark_results_for_run(self.run_id)
            tasks_to_run = self.data_api.retrieve_benchmark_results_for_run_with_status(
                run_id=self.run_id,
                status=BenchmarkResultStatus.NOT_COMPLETED,
            )

            self._total_tasks = len(all_tasks)
            self._completed_tasks = len(all_tasks) - len(tasks_to_run)
            self._update_progress()

            if not tasks_to_run:
                self._notify("No tasks to run for benchmark stage.")
                return False

            model_to_tasks = self._group_tasks_by_model(tasks_to_run)

            for model_name, tasks_for_model in model_to_tasks.items():
                if self._should_stop():
                    return False

                self._current_model = model_name
                self._notify(f"Starting execution for model: {model_name}")
                self._update_progress()

                if not self._warmup_model(model_name):
                    return False

                for task in tasks_for_model:
                    if self._should_stop():
                        return False
                    self._current_task_id = task.task_id
                    try:
                        self._notify(f"Processing task {task.task_id} for model {model_name}")
                        self._execute_benchmark_task(model_name, task)
                        self._notify(f"Finished task {task.task_id} for model {model_name}.")
                    except Exception as e:
                        self._notify_warn(f"Failed to process task {task.task_id} for model {model_name}: {e}")
                        self._update_failed_task(task, e)
                    finally:
                        self._completed_tasks += 1
                        self._update_progress()

        except Exception as e:
            self._notify_warn(f"Failed to execute benchmark for tasks: {e}")
            return False
        return True

    def _execute_benchmark_task(self, model_name: str, task: BenchmarkResult) -> None:
        """
        Execute inference for a single benchmark task.

        Args:
            model_name: Name of the model to benchmark.
            task: Benchmark task to execute.

        Raises:
            Exception: If inference fails or task update fails.
        """
        user_prompt = self.prompt_builder_api.build_prompt(task.task_id)
        response = self.llm_api.inference(
            model_name=model_name,
            user_prompt=user_prompt,
            system_prompt="",
            on_llm_response=self._log_msg_to_global_logger,
            on_is_stop_signal=self.is_stopped,
        )

        updated_task = BenchmarkResult(
            result_id=task.result_id,
            run_id=task.run_id,
            task_id=task.task_id,
            model_name=task.model_name,
            status=BenchmarkResultStatus.WAITING_FOR_JUDGE,
            llm_response=response.llm_response,
            time_taken_ms=response.time_taken_ms,
            tokens_generated=response.tokens_generated,
            evaluation_score=None,
            evaluation_reason=None,
            error_message=None,
        )
        self.data_api.update_benchmark_result(updated_task)
        self.logger.info(
            f"Completed task {task.task_id} for model {model_name} "
            f"({response.time_taken_ms}ms, {response.tokens_generated} tokens)",
        )

    def _execute_judging_for_tasks(self) -> bool:
        """
        Execute the judging stage: evaluate all benchmark results with the judge model.

        Returns:
            True if stage completed successfully, False if stopped or failed.
        """
        try:
            self._notify("Starting evaluation with judge model...")
            self._stage = STAGE_JUDGING

            all_tasks = self.data_api.retrieve_benchmark_results_for_run(self.run_id)
            tasks_to_judge = self.data_api.retrieve_benchmark_results_for_run_with_status(
                run_id=self.run_id,
                status=BenchmarkResultStatus.WAITING_FOR_JUDGE,
            )

            self._total_tasks = len(all_tasks)
            self._completed_tasks = len(all_tasks) - len(tasks_to_judge)
            run = self.data_api.retrieve_benchmark_run(self.run_id)
            judge_model = run.judge_model
            self._current_model = judge_model

            self._notify(
                f"Judge model: {judge_model}. "
                f"Tasks total: {self._total_tasks}. Judged tasks: {self._completed_tasks}.",
            )
            self._update_progress()

            if not tasks_to_judge:
                self._notify("No tasks to judge.")
                return False

            self._notify(f"Evaluating {len(tasks_to_judge)} results with judge model {judge_model}")
            if not self._warmup_model(judge_model):
                return False

            for task in tasks_to_judge:
                if self._should_stop():
                    return False
                self._current_task_id = task.task_id
                try:
                    self._notify(f"Evaluating task {task.task_id} (model: {task.model_name})")
                    self._judge_task(task, judge_model)
                except Exception as e:
                    self._notify_warn(f"Error evaluating task {task.task_id}: {e}")
                    self._update_judge_failed(task, e)
                finally:
                    self._completed_tasks += 1
                    self._update_progress()

        except Exception as e:
            self._notify_warn(f"Failed to execute judging for tasks: {e}")
            return False
        return True

    def _judge_task(self, task: BenchmarkResult, judge_model: str) -> None:
        """
        Evaluate a benchmark result using the judge model.

        Args:
            task: Benchmark result to evaluate.
            judge_model: Name of the model to use for judging.

        Raises:
            Exception: If judging fails or result update fails.
        """
        user_prompt, system_prompt = self.prompt_builder_api.build_judge_prompt(task)
        response = self.llm_api.inference(
            model_name=judge_model,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            on_llm_response=self._log_msg_to_global_logger,
            on_is_stop_signal=self.is_stopped,
            is_judge_mode=True,
        )

        has_error, grade, reason = parse_judge_response(response.llm_response)
        if has_error:
            self._notify_warn(f"Parsing of Judge response failed for task {task.task_id}.")
        else:
            self._notify(f"Judge response for task {task.task_id}: Grade={grade}, Reason={reason}")

        updated_task = BenchmarkResult(
            result_id=task.result_id,
            run_id=task.run_id,
            task_id=task.task_id,
            model_name=task.model_name,
            status=BenchmarkResultStatus.COMPLETED,
            llm_response=task.llm_response,
            time_taken_ms=task.time_taken_ms,
            tokens_generated=task.tokens_generated,
            evaluation_score=grade,
            evaluation_reason=reason,
            error_message=None,
        )
        self.data_api.update_benchmark_result(updated_task)

    def _group_tasks_by_model(self, tasks: list[BenchmarkResult]) -> dict[str, list[BenchmarkResult]]:
        """
        Group benchmark tasks by model name for batched execution.

        Args:
            tasks: List of tasks to group.

        Returns:
            Dictionary mapping model names to lists of tasks.
        """
        grouped = defaultdict(list)
        for task in tasks:
            grouped[task.model_name].append(task)
        self._notify(f"Found {len(tasks)} pending tasks across {len(grouped)} models")
        return dict(grouped)

    def _warmup_model(self, model_name: str) -> bool:
        """
        Load and initialize a model before use to reduce inference latency.

        Args:
            model_name: Name of the model to warm up.

        Returns:
            True if warm-up succeeded, False otherwise.
        """
        try:
            self.logger.debug(f"Warming up model: {model_name}")
            if not self.llm_api.warm_up(model_name):
                self._notify_warn(f"Failed to warm up model: {model_name}")
                self._log_stop_requested()
                return False
        except Exception as e:
            self._notify_warn(f"Error warming up model {model_name}: {e}")
            self._log_stop_requested()
            return False
        return True

    def _update_failed_task(self, task: BenchmarkResult, e: Exception) -> None:
        """
        Update task status to failed with error information.

        Args:
            task: Task that failed.
            e: Exception that caused the failure.
        """
        updated_task = BenchmarkResult(
            result_id=task.result_id,
            run_id=task.run_id,
            task_id=task.task_id,
            model_name=task.model_name,
            status=BenchmarkResultStatus.FAILED,
            llm_response=task.llm_response,
            time_taken_ms=task.time_taken_ms,
            tokens_generated=task.tokens_generated,
            evaluation_score=None,
            evaluation_reason=None,
            error_message=str(e),
        )
        self.data_api.update_benchmark_result(updated_task)

    def _update_judge_failed(self, task: BenchmarkResult, e: Exception) -> None:
        """
        Update judging task status to failed with error information.

        Args:
            task: Task whose evaluation failed.
            e: Exception that caused the failure.
        """
        updated_task = BenchmarkResult(
            result_id=task.result_id,
            run_id=task.run_id,
            task_id=task.task_id,
            model_name=task.model_name,
            status=BenchmarkResultStatus.FAILED,
            llm_response=task.llm_response,
            time_taken_ms=task.time_taken_ms,
            tokens_generated=task.tokens_generated,
            evaluation_score=None,
            evaluation_reason=None,
            error_message=f"Evaluation failed: {e}",
        )
        self.data_api.update_benchmark_result(updated_task)

    def _update_progress(self) -> None:
        """
        Emit current progress status to subscribed listeners.
        """
        end_time = self._end_time if self._end_time > 0 else time.time()
        status_msg = ReporterStatusMsg(
            current_run_id=self.run_id,
            current_task=self._current_task_id,
            current_model=self._current_model,
            current_stage=self._stage,
            tasks_total=self._total_tasks,
            tasks_completed=self._completed_tasks,
            start_time_ms=self._start_time,
            end_time_ms=end_time,
        )
        self.signals.progress.emit(status_msg)

        pct = (self._completed_tasks / self._total_tasks * 100) if self._total_tasks else 0
        self.logger.debug(
            f"Progress: {self._completed_tasks}/{self._total_tasks} "
            f"({pct:.1f}%) - Model: {self._current_model}, Task: {self._current_task_id}",
        )
