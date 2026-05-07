"""SQLite-backed implementation of DataApi for V2 benchmark data persistence."""

import contextlib
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import override

from ollama_llm_bench.backend.core.interfaces import DataApi
from ollama_llm_bench.backend.core.models import (
    AppSetting,
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
    PromptVariant,
    RunMode,
)
from ollama_llm_bench.backend.core.sql_constants import (
    DB_SCHEMA,
    DELETE_BENCHMARK_RUN,
    DELETE_PROMPT_VARIANTS_BY_RUN_ID,
    DELETE_RESULT,
    DELETE_RESULTS_BY_RUN_ID,
    INSERT_BENCHMARK_RUN,
    INSERT_PROMPT_VARIANT,
    INSERT_RESULT,
    MIGRATE_ADD_PERFORMANCE_COLUMNS,
    SELECT_ALL_APP_SETTINGS,
    SELECT_ALL_BENCHMARK_RUNS,
    SELECT_APP_SETTING_BY_KEY,
    SELECT_BENCHMARK_RUN_BY_ID,
    SELECT_BENCHMARK_RUNS_BY_STATUS,
    SELECT_PROMPT_VARIANTS_BY_RUN_ID,
    SELECT_RESULT_BY_ID,
    SELECT_RESULTS_BY_RUN_ID,
    SELECT_RESULTS_BY_RUN_ID_AND_STATUS,
    UPDATE_BENCHMARK_RUN,
    UPDATE_RESULT,
    UPDATE_RUN_PERF_ANALYSIS,
    UPSERT_APP_SETTING,
)

logger = logging.getLogger(__name__)


