import logging
from typing import Optional

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from ollama_llm_bench.core.interfaces import BenchmarkTaskApi, DataApi, LLMApi, PromptBuilderApi
from ollama_llm_bench.core.models import BenchmarkResult, BenchmarkResultStatus, BenchmarkRunStatus, ReporterStatusMsg
from ollama_llm_bench.utils.text_utils import parse_judge_response


class BenchmarkExecutionTask(QRunnable):
    class Signals(QObject):
        """Only the three required signals as per your specification"""
        status_changed = pyqtSignal(bool)  # is_running
        log_message = pyqtSignal(str)  # string messages that should be logged
        progress = pyqtSignal(ReporterStatusMsg)  # status of the current run

    def __init__(
        self,
        run_id: int,
        data_api: DataApi,
        task_api: BenchmarkTaskApi,
        prompt_builder_api: PromptBuilderApi,
        llm_api: LLMApi,
    ):
        super().__init__()
        self.run_id = run_id
        self.data_api = data_api
        self.task_api = task_api
        self.prompt_builder_api = prompt_builder_api
        self.llm_api = llm_api

        # Set up logger
        self.logger = logging.getLogger(f"{__name__}.BenchmarkExecutionTask[{run_id}]")
        self.signals = self.Signals()
        self._stop_requested = False
        self.setAutoDelete(True)

        # Execution state for progress tracking
        self._total_tasks = 0
        self._completed_tasks = 0
        self._current_model = ""
        self._current_task_id = ""

    def _log_msg_to_global_logger(self, msg: str) -> None:
        self.signals.log_message.emit(msg)

    def _notify(self, message: str):
        self.logger.debug(message)
        self._log_msg_to_global_logger.emit(message)

    def _notify_warn(self, message: str):
        self.logger.warning(message)
        self._log_msg_to_global_logger.emit(message)

    def _log_stop_requested(self) -> None:
        self._notify(f"Benchmark run #{self.run_id} was stopped by user request. Incomplete tasks will resume on next run.")

    def stop(self) -> None:
        if not self._stop_requested:
            self._stop_requested = True
            self._notify("Stopping benchmark execution...")

    def is_stopped(self) -> bool:
        return self._stop_requested

    def run(self) -> None:
        self.logger.info(f"Starting benchmark execution for run_id={self.run_id}")
        try:
            self.signals.status_changed.emit(True)
            self._execute_benchmark()
            self.logger.info(f"Benchmark execution completed for run_id={self.run_id}")
        except Exception as e:
            import traceback
            error_msg = f"Execution error: {str(e)}\n{traceback.format_exc()}"
            self._notify_warn(error_msg)
        finally:
            self.signals.status_changed.emit(False)
            self.logger.debug("Benchmark execution thread completed")

    def _execute_benchmark(self) -> None:
        is_success = self._execute_benchmark_for_tasks()
        if not is_success:
            return

        is_success = self._execute_judging_for_tasks()
        if not is_success:
            return

        self._notify(f"Finished benchmark for run: {self.run_id}.")

    def _execute_benchmark_for_tasks(self) -> bool:
        try:
            self._notify("Starting benchmark stage...")
            if self._should_stop():
                return False

            all_tasks = self.data_api.retrieve_benchmark_results_for_run(self.run_id)
            tasks_to_run = self.data_api.retrieve_benchmark_results_for_run_with_status(run_id=self.run_id,
                                                                                        status=BenchmarkResultStatus.NOT_COMPLETED,
                                                                                        )

            self._total_tasks = len(all_tasks)
            self._completed_tasks = len(all_tasks) - len(tasks_to_run)
            self._update_progress(self._completed_tasks, self._total_tasks)

            if not self._has_tasks_to_continue():
                return False

            model_to_tasks = self._load_and_group_tasks_by_models(tasks_to_run)
            self._update_progress()

            # 3. Process each model-task combination
            for model_name, tasks_list in model_to_tasks.items():
                if self._should_stop():
                    return False

                self._current_model = model_name
                self._notify(f"Starting execution for model: {model_name}")

                # Warm up the model
                if not self._warmup_model(model_name=model_name):
                    return False

                # Process each task for this model

                self._update_progress(self._completed_tasks, self._total_tasks)

                for task in tasks_list:
                    if self._should_stop():
                        return False
                    self._current_task_id = task.task_id
                    try:
                        self._notify(f"Processing task {task.task_id} for model {model_name}")
                        self._execute_benchmark_for_task_on_llm(model_name, task)
                        self._notify(f"Finished task {task.task_id} for model {model_name}.")
                    except Exception as e:
                        self._notify_warn(f"Failed to process task {task.task_id} for model {model_name}: {str(e)}")
                        self._update_failed_task(task, e)
                    finally:
                        self._completed_tasks += 1
                        self._update_progress(self._completed_tasks, self._total_tasks)
                if self._should_stop():
                    return False

        except Exception as e:
            self._notify_warn(f"Failed to execute benchmark for tasks: {e}")
            return False
        return True

    def _execute_judging_for_tasks(self) -> bool:
        try:
            self._notify("Starting evaluation with judge model...")
            # Retrieve updated list of tasks
            all_tasks = self.data_api.retrieve_benchmark_results_for_run(self.run_id)
            tasks_to_run = self.data_api.retrieve_benchmark_results_for_run_with_status(run_id=self.run_id,
                                                                                        status=BenchmarkResultStatus.WAITING_FOR_JUDGE,
                                                                                        )

            self._total_tasks = len(all_tasks)
            self._completed_tasks = len(all_tasks) - len(tasks_to_run)
            run = self.data_api.retrieve_benchmark_run(self.run_id)
            judge_model = run.judge_model
            self._current_model = judge_model
            self._notify(f"Judge model: {judge_model}. Tasks total: {self._total_tasks}. Judged tasks: {self._completed_tasks}.")
            self._update_progress(self._completed_tasks, self._total_tasks)

            if not self._has_tasks_to_continue():
                return False

            if self._total_tasks > 0:
                self._notify(f"Will be evaluated {self._total_tasks} results with judge model {judge_model}")
                if not self._warmup_model(judge_model):
                    return False

                for task in tasks_to_run:
                    if self._should_stop():
                        return False

                    try:
                        self._current_task_id = task.task_id
                        self._notify(f"Current task {task.task_id} with response from model: {task.model_name}.")
                        self._judge_task_by_llm(task, judge_model)
                    except Exception as e:
                        self._notify_warn(f"Error evaluating task {task.task_id}: {str(e)}")
                        self._update_judge_failed(task, e)
                    finally:
                        self._completed_tasks += 1
                        self._update_progress(self._completed_tasks, self._total_tasks)

        except Exception as e:
            self._notify_warn(f"Failed to execute judging for tasks: {e}")
            return False
        return True

    def _should_stop(self) -> bool:
        if self.is_stopped():
            self._log_stop_requested()
            return True
        return False

    def _has_tasks_to_continue(self) -> bool:
        if self._total_tasks > 0:
            return True
        self._notify("No tasks found for benchmark execution")
        return False

    def _load_and_group_tasks_by_models(self, all_tasks: list[BenchmarkResult]) -> dict[str, list[BenchmarkResult]]:
        model_to_tasks = { }
        for task in all_tasks:
            if task.model_name not in model_to_tasks:
                model_to_tasks[task.model_name] = []
            model_to_tasks[task.model_name].append(task)
        self._notify(f"Found {self._total_tasks} tasks across {len(model_to_tasks)} models")
        return model_to_tasks

    def _warmup_model(self, model_name: str) -> bool:
        try:
            self.logger.debug(f"Warming up model: {model_name}")
            if not self.llm_api.warm_up(model_name):
                self._notify_warn(f"Warning: Failed to warm up model: {model_name}")
                self._log_stop_requested()
                return False
        except Exception as e:
            self._notify_warn(f"Error warming up model {model_name}: {str(e)}")
            self._log_stop_requested()
            return False
        return True

    def _execute_benchmark_for_task_on_llm(self, model_name: str, task: BenchmarkResult):
        user_prompt = self.prompt_builder_api.build_prompt(task.task_id)
        response = self.llm_api.inference(
            model_name=model_name,
            user_prompt=user_prompt,
            system_prompt='',
            on_llm_response=self._log_msg_to_global_logger,
            on_is_stop_signal=self.is_stopped,
        )
        # Update task result
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

    def _judge_task_by_llm(self, task, judge_model):
        user_prompt, system_prompt = self.prompt_builder_api.build_judge_prompt(task)
        response = self.llm_api.inference(
            model_name=judge_model,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            on_llm_response=self._log_msg_to_global_logger,
            on_is_stop_signal=self.is_stopped,
        )
        # Parse judge response
        has_error, grade, reason = parse_judge_response(response.llm_response)
        if has_error:
            self._notify_warn(f"Parsing of Judge response failed for task {task.task_id}.")
        else:
            self._notify(f"Judge response for task {task.task_id}. Grade: {grade}. Reason: {reason}")
        # Update task result with evaluation
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

    def _update_judge_failed(self, task, e):
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
            error_message=f"Evaluation failed: {str(e)}",
        )
        self.data_api.update_benchmark_result(updated_task)

    def _update_failed_task(self, task: BenchmarkResult, e: Exception):
        updated_task = BenchmarkResult(
            result_id=task.result_id,
            run_id=task.run_id,
            task_id=task.task_id,
            model_name=task.model_name,
            status=BenchmarkResultStatus.FAILED,
            llm_response='',
            time_taken_ms=None,
            tokens_generated=None,
            evaluation_score=None,
            evaluation_reason=None,
            error_message=str(e),
        )
        self.data_api.update_benchmark_result(updated_task)

    def _update_progress(self, completed: Optional[int] = None, total: Optional[int] = None) -> None:
        model_completed_val = completed or self._completed_tasks
        model_total_val = total or self._total_tasks

        status_msg = ReporterStatusMsg(
            total_amount_of_tasks=self._total_tasks,
            completed_amount_of_tasks=self._completed_tasks,
            current_model_name=self._current_model,
            current_task_id=self._current_task_id,
            total_amount_of_tasks_for_model=model_total_val,
            completed_amount_of_tasks_for_model=model_completed_val,
            run_status=BenchmarkRunStatus.NOT_COMPLETED,
            task_status=BenchmarkResultStatus.NOT_COMPLETED,
        )

        # Emit progress signal
        self.signals.progress.emit(status_msg)

        # Log progress
        progress_pct = (self._completed_tasks / self._total_tasks * 100) if self._total_tasks > 0 else 0
        self.logger.debug(
            f"Progress: {self._completed_tasks}/{self._total_tasks} tasks completed "
            f"({progress_pct:.1f}%) - Model: {self._current_model}, Task: {self._current_task_id}",
        )


