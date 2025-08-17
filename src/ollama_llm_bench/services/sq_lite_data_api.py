import logging
import sqlite3
from pathlib import Path
from typing import List, override

from ollama_llm_bench.core.interfaces import DataApi
from ollama_llm_bench.core.models import (BenchmarkResult, BenchmarkResultStatus, BenchmarkRun, BenchmarkRunStatus)
from ollama_llm_bench.core.sql_constants import (
    DB_SCHEMA,
    DELETE_BENCHMARK_RUN,
    DELETE_RESULT, INSERT_BENCHMARK_RUN, INSERT_RESULT,
    SELECT_ALL_BENCHMARK_RUNS,
    SELECT_BENCHMARK_RUNS_BY_STATUS,
    SELECT_BENCHMARK_RUN_BY_ID,
    SELECT_RESULTS_BY_RUN_ID,
    SELECT_RESULTS_BY_RUN_ID_AND_STATUS,
    SELECT_RESULT_BY_ID,
    UPDATE_BENCHMARK_RUN, UPDATE_RESULT,
)

logger = logging.getLogger(__name__)


class SqLiteDataApi(DataApi):
    """
    SQLite-based implementation of DataApi for persistent storage of benchmark data.
    Uses a local SQLite database to store runs, results, and metadata.
    """

    _RUN_ID_INDEX = 0
    _TIMESTAMP_INDEX = 1
    _JUDGE_MODEL_INDEX = 2
    _STATUS_INDEX = 3

    _RESULT_ID_INDEX = 0
    _RUN_ID_RESULTS_INDEX = 1
    _TASK_ID_INDEX = 2
    _MODEL_NAME_INDEX = 3
    _STATUS_RESULTS_INDEX = 4
    _LLM_RESPONSE_INDEX = 5
    _TIME_TAKEN_MS_INDEX = 6
    _TOKENS_GENERATED_INDEX = 7
    _EVALUATION_SCORE_INDEX = 8
    _EVALUATION_REASON_INDEX = 9
    _ERROR_MESSAGE_INDEX = 10

    def __init__(self, db_path: Path):
        """
        Initialize the SQLite data access layer.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """
        Initialize the database schema by creating required tables if they don't exist.
        """
        logger.debug("Initializing database schema")
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(DB_SCHEMA)

    @override
    def create_benchmark_run(self, benchmark_run: BenchmarkRun) -> int:
        """
        Store a new benchmark run and assign a unique identifier.

        Args:
            benchmark_run: The benchmark run to persist.

        Returns:
            Unique ID assigned to the created run.
        """
        logger.debug("Creating benchmark run: %s", benchmark_run)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                INSERT_BENCHMARK_RUN,
                (
                    benchmark_run.timestamp,
                    benchmark_run.judge_model,
                    benchmark_run.status.value
                ),
            )
            run_id = cursor.lastrowid
        logger.info("Created benchmark run with ID %d", run_id)
        return run_id

    @override
    def retrieve_benchmark_run(self, run_id: int) -> BenchmarkRun:
        """
        Fetch a specific benchmark run by its identifier.

        Args:
            run_id: Unique ID of the run to retrieve.

        Returns:
            The requested benchmark run.

        Raises:
            ValueError: If no run with the given ID exists.
        """
        logger.debug("Retrieving benchmark run with ID %d", run_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                SELECT_BENCHMARK_RUN_BY_ID,
                (run_id,),
            )
            row = cursor.fetchone()

            if not row:
                logger.error("Benchmark run with ID %d not found", run_id)
                raise ValueError(f"Benchmark run with ID {run_id} not found")

            return BenchmarkRun(
                run_id=row[self._RUN_ID_INDEX],
                timestamp=row[self._TIMESTAMP_INDEX],
                judge_model=row[self._JUDGE_MODEL_INDEX],
                status=BenchmarkRunStatus(row[self._STATUS_INDEX]),
            )

    @override
    def retrieve_benchmark_runs(self) -> List[BenchmarkRun]:
        """
        Retrieve all stored benchmark runs.

        Returns:
            List of all benchmark runs, empty if none exist.
        """
        logger.debug("Retrieving all benchmark runs")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(SELECT_ALL_BENCHMARK_RUNS)
            rows = cursor.fetchall()

            results = [
                BenchmarkRun(
                    run_id=row[self._RUN_ID_INDEX],
                    timestamp=row[self._TIMESTAMP_INDEX],
                    judge_model=row[self._JUDGE_MODEL_INDEX],
                    status=BenchmarkRunStatus(row[self._STATUS_INDEX]),
                )
                for row in rows
            ]
            logger.debug("Retrieved %d benchmark runs", len(results))
            return results

    @override
    def retrieve_benchmark_runs_with_status(self, status: BenchmarkRunStatus) -> List[BenchmarkRun]:
        """
        Retrieve benchmark runs filtered by execution status.

        Args:
            status: Status to filter runs by.

        Returns:
            List of runs matching the specified status.
        """
        logger.debug("Retrieving benchmark runs with status %s", status.value)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                SELECT_BENCHMARK_RUNS_BY_STATUS,
                (status.value,),
            )
            rows = cursor.fetchall()

            results = [
                BenchmarkRun(
                    run_id=row[self._RUN_ID_INDEX],
                    timestamp=row[self._TIMESTAMP_INDEX],
                    judge_model=row[self._JUDGE_MODEL_INDEX],
                    status=BenchmarkRunStatus(row[self._STATUS_INDEX]),
                )
                for row in rows
            ]
            logger.debug("Retrieved %d benchmark runs with status %s", len(results), status.value)
            return results

    @override
    def update_benchmark_run(self, benchmark_run: BenchmarkRun) -> None:
        """
        Update an existing benchmark run in storage.

        Args:
            benchmark_run: The updated run instance to persist.
        """
        logger.debug("Updating benchmark run: %s", benchmark_run)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                UPDATE_BENCHMARK_RUN,
                (
                    benchmark_run.timestamp,
                    benchmark_run.judge_model,
                    benchmark_run.status.value,
                    benchmark_run.run_id
                ),
            )
        logger.info("Updated benchmark run with ID %d", benchmark_run.run_id)

    @override
    def delete_benchmark_run(self, run_id: int) -> None:
        """
        Remove a benchmark run and all associated results from storage.

        Args:
            run_id: Unique ID of the run to delete.
        """
        logger.debug("Deleting benchmark run with ID %d", run_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(DELETE_BENCHMARK_RUN, (run_id,))
            affected = cursor.rowcount
        if affected == 0:
            logger.warning("No benchmark run found with ID %d to delete", run_id)
        else:
            logger.info("Deleted benchmark run with ID %d (and cascaded results)", run_id)

    @override
    def create_benchmark_result(self, benchmark_result: BenchmarkResult) -> int:
        """
        Store a single benchmark result and assign a unique identifier.

        Args:
            benchmark_result: The result to persist.

        Returns:
            Unique ID assigned to the created result.
        """
        logger.debug("Creating benchmark result: %s", benchmark_result)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                INSERT_RESULT,
                (
                    benchmark_result.run_id,
                    benchmark_result.task_id,
                    benchmark_result.model_name,
                    benchmark_result.status.value,
                    benchmark_result.llm_response,
                    benchmark_result.time_taken_ms,
                    benchmark_result.tokens_generated,
                    benchmark_result.evaluation_score,
                    benchmark_result.evaluation_reason,
                    benchmark_result.error_message
                ),
            )
            result_id = cursor.lastrowid
        logger.info("Created benchmark result with ID %d", result_id)
        return result_id

    @override
    def create_benchmark_results(self, benchmark_results: List[BenchmarkResult]) -> None:
        """
        Store multiple benchmark results in bulk.

        Args:
            benchmark_results: List of results to persist.
        """
        logger.debug("Creating %d benchmark results", len(benchmark_results))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for result in benchmark_results:
                cursor.execute(
                    INSERT_RESULT,
                    (
                        result.run_id,
                        result.task_id,
                        result.model_name,
                        result.status.value,
                        result.llm_response,
                        result.time_taken_ms,
                        result.tokens_generated,
                        result.evaluation_score,
                        result.evaluation_reason,
                        result.error_message
                    ),
                )
        logger.info("Created %d benchmark results", len(benchmark_results))

    @override
    def retrieve_benchmark_result(self, result_id: int) -> BenchmarkResult:
        """
        Fetch a specific benchmark result by its identifier.

        Args:
            result_id: Unique ID of the result to retrieve.

        Returns:
            The requested benchmark result.

        Raises:
            ValueError: If no result with the given ID exists.
        """
        logger.debug("Retrieving benchmark result with ID %d", result_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                SELECT_RESULT_BY_ID,
                (result_id,),
            )
            row = cursor.fetchone()

            if not row:
                logger.error("Benchmark result with ID %d not found", result_id)
                raise ValueError(f"Benchmark result with ID {result_id} not found")

            return self._map_bench_result(row)

    def _map_bench_result(self, row) -> BenchmarkResult:
        """
        Map a database row to a BenchmarkResult object.

        Args:
            row: Tuple of values from the results table.

        Returns:
            Mapped BenchmarkResult instance.
        """
        return BenchmarkResult(
            result_id=row[self._RESULT_ID_INDEX],
            run_id=row[self._RUN_ID_RESULTS_INDEX],
            task_id=row[self._TASK_ID_INDEX],
            model_name=row[self._MODEL_NAME_INDEX],
            status=BenchmarkResultStatus(row[self._STATUS_RESULTS_INDEX]),
            llm_response=row[self._LLM_RESPONSE_INDEX],
            time_taken_ms=row[self._TIME_TAKEN_MS_INDEX],
            tokens_generated=row[self._TOKENS_GENERATED_INDEX],
            evaluation_score=row[self._EVALUATION_SCORE_INDEX],
            evaluation_reason=row[self._EVALUATION_REASON_INDEX],
            error_message=row[self._ERROR_MESSAGE_INDEX],
        )

    @override
    def retrieve_benchmark_results_for_run(self, run_id: int) -> List[BenchmarkResult]:
        """
        Retrieve all results associated with a specific benchmark run.

        Args:
            run_id: Unique ID of the parent run.

        Returns:
            List of results belonging to the specified run.
        """
        logger.debug("Retrieving results for benchmark run ID %d", run_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                SELECT_RESULTS_BY_RUN_ID,
                (run_id,),
            )
            rows = cursor.fetchall()

            results = [
                self._map_bench_result(row)
                for row in rows
            ]
            logger.debug("Retrieved %d results for run ID %d", len(results), run_id)
            return results

    @override
    def retrieve_benchmark_results_for_run_with_status(self, *, run_id: int, status: BenchmarkResultStatus) -> List[
        BenchmarkResult]:
        """
        Retrieve benchmark results for a run, filtered by status.

        Args:
            run_id: Unique ID of the parent run.
            status: Status to filter results by.

        Returns:
            List of results matching the run ID and status.
        """
        logger.debug("Retrieving results for run ID %d with status %s", run_id, status.value)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                SELECT_RESULTS_BY_RUN_ID_AND_STATUS,
                (run_id, status.value),
            )
            rows = cursor.fetchall()

            results = [
                self._map_bench_result(row)
                for row in rows
            ]
            logger.debug("Retrieved %d results for run ID %d with status %s", len(results), run_id, status.value)
            return results

    @override
    def update_benchmark_result(self, benchmark_result: BenchmarkResult) -> None:
        """
        Update an existing benchmark result in storage.

        Args:
            benchmark_result: The updated result instance to persist.
        """
        logger.debug("Updating benchmark result: %s", benchmark_result)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                UPDATE_RESULT,
                (
                    benchmark_result.run_id,
                    benchmark_result.task_id,
                    benchmark_result.model_name,
                    benchmark_result.status.value,
                    benchmark_result.llm_response,
                    benchmark_result.time_taken_ms,
                    benchmark_result.tokens_generated,
                    benchmark_result.evaluation_score,
                    benchmark_result.evaluation_reason,
                    benchmark_result.error_message,
                    benchmark_result.result_id
                ),
            )
        logger.info("Updated benchmark result with ID %d", benchmark_result.result_id)

    @override
    def delete_benchmark_result(self, result_id: int) -> None:
        """
        Remove a benchmark result from storage.

        Args:
            result_id: Unique ID of the result to delete.
        """
        logger.debug("Deleting benchmark result with ID %d", result_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(DELETE_RESULT, (result_id,))
            affected = cursor.rowcount
        if affected == 0:
            logger.warning("No benchmark result found with ID %d to delete", result_id)
        else:
            logger.info("Deleted benchmark result with ID %d", result_id)
