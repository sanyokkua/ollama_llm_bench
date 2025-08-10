import json
import logging
from typing import Callable, Optional, override

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from ollama_llm_bench.core.interfaces import BenchmarkFlowApi, BenchmarkTaskApi, DataApi, LLMApi, PromptBuilderApi
from ollama_llm_bench.core.models import BenchmarkResult, BenchmarkResultStatus, BenchmarkRunStatus, ReporterStatusMsg
from ollama_llm_bench.qt_classes.meta_class import MetaQObjectABC


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

    def stop(self) -> None:
        """Request graceful termination"""
        if not self._stop_requested:
            self._stop_requested = True
            self.logger.info("Stop requested for benchmark execution")
            self.signals.log_message.emit("Stopping benchmark execution...")

    def is_stopped(self) -> bool:
        return self._stop_requested

    def run(self) -> None:
        """Executes in worker thread - NEVER call directly!"""
        self.logger.info(f"Starting benchmark execution for run_id={self.run_id}")
        try:
            self.signals.status_changed.emit(True)
            self._execute_benchmark()
            self.logger.info(f"Benchmark execution completed for run_id={self.run_id}")
        except Exception as e:
            import traceback
            error_msg = f"Execution error: {str(e)}\n{traceback.format_exc()}"
            self.logger.error(error_msg)
            self.signals.log_message.emit(error_msg)
        finally:
            self.signals.status_changed.emit(False)
            self.logger.debug("Benchmark execution thread completed")

    def _execute_benchmark(self) -> None:
        """Core execution logic running in worker thread"""
        try:
            self._update_progress(0, 100)
            # 1. Load all tasks and organize by model
            all_tasks = self.data_api.retrieve_benchmark_results_for_run(self.run_id)
            self._total_tasks = len(all_tasks)

            if self._total_tasks == 0:
                self.logger.warning("No tasks found for benchmark execution")
                self.signals.log_message.emit("No tasks found for benchmark execution")
                return

            # Group tasks by model
            model_to_tasks = { }
            for task in all_tasks:
                if task.model_name not in model_to_tasks:
                    model_to_tasks[task.model_name] = []
                model_to_tasks[task.model_name].append(task)

            self.logger.info(f"Found {self._total_tasks} tasks across {len(model_to_tasks)} models")
            self.signals.log_message.emit(f"Found {self._total_tasks} tasks across {len(model_to_tasks)} models")

            # 2. Initialize progress tracking
            self._completed_tasks = 0
            self._update_progress()

            # 3. Process each model-task combination
            for model_name, tasks_list in model_to_tasks.items():
                if self.is_stopped():
                    self._handle_stop_requested()
                    return

                self._current_model = model_name
                self.logger.info(f"Starting execution for model: {model_name}")
                self.signals.log_message.emit(f"Starting execution for model: {model_name}")

                # Warm up the model
                try:
                    self.logger.debug(f"Warming up model: {model_name}")
                    if not self.llm_api.warm_up(model_name):
                        self.logger.warning(f"Failed to warm up model: {model_name}")
                        self.signals.log_message.emit(f"Warning: Failed to warm up model: {model_name}")
                except Exception as e:
                    self.logger.error(f"Error warming up model {model_name}: {str(e)}")
                    self.signals.log_message.emit(f"Error warming up model {model_name}: {str(e)}")

                if self.is_stopped():
                    self._handle_stop_requested()
                    return

                # Process each task for this model
                model_total = len(tasks_list)
                model_completed = 0
                for task in tasks_list:
                    if self.is_stopped():
                        break

                    self._current_task_id = task.task_id
                    self.logger.debug(f"Processing task {task.task_id} for model {model_name}")

                    # Skip completed tasks
                    if task.status == BenchmarkResultStatus.COMPLETED:
                        self._completed_tasks += 1
                        model_completed += 1
                        self._update_progress(model_completed, model_total)
                        continue

                    try:
                        # Build and execute prompt
                        self.signals.log_message.emit(f"Processing task {task.task_id} for model {model_name}")
                        self.logger.info(f"Processing task {task.task_id} for model {model_name}")
                        self._update_progress(model_completed, model_total)

                        user_prompt = self.prompt_builder_api.build_prompt(task.task_id)
                        response = self.llm_api.inference(
                            model_name=model_name,
                            user_prompt=user_prompt,
                            system_prompt='',
                            on_llm_response=self.log_msg_to_global_logger,
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

                        # Update progress
                        self._completed_tasks += 1
                        model_completed += 1
                        self._update_progress(model_completed, model_total)

                        self.logger.info(
                            f"Completed task {task.task_id} for model {model_name} "
                            f"({response.time_taken_ms}ms, {response.tokens_generated} tokens)",
                        )

                    except Exception as e:
                        self.logger.error(f"Error processing task {task.task_id} for model {model_name}: {str(e)}")
                        self.signals.log_message.emit(
                            f"Error processing task {task.task_id} for model {model_name}: {str(e)}",
                        )

                        # Update task as failed
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

                        # Still count as completed for progress
                        self._completed_tasks += 1
                        model_completed += 1
                        self._update_progress(model_completed, model_total)

            # 4. Judge results if not stopped
            if self.is_stopped():
                self._handle_stop_requested()
                return

            self.signals.log_message.emit("Starting evaluation with judge model...")
            self.logger.info("Starting evaluation with judge model...")

            # Retrieve updated list of tasks
            all_tasks = self.data_api.retrieve_benchmark_results_for_run(self.run_id)
            run = self.data_api.retrieve_benchmark_run(self.run_id)
            judge_model = run.judge_model

            # Reset progress tracking for judging phase
            self._completed_tasks = 0
            self._total_tasks = len([t for t in all_tasks if t.status == BenchmarkResultStatus.WAITING_FOR_JUDGE])

            if self._total_tasks > 0:
                self.signals.log_message.emit(f"Evaluating {self._total_tasks} results with judge model {judge_model}")
                self.logger.info(f"Evaluating {self._total_tasks} results with judge model {judge_model}")

                for task in all_tasks:
                    if self.is_stopped():
                        self._handle_stop_requested()
                        return

                    if task.status != BenchmarkResultStatus.WAITING_FOR_JUDGE:
                        continue

                    try:
                        self._current_task_id = task.task_id
                        self._current_model = task.model_name
                        self.logger.debug(f"Evaluating task {task.task_id} for model {task.model_name} with judge {judge_model}")

                        user_prompt, system_prompt = self.prompt_builder_api.build_judge_prompt(task)
                        response = self.llm_api.inference(
                            model_name=judge_model,
                            user_prompt=user_prompt,
                            system_prompt=system_prompt,
                            on_llm_response=self.log_msg_to_global_logger,
                        )

                        # Parse judge response
                        try:
                            data = json.loads(response.llm_response)
                            reason = data.get("reason", "")
                            grade = float(data.get("grade", 0.0))

                            self.logger.info(f"Task {task.task_id} graded: {grade} - {reason[:100]}...")
                            self.signals.log_message.emit(f"Task {task.task_id} graded: {grade} - {reason[:50]}...")
                        except (json.JSONDecodeError, ValueError, TypeError) as e:
                            self.logger.error(f"Failed to parse judge response for task {task.task_id}: {str(e)}")
                            self.logger.debug(f"Judge response: {response.llm_response}")
                            self.signals.log_message.emit(
                                f"Warning: Failed to parse judge response for task {task.task_id}: {str(e)}",
                            )
                            reason = "Failed to parse judge response"
                            grade = 0.0

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

                        # Update progress
                        self._completed_tasks += 1
                        self._update_progress()

                    except Exception as e:
                        self.logger.error(f"Error evaluating task {task.task_id}: {str(e)}")
                        self.signals.log_message.emit(f"Error evaluating task {task.task_id}: {str(e)}")

                        # Update task as failed evaluation
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

                        # Still count as completed for progress
                        self._completed_tasks += 1
                        self._update_progress()

            # 5. Finalize run - no status change needed, just log completion
            self.logger.info(f"Benchmark run #{self.run_id} completed")
            self.signals.log_message.emit("Benchmark run completed")

        except Exception as e:
            self.logger.exception("Critical error during benchmark execution")
            raise e

    def _update_progress(self, model_completed: Optional[int] = None, model_total: Optional[int] = None) -> None:
        """Update progress and emit signal with current status"""
        # Calculate model-specific progress if provided
        model_completed_val = model_completed or self._completed_tasks
        model_total_val = model_total or self._total_tasks

        # Create status message
        status_msg = ReporterStatusMsg(
            total_amount_of_tasks=self._total_tasks,
            completed_amount_of_tasks=self._completed_tasks,
            current_model_name=self._current_model,
            current_task_id=self._current_task_id,
            total_amount_of_tasks_for_model=model_total_val,
            completed_amount_of_tasks_for_model=model_completed_val,
            run_status=BenchmarkRunStatus.NOT_COMPLETED,  # Always NOT_COMPLETED while running
            task_status=BenchmarkResultStatus.COMPLETED,  # Status of the CURRENT task being processed
        )

        # Emit progress signal
        self.signals.progress.emit(status_msg)

        # Log progress
        progress_pct = (self._completed_tasks / self._total_tasks * 100) if self._total_tasks > 0 else 0
        self.logger.debug(
            f"Progress: {self._completed_tasks}/{self._total_tasks} tasks completed "
            f"({progress_pct:.1f}%) - Model: {self._current_model}, Task: {self._current_task_id}",
        )

    def _handle_stop_requested(self) -> None:
        """Handle graceful termination when stop is requested"""
        self.logger.info("Handling stop request for benchmark execution")
        self.signals.log_message.emit(f"Benchmark run #{self.run_id} was stopped by user request")

        # No need to update run status - it will remain NOT_COMPLETED
        # The system will automatically resume incomplete tasks on next run
        self.signals.log_message.emit("Benchmark execution stopped. Incomplete tasks will resume on next run.")

    def log_msg_to_global_logger(self, msg: str) -> None:
        self.signals.log_message.emit(msg)


class QtBenchmarkFlowApi(QObject, BenchmarkFlowApi, metaclass=MetaQObjectABC):
    benchmark_status_events = pyqtSignal(bool)  # running/stopped
    benchmark_output_events = pyqtSignal(str)  # log messages
    benchmark_progress_events = pyqtSignal(ReporterStatusMsg)  # progress updates

    def __init__(
        self,
        *,
        data_api: DataApi,
        task_api: BenchmarkTaskApi,
        prompt_builder_api: PromptBuilderApi,
        llm_api: LLMApi,
        thread_pool: QThreadPool,
    ):
        super().__init__(
            data_api=data_api,
            task_api=task_api,
            prompt_builder_api=prompt_builder_api,
            llm_api=llm_api,
        )
        self._thread_pool = thread_pool

        # Execution state
        self._current_task: Optional[BenchmarkExecutionTask] = None
        self._current_run_id: Optional[int] = None

    @override
    def start_execution(self, run_id: int) -> None:
        """Start a new benchmark execution (non-blocking)"""
        if self.is_running():
            raise RuntimeError("A benchmark is already running")

        # Validate run exists
        try:
            run = self._data_api.retrieve_benchmark_run(run_id)
            if run.status != BenchmarkRunStatus.NOT_COMPLETED:
                raise ValueError(f"Benchmark run #{run_id} is not in NOT_COMPLETED state")
        except Exception as e:
            raise ValueError(f"Invalid run_id: {run_id}") from e

        # Create execution task
        task = BenchmarkExecutionTask(
            run_id=run_id,
            data_api=self._data_api,
            task_api=self._task_api,
            prompt_builder_api=self._prompt_builder_api,
            llm_api=self._llm_api,
        )

        # Disconnect any previous task signals (shouldn't happen, but safe)
        self._disconnect_current_task()

        # Connect task signals to our class signals
        self._connect_task_signals(task)

        # Store reference and start in thread pool
        self._current_task = task
        self._current_run_id = run_id
        self._thread_pool.start(task)

        # Notify status change (should be True)
        self.benchmark_status_events.emit(self.is_running())

    @override
    def stop_execution(self) -> None:
        """Request graceful termination of current execution"""
        if not self.is_running():
            raise RuntimeError("No benchmark is currently running")

        self._current_task.stop()

    @override
    def is_running(self) -> bool:
        """Check if any benchmark is currently executing"""
        return self._current_task is not None and not self._current_task.is_stopped()

    @override
    def get_current_run_id(self) -> Optional[int]:
        """Get ID of currently executing run, if any"""
        return self._current_run_id

    @override
    def subscribe_to_benchmark_status_events(self, callback: Callable[[bool], None]) -> None:
        """Subscribe to execution status changes (running vs not running)"""
        self.benchmark_status_events.connect(callback)
        # Immediately notify of current status
        callback(self.is_running())

    @override
    def subscribe_to_benchmark_output_events(self, callback: Callable[[str], None]) -> None:
        """Subscribe to log/output messages from benchmark execution"""
        self.benchmark_output_events.connect(callback)

    @override
    def subscribe_to_benchmark_progress_events(self, callback: Callable[[ReporterStatusMsg], None]) -> None:
        """Subscribe to progress updates"""
        self.benchmark_progress_events.connect(callback)
        # If currently running, send current progress
        if self.is_running() and self._current_task:
            # In a real implementation, you'd have access to current progress state
            # This would require tracking progress state in the flow API
            pass

    def _connect_task_signals(self, task: BenchmarkExecutionTask) -> None:
        """Connect a task's signals to our class signals"""
        task.signals.status_changed.connect(self.benchmark_status_events)
        task.signals.log_message.connect(self.benchmark_output_events)
        task.signals.progress.connect(self.benchmark_progress_events)

    def _disconnect_current_task(self) -> None:
        """Disconnect signals from current task (if any)"""
        if self._current_task is None:
            return

        try:
            self._current_task.signals.status_changed.disconnect(self.benchmark_status_events)
            self._current_task.signals.log_message.disconnect(self.benchmark_output_events)
            self._current_task.signals.progress.disconnect(self.benchmark_progress_events)
        except TypeError:
            # Signals might not be connected, ignore
            pass
        finally:
            self._current_task = None
            self._current_run_id = None