class SqLiteDataApi(DataApi):
    """SQLite-based implementation of DataApi for persistent storage of V2 benchmark data.

    Uses a local SQLite database with foreign keys enabled.  All rows are
    accessed via sqlite3.Row for named-column access.  Schema creation is
    applied automatically at construction time.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize the SQLite data access layer and ensure the schema is current.

        Args:
            db_path: Path to the SQLite database file; parent directories are
                created if absent.
        """
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Open a connection with Row factory and foreign-key enforcement.

        Returns:
            Configured sqlite3 Connection.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        """Create the V2 schema tables if absent and seed the schema version row."""
        logger.debug("Initializing database schema at %s", self._db_path)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(DB_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (2, datetime.now(UTC).isoformat()),
            )
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE benchmark_runs ADD COLUMN judge_summary TEXT")
            for stmt in MIGRATE_ADD_PERFORMANCE_COLUMNS.strip().splitlines():
                stmt = stmt.strip()
                if stmt:
                    with contextlib.suppress(sqlite3.OperationalError):
                        conn.execute(stmt)

    def _row_to_benchmark_run(self, row: sqlite3.Row) -> BenchmarkRun:
        """Build a BenchmarkRun from a sqlite3.Row using named column access.

        Args:
            row: Row returned from a benchmark_runs query.

        Returns:
            Populated BenchmarkRun dataclass instance.
        """
        task_file_paths: tuple[str, ...] = tuple(json.loads(row["task_file_paths"] or "[]"))
        return BenchmarkRun(
            run_id=row["run_id"],
            timestamp=row["timestamp"],
            run_mode=RunMode(row["run_mode"] or "full_grading"),
            judge_provider_id=row["judge_provider_id"] or "",
            judge_model=row["judge_model"],
            embedding_provider_id=row["embedding_provider_id"],
            embedding_model=row["embedding_model"],
            status=BenchmarkRunStatus(row["status"]),
            task_file_paths=task_file_paths,
            models_json=row["models_json"] or "[]",
            total_tasks=row["total_tasks"] or 0,
            completed_tasks=row["completed_tasks"] or 0,
            judge_summary=row["judge_summary"],
            performance_config=row["performance_config"],
            perf_analysis_result=row["perf_analysis_result"],
        )

    def _row_to_benchmark_result(self, row: sqlite3.Row) -> BenchmarkResult:
        """Build a BenchmarkResult from a sqlite3.Row using named column access.

        Integer-stored booleans are converted to Python bool.

        Args:
            row: Row returned from a benchmark_results query.

        Returns:
            Populated BenchmarkResult dataclass instance.
        """
        return BenchmarkResult(
            result_id=row["result_id"],
            run_id=row["run_id"],
            run_type=row["run_type"] or "",
            created_at=row["created_at"] or "",
            completed_at=row["completed_at"],
            provider_id=row["provider_id"] or "",
            provider_type=row["provider_type"] or "",
            model_name=row["model_name"],
            model_family=row["model_family"],
            model_size_b=row["model_size_b"],
            quantization_label=row["quantization_label"],
            task_id=row["task_id"],
            task_category=row["task_category"] or "",
            task_type=row["task_type"] or "",
            task_difficulty=row["task_difficulty"],
            response_scope=row["response_scope"],
            source_language=row["source_language"],
            target_language=row["target_language"],
            prompt_version=row["prompt_version"] or "v1",
            prompt_hash=row["prompt_hash"] or "",
            user_prompt_sent=row["user_prompt_sent"] or "",
            system_prompt_sent=row["system_prompt_sent"],
            golden_answer=row["golden_answer"] or "",
            raw_response=row["raw_response"],
            sanitized_response=row["sanitized_response"],
            response_char_length=row["response_char_length"],
            has_thinking_block=bool(row["has_thinking_block"]),
            status=BenchmarkResultStatus(row["status"] or "NOT_COMPLETED"),
            total_time_ms=row["total_time_ms"],
            ttft_ms=row["ttft_ms"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            tokens_per_second=row["tokens_per_second"],
            rule_check_result=row["rule_check_result"],
            rule_check_flag=row["rule_check_flag"],
            rule_check_resolved=bool(row["rule_check_resolved"]),
            keyword_check_result=row["keyword_check_result"],
            missing_exact_terms=row["missing_exact_terms"],
            found_forbidden_terms=row["found_forbidden_terms"],
            semantic_term_scores=row["semantic_term_scores"],
            keyword_check_resolved=bool(row["keyword_check_resolved"]),
            cosine_similarity=row["cosine_similarity"],
            cosine_embedding_model=row["cosine_embedding_model"],
            cosine_strategy=row["cosine_strategy"],
            cosine_auto_pass=bool(row["cosine_auto_pass"]),
            cosine_resolved=bool(row["cosine_resolved"]),
            judge_result=row["judge_result"],
            judge_score=row["judge_score"],
            judge_reasoning=row["judge_reasoning"],
            judge_prompt_template=row["judge_prompt_template"],
            judge_time_ms=row["judge_time_ms"],
            judge_completion_tokens=row["judge_completion_tokens"],
            final_verdict=row["final_verdict"],
            resolution_layer=row["resolution_layer"],
            has_inference_error=bool(row["has_inference_error"]),
            inference_error_message=row["inference_error_message"],
            has_judge_error=bool(row["has_judge_error"]),
            judge_error_message=row["judge_error_message"],
        )

    # ------------------------------------------------------------------
    # BenchmarkRun CRUD
    # ------------------------------------------------------------------

    @override
    def create_benchmark_run(self, benchmark_run: BenchmarkRun) -> int:
        """Store a new benchmark run and return its assigned row ID.

        Args:
            benchmark_run: The benchmark run to persist.

        Returns:
            Unique integer ID assigned to the created run.

        Raises:
            RuntimeError: If the INSERT returns no lastrowid.
        """
        logger.debug("Creating benchmark run: timestamp=%s", benchmark_run.timestamp)
        task_file_paths_json = json.dumps(list(benchmark_run.task_file_paths))
        with self._get_connection() as conn:
            cursor = conn.execute(
                INSERT_BENCHMARK_RUN,
                (
                    benchmark_run.timestamp,
                    benchmark_run.run_mode,
                    benchmark_run.judge_provider_id,
                    benchmark_run.judge_model,
                    benchmark_run.embedding_provider_id,
                    benchmark_run.embedding_model,
                    benchmark_run.status,
                    task_file_paths_json,
                    benchmark_run.models_json,
                    benchmark_run.total_tasks,
                    benchmark_run.completed_tasks,
                    benchmark_run.judge_summary,
                    benchmark_run.performance_config,
                    benchmark_run.perf_analysis_result,
                ),
            )
            run_id = cursor.lastrowid
        if run_id is None:
            raise RuntimeError("INSERT_BENCHMARK_RUN returned no lastrowid — database invariant violated.")
        logger.info("Created benchmark run with ID %d", run_id)
        return run_id

    @override
    def retrieve_benchmark_run(self, run_id: int) -> BenchmarkRun:
        """Fetch a specific benchmark run by its identifier.

        Args:
            run_id: Unique ID of the run to retrieve.

        Returns:
            The requested BenchmarkRun instance.

        Raises:
            ValueError: If no run with the given ID exists.
        """
        logger.debug("Retrieving benchmark run with ID %d", run_id)
        with self._get_connection() as conn:
            row = conn.execute(SELECT_BENCHMARK_RUN_BY_ID, (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Benchmark run with ID {run_id} not found")
        return self._row_to_benchmark_run(row)

    @override
    def retrieve_benchmark_runs(self) -> list[BenchmarkRun]:
        """Retrieve all stored benchmark runs.

        Returns:
            List of all BenchmarkRun records; empty if none exist.
        """
        logger.debug("Retrieving all benchmark runs")
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_ALL_BENCHMARK_RUNS).fetchall()
        results = [self._row_to_benchmark_run(row) for row in rows]
        logger.debug("Retrieved %d benchmark runs", len(results))
        return results

    @override
    def retrieve_benchmark_runs_with_status(self, status: BenchmarkRunStatus) -> list[BenchmarkRun]:
        """Retrieve benchmark runs filtered by execution status.

        Args:
            status: Status to filter runs by.

        Returns:
            List of BenchmarkRun records matching the given status.
        """
        logger.debug("Retrieving benchmark runs with status %s", status)
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_BENCHMARK_RUNS_BY_STATUS, (status,)).fetchall()
        results = [self._row_to_benchmark_run(row) for row in rows]
        logger.debug("Retrieved %d runs with status %s", len(results), status)
        return results

    @override
    def update_benchmark_run(self, benchmark_run: BenchmarkRun) -> None:
        """Update an existing benchmark run in storage.

        Args:
            benchmark_run: The updated BenchmarkRun instance.
        """
        logger.debug("Updating benchmark run ID %d", benchmark_run.run_id)
        task_file_paths_json = json.dumps(list(benchmark_run.task_file_paths))
        with self._get_connection() as conn:
            conn.execute(
                UPDATE_BENCHMARK_RUN,
                (
                    benchmark_run.timestamp,
                    benchmark_run.run_mode,
                    benchmark_run.judge_provider_id,
                    benchmark_run.judge_model,
                    benchmark_run.embedding_provider_id,
                    benchmark_run.embedding_model,
                    benchmark_run.status,
                    task_file_paths_json,
                    benchmark_run.models_json,
                    benchmark_run.total_tasks,
                    benchmark_run.completed_tasks,
                    benchmark_run.judge_summary,
                    benchmark_run.performance_config,
                    benchmark_run.perf_analysis_result,
                    benchmark_run.run_id,
                ),
            )
        logger.info("Updated benchmark run with ID %d", benchmark_run.run_id)

    @override
    def delete_benchmark_run(self, run_id: int) -> None:
        """Remove a benchmark run from storage.

        Args:
            run_id: Unique ID of the run to delete.
        """
        logger.debug("Deleting benchmark run with ID %d", run_id)
        with self._get_connection() as conn:
            conn.execute(DELETE_PROMPT_VARIANTS_BY_RUN_ID, (run_id,))
            conn.execute(DELETE_RESULTS_BY_RUN_ID, (run_id,))
            cursor = conn.execute(DELETE_BENCHMARK_RUN, (run_id,))
            affected = cursor.rowcount
        if affected == 0:
            logger.warning("No benchmark run found with ID %d to delete", run_id)
        else:
            logger.info("Deleted benchmark run with ID %d", run_id)

    def update_run_perf_analysis(self, *, run_id: int, analysis: str) -> None:
        """Persist the LLM-generated performance analysis text for a finished run.

        Args:
            run_id: Unique ID of the benchmark run.
            analysis: Analysis text produced by the judge LLM.
        """
        logger.debug("Storing perf analysis for run_id=%d", run_id)
        with self._get_connection() as conn:
            conn.execute(UPDATE_RUN_PERF_ANALYSIS, (analysis, run_id))
        logger.info("Stored perf analysis for run_id=%d", run_id)

    # ------------------------------------------------------------------
    # BenchmarkResult CRUD
    # ------------------------------------------------------------------

    @override
    def create_benchmark_result(self, benchmark_result: BenchmarkResult) -> int:
        """Store a single benchmark result and return its assigned row ID.

        Args:
            benchmark_result: The result to persist.

        Returns:
            Unique integer ID assigned to the created result.

        Raises:
            RuntimeError: If the INSERT returns no lastrowid.
        """
        logger.debug(
            "Creating benchmark result for run_id=%d task_id=%s", benchmark_result.run_id, benchmark_result.task_id
        )
        with self._get_connection() as conn:
            cursor = conn.execute(INSERT_RESULT, self._result_to_params(benchmark_result))
            result_id = cursor.lastrowid
        if result_id is None:
            raise RuntimeError("INSERT_RESULT returned no lastrowid — database invariant violated.")
        logger.info("Created benchmark result with ID %d", result_id)
        return result_id

    @override
    def create_benchmark_results(self, benchmark_result: list[BenchmarkResult]) -> None:
        """Store multiple benchmark results in bulk.

        Args:
            benchmark_result: List of results to persist.
        """
        logger.debug("Creating %d benchmark results", len(benchmark_result))
        with self._get_connection() as conn:
            for result in benchmark_result:
                conn.execute(INSERT_RESULT, self._result_to_params(result))
        logger.info("Created %d benchmark results", len(benchmark_result))

    @override
    def retrieve_benchmark_result(self, result_id: int) -> BenchmarkResult:
        """Fetch a specific benchmark result by its identifier.

        Args:
            result_id: Unique ID of the result to retrieve.

        Returns:
            The requested BenchmarkResult instance.

        Raises:
            ValueError: If no result with the given ID exists.
        """
        logger.debug("Retrieving benchmark result with ID %d", result_id)
        with self._get_connection() as conn:
            row = conn.execute(SELECT_RESULT_BY_ID, (result_id,)).fetchone()
        if row is None:
            raise ValueError(f"Benchmark result with ID {result_id} not found")
        return self._row_to_benchmark_result(row)

    @override
    def retrieve_benchmark_results_for_run(self, run_id: int) -> list[BenchmarkResult]:
        """Retrieve all results associated with a specific benchmark run.

        Args:
            run_id: Unique ID of the parent benchmark run.

        Returns:
            List of BenchmarkResult records belonging to the run; empty if none exist.
        """
        logger.debug("Retrieving results for run ID %d", run_id)
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_RESULTS_BY_RUN_ID, (run_id,)).fetchall()
        results = [self._row_to_benchmark_result(row) for row in rows]
        logger.debug("Retrieved %d results for run ID %d", len(results), run_id)
        return results

    @override
    def retrieve_benchmark_results_for_run_with_status(
        self, *, run_id: int, status: BenchmarkResultStatus
    ) -> list[BenchmarkResult]:
        """Retrieve benchmark results for a run, filtered by status.

        Args:
            run_id: Unique ID of the parent benchmark run.
            status: Status to filter results by.

        Returns:
            List of BenchmarkResult records matching the run ID and status.
        """
        logger.debug("Retrieving results for run ID %d with status %s", run_id, status)
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_RESULTS_BY_RUN_ID_AND_STATUS, (run_id, status)).fetchall()
        results = [self._row_to_benchmark_result(row) for row in rows]
        logger.debug("Retrieved %d results for run ID %d with status %s", len(results), run_id, status)
        return results

    @override
    def update_benchmark_result(self, benchmark_result: BenchmarkResult) -> None:
        """Update an existing benchmark result in storage.

        Args:
            benchmark_result: The updated BenchmarkResult instance.
        """
        logger.debug("Updating benchmark result ID %d", benchmark_result.result_id)
        params = self._result_to_update_params(benchmark_result)
        with self._get_connection() as conn:
            conn.execute(UPDATE_RESULT, params)
        logger.info("Updated benchmark result with ID %d", benchmark_result.result_id)

    @override
    def delete_benchmark_result(self, result_id: int) -> None:
        """Remove a benchmark result from storage.

        Args:
            result_id: Unique ID of the result to delete.
        """
        logger.debug("Deleting benchmark result with ID %d", result_id)
        with self._get_connection() as conn:
            cursor = conn.execute(DELETE_RESULT, (result_id,))
            affected = cursor.rowcount
        if affected == 0:
            logger.warning("No benchmark result found with ID %d to delete", result_id)
        else:
            logger.info("Deleted benchmark result with ID %d", result_id)

    # ------------------------------------------------------------------
    # AppSettings
    # ------------------------------------------------------------------

    @override
    def get_app_setting(self, key: str) -> AppSetting | None:
        """Retrieve an app setting by key, or None if not set.

        Args:
            key: Setting key to look up.

        Returns:
            The AppSetting if found, or None if the key is not stored.
        """
        with self._get_connection() as conn:
            row = conn.execute(SELECT_APP_SETTING_BY_KEY, (key,)).fetchone()
        if row is None:
            return None
        return AppSetting(key=row["key"], value=row["value"], updated_at=row["updated_at"])

    @override
    def set_app_setting(self, *, key: str, value: str) -> None:
        """Persist or update an app setting key-value pair.

        Args:
            key: Setting key to create or overwrite.
            value: New value to store for the key.
        """
        updated_at = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute(UPSERT_APP_SETTING, (key, value, updated_at))
        logger.debug("Set app setting key=%s", key)

    @override
    def get_all_app_settings(self) -> list[AppSetting]:
        """Retrieve all stored app settings.

        Returns:
            List of all AppSetting records; empty if none exist.
        """
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_ALL_APP_SETTINGS).fetchall()
        return [AppSetting(key=row["key"], value=row["value"], updated_at=row["updated_at"]) for row in rows]

    # ------------------------------------------------------------------
    # PromptVariants
    # ------------------------------------------------------------------

    @override
    def create_prompt_variant(self, variant: PromptVariant) -> None:
        """Store a new prompt variant for a Prompt Eval run.

        Args:
            variant: PromptVariant record to persist.
        """
        logger.debug("Creating prompt variant id=%s for run_id=%d", variant.variant_id, variant.run_id)
        with self._get_connection() as conn:
            conn.execute(
                INSERT_PROMPT_VARIANT,
                (
                    variant.variant_id,
                    variant.run_id,
                    variant.variant_label,
                    variant.system_prompt,
                    variant.user_prompt_template,
                    variant.created_at,
                ),
            )
        logger.info("Created prompt variant id=%s", variant.variant_id)

    @override
    def retrieve_prompt_variants_for_run(self, run_id: int) -> list[PromptVariant]:
        """Retrieve all prompt variants associated with a benchmark run.

        Args:
            run_id: Unique ID of the parent benchmark run.

        Returns:
            List of PromptVariant records for the run; empty if none exist.
        """
        logger.debug("Retrieving prompt variants for run_id=%d", run_id)
        with self._get_connection() as conn:
            rows = conn.execute(SELECT_PROMPT_VARIANTS_BY_RUN_ID, (run_id,)).fetchall()
        return [
            PromptVariant(
                variant_id=row["variant_id"],
                run_id=row["run_id"],
                variant_label=row["variant_label"],
                system_prompt=row["system_prompt"],
                user_prompt_template=row["user_prompt_template"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Private parameter builders
    # ------------------------------------------------------------------

    def _result_to_params(self, r: BenchmarkResult) -> tuple[object, ...]:
        """Build the INSERT parameter tuple for a BenchmarkResult.

        Follows the column order declared in INSERT_RESULT.

        Args:
            r: BenchmarkResult to serialize.

        Returns:
            Tuple of 57 values matching the INSERT_RESULT placeholder order.
        """
        return (
            r.run_id,
            r.run_type,
            r.created_at,
            r.completed_at,
            r.provider_id,
            r.provider_type,
            r.model_name,
            r.model_family,
            r.model_size_b,
            r.quantization_label,
            r.task_id,
            r.task_category,
            r.task_type,
            r.task_difficulty,
            r.response_scope,
            r.source_language,
            r.target_language,
            r.prompt_version,
            r.prompt_hash,
            r.user_prompt_sent,
            r.system_prompt_sent,
            r.golden_answer,
            r.raw_response,
            r.sanitized_response,
            r.response_char_length,
            int(r.has_thinking_block),
            r.status,
            r.total_time_ms,
            r.ttft_ms,
            r.prompt_tokens,
            r.completion_tokens,
            r.tokens_per_second,
            r.rule_check_result,
            r.rule_check_flag,
            int(r.rule_check_resolved),
            r.keyword_check_result,
            r.missing_exact_terms,
            r.found_forbidden_terms,
            r.semantic_term_scores,
            int(r.keyword_check_resolved),
            r.cosine_similarity,
            r.cosine_embedding_model,
            r.cosine_strategy,
            int(r.cosine_auto_pass),
            int(r.cosine_resolved),
            r.judge_result,
            r.judge_score,
            r.judge_reasoning,
            r.judge_prompt_template,
            r.judge_time_ms,
            r.judge_completion_tokens,
            r.final_verdict,
            r.resolution_layer,
            int(r.has_inference_error),
            r.inference_error_message,
            int(r.has_judge_error),
            r.judge_error_message,
        )

    def _result_to_update_params(self, r: BenchmarkResult) -> tuple[object, ...]:
        """Build the UPDATE parameter tuple for a BenchmarkResult.

        Follows the SET column order declared in UPDATE_RESULT and appends
        result_id as the WHERE parameter.

        Args:
            r: BenchmarkResult to serialize.

        Returns:
            Tuple of 58 values (57 SET values + result_id WHERE clause).
        """
        return (
            r.run_id,
            r.run_type,
            r.created_at,
            r.completed_at,
            r.provider_id,
            r.provider_type,
            r.model_name,
            r.model_family,
            r.model_size_b,
            r.quantization_label,
            r.task_id,
            r.task_category,
            r.task_type,
            r.task_difficulty,
            r.response_scope,
            r.source_language,
            r.target_language,
            r.prompt_version,
            r.prompt_hash,
            r.user_prompt_sent,
            r.system_prompt_sent,
            r.golden_answer,
            r.raw_response,
            r.sanitized_response,
            r.response_char_length,
            int(r.has_thinking_block),
            r.status,
            r.total_time_ms,
            r.ttft_ms,
            r.prompt_tokens,
            r.completion_tokens,
            r.tokens_per_second,
            r.rule_check_result,
            r.rule_check_flag,
            int(r.rule_check_resolved),
            r.keyword_check_result,
            r.missing_exact_terms,
            r.found_forbidden_terms,
            r.semantic_term_scores,
            int(r.keyword_check_resolved),
            r.cosine_similarity,
            r.cosine_embedding_model,
            r.cosine_strategy,
            int(r.cosine_auto_pass),
            int(r.cosine_resolved),
            r.judge_result,
            r.judge_score,
            r.judge_reasoning,
            r.judge_prompt_template,
            r.judge_time_ms,
            r.judge_completion_tokens,
            r.final_verdict,
            r.resolution_layer,
            int(r.has_inference_error),
            r.inference_error_message,
            int(r.has_judge_error),
            r.judge_error_message,
            r.result_id,
        )
